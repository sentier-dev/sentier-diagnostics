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

test('every summed value of an estimated set is marked, and its counts are said to be estimated', () => {
  const d = drawn('an estimated sum', 'set=a,b');
  assert.match(d.byId['step-said'].textContent, /^2 fixes together\. estimated/);
  assert.match(d.byId['step-said'].textContent, /Whether fixes interact was not checked/);
  assert.match(d.byId['grid-said'].textContent, /^Estimated: /);
  assert.match(d.byId['worst-said'].textContent, /^Estimated: /);
  // a and b both move p1: its value is their sum, marked; p3, which neither moves, is not
  const p1 = cell(d, 'p1', 0);
  assert.ok(p1.all().some((n) => n.textContent === '≈'), p1.textContent);
  assert.ok(!cell(d, 'p3', 0).all().some((n) => n.textContent === '≈'));
  // one fix alone is its build, never marked
  const alone = drawn('an estimated sum', 'set=a');
  assert.match(alone.byId['step-said'].textContent, /^Fix A\. built/);
  assert.ok(!cell(alone, 'p1', 0).all().some((n) => n.textContent === '≈'));
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
  // another page's entry first: never taken
  const other = copy(p.fixes);
  other.of.title = 'Another chain';
  d.context.SENTIER_DIAGNOSTICS_FIXES_FILES = [{ src: 'fixes.js', fixes: p.fixes }, { src: 'other/fixes.js', fixes: other }];
  script.onload();
  assert.deepEqual(ticked(d), ['a', 'd', 'e']);
  assert.match(d.byId['fixes-said'].textContent, /^5 fixes/);
});
