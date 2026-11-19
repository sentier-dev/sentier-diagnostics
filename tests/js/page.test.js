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
  // what rounds to 1e4 is written as 1e4 is (issue 19: "1.000e+4" for 9999.5)
  assert.equal(page.formatNumber(9999.5), '1e4');
  assert.equal(page.formatNumber(-99999.5), '−1e5');
  assert.deepEqual(page.quantileTexts({ p10: 1234.5, median: 2000, p90: 3001 }), ['1.23e3', '2.00e3', '3.00e3']);
  assert.equal(page.ratioShort(1, 999.6), '1e3');
  assert.equal(page.percentText(1, 1.00001), '+1e−3 %');
  assert.equal(page.shareText(0.0005), '5e−2 %');
});

test('the rule\'s numbers and every tooltip are written with every digit, in the page\'s style (issue 19)', () => {
  const tight = example();
  tight.steps[1].tolerance.value = 1e-7;
  tight.rule.total_tolerance = 1e-7;
  tight.rule.floor_factor = 1e-7;
  const said = dom.page(tight);
  const row = said.byId['steps-table'].childNodes.find((n) => n.tagName === 'TBODY').childNodes[1];
  assert.ok(row.childNodes.some((td) => td.textContent === '1e−7'), 'the tolerance cell');
  said.open('sd.step=fix-1');
  assert.match(said.byId['step-said'].textContent, /Tolerance 1e−7 \(/);
  said.open('sd.step=total');
  assert.match(said.byId['step-said'].textContent, /Tolerance 1e−7, the largest of the steps/);
  assert.match(said.text(), /a tolerance of 1e−7, the largest of the steps/);
  assert.match(said.text(), /reference unit: 1e−7 times the median/);
  // the example's toxicity results are near 1e−7: each tooltip says them in the same style
  said.open('sd.item=p01');
  assert.match(said.text(), /Before 2e−7, after 2\.0000002e−7/);
  assert.ok(!/\de-\d/.test(said.text()), 'no number in the style of String()');
});

test('a number that rounds across a threshold of its style is written as the numbers beyond it (issue 19)', () => {
  // each pair: a number just short of a threshold that rounds onto it, and the threshold itself
  const same = (write, near, at) => assert.equal(write(...near), write(...at), `${write.name}(${near}) and (${at})`);
  same(page.formatNumber, [9999.5], [1e4]);
  same(page.formatNumber, [0.00099996], [0.001]);
  same(page.formatNumber, [-0.00099996], [-0.001]);
  for (const [near, at] of [[199.96, 200], [1099.6, 1100], [100.996, 101], [100.00996, 100.01], [10099.6, 10100]]) {
    same(page.percentText, [100, near], [100, at]);
    same(page.percentText, [100, 200 - near], [100, 200 - at]);
  }
  same(page.shareText, [99.99996], [100]);
  same(page.shareText, [0.000999], [0.001]);
  same(page.ratioShort, [1, 0.009996], [1, 0.01]);
  // 1.001 − 1 is 0.000999999999999889 in floats: the ratio still reads 1.001, and a difference
  // that four digits keep under 0.001 is still written as one (reviews of 9a11c09, 2d0d545)
  assert.equal(page.ratioText(1, 1.001), '1.001');
  assert.equal(page.ratioText(1, 0.999), '0.999');
  assert.equal(page.ratioText(1, 1.0009995), '1 + 9.995e−4');
  assert.equal(page.ratioText(1, 0.9990005), '1 − 9.995e−4');
  same(page.ratioShort, [1, 999.6], [1, 1000]);
  const all = (v) => ({ p10: v, median: v, p90: v });
  assert.deepEqual(page.quantileTexts(all(0.0099996)), page.quantileTexts(all(0.01)));
  assert.deepEqual(page.quantileTexts(all(-0.0099996)), page.quantileTexts(all(-0.01)));
  // and the texts themselves: grouped from 1 000 on, whole from 100 on, one decimal from 1 on
  assert.deepEqual([[100, 1099.6], [100, 199.96], [100, 100.996], [100, 100.00996]].map((p) => page.percentText(...p)),
    ['+1 000 %', '+100 %', '+1.0 %', '+0.01 %']);
  assert.equal(page.shareText(99.99996), '1e4 %');
});

test('a number written with every digit has the page\'s style however large it is (issue 19)', () => {
  // String() writes "1e+21" from 1e21 on: the tooltips of the largest results
  assert.equal(page.exactText(1e21), '1e21');
  assert.equal(page.exactText(-1.5e300), '−1.5e300');
  assert.equal(page.exactText(1e-7), '1e−7');
  assert.equal(page.exactText(123.456), '123.456');
  assert.equal(page.exactText(null), 'missing');
});

test('every number the page writes has the one style, over the whole range of the floats (issue 19)', () => {
  const values = [9999.5, 99999.5, 999.95, 0.0099995, 0.00099995, 5e-324, Number.MAX_VALUE, 1e21, 123456789012345680000];
  for (let e = -323; e <= 307; e++) for (const m of [1, 1.2345, 9.5, 9.9995, 9.99995]) values.push(m * 10 ** e);
  const plain = /^\d+(\.\d+)?(e−?\d+)?$/;
  const said = [];
  for (const v of values) {
    said.push(['formatNumber', v, page.formatNumber(v).replace(/^−/, '')], ['formatNumber', -v, page.formatNumber(-v).replace(/^−/, '')]);
    said.push(['shareText', v, page.shareText(v / 100).replace(/ %$/, '')]);
    said.push(['ratioShort', v, page.ratioShort(1, v)]);
    const percent = page.percentText(1, 1 + v / 100).replace(/^[+−]/, '').replace(/ %$/, '');
    if (v < 1e300) said.push(['percentText', v, /^\d \d{3}$/.test(percent) ? percent.replace(' ', '') : percent]);
    if (isFinite(v * 3)) for (const q of page.quantileTexts({ p10: v, median: v * 1.5, p90: v * 3 })) said.push(['quantileTexts', v, q]);
  }
  const off = said.filter(([, , text]) => !plain.test(text));
  assert.deepEqual(off.slice(0, 5), []);
  assert.ok(said.length > 15000);
});

test('an item\'s whole difference is split by the steps, and the shares added up are what rounding left of 100 % (A18, issue 9)', () => {
  const split = page.splitOf([1, 1.5, 1.75], [true, false], 'differs');
  assert.equal(split.state, 'split');
  assert.deepEqual(split.shares, [2 / 3, 1 / 3]);
  assert.equal(page.splitText(split), '100 %, of which nothing explains 33.3 %');
  // in floating point the shares need not add up to exactly 1: the page prints what is left
  const rounded = page.splitOf([3, 1.1, 2.2, 0.3], [true, true, true], 'differs');
  assert.equal(rounded.sum, 0.9999999999999999);
  assert.equal(page.splitText(rounded), '100 % − 1.11e−14 %');
  // a step nothing explains is named even where its share is 0
  assert.equal(page.splitText(page.splitOf([1, 1, 2], [false, true], 'differs')), '100 %, of which nothing explains 0 %');
});

test('steps that cancel are printed, and said to cancel; a sum is withheld only where rounding reaches its last digit (A18, issue 9)', () => {
  // correct to the last digit printed: +1000 % and −900 %
  const nineteen = page.splitOf([1, 6, 1.5], [true, true], 'differs');
  assert.deepEqual(nineteen.shares.map(page.shareText), ['1000.0 %', '−900.0 %']);
  assert.equal(page.splitText(nineteen), '100 %; the steps cancel: their differences add up to 19 times the whole difference');
  // under ten times the steps do not cancel, and nothing is said of it
  assert.equal(page.splitText(page.splitOf([1, 3, 1.5], [true, true], 'differs')), '100 %');
  // the rounding of the sum stays under its last digit at 4e9 times, and reaches it at 4e12
  const far = page.splitOf([1, 1e9, 1.5], [true, true], 'differs');
  assert.deepEqual(far.shares.map(page.shareText), ['2e11 %', '−2e11 %']);
  assert.equal(page.splitText(far), '100 %; the steps cancel: their differences add up to 4e9 times the whole difference');
  const farther = page.splitOf([1, 1e12, 1.5], [true, false], 'differs');
  assert.equal(page.splitText(farther), 'the shares are not added up: rounding would reach the last digit; the steps cancel: their differences add up to 4e12 times the whole difference');
  // each share is still one difference over the whole, right to the digits it is printed to
  const split = page.splitOf([1, 1e16, 1, 2], [true, true, true], 'differs');
  assert.equal(split.state, 'split');
  assert.deepEqual(split.shares.map(page.shareText), ['1e18 %', '−1e18 %', '100.0 %']);
  assert.match(page.splitText(split), /^the shares are not added up: rounding would reach the last digit; the steps cancel: their differences add up to 2e16 times/);
  // a share is printed to four digits from 1e4 % on, never to more digits than a float holds
  assert.deepEqual([page.shareText(99.99), page.shareText(123.45), page.shareText(-1e16)], ['9999.0 %', '1.235e4 %', '−1e18 %']);
});

test('an item missing in any state is not split, not even for the steps before the gap (A18)', () => {
  assert.equal(page.splitOf([1, 2, null, 4], [true, true, true], 'differs').state, 'gap');
  assert.equal(page.splitOf([null, 2, 4], [true, true], 'missing').state, 'missing');
  assert.equal(page.splitOf([1, 1, 1], [true, true], 'agrees').state, 'still');
  // a file whose class says the whole way moved, with its first and last results equal, is
  // one the validator refuses; the page divides by nothing all the same
  const level = page.splitOf([1, 2, 1], [true, true], 'differs');
  assert.equal(level.state, 'level');
  assert.equal(page.splitText(level), 'not split: its first and last results are the same');
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
  const all = drawn.byId['steps-table'].all().filter((n) => n.tagName === 'TR');
  const head = all[0].childNodes.map((th) => th.textContent);
  const rows = all.slice(1);
  const cell = (row, name) => { assert.ok(head.includes(name), name); return row.childNodes[head.indexOf(name)].textContent; };
  data.steps.forEach((s, k) => {
    const said = Object.values(data.counts.steps[s.id]).reduce((a, b) => a + moves.reduce((m, c) => m + b.classes[c], 0), 0);
    assert.equal(cell(rows[k], 'Moved'), String(said), s.id);
    const side = (name) => Object.values(data.counts.steps[s.id]).reduce((a, b) => a + b.missing[name] + b.missing.both, 0);
    assert.equal(cell(rows[k], 'Missing before'), String(side('before')), s.id + ': missing before');
    assert.equal(cell(rows[k], 'Missing after'), String(side('after')), s.id + ': missing after');
    // every verdict worth a look has its column, with the file's count (issue 3: "claimed, not judged")
    for (const v of ['as claimed', 'off claim', 'not claimed', 'claimed, not moved', 'claimed, not judged', 'within noise']) {
      const name = v[0].toUpperCase() + v.slice(1);
      const total = s.claim ? String(Object.values(data.counts.steps[s.id]).reduce((a, b) => a + b.verdicts[v], 0)) : '—';
      assert.equal(cell(rows[k], name), total, s.id + ': ' + v);
    }
  });
  assert.notEqual(rows.map((r) => cell(r, 'Missing before')).join(), rows.map((r) => cell(r, 'Missing after')).join(),
    'the example has a step with missing values on one side only');
  assert.ok(rows.some((r) => !['0', '—'].includes(cell(r, 'Claimed, not judged'))), 'the example leaves a claim open');
  // each verdict column reads its own count: the example has as many open as not moved, so
  // one value is moved from unchanged to open in a copy
  const apart = example();
  const water = apart.counts.steps['mapping-2']['x:water'].verdicts;
  water.unchanged -= 1; water['claimed, not judged'] += 1;
  const at = apart.steps.findIndex((s) => s.id === 'mapping-2');
  const apartRows = dom.page(apart).byId['steps-table'].all().filter((n) => n.tagName === 'TR').slice(1);
  assert.equal(cell(apartRows[at], 'Claimed, not judged'), '2');
  assert.equal(cell(apartRows[at], 'Claimed, not moved'), '1');
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

// the string literals of a script, its comments left out
const stringsOf = (source) => {
  const found = [];
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (c === '/' && source[i + 1] === '/') { i = source.indexOf('\n', i); if (i < 0) break; }
    else if (c === '/' && source[i + 1] === '*') { i = source.indexOf('*/', i + 2) + 1; if (i <= 0) break; }
    else if (c === "'" || c === '"' || c === '`') {
      let j = i + 1, text = '';
      while (j < source.length && source[j] !== c) { if (source[j] === '\\') { text += source[j + 1]; j += 2; } else text += source[j++]; }
      found.push(text);
      i = j;
    }
  }
  return found;
};

test('nothing drawn calls a move better or worse (A22)', () => {
  // what the script draws, in each view; the page's own words are read in the written page
  // (`test_a22_the_reference_is_neutral_after_step_0`)
  const drawn = dom.page(example(), { 'p01-fix-1.json': wheat() });
  const seen = [drawn.text()];
  for (const view of ['sd.item=p01', 'sd.step=fix-1', 'sd.step=step-0&sd.item=p02']) { drawn.open(view); seen.push(drawn.text()); }
  const text = seen.join('\n').toLowerCase();
  assert.ok(text.includes('the whole way') && text.includes('what it is made of'), 'the views were drawn');
  for (const word of ['better', 'worse', 'improve', 'closer']) assert.ok(!text.includes(word), word);
  // and what it draws only in a branch these views do not reach ("Every part is listed."
  // shows only where no part is left out): every string the script holds
  const strings = stringsOf(fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'sentier_diagnostics', 'page', 'diagnostics.js'), 'utf8'));
  assert.ok(strings.includes('Every part is listed. ') && strings.includes('nothing explains it'), 'the script\'s strings were read');
  assert.deepEqual(strings.filter((t) => t.includes('\n')), [], 'each string ends on its own line: the script was read in step');
  for (const word of ['better', 'worse', 'improve', 'closer']) assert.deepEqual(strings.filter((t) => t.toLowerCase().includes(word)), [], word);
});

// a drawn table as its rows, each cell's text under its column's name
const tableRows = (table) => {
  const part = (tag) => table.childNodes.find((n) => n.tagName === tag);
  const head = part('THEAD').childNodes[0].childNodes.map((th) => th.textContent);
  return part('TBODY').childNodes.map((tr) => Object.fromEntries(tr.childNodes.map((cell, i) => [head[i], cell.textContent])));
};
const within = (node) => [node, ...node.childNodes.flatMap(within)];

test('a host can lead with the absolute scores from the first and last state', () => {
  const data = example(), drawn = dom.page(data);
  drawn.root.setAttribute('data-sd-score-summary', 'true');
  drawn.open('sd.item=p01');
  const table = drawn.byId['item-body'].firstChild.firstChild;
  assert.equal(table.getAttribute('data-sd'), 'score-summary');
  const rows = tableRows(table);
  const item = data.items.find((i) => i.id === 'p01');
  assert.equal(rows.length, data.indicators.length);
  data.indicators.forEach((ind, i) => {
    assert.equal(rows[i][data.states[0].label], page.formatNumber(item.values[ind.id][0]));
    assert.equal(rows[i][data.states.at(-1).label], page.formatNumber(item.values[ind.id].at(-1)));
  });
});

test('the item view draws each result in its own row and column, and each part of a breakdown on its own line (issue 14)', () => {
  const d = example();
  const drawn = dom.page(d, { 'p01-fix-1.json': wheat() });
  drawn.open('sd.item=p01');
  const item = d.items.find((i) => i.id === 'p01');
  const tables = within(drawn.byId['item-body']).filter((n) => n.tagName === 'TABLE');
  let checked = 0;
  for (const ind of d.indicators) {
    const values = item.values[ind.id];
    const rows = tableRows(tables.find((t) => t.getAttribute('data-indicator') === ind.id));
    d.steps.forEach((s, k) => {
      assert.equal(rows[k].Before, page.formatNumber(values[k]), `${ind.id} ${s.id} before`);
      assert.equal(rows[k].After, page.formatNumber(values[k + 1]), `${ind.id} ${s.id} after`);
      assert.equal(rows[k].Verdict, item.verdicts[ind.id][k] || '—', `${ind.id} ${s.id} verdict`);
      checked += values[k] !== values[k + 1];
    });
    assert.equal(rows[d.steps.length].Before, page.formatNumber(values[0]));
    assert.equal(rows[d.steps.length].After, page.formatNumber(values[values.length - 1]));
    assert.equal(rows[d.steps.length].Verdict, '—', 'the whole way has no claim');
  }
  assert.ok(checked >= 2, 'some results moved, so before and after differ');
  assert.ok(Object.values(item.verdicts).flat().some((v) => v && v !== 'unchanged'), 'a verdict other than unchanged is drawn');
  const parts = tables.filter((t) => tableRows(t).length && 'Part' in tableRows(t)[0]);
  const bd = wheat();
  assert.equal(parts.length, Object.keys(bd.indicators).length);
  Object.values(bd.indicators).forEach((entry, i) => {
    const rows = tableRows(parts[i]);
    const lines = [...entry.parts.map((p) => [p.label, p.kind || '', p.values]), [null, '', entry.rest], ['Total', '', entry.total]];
    assert.equal(rows.length, lines.length);
    lines.forEach(([label, kind, pair], k) => {
      if (label !== null) assert.equal(rows[k].Part, label);
      assert.equal(rows[k].Kind, kind);
      assert.equal(rows[k].Before, page.formatNumber(pair[0]), `${rows[k].Part} before`);
      assert.equal(rows[k].After, page.formatNumber(pair[1]), `${rows[k].Part} after`);
      // the change is after less before, with its sign
      const change = pair[1] - pair[0];
      assert.equal(rows[k].Change, change === 0 ? '=' : (change > 0 ? '+' : '−') + page.formatNumber(Math.abs(change)), `${rows[k].Part} change`);
    });
    assert.ok(entry.parts.some((p) => p.values[0] !== p.values[1]));
  });
});

test('the whole way and the steps are drawn with each count in its own column (issue 14)', () => {
  const d = example();
  const drawn = dom.page(d);
  const n = (x) => String(x).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const label = (id) => d.steps.find((s) => s.id === id).label;
  const whole = tableRows(drawn.byId['total-table']);
  assert.equal(whole.length, d.indicators.length);
  d.indicators.forEach((ind, k) => {
    const row = whole[k], block = d.counts.total[ind.id], att = d.attribution[ind.id];
    for (const [cls, count] of Object.entries(block.classes)) assert.equal(row[cls], n(count), `${ind.id} ${cls}`);
    assert.equal(row.Up, n(block.directions.up), ind.id);
    assert.equal(row.Down, n(block.directions.down), ind.id);
    const ranked = Object.entries(att.dominant).filter(([, c]) => c).sort((a, b) => b[1] - a[1]).map(([id, c]) => `${label(id)} (${c})`);
    assert.equal(row['Largest step'], ranked.join(', ') || 'none', ind.id);
    assert.equal(row['Spread over steps'], n(att.spread));
    assert.equal(row['Not attributable'], n(att.not_attributable));
    assert.equal(row['Moved by what nothing explains'], n(att.unexplained_moved));
  });
  assert.ok(d.indicators.some((ind) => d.counts.total[ind.id].directions.up !== d.counts.total[ind.id].directions.down));
  assert.ok(d.indicators.some((ind) => Object.values(d.attribution[ind.id].dominant).filter(Boolean).length > 1), 'a ranking of two steps');
  const steps = tableRows(drawn.byId['steps-table']);
  d.steps.forEach((s, k) => {
    const sum = (f) => n(Object.values(d.counts.steps[s.id]).reduce((a, b) => a + f(b), 0));
    assert.equal(steps[k].Up, sum((b) => b.directions.up), s.id);
    assert.equal(steps[k].Down, sum((b) => b.directions.down), s.id);
    assert.equal(steps[k].Explained, s.explained ? 'yes' : 'no: nothing explains it', s.id);
  });
  assert.ok(d.steps.some((s) => s.explained) && d.steps.some((s) => !s.explained), 'steps of both kinds');
});

test('the page takes each edge it shares with the Python where the Python does: ten times, a zero, a large noise (issue 15)', () => {
  // steps cancel beyond ten times the whole difference, not at it
  const ten = page.splitOf([1, 6.5, 2], [true, true], 'differs');
  assert.equal(ten.factor, 10);
  assert.ok(!page.splitText(ten).includes('cancel'), page.splitText(ten));
  assert.match(page.splitText(page.splitOf([1, 6.75, 2], [true, true], 'differs')), /the steps cancel: their differences add up to 10\.5 times/);
  // a result of exactly 0 is "0"; one within the floor, of either sign, is "≈ 0"
  assert.equal(page.cellView(0, 5, 'zero reference', 'up').text, 'from 0');
  assert.equal(page.cellView(-1e-12, 5, 'zero reference', 'up').text, 'from ≈ 0');
  assert.equal(page.cellView(5, 0, 'zero result', 'down').text, 'to 0');
  assert.equal(page.cellView(5, -1e-12, 'zero result', 'down').text, 'to ≈ 0');
  // a noise of exactly 1 % is not large (chain.LARGE_NOISE)
  const noise = (size) => page.noiseText({ measured: true, between: ['a', 'b'], by: { x: size }, note: null }, ['x']);
  assert.ok(!noise(0.01).includes('large'), noise(0.01));
  // a noise called large never reads as 1 % itself: it takes the digits that show it is
  // over, and where six do not, it is "just over 1 %" (review of 9a11c09)
  assert.match(noise(0.010000000000000002), /large: just over 1 %$/);
  assert.match(noise(0.0100001), /large: up to 1\.00001 %$/);
  assert.match(noise(0.0104), /large: up to 1\.04 %$/);
  assert.match(noise(0.0100016), /large: up to 1\.0002 %$/); // five digits where they do
  // and where a step's noise is the sum of its two states'
  const said = (sizes) => {
    const d = example();
    d.states.filter((s) => s.noise && s.noise.measured).forEach((s, k) => { s.noise.by = { [d.indicators[0].id]: sizes[k] }; });
    const drawn = dom.page(d);
    drawn.open('sd.step=rebuilt');
    return drawn.byId['step-said'].textContent;
  };
  assert.match(said([0.005, 0.005]), /the sum of its two ends'/);
  assert.ok(!said([0.005, 0.005]).includes('large'), said([0.005, 0.005]));
  assert.match(said([0.005, 0.0051]), /large: up to 1\.01 %/);
  assert.match(said([0.005, 0.0050001]), /large: up to 1\.00001 %\./);
  assert.match(said([0.005, 0.0050000001]), /large: just over 1 %\./);
  // steps said to cancel never add up to "10 times", the bound itself
  const cancel = (factor) => page.splitText({ state: 'split', shares: [1], sum: 1, unexplained: null, factor, bound: 0 });
  assert.match(cancel(10.001), /add up to 10\.001 times/);
  assert.match(cancel(10.0000001), /add up to just over 10 times/);
  assert.ok(!cancel(10).includes('cancel'), cancel(10));
});


test('a class the page does not know sorts after every class it knows, and keys compare as Python compares tuples (issue 15)', () => {
  const known = Math.max(...Object.values(page.RANK));
  assert.ok(page.severityKey(1, 2, 'a class of a later format')[0] > known);
  assert.ok(page.severityKey(null, 2, 'a class of a later format')[0] > known);
  // part by part, then the shorter first: [1] < [1, 0], as (1,) < (1, 0) in Python
  assert.ok(page.compareKeys([1], [1, 0]) < 0);
  assert.ok(page.compareKeys([1, 0], [1]) > 0);
  assert.equal(page.compareKeys([1, -2], [1, -2]), 0);
  assert.ok(page.compareKeys([0, 5], [1]) < 0);
});

test('the item view splits only what can be split and draws the breakdown of its own step', () => {
  const drawn = dom.page(example(), { 'p01-fix-1.json': wheat() });
  drawn.open('sd.item=p01');
  const body = drawn.byId['item-body'].seen().join(' ');
  assert.ok(body.includes('What it is made of'));
  assert.ok(body.includes('Fertiliser') || body.includes('Total'), 'the breakdown is drawn');
  assert.ok(/100\.0 %/.test(body), 'the sum of the shares');
  drawn.open('sd.item=p03'); // barley: no water use in the rebuilt state
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
  drawn.open('sd.item=p05');
  const body = drawn.byId['item-body'].seen().join(' ');
  assert.ok(body.includes('is of another product or another step: not drawn'), body.slice(-300));
});

test('a breakdown of the right step and another item is not drawn under it (issue 5)', () => {
  const data = example();
  const step = Object.keys(data.items.find((i) => i.id === 'p01').breakdowns)[0];
  const rice = data.items.find((i) => i.id === 'p05');
  rice.breakdowns = { [step]: 'p01-fix-1.json' };
  const drawn = dom.page(data, { 'p01-fix-1.json': wheat() });
  drawn.open('sd.item=p05');
  const body = drawn.byId['item-body'].seen().join(' ');
  assert.ok(body.includes('is of another product or another step: not drawn'), body.slice(-300));
});

test('the page refuses a breakdown for each reason the check has, and says which (issue 5)', () => {
  // each case changes one thing of wheat's breakdown of its step, or where it is named
  const data = example();
  const step = Object.keys(data.items.find((i) => i.id === 'p01').breakdowns)[0];
  const shown = (bd, comp = step) => {
    const d = example();
    d.items.find((i) => i.id === 'p01').breakdowns = { [comp]: 'b.json' };
    const drawn = dom.page(d, { 'b.json': bd });
    drawn.open('sd.item=p01');
    return drawn.byId['item-body'].seen().join(' ');
  };
  const indicator = Object.keys(wheat().indicators)[0];
  const other = (b) => data.states.map((s) => s.id).find((id) => id !== b.from && id !== b.to);
  const cases = [
    ['is not a breakdown', (b) => { b.format = 'sentier-diagnostics-breakdown/2'; }],
    // the item's own breakdown, named for the whole way: its states are not the whole way's
    ['is of another product or another step', null, 'total'],
    // one of the three it names changed alone: another item, or a step that ends or starts elsewhere
    ['is of another product or another step', (b) => { b.item = 'p02'; }],
    ['is of another product or another step', (b) => { b.to = other(b); }],
    ['is of another product or another step', (b) => { b.from = other(b); }],
    ['holds no indicators', (b) => { b.indicators = {}; }],
    ['names an indicator this file does not hold, x:nowhere', (b) => { b.indicators['x:nowhere'] = b.indicators[indicator]; delete b.indicators[indicator]; }],
    ['is not of the shape of a breakdown in', (b) => { b.indicators[indicator].parts[0].values = [1]; }],
    ['is not of the shape of a breakdown in', (b) => { b.indicators[indicator].total = [b.indicators[indicator].total[0]]; }],
    ['is not of the shape of a breakdown in', (b) => { b.indicators[indicator].rest = [b.indicators[indicator].rest[0], 'x']; }],
    ['is not of the shape of a breakdown in', (b) => { b.indicators[indicator].parts = {}; }],
    ['is not of the shape of a breakdown in', (b) => { b.indicators[indicator] = null; }],
    ['does not add up', (b) => { b.indicators[indicator].rest[0] += 1; }],
    ['is not of this file', (b) => { const e = b.indicators[indicator]; e.total[1] += 1; e.rest[1] += 1; }],
    // off by a millionth: the check holds parts and totals to 1e-9, as the Python does (review of #34)
    ['does not add up', (b) => { const e = b.indicators[indicator]; e.rest[0] += 1e-6 * Math.abs(e.total[0]); }],
    ['is not of this file', (b) => { const e = b.indicators[indicator]; const off = 1e-6 * Math.abs(e.total[1]); e.total[1] += off; e.rest[1] += off; }],
  ];
  assert.ok(shown(wheat()).includes('What it is made of') && !/not drawn/.test(shown(wheat())), 'the breakdown itself is drawn');
  for (const [said, change, comp] of cases) {
    const bd = wheat();
    if (change) change(bd);
    const body = shown(bd, comp);
    assert.ok(body.includes('The breakdown b.json ' + said), said + ' | ' + body.slice(-240));
    assert.ok(body.includes(': not drawn.'), said);
  }
  // and off by less than 1e-9 of the size, it is drawn
  const close = wheat();
  close.indicators[indicator].rest[0] += 1e-11 * Math.abs(close.indicators[indicator].total[0]);
  assert.ok(!/not drawn/.test(shown(close)), 'within 1e-9');
});

test('a breakdown the page fetches is checked as one that came with it (issue 5)', async () => {
  const served = (bd) => (url) => (bd ? Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify(bd)) }) : Promise.resolve({ ok: false, status: 404 }));
  const opened = async (bd, comp) => {
    const d = example();
    const step = Object.keys(d.items.find((i) => i.id === 'p01').breakdowns)[0];
    d.items.find((i) => i.id === 'p01').breakdowns = { [comp || step]: 'b.json' };
    const drawn = dom.page(d, undefined, { protocol: 'http:', fetch: served(bd) });
    drawn.open('sd.item=p01');
    await new Promise((resolve) => setTimeout(resolve, 0));
    return drawn.byId['item-body'].seen().join(' ');
  };
  const right = await opened(wheat());
  assert.ok(!right.includes('not drawn') && !right.includes('is not with this page'), right.slice(-240));
  assert.ok(right.includes('What it is made of'));
  const other = await opened(wheat(), 'total');
  assert.ok(other.includes('The breakdown b.json is of another product or another step: not drawn.'), other.slice(-240));
  const gone = await opened(null);
  assert.ok(gone.includes('The breakdown b.json is not with this page.'), gone.slice(-240));
});

test('a file the page cannot draw draws nothing', () => {
  const data = example();
  data.counts.total = null;
  const drawn = dom.page(data);
  assert.equal(drawn.byId.content.hidden, true);
  assert.equal(drawn.byId.load.hidden, false);
  assert.equal(drawn.byId.title.textContent, '');
});

// a file of counts made from one of items, as `build(tier="counts")` writes it: no item, no
// explanation of one, and claims without their lists
const countsOf = (d) => {
  d.tier = 'counts';
  d.items = [];
  d.items_count.not_listed += d.items_count.listed;
  d.items_count.listed = 0;
  d.explanations = d.explanations.filter((e) => !e.about.item);
  d.steps.forEach((s) => { if (s.claim) s.claim.scope.forEach((e) => { e.items = null; }); });
  return d;
};

test('a file of counts beside a host\'s matrix says nothing of a matrix (review of #34)', () => {
  const counts = dom.page(countsOf(local()), undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: full() } });
  assert.equal(counts.byId.load.hidden, true, counts.byId['load-error'].textContent);
  assert.equal(counts.byId['matrix-said'].textContent, '');
  // the same file with its items takes the host's matrix
  const items = dom.page(local(), undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: full() } });
  assert.match(items.byId['matrix-said'].textContent, /matrix of all 10 products is loaded/);
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

test('a matrix that says other numbers of a listed item than its file is refused', () => {
  // a matrix left over from another run of the same chain: same title, states, steps and count
  const data = local();
  const listed = data.items[0].id;
  const at = full().items.findIndex((row) => row[0] === listed);
  const tripled = full(); tripled.values[at] = tripled.values[at].map((v) => (typeof v === 'number' ? v * 3 : v));
  assert.match(page.checkMatrix(tripled, data), new RegExp('item ' + listed + ', .*: its results or classes differ'));
  const reclassed = full();
  const code = reclassed.classes[at][0];
  const other = [...reclassed.classes.join('')].find((c) => c !== code); // another class the matrix itself uses
  reclassed.classes[at] = other + reclassed.classes[at].slice(1);
  assert.match(page.checkMatrix(reclassed, data), /its results or classes differ/);
  const renamed = full(); renamed.items[at][1] = 'Another name';
  assert.match(page.checkMatrix(renamed, data), /its name, place, group or unit differ/);
  const swapped = full(); swapped.items[at][0] = 'not-listed';
  assert.match(page.checkMatrix(swapped, data), /1 of the items this file lists are not in it/);
  // an item the file does not list has nothing to be held to
  const unlisted = full();
  const free = unlisted.items.findIndex((row) => !data.items.some((item) => item.id === row[0]));
  unlisted.values[free] = unlisted.values[free].map((v) => (typeof v === 'number' ? v * 3 : v));
  assert.equal(page.checkMatrix(unlisted, data), null);
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
  const served = (m) => () => Promise.resolve({ ok: true, status: 200, arrayBuffer: () => Promise.resolve(bytesOf(Buffer.from(JSON.stringify(m)))) });
  const drawn = dom.page(local(), undefined, { protocol: 'https:', fetch: served(full()) });
  await new Promise((done) => setImmediate(done));
  assert.equal(gridRows(drawn).length, 10);
  const other = full(); other.of.steps = other.of.steps.slice().reverse();
  const refused = dom.page(local(), undefined, { protocol: 'https:', fetch: served(other) });
  await new Promise((done) => setImmediate(done));
  assert.equal(gridRows(refused).length, 6);
  assert.match(refused.byId['matrix-said'].textContent, /not loaded: it is the matrix of another file/);
});

// a Buffer's own bytes, as a response's arrayBuffer() gives them
const bytesOf = (buffer) => buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.length);

test('a matrix over http is held to its size in bytes, and refused when it is not JSON, not UTF-8 or not served', async () => {
  const fetched = async (bytes, status) => {
    const drawn = dom.page(local(), undefined, { protocol: 'https:', fetch: () => Promise.resolve({ ok: !status, status: status || 200,
      arrayBuffer: () => Promise.resolve(bytes ? bytesOf(bytes) : null) }) });
    await new Promise((done) => setImmediate(done));
    return drawn.byId['matrix-said'].textContent;
  };
  // 2-byte characters: the text is half as long as the file, so only its size in bytes is over
  const max = 64 * 1024 * 1024, large = Buffer.alloc(max + 2, 'é');
  assert.equal(large.toString('utf8').length, max / 2 + 1);
  assert.match(await fetched(large), /matrix\.json is larger than 67\D108\D864 bytes/);
  assert.match(await fetched(Buffer.from('{"format": ')), /matrix\.json is not JSON/);
  assert.match(await fetched(Buffer.from([0x7b, 0xff, 0x7d])), /matrix\.json is not UTF-8 text/);
  assert.match(await fetched(null, 404), /matrix\.json could not be read \(404\)/);
});

test('a key written twice in one object is refused wherever the page reads JSON, as the Python refuses it (issue 19)', async () => {
  for (const text of ['{"a": 1, "a": 2}', '{"a\\u0062": 1, "ab": 2}', '{"a": 1, "b": {"c": 1, "c": 2}}', '[{"a": 1}, {"b": 1, "b": 2}]',
    '{"__proto__": 1, "__proto__": 2}', '{"x": [], "x": {}}']) {
    assert.throws(() => page.readJSON(text), /^Error: the key "[a-z_]+" is written twice in one object$/, text);
  }
  // the same key in two objects, a key's text inside a value, escapes inside a string
  for (const text of ['{"a": {"b": 1}, "b": {"b": 2}}', '{"a": [{"x": 1}, {"x": 2}]}', '["a", "a"]', '{"a": "}\\",{\\"a\\": [", "b": 1}',
    '{"": 1, "x": {"": 2}}', '{"a\\\\": 1, "a": 2}']) {
    assert.equal(JSON.stringify(page.readJSON(text)), JSON.stringify(JSON.parse(text)), text);
  }
  assert.throws(() => page.readJSON('{"a": NaN}'), SyntaxError);
  const twice = (value) => JSON.stringify(value).replace('"tier":', '"tier": "counts", "tier":');
  const data = dom.page(undefined, undefined, { scripts: { data: new dom.Text(twice(example())) } });
  assert.match(data.byId['load-error'].textContent, /The data of this page cannot be read: the key "tier" is written twice in one object/);
  // served as a response serves it: its text, or its bytes (a matrix, held to its size in bytes)
  const served = (text) => () => Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(text),
    arrayBuffer: () => Promise.resolve(bytesOf(Buffer.from(text))) });
  const matrix = dom.page(local(), undefined, { protocol: 'https:', fetch: served(JSON.stringify(full()).replace('"items":', '"items": [], "items":')) });
  await new Promise((done) => setImmediate(done));
  assert.match(matrix.byId['matrix-said'].textContent, /matrix\.json cannot be read: the key "items" is written twice/);
  const d = example();
  const step = Object.keys(d.items.find((i) => i.id === 'p01').breakdowns)[0];
  d.items.find((i) => i.id === 'p01').breakdowns = { [step]: 'b.json' };
  const breakdown = dom.page(d, undefined, { protocol: 'http:', fetch: served(JSON.stringify(wheat()).replace('"item":', '"item": "p02", "item":')) });
  breakdown.open('sd.item=p01');
  await new Promise((done) => setTimeout(done, 0));
  assert.match(breakdown.byId['item-body'].seen().join(' '), /The breakdown b\.json cannot be read: the key "item" is written twice in one object\. Not drawn\./);
  // a file picked, and one the address names
  const reader = class { readAsText(file) { this.result = file.text; this.onload(); } };
  const picked = (text) => {
    const drawn = dom.page(undefined, undefined, { globals: { FileReader: reader } });
    drawn.byId.file.dispatch('change', { target: { files: [{ text }] } });
    return drawn;
  };
  assert.match(picked(twice(example())).byId['load-error'].textContent, /The file cannot be read: the key "tier" is written twice in one object/);
  assert.equal(picked(JSON.stringify(example())).byId.load.hidden, true);
  const asked = dom.page(undefined, undefined, { protocol: 'https:', search: '?file=d.json', fetch: served(twice(example())) });
  await new Promise((done) => setImmediate(done));
  assert.match(asked.byId['load-error'].textContent, /d\.json cannot be read: the key "tier" is written twice in one object/);
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
  // a move without a factor first, then the largest factor among the values that moved, then the worst value
  const worst = (id) => {
    const i = data.items.find((x) => x.id === id);
    let furthest = 0;
    const keys = data.indicators.map((ind) => {
      const v = i.values[ind.id], cls = i.classes[ind.id][4];
      if (['zero reference', 'zero result', 'sign change'].includes(cls)) furthest = Infinity;
      else if (cls === 'differs' || cls === 'beyond 10x') furthest = Math.max(furthest, Math.abs(Math.log10(Math.abs(v[v.length - 1] / v[0]))));
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

test('a heading sorts its column as its title says: moves without a factor first, then the largest factor (issue 32)', () => {
  // climate holds a sign change, a zero result and factors, the smallest of them ×1.0x: a
  // move without a factor lies further apart than any factor, so it stands above them all
  const data = example();
  const drawn = dom.page(data);
  const head = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]');
  const climate = head.find((th) => th.getAttribute('title') && th.getAttribute('title').indexOf('Climate') === 0);
  const button = climate.querySelector('button[type="button"]');
  assert.match(button.getAttribute('title'), /the moves that have no factor first \(from or to zero, a sign change\), then the largest factor between the two results/);
  button.dispatch('click', {});
  const after = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').find((th) => th.getAttribute('aria-sort'));
  assert.equal(after.getAttribute('aria-sort'), 'descending');
  const order = gridRows(drawn).map((tr) => tr.getAttribute('data-item'));
  const pair = (id) => { const i = data.items.find((x) => x.id === id); const v = i.values['x:climate']; return [v[0], v[v.length - 1], i.classes['x:climate'][4]]; };
  const NO_FACTOR = ['zero reference', 'zero result', 'sign change'];
  const furthest = (id) => { const [b, a, c] = pair(id); return [NO_FACTOR.includes(c) ? -Infinity : c === 'differs' || c === 'beyond 10x' ? -page.distance(b, a) : -0].concat(page.severityKey(b, a, c)); };
  for (let k = 1; k < order.length; k++) assert.ok(page.compareKeys(furthest(order[k - 1]), furthest(order[k])) <= 0, order.join());
  const classes = order.map((id) => pair(id)[2]);
  const lastNoFactor = Math.max(...classes.map((c, at) => (NO_FACTOR.includes(c) ? at : -1)));
  const firstFactor = classes.findIndex((c) => c === 'differs' || c === 'beyond 10x');
  assert.ok(lastNoFactor >= 0 && firstFactor >= 0, 'the column holds both kinds: ' + classes.join());
  assert.ok(lastNoFactor < firstFactor, 'every move without a factor stands above every factor: ' + classes.join());
  // one order: a column sorts as the Python rule orders values from the worst (rule.severity)
  const severity = order.slice().sort((x, y) => page.compareKeys(page.severityKey(...pair(x)), page.severityKey(...pair(y))));
  assert.deepEqual(order.filter((id) => NO_FACTOR.includes(pair(id)[2]) || ['differs', 'beyond 10x'].includes(pair(id)[2])),
    severity.filter((id) => NO_FACTOR.includes(pair(id)[2]) || ['differs', 'beyond 10x'].includes(pair(id)[2])));
});

test('sorting from the keyboard keeps the focus on the heading it sorted by (issue 32)', () => {
  const drawn = dom.page(example());
  const climate = () => drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').find((th) => (th.getAttribute('title') || '').indexOf('Climate') === 0).querySelector('button[type="button"]');
  const first = climate();
  drawn.document.activeElement = first;
  first.dispatch('click', {});
  const again = climate();
  assert.notEqual(again, first, 'the headings are drawn anew');
  assert.equal(again.focused, true, 'the new button of the same heading has the focus');
  drawn.document.activeElement = again;
  again.dispatch('click', {}); // back to the furthest apart first: still this heading
  assert.equal(climate().focused, true);
  // every heading of its kind, not only the first: the focus goes to the one sorted by
  // (review of #34)
  for (const name of ['Climate', 'Water', 'Human']) {
    const each = dom.page(example());
    const heading = () => each.byId['grid-table'].querySelectorAll('th[scope="col"]').find((th) => (th.getAttribute('title') || '').indexOf(name) === 0).querySelector('button[type="button"]');
    each.document.activeElement = heading();
    heading().dispatch('click', {});
    assert.equal(heading().focused, true, name);
    assert.deepEqual(each.byId['grid-table'].querySelectorAll('button[type="button"]').filter((b) => b.focused), [heading()], name);
  }
  const unfocused = dom.page(example());
  const other = unfocused.byId['grid-table'].querySelectorAll('th[scope="col"]').find((th) => (th.getAttribute('title') || '').indexOf('Climate') === 0).querySelector('button[type="button"]');
  other.dispatch('click', {}); // a click with the focus elsewhere moves no focus
  assert.ok(!unfocused.byId['grid-table'].querySelectorAll('button[type="button"]').some((b) => b.focused));
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
  assert.equal(drawn.context.location.hash, 'sd.item=' + unlisted);
  drawn.open('sd.item=' + unlisted);
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
    drawn.open('sd.item=' + item.id);
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
  data.states[0].noise = { measured: false, between: null, by: null, note: null }; // a build says its noise
  const drawn = dom.page(data);
  assert.equal(drawn.byId.content.hidden, false);
  assert.equal(drawn.byId['steps-zero'].hidden, true);
  const text = drawn.text();
  assert.doesNotMatch(text, /Step 0\b/);
  data.steps.forEach((s, k) => assert.ok(text.includes('Step ' + (k + 1) + ': ' + s.label), s.label));
  const rows = drawn.byId['steps-table'].all().filter((n) => n.tagName === 'TR' && n.firstChild && n.firstChild.tagName === 'TD');
  assert.deepEqual(rows.map((row) => row.firstChild.textContent), data.steps.map((s, k) => String(k + 1)));
  drawn.open('sd.item=' + encodeURIComponent(data.items[0].id));
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
  const look = ['off claim', 'not claimed', 'claimed, not moved', 'claimed, not judged'];
  const found = look.filter((v) => Object.values(data.counts.steps[step.id]).some((b) => b.verdicts[v]));
  if (found.length) found.forEach((v) => assert.ok(said.includes(v), v));
  else assert.match(said, /as claimed/);
  assert.equal(drawn.context.location.hash, 'sd.step=' + encodeURIComponent(step.id));
  assert.equal(chips(drawn)[k + 1].getAttribute('aria-pressed'), 'true');
});

test('a claim left open is marked in the grid and named in the legend (issue 3)', () => {
  const data = example();
  const drawn = dom.page(data);
  const k = data.steps.findIndex((s) => s.id === 'mapping-2');
  chips(drawn)[k + 1].dispatch('click', {});
  const marks = (id) => gridRows(drawn).find((tr) => tr.getAttribute('data-item') === id)
    .all().filter((s) => /verdict-look/.test(s.className || '')).map((s) => s.title || s.getAttribute('title'));
  assert.deepEqual(marks('p03'), ['claimed, not judged'], 'Barley, missing before the step its claim says must move it');
  assert.deepEqual(marks('p02'), ['claimed, not moved']);
  assert.match(drawn.text(), /◇ claimed, not judged/);
  assert.match(drawn.byId['step-said'].textContent, /1 value claimed, not judged ◇/);
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

test('a host that routes by its hash keeps the page out of the address, and the page keeps its view (review of #34)', () => {
  const data = example();
  const step = data.steps[2];
  const pressed = (drawn) => chips(drawn).find((c) => c.getAttribute('aria-pressed') === 'true').getAttribute('data-comp');
  // without it, the page's part joins the host's route: a hash router reads it as its path
  const joined = dom.page(data, undefined, { hash: '/products/12' });
  const first = gridRows(joined)[0].getAttribute('data-item');
  gridRows(joined)[0].childNodes[0].dispatch('click', {});
  assert.equal(joined.context.location.hash, '/products/12&sd.item=' + first);
  // with it, the address is the host's alone, and the page keeps what is chosen itself
  const off = { 'data-sd-address': 'off' };
  const drawn = dom.page(data, undefined, { hash: '/products/12', attributes: off });
  chips(drawn).find((c) => c.getAttribute('data-comp') === step.id).dispatch('click', {});
  const item = gridRows(drawn)[0].getAttribute('data-item');
  gridRows(drawn)[0].childNodes[0].dispatch('click', {});
  assert.equal(drawn.context.location.hash, '#/products/12');
  assert.equal(drawn.byId.item.hidden, false, 'the item opens');
  assert.match(drawn.byId['item-title'].textContent, new RegExp(data.items.find((i) => i.id === item).name));
  assert.equal(pressed(drawn), step.id);
  // the host's route moves on: the page keeps its step and its item, and leaves the open
  // item as it is: not drawn again, so its scroll and the focus in it stay
  const shown = drawn.byId['item-body'].firstChild;
  assert.ok(shown);
  drawn.open('/products/13');
  assert.equal(pressed(drawn), step.id);
  assert.equal(drawn.byId.item.hidden, false);
  assert.equal(drawn.byId['item-body'].firstChild, shown, 'the open item is not drawn again');
  // an address in the page's own words is not the page's
  drawn.open('sd.step=' + encodeURIComponent(data.steps[0].id));
  assert.equal(pressed(drawn), step.id);
  assert.equal(drawn.byId['item-body'].firstChild, shown);
  // closing the item leaves the address as the host has it, and keeps the step
  drawn.byId['item-close'].dispatch('click', {});
  assert.equal(drawn.byId.item.hidden, true);
  assert.equal(drawn.context.location.hash, '#sd.step=' + encodeURIComponent(data.steps[0].id));
  assert.equal(pressed(drawn), step.id);
  // and none opens it when it is drawn
  const asked = dom.page(data, undefined, { hash: 'sd.step=' + encodeURIComponent(step.id) + '&sd.item=' + encodeURIComponent(data.items[0].id), attributes: off });
  assert.equal(asked.byId.item.hidden, true);
  assert.equal(pressed(asked), 'total');
  // what is chosen survives the page reading its parts again, as it does when its matrix comes
  const later = dom.page(local(), undefined, { attributes: { ...off, 'data-sd-matrix': 'matrix.js' } });
  const chosen = local().steps[1].id;
  chips(later).find((c) => c.getAttribute('data-comp') === chosen).dispatch('click', {});
  gridRows(later)[0].childNodes[0].dispatch('click', {});
  later.context.SENTIER_DIAGNOSTICS_MATRIX = full();
  later.head.querySelectorAll('script[src]')[0].onload();
  assert.match(later.byId['matrix-said'].textContent, /matrix of all 10 products is loaded/);
  assert.equal(pressed(later), chosen);
  assert.equal(later.byId.item.hidden, false);
});

test('an address with a step opens the page on that step, and with an item on that item', () => {
  const data = example();
  const step = data.steps[2];
  const drawn = dom.page(data);
  drawn.open('sd.step=' + encodeURIComponent(step.id) + '&sd.item=' + encodeURIComponent(data.items[0].id));
  assert.equal(chips(drawn).find((c) => c.getAttribute('aria-pressed') === 'true').getAttribute('data-comp'), step.id);
  assert.equal(drawn.byId.item.hidden, false);
  // closing the item keeps the step
  drawn.byId['item-close'].dispatch('click', {});
  assert.equal(drawn.byId.item.hidden, true);
  assert.equal(drawn.context.location.hash, 'sd.step=' + encodeURIComponent(step.id));
  // an unknown step falls back to the whole way
  drawn.open('sd.step=nothing-of-the-kind');
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
  for (const v of ['as claimed', 'off claim', 'not claimed', 'claimed, not moved', 'claimed, not judged']) {
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

// ------------------------------------------------------------------ a run of steps

const pressed = (drawn) => chips(drawn).filter((c) => c.getAttribute('aria-pressed') === 'true').map((c) => c.getAttribute('data-comp'));
const chipOf = (drawn, id) => chips(drawn).find((c) => c.getAttribute('data-comp') === id);
const pickRows = (drawn) => drawn.byId['pick-list'].querySelectorAll('button[data-pick]');
const rowOf = (drawn, k) => pickRows(drawn).find((b) => b.getAttribute('data-pick') === String(k));
const chosenRows = (drawn) => pickRows(drawn).filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => +b.getAttribute('data-pick'));
const together = () => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'together.json'), 'utf8')).runs;
test('two results near the largest float on either side of zero lie two apart, as the Python says, not infinitely (issue 37)', () => {
  assert.deepEqual(page.severityKey(1e308, -1e308, 'sign change'), [page.RANK['sign change'], -2]);
  assert.deepEqual(page.severityKey(-1.7e308, 1.7e308, 'sign change'), [page.RANK['sign change'], -2]);
  assert.equal(page.judge(1e308, -1e308, 0, 0.01, null)[0], 'sign change');
});

const boundaries = () => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'boundaries.json'), 'utf8')).cases;
const withMatrix = () => dom.page(local(), undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: full() } });
const tagged = (node, tag) => (node.tagName === tag ? [node] : []).concat(...(node.childNodes || []).map((c) => tagged(c, tag)));
const ids = (data, first, last) => data.steps.slice(first, last + 1).map((s) => s.id);
// the address of a run of steps of a file, as the page writes it: its first and last step
const runAddress = (data, first, last) => 'sd.steps=' + encodeURIComponent(data.steps[first].id) + ':' + encodeURIComponent(data.steps[last].id);
// what a grid shows: per row, the class of each indicator
const gridClasses = (drawn, data) => {
  const heads = drawn.byId['grid-table'].querySelectorAll('th[scope="col"]').slice(2)
    .map((th) => data.indicators.find((i) => th.getAttribute('title').indexOf(i.name) === 0).id);
  const out = {};
  for (const row of gridRows(drawn)) {
    const cells = row.childNodes.filter((n) => n.tagName === 'TD').slice(1);
    out[row.getAttribute('data-item')] = Object.fromEntries(heads.map((ind, k) => [ind, cells[k].getAttribute('data-class')]));
  }
  return out;
};

test('the page judges with the rule of the Python on every acceptance case', () => {
  for (const c of cases) {
    assert.deepEqual(page.judge(c.before, c.after, c.floor, c.tolerance, c.noise), [c.class, c.direction, c.band], c.id);
  }
});

test('the page judges as the Python on every edge of the rule, down to the last bit', () => {
  const all = boundaries();
  assert.ok(all.length > 700, String(all.length));
  for (const c of all) {
    assert.deepEqual(page.judge(c.before, c.after, c.floor, c.tolerance, c.noise), [c.class, c.direction, c.band], c.why + ': ' + c.before + ' to ' + c.after);
  }
});

test('a run of steps is the two built states it lies between, never a sum', () => {
  assert.deepEqual(page.runPair([1, 2, 2.5, 4], 1, 2), [2, 4]);
  assert.deepEqual(page.runPair([1, null, 2.5, 4], 2, 2), [2.5, 4]);
  assert.deepEqual(page.runPair([1, 2, null, 4], 0, 1), [1, null]);
});

test('two states are compared with the sum of their noise; the published results are exact', () => {
  const built = (by) => ({ kind: 'build', noise: { measured: by !== null, between: by && ['x', 'y'], by: by, note: null } });
  const published = { kind: 'published' };
  assert.deepEqual(page.noiseOfStates(built({ a: 1e-9 }), built({ a: 3e-9, b: 2e-9 })), { a: 1e-9 + 3e-9, b: 2e-9 });
  assert.deepEqual(page.noiseOfStates(published, built({ a: 0 })), { a: 0 });
  assert.equal(page.noiseOfStates(published, built(null)), null);
  assert.equal(page.endsKnown(published, built({ a: 0.1 }), 'a'), 2);
  assert.equal(page.endsKnown(built(null), built({ a: 0.1 }), 'a'), 1);
  assert.equal(page.endsKnown(built({ b: 0.1 }), built(null), 'a'), 0);
  assert.equal(page.statesCarryNoise({ states: [published, built(null)] }), true);
  assert.equal(page.statesCarryNoise({ states: [published, { kind: 'build' }] }), false);
});

test('a run judged by the page has the classes and counts of the Python reference, item by item', () => {
  const data = local();
  assert.equal(together().length, 5);
  for (const one of together()) {
    const drawn = withMatrix();
    drawn.open(runAddress(data, one.first, one.last));
    const at = one.first + ' to ' + one.last;
    assert.equal(drawn.byId['step-said'].textContent.indexOf('The address'), -1, drawn.byId['step-said'].textContent);
    assert.deepEqual(pressed(drawn), ids(data, one.first, one.last), at);
    assert.deepEqual(gridClasses(drawn, data), one.classes, at);
    // every bar of every card is the reference's count, by its own words
    for (const card of cards(drawn)) {
      const block = one.blocks[card.getAttribute('data-indicator')];
      for (const bar of card.childNodes[2].childNodes) {
        const said = /^(.*?)(?: \(.*\))?: ([\d\s]+) of ([\d\s]+)$/.exec(bar.getAttribute('title'));
        const count = (said[1] in block.bands ? block.bands : block.classes)[said[1]];
        assert.equal(+said[2].replace(/\s/g, ''), count, at + ' ' + said[1]);
        assert.equal(+said[3].replace(/\s/g, ''), block.pairs);
      }
    }
  }
});

test('a run is judged with the largest tolerance of its steps, never the smallest', () => {
  // steps of 1e-5 and 1e-2: an item that moves by 5e-3 in the first differs there and
  // agrees in the run of the two (tests/test_together.py, `mixed_tolerances`)
  const mixed = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'together.json'), 'utf8')).tolerances;
  const opened = (address) => {
    const drawn = dom.page(mixed.data, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: mixed.matrix } });
    drawn.open(address);
    return gridClasses(drawn, mixed.data);
  };
  assert.deepEqual(opened('sd.step=' + mixed.data.steps[0].id).t, { 'x:a': 'differs', 'x:b': 'differs' });
  const run = opened(runAddress(mixed.data, mixed.first, mixed.last));
  assert.deepEqual(run.t, mixed.classes.t);
  assert.deepEqual(mixed.classes.t, { 'x:a': 'agrees', 'x:b': 'agrees' });
});

test('a run is judged with the sum of the noise of its two ends, as the Python reference', () => {
  // States 1 and 3 measured 3 % and 1 %: q moved by 3.4 % between them (tests/test_together.py)
  const sum = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'together.json'), 'utf8')).noise;
  const drawn = dom.page(sum.data, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: sum.matrix } });
  drawn.open(runAddress(sum.data, sum.first, sum.last));
  const run = gridClasses(drawn, sum.data);
  assert.ok('q' in run && 'n' in run, Object.keys(run).join(','));
  for (const id of Object.keys(run)) assert.deepEqual(run[id], sum.classes[id], id);
  assert.equal(sum.classes.q['x:a'], 'within noise');
  assert.match(drawn.byId['step-said'].textContent, /Noise the sum of its two ends' \(State 1 measured, State 3 measured\)/);
});

test('the strip: the whole way first, then a cell per step, its bar as high as what moved in it', () => {
  const data = example();
  const drawn = dom.page(data);
  assert.deepEqual(chips(drawn).map((c) => c.getAttribute('data-comp')), ['total'].concat(data.steps.map((s) => s.id)));
  // the whole way is every step
  assert.deepEqual(pressed(drawn), ['total'].concat(data.steps.map((s) => s.id)));
  const moved = (comp) => Object.values(data.counts.steps[comp])
    .reduce((sum, b) => sum + ['differs', 'beyond 10x', 'zero reference', 'zero result', 'sign change'].reduce((a, k) => a + b.classes[k], 0), 0);
  data.steps.forEach((s) => assert.match(chipOf(drawn, s.id).getAttribute('title'), new RegExp(moved(s.id) + ' values? moved')));
  const rebuilt = data.steps.find((s) => !s.explained);
  assert.match(chipOf(drawn, rebuilt.id).className, /sd-unexplained/);
  assert.match(chipOf(drawn, rebuilt.id).getAttribute('title'), /nothing explains it/);
  const claimed = data.steps.find((s) => s.claim && Object.values(data.counts.steps[s.id]).some((b) => b.verdicts['not claimed']));
  assert.match(chipOf(drawn, claimed.id).getAttribute('title'), /not claimed/);
  // a click on a cell chooses that step alone, and the grid follows
  chipOf(drawn, data.steps[1].id).childNodes[0].dispatch('click', {}); // on its bar: the click reaches the cell
  assert.deepEqual(pressed(drawn), [data.steps[1].id]);
  assert.ok(drawn.byId['grid-region'].getAttribute('aria-label').endsWith(': Step 1: ' + data.steps[1].label + ', the furthest apart first'),
    drawn.byId['grid-region'].getAttribute('aria-label'));
  // a long chain has no number under each cell, a short one has
  assert.match(drawn.byId.comparison.className, /sd-numbered/);
});

test('Shift-click chooses every step from one to another; steps apart are refused and said; the address keeps a run', () => {
  const data = example();
  const drawn = dom.page(data);
  chipOf(drawn, data.steps[1].id).dispatch('click', {});
  chipOf(drawn, data.steps[2].id).dispatch('click', { shiftKey: true });
  assert.deepEqual(pressed(drawn), ids(data, 1, 2));
  assert.equal(drawn.context.location.hash, runAddress(data, 1, 2));
  const said = drawn.byId['step-said'].textContent;
  assert.match(said, /^Steps 1 and 2 together\. /);
  assert.match(said, /two built states/);
  assert.match(said, /No verdict: each claim is judged in its own step/);
  for (const k of [1, 2]) assert.ok(said.includes('Step ' + k + ': ' + data.steps[k].label), k);
  // ⌘ or Ctrl does as Shift: a run from the step chosen before, never steps apart
  chipOf(drawn, data.steps[0].id).dispatch('click', {});
  chipOf(drawn, data.steps[2].id).dispatch('click', { metaKey: true });
  assert.deepEqual(pressed(drawn), ids(data, 0, 2));
  assert.match(drawn.byId['step-said'].textContent, /^Steps 0 to 2 together\. /);
  // the drawer holds the run's own row
  drawn.open(runAddress(data, 0, 2) + '&sd.item=' + encodeURIComponent(data.items[0].id));
  assert.ok(drawn.byId['item-body'].textContent.includes('Steps 0 to 2 together'));
  // steps apart, asked for by an address: refused, said why, the whole way shown
  drawn.open('sd.steps=' + data.steps[0].id + ',' + data.steps[2].id);
  assert.deepEqual(pressed(drawn), ['total'].concat(data.steps.map((s) => s.id)));
  assert.match(drawn.byId['step-said'].textContent, /^The address asks for steps 0 and 2\. Steps apart are not compared on a chain: each step was measured with every step before it applied/);
  // every step chosen is the whole way, its address none
  chipOf(drawn, data.steps[0].id).dispatch('click', {});
  chipOf(drawn, data.steps[3].id).dispatch('click', { shiftKey: true });
  assert.deepEqual(pressed(drawn), ['total'].concat(data.steps.map((s) => s.id)));
  assert.match(drawn.byId['step-said'].textContent, /^The whole way: /);
});

test('the list chooses one step, or with Shift a run; it offers nothing that would choose steps apart', () => {
  const data = example();
  const drawn = dom.page(data);
  assert.equal(drawn.byId['pick-panel'].hidden, false); // a short chain opens its list
  assert.deepEqual(chosenRows(drawn), []); // the whole way is no row's
  rowOf(drawn, 1).dispatch('click', {});
  assert.deepEqual(chosenRows(drawn), [1]);
  assert.deepEqual(pressed(drawn), [data.steps[1].id]);
  rowOf(drawn, 3).dispatch('click', { shiftKey: true });
  assert.deepEqual(chosenRows(drawn), [1, 2, 3]);
  rowOf(drawn, 0).dispatch('click', {});
  assert.deepEqual(chosenRows(drawn), [0]);
  // the example's kinds are one step each: no group has a heading, each row says its kind
  assert.equal(drawn.byId['pick-list'].querySelectorAll('button[data-group]').length, 0);
  assert.ok(drawn.byId['pick-list'].textContent.includes(data.steps[2].kind));
  assert.equal(tagged(drawn.byId['pick-list'], 'INPUT').length, 0);
  assert.equal(drawn.byId['pick-active'], undefined);
  drawn.byId['pick-all'].dispatch('click', {});
  assert.deepEqual(pressed(drawn), ['total'].concat(data.steps.map((s) => s.id)));
});

test('consecutive steps of one kind are one group, whose heading chooses their run', () => {
  const data = example();
  data.steps.slice(1).forEach((s) => { s.kind = 'fix'; });
  const drawn = dom.page(data);
  const group = drawn.byId['pick-list'].querySelectorAll('button[data-group]');
  assert.equal(group.length, 1);
  assert.equal(group[0].getAttribute('aria-pressed'), 'false');
  const count = () => drawn.byId['pick-list'].querySelectorAll('span[data-group-count]')[0].textContent;
  assert.equal(count(), '3 steps');
  rowOf(drawn, 2).dispatch('click', {});
  assert.equal(count(), '1 of 3 chosen');
  group[0].dispatch('click', {});
  assert.deepEqual(chosenRows(drawn), [1, 2, 3]);
  assert.equal(group[0].getAttribute('aria-pressed'), 'true');
  assert.match(drawn.byId['step-said'].textContent, /^Steps 1 to 3 together\. /);
});

test('the list finds steps by number, name or kind, and shows those where something moved', () => {
  const data = example();
  const drawn = dom.page(data);
  const shown = () => drawn.byId['pick-list'].querySelectorAll('button[data-row]').map((row) => +row.getAttribute('data-row'));
  drawn.byId['pick-find'].value = data.steps[2].label.slice(0, 6).toUpperCase();
  drawn.byId['pick-find'].dispatch('input', {});
  assert.ok(shown().includes(2) && shown().length < data.steps.length, String(shown()));
  assert.match(drawn.byId['pick-shown'].textContent, /^Showing \d of 4 steps\./);
  drawn.byId['pick-find'].value = 'nothing like it';
  drawn.byId['pick-find'].dispatch('input', {});
  assert.deepEqual(shown(), []);
  assert.match(drawn.byId['pick-list'].textContent, /No step matches "nothing like it"/);
  const still = example();
  for (const block of Object.values(still.counts.steps[still.steps[1].id])) for (const c of Object.keys(block.classes)) block.classes[c] = 0;
  const quiet = dom.page(still);
  quiet.byId['pick-moved'].checked = true;
  quiet.byId['pick-moved'].dispatch('change', {});
  // Rebuilt's one move (oats' water use) is within the noise of its two builds: nothing moved
  assert.deepEqual(quiet.byId['pick-list'].querySelectorAll('button[data-row]').map((row) => +row.getAttribute('data-row')), [0, 3]);
});

test('without every item no run is judged: said why, and one step and the whole way remain', () => {
  const data = local(); // 6 of 10 listed; its matrix is not read over file:
  const drawn = dom.page(data);
  assert.match(drawn.byId['pick-locked'].textContent, /judged from every product's results, and the matrix that holds them was not loaded/);
  assert.equal(drawn.byId['pick-locked'].hidden, false);
  chipOf(drawn, data.steps[1].id).dispatch('click', {});
  chipOf(drawn, data.steps[2].id).dispatch('click', { shiftKey: true });
  assert.deepEqual(pressed(drawn), [data.steps[1].id]); // nothing changed
  assert.match(drawn.byId['step-said'].textContent, /^A run of steps is judged from every product's results/);
  // an address that asks for a run while the matrix is loading falls back, and is read again once it is here
  const later = dom.page(local(), undefined, { attributes: { 'data-sd-matrix': 'matrix.js' } });
  later.open(runAddress(data, 1, 3));
  assert.match(later.byId['step-said'].textContent, /^The address asks for steps 1 to 3\. .*the matrix that holds them is loading\. The whole way is shown\./);
  later.context.SENTIER_DIAGNOSTICS_MATRIX = full();
  later.head.querySelector('script[src]').onload();
  assert.deepEqual(pressed(later), ids(data, 1, 3));
  assert.equal(later.byId['pick-locked'].hidden, true);
});

test('the page refuses a run whose steps its rule does not judge as the file does, and says where', () => {
  const data = local();
  const m = full();
  // one item's class in step 1 rewritten: the page's rule no longer gives the file's. An item
  // the file does not list: a listed one would be refused with the matrix, as not the file's
  const at = m.items.findIndex((row, k) => k >= 3 && !data.items.some((item) => item.id === row[0]));
  assert.ok(at >= 3, 'the local example has an item it does not list');
  const codes = m.classes[at].split('');
  codes[1] = codes[1] === '=' ? 'D' : '=';
  m.classes[at] = codes.join('');
  const drawn = dom.page(data, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: m } });
  drawn.open(runAddress(data, 1, 2));
  assert.match(drawn.byId['step-said'].textContent, new RegExp("This page's rule does not give the file's classes in step 1 \\(" + m.items[at][0] + ', '));
  assert.deepEqual(pressed(drawn), ['total'].concat(data.steps.map((s) => s.id)));
  // a run without that step is judged, and step 1 alone is still the file's
  drawn.open(runAddress(data, 2, 3));
  assert.deepEqual(pressed(drawn), ids(data, 2, 3));
  drawn.open('sd.step=' + encodeURIComponent(data.steps[1].id));
  assert.deepEqual(pressed(drawn), [data.steps[1].id]);
});

test('an address names a run; one with a step the file does not have falls back to the whole way, said', () => {
  const data = example();
  const drawn = dom.page(data);
  drawn.open(runAddress(data, 1, 3));
  assert.deepEqual(pressed(drawn), ids(data, 1, 3));
  assert.equal(runAddress(data, 1, 3), 'sd.steps=' + data.steps[1].id + ':' + data.steps[3].id);
  drawn.open('sd.steps=' + data.steps[0].id + ':nothing-of-the-kind');
  assert.deepEqual(pressed(drawn), ['total'].concat(data.steps.map((s) => s.id)));
  assert.match(drawn.byId['step-said'].textContent, /^The address names a step this file does not have \(nothing-of-the-kind\)\. The whole way is shown\./);
  // an id holding a comma or a colon is still one id
  // the step's id rewritten wherever the file names it: its counts, attribution, breakdowns
  const odd = JSON.parse(JSON.stringify(example()).split(JSON.stringify(data.steps[1].id)).join(JSON.stringify('fix, part: one')));
  assert.equal(odd.steps[1].id, 'fix, part: one');
  const shown = dom.page(odd);
  chipOf(shown, odd.steps[1].id).dispatch('click', {});
  chipOf(shown, odd.steps[2].id).dispatch('click', { shiftKey: true });
  const hash = shown.context.location.hash;
  shown.open('');
  shown.open(hash);
  assert.deepEqual(pressed(shown), ids(odd, 1, 2));
});

test('in a run, the steps where nothing moved and nothing was judged fold into one line', () => {
  const data = example();
  const drawn = dom.page(data);
  drawn.open(runAddress(data, 0, 2));
  // the example's steps move something: nothing folds, every step has its own line
  assert.equal(tagged(drawn.byId['step-said'], 'DETAILS').length, 0);
  for (const k of [0, 1, 2]) assert.ok(drawn.byId['step-said'].textContent.includes('Step ' + k + ': ' + data.steps[k].label), k);
  // the first two steps made quiet in the file's counts: a claim, nothing moved, no verdict
  const calm = example();
  for (const k of [0, 1]) {
    for (const block of Object.values(calm.counts.steps[calm.steps[k].id])) {
      for (const name of Object.keys(block.classes)) block.classes[name] = 0;
      for (const name of Object.keys(block.verdicts)) block.verdicts[name] = 0;
    }
  }
  const shown = dom.page(calm);
  shown.open(runAddress(calm, 0, 2));
  const folded = tagged(shown.byId['step-said'], 'DETAILS');
  assert.equal(folded.length, 1);
  assert.match(folded[0].textContent, /^Steps 0 and 1: nothing moved in any of them, as each claims\./);
  for (const k of [0, 1]) assert.ok(folded[0].textContent.includes('Step ' + k + ': ' + calm.steps[k].label), 'each is still there to open');
  assert.ok(!folded[0].textContent.includes('Step 2: '), 'the step that moved stays outside');
  assert.ok(shown.byId['step-said'].textContent.includes('Step 2: ' + calm.steps[2].label));
  // a quiet step without a claim folds too, and the line no longer says each one claims it
  const unclaimed = JSON.parse(JSON.stringify(calm));
  unclaimed.steps[1].claim = null;
  for (const block of Object.values(unclaimed.counts.steps[unclaimed.steps[1].id])) block.verdicts = null;
  const plain = dom.page(unclaimed);
  plain.open(runAddress(unclaimed, 0, 2));
  const line = tagged(plain.byId['step-said'], 'DETAILS');
  assert.equal(line.length, 1);
  assert.match(line[0].textContent, /^Steps 0 and 1: nothing moved in any of them\.Step/);
});

test('Shift and an arrow key grow the steps chosen, and shrink them back', () => {
  const data = example();
  const drawn = dom.page(data);
  chipOf(drawn, data.steps[1].id).dispatch('click', {});
  drawn.byId.comparison.dispatch('keydown', { key: 'ArrowRight', shiftKey: true });
  assert.deepEqual(pressed(drawn), data.steps.slice(1, 3).map((s) => s.id));
  drawn.byId.comparison.dispatch('keydown', { key: 'ArrowLeft', shiftKey: true });
  assert.deepEqual(pressed(drawn), [data.steps[1].id]);
});

test('the whole way and a run take the noise of their two ends only; a file made before says it has none', () => {
  // the example measured noise in With fix 1 and Rebuilt, two builds of one commit: the whole
  // way runs from the published results (exact) to Mapping 2 (not measured), and takes none
  const data = example();
  const drawn = dom.page(data);
  assert.match(drawn.byId['step-said'].textContent, /Noise the sum of its two ends' \(Published exact, With mapping 2 not measured\): not measured\./);
  assert.match(drawn.byId['rule-body'].textContent, /With fix 1: measured between fix-1 and rebuilt/);
  assert.match(drawn.byId['rule-body'].textContent, /Published: exact: the published results have no builds/);
  // one step: Rebuilt is two builds, each measured, so its noise is their sum
  drawn.open('sd.step=' + data.steps[2].id);
  assert.match(drawn.byId['step-said'].textContent, /Noise the sum of its two ends' \(With fix 1 measured, Rebuilt measured\); large: up to 4\.878 %\./);
  // a run from Recomputed (not measured) to Rebuilt: measured at one end
  drawn.open(runAddress(data, 1, 2));
  assert.match(drawn.byId['step-said'].textContent, /Noise the sum of its two ends' \(Recomputed not measured, Rebuilt measured\), measured at 1 of 2 ends; large: up to 2\.439 %\./);
  // a file made before noise belonged to a state: its whole way and its runs have none
  const older = example();
  delete older.rule.total_noise;
  older.states.forEach((st) => delete st.noise);
  const old = dom.page(older);
  assert.match(old.byId['step-said'].textContent, /Noise none: this file was made before noise belonged to a state\./);
  // one that took the whole way's noise from its steps is refused
  const guessed = example();
  guessed.states.forEach((st) => delete st.noise);
  assert.equal(dom.page(guessed).byId.content.hidden, true);
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

// ------------------------------------------------------------------ a page inside a host (issues 25 to 33)

test('the drawer is a dialog named by its item, opened as a popover on a wide window (issue 25)', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'sentier_diagnostics', 'page', 'body.html'), 'utf8');
  assert.match(html, /<dialog class="sd-drawer" data-sd="item" popover="manual" hidden>[\s\S]*<\/dialog>/);
  const drawn = dom.page(example());
  const drawer = drawn.byId.item;
  let up = false;
  const calls = [];
  drawer.showPopover = () => { calls.push('popover'); up = true; };
  drawer.hidePopover = () => { calls.push('hide'); up = false; };
  drawer.showModal = () => { calls.push('modal'); drawer.open = true; };
  drawer.matches = (selector) => selector === ':popover-open' && up;
  drawn.context.matchMedia = () => ({ matches: false }); // wide
  drawn.open('sd.item=p01');
  assert.deepEqual(calls, ['popover']);
  assert.equal(drawer.hidden, false);
  assert.equal(drawer.getAttribute('aria-label'), example().items.find((i) => i.id === 'p01').name);
  assert.equal(drawn.byId['item-title'].focusOptions.preventScroll, true);
  drawn.open('sd.item=p03'); // another item while it is open: still one popover, named anew
  assert.deepEqual(calls, ['popover']);
  assert.equal(drawer.getAttribute('aria-label'), example().items.find((i) => i.id === 'p03').name);
  drawn.root.dispatch('keydown', { key: 'Escape' });
  assert.deepEqual(calls, ['popover', 'hide']);
  assert.equal(drawer.hidden, true);
});

test('where the drawer fills the window, or no popover is known, it opens modal; where neither is known, as a fixed element (issue 25)', () => {
  const setUp = (narrow, kinds) => {
    const drawn = dom.page(example());
    const drawer = drawn.byId.item;
    const calls = [];
    if (kinds.includes('popover')) {
      drawer.showPopover = () => calls.push('popover');
      drawer.hidePopover = () => calls.push('hide');
    }
    if (kinds.includes('dialog')) {
      drawer.showModal = () => { calls.push('modal'); drawer.open = true; };
      drawer.close = () => { calls.push('close'); drawer.open = false; };
    }
    // a browser without popovers knows no ":popover-open" and throws on it
    drawer.matches = (selector) => { if (!kinds.includes('popover')) throw new SyntaxError(selector); return false; };
    drawn.context.matchMedia = (query) => ({ matches: narrow && /max-width/.test(query) });
    return { drawn, drawer, calls };
  };
  const phone = setUp(true, ['popover', 'dialog']);
  phone.drawn.open('sd.item=p01');
  assert.deepEqual(phone.calls, ['modal'], 'a phone: modal, the grid under it inert');
  phone.drawn.root.dispatch('keydown', { key: 'Escape' });
  assert.deepEqual(phone.calls, ['modal', 'close']);
  assert.equal(phone.drawer.hidden, true);
  const old = setUp(false, ['dialog']);
  old.drawn.open('sd.item=p01');
  assert.deepEqual(old.calls, ['modal'], 'no popovers: modal, wide or not');
  // a modal drawer the browser closed itself (a back gesture) is closed by the page too
  old.drawer.open = false;
  old.drawer.dispatch('close', {});
  assert.equal(old.drawer.hidden, true);
  assert.equal(old.drawn.context.location.hash, '');
  const none = setUp(false, []);
  assert.doesNotThrow(() => none.drawn.open('sd.item=p01'));
  assert.equal(none.drawer.hidden, false, 'the fixed element stands');
  const failing = setUp(false, ['popover']);
  failing.drawer.showPopover = () => { throw new Error('not supported'); };
  failing.drawn.open('sd.item=p01');
  assert.equal(failing.drawer.hidden, false, 'the fixed element stands where showing it fails');
  // the fixed element and the dialog look alike, and the fixed one stands above a host's header
  const css = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'sentier_diagnostics', 'page', 'diagnostics.css'), 'utf8');
  const drawerRule = css.slice(css.indexOf(' .sd-drawer {'), css.indexOf('}', css.indexOf(' .sd-drawer {')));
  for (const said of ['position: fixed', 'z-index: 2147483000', 'max-height: none', 'margin: 0', 'border: 0']) assert.ok(drawerRule.includes(said), said);
  // a dialog and a popover take the browser's own place and size (inset 0, margin auto, fit
  // to their content), which centres them: the drawer sets its own, at the right edge and
  // the window's height (review of #34)
  for (const said of ['inset: 0 0 0 auto', 'width: var(--sd-drawer)', 'height: auto', 'padding: 0']) assert.ok(drawerRule.includes(said), said);
  // a drawer that leaves the grid in use does not darken it: only the modal one
  assert.match(css, /\.sd-drawer:modal::backdrop \{/);
  assert.doesNotMatch(css, /\.sd-drawer::backdrop/);
});

test('a "%" in the address leaves the page drawn, the host\'s part kept and the page\'s own one set aside (issue 26)', () => {
  const drawn = dom.page(example(), undefined, { hash: 'save-50%' });
  assert.equal(drawn.byId.content.hidden, false);
  assert.doesNotThrow(() => drawn.changed());
  assert.equal(drawn.byId.content.hidden, false);
  chips(drawn).find((c) => c.getAttribute('data-comp') !== 'total').dispatch('click', {});
  assert.match(drawn.context.location.hash, /^save-50%&sd\.step=/);
  // the page's own part with a "%" that is no escape: drawn, no item opened, nothing thrown
  for (const [options, hash] of [[{}, 'sd.item=50%'], [{ standalone: true }, 'item=50%'], [{}, 'sd.step=50%']]) {
    const own = dom.page(example(), undefined, { ...options, hash });
    assert.equal(own.byId.content.hidden, false, hash);
    assert.equal(own.byId.item.hidden, true, hash);
    assert.doesNotThrow(() => own.changed(), hash);
  }
});

test('a page in a host keeps to its own key: it reads no part of the host\'s, and two pages keep apart (issue 27)', () => {
  // the host's own "item=" is not the page's
  const hosted = dom.page(example(), undefined, { hash: 'item=p01' });
  assert.equal(hosted.byId.item.hidden, true, 'a host\'s own part opens nothing');
  hosted.open('item=p01&sd.item=p03');
  assert.equal(hosted.byId['item-title'].textContent, example().items.find((i) => i.id === 'p03').name);
  hosted.root.dispatch('keydown', { key: 'Escape' });
  assert.equal(hosted.context.location.hash, 'item=p01', 'the host\'s part is kept');
  // a page of its own has no host: its parts carry no key
  const own = dom.page(example(), undefined, { standalone: true, hash: 'item=p01' });
  assert.equal(own.byId.item.hidden, false);
  // a page named by its host takes that name
  const named = dom.page(example(), undefined, { attributes: { 'data-sd-key': 'left' }, hash: 'left.item=p01' });
  assert.equal(named.byId.item.hidden, false);
});

test('two pages on one host each take their own key, by the order they were mounted in (issue 27)', () => {
  const drawn = dom.page(example()); // mounted first: "sd."
  const second = dom.body({ data: example() });
  second.ownerDocument = drawn.document;
  // the second is placed before the first, as a host that draws it later may do
  drawn.document.querySelectorAll = () => [second, drawn.root];
  drawn.context.SentierDiagnostics.mount(second);
  const drawerOf = (root) => root.querySelector('[data-sd="item"]');
  const titleOf = (root) => root.querySelector('[data-sd="item-title"]').textContent;
  drawn.open('sd2.item=p01');
  assert.equal(drawerOf(second).hidden, false, 'the second page opens its item');
  assert.equal(drawerOf(drawn.root).hidden, true, 'the first page does not open the same id');
  gridRows(drawn).find((tr) => tr.getAttribute('data-item') === 'p03').childNodes[0].dispatch('click', {});
  assert.equal(drawn.context.location.hash, 'sd2.item=p01&sd.item=p03', 'the other page\'s part is kept');
  drawn.changed();
  assert.equal(titleOf(drawn.root), example().items.find((i) => i.id === 'p03').name);
  assert.equal(titleOf(second), example().items.find((i) => i.id === 'p01').name);
  drawn.root.dispatch('keydown', { key: 'Escape' });
  assert.equal(drawn.context.location.hash, 'sd2.item=p01');
  drawn.changed();
  assert.equal(drawerOf(second).hidden, false);
});

test('choosing the whole way adds a history entry with the case query and host state', () => {
  const drawn = dom.page(example(), undefined, { search: '?case=F1', hash: 'sd.step=fix-1', historyState: { caseId: 'F1' } });
  const pushed = [];
  drawn.context.history.pushState = (state, title, url) => {
    pushed.push({ state, url });
    drawn.context.location.hash = '';
  };
  chipOf(drawn, 'total').dispatch('click', {});
  chipOf(drawn, 'total').dispatch('click', {});
  assert.deepEqual(pushed, [{ state: { caseId: 'F1' }, url: '/index.html?case=F1' }]);
  assert.equal(drawn.context.history.replaced.length, 0);
});

test('closing the drawer keeps the host\'s history state (issue 27)', () => {
  const drawn = dom.page(example(), undefined, { historyState: { host: 'kept' } });
  drawn.open('sd.item=p01');
  drawn.root.dispatch('keydown', { key: 'Escape' });
  assert.equal(drawn.context.history.replaced.length, 1);
  assert.deepEqual(drawn.context.history.replaced[0].state, { host: 'kept' });
});

test('a page takes the matrix of the script it names, and no other page\'s (issue 27)', () => {
  const other = full(); other.of.steps = other.of.steps.slice().reverse();
  const listed = local().items[0].id;
  const at = full().items.findIndex((row) => row[0] === listed);
  const stale = full(); stale.values[at] = stale.values[at].map((v) => (typeof v === 'number' ? v * 3 : v));
  const loading = (entries) => {
    const drawn = dom.page(local(), undefined, { attributes: { 'data-sd-matrix': 'matrix.js' }, globals: { SENTIER_DIAGNOSTICS_MATRIX: other, SENTIER_DIAGNOSTICS_MATRICES: [{ src: 'elsewhere/matrix.js', matrix: other }] } });
    const script = drawn.head.querySelector('script[src]');
    assert.ok(script, 'its own matrix is requested');
    assert.match(drawn.byId['matrix-said'].textContent, /^Loading/);
    drawn.context.SENTIER_DIAGNOSTICS_MATRICES.push(...entries); // as the script page.write puts beside it does
    script.onload();
    return drawn;
  };
  assert.equal(gridRows(loading([{ src: 'matrix.js', matrix: full() }])).length, 10, 'its own is taken');
  // its own, stale: refused for what is wrong with it, not as another file's
  const refused = loading([{ src: 'matrix.js', matrix: stale }]);
  assert.match(refused.byId['matrix-said'].textContent, /its results or classes differ/);
  assert.doesNotMatch(refused.byId['matrix-said'].textContent, /another file/);
  assert.match(loading([]).byId['matrix-said'].textContent, /matrix\.js holds no matrix/);
  // a script the host put in its page itself: taken without loading it again
  const there = dom.page(local(), undefined, { attributes: { 'data-sd-matrix': 'matrix.js' }, globals: { SENTIER_DIAGNOSTICS_MATRICES: [{ src: 'matrix.js', matrix: full() }] } });
  assert.equal(there.head.querySelector('script[src]'), null);
  assert.equal(gridRows(there).length, 10);
  // a page that names no matrix is silent about another page's, and says why the host's single global is not its
  const bare = local(); bare.matrix = null;
  const silent = dom.page(bare, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRICES: [{ src: 'other/matrix.js', matrix: other }] } });
  assert.match(silent.byId['matrix-said'].textContent, /^This file lists \d+ of its \d+ products and names no matrix of every product/);
  assert.equal(gridRows(silent).length, bare.items.length);
  const said = dom.page(bare, undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: other } });
  assert.match(said.byId['matrix-said'].textContent, /not loaded: it is the matrix of another file/);
  // the host's global, where it is this file's, is taken before anything is loaded
  const global = dom.page(local(), undefined, { globals: { SENTIER_DIAGNOSTICS_MATRIX: full() } });
  assert.equal(global.head.querySelector('script[src]'), null);
  assert.equal(gridRows(global).length, 10);
});

test('a pair that moved never prints the "1.00" of a pair that agrees (issue 28)', () => {
  assert.equal(page.ratioView(1, 1.0002, 'differs', 'up', 'up, factor 1-1.1').text, '1 + 2e−4');
  assert.equal(page.ratioView(1, 1.004, 'differs', 'up', 'up, factor 1-1.1').text, '1.004');
  assert.equal(page.ratioView(1, 0.9996, 'differs', 'down', 'down, factor 1-1.1').text, '1 − 4e−4');
  assert.equal(page.ratioView(-2, -2.0004, 'differs', 'down', 'down, factor 1-1.1').text, '1 + 2e−4');
  assert.equal(page.ratioView(1, 1.0002, 'agrees', null, null).text, '1.00');
  assert.equal(page.ratioView(1, 1.02, 'differs', 'up', 'up, factor 1-1.1').text, '1.02', 'three digits wherever they part it from 1');
});

test('indicators called "name" and "worst" are columns like any other (issue 29)', () => {
  const data = JSON.parse(JSON.stringify(example()).split('"x:water"').join('"worst"').split('"x:tox"').join('"name"'));
  const drawn = dom.page(data);
  const heads = () => drawn.byId['grid-table'].querySelectorAll('th[scope="col"]');
  const marked = () => heads().filter((th) => th.getAttribute('aria-sort')).map((th) => th.getAttribute('title') || th.textContent);
  assert.deepEqual(marked(), [], 'the grid opens furthest apart first, with no heading marked');
  const column = (id) => heads().find((th) => (th.getAttribute('title') || '').indexOf(data.indicators.find((i) => i.id === id).name) === 0);
  column('name').querySelector('button[type="button"]').dispatch('click', {});
  assert.equal(marked().length, 1);
  assert.equal(column('name').getAttribute('aria-sort'), 'descending');
  assert.equal(heads()[0].getAttribute('aria-sort'), null, 'the item column is not sorted');
  column('worst').querySelector('button[type="button"]').dispatch('click', {});
  assert.equal(column('worst').getAttribute('aria-sort'), 'descending');
  assert.doesNotMatch(drawn.byId['grid-region'].getAttribute('aria-label'), /furthest apart first/);
  column('worst').querySelector('button[type="button"]').dispatch('click', {});
  assert.deepEqual(marked(), []);
  assert.match(drawn.byId['grid-region'].getAttribute('aria-label'), /, the furthest apart first$/);
});

test('host styles stop at the page: every rule weighs two ids more, and resets buttons and lists (issue 30)', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'sentier_diagnostics', 'page', 'diagnostics.css'), 'utf8');
  const ROOT = '.sentier-diagnostics:not(#sd-none):not(#sd-none)';
  const rules = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const selectors = [...rules.matchAll(/([^{}]+)\{/g)].map((m) => m[1].trim()).filter((s) => !s.startsWith('@'));
  assert.ok(selectors.length > 100);
  for (const one of selectors.flatMap((s) => s.split(','))) assert.ok(one.trim().startsWith(ROOT), one.trim());
  const rule = (selector) => { const at = rules.indexOf(selector + ' {'); assert.ok(at >= 0, selector); return rules.slice(at, rules.indexOf('}', at)); };
  const button = rule(ROOT + ' button');
  for (const said of ['min-height: 0', 'width: auto', 'border-radius: 0', 'text-transform: none', 'letter-spacing: normal', 'font: inherit']) assert.ok(button.includes(said), said);
  assert.ok(rule(ROOT + ' li').includes('list-style: inherit'));
  assert.ok(rule(ROOT + ' li::marker').includes('content: normal'));
  assert.ok(rule(ROOT + ' li::before, ' + ROOT + ' li::after').includes('content: none'));
  const root = rule(ROOT);
  assert.ok(root.includes('color: var(--sd-ink)') && root.includes('background: var(--sd-surface)'));
  // the reset comes before the page's own controls, which weigh more and set their look
  assert.ok(rules.indexOf(ROOT + ' button {') < rules.indexOf(ROOT + ' .sd-button {'));
  const dark = rule(ROOT + '[data-sd-scheme="dark"]');
  assert.ok(dark.includes('--sd-surface: var(--surface, #15191d)') && dark.includes('--sd-ink: var(--ink, #e6eaee)'));
});

test('the page\'s colours follow the host\'s ink: a light ink never stands on the page\'s white (issue 30)', () => {
  const lum = (c) => page.luminance(c);
  assert.equal(page.schemeIsDark('#eee', '', lum), true, 'a light ink and no ground: dark');
  assert.equal(page.schemeIsDark(' #eeeeee ', '#ffffff', lum), true, 'the ink decides');
  assert.equal(page.schemeIsDark('', '#111', lum), true, 'a dark ground and no ink: dark');
  assert.equal(page.schemeIsDark('rgb(29, 35, 42)', '', lum), false);
  assert.equal(page.schemeIsDark('', '', lum), false, 'no tokens: the light colours');
  assert.equal(page.schemeIsDark('not a colour', '', lum), false);
  assert.ok(Math.abs(page.luminance('#fff') - 1) < 1e-12 && page.luminance('#000') === 0);
  assert.ok(Math.abs(page.luminance('#777') - page.luminance('rgb(119, 119, 119)')) < 1e-12);
  const styled = (vars) => ({ getComputedStyle: () => ({ getPropertyValue: (name) => vars[name] || '' }) });
  assert.equal(dom.page(example(), undefined, { globals: styled({ '--ink': '#eee' }) }).root.getAttribute('data-sd-scheme'), 'dark');
  assert.equal(dom.page(example(), undefined, { globals: styled({ '--ink': '#1d232a', '--surface': '#fff' }) }).root.getAttribute('data-sd-scheme'), null);
  assert.equal(dom.page(example(), undefined, { globals: styled({}) }).root.getAttribute('data-sd-scheme'), null);
  // read again when the reader's scheme changes, as a host's tokens may follow it
  const vars = { '--ink': '#1d232a' };
  const listeners = [];
  const following = dom.page(example(), undefined, { globals: { ...styled(vars), matchMedia: () => ({ matches: false, addEventListener: (type, f) => listeners.push([type, f]) }) } });
  assert.equal(following.root.getAttribute('data-sd-scheme'), null);
  vars['--ink'] = '#e6eaee';
  listeners.filter(([type]) => type === 'change').forEach(([, f]) => f({ matches: true }));
  assert.equal(following.root.getAttribute('data-sd-scheme'), 'dark');
  vars['--ink'] = '#1d232a';
  listeners.filter(([type]) => type === 'change').forEach(([, f]) => f({ matches: false }));
  assert.equal(following.root.getAttribute('data-sd-scheme'), null);
});

// a canvas as a browser's: it takes a colour it can read, and keeps its own for any other.
// `shown` stands for what a browser that hides what a canvas holds gives back instead.
const canvasOf = (shown) => {
  const known = { white: [255, 255, 255], 'color(srgb 0.949 0.949 0.949)': [242, 242, 242], 'color(srgb 0.1 0.1 0.1)': [26, 26, 26], 'color(srgb 1 1 1 / 0.5)': [255, 255, 255, 128], '#010203': [1, 2, 3], '#fdfeff': [253, 254, 255] };
  return {
    createElement: () => {
      let fill = '#010203';
      let pixel = [0, 0, 0, 0];
      const context = {
        get fillStyle() { return fill; },
        set fillStyle(text) { if (known[text]) fill = text; },
        clearRect() { pixel = [0, 0, 0, 0]; },
        // a colour drawn over what is there: a translucent one is mixed with it
        fillRect() {
          const [r, g, b, a = 255] = known[fill];
          const over = a / 255;
          pixel = pixel[3] ? [r, g, b].map((v, i) => Math.round(v * over + pixel[i] * (1 - over))).concat(255) : [r, g, b, a];
        },
        getImageData: () => ({ data: shown ? [...shown] : [...pixel] }),
      };
      return { getContext: () => context };
    },
  };
};

test('a colour in oklch() or oklab() is read as it is written, without a canvas (review of 3a80142)', () => {
  // Tailwind 4 writes every colour in oklch, and a browser gives it back so
  const near = (a, b, within) => assert.ok(Math.abs(a - b) < within, a + ' and ' + b);
  near(page.luminance('oklch(0.95 0 0)'), 0.857375, 1e-12); // grey: the cube of L
  near(page.luminance('oklab(0.95 0 0)'), 0.857375, 1e-12);
  near(page.luminance('OKLCH(95% 0 0)'), 0.857375, 1e-12);
  near(page.luminance('OKLCH(0.95 0.3 330)'), 0.4887679976337716, 1e-12);
  // Tailwind's gray-900 and slate-50 against their sRGB fallbacks, to the rounding of a hex
  near(page.luminance('oklch(21% 0.034 264.665)'), page.luminance('#101828'), 1e-6);
  near(page.luminance('oklch(98.4% 0.003 247.858)'), page.luminance('#f8fafc'), 1e-3);
  // beyond sRGB: clipped as a canvas draws it (unclipped, it would read 0.757)
  near(page.luminance('oklch(0.95 0.3 330)'), 0.4887679976337716, 1e-12);
  near(page.luminance('oklch(0.95 75% 330deg)'), 0.4887679976337716, 1e-12); // C as a percentage of 0.4
  near(page.luminance('oklch(0.95 0.3 0.9166666666666666turn)'), 0.4887679976337716, 1e-12);
  near(page.luminance('oklch(0.95 0.3 5.759586531581287rad)'), 0.4887679976337716, 1e-12);
  near(page.luminance('oklab(0.95 75% -10%)'), page.luminance('oklab(0.95 0.3 -0.04)'), 1e-15);
  assert.equal(page.luminance('oklch(0.5 0.1 200 / 0.5)'), page.luminance('oklch(0.5 0.1 200)')); // alpha aside, as rgb() leaves it
  assert.equal(page.luminance('oklch(none 0 0)'), 0);
  for (const wrong of ['oklch(0.5deg 0.1 200)', 'oklch(0.5 0.1 200%)', 'oklab(0.5 0.1)', 'oklch(0.5 0.1deg 200)'])
    assert.equal(page.luminance(wrong), null, wrong);
  assert.equal(page.schemeIsDark('oklch(0.967 0.003 264.542)', '', page.luminance), true, 'a light ink in oklch makes a dark page');
  assert.equal(page.schemeIsDark('oklch(0.21 0.034 264.665)', '', page.luminance), false);
});

test('a browser that hides what a canvas holds says nothing of a colour, and never a wrong one (review of 3a80142)', () => {
  // blank white (as Tor Browser gives), all zeros, and a colour altered by one, in red or in blue
  for (const shown of [[255, 255, 255, 255], [0, 0, 0, 0], [2, 2, 3, 255], [1, 2, 4, 255]]) {
    const hidden = canvasOf(shown);
    assert.equal(page.luminance('color(srgb 0.1 0.1 0.1)', hidden), null, String(shown));
    assert.equal(page.luminance('white', hidden), null, String(shown));
    assert.equal(page.schemeIsDark('color(srgb 0.1 0.1 0.1)', '', (c) => page.luminance(c, hidden)), false, 'a dark ink is not read as a light one');
    // what is read without a canvas is still read
    assert.ok(Math.abs(page.luminance('oklch(0.95 0 0)', hidden) - 0.857375) < 1e-12);
    assert.ok(Math.abs(page.luminance('#fff', hidden) - 1) < 1e-12);
  }
  assert.ok(Math.abs(page.luminance('color(srgb 0.1 0.1 0.1)', canvasOf()) - page.luminance('#1a1a1a')) < 1e-12, 'a canvas that shows what it holds is read');
  // the colour is drawn on a clear pixel, not over the one that tried the canvas: a
  // translucent colour reads as its own, as on a canvas tried by nothing
  assert.ok(Math.abs(page.luminance('color(srgb 1 1 1 / 0.5)', canvasOf()) - 1) < 1e-12);
});

test('a host colour the page cannot read is unknown, never black (review of issue 30)', () => {
  // a canvas as a browser's: it takes a colour it can read, and keeps its own for any other
  const canvasDoc = canvasOf();
  assert.equal(page.luminance('light-dark(#fff, #111)', canvasDoc), null);
  assert.equal(page.luminance('0 0% 100%', canvasDoc), null);
  assert.ok(Math.abs(page.luminance('white', canvasDoc) - 1) < 1e-12);
  assert.ok(Math.abs(page.luminance('color(srgb 0.949 0.949 0.949)', canvasDoc) - page.luminance('#f2f2f2')) < 1e-12);
  const lum = (c) => page.luminance(c, canvasDoc);
  assert.equal(page.schemeIsDark('', 'light-dark(#fff, #111)', lum), false, 'an unreadable ground is not a dark one');
  assert.equal(page.schemeIsDark('0 0% 100%', '', lum), false, 'an unreadable ink is not a dark one');
  assert.equal(page.schemeIsDark('0 0% 100%', '#111', lum), true, 'where the ink says nothing, the ground decides');
  assert.equal(page.schemeIsDark('white', '#111', lum), true);
  assert.equal(page.schemeIsDark(null, '', lum), false);
});

// a browser's styles, as far as the page reads them: the tokens on the page, and the colour of
// a probe set to `var(--token)`, which the browser resolves (light-dark() to one of its two)
// or, for a token that is no colour, leaves the colour of the probe's parent
const RESOLVED = { 'light-dark(#fff, #111)': 'rgb(255, 255, 255)', 'light-dark(#eee, #1d232a)': 'rgb(238, 238, 238)', 'light-dark(#1d232a, #eee)': 'rgb(29, 35, 42)', '#eee': 'rgb(238, 238, 238)', '#1d232a': 'rgb(29, 35, 42)' };
const browserStyles = (vars) => ({
  getComputedStyle: (node) => {
    const color = node.style.getPropertyValue('color');
    if (color.startsWith('var(')) return { color: RESOLVED[vars[color.slice(4, -1)]] || node.parentNode.style.getPropertyValue('color') };
    return { getPropertyValue: (name) => vars[name] || '', color: '' };
  },
});

test('the page reads the host\'s tokens as the browser resolves them, and follows a theme switched by a class (review of issue 30)', () => {
  const scheme = (vars) => dom.page(example(), undefined, { globals: browserStyles(vars) }).root.getAttribute('data-sd-scheme');
  assert.equal(scheme({ '--surface': 'light-dark(#fff, #111)' }), null, 'a light host keeps the light page');
  assert.equal(scheme({ '--surface': '0 0% 100%' }), null, 'a bare triplet is no colour, and not black');
  assert.equal(scheme({ '--ink': '0 0% 100%' }), null);
  assert.equal(scheme({ '--ink': 'light-dark(#1d232a, #eee)' }), null);
  assert.equal(scheme({ '--ink': '#eee' }), 'dark');
  assert.equal(scheme({ '--ink': 'light-dark(#eee, #1d232a)' }), 'dark', 'only the browser can say what light-dark() is');
  // the probe leaves nothing behind
  const probed = dom.page(example(), undefined, { globals: browserStyles({ '--ink': '#eee' }) });
  const plain = dom.page(example(), undefined, { globals: {} }); // the data as a global, as above: no script element
  assert.equal(probed.root.childNodes.length, plain.root.childNodes.length);
  assert.ok(probed.root.childNodes.every((n) => !n.style.getPropertyValue('color')));

  // a host that switches its theme by a class of an element around the page, after it drew it
  const observers = [];
  class Observer {
    constructor(react) { this.react = react; this.watched = []; observers.push(this); }
    observe(node, options) { this.watched.push([node, options]); }
    disconnect() { this.watched = []; }
  }
  const vars = { '--ink': '#1d232a' };
  const first = dom.page(example(), undefined, { globals: { ...browserStyles(vars), MutationObserver: Observer } });
  const around = new dom.FakeNode('main');
  around.nodeType = 1;
  const themed = dom.body({ data: example() });
  themed.ownerDocument = first.document;
  around.appendChild(themed);
  first.context.SentierDiagnostics.mount(themed);
  const watch = observers[observers.length - 1];
  assert.ok(watch.watched.some(([node, options]) => node === first.document && options.subtree && options.attributes && options.childList),
    'the whole document is watched, so a class anywhere around the page is seen');
  assert.equal(themed.getAttribute('data-sd-scheme'), null);
  vars['--ink'] = '#eee';
  watch.react([]);
  assert.equal(themed.getAttribute('data-sd-scheme'), 'dark');
  vars['--ink'] = '#1d232a';
  watch.react([]);
  assert.equal(themed.getAttribute('data-sd-scheme'), null);
  // a page out of the document reads nothing, and follows again once it is put back
  themed.isConnected = false;
  vars['--ink'] = '#eee';
  watch.react([]);
  assert.equal(themed.getAttribute('data-sd-scheme'), null);
  themed.isConnected = true;
  watch.react([]);
  assert.equal(themed.getAttribute('data-sd-scheme'), 'dark');
  // a page in a shadow root: that root is watched too, as the document does not see into
  // it, and loads are heard there, as a load does not leave it
  const loadsIn = (top) => { top.loads = []; top.addEventListener = (type, react, capture) => { if (type === 'load' && capture) top.loads.push(react); }; return top; };
  const shadow = loadsIn({ host: around, nodeType: 11 });
  const shaded = dom.body({ data: example() });
  shaded.ownerDocument = first.document;
  shaded.getRootNode = () => shadow;
  around.getRootNode = () => first.document;
  first.context.SentierDiagnostics.mount(shaded);
  const shadedWatch = observers[observers.length - 1];
  const inShadow = shadedWatch.watched.map(([node]) => node);
  assert.ok(inShadow.includes(first.document) && inShadow.includes(shadow));
  assert.equal(shadow.loads.length, 1);
  vars['--ink'] = '#eee';
  shadow.loads[0]({ type: 'load' }); // a sheet swapped inside the shadow root finished loading
  assert.equal(shaded.getAttribute('data-sd-scheme'), 'dark');
  // moved into another shadow root whose colours are the same: that one is watched from then on
  const elsewhere = new dom.FakeNode('section');
  elsewhere.nodeType = 1;
  elsewhere.getRootNode = () => first.document;
  const moved = loadsIn({ host: elsewhere, nodeType: 11 });
  shaded.getRootNode = () => moved;
  shadedWatch.react([{ type: 'childList' }]);
  assert.ok(shadedWatch.watched.some(([node]) => node === moved));
  assert.equal(moved.loads.length, 1);
});

// A host page in a browser's styles: the page's tokens and the probes set to them, as
// browserStyles gives them, with a ground of alpha below 1 resolved as a browser writes it; the
// background of each element around the page (main, body, html); and the root element's
// colour scheme. Every value here is made up.
const SEEN = { transparent: 'rgba(0, 0, 0, 0)', 'rgba(0,0,0,.04)': 'rgba(0, 0, 0, 0.04)', 'rgb(255 255 255 / .05)': 'rgba(255, 255, 255, 0.05)', '#111': 'rgb(17, 17, 17)', '#fff': 'rgb(255, 255, 255)' };
const inHost = (vars, grounds, options = {}) => {
  const reader = { matches: !!options.readerDark, heard: [], addEventListener(type, react) { if (type === 'change') this.heard.push(react); } };
  const scheme = { value: options.scheme || 'normal', meta: options.meta || null };
  const observers = [];
  class Observer {
    constructor(react) { this.react = react; observers.push(this); }
    observe() {}
    disconnect() {}
  }
  let reads = 0;
  const read = new Set();
  const styles = {
    getComputedStyle: (node) => {
      // as a browser: an element or a TypeError; and a walk that does not end is ended here
      if (!(node instanceof dom.FakeNode)) throw new TypeError('parameter 1 is not of type \'Element\'');
      if (++reads > 50000) throw new Error('the walk around the page did not end');
      read.add(node);
      const color = node.style ? node.style.getPropertyValue('color') : '';
      if (color.startsWith('var(')) {
        let said = vars[color.slice(4, -1)];
        const both = /^light-dark\(([^,]+), ([^)]+)\)$/.exec(said || ''); // as the reader's scheme resolves it
        if (both) said = both[reader.matches ? 2 : 1];
        return { color: SEEN[said] || RESOLVED[said] || node.parentNode.style.getPropertyValue('color') };
      }
      return { getPropertyValue: (name) => (name === 'background-color' ? node.bg || '' : name === 'color-scheme' ? (node.isRoot ? scheme.value : '') : vars[name] || '') };
    },
  };
  // `manual`: the first page waits, so that `before` changes the document before any page mounts
  const first = dom.page(example(), undefined, {
    attributes: options.manual ? { 'data-sentier-diagnostics': 'manual' } : {},
    globals: { ...styles, matchMedia: () => reader, MutationObserver: Observer, ...(options.globals || {}) },
  });
  const html = new dom.FakeNode('html'), body = new dom.FakeNode('body'), main = new dom.FakeNode('main');
  html.isRoot = true;
  [html.bg, body.bg, main.bg] = [grounds.html, grounds.body, grounds.main];
  html.appendChild(body);
  body.appendChild(main);
  first.document.nodeType = 9;
  html.parentNode = first.document;
  first.document.documentElement = html;
  first.document.querySelector = (selector) => (selector === 'meta[name="color-scheme"]' && scheme.meta !== null
    ? { getAttribute: () => scheme.meta } : null);
  const themed = dom.body({ data: example() });
  themed.ownerDocument = first.document;
  main.appendChild(themed);
  if (options.before) options.before({ document: first.document, html, body, main, themed });
  first.context.SentierDiagnostics.mount(themed);
  const look = () => observers[observers.length - 1].react([]);
  return {
    themed, html, body, main, reader, scheme, vars, look,
    dark: () => themed.getAttribute('data-sd-scheme') === 'dark',
    ended: () => reads <= 50000, // every walk ended (a page that threw is refused, and light)
    wasRead: (node) => read.has(node),
    // an event the document hears on its way down (capture): a transition or animation ending
    fire: (type) => (first.documentListeners[type] || []).filter(([, capture]) => capture).forEach(([react]) => react({ type })),
  };
};

test('a ground with alpha is read as it is seen, through what is behind the page (issue 45)', () => {
  // a colour's alpha, as CSS and the browser write it
  assert.equal(page.colourOf('rgba(0, 0, 0, 0.04)').alpha, 0.04);
  assert.equal(page.colourOf('rgb(255 255 255 / 5%)').alpha, 0.05);
  assert.equal(page.colourOf('#ffffff80').alpha, 128 / 255);
  assert.equal(page.colourOf('#fff8').alpha, 136 / 255);
  assert.equal(page.colourOf('oklch(0.5 0.1 200 / 0.5)').alpha, 0.5);
  assert.equal(page.colourOf('oklch(0.5 0.1 200 / none)').alpha, 0);
  assert.equal(page.colourOf('rgb(0 0 0 / none)').alpha, 0);
  assert.equal(page.colourOf('rgb(0 0 0 / 0.5) 1px'), null, 'a colour and something after it is not a colour');
  assert.equal(page.colourOf('rgb(29, 35, 42)').alpha, 1);
  assert.deepEqual(page.colourOf('rgba(0, 0, 0, 0)'), { rgb: [0, 0, 0], alpha: 0 });
  assert.equal(page.colourOf('color(srgb 1 1 1 / 0.5)', canvasOf()).alpha, 128 / 255, 'read back from a canvas');
  assert.equal(page.luminance('rgba(0, 0, 0, 0)'), null, 'a colour of nothing at all is no colour, and not black');
  // a faint white over a dark veil over white: 255 × 0.05 + (255 × 0.2) × 0.95 = 61.2
  const seen = page.seenThrough([{ rgb: [255, 255, 255], alpha: 0.05 }, { rgb: [0, 0, 0], alpha: 0.8 }, { rgb: [255, 255, 255], alpha: 1 }]);
  assert.match(seen, /^rgb\((61\.\d+), \1, \1\)$/);
  assert.ok(Math.abs(parseFloat(seen.slice(4)) - 61.2) < 1e-9, seen);

  // the three hosts of the issue, with no ink: the page is light on a light host, dark on a dark one
  assert.equal(inHost({ '--surface': 'transparent' }, { body: 'rgb(255, 255, 255)' }).dark(), false, 'transparent on white');
  assert.equal(inHost({ '--surface': 'rgba(0,0,0,.04)' }, { body: 'rgb(255, 255, 255)' }).dark(), false, 'a faint tint on white');
  assert.equal(inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { body: 'rgb(17, 17, 17)' }).dark(), true, 'a raised surface on #111');
  // an opaque ground is read as it is, whatever is behind it
  assert.equal(inHost({ '--surface': '#111' }, { body: 'rgb(255, 255, 255)' }).dark(), true);
  // each background is laid over the next: a dark veil on white, under a faint white, is dark;
  // a light one is not
  assert.equal(inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { main: 'rgba(0, 0, 0, 0.8)', body: 'rgb(255, 255, 255)' }).dark(), true);
  assert.equal(inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { main: 'rgba(0, 0, 0, 0.3)', body: 'rgb(255, 255, 255)' }).dark(), false);
  // the first opaque background ends the walk: html's is not seen through body's, nor read
  assert.equal(inHost({ '--surface': 'transparent' }, { body: 'rgb(255, 255, 255)', html: 'rgb(17, 17, 17)' }).dark(), false);
  assert.equal(inHost({ '--surface': 'transparent' }, { body: 'rgb(17, 17, 17)', html: 'color(display-p3 0 0 0)' }).dark(), true);
  // behind every element the canvas, painted with the root's colour scheme, or the
  // document's meta where the root says nothing
  const bare = (options) => inHost({ '--surface': 'transparent' }, {}, options).dark();
  assert.equal(bare({}), false);
  assert.equal(bare({ scheme: 'dark' }), true);
  assert.equal(bare({ scheme: 'light dark' }), false);
  assert.equal(bare({ scheme: 'light dark', readerDark: true }), true);
  assert.equal(bare({ scheme: 'only light', readerDark: true }), false);
  assert.equal(bare({ meta: 'dark' }), true);
  assert.equal(bare({ scheme: 'light', meta: 'dark' }), false, 'the root\'s own scheme before the meta');
  // a background behind the ground that cannot be read leaves the ground unknown: the page
  // keeps its light colours, never reading past it to the dark canvas
  assert.equal(inHost({ '--surface': 'transparent' }, { body: 'color(display-p3 0 0 0)' }, { scheme: 'dark' }).dark(), false);
  // where the ink says something, the ink decides, as before
  assert.equal(inHost({ '--ink': '#1d232a', '--surface': 'rgb(255 255 255 / .05)' }, { body: 'rgb(17, 17, 17)' }).dark(), false);
  // an opaque ground hides what is behind it: nothing around the page is read, then or on a look
  const opaque = inHost({ '--surface': '#fff' }, { body: 'rgb(17, 17, 17)' });
  opaque.look();
  assert.ok(![opaque.main, opaque.body, opaque.html].some(opaque.wasRead), 'an opaque ground reads nothing around it');
  const faint = inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { body: 'rgb(17, 17, 17)' });
  assert.ok([faint.main, faint.body].every(faint.wasRead));
});

test('a host that switches what is behind a translucent ground is followed, its tokens unchanged (issue 45)', () => {
  const host = inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { body: 'rgb(255, 255, 255)' });
  assert.equal(host.dark(), false);
  host.body.bg = 'rgb(17, 17, 17)'; // a class on body switched its background
  host.look();
  assert.equal(host.dark(), true);
  host.body.bg = 'rgb(255, 255, 255)';
  host.look();
  assert.equal(host.dark(), false);
  // a page in a shadow root: what is behind it is its host's, and on; a page slotted into
  // a host is drawn in the slot, inside the host's own shadow tree
  const shaded = inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { body: 'rgb(255, 255, 255)' });
  const panel = new dom.FakeNode('x-panel');
  panel.bg = 'rgb(17, 17, 17)';
  shaded.main.appendChild(panel);
  shaded.main.removeChild(shaded.themed);
  shaded.themed.parentNode = { host: panel, nodeType: 11 };
  shaded.look();
  assert.equal(shaded.dark(), true, 'in a shadow root of a dark host');
  const slotted = inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { body: 'rgb(255, 255, 255)' });
  const card = new dom.FakeNode('x-card'), frame = new dom.FakeNode('div'), slot = new dom.FakeNode('slot');
  frame.bg = 'rgb(17, 17, 17)'; // the card's own dark frame, inside its shadow tree
  frame.appendChild(slot);
  frame.parentNode = { host: card, nodeType: 11 };
  slotted.main.appendChild(card);
  card.appendChild(slotted.themed);
  slotted.themed.assignedSlot = slot;
  slotted.look();
  assert.equal(slotted.dark(), true, 'slotted into a card whose frame is dark');
  // a ground made translucent is seen through from then on: what is behind it is followed
  const turned = inHost({ '--surface': '#fff' }, { body: 'rgb(17, 17, 17)' });
  assert.equal(turned.dark(), false);
  turned.vars['--surface'] = 'rgb(255 255 255 / .05)';
  turned.look();
  assert.equal(turned.dark(), true);
  turned.body.bg = 'rgb(255, 255, 255)';
  turned.look();
  assert.equal(turned.dark(), false);
  // and the canvas: the root's colour scheme switched, with nothing behind the page
  const bare = inHost({ '--surface': 'transparent' }, {});
  assert.equal(bare.dark(), false);
  bare.scheme.value = 'dark';
  bare.look();
  assert.equal(bare.dark(), true);
});

test('the walk around the page follows the tree, not what a host\'s names put in its place (review of #46)', () => {
  // a faint white on a dark body: dark, read through every element out to the body
  const faint = (options) => inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { body: 'rgb(17, 17, 17)' }, options);
  assert.equal(faint().dark(), true);
  // an element named "host" in the document (<form name="host">, <img name="host">) is
  // document.host; an <iframe name="host"> makes it a window. Nothing is above the document.
  const named = faint({ before: ({ document, body }) => { document.host = body; } });
  assert.equal(named.dark(), true, 'document.host an element of the page');
  named.look();
  assert.equal(named.dark(), true);
  assert.equal(faint({ before: ({ document }) => { document.host = { closed: false }; } }).dark(), true, 'document.host a window');
  // a page inside a link: the link's host is its address's host name, and no node
  const linked = faint({
    before: ({ main, themed }) => {
      const link = new dom.FakeNode('a');
      link.host = 'example.org';
      main.removeChild(themed);
      main.appendChild(link);
      link.appendChild(themed);
    },
  });
  assert.equal(linked.dark(), true, 'inside a link');
  // In a browser the walk reads the DOM's own getters. A form gives its controls by name
  // (WebForms wraps a whole page in one form), so a control named parentNode, nodeType,
  // assignedSlot or host is what the form says for that name; the getters say what it is.
  const truth = new WeakMap();
  const held = (key) => function () {
    if (!truth.has(this)) throw new TypeError('Illegal invocation');
    return truth.get(this)[key];
  };
  class Node {}
  Object.defineProperty(Node.prototype, 'parentNode', { get: held('parentNode') });
  Object.defineProperty(Node.prototype, 'nodeType', { get: held('nodeType') });
  Node.prototype.getRootNode = function () { let n = this; while (truth.get(n).parentNode) n = truth.get(n).parentNode; return n; };
  class Element {}
  Object.defineProperty(Element.prototype, 'assignedSlot', { get: held('assignedSlot') });
  class ShadowRoot {}
  Object.defineProperty(ShadowRoot.prototype, 'host', { get: held('host') });
  const wrapped = (globals, options, names = ['parentNode', 'nodeType', 'assignedSlot', 'host']) => faint({
    ...options,
    globals,
    before: ({ document, html, body, main, themed }) => {
      const form = new dom.FakeNode('form'), control = new dom.FakeNode('input');
      main.removeChild(themed);
      main.appendChild(form);
      form.appendChild(control);
      form.appendChild(themed);
      [html, body, main, form, control, themed].forEach((n) => truth.set(n, { parentNode: n.parentNode, nodeType: 1, assignedSlot: null }));
      truth.set(document, { parentNode: null, nodeType: 9 });
      names.forEach((name) => { form[name] = control; });
    },
  });
  assert.equal(wrapped({ Node, Element, ShadowRoot }).dark(), true, 'inside a form whose controls take its names');
  // a page deep in its host is read out to its body: the limit is far above any real depth
  const deep = faint({
    before: ({ main, themed }) => {
      main.removeChild(themed);
      let at = main;
      for (let n = 0; n < 300; n++) { const div = new dom.FakeNode('div'); at.appendChild(div); at = div; }
      at.appendChild(themed);
    },
  });
  assert.equal(deep.dark(), true, 'a page 300 elements deep reads its body');
  // without the getters, a form whose control is named assignedSlot leads the walk round
  // and round between them: it ends at its limit, and the ground is unknown (light), never
  // a hang or an error, nor the canvas behind
  const round = wrapped({}, {}, ['assignedSlot']);
  assert.equal(round.dark(), false);
  assert.ok(round.ended());
  round.look();
  assert.ok(round.ended());
  const roundDark = wrapped({}, { scheme: 'dark' }, ['assignedSlot']);
  assert.equal(roundDark.dark(), false, 'not read past the limit to a dark canvas');
  assert.ok(roundDark.ended());
  // the walk out to the document, through shadow roots, ends too: a stand-in whose shadow
  // root is the page's own
  let asked = 0;
  const looped = faint({
    before: ({ themed }) => {
      const top = { nodeType: 11, host: themed, addEventListener() {}, removeEventListener() {} };
      themed.getRootNode = () => { if (++asked > 50000) throw new Error('the walk out to the document did not end'); return top; };
    },
  });
  looped.look();
  assert.ok(asked <= 50000);
});

test('a host that animates its switch is followed where the transition or animation ends (review of #46)', () => {
  // a transition moves the body's background and changes nothing in the document: no look is
  // asked for until it ends, and then one is
  const host = inHost({ '--surface': 'rgb(255 255 255 / .05)' }, { body: 'rgb(255, 255, 255)' });
  assert.equal(host.dark(), false);
  host.body.bg = 'rgb(17, 17, 17)';
  assert.equal(host.dark(), false, 'nothing heard while it runs');
  host.fire('transitionend');
  assert.equal(host.dark(), true);
  host.body.bg = 'rgb(255, 255, 255)'; // a theme switched by @keyframes
  host.fire('animationend');
  assert.equal(host.dark(), false);
  // A document whose names stand in for its own: an <img name="addEventListener">, an
  // <iframe name="documentElement"> (a window), an <img name="querySelector">. The page reads
  // the document through its prototypes: it hears the ends, and reads the canvas's scheme
  // from the root element or the meta, as in any document.
  const own = new WeakMap(); // what the document's prototype holds, once its names stand in for it
  const ownOf = (node) => (own.has(node) ? own.get(node) : node);
  const by = (name) => function (...args) { return ownOf(this)[name].apply(this, args); };
  class EventTarget {}
  EventTarget.prototype.addEventListener = by('addEventListener');
  EventTarget.prototype.removeEventListener = by('removeEventListener');
  class Document {}
  Object.defineProperty(Document.prototype, 'documentElement', { get() { return ownOf(this).documentElement; } });
  Document.prototype.querySelector = by('querySelector');
  const named = (globals, options, names = ['addEventListener', 'removeEventListener', 'documentElement', 'querySelector']) => inHost({ '--surface': 'transparent' }, {}, {
    ...options,
    globals,
    manual: true, // the document's names stand in before the first page mounts
    before: ({ document }) => {
      const kept = {};
      names.forEach((name) => { kept[name] = document[name]; });
      own.set(document, kept);
      const img = new dom.FakeNode('img');
      names.forEach((name) => { document[name] = name === 'documentElement' ? { closed: false } : img; });
    },
  });
  const read = named({ EventTarget, Document }, { scheme: 'dark' });
  assert.equal(read.dark(), true, 'the root element\'s scheme, read through the document\'s getter');
  assert.equal(named({ EventTarget, Document }, { meta: 'dark' }).dark(), true, 'the meta, found through the document\'s own querySelector');
  read.body.bg = 'rgb(255, 255, 255)';
  read.fire('transitionend');
  assert.equal(read.dark(), false, 'the end heard through the document\'s own addEventListener');
  // without the prototypes those names are all the page has: nothing is read or heard, and
  // nothing throws
  const unread = named({}, { scheme: 'dark' });
  assert.equal(unread.dark(), false);
  assert.ok(unread.ended());
  // and a root element that is not one is not read: the meta still is
  assert.equal(named({}, { meta: 'dark' }, ['documentElement']).dark(), true);
});

test('the reader\'s scheme alone is followed: a token in light-dark() resolves anew, its text unchanged (review of #34)', () => {
  // the host's ink is light-dark(#1d232a, #eee) and its root takes both schemes: the text the
  // page reads of the token stays the same, and only the reader's switch says it changed
  const host = inHost({ '--ink': 'light-dark(#1d232a, #eee)' }, { body: 'rgb(255, 255, 255)' });
  assert.equal(host.dark(), false);
  host.reader.matches = true;
  host.reader.heard.forEach((react) => react({ matches: true }));
  assert.equal(host.dark(), true);
  host.vars['--ink'] = 'light-dark(#1d232a, #eee)'; // a change elsewhere in the document: still dark
  host.look();
  assert.equal(host.dark(), true);
  host.reader.matches = false;
  host.reader.heard.forEach((react) => react({ matches: false }));
  assert.equal(host.dark(), false);
});

test('a page reads only the parts of the address under its own key, whatever the length of another key (review of #34)', () => {
  // `sd.` and `ab.` are as long: the page `sd` does not read `ab.item` as its own `item`
  const sd = dom.page(example(), undefined, { hash: 'ab.item=p01' });
  const ab = dom.body({ data: example() });
  ab.setAttribute('data-sd-key', 'ab');
  ab.ownerDocument = sd.document;
  sd.context.SentierDiagnostics.mount(ab);
  sd.open('ab.item=p01');
  assert.equal(ab.querySelector('[data-sd="item"]').hidden, false, 'ab opens its item');
  assert.equal(sd.byId.item.hidden, true, 'sd opens nothing');
  sd.open('sd.item=p01');
  assert.equal(sd.byId.item.hidden, false);
});

test('a key the host names is a plain word, neither the page\'s own nor another page\'s (review of issue 27)', () => {
  for (const [key, why] of [['a&b', /is not a plain word/], ['left.item', /is not a plain word/], ['', /is not a plain word/],
    ['x'.repeat(41), /is not a plain word/], ['sd', /is one the page gives/], ['SD2', /is one the page gives/]]) {
    const drawn = dom.page(example(), undefined, { attributes: { 'data-sd-key': key }, hash: 'item=p01' });
    assert.match(drawn.byId['load-error'].textContent, why, JSON.stringify(key));
    assert.equal(drawn.byId.load.hidden, false, key);
    assert.equal(drawn.byId.content.hidden, true, key);
    assert.equal(drawn.context.location.hash, '#item=p01', 'the address is left as it was');
  }
  assert.equal(dom.page(example(), undefined, { attributes: { 'data-sd-key': 'x'.repeat(40) } }).byId.load.hidden, true);
  // two pages named alike: the second is refused while the first is in the document
  const mountBeside = (drawn, key) => {
    const next = dom.body({ data: example() });
    if (key !== undefined) next.setAttribute('data-sd-key', key);
    next.ownerDocument = drawn.document;
    drawn.context.SentierDiagnostics.mount(next);
    return next;
  };
  const errorOf = (root) => root.querySelector('[data-sd="load-error"]').textContent;
  const left = dom.page(example(), undefined, { attributes: { 'data-sd-key': 'left' } });
  const twin = mountBeside(left, 'left');
  assert.match(errorOf(twin), /^Another page in the document has the key data-sd-key="left": .* This page is drawn once the other has left\.$/);
  assert.equal(twin.querySelector('[data-sd="content"]').hidden, true);
  assert.equal(errorOf(mountBeside(left, 'right')), '');
  // once the first has left, the page that waited is drawn, takes the key and reads the address
  left.root.isConnected = false;
  left.open('left.item=p01');
  assert.equal(errorOf(twin), '');
  assert.equal(twin.querySelector('[data-sd="content"]').hidden, false);
  assert.equal(twin.querySelector('[data-sd="item"]').hidden, false);
  assert.equal(left.byId.item.hidden, true, 'the page that left opens nothing');
  // a page drawn in place of one that left takes its key
  twin.isConnected = false;
  assert.equal(errorOf(mountBeside(left, 'left')), '');
});

test('a page whose key is refused keeps saying why, whatever the host calls (review of issue 27)', () => {
  // a host that mounts by hand and gives the page its file: the key's reason stays, never a
  // fault of the file
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual', 'data-sd-key': 'sd' }, hash: 'item=p01' });
  const api = drawn.context.SentierDiagnostics.mount(drawn.root);
  const reason = /is one the page gives/;
  assert.match(drawn.byId['load-error'].textContent, reason);
  api.show(example(), true);
  assert.match(drawn.byId['load-error'].textContent, reason);
  api.open('p01');
  api.close();
  assert.match(drawn.byId['load-error'].textContent, reason);
  assert.equal(drawn.byId.content.hidden, true);
  assert.equal(drawn.byId.item.hidden, true);
  assert.equal(drawn.context.location.hash, '#item=p01', 'the address is left as it was');
});

test('a page drawn again in place of a removed one takes the key it left, so an address made before still opens it (review of issue 27)', () => {
  const drawn = dom.page(example()); // "sd."
  drawn.root.isConnected = false; // the host removed it, and draws it again
  drawn.context.location.hash = '#sd.item=p01';
  const again = dom.body({ data: example() });
  again.ownerDocument = drawn.document;
  drawn.context.SentierDiagnostics.mount(again);
  assert.equal(again.querySelector('[data-sd="item"]').hidden, false);
  // while the first is still there, the next page takes the next key
  const kept = dom.page(example());
  const beside = dom.body({ data: example() });
  beside.ownerDocument = kept.document;
  kept.context.location.hash = '#sd.item=p01';
  kept.context.SentierDiagnostics.mount(beside);
  assert.equal(beside.querySelector('[data-sd="item"]').hidden, true);
  kept.open('sd2.item=p01');
  assert.equal(beside.querySelector('[data-sd="item"]').hidden, false);
});

// a MutationObserver as far as the page uses it: what it watches, and a call that delivers records
const observerKind = (observers) => class {
  constructor(react) { this.react = react; this.watched = []; observers.push(this); }
  observe(node, options) { this.watched.push([node, options]); }
  disconnect() { this.watched = []; }
};

test('a host that answers the page\'s reading of its colours sets off no other reading (review of issue 30)', () => {
  const observers = [];
  const frames = [];
  const vars = { '--ink': '#1d232a' };
  const first = dom.page(example(), undefined, { globals: { ...browserStyles(vars), MutationObserver: observerKind(observers), requestAnimationFrame: (f) => frames.push(f) } });
  // as a browser runs frames; a page that kept asking for one would never let this end
  const flush = () => { for (let n = 0; n < 50 && frames.length; n++) frames.shift()(); return frames.length; };
  // the loads the document hears on their way down (capture), for every page of the window
  const loaded = () => (first.documentListeners.load || []).filter(([, capture]) => capture).map(([react]) => react);
  const around = new dom.FakeNode('main');
  around.nodeType = 1;
  const themed = dom.body({ data: example() });
  themed.ownerDocument = first.document;
  around.appendChild(themed);
  first.context.SentierDiagnostics.mount(themed);
  const watch = observers[observers.length - 1];
  // the host: an observer of its wrapper's children that marks the wrapper on each change
  // (a counter, or the same value each time); the browser hands each mark to the page's observer
  let probes = 0, marks = 0, written = 0;
  const own = { append: themed.appendChild.bind(themed), remove: themed.removeChild.bind(themed), set: themed.setAttribute.bind(themed), unset: themed.removeAttribute.bind(themed) };
  const mark = () => { marks += 1; around.setAttribute('data-updated', 'yes'); watch.react([{ type: 'attributes', target: around }]); };
  themed.appendChild = (child) => { probes += 1; const got = own.append(child); mark(); return got; };
  themed.removeChild = (child) => { const got = own.remove(child); mark(); return got; };
  themed.setAttribute = (name, value) => { if (name === 'data-sd-scheme') written += 1; return own.set(name, value); };
  themed.removeAttribute = (name) => { if (name === 'data-sd-scheme') written += 1; return own.unset(name); };

  // the host switches to a dark theme: one reading, then the host's marks find nothing new
  vars['--ink'] = '#eee';
  watch.react([{ type: 'attributes', target: around }]);
  assert.equal(flush(), 0, 'the page stops asking for frames');
  assert.equal(themed.getAttribute('data-sd-scheme'), 'dark');
  assert.equal(probes, 2, 'one reading of the ink: two probes');
  assert.equal(marks, 4, 'the host marked each probe put in and taken out, and nothing more');
  assert.equal(written, 1, 'the mark set once');
  // changes that leave the host's tokens as they were: one look a frame, and no reading
  for (let n = 0; n < 5; n++) watch.react([{ type: 'childList', target: around }]);
  assert.equal(frames.length, 1, 'five changes in one frame, one look');
  flush();
  assert.equal(probes, 2);
  assert.equal(written, 1, 'a look that finds what it found before writes nothing');
  // the host's ink changes and its scheme does not: read again, the mark not written again
  vars['--ink'] = 'light-dark(#eee, #1d232a)'; // another token, the same light ink
  watch.react([{ type: 'attributes', target: around }]);
  flush();
  assert.equal(probes, 4, 'the ink changed: read');
  assert.equal(written, 1, 'the scheme did not: nothing written');
  // a stylesheet that finished loading (a host that swapped its theme's sheet) changes no
  // element: the load is caught on its way down the document, and looked at
  vars['--ink'] = '#1d232a';
  assert.equal(loaded().length, 1, 'one listener for the loads, whatever the number of pages');
  loaded().forEach((react) => react({ type: 'load' }));
  flush();
  assert.equal(themed.getAttribute('data-sd-scheme'), null);
  assert.equal(probes, 6);
  assert.equal(written, 2);
});

test('a page mounted before it is put in reads the host\'s colours once it is in (review of issue 30)', () => {
  const observers = [];
  const vars = { '--ink': '#eee' };
  // a browser computes no style for an element outside the document
  const styles = browserStyles(vars);
  const outside = (node) => { for (let n = node; n; n = n.parentNode) if (n.isConnected === false) return true; return false; };
  const browser = { getComputedStyle: (node) => (outside(node) ? { getPropertyValue: () => '', color: '' } : styles.getComputedStyle(node)) };
  const first = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { ...browser, MutationObserver: observerKind(observers) } });
  const built = dom.body({ data: example() });
  // built from a <template>: its document is inert, with no window, until the host puts it in
  built.ownerDocument = { createElement: first.document.createElement, createTextNode: first.document.createTextNode };
  built.isConnected = false;
  first.context.SentierDiagnostics.mount(built);
  assert.equal(built.getAttribute('data-sd-scheme'), null, 'nothing to read yet');
  const watching = observers[observers.length - 1].watched.map(([node]) => node);
  assert.deepEqual(watching, [first.document], 'the window\'s document is watched, not the template\'s');
  built.isConnected = true; // the host puts it in: the document's observer sees an element added
  built.ownerDocument = first.document;
  observers[observers.length - 1].react([{ type: 'childList' }]);
  assert.equal(built.getAttribute('data-sd-scheme'), 'dark');
  // seen in the document by that look alone: once it leaves, the page drawn in its place takes its key
  built.isConnected = false;
  first.context.location.hash = '#sd.item=p01';
  const again = dom.body({ data: example() });
  again.ownerDocument = first.document;
  first.context.SentierDiagnostics.mount(again);
  assert.equal(again.querySelector('[data-sd="item"]').hidden, false);
});

test('pages built and mounted before the host puts them in take keys of their own once they are in (review of issue 27, and of 233b988)', () => {
  const observers = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers) } });
  const build = (key) => {
    const root = dom.body({ data: example() });
    if (key !== undefined) root.setAttribute('data-sd-key', key);
    root.ownerDocument = drawn.document;
    root.isConnected = false;
    drawn.context.SentierDiagnostics.mount(root);
    return root;
  };
  const drawerOf = (root) => root.querySelector('[data-sd="item"]');
  const errorOf = (root) => root.querySelector('[data-sd="load-error"]').textContent;
  const a = build(), b = build();
  assert.deepEqual(Object.keys(drawn.context.SENTIER_DIAGNOSTICS_KEYS), [], 'no key is taken outside the document');
  a.isConnected = true; b.isConnected = true; // the host puts both in
  drawn.open('sd.item=p01');
  assert.equal(drawerOf(a).hidden, false);
  assert.equal(drawerOf(b).hidden, true, 'the second did not take the first one\'s key');
  drawn.open('sd2.item=p01');
  assert.equal(drawerOf(b).hidden, false);
  assert.equal(drawerOf(a).hidden, true);
  // named alike, both built before either is put in: neither is refused until both are in
  const left = build('left'), twin = build('left');
  assert.equal(errorOf(left), '');
  assert.equal(errorOf(twin), '');
  left.isConnected = true; twin.isConnected = true;
  drawn.open('left.item=p01');
  assert.equal(drawerOf(left).hidden, false);
  assert.match(errorOf(twin), /Another page in the document has the key data-sd-key="left"/);
  // a page that was in and has left: the page drawn in its place takes its key, and the
  // one it replaces opens nothing
  a.isConnected = false;
  const c = build();
  c.isConnected = true;
  drawn.open('sd.item=p02');
  assert.equal(drawerOf(c).hidden, false);
  assert.equal(drawerOf(a).hidden, true, 'the removed page opens nothing');
  // a page built and never put in takes no key: the next page put in takes the first free one
  build();
  const d = build();
  d.isConnected = true;
  drawn.open('sd3.item=p01');
  assert.equal(drawerOf(d).hidden, false);
  assert.equal(drawerOf(c).hidden, true);
});

test('a page taken out and put back works: it takes its key again, or the next free one, never one a page in the document holds (review of 233b988)', () => {
  // a host with tabs takes the page of a hidden tab out of the document, and puts it back
  const observers = [];
  const drawn = dom.page(example(), undefined, { globals: { MutationObserver: observerKind(observers) } }); // "sd"
  const watchOfFirst = observers[0];
  const putBack = (root) => { root.isConnected = true; observers.forEach((o) => o.react([{ type: 'childList' }])); };
  const beside = (key) => {
    const root = dom.body({ data: example() });
    if (key !== undefined) root.setAttribute('data-sd-key', key);
    root.ownerDocument = drawn.document;
    drawn.context.SentierDiagnostics.mount(root);
    return root;
  };
  const drawerOf = (root) => root.querySelector('[data-sd="item"]');
  const titleOf = (root) => root.querySelector('[data-sd="item-title"]').textContent;
  const nameOf = (id) => example().items.find((i) => i.id === id).name;
  drawn.root.isConnected = false;
  const b = beside(); // takes "sd": the first is out of the document
  putBack(drawn.root);
  drawn.open('sd2.item=p01&sd.item=p03');
  assert.equal(drawerOf(drawn.root).hidden, false, 'the first, put back, took the next free key');
  assert.equal(titleOf(drawn.root), nameOf('p01'));
  assert.equal(titleOf(b), nameOf('p03'), 'the page that took its key keeps it');
  assert.ok(watchOfFirst.watched.length > 0, 'and it still follows the host\'s theme');
  // a file handed to a page that is out, and whose key another took: it reads no part of
  // that page's
  const handed = dom.body({});
  handed.ownerDocument = drawn.document;
  handed.setAttribute('data-sentier-diagnostics', 'manual');
  const api = drawn.context.SentierDiagnostics.mount(handed); // takes "sd3"
  handed.isConnected = false;
  const taker = beside(); // takes "sd3": the page that held it is out
  drawn.open('sd3.item=p02');
  assert.equal(drawerOf(taker).hidden, false);
  api.show(example(), true);
  assert.equal(drawerOf(handed).hidden, true, 'the page that is out opens nothing of the page that took its key');
  // put back where its own key and a lower one are both free: it takes its own again, so the
  // addresses made for it still open it
  taker.isConnected = false;
  drawn.root.isConnected = false;
  b.isConnected = false; // "sd" and "sd2" are free, and "sd3" is
  putBack(handed);
  drawn.open('sd3.item=p01');
  assert.equal(drawerOf(handed).hidden, false);
  assert.equal(titleOf(handed), nameOf('p01'));
  // put back where no page took its key: it keeps it, and reads the address as it is now
  const kept = dom.page(example(), undefined, { globals: { MutationObserver: observerKind(observers) } });
  kept.root.isConnected = false;
  kept.open('sd.item=p02');
  assert.equal(kept.byId.item.hidden, true, 'a page out of the document answers no address');
  kept.root.isConnected = true;
  observers[observers.length - 1].react([{ type: 'childList' }]);
  assert.equal(kept.byId.item.hidden, false);
  assert.equal(kept.byId['item-title'].textContent, nameOf('p02'));
  // a page the host named: put back while another holds its name, it waits and says why,
  // and is drawn once the other has left
  const left = beside('left');
  left.isConnected = false;
  const right = beside('left');
  putBack(left);
  assert.match(left.querySelector('[data-sd="load-error"]').textContent, /Another page in the document has the key data-sd-key="left"/);
  drawn.open('left.item=p01');
  assert.equal(drawerOf(right).hidden, false);
  assert.equal(drawerOf(left).hidden, true);
  right.isConnected = false;
  observers.forEach((o) => o.react([{ type: 'childList' }]));
  assert.equal(left.querySelector('[data-sd="content"]').hidden, false);
  assert.equal(drawerOf(left).hidden, false, 'drawn at the address as it is');
});

test('a page in the document takes its key when it is mounted, file or not; one put in later, when the document changes, before any frame (review of 233b988)', () => {
  const observers = [];
  const frames = []; // frames held, as in a tab in the background
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers), requestAnimationFrame: (f) => frames.push(f) } });
  const mount = (data, inside) => {
    const root = dom.body(data ? { data } : {});
    root.ownerDocument = drawn.document;
    root.isConnected = inside;
    drawn.context.SentierDiagnostics.mount(root);
    return root;
  };
  const empty = mount(null, true); // a host that hands it its file later
  const held = () => Object.keys(drawn.context.SENTIER_DIAGNOSTICS_KEYS).map((k) => [k, drawn.context.SENTIER_DIAGNOSTICS_KEYS[k].deref().root]);
  assert.deepEqual(held(), [['sd', empty]]);
  const later = mount(example(), false);
  later.isConnected = true;
  observers[observers.length - 1].react([{ type: 'childList' }]);
  assert.deepEqual(held(), [['sd', empty], ['sd2', later]], 'taken when the document changed, with no frame run');
});

test('a page put in and handed its file before the document\'s change reaches it reads the address with its key (review of 233b988)', () => {
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, hash: 'sd.item=p01' });
  const root = dom.body({});
  root.ownerDocument = drawn.document;
  root.isConnected = false;
  const api = drawn.context.SentierDiagnostics.mount(root);
  root.isConnected = true; // put in, and handed its file in the same task
  api.show(example(), true);
  assert.equal(root.querySelector('[data-sd="item"]').hidden, false);
});

test('a page put in and taken out before it was found there, or never put in, takes no key (review of 233b988)', () => {
  const observers = [];
  const manual = { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers) } };
  const build = (drawn, key, inside) => {
    const root = dom.body({ data: example() });
    if (key !== undefined) root.setAttribute('data-sd-key', key);
    root.ownerDocument = drawn.document;
    root.isConnected = !!inside;
    drawn.context.SentierDiagnostics.mount(root);
    return root;
  };
  const deliver = () => observers.forEach((o) => o.react([{ type: 'childList' }])); // the task ends
  // mounted, put in, taken out and mounted again in one task (React's StrictMode in development)
  for (const key of [undefined, 'left']) {
    const drawn = dom.page(undefined, undefined, manual);
    const first = build(drawn, key);
    first.isConnected = true;
    first.isConnected = false;
    const again = build(drawn, key, true);
    deliver();
    assert.equal(again.querySelector('[data-sd="load-error"]').textContent, '', String(key));
    drawn.open((key || 'sd') + '.item=p01');
    assert.equal(again.querySelector('[data-sd="item"]').hidden, false, String(key));
    assert.equal(first.querySelector('[data-sd="item"]').hidden, true, String(key));
  }
  // mounted and never put in (a host's error path): the page drawn next takes "sd"
  const drawn = dom.page(undefined, undefined, manual);
  build(drawn);
  const next = build(drawn, undefined, true);
  drawn.open('sd.item=p01');
  assert.equal(next.querySelector('[data-sd="item"]').hidden, false);
});

test('unmount takes a page\'s listeners off and gives its key up; the address keeps what it said (review of 233b988)', () => {
  const observers = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers) } });
  const hashListeners = () => (drawn.listeners.hashchange || []).length;
  const root = dom.body({ data: example() });
  root.ownerDocument = drawn.document;
  const api = drawn.context.SentierDiagnostics.mount(root);
  const watch = observers[observers.length - 1];
  assert.equal(hashListeners(), 1);
  drawn.open('sd.item=p01');
  assert.equal(root.querySelector('[data-sd="item"]').hidden, false);
  api.unmount();
  assert.equal(hashListeners(), 0);
  assert.deepEqual(watch.watched, [], 'it watches the document no more');
  assert.equal(root.querySelector('[data-sd="content"]').hidden, true, 'it draws nothing');
  assert.equal(root.querySelector('[data-sd="item"]').hidden, true);
  assert.equal(drawn.context.location.hash, '#sd.item=p01', 'the address is left as it was');
  root.querySelector('[data-sd="grid-table"]').querySelectorAll('tr[data-item]')[0].childNodes[0].dispatch('click', {});
  assert.equal(root.querySelector('[data-sd="item"]').hidden, true, 'a click opens nothing');
  api.open('p01');
  api.show(example(), true);
  assert.equal(root.querySelector('[data-sd="content"]').hidden, true, 'and does nothing a host asks of it');
  watch.react([{ type: 'childList' }]);
  // still in the document, its key is free: the page mounted next takes it and opens the item
  const next = dom.body({ data: example() });
  next.ownerDocument = drawn.document;
  drawn.context.SentierDiagnostics.mount(next);
  assert.equal(next.querySelector('[data-sd="item"]').hidden, false);
});

test('an element unmounted can be mounted again, and only the page mounted last answers on it (review of 3a80142)', () => {
  // React's StrictMode in development: mount, unmount and mount again, on one element
  const observers = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers) } });
  const root = dom.body({});
  root.setAttribute('data-sd-matrix', 'matrix.js');
  root.ownerDocument = drawn.document;
  const { mount } = drawn.context.SentierDiagnostics;
  const part = (name) => root.querySelector('[data-sd="' + name + '"]');
  const first = mount(root);
  first.show(local(), true);
  // how many listeners each element of the page holds, the page's own element first
  const held = () => [root].concat(root.querySelectorAll('[data-sd]')).map((node) => Object.values(node.listeners).reduce((n, list) => n + list.length, 0));
  const heldByOne = held();
  const sortOfFirst = part('grid-table').querySelectorAll('th[scope="col"]')[0].querySelector('button[type="button"]');
  const cardOfFirst = part('dist-cards').querySelectorAll('div[data-indicator]')[0].querySelector('button[type="button"]');
  const scriptOfFirst = drawn.head.querySelectorAll('script[src]')[0];
  first.unmount();
  assert.equal(root.getAttribute('data-sd-mounted'), null, 'the element is free again');
  // what the first page drew, and the matrix it asked for, do nothing once it is unmounted
  const said = part('matrix-said').textContent;
  sortOfFirst.dispatch('click', {});
  cardOfFirst.dispatch('click', {});
  drawn.context.SENTIER_DIAGNOSTICS_MATRIX = full();
  scriptOfFirst.onload();
  delete drawn.context.SENTIER_DIAGNOSTICS_MATRIX;
  scriptOfFirst.onerror();
  assert.equal(part('content').hidden, true);
  assert.equal(part('matrix-said').textContent, said, 'neither taken nor refused');
  const api = mount(root);
  assert.ok(api, 'mounted again');
  api.show(local(), true);
  assert.equal(part('content').hidden, false);
  assert.deepEqual(held(), heldByOne, 'every element holds the listeners of one page, not of two');
  // the first page's matrix that failed to come does not speak for the second
  assert.match(part('matrix-said').textContent, /^Loading the matrix/);
  drawn.open('sd.item=' + local().items[0].id);
  assert.equal(part('item').hidden, false);
  part('item-close').dispatch('click', {});
  assert.equal(part('item').hidden, true);
  assert.equal(drawn.context.location.hash, '', 'the address says the drawer is closed');
  // and the second page's own matrix is taken when it comes
  drawn.context.SENTIER_DIAGNOSTICS_MATRIX = full();
  drawn.head.querySelectorAll('script[src]')[1].onload();
  assert.equal(part('pick-locked').hidden, true);
});

test('a page that gives a key up wakes the page waiting for it, which no change to the document may reach (review of 3a80142)', () => {
  // the holder sits in a closed shadow root the waiter does not watch: only its own
  // observer sees it leave
  const observers = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers) } });
  const named = () => {
    const root = dom.body({ data: example() });
    root.setAttribute('data-sd-key', 'left');
    root.ownerDocument = drawn.document;
    const api = drawn.context.SentierDiagnostics.mount(root);
    return { root, api, watch: observers[observers.length - 1] };
  };
  const waits = (page) => /Another page in the document has the key/.test(page.root.querySelector('[data-sd="load-error"]').textContent);
  const holder = named();
  const waiter = named();
  assert.ok(waits(waiter));
  holder.root.isConnected = false;
  holder.watch.react([{ type: 'childList' }]);
  assert.ok(!waits(waiter), 'drawn once the holder is gone');
  assert.equal(waiter.root.querySelector('[data-sd="content"]').hidden, false);
  // a holder unmounted in the document wakes it too, with no change delivered at all
  const third = named();
  assert.ok(waits(third));
  third.watch.react([{ type: 'childList' }]); // asked again while it waits: it waits once
  const fourth = named();
  fourth.api.unmount(); // a page unmounted while it waits waits no more
  waiter.api.unmount();
  assert.ok(!waits(third));
  drawn.open('left.item=p01');
  assert.equal(third.root.querySelector('[data-sd="item"]').hidden, false);
  assert.equal(drawn.context.SENTIER_DIAGNOSTICS_WAITERS.length, 0, 'no page is left waiting');
});

test('a page out of the document writes nothing to the address, whatever is clicked in it (review of 3a80142)', () => {
  // its key is free for another page, which may hold it by now: the address is not its own
  const drawn = dom.page(example(), undefined, { hash: 'other=1' }); // takes "sd"
  drawn.root.isConnected = false;
  drawn.byId['grid-table'].querySelectorAll('tr[data-item]')[0].childNodes[0].dispatch('click', {});
  assert.equal(drawn.context.location.hash, '#other=1');
});

test('a file that fails to come after the page was unmounted draws nothing (review of 3a80142)', async () => {
  let fail = null;
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, protocol: 'http:', fetch: () => new Promise((resolve, reject) => { fail = reject; }) });
  drawn.context.location.search = '?file=diagnostics.json';
  const root = dom.body({});
  root.ownerDocument = drawn.document;
  const api = drawn.context.SentierDiagnostics.mount(root);
  assert.ok(fail, 'the file was asked for');
  api.unmount();
  fail(new Error('gone'));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(root.querySelector('[data-sd="load"]').hidden, true);
  assert.equal(root.querySelector('[data-sd="load-error"]').textContent, '');
});

test('a look the page asked for before it was unmounted watches nothing again (review of 3a80142)', () => {
  const observers = [];
  const frames = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { ...browserStyles({ '--ink': '#1d232a' }), MutationObserver: observerKind(observers), requestAnimationFrame: (f) => frames.push(f) } });
  const root = dom.body({ data: example() });
  root.ownerDocument = drawn.document;
  const api = drawn.context.SentierDiagnostics.mount(root);
  const watch = observers[observers.length - 1];
  while (frames.length) frames.shift()();
  assert.ok(watch.watched.length > 0, 'it watches the host\'s theme');
  watch.react([{ type: 'attributes' }]);
  assert.equal(frames.length, 1, 'a look asked for');
  api.unmount();
  frames.shift()();
  assert.deepEqual(watch.watched, [], 'the look it asked for before does not watch again');
  assert.equal(frames.length, 0);
});

test('a page put in and clicked before the document\'s change reaches it writes the address with its key (review of 3a80142)', () => {
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' } });
  const root = dom.body({ data: example() });
  root.ownerDocument = drawn.document;
  root.isConnected = false;
  drawn.context.SentierDiagnostics.mount(root); // drawn out of the document, with no key
  root.isConnected = true;
  root.querySelector('[data-sd="grid-table"]').querySelectorAll('tr[data-item]')[0].childNodes[0].dispatch('click', {});
  assert.match(drawn.context.location.hash, /^#?sd\.item=/);
});

test('a matrix the host put in its page under another query is taken where it is this file\'s (review of issue 27)', () => {
  const listed = local().items[0].id;
  const at = full().items.findIndex((row) => row[0] === listed);
  const stale = full(); stale.values[at] = stale.values[at].map((v) => (typeof v === 'number' ? v * 3 : v));
  const handed = (entries) => dom.page(local(), undefined, { attributes: { 'data-sd-matrix': 'matrix.js' }, globals: { SENTIER_DIAGNOSTICS_MATRICES: entries } });
  // the plain address is the stale copy a host's ?v=3 exists to pass
  const fresh = handed([{ src: 'matrix.js', matrix: stale }, { src: 'matrix.js?v=3', matrix: full() }]);
  assert.equal(fresh.head.querySelector('script[src]'), null, 'nothing loaded again');
  assert.equal(gridRows(fresh).length, 10);
  // a stale copy under another query, none at the address: the named script is loaded
  assert.ok(handed([{ src: 'matrix.js?v=2', matrix: stale }]).head.querySelector('script[src]'));
  // stale at the address and under the query: the one at the address is refused, and why
  const refused = handed([{ src: 'matrix.js', matrix: stale }, { src: 'matrix.js?v=2', matrix: stale }]);
  assert.equal(refused.head.querySelector('script[src]'), null);
  assert.match(refused.byId['matrix-said'].textContent, /its results or classes differ/);
  // a script of the same name elsewhere is another page's
  assert.ok(handed([{ src: 'other/matrix.js?v=3', matrix: full() }]).head.querySelector('script[src]'));
});

test('the whole way names each count of the attribution in its own column (issue 8)', () => {
  const data = example();
  const water = data.indicators.find((i) => i.id === 'x:water');
  data.attribution['x:water'] = { ...data.attribution['x:water'], spread: 4, not_attributable: 1, unexplained_moved: 2 };
  const drawn = dom.page(data);
  const rows = drawn.byId['total-table'].all().filter((n) => n.tagName === 'TR');
  const head = rows[0].childNodes.map((c) => c.textContent);
  const row = rows.find((r) => r.childNodes[0].textContent.startsWith(water.name));
  const cell = (name) => row.childNodes[head.indexOf(name)].textContent;
  assert.deepEqual([cell('Spread over steps'), cell('Not attributable'), cell('Moved by what nothing explains')], ['4', '1', '2']);
  assert.match(row.childNodes[head.indexOf('Spread over steps')].getAttribute('title'), /the step with its largest difference did not move it/);
});

test('an item the file does not list is said to carry no explanation, never "none given" (issue 31)', () => {
  const data = local();
  const drawn = withMatrix();
  const unlisted = full().items.map((r) => r[0]).filter((id) => !data.items.some((i) => i.id === id));
  drawn.open('sd.item=' + unlisted[0]);
  const why = () => drawn.byId['item-body'].childNodes[1].seen().join(' ');
  assert.match(why(), /^Not listed in this file, so it carries no explanation of its own: a file explains only the products it lists\./);
  assert.doesNotMatch(why(), /None given/);
  // the last line of one with no wider explanation either: about what it moved in, never "none given"
  const lastLines = unlisted.map((id) => { drawn.open('sd.item=' + id); const lis = drawn.byId['item-body'].childNodes[1].childNodes; return lis[lis.length - 1].textContent; });
  const bare = lastLines.filter((line) => /^(No explanation in this file is about a step or indicator in which it moved\.|It moved in no comparison\.)$/.test(line));
  assert.ok(bare.length >= 1, lastLines.join(' | '));
  assert.ok(lastLines.every((line) => !/None given|no explanation in this file is about it/.test(line)), lastLines.join(' | '));
  drawn.open('sd.item=' + data.items[0].id);
  assert.doesNotMatch(drawn.byId['item-body'].childNodes[1].seen().join(' '), /Not listed in this file/);
});

test('a table of items is one tab stop; the arrow keys, Home and End move between its rows (issue 32)', () => {
  const drawn = dom.page(example());
  const stops = () => gridRows(drawn).filter((tr) => tr.getAttribute('tabindex') === '0');
  assert.equal(stops().length, 1);
  assert.equal(stops()[0], gridRows(drawn)[0]);
  assert.ok(gridRows(drawn).slice(1).every((tr) => tr.getAttribute('tabindex') === '-1'));
  let prevented = 0;
  const key = (tr, k) => tr.dispatch('keydown', { key: k, preventDefault: () => { prevented += 1; } });
  key(gridRows(drawn)[0], 'ArrowDown');
  assert.equal(stops()[0], gridRows(drawn)[1]);
  assert.equal(gridRows(drawn)[1].focused, true);
  key(gridRows(drawn)[1], 'End');
  assert.equal(stops()[0], gridRows(drawn)[gridRows(drawn).length - 1]);
  key(stops()[0], 'ArrowDown'); // at the end it stays
  assert.equal(stops()[0], gridRows(drawn)[gridRows(drawn).length - 1]);
  key(stops()[0], 'Home');
  assert.equal(stops()[0], gridRows(drawn)[0]);
  assert.equal(prevented, 4);
  gridRows(drawn)[2].childNodes[0].dispatch('click', {}); // a click makes its row the stop
  assert.equal(stops()[0], gridRows(drawn)[2]);
  const worst = drawn.byId['worst-table'].querySelectorAll('tr[data-item]');
  assert.equal(worst.filter((tr) => tr.getAttribute('tabindex') === '0').length, 1);
});

test('a breakdown is held to its item\'s results, whether it came with the page or over http (issue 33)', async () => {
  const scaled = () => { const b = wheat(); for (const e of Object.values(b.indicators)) { e.total = e.total.map((v) => v * 2); e.rest = e.rest.map((v) => v * 2); e.parts.forEach((p) => { p.values = p.values.map((v) => v * 2); }); } return b; };
  const broken = () => { const b = wheat(); const e = Object.values(b.indicators)[0]; e.parts[0].values[1] += 0.01; return b; };
  const empty = () => { const b = wheat(); b.indicators = {}; return b; };
  const body = (drawn) => drawn.byId['item-body'].seen().join(' ');
  const bundled = dom.page(example(), { 'p01-fix-1.json': scaled() });
  bundled.open('sd.item=p01');
  assert.match(body(bundled), /The breakdown p01-fix-1\.json is not of this file: its total in Climate is not the product's result in repro: not drawn\./);
  const served = (b) => () => Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify(b)) });
  for (const [made, said] of [[scaled, /is not of this file: its total in Climate is not/], [broken, /does not add up: in Climate its parts are not its total after/], [empty, /The breakdown p01-fix-1\.json holds no indicators: not drawn\./]]) {
    const fetched = dom.page(example(), undefined, { protocol: 'https:', fetch: served(made()) });
    fetched.open('sd.item=p01');
    await new Promise((done) => setImmediate(done));
    assert.match(body(fetched), said);
    assert.doesNotMatch(body(fetched), /Dinitrogen monoxide, field/, 'its parts are not drawn');
  }
  const right = dom.page(example(), undefined, { protocol: 'https:', fetch: served(wheat()) });
  right.open('sd.item=p01');
  await new Promise((done) => setImmediate(done));
  assert.match(body(right), /Dinitrogen monoxide, field/);
});

// ------------------------------------------------------------------ issue 40: what a page leaves behind

// a full collection, as the engine runs one when memory is short; a WeakRef made or read in
// a task holds what it names to the end of that task, so the tests collect between tasks
const vm = require('node:vm');
require('node:v8').setFlagsFromString('--expose-gc');
const collect = vm.runInNewContext('gc');
const nextTask = () => new Promise((resolve) => setImmediate(resolve));
const collected = async (refs) => {
  for (let n = 0; n < 3; n++) { await nextTask(); collect(); }
  return refs.map((ref) => ref.deref() === undefined);
};
// the reader's colour scheme, as matchMedia gives it: every query a list of its own, each
// with the listeners put on it
const schemeReader = (lists) => () => {
  const list = { matches: false, held: [] };
  list.addEventListener = (type, react) => list.held.push([type, react]);
  list.removeEventListener = (type, react) => { const at = list.held.findIndex(([t, r]) => t === type && r === react); if (at >= 0) list.held.splice(at, 1); };
  lists.push(list);
  return list;
};
const listening = (lists) => lists.reduce((n, list) => n + list.held.length, 0);
// a made-up page with its file of fixes (SPEC 16.8), as tests/test_fixes_page.py writes them
const fixesPage = () => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'fixes_page.json'), 'utf8')).pages['fixes that need others'];

test('a page a host removed without unmount() is let go once nothing holds it, and then nothing listens (issue 40)', async () => {
  const observers = [], lists = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers), matchMedia: schemeReader(lists) } });
  const { mount } = drawn.context.SentierDiagnostics;
  // pages as a host leaves them: mounted, used, taken out of the document, never unmounted,
  // and dropped; only a weak reference to each is kept here
  const removed = (() => {
    const refs = [];
    const put = (scripts, attributes) => {
      const root = dom.body(scripts);
      for (const [name, value] of Object.entries(attributes || {})) root.setAttribute(name, value);
      root.ownerDocument = drawn.document;
      mount(root);
      refs.push(new WeakRef(root));
      return root;
    };
    const open = put({ data: example() }); // "sd": its drawer open
    drawn.open('sd.item=p01');
    assert.equal(open.querySelector('[data-sd="item"]').hidden, false);
    put({ data: example() }, { 'data-sd-key': 'left' }); // holds the key "left"
    const waiter = put({ data: example() }, { 'data-sd-key': 'left' }); // waits for it
    assert.match(waiter.querySelector('[data-sd="load-error"]').textContent, /Another page in the document has the key/);
    // its file of fixes still coming, and one whose file came: fixes.js stays in the head too
    const fp = fixesPage();
    drawn.context.SENTIER_DIAGNOSTICS_MATRIX = fp.matrix;
    put({ data: fp.data }, { 'data-sd-fixes': 'fixes.js' });
    const fixed = put({ data: fp.data }, { 'data-sd-fixes': 'fixes.js' });
    delete drawn.context.SENTIER_DIAGNOSTICS_MATRIX;
    const fixScripts = drawn.head.querySelectorAll('script[src]').filter((script) => script.getAttribute('src') === 'fixes.js');
    assert.equal(fixScripts.length, 2);
    drawn.context.SENTIER_DIAGNOSTICS_FIXES_FILES = [{ src: 'fixes.js', fixes: fp.fixes }];
    fixScripts[1].onload();
    assert.match(fixed.querySelector('[data-sd="fixes-said"]').textContent, /^5 fixes/);
    delete drawn.context.SENTIER_DIAGNOSTICS_FIXES_FILES;
    put({ data: local() }, { 'data-sd-matrix': 'matrix.js' }); // its matrix still coming
    put({ data: local() }, { 'data-sd-matrix': 'matrix.js' }); // its matrix come
    const scripts = drawn.head.querySelectorAll('script[src]').filter((script) => script.getAttribute('src') === 'matrix.js');
    assert.equal(scripts.length, 2);
    drawn.context.SENTIER_DIAGNOSTICS_MATRIX = full();
    scripts[1].onload();
    delete drawn.context.SENTIER_DIAGNOSTICS_MATRIX;
    refs.forEach((ref) => { ref.deref().isConnected = false; });
    observers.forEach((o) => o.react([{ type: 'childList' }])); // the document changed: they left
    return refs;
  })();
  assert.equal(observers.length, 1, 'one observer for every page');
  assert.equal(drawn.listeners.hashchange.length, 1, 'one listener on the window for every page');
  assert.deepEqual(await collected(removed), removed.map(() => true), 'every page removed and dropped is collected');
  // once they are gone, the next event finds no page, and the window and the document are left alone
  drawn.changed();
  assert.equal(drawn.listeners.hashchange.length, 0);
  assert.deepEqual(observers[0].watched, [], 'the document is watched no more');
  ['load', 'transitionend', 'animationend'].forEach((type) => assert.equal((drawn.documentListeners[type] || []).length, 0, type));
  assert.equal(listening(lists), 0, 'nor the reader\'s colour scheme');
  assert.ok(drawn.context.SENTIER_DIAGNOSTICS_WAITERS.every((ref) => ref.deref() === undefined), 'no page is held waiting');
  // the scripts left in the head call nothing
  drawn.head.querySelectorAll('script[src]').forEach((script) => { assert.doesNotThrow(() => { script.onload(); script.onerror(); }); });
  // and a page mounted after takes the first key, and the window's listeners again
  const next = dom.body({ data: example() });
  next.ownerDocument = drawn.document;
  drawn.context.location.hash = '#sd.item=p02';
  const api = mount(next);
  assert.equal(next.querySelector('[data-sd="item"]').hidden, false);
  assert.equal(drawn.listeners.hashchange.length, 1);
  assert.ok(observers[0].watched.some(([node]) => node === drawn.document));
  // the next page that gives a key up takes a page collected while it waited off the list
  api.unmount();
  assert.equal(drawn.context.SENTIER_DIAGNOSTICS_WAITERS.length, 0);
});

test('a page out of the document that its host still holds is kept, and works when it is put back (issue 40)', async () => {
  const observers = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers) } });
  const tab = dom.body({ data: example() }); // a hidden tab's page, held by the host
  tab.ownerDocument = drawn.document;
  drawn.context.SentierDiagnostics.mount(tab);
  tab.isConnected = false;
  observers[0].react([{ type: 'childList' }]);
  await collected([]);
  tab.isConnected = true; // put back
  observers[0].react([{ type: 'childList' }]);
  drawn.open('sd.item=p01');
  assert.equal(tab.querySelector('[data-sd="item"]').hidden, false, 'it still answers its address');
});

test('the pages of a window share one observer, one listener of each kind and one look a frame, however many are removed (issue 40)', () => {
  const observers = [], lists = [], frames = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { ...browserStyles({ '--ink': '#1d232a' }), MutationObserver: observerKind(observers), matchMedia: schemeReader(lists), requestAnimationFrame: (f) => frames.push(f) } });
  const roots = [];
  for (let n = 0; n < 50; n++) {
    const root = dom.body({ data: example() });
    root.ownerDocument = drawn.document;
    drawn.context.SentierDiagnostics.mount(root);
    roots.push(root);
  }
  roots.slice(1).forEach((root) => { root.isConnected = false; }); // 49 removed, held here
  assert.equal(observers.length, 1);
  assert.equal(observers[0].watched.length, 1, 'the document watched once');
  assert.equal(drawn.listeners.hashchange.length, 1);
  ['load', 'transitionend', 'animationend'].forEach((type) => assert.equal(drawn.documentListeners[type].length, 1, type));
  assert.equal(listening(lists), 1);
  for (let n = 0; n < 100; n++) observers[0].react([{ type: 'attributes' }]);
  assert.equal(frames.length, 1, 'a hundred changes, one look for every page');
});

test('without WeakRef a removed page is held until unmount(), as before, and works the same (issue 40)', async () => {
  const observers = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { WeakRef: undefined, MutationObserver: observerKind(observers) } });
  const { mount } = drawn.context.SentierDiagnostics;
  let api;
  const refs = (() => {
    const root = dom.body({ data: example() });
    root.ownerDocument = drawn.document;
    api = mount(root);
    root.isConnected = false;
    observers[0].react([{ type: 'childList' }]);
    return [new WeakRef(root)];
  })();
  assert.deepEqual(await collected(refs), [false], 'held: the browser cannot let it go');
  // a page drawn in its place takes the key it left, and its address opens it
  const next = dom.body({ data: example() });
  next.ownerDocument = drawn.document;
  drawn.context.location.hash = '#sd.item=p01';
  mount(next);
  assert.equal(next.querySelector('[data-sd="item"]').hidden, false);
  api.unmount();
  api = null;
  assert.deepEqual(await collected(refs), [true], 'unmounted, it is let go');
});

test('a page that leaves wakes a page another copy of the script mounted, which its own listeners may not tell (issue 40)', () => {
  // two copies of the script in one window, each with its own listeners; the holder sits in
  // a shadow root only the first copy watches
  const observers = [];
  const drawn = dom.page(undefined, undefined, { attributes: { 'data-sentier-diagnostics': 'manual' }, globals: { MutationObserver: observerKind(observers) } });
  const first = drawn.context.SentierDiagnostics;
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'sentier_diagnostics', 'page', 'diagnostics.js'), 'utf8'), drawn.context);
  const second = drawn.context.SentierDiagnostics;
  assert.notEqual(first, second);
  const named = (copy) => {
    const root = dom.body({ data: example() });
    root.setAttribute('data-sd-key', 'left');
    root.ownerDocument = drawn.document;
    copy.mount(root);
    return root;
  };
  const holder = named(first);
  const waiter = named(second);
  assert.equal(observers.length, 2, 'an observer for each copy');
  assert.match(waiter.querySelector('[data-sd="load-error"]').textContent, /Another page in the document has the key/);
  holder.isConnected = false;
  observers[0].react([{ type: 'childList' }]); // only the first copy's observer sees it leave
  assert.equal(waiter.querySelector('[data-sd="load-error"]').textContent, '');
  assert.equal(waiter.querySelector('[data-sd="content"]').hidden, false, 'drawn once the holder is gone');
});

test('a page moved with its drawer open shows it again where it now stands (issue 40)', () => {
  const setUp = (narrow, kinds, standalone) => {
    const observers = [];
    const drawn = dom.page(example(), undefined, { standalone, globals: { MutationObserver: observerKind(observers) } });
    const drawer = drawn.byId.item;
    const calls = [];
    const state = { popover: false, modal: false };
    // as a browser: nothing out of the document is shown above, and a dialog open is not shown modal
    const out = () => drawn.root.isConnected === false;
    if (kinds.includes('popover')) {
      drawer.showPopover = () => { if (out()) throw new Error('InvalidStateError'); calls.push('popover'); state.popover = true; };
      drawer.hidePopover = () => { calls.push('hide'); state.popover = false; };
    }
    if (kinds.includes('dialog')) {
      drawer.showModal = () => { if (drawer.open || out()) throw new Error('InvalidStateError'); calls.push('modal'); drawer.open = true; state.modal = true; };
      drawer.close = () => { calls.push('close'); drawer.open = false; state.modal = false; };
    }
    drawer.matches = (selector) => (selector === ':popover-open' && state.popover) || (selector === ':modal' && state.modal);
    drawn.context.matchMedia = (query) => ({ matches: narrow && /max-width/.test(query) });
    // the host moves the page: the browser no longer draws the drawer above the rest (a popover
    // is hidden; a modal dialog stays open, no longer modal), and the change reaches the page
    const move = () => { state.popover = false; state.modal = false; observers.forEach((o) => o.react([{ type: 'childList' }])); };
    return { drawn, drawer, calls, state, move, observers };
  };
  const wide = setUp(false, ['popover', 'dialog']);
  wide.drawn.open('sd.item=p01');
  assert.deepEqual(wide.calls, ['popover']);
  wide.move();
  assert.deepEqual(wide.calls, ['popover', 'popover'], 'shown again as a popover');
  assert.ok(wide.state.popover);
  wide.observers.forEach((o) => o.react([{ type: 'attributes' }])); // a change that moves nothing
  assert.deepEqual(wide.calls, ['popover', 'popover']);
  wide.drawn.root.dispatch('keydown', { key: 'Escape' });
  wide.move();
  assert.deepEqual(wide.calls, ['popover', 'popover', 'hide'], 'a closed drawer is not opened by a move');
  // out of the document, it is not shown; put back, it is
  wide.drawn.open('sd.item=p01');
  wide.drawn.root.isConnected = false;
  wide.move();
  assert.equal(wide.state.popover, false);
  wide.drawn.root.isConnected = true;
  wide.observers.forEach((o) => o.react([{ type: 'childList' }]));
  assert.ok(wide.state.popover, 'shown once it is back');

  const phone = setUp(true, ['popover', 'dialog']);
  phone.drawn.open('sd.item=p01');
  assert.deepEqual(phone.calls, ['modal']);
  phone.move();
  assert.deepEqual(phone.calls, ['modal', 'close', 'modal'], 'closed, as an open dialog is not shown modal, and shown modal again');
  assert.ok(phone.state.modal);
  phone.drawer.dispatch('close', {}); // the close the page called is heard after it showed it again
  assert.equal(phone.drawer.hidden, false, 'and closes nothing');
  assert.equal(phone.drawn.context.location.hash, '#sd.item=p01');
  // a modal drawer taken out and put back later: shown modal again, not left open as it was
  phone.drawn.root.isConnected = false;
  phone.move();
  phone.drawn.root.isConnected = true;
  phone.observers.forEach((o) => o.react([{ type: 'childList' }]));
  assert.ok(phone.state.modal);
  phone.drawer.open = false; // the browser closes it itself (a back gesture)
  phone.state.modal = false;
  phone.drawer.dispatch('close', {});
  assert.equal(phone.drawer.hidden, true);

  // a page of its own, out of the document a while with its drawer open: nothing is tried
  // while it is out, and the drawer is shown above once it is back (review of b2ab444)
  for (const narrow of [false, true]) {
    const own = setUp(narrow, ['popover', 'dialog'], true);
    own.drawn.open('item=p01');
    own.drawn.root.isConnected = false;
    own.move();
    own.drawn.root.isConnected = true;
    own.observers.forEach((o) => o.react([{ type: 'childList' }]));
    if (own.calls.includes('close')) own.drawer.dispatch('close', {}); // the close the page called, heard after it is back
    assert.deepEqual(own.calls, narrow ? ['modal', 'close', 'modal'] : ['popover', 'popover'], String(narrow));
    assert.ok(own.state.popover || own.state.modal, 'shown above again');
    assert.equal(own.drawer.hidden, false, 'the item is still open');
  }

  // a browser that knows neither: the fixed element stands, and a move tries nothing
  const none = setUp(false, []);
  none.drawn.open('sd.item=p01');
  none.move();
  assert.deepEqual(none.calls, []);
  assert.equal(none.drawer.hidden, false);
  // a browser that knows dialogs and not ":modal": an open dialog is taken as modal, and a
  // change to the document does not close and show it again (which would change the
  // document again, and again)
  const older = setUp(false, ['dialog']);
  older.drawer.matches = (selector) => { throw new SyntaxError(selector); };
  older.drawn.open('sd.item=p01');
  for (let n = 0; n < 3; n++) older.observers.forEach((o) => o.react([{ type: 'attributes' }]));
  older.drawn.open('sd.item=p03'); // another item while it is open
  assert.deepEqual(older.calls, ['modal']);
  // showing it failed: the fixed element stands, and a move does not try again
  const failing = setUp(false, ['popover']);
  failing.drawer.showPopover = () => { failing.calls.push('popover'); throw new Error('not supported'); };
  failing.drawn.open('sd.item=p01');
  failing.move();
  assert.deepEqual(failing.calls, ['popover']);
  assert.equal(failing.drawer.hidden, false);
});

test('counts-only selections show measured indicator rows instead of item controls', () => {
  const data = countsOf(example());
  const drawn = dom.page(data);
  const table = drawn.byId['indicator-table'];
  assert.ok(table, 'the selected comparison has a table of counts');
  assert.equal(drawn.byId['item-results'].hidden, true);
  assert.equal(drawn.byId.worst.hidden, true);
  for (const comp of ['total', 'fix-1', 'rebuilt']) {
    drawn.open(comp === 'total' ? '' : 'sd.step=' + comp);
    assert.deepEqual(pressed(drawn), [comp]);
    const rows = table.querySelectorAll('tr[data-indicator]');
    assert.equal(rows.length, data.indicators.length);
    for (const row of rows) {
      const id = row.getAttribute('data-indicator');
      const block = (comp === 'total' ? data.counts.total : data.counts.steps[comp])[id];
      const paired = block.pairs - block.classes.missing;
      const moved = ['differs', 'beyond 10x', 'zero reference', 'zero result', 'sign change'].reduce((a, cls) => a + block.classes[cls], 0);
      assert.deepEqual(row.childNodes.slice(1).map((c) => c.textContent),
        [paired, paired ? moved : '—', paired ? block.directions.up : '—',
          paired ? block.directions.down : '—', block.classes.missing].map(String));
    }
    assert.doesNotMatch(drawn.byId['dist-said'].textContent, /matrix/);
  }
  const named = dom.page(example());
  assert.equal(named.byId['indicator-results'].hidden, true);
  assert.equal(named.byId['item-results'].hidden, false);
  assert.ok(gridRows(named).length);
});

test('a counts-only range keeps each selected step separate, including all-missing results', () => {
  const data = countsOf(example());
  const block = data.counts.steps['fix-1']['x:water'];
  for (const cls of Object.keys(block.classes)) block.classes[cls] = cls === 'missing' ? block.pairs : 0;
  const drawn = dom.page(data);
  drawn.open('sd.steps=fix-1:rebuilt');
  assert.deepEqual(pressed(drawn), ['fix-1', 'rebuilt']);
  assert.match(drawn.byId['step-said'].textContent, /separately/);
  assert.equal(drawn.byId.distributions.hidden, true);
  const tables = drawn.byId['indicator-table'].querySelectorAll('tbody[data-comp]');
  assert.deepEqual(tables.map((b) => b.getAttribute('data-comp')), ['fix-1', 'rebuilt']);
  for (const body of tables) assert.equal(body.querySelectorAll('tr[data-indicator]').length, data.indicators.length);
  const water = tables[0].querySelectorAll('tr[data-indicator]').find((r) => r.getAttribute('data-indicator') === 'x:water');
  assert.deepEqual(water.childNodes.slice(1).map((c) => c.textContent), ['0', '—', '—', '—', String(block.pairs)]);
  drawn.open('sd.step=fix-1');
  assert.equal(drawn.byId.distributions.hidden, false);
});

test('a single-step counts chain keeps the step distinct from the whole way on reload and by keyboard', () => {
  const data = countsOf(example());
  data.steps = data.steps.slice(0, 1);
  data.states = data.states.slice(0, 2);
  data.explanations = [];
  for (const att of Object.values(data.attribution)) att.dominant = { 'step-0': 0 };
  const drawn = dom.page(data, undefined, { hash: 'sd.step=step-0' });
  assert.equal(drawn.byId.load.hidden, true, drawn.byId['load-error'].textContent);
  assert.deepEqual(pressed(drawn), ['step-0']);
  chipOf(drawn, 'step-0').dispatch('keydown', { key: 'ArrowLeft' });
  assert.deepEqual(pressed(drawn), ['total']);
  chipOf(drawn, 'total').dispatch('keydown', { key: 'ArrowRight' });
  assert.deepEqual(pressed(drawn), ['step-0']);
  assert.match(drawn.context.location.hash, /sd.step=step-0/);
});

test('the selected step links to its source only when it has a safe address', () => {
  const data = countsOf(example());
  data.steps[1].link = 'https://example.org/checked-patch';
  data.steps[2].link = 'file:///internal/patch';
  const drawn = dom.page(data);
  drawn.open('sd.step=fix-1');
  const links = tagged(drawn.byId['step-said'], 'A');
  assert.equal(links.length, 1);
  assert.equal(links[0].getAttribute('href'), data.steps[1].link);
  assert.equal(links[0].textContent, 'Step source');
  drawn.open('sd.step=rebuilt');
  assert.equal(tagged(drawn.byId['step-said'], 'A').length, 0);
});

test('choosing one search result reveals the comparison and puts focus on its numbered step', () => {
  const drawn = dom.page(example());
  assert.equal(drawn.byId['pick-panel'].hidden, false);
  rowOf(drawn, 1).dispatch('click', {});
  assert.equal(drawn.byId['pick-panel'].hidden, true);
  assert.equal(drawn.byId['pick-open'].getAttribute('aria-expanded'), 'false');
  assert.equal(chipOf(drawn, 'fix-1').focused, true);
  drawn.byId['pick-open'].dispatch('click', {});
  rowOf(drawn, 2).dispatch('click', { shiftKey: true });
  assert.equal(drawn.byId['pick-panel'].hidden, false);
});

test('a public range reuses a measured population only for identical score tables and rule', () => {
  const states = ['a', 'b', 'b', 'c'].map(x => ({
    kind: 'build', identity: {scores: x.repeat(64)}, noise: {measured: false, by: null}
  }));
  const steps = [0, 1, 2].map(k => ({id: String(k), tolerance: {value: 0.01}}));
  const data = {states, steps};
  assert.equal(page.measuredRangeStep(data, 'scores', 0, 1), 0);
  assert.equal(page.measuredRangeStep(data, 'scores', 1, 2), 2);
  assert.equal(page.measuredRangeStep(data, 'scores', 0, 2), -1);
  steps[1].tolerance.value = 0.1;
  assert.equal(page.measuredRangeStep(data, 'scores', 0, 1), -1);
  steps[1].tolerance.value = 0.01;
  states[2].noise = {measured: true, by: {climate: 0.5}};
  assert.equal(page.measuredRangeStep(data, 'scores', 0, 1), -1);
  assert.equal(page.measuredRangeStep(data, 'other', 0, 1), -1);
});
