// The page script against the acceptance cases the Python rule is tested on.
// Run with `node --test tests/js/page.test.js`. Node's own test runner: no package, no install.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const page = require('../../src/sentier_diagnostics/page/diagnostics.js');
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'acceptance', 'cases.json'), 'utf8')).cases;

test('every case is drawn with the tone of its direction and the text it must have', () => {
  for (const c of cases) {
    const view = page.cellView(c.before, c.after, c.class, c.direction, c.band);
    assert.equal(view.tone, c.page.tone, c.id + ': ' + c.from);
    if (c.page.text !== undefined) assert.equal(view.text, c.page.text, c.id + ': ' + c.from);
    if (c.class === 'beyond 10x') assert.ok(view.text.length > 0 && view.mark === '»', c.id + ': never blank');
  }
});

test('the tone comes from the direction only, never from the ratio (A1)', () => {
  // two results below zero going further below zero: the ratio is 2, the direction is down
  assert.equal(page.cellView(-2, -4, 'differs', 'down', 'down, factor 1.25-2').tone, 'down');
  assert.equal(page.cellView(-4, -2, 'differs', 'up', 'up, factor 1.25-2').tone, 'up');
});

test('the page takes the class from the file and works out none (A2)', () => {
  // the file says agrees: the page draws agreement, whatever the numbers
  assert.equal(page.cellView(1, 2, 'agrees', null, null).text, '=');
  assert.equal(page.cellView(1e-12, 5e-12, 'near zero', null, null).text, '≈ 0');
});

test('a missing side is never shown as a number (A7)', () => {
  for (const [b, a, said] of [[null, 0, 'missing before'], [0.5, null, 'missing after'], [null, null, 'missing']]) {
    const view = page.cellView(b, a, 'missing', null, null);
    assert.equal(view.text, said);
    assert.doesNotMatch(view.text, /\d/);
  }
});

test('the order worst first is the order of the Python rule', () => {
  for (const c of cases) {
    const key = page.severityKey(c.before, c.after, c.class);
    assert.equal(key[0], c.severity[0], c.id);
    assert.ok(Math.abs(key[1] - c.severity[1]) <= 1e-12, c.id + ': ' + key[1] + ' against ' + c.severity[1]);
  }
});

test('numbers keep their sign and never read 0 when they are not', () => {
  assert.equal(page.formatNumber(-2e-6), '−2e−6');
  assert.equal(page.formatNumber(0), '0');
  assert.equal(page.formatNumber(1234.5), '1235');
  assert.equal(page.formatNumber(null), 'missing');
  assert.notEqual(page.percentText(1, 1.0000003), '0 %');
  assert.equal(page.shareText(0), '0 %');
  assert.notEqual(page.shareText(-0.00025), '−0.0 %');
});

test('the size filter hides small changes and keeps every value without a ratio', () => {
  assert.equal(page.sizeAtLeast('differs', 'up, factor 1.1-1.25', 1.25), false);
  assert.equal(page.sizeAtLeast('differs', 'up, factor 1.25-2', 1.25), true);
  assert.equal(page.sizeAtLeast('differs', 'down, factor 1-1.1', 0), true);
  for (const kind of ['zero reference', 'zero result', 'sign change', 'missing', 'beyond 10x']) {
    assert.equal(page.sizeAtLeast(kind, null, 10), true, kind);
  }
  assert.equal(page.sizeAtLeast('agrees', null, 1.1), false);
});

test('the page refuses a file of another format, and an older one', () => {
  assert.match(page.checkShape({ format: 'sentier-diagnostics/2' }), /shows sentier-diagnostics\/1 only/);
  assert.match(page.checkShape({ format: 'sentier/before-after/2' }), /not a diagnostics file/);
  const example = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'examples', 'diagnostics.json'), 'utf8'));
  assert.equal(page.checkShape(example), null);
});

test('two identical builds are a finding, not "not measured"', () => {
  assert.equal(page.noiseText({ measured: false, between: null, by: null }), 'not measured');
  assert.equal(page.noiseText({ measured: true, between: ['a', 'b'], by: { 'x:a': 0, 'x:b': 0 } }), 'identical between a and b');
  assert.equal(page.noiseText({ measured: true, between: ['a', 'b'], by: { 'x:a': 0, 'x:b': 2e-7 } }), 'measured between a and b');
});

test('noise that was not measured for an indicator is never "identical"', () => {
  const ids = ['x:a', 'x:b', 'x:c'];
  assert.equal(page.noiseText({ measured: true, between: ['a', 'b'], by: {} }, ids),
    'not measured: no result beyond the floor in both builds between a and b');
  assert.equal(page.noiseText({ measured: true, between: ['a', 'b'], by: { 'x:a': 0 } }, ids),
    'identical between a and b, for 1 of 3 indicators');
  assert.equal(page.noiseText({ measured: true, between: ['a', 'b'], by: { 'x:a': 0, 'x:b': 0, 'x:c': 0.21 } }, ids),
    'measured between a and b; large: up to 21 %');
});

test('only an https address becomes a link', () => {
  assert.equal(page.safeLink('https://example.org/a'), 'https://example.org/a');
  for (const bad of ['javascript:alert(1)', 'JAVASCRIPT:x', 'http://example.org', 'data:text/html,x', ' https://x', 'https://a b', null, 7]) {
    assert.equal(page.safeLink(bad), null, String(bad));
  }
});

test('a file with a part of the wrong shape is refused before anything is drawn', () => {
  const example = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'examples', 'diagnostics.json'), 'utf8'));
  for (const [key, value] of [['items', {}], ['counts', []], ['steps', null], ['indicators', []], ['counts', { steps: {} }]]) {
    assert.notEqual(page.checkShape({ ...example, [key]: value }), null, key + ': ' + JSON.stringify(value));
  }
});

test('one number style from 1e4 on, never the "e+" of toPrecision', () => {
  assert.equal(page.formatNumber(9999), '9999');
  assert.equal(page.formatNumber(12345), '1.235e4');
  assert.equal(page.formatNumber(1e6), '1e6');
  assert.equal(page.formatNumber(-123456), '−1.235e5');
  assert.equal(page.formatNumber(0.00042), '4.2e−4');
});

test('an item\'s whole difference is split by the steps, the sum of the shares shown (A18)', () => {
  const split = page.splitOf([1, 1.5, 1.75], [true, false], 'differs');
  assert.equal(split.state, 'split');
  assert.deepEqual(split.shares, [2 / 3, 1 / 3]);
  assert.equal(page.splitText(split), '100.0 %, of which nothing explains 33.3 %');
  // in floating point the shares need not add up to exactly 1: the page prints their sum
  const rounded = page.splitOf([0.1, 0.2, 0.7], [true, true], 'differs');
  assert.equal(page.splitText(rounded), page.shareText(rounded.shares[0] + rounded.shares[1]));
});

test('steps that cancel are said to cancel, not split into large shares of both signs (A18)', () => {
  const split = page.splitOf([1, 1e16, 1, 2], [true, true, true], 'differs');
  assert.equal(split.state, 'cancel');
  assert.match(page.splitText(split), /^not split: the steps cancel, their differences add up to 2e16 times/);
});

test('an item missing in any state is not split, not even for the steps before the gap (A18)', () => {
  assert.equal(page.splitOf([1, 2, null, 4], [true, true, true], 'differs').state, 'gap');
  assert.equal(page.splitOf([null, 2, 4], [true, true], 'missing').state, 'missing');
  assert.equal(page.splitOf([1, 1, 1], [true, true], 'agrees').state, 'still');
});

const dom = require('./dom.js');
const EXAMPLE = path.join(__dirname, '..', '..', 'examples');
const example = () => JSON.parse(fs.readFileSync(path.join(EXAMPLE, 'diagnostics.json'), 'utf8'));
const wheat = () => JSON.parse(fs.readFileSync(path.join(EXAMPLE, 'p01-fix-1.json'), 'utf8'));

test('the example page is drawn whole', () => {
  const drawn = dom.page(example(), { 'p01-fix-1.json': wheat() }, { standalone: true });
  assert.equal(drawn.byId.load.hidden, true, drawn.byId['load-error'].textContent);
  assert.equal(drawn.byId.content.hidden, false);
  assert.equal(drawn.byId.unchecked.hidden, true);
  assert.equal(drawn.document.title, example().title);
  const text = drawn.text();
  for (const said of ['Reproduction', 'Spread over steps', 'Not attributable', 'Water 2.4 %'.slice(0, 5)]) assert.ok(text.includes(said), said);
  assert.equal(drawn.byId['steps-table'].all().filter((n) => n.tagName === 'TR').length, 1 + example().steps.length);
  assert.ok(drawn.byId['grid-table'].all().some((n) => n.getAttribute('data-item') === 'p01'));
});

test('the steps table prints the file\'s counts of what moved, never a recount from the items (A2)', () => {
  const data = example();
  const moves = ['differs', 'beyond 10x', 'zero reference', 'zero result', 'sign change'];
  const drawn = dom.page(data);
  const rows = drawn.byId['steps-table'].all().filter((n) => n.tagName === 'TR').slice(1);
  data.steps.forEach((s, k) => {
    const said = Object.values(data.counts.steps[s.id]).reduce((a, b) => a + moves.reduce((m, c) => m + b.classes[c], 0), 0);
    assert.equal(rows[k].childNodes[5].textContent, String(said), s.id);
    const side = (name) => Object.values(data.counts.steps[s.id]).reduce((a, b) => a + b.missing[name] + b.missing.both, 0);
    assert.equal(rows[k].childNodes[13].textContent, String(side('before')), s.id + ': missing before');
    assert.equal(rows[k].childNodes[14].textContent, String(side('after')), s.id + ': missing after');
  });
  assert.notEqual(rows.map((r) => r.childNodes[13].textContent).join(), rows.map((r) => r.childNodes[14].textContent).join(),
    'the example has a step with missing values on one side only');
});

test('a share is signed against the whole difference, whichever way it goes (A18)', () => {
  // the whole way goes down: a step that goes down carries a positive share of it
  assert.deepEqual(page.splitOf([2, 1], [true], 'differs').shares, [1]);
  const split = page.splitOf([4, 5, 2], [true, true], 'differs');
  assert.deepEqual(split.shares, [-0.5, 1.5]);
  assert.equal(split.sum, 1);
});

test('step 0 is said to reproduce the published results only where the chain starts from them', () => {
  assert.equal(dom.page(example()).byId['steps-zero'].hidden, false);
  const built = example();
  built.states[0].kind = 'build';
  assert.equal(dom.page(built).byId['steps-zero'].hidden, true);
});

test('a local file says so at its top, a public one does not (A25)', () => {
  const local = example();
  local.audience = 'local';
  const drawn = dom.page(local);
  assert.equal(drawn.byId.audience.hidden, false);
  assert.ok(drawn.byId.audience.textContent.includes('Local file'));
  assert.equal(dom.page(example()).byId.audience.hidden, true);
});

test('a text by a model is drawn as a claim nobody checked (A9)', () => {
  const drawn = dom.page(example());
  const list = drawn.byId['explanation-list'];
  const model = list.childNodes.find((li) => li.seen().join(' ').includes('model'));
  assert.ok(model, 'the example has an explanation by a model');
  assert.ok(model.seen().join(' ').includes('A claim, not checked by a person'));
});

test('nothing drawn calls a move better or worse (A22)', () => {
  const drawn = dom.page(example(), { 'p01-fix-1.json': wheat() });
  drawn.open('item=p01');
  const html = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'sentier_diagnostics', 'page', 'body.html'), 'utf8')
    .replace(/<[^>]*>/g, ' ');
  const text = (drawn.text() + '\n' + html).toLowerCase();
  for (const word of ['better', 'worse', 'improve', 'closer']) assert.ok(!text.includes(word), word);
});

test('the item view splits only what can be split and draws the breakdown of its own step', () => {
  const drawn = dom.page(example(), { 'p01-fix-1.json': wheat() });
  drawn.open('item=p01');
  const body = drawn.byId['item-body'].seen().join(' ');
  assert.ok(body.includes('What it is made of'));
  assert.ok(body.includes('Fertiliser') || body.includes('Total'), 'the breakdown is drawn');
  assert.ok(/100\.0 %/.test(body), 'the sum of the shares');
  drawn.open('item=p03'); // barley: no water use in the rebuilt state
  const barley = drawn.byId['item-body'];
  const water = barley.querySelector('table[data-indicator="x:water"]');
  const shares = water.all().filter((n) => n.tagName === 'TR').slice(1, -1).map((tr) => tr.childNodes[5].textContent);
  assert.deepEqual(shares, shares.map(() => '—'));
  assert.ok(water.seen().join(' ').includes('not split: missing in a state between'));
});

test('a breakdown named by another item is not drawn under it (issue 5)', () => {
  const data = example();
  const rice = data.items.find((i) => i.id === 'p05');
  rice.breakdowns = { total: 'p01-fix-1.json' };
  const drawn = dom.page(data, { 'p01-fix-1.json': wheat() });
  drawn.open('item=p05');
  const body = drawn.byId['item-body'].seen().join(' ');
  assert.ok(body.includes('is of another product or another step: not drawn'), body.slice(-300));
});

test('a breakdown of the right step and another item is not drawn under it (issue 5)', () => {
  const data = example();
  const step = Object.keys(data.items.find((i) => i.id === 'p01').breakdowns)[0];
  const rice = data.items.find((i) => i.id === 'p05');
  rice.breakdowns = { [step]: 'p01-fix-1.json' };
  const drawn = dom.page(data, { 'p01-fix-1.json': wheat() });
  drawn.open('item=p05');
  const body = drawn.byId['item-body'].seen().join(' ');
  assert.ok(body.includes('is of another product or another step: not drawn'), body.slice(-300));
});

test('a file the page cannot draw draws nothing', () => {
  const data = example();
  data.counts.total = null;
  const drawn = dom.page(data);
  assert.equal(drawn.byId.content.hidden, true);
  assert.equal(drawn.byId.load.hidden, false);
  assert.equal(drawn.byId.title.textContent, '');
});

// ------------------------------------------------------------------ the matrix and the drawer

const local = () => JSON.parse(fs.readFileSync(path.join(EXAMPLE, 'local', 'diagnostics.json'), 'utf8'));
const full = () => JSON.parse(fs.readFileSync(path.join(EXAMPLE, 'local', 'matrix.json'), 'utf8'));
const gridRows = (drawn) => drawn.byId['grid-table'].querySelectorAll('tr[data-item]');

test('the band the page names for a matrix row is the band of the Python rule', () => {
  for (const c of cases) {
    if (c.class !== 'differs' && c.class !== 'beyond 10x') continue;
    assert.equal(page.bandOf(c.before, c.after, c.class, c.direction), c.band, c.id);
  }
});

test('a ratio never reads 1 when it is not, nor Infinity', () => {
  assert.equal(page.ratioText(2, 3), '1.5');
  assert.equal(page.ratioText(-2, -4), '2');
  assert.equal(page.ratioText(1, 1.0000003), '1 + 3e−7');
  assert.equal(page.ratioText(1, 0.9999), '1 − 1e−4');
  assert.equal(page.ratioText(1e-300, 1e300), '1e600');
  assert.equal(page.ratioText(1e300, 1e-300), '1e−600');
});

test('the matrix the Python writes is one the page takes, and the rows are the file\'s', () => {
  const data = local();
  assert.equal(page.checkMatrix(full(), data), null);
  const rows = page.matrixRows(full(), data);
  assert.equal(rows.length, data.items_count.all);
  for (const item of data.items) {
    const row = rows.find((r) => r.id === item.id);
    assert.deepEqual(row.values, item.values, item.id);
    assert.deepEqual(row.classes, item.classes, item.id);
    assert.deepEqual(row.directions, item.directions, item.id);
    assert.deepEqual(row.verdicts, item.verdicts, item.id);
  }
});

test('a matrix of another file, or of another shape, is refused', () => {
  const data = local();
  const other = full(); other.of.title = 'Another';
  assert.match(page.checkMatrix(other, data), /another file/);
  const short = full(); short.classes[0] = short.classes[0].slice(1);
  assert.match(page.checkMatrix(short, data), /class code/);
  const wrong = full(); wrong.values[2][0] = 'x';
  assert.match(page.checkMatrix(wrong, data), /not a number/);
  const fewer = full(); fewer.items.pop(); fewer.values.pop(); fewer.classes.pop(); fewer.verdicts.pop();
  assert.match(page.checkMatrix(fewer, data), /says 10 items/);
});

test('the grid shows the listed items, says so, and every item once the matrix is here', () => {
  const data = local();
  const before = dom.page(data); // over file: the matrix.json the file names cannot be read
  assert.equal(gridRows(before).length, data.items.length);
  assert.match(before.byId['matrix-said'].textContent, /not loaded: matrix\.json is read over http only/);
  assert.match(before.byId['grid-said'].textContent, new RegExp('of ' + data.items.length + ' products, among the ' + data.items.length + ' products in this file; ' + data.items_count.not_listed + ' more'));
  const after = dom.page(data, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: full() } });
  assert.equal(gridRows(after).length, data.items_count.all);
  assert.match(after.byId['matrix-said'].textContent, /matrix of all 10 products is loaded/);
  assert.match(before.byId.tier.textContent, /6 of the \d+ products worth a look are in this file; \d+ are not\./);
  assert.match(after.byId.tier.textContent, /All 10 are loaded from the matrix; 6 of the \d+ worth a look are listed in this file\./);
  assert.equal(after.byId['grid-table'].all().filter((n) => n.className === 'sd-listed').length, data.items.length);
});

test('a matrix beside the page is loaded as a script after the page is drawn', () => {
  const drawn = dom.page(local(), undefined, { attributes: { 'data-sd-matrix': 'matrix.js', 'data-sd-base': 'runs/1/' } });
  const script = drawn.head.querySelector('script[src]');
  assert.equal(script.getAttribute('src'), 'runs/1/matrix.js');
  assert.match(drawn.byId['matrix-said'].textContent, /^Loading/);
  drawn.context.SENTIER_DIAGNOSTICS_MATRIX = full();
  script.onload();
  assert.equal(gridRows(drawn).length, 10);
});

test('a matrix is fetched as JSON over http, and one of another file is not drawn', async () => {
  const served = (m) => () => Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(m)) });
  const drawn = dom.page(local(), undefined, { protocol: 'https:', fetch: served(full()) });
  await new Promise((done) => setImmediate(done));
  assert.equal(gridRows(drawn).length, 10);
  const other = full(); other.of.steps = other.of.steps.slice().reverse();
  const refused = dom.page(local(), undefined, { protocol: 'https:', fetch: served(other) });
  await new Promise((done) => setImmediate(done));
  assert.equal(gridRows(refused).length, 6);
  assert.match(refused.byId['matrix-said'].textContent, /not loaded: it is the matrix of another file/);
});

test('a grid cell is the ratio after ÷ before, coloured by its direction', () => {
  const drawn = dom.page(example());
  const wheat = gridRows(drawn).find((tr) => tr.getAttribute('data-item') === 'p01');
  const item = example().items.find((i) => i.id === 'p01');
  const values = item.values['x:climate'];
  const cell = wheat.childNodes[3];
  assert.equal(item.classes['x:climate'][4], 'differs');
  assert.equal(cell.textContent, page.ratioText(values[0], values[values.length - 1]));
  assert.match(cell.className, new RegExp('tone-' + item.directions['x:climate'][4]));
});

test('a heading sorts the grid by how far the two lie apart, the furthest first, and says so', () => {
  const data = example();
  const drawn = dom.page(data);
  const head = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]');
  const water = head.find((th) => th.getAttribute('title') && th.getAttribute('title').indexOf('Water') === 0);
  water.querySelector('button[type="button"]').dispatch('click', {});
  const after = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').find((th) => th.getAttribute('aria-sort'));
  assert.equal(after.getAttribute('aria-sort'), 'descending');
  const order = gridRows(drawn).map((tr) => tr.getAttribute('data-item'));
  const key = (id) => { const i = data.items.find((x) => x.id === id); const v = i.values['x:water']; return page.severityKey(v[0], v[v.length - 1], i.classes['x:water'][4]); };
  for (let k = 1; k < order.length; k++) assert.ok(page.compareKeys(key(order[k - 1]), key(order[k])) <= 0, order.join());
});

test('the grid draws 300 rows at a time', () => {
  const data = local();
  const m = full();
  const n = 650;
  const grown = { ...m, items: [], values: [], classes: [], verdicts: [] };
  for (let i = 0; i < n; i++) {
    const at = i % m.items.length;
    grown.items.push(i < m.items.length ? m.items[at] : [m.items[at][0] + '-' + i].concat(m.items[at].slice(1)));
    grown.values.push(m.values[at]); grown.classes.push(m.classes[at]); grown.verdicts.push(m.verdicts[at]);
  }
  data.matrix.items = n;
  const drawn = dom.page(data, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: grown } });
  assert.equal(gridRows(drawn).length, 300);
  assert.equal(drawn.byId['grid-more'].textContent, 'Show 300 more');
  drawn.byId['grid-more'].dispatch('click', {});
  drawn.byId['grid-more'].dispatch('click', {});
  assert.equal(gridRows(drawn).length, n);
  assert.equal(drawn.byId['grid-more'].hidden, true);
});

test('the drawer opens on an item of the matrix, says why first, and closes with Escape', () => {
  const data = local();
  const drawn = dom.page(data, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: full() } });
  const unlisted = full().items.map((r) => r[0]).find((id) => !data.items.some((i) => i.id === id));
  gridRows(drawn).find((tr) => tr.getAttribute('data-item') === unlisted).childNodes[0].dispatch('click', {});
  assert.equal(drawn.context.location.hash, 'item=' + unlisted);
  drawn.open('item=' + unlisted);
  assert.equal(drawn.byId.item.hidden, false);
  assert.match(drawn.byId['item-meta'].textContent, /from the matrix: not listed in this file/);
  assert.equal(drawn.byId['item-body'].childNodes[0].textContent, 'Why it differs');
  assert.equal(drawn.byId['item-title'].focused, true);
  drawn.root.dispatch('keydown', { key: 'Escape' });
  assert.equal(drawn.byId.item.hidden, true);
});

test('why it differs: the item\'s own explanations, then those of a step or indicator it moved in, never a "none" over a part', () => {
  const data = example();
  const drawn = dom.page(data);
  for (const item of data.items) {
    drawn.open('item=' + item.id);
    const why = drawn.byId['item-body'].childNodes[1];
    const own = data.explanations.filter((e) => e.about.item === item.id).length;
    const scopes = why.childNodes.map((li) => (li.childNodes[0].className === 'sd-scope' ? li.childNodes[0].textContent : 'none'));
    assert.equal(scopes.filter((s) => s === 'This product').length, own, item.id);
    assert.ok(scopes.indexOf('This product') <= 0 || scopes.slice(0, own).every((s) => s === 'This product'), item.id + ': its own first');
    if (scopes.includes('none')) assert.equal(why.childNodes.length, 1, item.id + ': "none" only where nothing is given');
  }
});

test('the page sets the title of a page of its own only, never a host\'s', () => {
  assert.equal(dom.page(example()).document.title, '');
  assert.equal(dom.page(example(), undefined, { standalone: true }).document.title, example().title);
});

test('the data can come from a global, as a site\'s own data.js sets it', () => {
  const drawn = dom.page(example(), { 'p01-fix-1.json': wheat() }, { globals: {} });
  assert.equal(drawn.byId.content.hidden, false);
  assert.equal(drawn.byId.unchecked.hidden, true);
});
