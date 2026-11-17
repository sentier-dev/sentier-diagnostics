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

test('a host page never offers to open a file; a page of its own does', () => {
  const host = dom.page(undefined);
  assert.equal(host.byId.load.hidden, false);
  assert.equal(host.byId['load-choose'].hidden, true);
  assert.match(host.byId['load-error'].textContent, /No diagnostics file came with this page/);
  const broken = example(); broken.counts.total = null;
  assert.equal(dom.page(broken).byId['load-choose'].hidden, true);
  const own = dom.page(undefined, undefined, { standalone: true });
  assert.equal(own.byId['load-choose'].hidden, false);
  assert.equal(own.byId['load-error'].textContent, '');
});

test('chips choose the comparison: the whole way first, then each step with what moved in it', () => {
  const data = example();
  const drawn = dom.page(data);
  const chips = () => drawn.byId.comparison.querySelectorAll('button[data-comp]');
  assert.deepEqual(chips().map((c) => c.getAttribute('data-comp')), ['total'].concat(data.steps.map((s) => s.id)));
  assert.deepEqual(chips().map((c) => c.getAttribute('aria-pressed')), ['true'].concat(data.steps.map(() => 'false')));
  const moved = (comp) => Object.values(comp === 'total' ? data.counts.total : data.counts.steps[comp])
    .reduce((sum, b) => sum + ['differs', 'beyond 10x', 'zero reference', 'zero result', 'sign change'].reduce((a, k) => a + b.classes[k], 0), 0);
  chips().forEach((chip) => assert.ok(chip.textContent.includes(moved(chip.getAttribute('data-comp')) + ' moved'), chip.textContent));
  // the unexplained step is flagged, the verdicts worth a look are marked
  const rebuilt = data.steps.findIndex((s) => !s.explained);
  assert.ok(rebuilt >= 0);
  assert.ok(chips()[rebuilt + 1].textContent.includes('!'));
  assert.match(chips()[rebuilt + 1].getAttribute('title'), /nothing explains it/);
  const claimed = data.steps.findIndex((s) => s.claim && Object.values(data.counts.steps[s.id]).some((b) => b.verdicts['not claimed']));
  assert.ok(chips()[claimed + 1].textContent.includes('■'), chips()[claimed + 1].textContent);
  // a click on a step's label chooses it, and the grid follows
  const label = chips()[2].childNodes[1]; // the label inside the chip: the click reaches the chip
  label.dispatch('click', {});
  assert.deepEqual(chips().map((c) => c.getAttribute('aria-pressed')), ['false', 'false', 'true'].concat(data.steps.slice(2).map(() => 'false')));
  assert.ok(drawn.byId['grid-region'].getAttribute('aria-label').endsWith(': Step 1: ' + data.steps[1].label + ', the furthest apart first'),
    drawn.byId['grid-region'].getAttribute('aria-label'));
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
  const cell = wheat.childNodes[2]; // name, group, then the first indicator: no unit column
  assert.equal(item.classes['x:climate'][4], 'differs');
  assert.equal(cell.textContent, page.ratioShort(values[0], values[values.length - 1]));
  assert.match(cell.className, new RegExp('tone-' + item.directions['x:climate'][4]));
  const heads = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').map((th) => th.textContent);
  assert.equal(heads.length, 2 + example().indicators.length);
  assert.ok(!heads.includes('Unit'));
});

test('a ratio in the grid has three significant digits, and never "Infinity"', () => {
  assert.equal(page.ratioShort(1, 1), '1.00');
  assert.equal(page.ratioShort(1, 1.0000003), '1.00');
  assert.equal(page.ratioShort(1, 0.984), '0.984');
  assert.equal(page.ratioShort(-2, -4.54), '2.27');
  assert.equal(page.ratioShort(1, 25), '25.0');
  assert.equal(page.ratioShort(1, 999.7), '1e3');
  assert.equal(page.ratioShort(1, 12345), '1.23e4');
  assert.equal(page.ratioShort(1, 0.004), '4e−3');
  assert.equal(page.ratioShort(1e-300, 1e300), '1e600');
  const noise = page.ratioView(1, 1.001, 'within noise', 'up', null);
  assert.deepEqual([noise.text, noise.mark, noise.tone], ['1.00', '~', 'noise']);
  const agrees = page.ratioView(2, 2, 'agrees', null, null);
  assert.deepEqual([agrees.text, agrees.tone, agrees.strength], ['1.00', 'none', 0]);
  assert.equal(page.ratioView(0, 0, 'agrees', null, null).text, '=');
  assert.equal(page.ratioView(-1, 2, 'sign change', 'up', null).text, '− → +');
});

test('every grid cell with a ratio shows it, agreeing ones too; the class is the tint and a mark', () => {
  const data = example();
  const drawn = dom.page(data);
  let agrees = 0, noise = 0;
  for (const tr of gridRows(drawn)) {
    const item = data.items.find((i) => i.id === tr.getAttribute('data-item'));
    data.indicators.forEach((ind, at) => {
      const cell = tr.childNodes[2 + at];
      const v = item.values[ind.id], before = v[0], after = v[v.length - 1], cls = item.classes[ind.id][4];
      const shared = before !== null && after !== null && before !== 0 && after !== 0 && (before > 0) === (after > 0);
      if (shared && ['agrees', 'within noise', 'differs', 'beyond 10x'].includes(cls)) {
        assert.ok(cell.textContent.startsWith(page.ratioShort(before, after)), item.id + ' ' + ind.id + ': ' + cell.textContent);
        if (cls === 'agrees') { agrees += 1; assert.match(cell.className, /tone-none/); }
        if (cls === 'within noise') { noise += 1; assert.match(cell.textContent, /~$/); }
      } else {
        assert.doesNotMatch(cell.textContent, /^\d/, item.id + ' ' + ind.id + ' (' + cls + '): ' + cell.textContent);
      }
      assert.notEqual(cell.textContent, '=');
    });
  }
  assert.ok(agrees > 5, 'agreeing cells were checked');
});

test('the grid opens with the items that lie furthest apart, and a second click goes back to that', () => {
  const data = example();
  data.items.reverse(); // the file lists them worst first already: the page must order them itself
  const drawn = dom.page(data);
  // the largest factor among the values that moved with a ratio first, then the worst value
  const worst = (id) => {
    const i = data.items.find((x) => x.id === id);
    let furthest = 0;
    const keys = data.indicators.map((ind) => {
      const v = i.values[ind.id], cls = i.classes[ind.id][4];
      if (cls === 'differs' || cls === 'beyond 10x') furthest = Math.max(furthest, Math.abs(Math.log10(Math.abs(v[v.length - 1] / v[0]))));
      return page.severityKey(v[0], v[v.length - 1], cls);
    });
    return [-furthest].concat(keys.sort(page.compareKeys)[0]);
  };
  const order = () => gridRows(drawn).map((tr) => tr.getAttribute('data-item'));
  const first = order();
  for (let k = 1; k < first.length; k++) assert.ok(page.compareKeys(worst(first[k - 1]), worst(first[k])) <= 0, first.join());
  assert.notDeepEqual(first, data.items.map((i) => i.id), 'the example is not already in that order');
  assert.match(drawn.byId['grid-region'].getAttribute('aria-label'), /, the furthest apart first$/);
  const button = () => drawn.byId['grid-table'].querySelectorAll('th[scope="col"]')[0].querySelector('button[type="button"]');
  button().dispatch('click', {});
  assert.doesNotMatch(drawn.byId['grid-region'].getAttribute('aria-label'), /furthest apart first/);
  button().dispatch('click', {});
  assert.deepEqual(order(), first);
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

test('the page\'s own sentences say the file\'s word for an item', () => {
  const data = example();
  data.item = { one: 'dataset', many: 'datasets' };
  const drawn = dom.page(data);
  const words = drawn.root.querySelectorAll('[data-sd-word]');
  assert.ok(words.length >= 4);
  const items = words.filter((span) => ['one', 'many'].includes(span.getAttribute('data-sd-word')));
  assert.ok(items.length >= 4);
  for (const span of items) assert.equal(span.textContent, span.getAttribute('data-sd-word') === 'many' ? 'datasets' : 'dataset');
  assert.equal(drawn.byId['item-close'].getAttribute('aria-label'), 'Close the dataset');
  assert.ok(drawn.byId['grid-region'].getAttribute('aria-label').startsWith('After divided by before, per dataset and indicator: The whole way'));
});

test('the page says the file\'s word for an indicator, and "indicator" where it gives none', () => {
  const plain = dom.page(example());
  const said = (drawn, value) => drawn.root.querySelectorAll('[data-sd-word]')
    .filter((span) => span.getAttribute('data-sd-word') === value).map((span) => span.textContent);
  assert.deepEqual([...new Set(said(plain, 'indicator'))], ['indicator']);
  const data = example();
  data.indicator = { one: 'impact category', many: 'impact categories' };
  const drawn = dom.page(data);
  assert.equal(drawn.byId.content.hidden, false);
  assert.ok(said(drawn, 'indicator').length >= 3);
  assert.deepEqual([...new Set(said(drawn, 'indicator'))], ['impact category']);
  assert.deepEqual(said(drawn, 'Indicator'), ['Impact category']);
  assert.ok(drawn.byId['grid-region'].getAttribute('aria-label').startsWith('After divided by before, per ' + data.item.one + ' and impact category: '));
  const text = drawn.text();
  assert.match(text, new RegExp(data.indicators.length + ' impact categories\\. '));
  assert.match(text, /One floor per impact category and reference unit/);
  assert.doesNotMatch(text.replace(data.about, ''), /\bindicators?\b/i);
});

test('a page refuses an indicator word that is not {one, many}', () => {
  const data = example();
  data.indicator = { one: 'impact category' };
  const drawn = dom.page(data);
  assert.equal(drawn.byId.content.hidden, true);
  assert.match(drawn.text(), /indicator word of the file is not \{one, many\}/);
});

test('steps count from 1 where the chain does not start from the published results', () => {
  const published = example();
  assert.equal(published.states[0].kind, 'published');
  const first = dom.page(published);
  assert.match(first.text(), /Step 0: /);
  assert.equal(first.byId['steps-zero'].hidden, false);
  const data = example();
  data.states[0].kind = 'build';
  const drawn = dom.page(data);
  assert.equal(drawn.byId.content.hidden, false);
  assert.equal(drawn.byId['steps-zero'].hidden, true);
  const text = drawn.text();
  assert.doesNotMatch(text, /Step 0\b/);
  data.steps.forEach((s, k) => assert.ok(text.includes('Step ' + (k + 1) + ': ' + s.label), s.label));
  const rows = drawn.byId['steps-table'].all().filter((n) => n.tagName === 'TR' && n.firstChild && n.firstChild.tagName === 'TD');
  assert.deepEqual(rows.map((row) => row.firstChild.textContent), data.steps.map((s, k) => String(k + 1)));
  drawn.open('item=' + encodeURIComponent(data.items[0].id));
  const drawer = drawn.byId['item-body'].seen().join(' ');
  assert.ok(drawer.includes('Step 1: ' + data.steps[0].label), drawer.slice(0, 200));
  assert.doesNotMatch(drawer, /Step 0\b/);
});


// ------------------------------------------------------------------ reviewing one step

const chips = (drawn) => drawn.byId.comparison.querySelectorAll('button[data-comp]');

test('choosing a step says its claim and what the claim found, under the chips, and the address keeps it', () => {
  const data = example();
  const drawn = dom.page(data);
  assert.match(drawn.byId['step-said'].textContent, /^The whole way: /);
  const k = data.steps.findIndex((s) => s.claim && s.claim.scope.length);
  const step = data.steps[k];
  chips(drawn)[k + 1].dispatch('click', {});
  const said = drawn.byId['step-said'].textContent;
  assert.ok(said.includes(step.claim.text), said);
  // what the claim found, from the file's own counts
  const look = ['off claim', 'not claimed', 'claimed, not moved'];
  const found = look.filter((v) => Object.values(data.counts.steps[step.id]).some((b) => b.verdicts[v]));
  if (found.length) found.forEach((v) => assert.ok(said.includes(v), v));
  else assert.match(said, /as claimed/);
  assert.equal(drawn.context.location.hash, 'step=' + encodeURIComponent(step.id));
  assert.equal(chips(drawn)[k + 1].getAttribute('aria-pressed'), 'true');
});

test('the matrix shows first the indicators in which the chosen comparison moved most', () => {
  const data = example();
  const drawn = dom.page(data);
  const moves = ['differs', 'beyond 10x', 'zero reference', 'zero result', 'sign change'];
  // what moved, and the missing values with it: missing is a finding, not stillness
  const moved = (comp, id) => moves.concat(['missing']).reduce((m, c) => m + (comp === 'total' ? data.counts.total : data.counts.steps[comp])[id].classes[c], 0);
  for (const comp of ['total'].concat(data.steps.map((s) => s.id))) {
    drawn.byId.comparison.querySelectorAll('button[data-comp="' + comp + '"]')[0].dispatch('click', {});
    const heads = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').slice(2);
    const counts = heads.map((th) => moved(comp, data.indicators.find((i) => th.getAttribute('title').indexOf(i.name) === 0).id));
    for (let k = 1; k < counts.length; k++) assert.ok(counts[k - 1] >= counts[k], comp + ': ' + counts.join());
    heads.forEach((th, k) => assert.equal(/sd-still/.test(th.className), counts[k] === 0, comp));
    // the cells of a quiet column are quiet too
    const row = gridRows(drawn)[0];
    const cells = row.childNodes.filter((n) => n.tagName === 'TD').slice(1); // after the group
    cells.forEach((td, k) => assert.equal(/sd-still/.test(td.className), counts[k] === 0, comp + ' cell ' + k));
  }
});

test('an address with a step opens the page on that step, and with an item on that item', () => {
  const data = example();
  const step = data.steps[2];
  const drawn = dom.page(data);
  drawn.open('step=' + encodeURIComponent(step.id) + '&item=' + encodeURIComponent(data.items[0].id));
  assert.equal(chips(drawn).find((c) => c.getAttribute('aria-pressed') === 'true').getAttribute('data-comp'), step.id);
  assert.equal(drawn.byId.item.hidden, false);
  // closing the item keeps the step
  drawn.byId['item-close'].dispatch('click', {});
  assert.equal(drawn.byId.item.hidden, true);
  assert.equal(drawn.context.location.hash, 'step=' + encodeURIComponent(step.id));
  // an unknown step falls back to the whole way
  drawn.open('step=nothing-of-the-kind');
  assert.equal(chips(drawn)[0].getAttribute('aria-pressed'), 'true');
});

test('the arrow keys move between the chips', () => {
  const data = example();
  const drawn = dom.page(data);
  drawn.byId.comparison.dispatch('keydown', { key: 'ArrowRight' });
  assert.equal(chips(drawn)[1].getAttribute('aria-pressed'), 'true');
  drawn.byId.comparison.dispatch('keydown', { key: 'ArrowLeft' });
  assert.equal(chips(drawn)[0].getAttribute('aria-pressed'), 'true');
  drawn.byId.comparison.dispatch('keydown', { key: 'ArrowLeft' }); // nothing before the whole way
  assert.equal(chips(drawn)[0].getAttribute('aria-pressed'), 'true');
});

const cards = (drawn) => drawn.byId['dist-cards'].childNodes;

test('a distribution card per indicator, in the order of the matrix, its bars the file\'s counts', () => {
  const data = example();
  const drawn = dom.page(data);
  for (const comp of ['total'].concat(data.steps.map((s) => s.id))) {
    drawn.byId.comparison.querySelectorAll('button[data-comp="' + comp + '"]')[0].dispatch('click', {});
    const heads = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').slice(2).map((th) => th.getAttribute('title'));
    const ids = cards(drawn).map((card) => card.getAttribute('data-indicator'));
    assert.equal(ids.length, data.indicators.length);
    ids.forEach((id, k) => assert.ok(heads[k].indexOf(data.indicators.find((i) => i.id === id).name) === 0, comp + ' ' + k));
    for (const card of cards(drawn)) {
      const block = (comp === 'total' ? data.counts.total : data.counts.steps[comp])[card.getAttribute('data-indicator')];
      const bars = card.childNodes[2].childNodes;
      const sum = bars.reduce((s, bar) => s + Number(bar.getAttribute('title').match(/: ([\d,]+) of/)[1].replace(/,/g, '')), 0);
      // every pair is in one bar: the bands split what moved and what agrees, the rest is a class
      assert.equal(sum, block.pairs, comp + ' ' + card.getAttribute('data-indicator'));
    }
  }
});

test('a median of after ÷ before only from every item, never from the listed ones', () => {
  const data = local();
  const listed = dom.page(data);
  for (const card of cards(listed)) assert.doesNotMatch(card.textContent, /Median/);
  assert.match(listed.byId['dist-said'].textContent, /need every product/);
  const loaded = dom.page(data, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: full() } });
  const rows = page.matrixRows(full(), data);
  const k = data.steps.length; // the whole way
  const card = cards(loaded)[0];
  const id = card.getAttribute('data-indicator');
  const ratios = rows.filter((r) => ['agrees', 'within noise', 'differs', 'beyond 10x'].includes(r.classes[id][k]))
    .map((r) => [r.values[id][0], r.values[id][r.values[id].length - 1]])
    .filter(([a, b]) => a && b && (a > 0) === (b > 0)).map(([a, b]) => b / a).sort((a, b) => a - b);
  const x = 0.5 * (ratios.length - 1), lo = Math.floor(x), hi = Math.ceil(x);
  const median = ratios[lo] + (ratios[hi] - ratios[lo]) * (x - lo);
  assert.ok(ratios.length > 0);
  const shown = Number(card.textContent.match(/Median of [\d ]+ ratios? ([\d.e−]+)/)[1].replace('−', '-'));
  assert.ok(Math.abs(shown - median) <= 5e-3 * Math.abs(median), shown + ' vs ' + median);
});

test('percentiles share one precision: the fewest digits that keep apart the ones that differ', () => {
  // a spread only the fifth digit shows
  const text = page.quantileTexts({ p10: 0.99981, median: 1.0, p90: 1.00042 });
  assert.notEqual(text[0], text[2]);
  assert.deepEqual(text, ['0.99981', '1.0000', '1.0004']);
  // never mixed: a 10th percentile that reads as exactly 1 beside a six-digit median
  assert.deepEqual(page.quantileTexts({ p10: 1.00004, median: 1.00005, p90: 1.00006 }), ['1.00004', '1.00005', '1.00006']);
  assert.deepEqual(page.quantileTexts({ p10: 0.999, median: 1, p90: 1.0001 }), ['0.99900', '1.0000', '1.0001']);
  assert.deepEqual(page.quantileTexts({ p10: 0.5, median: 1, p90: 2 }), ['0.500', '1.00', '2.00']);
  assert.deepEqual(page.quantileTexts({ p10: 1, median: 1, p90: 1 }), ['1.00', '1.00', '1.00']);
});

test('a card sorts the matrix by its indicator, and a heading marks its card', () => {
  const data = example();
  const drawn = dom.page(data);
  const card = cards(drawn)[1];
  const id = card.getAttribute('data-indicator');
  card.childNodes[0].childNodes[0].dispatch('click', {});
  const sorted = drawn.byId['grid-table'].querySelectorAll('th[aria-sort]');
  assert.equal(sorted.length, 1);
  assert.ok(sorted[0].getAttribute('title').indexOf(data.indicators.find((i) => i.id === id).name) === 0);
  assert.equal(cards(drawn)[1].childNodes[0].childNodes[0].getAttribute('aria-pressed'), 'true');
  assert.match(cards(drawn)[1].className, /sd-chosen/);
  // the heading of another indicator moves the mark to its card
  const other = cards(drawn)[0].getAttribute('data-indicator');
  const head = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').slice(2)
    .find((th) => th.getAttribute('title').indexOf(data.indicators.find((i) => i.id === other).name) === 0);
  head.childNodes[0].dispatch('click', {});
  assert.equal(cards(drawn)[0].childNodes[0].childNodes[0].getAttribute('aria-pressed'), 'true');
  assert.equal(cards(drawn)[1].childNodes[0].childNodes[0].getAttribute('aria-pressed'), 'false');
});

test('the bars of every card can be put on one scale, the share of all values (A21)', () => {
  const data = example();
  const drawn = dom.page(data);
  const heights = () => cards(drawn).map((card) => card.childNodes[2].childNodes.map((bar) => parseFloat(/height:([\d.]+)%/.exec(bar.getAttribute('style'))[1])));
  // each card to its own tallest bar: every card that has values reaches the top
  heights().forEach((h) => assert.equal(Math.max(...h), 100));
  const select = drawn.byId['dist-scale'];
  select.value = 'one';
  select.dispatch('change', { target: select });
  const one = heights();
  assert.equal(Math.max(...one.flat()), 100);
  // on one scale, a bar's height is its share of the values of its card, the same factor in every card
  const shares = cards(drawn).map((card, i) => {
    const block = data.counts.total[card.getAttribute('data-indicator')];
    // a bar is at least 2% high, so that one value is seen: those are left out
    return card.childNodes[2].childNodes.map((bar, j) => {
      const n = Number(bar.getAttribute('title').match(/: ([\d,]+) of/)[1].replace(/,/g, ''));
      return n && one[i][j] > 2 ? one[i][j] / (n / block.pairs) : null;
    }).filter((x) => x !== null);
  }).flat();
  for (const f of shares) assert.ok(Math.abs(f - shares[0]) < 0.06 * shares[0], f + ' vs ' + shares[0]);
  assert.match(drawn.byId['dist-said'].textContent, /one scale/);
});

test('the claim line names every verdict on a move, "as claimed" first, in words and without colour', () => {
  const data = example();
  const drawn = dom.page(data);
  const k = data.steps.findIndex((s) => s.claim && s.claim.scope.length);
  const step = data.steps[k];
  chips(drawn)[k + 1].dispatch('click', {});
  const said = drawn.byId['step-said'].textContent;
  const total = (v) => Object.values(data.counts.steps[step.id]).reduce((a, b) => a + b.verdicts[v], 0);
  for (const v of ['as claimed', 'off claim', 'not claimed', 'claimed, not moved']) {
    const word = v === 'as claimed' ? 'moved as claimed' : v;
    if (total(v)) assert.ok(said.includes(total(v) + ' value' + (total(v) === 1 ? '' : 's') + ' ' + word), v + ': ' + said);
    else assert.ok(!said.includes(word), v);
  }
  if (total('as claimed')) assert.ok(said.indexOf('moved as claimed') < Math.max(said.indexOf('off claim'), said.indexOf('not claimed')) || !/off claim|not claimed/.test(said));
  assert.doesNotMatch(said, /moves as claimed/);
  const all = drawn.byId['step-said'].all();
  assert.ok(!all.some((node) => /sd-good|sd-look/.test(node.className || '')));
});

test('a column whose only change is a missing value is not quietened as if nothing moved', () => {
  const data = example();
  const step = data.steps[0].id;
  const id = data.indicators[data.indicators.length - 1].id;
  const block = data.counts.steps[step][id];
  // nothing moved in this indicator, two values went missing
  for (const c of ['differs', 'beyond 10x', 'zero reference', 'zero result', 'sign change']) block.classes[c] = 0;
  block.classes.missing = 2;
  const drawn = dom.page(data);
  drawn.byId.comparison.querySelectorAll('button[data-comp="' + step + '"]')[0].dispatch('click', {});
  const name = data.indicators.find((i) => i.id === id).name;
  const head = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').slice(2).find((th) => th.getAttribute('title').indexOf(name) === 0);
  assert.doesNotMatch(head.className, /sd-still/);
  assert.match(head.getAttribute('title'), /2 missing/);
  const card = cards(drawn).find((c) => c.getAttribute('data-indicator') === id);
  assert.doesNotMatch(card.className, /sd-still/);
});

test('two percentiles that six digits cannot part are said to lie just under or over the median', () => {
  const t = page.quantileTexts({ p10: 1 - 1e-9, median: 1, p90: 5.94545 });
  assert.equal(t[0], 'just under the median');
  assert.notEqual(t[2], t[1]);
  assert.equal(t[2], '5.95'); // the pair (median, 90th) never blurred
  assert.equal(t[1], '1.00'); // the words took the place of the six digits: the rest go back to three
  // only the pair that blurs is widened: 5.94545 needs no six digits beside 1
  assert.equal(page.quantileTexts({ p10: 0.5, median: 1, p90: 1 + 1e-9 })[0], '0.500');
  assert.equal(page.quantileTexts({ p10: 0.5, median: 1, p90: 1 + 1e-9 })[2], 'just over the median');
});

test('a card says over how many ratios its median is, how many have none, and what full height is', () => {
  const data = local();
  const loaded = dom.page(data, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: full() } });
  for (const card of cards(loaded)) {
    const text = card.textContent;
    const block = data.counts.total[card.getAttribute('data-indicator')];
    const m = text.match(/Median of ([\d ]+) ratios?/);
    if (!m) { assert.match(text, /No value with a ratio/); continue; }
    const n = Number(m[1].replace(/ /g, ''));
    const left = block.pairs - n;
    if (left) assert.ok(text.includes(left + ' without a ratio'), text);
    else assert.doesNotMatch(text, /without a ratio/);
    assert.match(card.childNodes[1].textContent, /^tallest bar: \d/);
  }
});

// ------------------------------------------------------------------ several steps: a run

const pressed = (drawn) => chips(drawn).filter((c) => c.getAttribute('aria-pressed') === 'true').map((c) => c.getAttribute('data-comp'));
const chipOf = (drawn, id) => chips(drawn).find((c) => c.getAttribute('data-comp') === id);

test('Shift-click chooses the steps from one to another together: the range the file compares', () => {
  const data = example();
  const [a, b] = [data.steps[1], data.steps[2]];
  const id = a.id + '..' + b.id;
  assert.ok(data.ranges.some((r) => r.id === id));
  const drawn = dom.page(data);
  assert.equal(drawn.byId.pick.hidden, false);
  chipOf(drawn, a.id).dispatch('click', {});
  chipOf(drawn, b.id).dispatch('click', { shiftKey: true });
  assert.deepEqual(pressed(drawn), [a.id, b.id]);
  assert.equal(drawn.context.location.hash, 'step=' + encodeURIComponent(id));
  const said = drawn.byId['step-said'].textContent;
  assert.match(said, /^Steps 1 to 2 together\. /);
  for (const s of [a, b]) assert.ok(said.includes('Step ' + data.steps.indexOf(s) + ': ' + s.label), s.id);
  assert.match(said, /no verdict: a run is judged as the whole way is/);
  // every card shows the file's counts of the range, never a sum of its steps
  for (const card of cards(drawn)) {
    const block = data.counts.ranges[id][card.getAttribute('data-indicator')];
    const total = card.childNodes[2].childNodes.reduce((sum, bar) => sum + Number(/: ([\d\s]+) of [\d\s]+$/.exec(bar.getAttribute('title'))[1].replace(/\s/g, '')), 0);
    assert.equal(total, block.pairs);
  }
  // a grid cell is the range's own class, after the last step against before the first
  const at = data.steps.length + 1 + data.ranges.findIndex((r) => r.id === id);
  const row = gridRows(drawn)[0];
  const item = data.items.find((i) => i.id === row.getAttribute('data-item'));
  const cls = row.childNodes.filter((n) => n.tagName === 'TD').slice(1).map((td) => td.getAttribute('data-class'));
  const heads = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').slice(2)
    .map((th) => data.indicators.find((i) => th.getAttribute('title').indexOf(i.name) === 0).id);
  heads.forEach((ind, k) => assert.equal(cls[k], item.classes[ind][at], ind));
});

test('Shift-click chooses every step of the run: none of them lies between', () => {
  const data = example();
  const id = data.steps[1].id + '..' + data.steps[3].id;
  assert.ok(data.ranges.some((r) => r.id === id));
  const drawn = dom.page(data);
  chipOf(drawn, data.steps[1].id).dispatch('click', {});
  chipOf(drawn, data.steps[3].id).dispatch('click', { shiftKey: true });
  assert.deepEqual(pressed(drawn), data.steps.slice(1, 4).map((s) => s.id));
  for (const s of data.steps.slice(1, 4)) assert.doesNotMatch(chipOf(drawn, s.id).className, /sd-between/, s.id);
  assert.doesNotMatch(drawn.byId['step-said'].textContent, /between the steps chosen/);
  // an address names a run, not how it was chosen: every step of it is chosen
  drawn.open('step=' + encodeURIComponent(data.steps[0].id + '..' + data.steps[2].id));
  for (const s of data.steps.slice(0, 3)) assert.doesNotMatch(chipOf(drawn, s.id).className, /sd-between/, s.id);
});

test('in a run, the steps where nothing moved and nothing was judged fold into one line', () => {
  const tagged = (node, tag) => (node.tagName === tag ? [node] : []).concat(...(node.childNodes || []).map((c) => tagged(c, tag)));
  const data = example();
  const range = data.ranges.find((r) => r.steps.length === 3);
  const at = range.steps.map((id) => data.steps.findIndex((s) => s.id === id));
  const drawn = dom.page(data);
  drawn.open('step=' + encodeURIComponent(range.id));
  // the example's steps move something: nothing folds, every step has its own line
  assert.equal(tagged(drawn.byId['step-said'], 'DETAILS').length, 0);
  for (const k of at) assert.ok(drawn.byId['step-said'].textContent.includes('Step ' + k + ': ' + data.steps[k].label), k);
  // the first two steps made quiet in the file's counts: a claim, nothing moved, no verdict
  const calm = example();
  for (const id of range.steps.slice(0, 2)) {
    for (const block of Object.values(calm.counts.steps[id])) {
      for (const name of Object.keys(block.classes)) block.classes[name] = 0;
      for (const name of Object.keys(block.verdicts)) block.verdicts[name] = 0;
    }
  }
  const shown = dom.page(calm);
  shown.open('step=' + encodeURIComponent(range.id));
  const folded = tagged(shown.byId['step-said'], 'DETAILS');
  assert.equal(folded.length, 1);
  assert.match(folded[0].textContent, new RegExp('^Steps ' + at[0] + ' and ' + at[1] + ': nothing moved in any of them, as each claims\\.'));
  for (const k of at.slice(0, 2)) assert.ok(folded[0].textContent.includes('Step ' + k + ': ' + calm.steps[k].label), 'each is still there to open');
  assert.ok(!folded[0].textContent.includes('Step ' + at[2] + ': '), 'the step that moved stays outside');
  assert.ok(shown.byId['step-said'].textContent.includes('Step ' + at[2] + ': ' + calm.steps[at[2]].label));
});

test('steps chosen apart take in the steps between them, and the page says so', () => {
  const data = example();
  const drawn = dom.page(data);
  chipOf(drawn, data.steps[0].id).dispatch('click', {});
  chipOf(drawn, data.steps[2].id).dispatch('click', { metaKey: true });
  assert.deepEqual(pressed(drawn), data.steps.slice(0, 3).map((s) => s.id));
  assert.match(chipOf(drawn, data.steps[1].id).className, /sd-between/);
  assert.doesNotMatch(chipOf(drawn, data.steps[2].id).className, /sd-between/);
  assert.match(drawn.byId['step-said'].textContent, /Step 1 lies between the steps chosen and is taken in: each state is built on the one before it/);
  // an end taken off shrinks the run; a step inside cannot be taken off, and nothing changes
  chipOf(drawn, data.steps[1].id).dispatch('click', { metaKey: true });
  assert.match(drawn.byId['step-said'].textContent, /^Step 1 lies inside the steps 0 to 2, which are compared as a whole/);
  assert.deepEqual(pressed(drawn), data.steps.slice(0, 3).map((s) => s.id));
  chipOf(drawn, data.steps[0].id).dispatch('click', { ctrlKey: true });
  assert.deepEqual(pressed(drawn), data.steps.slice(1, 3).map((s) => s.id));
  assert.equal(drawn.context.location.hash, 'step=' + encodeURIComponent(data.steps[1].id + '..' + data.steps[2].id));
  // with "Several steps" on, a plain click does what ⌘-click does
  drawn.byId['pick-several'].checked = true;
  drawn.byId['pick-several'].dispatch('change', {});
  chipOf(drawn, data.steps[3].id).dispatch('click', {});
  assert.deepEqual(pressed(drawn), data.steps.slice(1, 4).map((s) => s.id));
});

test('every step chosen is the whole way, and a run the file does not compare is said and not shown', () => {
  const data = example();
  const drawn = dom.page(data);
  chipOf(drawn, data.steps[0].id).dispatch('click', {});
  chipOf(drawn, data.steps[3].id).dispatch('click', { shiftKey: true });
  assert.deepEqual(pressed(drawn), ['total']);
  // a file that compares fewer runs
  const fewer = example();
  const gone = fewer.ranges.pop();
  delete fewer.counts.ranges[gone.id];
  const shown = dom.page(fewer);
  chipOf(shown, gone.steps[0]).dispatch('click', {});
  chipOf(shown, gone.steps[gone.steps.length - 1]).dispatch('click', { shiftKey: true });
  assert.deepEqual(pressed(shown), [gone.steps[0]]);
  assert.match(shown.byId['step-said'].textContent, /together are not compared in this file\. It compares 4 runs of steps, chosen by its writer/);
});

test('an address names a run of steps, and one the file does not compare falls back to the whole way, said', () => {
  const data = example();
  const range = data.ranges[2];
  const drawn = dom.page(data);
  drawn.open('step=' + encodeURIComponent(range.id) + '&item=' + encodeURIComponent(data.items[0].id));
  assert.deepEqual(pressed(drawn), range.steps);
  // the drawer holds the run's own row
  assert.ok(drawn.byId['item-body'].textContent.includes('together'), 'a row of the run');
  drawn.open('step=' + encodeURIComponent(data.steps[0].id + '..' + data.steps[3].id + 'x'));
  assert.deepEqual(pressed(drawn), ['total']);
  assert.match(drawn.byId['step-said'].textContent, /no step and no run of steps of this file\. The whole way is shown/);
  const fewer = example();
  const gone = fewer.ranges.pop();
  delete fewer.counts.ranges[gone.id];
  const shown = dom.page(fewer);
  shown.open('step=' + encodeURIComponent(gone.id));
  assert.match(shown.byId['step-said'].textContent, /^The address asks for steps \d to \d together, which this file does not compare/);
});

test('Shift and an arrow key grow the run, and a file without ranges offers no several steps', () => {
  const data = example();
  const drawn = dom.page(data);
  chipOf(drawn, data.steps[1].id).dispatch('click', {});
  drawn.byId.comparison.dispatch('keydown', { key: 'ArrowRight', shiftKey: true });
  assert.deepEqual(pressed(drawn), data.steps.slice(1, 3).map((s) => s.id));
  drawn.byId.comparison.dispatch('keydown', { key: 'ArrowLeft', shiftKey: true });
  assert.deepEqual(pressed(drawn), [data.steps[1].id]);
  const none = example();
  delete none.ranges;
  delete none.counts.ranges;
  const shown = dom.page(none);
  assert.equal(shown.byId.pick.hidden, true);
  chipOf(shown, none.steps[1].id).dispatch('click', {});
  chipOf(shown, none.steps[2].id).dispatch('click', { shiftKey: true });
  assert.match(shown.byId['step-said'].textContent, /This file compares no run of steps/);
});

test('a matrix result written "=" is the result before it, and a "=" that stands first is refused', () => {
  assert.deepEqual(page.expandValues([1.5, '=', null, 2, '=', '='], 3), [1.5, 1.5, null, 2, 2, 2]);
  assert.equal(page.expandValues(['=', 1], 2), null);
  assert.equal(page.expandValues([1, null, '='], 3), null);
  assert.equal(page.expandValues([1, 2, '=', 4], 2), null); // first of the second indicator
  const m = full();
  assert.ok(m.values.some((row) => row.includes('=')), 'the local example has repeated results');
  const broken = full();
  const at = broken.values.findIndex((row) => row.includes('='));
  broken.values[at][0] = '=';
  assert.match(page.checkMatrix(broken, local()), /"=" first in an indicator/);
});
