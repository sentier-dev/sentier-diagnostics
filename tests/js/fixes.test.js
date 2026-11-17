// The page's view of a file of fixes (SPEC 16.8), held to what the Python reader gives.
// Run with `node --test tests/js/fixes.test.js`. The cases are written by
// tests/test_fixes_page.py: every set of made-up files, and made-up pages to draw.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const page = require('../../src/sentier_diagnostics/page/diagnostics.js');
const dom = require('./dom.js');

const FIXTURE = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'fixes_page.json'), 'utf8'));
const copy = (x) => JSON.parse(JSON.stringify(x));
const pageOf = (name) => copy(FIXTURE.pages[name]);

// ------------------------------------------------------------------ the reader, ported

test('every set of every made-up file composes and counts as the Python does, bit for bit', () => {
  let sets = 0;
  for (const one of FIXTURE.files) {
    for (const s of one.sets) {
      const got = page.fixCompose(one.file, s.ids);
      // the Python's keys; the page's `stands` is its own
      for (const key of Object.keys(s.compose)) assert.deepStrictEqual(got[key], s.compose[key], one.name + ' ' + s.ids + ': ' + key);
      assert.deepStrictEqual(page.fixCounts(one.file, s.ids), s.counts, one.name + ' ' + s.ids + ': counts');
      sets += 1;
    }
  }
  assert.ok(sets >= 60, sets + ' sets');
});

test('three differences are added in the order of the file, as fixes.in_order adds them', () => {
  assert.equal(page.inOrder([0.1, 0.2, 0.3]), 0.6000000000000001);
  const one = FIXTURE.files.find((f) => f.name === 'three fixes at one item');
  const at = one.file.items.map((r) => r[0]).indexOf('p4');
  assert.equal(page.fixCompose(one.file, ['x', 'y', 'z']).results[one.file.indicators[0].id][at], 0.6000000000000001);
  // from a base of 2.0: the differences from 0 in order, then the base (0.10000000000000009);
  // the base first, or a compensated sum, gives 0.09999999999999987
  const two = FIXTURE.files.find((f) => f.name === 'three fixes from 2.0').file;
  const p2 = two.items.map((r) => r[0]).indexOf('p2');
  assert.equal(two.base[two.indicators[0].id][p2], 2.0);
  assert.equal(page.fixCompose(two, ['x', 'y', 'z']).results[two.indicators[0].id][p2], 0.10000000000000009);
});

test('where a fix with what it requires and a built set both cover an item, the fix comes first', () => {
  const f = FIXTURE.files.find((x) => x.name === 'covers in order').file;
  const ind = f.indicators[0].id, p1 = f.items.map((r) => r[0]).indexOf('p1');
  assert.equal(page.fixCompose(f, ['a', 'b', 'd', 'e']).results[ind][p1], 1.8);
  assert.equal(page.fixCompose(f, ['a', 'b', 'd']).results[ind][p1], 1.8001, 'the built set itself');
});

test('pair terms are added in order, and a pair with no size is never a known size', () => {
  const f = FIXTURE.files.find((x) => x.name === 'sized pairs').file;
  assert.deepEqual(page.fixCompose(f, ['a', 'b', 'c']).pair_terms, { value: 0.6000000000000001, measured: 3, no_size: 0, pairs: 3 });
  assert.deepEqual(page.fixCompose(f, ['a', 'b', 'c', 'g']).pair_terms, { value: null, measured: 4, no_size: 1, pairs: 5 });
});

test('the page works out each fix\'s own counts again and finds the file\'s', () => {
  for (const one of FIXTURE.files) {
    for (const f of one.file.fixes) assert.equal(page.fixCountsDiffer(one.file, f.id), null, one.name + ': ' + f.id);
  }
});

test('a count the page\'s rule does not give is found, and named', () => {
  const one = copy(FIXTURE.files.find((f) => f.name === 'a pair and two built sets').file);
  const ind = one.indicators[0].id;
  one.fixes[2].counts[ind].classes.agrees += 1;
  one.fixes[2].counts[ind].classes.differs -= 1;
  const found = page.fixCountsDiffer(one, one.fixes[2].id);
  assert.deepEqual([found.indicator, found.part], [ind, 'classes']);
  assert.equal(found.file.agrees, found.page.agrees + 1);
  // every part of the counts, not the classes only
  const changes = {
    pairs: (b) => { b.pairs += 1; },
    missing: (b) => { b.missing.after += 1; },
    directions: (b) => { b.directions.up += 1; },
    bands: (b) => { b.bands[Object.keys(b.bands)[0]] += 1; },
  };
  for (const [part, change] of Object.entries(changes)) {
    const other = copy(FIXTURE.files.find((f) => f.name === 'a pair and two built sets').file);
    change(other.fixes[2].counts[ind]);
    assert.equal(page.fixCountsDiffer(other, other.fixes[2].id).part, part);
  }
});

test('a choice holds every fix it requires, in the order of the file, and names an unknown one', () => {
  const one = FIXTURE.files.find((f) => f.name === 'fixes that need others').file;
  assert.deepEqual(page.fixChosen(one, ['e']), { names: ['a', 'd', 'e'], added: ['a', 'd'], unknown: [] });
  assert.deepEqual(page.fixChosen(one, ['g', 'zz']), { names: ['a', 'b', 'g'], added: ['a', 'b'], unknown: ['zz'] });
});

test('a file of fixes is refused when it does not hang on the file shown', () => {
  const p = pageOf('fixes that need others');
  assert.equal(page.checkFixes(p.fixes, p.data), null);
  const cases = [
    [(f) => { f.format = 'sentier-diagnostics-fixes/0'; }, /its format is/],
    [(f) => { f.of.title = 'Another chain'; }, /belongs to "Another chain"/],
    [(f) => { f.of.base = 'nowhere'; }, /no state of the file shown/],
    [(f) => { f.indicators.reverse(); }, /indicators are not those/],
    [(f) => { f.fixes[2].requires = ['e']; }, /requires e, which does not come before it/],
  ];
  for (const [change, said] of cases) {
    const f = copy(p.fixes);
    change(f);
    assert.match(page.checkFixes(f, p.data), said);
  }
});

// ------------------------------------------------------------------ the page

// a page with its matrix and its file of fixes, as a host hands them over
function drawn(name, hash, change) {
  const p = pageOf(name);
  if (change) change(p);
  return dom.page(p.data, undefined, { standalone: true, hash, globals: { SENTIER_DIAGNOSTICS_MATRIX: p.matrix, SENTIER_DIAGNOSTICS_FIXES: p.fixes } });
}
const boxes = (d) => d.byId['fix-list'].all().filter((n) => n.getAttribute('data-fix') !== null);
const ticked = (d) => boxes(d).filter((n) => n.checked).map((n) => n.getAttribute('data-fix'));
function tick(d, id, on) {
  const box = boxes(d).find((n) => n.getAttribute('data-fix') === id);
  box.checked = on;
  box.dispatch('change', {});
}
// the cell of an item in an indicator's column of the grid
function cell(d, item, column) {
  const row = d.byId['grid-table'].all().find((n) => n.tagName === 'TR' && n.getAttribute('data-item') === item);
  return row.childNodes.filter((n) => n.tagName === 'TD')[1 + column];
}
// the grid's columns, by indicator (they are ordered by what moved), and its rows
const columnsOf = (d) => d.byId['grid-table'].all().filter((n) => n.tagName === 'TH' && n.getAttribute('data-indicator') !== null).map((n) => n.getAttribute('data-indicator'));
const gridRows = (d) => d.byId['grid-table'].all().filter((n) => n.tagName === 'TR' && n.getAttribute('data-item') !== null);
const cellOf = (d, item, ind) => cell(d, item, columnsOf(d).indexOf(ind));
// the row of the drawer's table for an indicator whose heading starts with `label`
function drawerRow(d, ind, label) {
  const table = d.byId['item-body'].all().find((n) => n.tagName === 'TABLE' && n.getAttribute('data-indicator') === ind);
  return table.all().filter((n) => n.tagName === 'TR').find((r) => r.childNodes[0].textContent.startsWith(label));
}
const classIn = (row) => row.all().find((n) => n.getAttribute('data-class') !== null).getAttribute('data-class');
const options = (select) => select.all().filter((n) => n.tagName === 'OPTION').map((n) => n.getAttribute('value'));
function chooseClass(d, value) {
  const select = d.byId['grid-class'];
  select.value = value;
  select.dispatch('change', {});
}

test('a page with a file of fixes offers them beside the chain, and opens on the chain', () => {
  const d = drawn('fixes that need others');
  assert.equal(d.byId.mode.hidden, false);
  assert.match(d.byId['fixes-said'].textContent, /^5 fixes, each measured on its own against After; 1 built set\.$/);
  assert.equal(d.byId['fix-panel'].hidden, true);
  assert.equal(d.byId.comparison.hidden, false);
  assert.equal(d.context.location.hash, '');
});

test('a page with no file of fixes shows no choice of them', () => {
  const p = pageOf('fixes that need others');
  const d = dom.page(p.data, undefined, { standalone: true, globals: { SENTIER_DIAGNOSTICS_MATRIX: p.matrix } });
  assert.equal(d.byId.mode.hidden, true);
});

test('the address chooses a set, with every fix it requires; a tick adds them, a cleared box takes its dependents', () => {
  const d = drawn('fixes that need others', 'set=e');
  assert.deepEqual(ticked(d), ['a', 'd', 'e']);
  assert.equal(d.byId['fix-panel'].hidden, false);
  assert.equal(d.byId.comparison.hidden, true);
  assert.match(d.byId['step-said'].textContent, /^Fix E, with Fix A and Fix D\. built/);
  // clearing a fix clears every chosen fix that requires it
  tick(d, 'a', false);
  assert.deepEqual(ticked(d), []);
  assert.match(d.byId['step-said'].textContent, /^Cleared too: Fix D and Fix E, which require Fix A\./);
  assert.match(d.byId['step-said'].textContent, /The base: After\./);
  assert.equal(d.context.location.hash, 'set=');
  // ticking a fix ticks what it requires, and says so
  tick(d, 'g', true);
  assert.deepEqual(ticked(d), ['a', 'b', 'g']);
  assert.match(d.byId['step-said'].textContent, /^Ticked too: Fix A and Fix B, which Fix G requires\./);
  assert.equal(d.context.location.hash, 'set=a,b,g');
});

test('an address that names a fix the file does not have opens the base and names it', () => {
  const d = drawn('fixes that need others', 'set=a,zz');
  assert.deepEqual(ticked(d), []);
  assert.match(d.byId['step-said'].textContent, /^The address names a fix the file of fixes does not have \(zz\)\. The base is shown\./);
});

test('a set holding a fix whose counts the page cannot reproduce is not drawn', () => {
  const d = drawn('fixes that need others', 'set=b', (p) => {
    const ind = p.fixes.indicators[0].id;
    p.fixes.fixes[1].counts[ind].classes.agrees -= 1;
    p.fixes.fixes[1].counts[ind].classes.differs += 1;
  });
  assert.deepEqual(ticked(d), []);
  assert.match(d.byId['step-said'].textContent, /This page's rule does not give the file's counts of Fix B .* so it draws no set that holds it\. .*The base is shown\./);
});

test('a file of fixes of another chain is refused, and said', () => {
  const d = drawn('fixes that need others', 'set=a', (p) => { p.fixes.of.title = 'Another chain'; });
  assert.match(d.byId['fixes-said'].textContent, /^The file of fixes was not loaded: it belongs to "Another chain"/);
  assert.match(d.byId['step-said'].textContent, /The address asks for a set of fixes, and the file of fixes was not loaded/);
  assert.equal(d.byId['fix-panel'].hidden, true);
});

test('the grid shows a set\'s result over the base: a built set as built', () => {
  const d = drawn('fixes that need others', 'set=e');
  // with a, d and e, p3 is 3.3 over the base's 3.0
  const p3 = cell(d, 'p3', 0);
  assert.equal(p3.textContent, '1.10');
  assert.doesNotMatch(d.byId['grid-said'].textContent, /^Estimated/);
});

const marked = (node) => node.all().some((n) => n.textContent === '≈');
// every set a reader can choose on a page: closed, each once
function setsOf(p) {
  const ids = p.fixes.fixes.map((f) => f.id), seen = new Map();
  for (let mask = 1; mask < (1 << ids.length); mask++) {
    const names = page.fixChosen(p.fixes, ids.filter((_, i) => mask & (1 << i))).names;
    seen.set(names.join(','), names);
  }
  return [...seen.values()];
}
// the value cells of the grid, each with its item and indicator
function valueCells(d) {
  const cols = columnsOf(d);
  return gridRows(d).flatMap((r) => r.childNodes.filter((n) => n.tagName === 'TD').slice(1, 1 + cols.length)
    .map((td, i) => ({ item: r.getAttribute('data-item'), ind: cols[i], td })));
}

test('an estimated set says so in its line and before its counts; one fix alone is its build', () => {
  const d = drawn('an estimated sum', 'set=a,b');
  assert.match(d.byId['step-said'].textContent, /^2 fixes together\. estimated/);
  assert.match(d.byId['step-said'].textContent, /Whether fixes interact was not checked, so a set that was not built is an estimate, and every value it has is marked ≈/);
  assert.match(d.byId['grid-said'].textContent, /^Estimated: /);
  assert.match(d.byId['worst-said'].textContent, /^Estimated: /);
  assert.match(d.byId['dist-said'].textContent, /^Estimated: /);
  const alone = drawn('an estimated sum', 'set=a');
  assert.match(alone.byId['step-said'].textContent, /^Fix A\. built/);
  assert.ok(!gridRows(alone).some(marked));
  assert.doesNotMatch(alone.byId['dist-said'].textContent, /^Estimated/);
});

test('a pair the set holds marks every value it may move: a sum, and a value from the base or a build without the whole pair', () => {
  const p = pageOf('a pair inside a build');
  const [A, B] = p.fixes.indicators.map((i) => i.id);
  const d = drawn('a pair inside a build', 'set=a,b,c,d');
  assert.match(d.byId['step-said'].textContent, /^Every fix \(4\)\. estimated/);
  assert.match(d.byId['step-said'].textContent, /A value is marked ≈ wherever a pair may move it: every sum, and every value taken from the base or from a build that does not hold both fixes of each pair\./);
  // p1 stands on the build of a and b, which holds the pair: not marked
  assert.ok(!marked(cellOf(d, 'p1', A)), cellOf(d, 'p1', A).textContent);
  // p2 stands on a's build, and b, the pair's other fix, lies outside it
  assert.ok(marked(cellOf(d, 'p2', A)));
  assert.match(cellOf(d, 'p2', A).getAttribute('title'), /^Estimated: the result of a build of only some of these fixes, which the others may move by interacting with them\. /);
  // p3 on c's build and p4 in B on d's, which hold neither fix of the pair
  assert.ok(marked(cellOf(d, 'p3', A)));
  assert.ok(marked(cellOf(d, 'p4', B)));
  // a value no fix changes on its own stands on the base, which holds neither: a and b may
  // still move it together
  for (const [item, ind] of [['p4', A], ['p1', B], ['p2', B], ['p3', B]]) assert.ok(marked(cellOf(d, item, ind)), item + ' ' + ind);
  assert.match(cellOf(d, 'p4', A).getAttribute('title'), /^Estimated: no fix of the set changes it on its own, and two of them may change it together\. /);
  // the set of c and d holds no pair: exact, and nothing is marked
  const cd = drawn('a pair inside a build', 'set=c,d');
  assert.match(cd.byId['step-said'].textContent, /exact/);
  assert.ok(!gridRows(cd).some(marked));
});

test('the drawer of an estimated set says which values are estimated, and why a base value is', () => {
  const p1 = drawn('a pair inside a build', 'set=a,b,c,d&item=p1').byId['item-body'].textContent;
  assert.match(p1, /This setthe build of Fix a and Fix b[^,]/);
  const p2 = drawn('a pair inside a build', 'set=a,b,c,d&item=p2').byId['item-body'].textContent;
  assert.match(p2, /This setthat build, estimated/);
  const p4 = drawn('a pair inside a build', 'set=a,b,c,d&item=p4').byId['item-body'].textContent;
  assert.match(p4, /In the other 1 indicator no fix of this set changes it on its own\. Two fixes of a listed pair the set holds may change it together, so it is marked ≈\./);
  const none = drawn('an estimated sum', 'set=a,b&item=p3').byId['item-body'].textContent;
  assert.match(none, /No fix of this set changes this \w+ on its own: each result is the base's\. Whether these fixes interact was not checked, so it is marked ≈\./);
  // in an exact set, nothing is said
  const exact = drawn('a pair inside a build', 'set=c,d&item=p1').byId['item-body'].textContent;
  assert.match(exact, /No fix of this set changes this \w+ on its own: each result is the base's\.Along the chain/);
});

test('a built or exact set marks no value, on every page and every set', () => {
  let sets = 0;
  for (const name of Object.keys(FIXTURE.pages)) {
    const p = pageOf(name);
    for (const names of setsOf(p)) {
      if (page.fixCompose(p.fixes, names).label === 'estimated') continue;
      const d = drawn(name, 'set=' + names.join(','));
      for (const c of valueCells(d)) assert.ok(!marked(c.td), name + ': ' + names + ', ' + c.item + ' ' + c.ind + ' ' + c.td.textContent);
      sets += 1;
    }
  }
  assert.ok(sets >= 30, sets + ' sets');
  // where three fixes move one item, the set of two is exact: its sum is not marked
  const p = pageOf('three fixes at one item');
  const xy = drawn('three fixes at one item', 'set=x,y');
  assert.match(xy.byId['step-said'].textContent, /exact/);
  assert.ok(!marked(cellOf(xy, 'p4', p.fixes.indicators[0].id)));
});

test('where interactions were not checked, every value of an estimated set is marked but no sum', () => {
  let sets = 0;
  for (const name of Object.keys(FIXTURE.pages)) {
    const p = pageOf(name);
    if (p.fixes.interactions.checked) continue;
    for (const names of setsOf(p)) {
      if (page.fixCompose(p.fixes, names).label !== 'estimated') continue;
      const d = drawn(name, 'set=' + names.join(','));
      for (const c of valueCells(d)) {
        if (c.td.getAttribute('data-class') === 'no sum') assert.ok(!marked(c.td));
        else assert.ok(marked(c.td), name + ': ' + names + ', ' + c.item + ' ' + c.ind);
      }
      sets += 1;
    }
  }
  assert.ok(sets >= 2, sets + ' sets');
});

test('the drawer splits an item into each fix\'s effect, and the set\'s value is the sum', () => {
  const d = drawn('an estimated sum', 'set=a,b&item=p1');
  const body = d.byId['item-body'].textContent;
  assert.match(body, /^What the fixes did/);
  assert.match(body, /Fix A.*Fix B.*This setthe sum, estimated/);
  assert.match(body, /Along the chain/);
});

test('a built set that is a state of the chain is offered as one choice', () => {
  const d = drawn('a built set that is a state', 'set=');
  const built = d.byId['fix-built'].all().filter((n) => n.getAttribute('data-built') !== null);
  assert.deepEqual(built.map((n) => n.textContent), ['A and B', 'Every fix']);
  built[1].dispatch('click', {});
  assert.deepEqual(ticked(d), ['a', 'b', 'c']);
  assert.match(d.byId['step-said'].textContent, /^Every fix \(3\)\. built/);
  assert.equal(d.context.location.hash, 'set=a,b,c');
});

test('"Moved (any class)" keeps only the items with a value that moved, and says how many values', () => {
  const d = drawn('fixes that need others', 'set=e');
  const select = d.byId['grid-class'];
  select.value = 'moved';
  select.dispatch('change', {});
  const rows = d.byId['grid-table'].all().filter((n) => n.tagName === 'TR' && n.getAttribute('data-item') !== null);
  assert.deepEqual(rows.map((n) => n.getAttribute('data-item')).sort(), ['p1', 'p2', 'p3']);
  assert.match(d.byId['grid-said'].textContent, /in which \d+ values? moved\./);
});

test('a file of fixes beside the page loads after it is drawn, and takes the entry of its own script', () => {
  const p = pageOf('fixes that need others');
  const d = dom.page(p.data, undefined, { standalone: true, hash: 'set=e', attributes: { 'data-sd-fixes': 'fixes.js' },
    globals: { SENTIER_DIAGNOSTICS_MATRIX: p.matrix } });
  const script = d.head.all().find((n) => n.tagName === 'SCRIPT' && n.getAttribute('src') === 'fixes.js');
  assert.ok(script, 'the script is added');
  assert.match(d.byId['step-said'].textContent, /the file of fixes is loading, and the set is shown when it is here/);
  script.onload.call(script); // nothing handed over yet
  assert.match(d.byId['fixes-said'].textContent, /^The file of fixes was not loaded: fixes\.js holds no file of fixes/);
  // another page's entry, before this page's and after it: never taken
  const other = copy(p.fixes);
  other.of.title = 'Another chain';
  const mine = { src: 'fixes.js', fixes: p.fixes }, theirs = { src: 'other/fixes.js', fixes: other };
  for (const list of [[theirs, mine], [mine, theirs]]) {
    const again = dom.page(p.data, undefined, { standalone: true, hash: 'set=e', attributes: { 'data-sd-fixes': 'fixes.js' },
      globals: { SENTIER_DIAGNOSTICS_MATRIX: p.matrix } });
    const added = again.head.all().find((n) => n.tagName === 'SCRIPT' && n.getAttribute('src') === 'fixes.js');
    again.context.SENTIER_DIAGNOSTICS_FIXES_FILES = list;
    added.onload();
    assert.deepEqual(ticked(again), ['a', 'd', 'e'], list.map((e) => e.src).join(' then '));
    assert.match(again.byId['fixes-said'].textContent, /^5 fixes/);
  }
});

// a page that names fixes.json, served over http with `bytes` (a Buffer) or a status
async function fetched(bytes, status) {
  const p = pageOf('fixes that need others'), asked = [];
  const fetch = (url) => {
    asked.push(url);
    const buffer = bytes ? bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length) : null;
    return Promise.resolve({ ok: !status, status: status || 200, arrayBuffer: () => Promise.resolve(buffer) });
  };
  const d = dom.page(p.data, undefined, { standalone: true, hash: 'set=e', protocol: 'https:', fetch,
    attributes: { 'data-sd-fixes': 'fixes.json', 'data-sd-base': 'runs/1/' }, globals: { SENTIER_DIAGNOSTICS_MATRIX: p.matrix } });
  await new Promise((done) => setImmediate(done));
  return { d, asked, said: d.byId['fixes-said'].textContent };
}

test('a file of fixes named fixes.json is fetched over http, held to the file shown, and drawn', async () => {
  const { d, asked, said } = await fetched(Buffer.from(JSON.stringify(pageOf('fixes that need others').fixes)));
  assert.deepEqual(asked, ['runs/1/fixes.json']);
  assert.match(said, /^5 fixes/);
  assert.deepEqual(ticked(d), ['a', 'd', 'e']);
  // one of another chain is refused as one from a script is
  const other = pageOf('fixes that need others').fixes;
  other.of.title = 'Another chain';
  assert.match((await fetched(Buffer.from(JSON.stringify(other)))).said, /^The file of fixes was not loaded: it belongs to "Another chain"/);
});

test('fixes.json over http is refused when larger than a page loads in bytes, not JSON, not UTF-8, or not served', async () => {
  // 2-byte characters: the text is half as long as the file, so only its size in bytes is over
  const max = 64 * 1024 * 1024, large = Buffer.alloc(max + 2, 'é');
  assert.equal(large.toString('utf8').length, max / 2 + 1);
  assert.match((await fetched(large)).said, /^The file of fixes was not loaded: fixes\.json is larger than 67\D108\D864 bytes/);
  assert.match((await fetched(Buffer.from('{"format": '))).said, /^The file of fixes was not loaded: fixes\.json is not JSON/);
  assert.match((await fetched(Buffer.from([0x7b, 0xff, 0x7d]))).said, /^The file of fixes was not loaded: fixes\.json is not UTF-8 text/);
  assert.match((await fetched(null, 404)).said, /^The file of fixes was not loaded: fixes\.json could not be read \(404\)/);
  // from the disk, a page reads no JSON beside it
  const p = pageOf('fixes that need others');
  const local = dom.page(p.data, undefined, { standalone: true, attributes: { 'data-sd-fixes': 'fixes.json' }, globals: { SENTIER_DIAGNOSTICS_MATRIX: p.matrix } });
  assert.match(local.byId['fixes-said'].textContent, /fixes\.json is read over http only/);
});

test('a page whose key is refused loads no file of fixes, and keeps saying why', () => {
  const p = pageOf('fixes that need others');
  const d = dom.page(p.data, undefined, { hash: 'left.set=e', attributes: { 'data-sd-key': 'sd2', 'data-sd-fixes': 'fixes.js' },
    globals: { SENTIER_DIAGNOSTICS_MATRIX: p.matrix } });
  assert.equal(d.head.all().filter((n) => n.tagName === 'SCRIPT').length, 0, 'no script is added');
  assert.match(d.byId['load-error'].textContent, /is one the page gives/);
  assert.equal(d.byId.content.hidden, true);
  assert.equal(d.context.location.hash, '#left.set=e', 'the address is left as it was');
});

// ------------------------------------------------------------------ review of 57ceb6a

test('the drawer judges a fix as the file counts it: with its noise and that of what it was measured against', () => {
  const p = pageOf('a fix within its noise');
  const ind = p.fixes.indicators[0].id;
  assert.equal(p.fixes.fixes[0].counts[ind].classes['within noise'], 1, 'the file: 1.0 to 1.01 is within 0.5 % + 1 %');
  const d = drawn('a fix within its noise', 'set=x&item=p1');
  assert.equal(classIn(drawerRow(d, ind, 'Fix x')), 'within noise');
  assert.equal(classIn(drawerRow(d, ind, 'This set')), 'within noise');
  assert.equal(cellOf(d, 'p1', ind).getAttribute('data-class'), 'within noise');
});

test('the grid\'s classes add up to the counts of the set, on every page and every set', () => {
  let sets = 0;
  for (const name of Object.keys(FIXTURE.pages)) {
    const p = pageOf(name);
    const ids = p.fixes.fixes.map((f) => f.id), seen = new Set();
    for (let mask = 1; mask < (1 << ids.length); mask++) {
      const names = page.fixChosen(p.fixes, ids.filter((_, i) => mask & (1 << i))).names;
      if (seen.has(names.join(','))) continue;
      seen.add(names.join(','));
      const d = drawn(name, 'set=' + names.join(','));
      assert.deepEqual(ticked(d), names, name + ': ' + names);
      const counts = page.fixCounts(p.fixes, names).by, cannot = page.fixCompose(p.fixes, names).cannot_add;
      const cols = columnsOf(d), rows = gridRows(d);
      assert.equal(rows.length, p.fixes.items.length, name + ': every item is in the grid');
      for (const ind of Object.keys(counts)) {
        // the file's counts, with each value no sum can be formed for out of "missing"
        const want = {};
        for (const [c, k] of Object.entries(counts[ind].classes)) if (k) want[c] = k;
        if (cannot[ind].length) {
          want.missing -= cannot[ind].length;
          if (!want.missing) delete want.missing;
          want['no sum'] = cannot[ind].length;
        }
        const got = {};
        for (const r of rows) {
          const c = r.childNodes.filter((n) => n.tagName === 'TD')[1 + cols.indexOf(ind)].getAttribute('data-class');
          got[c] = (got[c] || 0) + 1;
        }
        assert.deepEqual(got, want, name + ': ' + names + ', ' + ind);
      }
      sets += 1;
    }
  }
  assert.ok(sets >= 40, sets + ' sets');
});

test('a value no sum can be formed for reads "no sum" wherever the page names it, never "missing"', () => {
  const ind = pageOf('three fixes at one item').fixes.indicators[0].id;
  // x moves p2 to 2.5; w has no result there
  const d = drawn('three fixes at one item', 'set=x,w');
  const p2 = cellOf(d, 'p2', ind);
  assert.equal(p2.textContent, 'no sum');
  assert.equal(p2.getAttribute('data-class'), 'no sum');
  assert.match(p2.getAttribute('title'), /^no sum: .*it is not a missing result\. Before 2\.$/);
  assert.doesNotMatch(p2.getAttribute('title'), /missing after/);
  const th = d.byId['grid-table'].all().find((n) => n.tagName === 'TH' && n.getAttribute('data-indicator') === ind);
  assert.match(th.getAttribute('title'), /: 1 moved, 1 no sum here$/);
  const card = d.byId['dist-cards'].all().find((n) => n.getAttribute('data-indicator') === ind && n.tagName === 'DIV');
  const meta = card.all().find((n) => n.className === 'sd-dist-meta');
  assert.match(meta.textContent, /^1 moved, 1 no sum, of 4/);
  assert.ok(options(d.byId['grid-class']).includes('no sum'));
  assert.ok(!options(d.byId['grid-class']).includes('missing'));
  chooseClass(d, 'no sum');
  assert.deepEqual(gridRows(d).map((n) => n.getAttribute('data-item')), ['p2']);
  // w alone has no result at p2: that is missing, and no sum is not said
  const alone = drawn('three fixes at one item', 'set=w');
  assert.equal(cellOf(alone, 'p2', ind).getAttribute('data-class'), 'missing');
  assert.ok(options(alone.byId['grid-class']).includes('missing'));
  assert.ok(!options(alone.byId['grid-class']).includes('no sum'));
});

test('"Moved (any class)": a missing value is not moved, the filter stays from set to set, and goes where nothing moved', () => {
  // y moves p4 in both indicators; w has no result at p2
  const d = drawn('three fixes at one item', 'set=y,w');
  chooseClass(d, 'moved');
  assert.deepEqual(gridRows(d).map((n) => n.getAttribute('data-item')), ['p4']);
  assert.match(d.byId['grid-said'].textContent, /in which 2 values moved\./);
  tick(d, 'x', true);
  assert.equal(d.byId['grid-class'].value, 'moved', 'kept when the set changes');
  assert.deepEqual(gridRows(d).map((n) => n.getAttribute('data-item')), ['p4'], 'no sum is not moved either');
  tick(d, 'x', false);
  tick(d, 'y', false);
  assert.deepEqual(ticked(d), ['w']);
  assert.ok(!options(d.byId['grid-class']).includes('moved'), 'nothing moved: no such choice');
  assert.equal(d.byId['grid-class'].value, '');
  assert.equal(gridRows(d).length, 4);
});

test('the drawer of a build of several fixes shows the rest; where it holds a listed pair, as the interaction', () => {
  const ind = pageOf('a built set that is a state').fixes.indicators[0].id;
  // a and b both move p1; b and c are a pair; every fix was built, and a with b
  const all = drawn('a built set that is a state', 'set=a,b,c&item=p1');
  assert.ok(drawerRow(all, ind, 'The interaction'));
  assert.ok(!drawerRow(all, ind, 'The rest'));
  const ab = drawn('a built set that is a state', 'set=a,b&item=p1');
  assert.ok(drawerRow(ab, ind, 'The rest'));
  assert.ok(!drawerRow(ab, ind, 'The interaction'));
});

test('a set\'s address is the page\'s own part in a host, beside the host\'s own set= and item=', () => {
  const p = pageOf('fixes that need others');
  const d = dom.page(p.data, undefined, { hash: 'set=zzz&left.set=e&item=host', attributes: { 'data-sd-key': 'left' },
    globals: { SENTIER_DIAGNOSTICS_MATRIX: p.matrix, SENTIER_DIAGNOSTICS_FIXES: p.fixes } });
  assert.deepEqual(ticked(d), ['a', 'd', 'e']);
  tick(d, 'g', true);
  const parts = d.context.location.hash.replace(/^#/, '').split('&');
  assert.ok(parts.includes('left.set=a,b,d,e,g'), parts.join('&'));
  assert.ok(parts.includes('set=zzz') && parts.includes('item=host'), 'the host\'s parts are kept: ' + parts.join('&'));
  assert.equal(parts.filter((x) => x.startsWith('set=')).length, 1);
});

test('a file of fixes is held to the file shown as the Python holds it: base noise, words, floors, whole items', () => {
  const cases = [
    ['a fix within its noise', (f) => { const by = f.of.base_noise.by; by[Object.keys(by)[0]] = 0.5; }, /its noise of the base \(of\.base_noise\) is not the noise the file shown gives/],
    ['a fix within its noise', (f) => { delete f.of.base_noise; }, /its base is a build, and it says no noise of it/],
    ['from the published results', (f) => { f.of.base_noise = copy(f.fixes[0].noise); }, /its base is the published results, which are exact/],
    ['fixes that need others', (f) => { f.indicators[0].name = 'Another'; }, /indicators are not those of the file shown/],
    ['fixes that need others', (f) => { f.item = { one: 'thing', many: 'things' }; }, /words for an item or an indicator/],
    ['fixes that need others', (f) => { f.rule.floors[0].value *= 2; }, /its floors are not those of the file shown/],
    ['fixes that need others', (f) => { f.items[0][1] = 'Another name'; }, /its item p\d: its name, place, group or unit are not the matrix's/],
    ['a built set that is a state', (f) => { f.built[1].state = 's0'; }, /says it is state "s0", which is no state of the chain after the base/],
  ];
  for (const [name, change, said] of cases) {
    const p = pageOf(name);
    assert.equal(page.fixesProblem(p.fixes, p.data, null), null, name);
    const d = drawn(name, 'set=', (q) => change(q.fixes));
    assert.match(d.byId['fixes-said'].textContent, /^The file of fixes was not loaded: /, String(said));
    assert.match(d.byId['fixes-said'].textContent, said);
  }
});

test('without the matrix, the listed items hold the file of fixes: their names and base results', () => {
  const p = pageOf('fixes that need others');
  assert.equal(page.fixesProblem(p.fixes, p.data, null), null);
  const cases = [
    [(f) => { for (const ind of Object.keys(f.base)) f.base[ind] = f.base[ind].map((v) => (v === null ? null : v * 7)); }, /its base result of p3 in .* is not the file's in state s1/],
    [(f) => { f.items.find((r) => r[0] === 'p3')[3] = 'another group'; }, /its item p3: its name, place, group or unit are not the file's/],
    [(f) => { f.items.find((r) => r[0] === 'p3')[0] = 'p33'; }, /the listed item p3 is not in it/],
  ];
  for (const [change, said] of cases) {
    const f = copy(p.fixes);
    change(f);
    assert.match(page.fixesProblem(f, p.data, null), said);
    const d = dom.page(p.data, undefined, { standalone: true, globals: { SENTIER_DIAGNOSTICS_FIXES: f } });
    assert.match(d.byId['fixes-said'].textContent, said);
  }
});

test('a malformed file of fixes from a host is refused and said, never thrown', () => {
  const name = 'a built set that is a state';
  const ind = pageOf(name).fixes.indicators[0].id;
  const cases = [
    [(f) => { delete f.built[0].fixes; }, /built set 1 is not what the format says/],
    [(f) => { delete f.built[0].results; }, /built set 1 is not what the format says/],
    [(f) => { f.built[1].noise = null; }, /built set 2 is not what the format says/],
    [(f) => { delete f.interactions.pairs; }, /its interactions are not what the format says/],
    [(f) => { delete f.fixes[0].counts[ind]; }, /the counts of fix a in .* are not what the format says/],
    [(f) => { f.fixes[0].effect[ind] = [[99, 1]]; }, /the effect of fix a in .* is not what the format says/],
    [(f) => { f.fixes = 'none'; }, /its fixes are not a list/],
    [(f) => { f.base[ind] = f.base[ind].slice(1); }, /its base does not hold a result for every item/],
    [(f) => { f.fixes[1].noise = null; }, /fix 2 is not what the format says/],
    [(f) => { f.interactions.pairs[0].fixes = ['b', 'zz']; }, /pair 1 is not what the format says/],
  ];
  for (const [change, said] of cases) {
    const p = pageOf(name);
    const f = copy(p.fixes);
    change(f);
    assert.match(page.fixesProblem(f, p.data, null), said);
    const d = drawn(name, 'set=a', (q) => { q.fixes = f; });
    assert.match(d.byId['fixes-said'].textContent, /^The file of fixes was not loaded: /);
    assert.match(d.byId['fixes-said'].textContent, said);
    assert.equal(d.byId['fix-panel'].hidden, true);
  }
});
