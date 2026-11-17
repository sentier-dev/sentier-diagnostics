/* sentier-diagnostics page: shows a diagnostics file (sentier-diagnostics/1) as it is.
 *
 * Plain JavaScript, no library, no network but the files the page names. The script mounts
 * into every element marked `data-sentier-diagnostics` (the body `page.body` writes), on a
 * page of its own or inside a host's page; it looks nothing up outside that element but the
 * address and the globals named below. A host that draws the element later calls
 * `SentierDiagnostics.mount(element, {data})`, and marks it `data-sentier-diagnostics="manual"`
 * so that it is not mounted before.
 *
 * The page works out no class, direction, verdict or count: they are in the file, checked by
 * the validator. It only orders and filters, formats numbers, divides the result after by the
 * result before to show their ratio, and subtracts consecutive results to show each step's
 * share. Every text of a file is set as text, never as markup.
 */
(function (global) {
  'use strict';

  var FORMAT = 'sentier-diagnostics/1';
  var MATRIX_FORMAT = 'sentier-diagnostics-matrix/1';
  var MATRIX_MAX_ITEMS = 200000;          // matrix.MAX_ITEMS
  var MATRIX_MAX_BYTES = 64 * 1024 * 1024; // matrix.MAX_BYTES
  var PAGE = 300;                          // rows of the grid drawn at a time
  var MOVES = ['differs', 'beyond 10x', 'zero reference', 'zero result', 'sign change'];
  var QUIET = ['agrees', 'within noise', 'near zero'];
  // the order of the classes from the worst: the same as the Python rule (rule.RANK)
  var RANK = {
    'sign change': 0, 'zero reference': 1, 'zero result': 2, 'beyond 10x': 3, 'differs': 4,
    'missing': 5, 'within noise': 6, 'agrees': 7, 'near zero': 8
  };
  var STRENGTH = { '1-1.1': 0.25, '1.1-1.25': 0.45, '1.25-2': 0.65, '2-10': 0.85, 'over 10': 1 };
  // the ends of the bands, as rule.SIZE_STEPS: the distance (|log10| of the factor) at which each ends
  var SIZE_STEPS = [[Math.log10(1.1), '1-1.1'], [Math.log10(1.25), '1.1-1.25'], [Math.log10(2), '1.25-2'], [1, '2-10']];
  var LOOK = ['off claim', 'not claimed', 'claimed, not moved'];
  var LOOK_MARK = { 'off claim': '◐', 'not claimed': '■', 'claimed, not moved': '○' };
  var SAID = {
    'agrees': 'the two results differ by no more than the tolerance',
    'within noise': 'they differ by no more than two builds of one state do',
    'differs': 'the results differ',
    'beyond 10x': 'one result is more than ten times the size of the other',
    'zero reference': 'the result before is zero or within the floor; the result after is not',
    'zero result': 'the result after is zero or within the floor; the result before is not',
    'sign change': 'the two results have different signs',
    'near zero': 'both results are within their floor: their ratio says nothing',
    'missing': 'a side has no result; it is not read as zero'
  };
  var SHORT = {
    'agrees': '=', 'within noise': '~', 'near zero': '≈ 0', 'missing': '∅',
    'zero reference': '0 →', 'zero result': '→ 0', 'sign change': '±'
  };
  // the codes of a matrix (matrix.CODES, matrix.VERDICT_CODES)
  var CODES = {
    '=': ['agrees', null], '~': ['within noise', null], '0': ['near zero', null], '-': ['missing', null],
    'D': ['differs', 'up'], 'd': ['differs', 'down'], 'B': ['beyond 10x', 'up'], 'b': ['beyond 10x', 'down'],
    'R': ['zero reference', 'up'], 'r': ['zero reference', 'down'], 'T': ['zero result', 'up'], 't': ['zero result', 'down'],
    'S': ['sign change', 'up'], 's': ['sign change', 'down']
  };
  var VERDICT_CODES = {
    'a': 'as claimed', 'o': 'off claim', 'n': 'not claimed', 'c': 'claimed, not moved',
    '~': 'within noise', '=': 'unchanged', '?': 'not judged'
  };
  var NO_CLAIM = '.';
  var SAME = '='; // matrix.SAME: a result equal to the one of the state before it

  // ------------------------------------------------------------------ pure helpers

  function groupThousands(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }

  // a result as a reader reads it: four significant digits; never "0" for a value that is not 0
  function formatNumber(v) {
    if (v === null || v === undefined) return 'missing';
    if (v === 0) return '0';
    var a = Math.abs(v);
    // one style from 1e4 on: toPrecision(4) would write 12345 as "1.235e+4" itself
    if (a >= 1e4 || a < 1e-3) {
      return v.toExponential(3).replace(/\.?0+e/, 'e').replace('e+', 'e').replace(/-/g, '−');
    }
    var s = v.toPrecision(4);
    if (s.indexOf('.') >= 0) s = s.replace(/0+$/, '').replace(/\.$/, '');
    return s.replace('-', '−');
  }

  // the change relative to the size of the result before, signed as the direction is
  function percentText(b, a) {
    var c = (a - b) / Math.abs(b) * 100;
    var size = Math.abs(c);
    var text;
    if (size === 0) text = '0';
    else if (size < 0.01) text = size.toExponential(1);
    else if (size >= 1000) text = groupThousands(Math.round(size));
    else text = size.toFixed(size >= 100 ? 0 : size >= 1 ? 1 : 2);
    return (c > 0 ? '+' : c < 0 ? '−' : '') + text + ' %';
  }

  // a step's share of the whole difference, signed; never "0.0 %" for a share that is not 0
  function shareText(part) {
    var v = part * 100, size = Math.abs(v);
    var text = size === 0 ? '0' : size < 0.1 ? size.toExponential(1) : size.toFixed(1);
    return (v > 0 ? '' : v < 0 ? '−' : '') + text + ' %';
  }

  // the result after divided by the result before, of two results of one sign; never "1" for
  // a ratio that is not 1, and never "Infinity" where the quotient leaves the floats
  function ratioText(before, after) {
    var r = after / before;
    if (!isFinite(r) || r === 0) {
      var orders = Math.log10(Math.abs(after)) - Math.log10(Math.abs(before));
      return '1e' + String(Math.round(orders)).replace('-', '−');
    }
    var d = r - 1;
    if (d !== 0 && Math.abs(d) < 1e-3) return '1 ' + (d > 0 ? '+ ' : '− ') + formatNumber(Math.abs(d));
    return formatNumber(r);
  }

  // a ratio as the grid shows it, compact enough for a column: three significant digits
  // ("1.00", "0.984", "2.27"), a power of ten below 0.01 and from 1000 on, and "1e600" where
  // the quotient leaves the floats. "1.00" is a rounding, not a claim of agreement: the
  // class says whether the two agree, and the cell's title holds both results exactly.
  function ratioShort(before, after) {
    var r = after / before;
    if (!isFinite(r) || r === 0) return ratioText(before, after);
    var s = r.toPrecision(3);
    if (r < 0.01 || s.indexOf('e') >= 0) s = r.toExponential(2).replace(/\.?0+e/, 'e').replace('e+', 'e');
    return s.replace(/-/g, '−');
  }

  // the 10th, 50th and 90th percentile in one precision: the smallest (three digits at
  // least, six at most) at which every two that differ read differently. "1.00, 1.00, 1.00"
  // over values that moved would hide the spread a reader looks for, and one line in mixed
  // precisions reads a rounded number as exact. Where six digits still read a percentile
  // as the median, the line says how it lies, and the numbers left take the digits they need.
  function quantileTexts(qs) {
    var values = [qs.p10, qs.median, qs.p90];
    var one = function (v, digits) {
      if (v !== 0 && (Math.abs(v) < 0.01 || Math.abs(v) >= 1e4)) return v.toExponential(digits - 1).replace(/\.?0+e/, 'e').replace('e+', 'e').replace(/-/g, '−');
      return v.toPrecision(digits).replace(/-/g, '−');
    };
    var pairs = [[0, 1], [1, 2], [0, 2]];
    var digitsFor = function (kept) {
      for (var d = 3; d <= 6; d++) {
        var apart = pairs.every(function (p) {
          return kept.indexOf(p[0]) < 0 || kept.indexOf(p[1]) < 0 || values[p[0]] === values[p[1]] || one(values[p[0]], d) !== one(values[p[1]], d);
        });
        if (apart) return d;
      }
      return null;
    };
    var words = {};
    var d = digitsFor([0, 1, 2]);
    if (d === null) {
      if (values[0] !== values[1] && one(values[0], 6) === one(values[1], 6)) words[0] = 'just under the median';
      if (values[2] !== values[1] && one(values[2], 6) === one(values[1], 6)) words[2] = 'just over the median';
      d = digitsFor([0, 1, 2].filter(function (i) { return !(i in words); })) || 6;
    }
    return [0, 1, 2].map(function (i) { return i in words ? words[i] : one(values[i], d); });
  }

  // Steps whose differences add up to more than this many times the whole difference
  // cancel: their shares would be large and of both signs, and in floating point the
  // whole may be mostly rounding. The page says so instead of printing them.
  var CANCEL = 10;

  // how an item's whole difference splits among the steps (SPEC 7): `values` are its
  // results per state, `explained` says per step whether a cause explains it, `totalClass`
  // is the class of the whole way. The split is exact up to rounding, so the page prints
  // the sum of the shares it shows, never a fixed 100 %.
  function splitOf(values, explained, totalClass) {
    if (totalClass === 'missing') return { state: 'missing' };
    if (MOVES.indexOf(totalClass) < 0) return { state: 'still' };
    for (var i = 0; i < values.length; i++) if (values[i] === null) return { state: 'gap' };
    var whole = values[values.length - 1] - values[0];
    var diffs = [], gross = 0;
    for (var k = 0; k + 1 < values.length; k++) {
      diffs.push(values[k + 1] - values[k]);
      gross += Math.abs(values[k + 1] - values[k]);
    }
    if (!whole || gross > CANCEL * Math.abs(whole)) return { state: 'cancel', factor: whole ? gross / Math.abs(whole) : Infinity };
    var shares = diffs.map(function (d) { return d / whole; });
    var sum = 0, unexplained = 0;
    shares.forEach(function (part, j) { sum += part; if (!explained[j]) unexplained += part; });
    return { state: 'split', shares: shares, sum: sum, unexplained: unexplained };
  }

  // what the whole way's row says of a split
  function splitText(split) {
    switch (split.state) {
      case 'split': return shareText(split.sum) + (split.unexplained ? ', of which nothing explains ' + shareText(split.unexplained) : '');
      case 'still': return 'not split: it did not move';
      case 'gap': return 'not split: missing in a state between';
      case 'missing': return 'not split: missing in the first or the last state';
      default: return 'not split: the steps cancel, their differences add up to ' + formatNumber(split.factor) + ' times the whole difference';
    }
  }

  // Noise above this is large: it puts every smaller difference of its indicator "within
  // noise". Same bound as chain.LARGE_NOISE.
  var LARGE_NOISE = 1e-2;

  // what a step's noise says: measured and identical, measured, or not measured. Two
  // identical builds are a finding, and never read as "not measured"; an indicator the noise
  // holds no size for was not measured, and is never read as identical. `ids` are the
  // file's indicators, and `many` what the file calls them.
  function noiseText(noise, ids, many) {
    if (!noise || !noise.measured) return 'not measured';
    var by = noise.by || {};
    var between = ' between ' + noise.between.join(' and ');
    var keys = Object.keys(by);
    var all = ids || keys;
    var absent = all.filter(function (k) { return !(k in by); }).length;
    if (!keys.length) return 'not measured: no result beyond the floor in both builds' + between;
    var part = absent ? ', for ' + keys.length + ' of ' + all.length + ' ' + (many || 'indicators') : '';
    var largest = Math.max.apply(null, keys.map(function (k) { return by[k]; }));
    if (largest === 0) return 'identical' + between + part;
    return 'measured' + between + part + (largest > LARGE_NOISE ? '; large: up to ' + formatNumber(largest * 100) + ' %' : '');
  }

  // a link a file may hold: an https address, or nothing. A page never makes any other
  // text a link, whatever the file says.
  function safeLink(value) {
    return typeof value === 'string' && /^https:\/\/[^\s]+$/.test(value) ? value : null;
  }

  // a file a page may load beside itself: a plain relative name, never an address or a way up
  function safeName(value) {
    return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._\/-]*$/.test(value) && value.indexOf('..') < 0;
  }

  function bandStep(band) {
    if (!band) return null;
    var at = band.indexOf('factor ');
    return at < 0 ? null : band.slice(at + 7);
  }

  // how far the sizes of two results of one sign lie apart, as rule.distance: the |log10|
  // of their factor, or, where the factor is too large or too small for a float, the
  // difference of their logarithms, which cannot overflow
  var SMALLEST_NORMAL = 2.2250738585072014e-308;
  function distance(before, after) {
    var factor = Math.abs(after) / Math.abs(before);
    if (isFinite(factor) && factor >= SMALLEST_NORMAL) return Math.abs(Math.log10(factor));
    return Math.abs(Math.log10(Math.abs(after)) - Math.log10(Math.abs(before)));
  }

  // the band of a pair, as rule.band, for a matrix, which holds no bands: the class and
  // direction are the file's, the band only names how far apart the two lie
  function bandOf(before, after, cls, dir) {
    if (cls === 'beyond 10x') return dir + ', factor over 10';
    if (cls !== 'differs') return null;
    var found = distance(before, after);
    for (var i = 0; i < SIZE_STEPS.length; i++) if (found <= SIZE_STEPS[i][0]) return dir + ', factor ' + SIZE_STEPS[i][1];
    return dir + ', factor ' + SIZE_STEPS[SIZE_STEPS.length - 1][1];
  }

  // the reader's own size filter: it hides values, it changes no class and no count.
  // A value without a ratio (a zero or a sign change) and a missing one always pass.
  function sizeAtLeast(cls, band, threshold) {
    if (!threshold) return true;
    if (['zero reference', 'zero result', 'sign change', 'missing', 'beyond 10x'].indexOf(cls) >= 0) return true;
    if (cls !== 'differs') return false;
    var step = bandStep(band);
    return step !== null && parseFloat(step) >= threshold;
  }

  // how one value is drawn: its text, its tone (direction or kind), the strength of the tone
  function cellView(before, after, cls, dir, band) {
    var view = { text: '', tone: 'none', strength: 0, noRatio: false, mark: '' };
    view.title = cls + (SAID[cls] ? ': ' + SAID[cls] : '') + '. Before ' +
      (before === null ? 'missing' : String(before)) + ', after ' +
      (after === null ? 'missing' : String(after)) + (dir ? '. Went ' + dir + '.' : '.');
    switch (cls) {
      case 'missing':
        view.text = before === null && after === null ? 'missing' : before === null ? 'missing before' : 'missing after';
        view.tone = 'missing';
        break;
      case 'near zero':
        view.text = '≈ 0'; view.tone = 'near'; break;
      case 'agrees':
        view.text = '='; view.tone = 'none'; break;
      case 'within noise':
        view.text = '~ ' + percentText(before, after); view.tone = 'noise'; break;
      case 'zero reference':
        view.text = before === 0 ? 'from 0' : 'from ≈ 0'; view.tone = dir; view.strength = 1; view.noRatio = true; break;
      case 'zero result':
        view.text = after === 0 ? 'to 0' : 'to ≈ 0'; view.tone = dir; view.strength = 1; view.noRatio = true; break;
      case 'sign change':
        view.text = (before < 0 ? '−' : '+') + ' → ' + (after < 0 ? '−' : '+');
        view.tone = dir; view.strength = 1; view.noRatio = true; break;
      case 'beyond 10x':
        var up = Math.abs(after) >= Math.abs(before);
        var r = up ? Math.abs(after) / Math.abs(before) : Math.abs(before) / Math.abs(after);
        var orders = Math.abs(Math.log10(Math.abs(after)) - Math.log10(Math.abs(before)));
        view.text = 'size ' + (up ? '×' : '÷') + (isFinite(r) ? formatNumber(r) : '1e' + Math.round(orders));
        view.tone = dir; view.strength = 1; view.mark = '»'; break;
      case 'differs':
        view.text = percentText(before, after); view.tone = dir;
        view.strength = STRENGTH[bandStep(band)] || 0.5; break;
      default:
        view.text = String(cls);
    }
    return view;
  }

  // a value of the matrix grid: the ratio after ÷ before in every cell that has one, agreeing
  // pairs included ("1.00"), so that a column reads as numbers; else what cellView says
  // ("≈ 0", "from 0", "− → +", "missing"). The class shows as the tint and a mark, never in
  // place of the number: the colour is the direction's, its strength the band's. The ratio is
  // a display; the class stays the file's.
  var RATIO_CLASSES = ['agrees', 'within noise', 'differs', 'beyond 10x'];
  function ratioView(before, after, cls, dir, band) {
    var view = cellView(before, after, cls, dir, band);
    var ratio = before !== null && after !== null && before !== 0 && after !== 0 && (before > 0) === (after > 0);
    if (ratio && RATIO_CLASSES.indexOf(cls) >= 0) {
      view.text = ratioShort(before, after);
      if (cls === 'within noise') view.mark = '~';
      view.title += ' After ÷ before: ' + String(after / before) + '.';
    }
    return view;
  }

  // the key that orders values from the worst: the same as the Python rule (rule.severity)
  function severityKey(before, after, cls) {
    var rank = RANK.hasOwnProperty(cls) ? RANK[cls] : 9;
    if (before === null || after === null) return [rank, 0];
    var magnitude;
    if (before !== 0 && after !== 0 && (before > 0) === (after > 0)) {
      magnitude = distance(before, after);
    } else {
      var size = Math.max(Math.abs(before), Math.abs(after));
      magnitude = size ? Math.abs(after - before) / size : 0;
    }
    return [rank, -magnitude];
  }

  function compareKeys(a, b) {
    for (var i = 0; i < Math.min(a.length, b.length); i++) {
      if (a[i] < b[i]) return -1;
      if (a[i] > b[i]) return 1;
    }
    return a.length - b.length;
  }

  // what a page needs of a file before it shows anything
  function checkShape(d) {
    if (!d || typeof d !== 'object') return 'not a diagnostics file';
    if (d.format !== FORMAT) {
      return typeof d.format === 'string' && d.format.indexOf('sentier-diagnostics/') === 0
        ? 'format ' + d.format + ': this page shows ' + FORMAT + ' only'
        : 'not a diagnostics file of format ' + FORMAT;
    }
    var needed = ['tier', 'audience', 'title', 'item', 'indicators', 'rule', 'states', 'steps', 'counts',
      'attribution', 'items', 'items_count', 'explanations', 'notes'];
    for (var i = 0; i < needed.length; i++) {
      if (!(needed[i] in d)) return 'the file has no ' + needed[i];
    }
    var lists = ['indicators', 'states', 'steps', 'items', 'explanations', 'notes'];
    for (var j = 0; j < lists.length; j++) {
      if (!Array.isArray(d[lists[j]])) return 'the ' + lists[j] + ' of the file are not a list';
    }
    var tables = ['item', 'rule', 'counts', 'attribution', 'items_count'];
    for (var k = 0; k < tables.length; k++) {
      if (!d[tables[k]] || typeof d[tables[k]] !== 'object' || Array.isArray(d[tables[k]])) return 'the ' + tables[k] + ' of the file is not a table';
    }
    if (!d.indicators.length) return 'the file has no indicator';
    if (d.indicator !== undefined && d.indicator !== null && !(d.indicator && typeof d.indicator.one === 'string' &&
        typeof d.indicator.many === 'string')) return 'the indicator word of the file is not {one, many}';
    if (d.steps.length !== d.states.length - 1) return 'the file has not one step fewer than states';
    if (!d.counts.steps || !d.counts.total) return 'the counts of the file are not {steps, total}';
    if (d.ranges !== undefined) {
      if (!Array.isArray(d.ranges)) return 'the ranges of the file are not a list';
      if (!d.counts.ranges || typeof d.counts.ranges !== 'object') return 'the file has ranges and no counts of them';
      for (var r = 0; r < d.ranges.length; r++) {
        var one = d.ranges[r];
        if (!one || typeof one.id !== 'string' || !Array.isArray(one.steps) || one.steps.length < 2 || !d.counts.ranges[one.id]) return 'a range of the file is not {id, steps, from, to, tolerance} with its counts';
      }
    }
    return null;
  }

  // one item's results from a matrix row, each `=` written out as the result before it;
  // null where a `=` stands first in an indicator or after a missing result
  function expandValues(values, ns) {
    var out = [];
    for (var i = 0; i < values.length; i++) {
      var v = values[i];
      if (v === SAME) {
        if (i % ns === 0 || out[i - 1] === null) return null;
        v = out[i - 1];
      }
      out.push(v);
    }
    return out;
  }

  function sameList(a, b) {
    if (!Array.isArray(a) || a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }

  // what a page needs of a matrix before it draws a row of it: that it is of the file the
  // page shows, and that every row has the shape the format gives. Its codes are not worked
  // out again here: `sentier-diagnostics check` does that.
  function checkMatrix(m, d) {
    if (!m || typeof m !== 'object') return 'not a matrix';
    if (m.format !== MATRIX_FORMAT) return 'not a matrix of format ' + MATRIX_FORMAT;
    var of = m.of || {};
    var ids = d.indicators.map(function (i) { return i.id; });
    if (of.title !== d.title || !sameList(of.states, d.states.map(function (s) { return s.id; })) ||
        !sameList(of.indicators, ids) || !sameList(of.steps, d.steps.map(function (s) { return s.id; })) ||
        !sameList(of.ranges, (d.ranges || []).map(function (r) { return r.id; }))) {
      return 'it is the matrix of another file: its title, states, indicators, steps or ranges differ';
    }
    if (!Array.isArray(m.items) || m.items.length > MATRIX_MAX_ITEMS) return 'its items are not a list of at most ' + groupThousands(MATRIX_MAX_ITEMS);
    var n = m.items.length;
    if (d.matrix && d.matrix.items !== n) return 'the file says ' + d.matrix.items + ' items, the matrix holds ' + n;
    var claimed = d.steps.some(function (s) { return !!s.claim; });
    if (!Array.isArray(m.values) || m.values.length !== n || !Array.isArray(m.classes) || m.classes.length !== n) return 'its values or classes are not one row per item';
    if (claimed ? !Array.isArray(m.verdicts) || m.verdicts.length !== n : m.verdicts !== null) return 'its verdicts are not one row per item, or null where no step has a claim';
    var ns = d.states.length, nk = d.steps.length, ni = ids.length, nc = nk + 1 + (d.ranges || []).length;
    for (var at = 0; at < n; at++) {
      var row = m.items[at];
      if (!Array.isArray(row) || row.length !== 5 || typeof row[0] !== 'string' || typeof row[1] !== 'string') return 'item ' + at + ' is not [id, name, place, group, unit]';
      var values = m.values[at];
      if (!Array.isArray(values) || values.length !== ni * ns) return 'item ' + row[0] + ': not one result per indicator and state';
      for (var v = 0; v < values.length; v++) if (values[v] !== null && values[v] !== SAME && (typeof values[v] !== 'number' || !isFinite(values[v]))) return 'item ' + row[0] + ': a result that is not a number';
      if (!expandValues(values, ns)) return 'item ' + row[0] + ': "=" first in ' + 'an indicator, or after a missing result';
      var codes = m.classes[at];
      if (typeof codes !== 'string' || codes.length !== ni * nc) return 'item ' + row[0] + ': not one class code per indicator and comparison';
      for (var c = 0; c < codes.length; c++) if (!CODES.hasOwnProperty(codes[c])) return 'item ' + row[0] + ': an unknown class code';
      if (claimed) {
        var said = m.verdicts[at];
        if (typeof said !== 'string' || said.length !== ni * nk) return 'item ' + row[0] + ': not one verdict code per indicator and step';
        for (var s = 0; s < said.length; s++) if (said[s] !== NO_CLAIM && !VERDICT_CODES.hasOwnProperty(said[s])) return 'item ' + row[0] + ': an unknown verdict code';
      }
    }
    return null;
  }

  // the rows of a checked matrix, in the shape of a listed item: values, classes, directions
  // and verdicts per indicator. A listed item keeps its own record beside the row.
  function matrixRows(m, d) {
    var ids = d.indicators.map(function (i) { return i.id; });
    var ns = d.states.length, nk = d.steps.length, nc = nk + 1 + (d.ranges || []).length;
    var listed = {};
    d.items.forEach(function (item) { listed[item.id] = item; });
    return m.items.map(function (row, at) {
      var out = { id: row[0], name: row[1], place: row[2], group: row[3], unit: row[4], values: {}, classes: {}, directions: {},
        bands: null, verdicts: m.verdicts ? {} : null, item: listed[row[0]] || null };
      var values = expandValues(m.values[at], ns);
      ids.forEach(function (id, x) {
        out.values[id] = values.slice(x * ns, (x + 1) * ns);
        var codes = m.classes[at].slice(x * nc, (x + 1) * nc).split('');
        out.classes[id] = codes.map(function (c) { return CODES[c][0]; });
        out.directions[id] = codes.map(function (c) { return CODES[c][1]; });
        if (m.verdicts) {
          out.verdicts[id] = m.verdicts[at].slice(x * nk, (x + 1) * nk).split('').map(function (c) { return c === NO_CLAIM ? null : VERDICT_CODES[c]; });
        }
      });
      if (out.item) out.bands = out.item.bands;
      return out;
    });
  }

  function listedRow(item) {
    return { id: item.id, name: item.name, place: item.place, group: item.group, unit: item.unit, values: item.values,
      classes: item.classes, directions: item.directions, bands: item.bands, verdicts: item.verdicts, item: item };
  }

  // ------------------------------------------------------------------ one mounted page

  function mount(root, given) {
    if (!root || root.getAttribute('data-sd-mounted') !== null) return null;
    root.setAttribute('data-sd-mounted', '');
    given = given || {};
    var doc = root.ownerDocument || global.document;
    var win = global;
    var standalone = root.getAttribute('data-sd-standalone') !== null;
    var base = root.getAttribute('data-sd-base') || '';

    var D = null, B = {}, LISTED = [], M = null;
    var matrix = { state: 'none', said: '' };
    var view = { comp: null, picked: [], anchor: null, several: false, notice: '', worstN: 20, worstIndicator: '', find: '', cls: '', verdict: '', group: '', limit: PAGE, size: 0, sort: 'worst', open: null, distScale: 'card' };
    var lastFocus = null;

    function q(name) { return root.querySelector('[data-sd="' + name + '"]'); }
    function el(tag, props, children) {
      var node = doc.createElement(tag);
      if (props) {
        Object.keys(props).forEach(function (key) {
          var value = props[key];
          if (value === null || value === undefined || value === false) return;
          if (key === 'text') node.textContent = value;
          else if (key === 'cls') node.className = value;
          else if (key === 'style') node.setAttribute('style', value);
          else node.setAttribute(key, value === true ? '' : value);
        });
      }
      (children || []).forEach(function (child) {
        if (child === null || child === undefined) return;
        node.appendChild(typeof child === 'string' ? doc.createTextNode(child) : child);
      });
      return node;
    }
    function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
    function n(x) { return x === null || x === undefined ? '—' : groupThousands(x); }
    function many(count) { return count === 1 ? D.item.one : D.item.many; }
    function capital(text) { return text.charAt(0).toUpperCase() + text.slice(1); }
    function article(word) { return (/^[aeiou]/i.test(word) ? 'an ' : 'a ') + word; }

    function indicatorName(id) {
      for (var i = 0; i < D.indicators.length; i++) {
        if (D.indicators[i].id === id) return D.indicators[i].short || D.indicators[i].name;
      }
      return id;
    }
    function indicatorIds() { return D.indicators.map(function (i) { return i.id; }); }
    // the comparisons of a file, in the order an item lists them: each step, the whole way,
    // then each range (a run of steps compared as one: the state before its first step
    // against the state after its last)
    function ranges() { return D.ranges || []; }
    function rangeAt(id) {
      var all = ranges();
      for (var j = 0; j < all.length; j++) if (all[j].id === id) return j;
      return -1;
    }
    function stepIndex(comp) { // the position of a comparison in an item's lists of classes
      if (comp === 'total') return D.steps.length;
      for (var i = 0; i < D.steps.length; i++) if (D.steps[i].id === comp) return i;
      var j = rangeAt(comp);
      return j >= 0 ? D.steps.length + 1 + j : D.steps.length;
    }
    function isComp(comp) {
      if (comp === 'total' || rangeAt(comp) >= 0) return true;
      return D.steps.some(function (s) { return s.id === comp; });
    }
    // the states (their positions) a comparison at position k of an item's lists compares
    function stateEnds(k) {
      var nk = D.steps.length;
      if (k < nk) return [k, k + 1];
      if (k === nk) return [0, D.states.length - 1];
      var run = runOf(ranges()[k - nk - 1].id);
      return [run[0], run[1] + 1];
    }
    // the steps (their positions, first and last) a comparison takes in
    function runOf(comp) {
      if (comp === 'total') return [0, D.steps.length - 1];
      var j = rangeAt(comp);
      if (j < 0) { var k = stepIndex(comp); return [k, k]; }
      var first = stepIndex(ranges()[j].steps[0]);
      return [first, first + ranges()[j].steps.length - 1];
    }
    // the comparison of the steps a to b: one step, the whole way, or a range the file has;
    // null where its producer did not compare those steps together
    function compOfRun(a, b) {
      if (a === b) return D.steps[a].id;
      if (a === 0 && b === D.steps.length - 1) return 'total';
      var id = D.steps[a].id + '..' + D.steps[b].id;
      var j = rangeAt(id);
      return j >= 0 && sameList(ranges()[j].steps, D.steps.slice(a, b + 1).map(function (s) { return s.id; })) ? id : null;
    }
    function blocksOf(comp) {
      if (comp === 'total') return D.counts.total;
      return rangeAt(comp) >= 0 ? D.counts.ranges[comp] : D.counts.steps[comp];
    }
    // which runs the file compares, in words, for a page that is asked for one it has not
    function rangesSaid() {
      var all = ranges();
      // a file made before ranges, and one whose writer asked for none, are said apart
      if (!('ranges' in D)) return 'This file was made before runs of steps could be compared: choose one step, or the whole way.';
      if (!all.length) return 'This file compares no run of steps: none was asked for when it was made. Choose one step, or the whole way.';
      var lo = D.steps.length, hi = -1, counted = {};
      all.forEach(function (r) { var run = runOf(r.id); lo = Math.min(lo, run[0]); hi = Math.max(hi, run[1]); counted[run[0] + ':' + run[1]] = true; });
      var every = true;
      for (var a = lo; a <= hi; a++) for (var b = a + 1; b <= hi; b++) if (!(a === 0 && b === D.steps.length - 1) && !counted[a + ':' + b]) every = false;
      return every
        ? 'It compares every run of steps within steps ' + stepNo(lo) + ' to ' + stepNo(hi) + '.'
        : 'It compares ' + groupThousands(all.length) + ' runs of steps, chosen by its writer, within steps ' + stepNo(lo) + ' to ' + stepNo(hi) + '.';
    }
    function stateIndex(stateId) {
      for (var i = 0; i < D.states.length; i++) if (D.states[i].id === stateId) return i;
      return 0;
    }
    function compLabel(comp) {
      if (comp === 'total') return 'The whole way: ' + D.states[0].label + ' → ' + D.states[D.states.length - 1].label;
      if (rangeAt(comp) >= 0) {
        var run = runOf(comp);
        return 'Steps ' + stepNo(run[0]) + ' to ' + stepNo(run[1]) + ' together: ' + D.states[run[0]].label + ' → ' + D.states[run[1] + 1].label;
      }
      var k = stepIndex(comp);
      return 'Step ' + stepNo(k) + ': ' + D.steps[k].label;
    }
    // a step's number: from 0 where the chain starts from the published results (step 0
    // checks they are reproduced), from 1 otherwise
    function stepNo(k) { return k + (D.states[0].kind === 'published' ? 0 : 1); }
    // what the file calls an indicator: its own word, or "indicator"
    function indWord(many) {
      var word = D.indicator || { one: 'indicator', many: 'indicators' };
      return many ? word.many : word.one;
    }
    function pairOf(row, indicator, k) {
      var values = row.values[indicator], ends = stateEnds(k);
      return [values[ends[0]], values[ends[1]]];
    }
    function verdictOf(row, indicator, k) {
      if (!row.verdicts || k >= D.steps.length) return null;
      return row.verdicts[indicator][k];
    }
    function bandAt(row, indicator, k) {
      if (row.bands) return row.bands[indicator][k];
      var pair = pairOf(row, indicator, k);
      return bandOf(pair[0], pair[1], row.classes[indicator][k], row.directions[indicator][k]);
    }

    // the rows the grid and the worst list draw from: every item once the matrix is loaded,
    // the listed items before
    function rows() { return M || LISTED; }
    function rowById(id) {
      var all = rows();
      for (var i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
      return null;
    }
    function heldSaid() {
      var c = D.items_count;
      if (M) return 'all ' + groupThousands(M.length) + ' ' + many(M.length) + ' (the matrix)';
      return 'the ' + groupThousands(c.listed) + ' ' + many(c.listed) + ' in this file' +
        (c.not_listed ? '; ' + groupThousands(c.not_listed) + ' more worth a look are not in it' : '');
    }

    function valueCell(row, indicator, k, ratio) {
      var pair = pairOf(row, indicator, k);
      var cls = row.classes[indicator][k];
      var v = (ratio ? ratioView : cellView)(pair[0], pair[1], cls, row.directions[indicator][k], bandAt(row, indicator, k));
      var verdict = verdictOf(row, indicator, k);
      var title = v.title + (verdict ? ' Verdict: ' + verdict + '.' : '');
      var classes = 'cell tone-' + v.tone + (v.noRatio ? ' no-ratio' : '');
      var td = el('td', { cls: classes, title: title, style: v.strength ? '--s:' + v.strength : null, 'data-class': cls },
        [v.text, v.mark ? el('span', { cls: 'mark', text: v.mark, 'aria-hidden': 'true' }) : null]);
      if (verdict && LOOK.indexOf(verdict) >= 0) td.appendChild(el('span', { cls: 'mark verdict-look', text: LOOK_MARK[verdict], title: verdict }));
      return td;
    }

    function legend(node, ratio) {
      clear(node);
      // short words beside each key, the whole sentence in its title
      var keys = [
        ['tone-up', ratio ? '1.3' : 'up', 'up', 'went up (as signed numbers)'],
        ['tone-down', ratio ? '0.77' : 'down', 'down', 'went down (as signed numbers): two results below zero that go further below zero went down'],
        ['tone-up no-ratio', '0 →', 'no ratio', 'from zero, to zero or across zero: no ratio'],
        ['tone-none', ratio ? '1.00' : '=', 'agrees', 'agrees within the tolerance' + (ratio ? ': no tint' : '')],
        ['tone-noise', ratio ? '1.00~' : '~', 'noise', 'within the measured noise'],
        ['tone-near', '≈ 0', 'near zero', 'near zero on both sides'],
        ['tone-missing', 'missing', '', 'a side has no result']
      ];
      keys.forEach(function (k) {
        node.appendChild(el('span', { title: k[3] }, [el('span', { cls: 'key ' + k[0], style: '--s:0.7', text: k[1] }), k[2]]));
      });
      node.appendChild(el('span', { title: 'verdicts worth a look' }, ['■ not claimed ◐ off claim ○ claimed, not moved']));
    }

    // the file's own word for an item, in the page's own sentences
    function sayWords() {
      var spans = root.querySelectorAll('[data-sd-word]');
      var words = { one: D.item.one, many: D.item.many, indicator: indWord(false), indicators: indWord(true), Indicator: capital(indWord(false)) };
      for (var i = 0; i < spans.length; i++) {
        var said = words[spans[i].getAttribute('data-sd-word')];
        if (said !== undefined) spans[i].textContent = said;
      }
      q('grid-region').setAttribute('aria-label', 'After divided by before, per ' + D.item.one + ' and ' + indWord(false));
      q('item-close').setAttribute('aria-label', 'Close the ' + D.item.one);
    }

    function renderHeader() {
      sayWords();
      if (standalone) doc.title = D.title;
      q('title').textContent = D.title;
      q('about').textContent = D.about || '';
      var states = clear(q('states'));
      D.states.forEach(function (s) {
        var identity = Object.keys(s.identity).map(function (k) { return k + ': ' + s.identity[k]; }).join(', ');
        var join = s.join ? n(s.join.compared) + ' compared, ' + n(s.join.unmatched) + ' unmatched, ' + n(s.join.ambiguous) + ' ambiguous' : '';
        states.appendChild(el('li', { title: (s.about || '') + (identity ? ' (' + identity + ')' : '') + (s.join && s.join.note ? ' ' + s.join.note : '') },
          [s.label + (s.kind === 'published' ? ' (published)' : ''), join ? el('span', { cls: 'sd-quiet', text: ' · ' + join }) : null]));
      });
      tierSaid();
      q('audience').textContent = D.audience === 'local'
        ? 'Local file: its writer has not said that it may be published.' : '';
      q('audience').hidden = D.audience !== 'local';
      // only a chain that starts from the published results has a step 0 that reproduces them
      q('steps-zero').hidden = D.states[0].kind !== 'published';
      q('made-by').textContent = 'Written by ' + D.made_by + '. ' + FORMAT + '.';
      renderChips();
      renderStepSaid();
    }

    // the comparison is chosen from a row of chips: the whole way, then each step with its
    // number, the values that moved in it and a mark for each verdict worth a look. Several
    // steps chosen together are a run, its chips pressed; a step taken in only because it lies
    // between two chosen ones is marked so (`markChips`)
    function renderChips() {
      var row = clear(q('comparison'));
      var chip = function (value, parts, title) {
        row.appendChild(el('button', { type: 'button', cls: 'sd-chip', 'data-comp': value, title: title,
          'aria-pressed': view.comp === value ? 'true' : 'false' }, parts));
      };
      var count = function (comp) {
        var m = sumOver(comp, moved);
        return el('span', { cls: 'sd-chip-count', text: n(m) + ' moved' });
      };
      chip('total', [el('span', { cls: 'sd-chip-label', text: 'The whole way' }), count('total')], compLabel('total'));
      D.steps.forEach(function (s, k) {
        var parts = [el('span', { cls: 'sd-chip-no', text: String(stepNo(k)) }), el('span', { cls: 'sd-chip-label', text: s.label }), count(s.id)];
        var said = [compLabel(s.id), n(sumOver(s.id, moved)) + ' values moved'];
        if (!s.explained) {
          parts.push(el('span', { cls: 'sd-chip-flag', text: '!' }));
          said.push('nothing explains it');
        }
        if (s.claim) LOOK.forEach(function (name) {
          var found = sumOver(s.id, function (b) { return b.verdicts[name]; });
          if (!found) return;
          parts.push(el('span', { cls: 'sd-chip-mark', text: LOOK_MARK[name] }));
          said.push(n(found) + ' ' + name);
        });
        chip(s.id, parts, said.join('. ') + '.');
      });
      var pick = q('pick');
      if (pick) {
        pick.hidden = !ranges().length;
        q('pick-several').checked = view.several;
        pickSaid();
      }
      markChips();
    }
    function pickSaid() {
      var node = q('pick-said');
      if (node) node.textContent = view.several
        ? 'A click adds a step to those chosen, or takes one off at an end; the steps between are taken in.'
        : 'Shift-click a second step to see the steps from one to the other together; ⌘- or Ctrl-click adds a step or takes one off.';
    }

    // what a step claims, who claimed it, and what the claim found in that step: every verdict
    // on a move, "as claimed" first, each with its count; the ones worth a look carry their
    // mark, as on the chips. No colour: a verdict is not an approval (ADR 0010).
    // each verdict on a step's moves with its count, the ones with none left out
    function verdictsOf(s) {
      return ['as claimed'].concat(LOOK).map(function (name) { return [name, sumOver(s.id, function (b) { return b.verdicts[name]; })]; })
        .filter(function (p) { return p[1]; });
    }

    function claimParts(s) {
      if (!s.claim) return [el('span', { cls: 'sd-quiet', text: 'none: what moves here is counted, not judged.' })];
      var claim = [s.claim.text, ' ', badge(s.claim.by)];
      var found = verdictsOf(s);
      claim.push(el('span', { cls: 'sd-verdicts', text: found.length
        ? ' ' + found.map(function (p) { return n(p[1]) + ' ' + (p[1] === 1 ? 'value' : 'values') + ' ' + (p[0] === 'as claimed' ? 'moved as claimed' : p[0]) + (LOOK_MARK[p[0]] ? ' ' + LOOK_MARK[p[0]] : ''); }).join(', ') + '.'
        : ' Nothing moved, as claimed.' }));
      if (s.claim.scope.some(function (e) { return e.items === null; })) {
        claim.push(el('span', { cls: 'sd-quiet', text: ' Its list of ' + D.item.many + ' is not in this file' + (s.claim.reach !== null ? ' (' + n(s.claim.reach) + ')' : '') + ': its verdicts were worked out by its writer.' }));
      }
      return claim;
    }

    function stepList(ks) {
      var nos = ks.map(function (k) { return String(stepNo(k)); });
      return nos.length === 1 ? nos[0] : nos.slice(0, -1).join(', ') + ' and ' + nos[nos.length - 1];
    }

    // under the chips: what the chosen comparison is, the claim of its step and who made it,
    // and its rule, so that a reviewer reads what a step said beside what it did. For a run of
    // steps: what they did together, each step's claim with what it found in that step alone
    function renderStepSaid() {
      var node = q('step-said');
      if (!node) return;
      clear(node);
      if (view.notice) node.appendChild(el('p', { cls: 'sd-notice', text: view.notice }));
      if (view.comp === 'total') {
        node.appendChild(el('p', null, [el('strong', { text: 'The whole way: ' }), D.states[0].label + ' → ' + D.states[D.states.length - 1].label + '. ',
          el('span', { cls: 'sd-quiet', text: 'Each cell holds the last result divided by the first. Choose a step to see what one change did' +
            (ranges().length ? ', or several to see what they did together' : '') + '; "Steps and the whole way" below splits the whole difference between them.' })]));
        return;
      }
      var j = rangeAt(view.comp);
      if (j >= 0) { renderRunSaid(node, ranges()[j]); return; }
      var k = stepIndex(view.comp);
      var s = D.steps[k];
      var line = [el('strong', { text: 'Step ' + stepNo(k) + ': ' + s.label + '. ' }), el('span', { cls: 'sd-quiet', text: D.states[k].label + ' → ' + D.states[k + 1].label + '. ' })];
      if (s.about) line.push(el('span', { cls: 'sd-quiet', text: s.about }));
      node.appendChild(el('p', null, line));
      if (k === 0 && D.states[0].kind === 'published') {
        node.appendChild(el('p', { cls: 'sd-quiet', text: 'What moves here was not reproduced within the tolerance: the residual the chain starts from, not a regression.' }));
      }
      if (!s.explained) node.appendChild(el('p', { cls: 'sd-error', text: 'Nothing explains this step.' }));
      node.appendChild(el('p', { cls: 'sd-claim' }, [el('span', { cls: 'sd-claim-label', text: 'Claim' })].concat(claimParts(s))));
      node.appendChild(el('p', { cls: 'sd-quiet', text: 'Tolerance ' + s.tolerance.value + ' (' + s.tolerance.basis + '). Noise ' + noiseText(s.noise, indicatorIds(), indWord(true)) + '.' }));
    }

    function renderRunSaid(node, r) {
      var run = runOf(r.id);
      var between = [];
      for (var k = run[0] + 1; k < run[1]; k++) if (view.picked.indexOf(k) < 0) between.push(k);
      node.appendChild(el('p', null, [el('strong', { text: 'Steps ' + stepNo(run[0]) + ' to ' + stepNo(run[1]) + ' together. ' }),
        el('span', { cls: 'sd-quiet', text: D.states[run[0]].label + ' → ' + D.states[run[1] + 1].label + '. Each cell holds the result after the last of these steps divided by the result before the first: what they did together.' })]));
      if (between.length) {
        node.appendChild(el('p', { cls: 'sd-quiet', text: (between.length === 1 ? 'Step ' : 'Steps ') + stepList(between) + (between.length === 1 ? ' lies' : ' lie') +
          ' between the steps chosen and ' + (between.length === 1 ? 'is' : 'are') + ' taken in: each state is built on the one before it, so steps are compared together only as a run.' }));
      }
      // the steps where something moved or was judged come first; the quiet ones (a claim,
      // nothing moved, no verdict) fold into one line, each still there to open
      var list = el('ul', { cls: 'sd-claims' });
      var quiet = [], folded = el('ul', { cls: 'sd-claims' });
      for (k = run[0]; k <= run[1]; k++) {
        var s = D.steps[k];
        var alone = sumOver(s.id, moved);
        var row = el('li', null, [el('strong', { text: 'Step ' + stepNo(k) + ': ' + s.label + '. ' }),
          s.explained ? null : el('span', { cls: 'sd-error', text: 'Nothing explains it. ' }),
          el('span', { cls: 'sd-claim-label', text: 'Claim' })].concat(claimParts(s),
          [el('span', { cls: 'sd-quiet', text: ' In this step alone: ' + (alone === 1 ? '1 value' : n(alone) + ' values') + ' moved.' })]));
        if (s.claim && s.explained && !alone && !verdictsOf(s).length) { quiet.push(k); folded.appendChild(row); }
        else list.appendChild(row);
      }
      if (quiet.length < 2) { while (folded.childNodes.length) list.appendChild(folded.childNodes[0]); quiet = []; }
      if (list.childNodes.length) node.appendChild(list);
      if (quiet.length) {
        node.appendChild(el('details', { cls: 'sd-quiet-steps' }, [el('summary', { text: 'Steps ' + stepList(quiet) +
          ': nothing moved in any of them, as each claims.' }), folded]));
      }
      node.appendChild(el('p', { cls: 'sd-quiet', text: 'Tolerance ' + r.tolerance + ', the largest of these steps; no noise, and no verdict: a run is judged as the whole way is, and each claim is judged in its own step.' }));
    }

    function markChips() {
      var run = view.comp === 'total' ? null : runOf(view.comp);
      var chips = q('comparison').querySelectorAll('button[data-comp]');
      for (var i = 0; i < chips.length; i++) {
        var comp = chips[i].getAttribute('data-comp');
        var k = comp === 'total' ? -1 : stepIndex(comp);
        var on = comp === 'total' ? view.comp === 'total' : !!run && k >= run[0] && k <= run[1];
        var between = !!run && on && k > run[0] && k < run[1] && view.picked.indexOf(k) < 0;
        chips[i].setAttribute('aria-pressed', on ? 'true' : 'false');
        chips[i].className = 'sd-chip' + (between ? ' sd-between' : '');
        if (between) chips[i].setAttribute('data-between', '');
        else if (chips[i].removeAttribute) chips[i].removeAttribute('data-between');
      }
    }

    // what the page holds of the items: the listed ones, or every one once the matrix is here
    function tierSaid() {
      var c = D.items_count;
      var head = groupThousands(c.all) + ' ' + D.item.many + ', ' + D.indicators.length + ' ' + indWord(D.indicators.length !== 1) + '. ';
      var said;
      if (D.tier === 'counts') said = 'This file holds counts only: no single ' + D.item.one + ' is shown.';
      else if (M) said = 'All ' + groupThousands(M.length) + ' are loaded from the matrix; ' + groupThousands(c.listed) + ' of the ' +
        groupThousands(c.qualifying) + ' worth a look are listed in this file.';
      else said = groupThousands(c.listed) + ' of the ' + groupThousands(c.qualifying) + ' ' + D.item.many + ' worth a look are in this file' +
        (c.not_listed ? '; ' + groupThousands(c.not_listed) + ' are not.' : '.');
      q('tier').textContent = head + said;
    }

    function sumOver(comp, fn) {
      var blocks = blocksOf(comp);
      return Object.keys(blocks).reduce(function (acc, key) { return acc + fn(blocks[key]); }, 0);
    }
    function moved(block) { return MOVES.reduce(function (a, k) { return a + block.classes[k]; }, 0); }

    function renderSteps() {
      var table = clear(q('steps-table'));
      var head = ['#', 'Step', 'Kind', 'Explained', 'Claim', 'Moved', 'Up', 'Down', 'As claimed', 'Off claim', 'Not claimed', 'Claimed, not moved', 'Within noise', 'Missing before', 'Missing after', 'Tolerance', 'Noise'];
      table.appendChild(el('thead', null, [el('tr', null, head.map(function (h) { return el('th', { scope: 'col', text: h }); }))]));
      var body = el('tbody');
      D.steps.forEach(function (s, k) {
        var verdict = function (name) { return s.claim ? n(sumOver(s.id, function (b) { return b.verdicts[name]; })) : '—'; };
        var noise = noiseText(s.noise, indicatorIds(), indWord(true));
        // the step from the published results: what moved there is the residual the chain
        // starts from, not a regression, whatever its claim says
        var unrepro = sumOver(s.id, moved);
        var residual = k === 0 && D.states[0].kind === 'published'
          ? (unrepro === 1 ? '1 value' : n(unrepro) + ' values') + ' not reproduced within the tolerance: the residual the chain starts from, not a regression.' : null;
        body.appendChild(el('tr', null, [
          el('td', { cls: 'num', text: String(stepNo(k)) }),
          el('td', null, [safeLink(s.link) ? el('a', { href: safeLink(s.link), text: s.label }) : s.label, s.about ? el('div', { cls: 'sd-quiet', text: s.about }) : null,
            residual ? el('div', { cls: 'sd-quiet', text: residual }) : null]),
          el('td', { text: s.kind }),
          el('td', { text: s.explained ? 'yes' : 'no: nothing explains it', cls: s.explained ? null : 'sd-error' }),
          el('td', null, [s.claim ? s.claim.text : 'no claim', s.claim && s.claim.by ? el('div', null, [badge(s.claim.by)]) : null,
            s.claim && s.claim.scope.some(function (e) { return e.items === null; })
              ? el('div', { cls: 'sd-quiet', text: 'Its list of ' + D.item.many + ' is not in this file' + (s.claim.reach !== null ? ' (' + n(s.claim.reach) + ')' : '') + ': the verdicts were worked out by its writer and cannot be checked again here.' }) : null]),
          el('td', { cls: 'num', text: n(sumOver(s.id, moved)) }),
          el('td', { cls: 'num', text: n(sumOver(s.id, function (b) { return b.directions.up; })) }),
          el('td', { cls: 'num', text: n(sumOver(s.id, function (b) { return b.directions.down; })) }),
          el('td', { cls: 'num', text: verdict('as claimed') }),
          el('td', { cls: 'num', text: verdict('off claim') }),
          el('td', { cls: 'num', text: verdict('not claimed') }),
          el('td', { cls: 'num', text: verdict('claimed, not moved') }),
          el('td', { cls: 'num', text: verdict('within noise') }),
          el('td', { cls: 'num', text: n(sumOver(s.id, function (b) { return b.missing.before + b.missing.both; })) }),
          el('td', { cls: 'num', text: n(sumOver(s.id, function (b) { return b.missing.after + b.missing.both; })) }),
          el('td', { cls: 'num', text: String(s.tolerance.value), title: s.tolerance.basis + (s.tolerance.note ? ': ' + s.tolerance.note : '') }),
          el('td', { text: noise })
        ]));
      });
      table.appendChild(body);

      var total = clear(q('total-table'));
      q('total-heading').textContent = 'The whole way: ' + D.states[0].label + ' → ' + D.states[D.states.length - 1].label;
      var classes = Object.keys(D.counts.total[D.indicators[0].id].classes);
      var cols = [capital(indWord(false))].concat(classes, ['Up', 'Down', 'Largest step', 'Spread over steps', 'Not attributable', 'Moved by what nothing explains']);
      total.appendChild(el('thead', null, [el('tr', null, cols.map(function (h) { return el('th', { scope: 'col', text: h, title: SAID[h] || null }); }))]));
      var tbody = el('tbody');
      D.indicators.forEach(function (ind) {
        var block = D.counts.total[ind.id];
        var att = D.attribution[ind.id];
        var ranked = Object.keys(att.dominant).filter(function (k) { return att.dominant[k]; })
          .sort(function (a, b) { return att.dominant[b] - att.dominant[a]; })
          .map(function (k) { return D.steps[stepIndex(k)].label + ' (' + att.dominant[k] + ')'; });
        var row = [el('th', { scope: 'row', text: ind.name + (ind.unit ? ' (' + ind.unit + ')' : '') })];
        classes.forEach(function (c) {
          var title = c === 'missing' ? 'missing before: ' + block.missing.before + ', after: ' + block.missing.after + ', on both sides: ' + block.missing.both : null;
          row.push(el('td', { cls: 'num' + (block.classes[c] ? '' : ' zero'), text: n(block.classes[c]), title: title }));
        });
        row.push(el('td', { cls: 'num', text: n(block.directions.up) }), el('td', { cls: 'num', text: n(block.directions.down) }));
        row.push(el('td', { cls: 'sd-wide', text: ranked.join(', ') || 'none' }));
        row.push(el('td', { cls: 'num', text: n(att.spread), title: 'its total moved, and no single step moved it: small steps that add up' }));
        row.push(el('td', { cls: 'num', text: n(att.not_attributable), title: 'its total moved, and it has no result in a state between: its difference cannot be split' }));
        row.push(el('td', { cls: 'num', text: n(att.unexplained_moved), title: 'moved in a step that no cause explains' }));
        tbody.appendChild(el('tr', null, row));
      });
      total.appendChild(tbody);
    }

    // the bars of a distribution, left to right: across zero, down from far to near, the
    // band around 1 (agrees, within noise), up from near to far, then the values with no
    // ratio. [kind, key, tone]
    function distBins(block) {
      var bands = Object.keys(block.bands);
      return [['class', 'sign change', 'aside']]
        .concat(bands.filter(function (b) { return b.indexOf('down') === 0; }).map(function (b) { return ['band', b, 'down']; }))
        .concat([['class', 'agrees', 'mid'], ['class', 'within noise', 'mid']])
        .concat(bands.filter(function (b) { return b.indexOf('up') === 0; }).map(function (b) { return ['band', b, 'up']; }))
        .concat(['zero reference', 'zero result', 'near zero', 'missing'].map(function (c) { return ['class', c, 'aside']; }));
    }
    // the words under a histogram, each under its run of bars
    function axis(bins) {
      var runs = [];
      bins.forEach(function (b, i) {
        var last = runs[runs.length - 1];
        if (last && last.tone === b[2] && !(b[2] === 'aside' && i > 0 && bins[i - 1][2] !== 'aside')) last.n += 1;
        else runs.push({ tone: b[2], n: 1, first: !runs.length });
      });
      var words = { down: '↓ ÷10', mid: '1', up: '×10 ↑' };
      return el('div', { cls: 'sd-axis', 'aria-hidden': 'true' }, runs.map(function (run) {
        var word = run.tone === 'aside' ? (run.first ? '±' : '0 ∅') : words[run.tone];
        return el('span', { cls: 'sd-axis-' + run.tone, style: 'flex-grow:' + run.n, text: word });
      }));
    }
    function distLegend() {
      var node = clear(q('dist-legend'));
      [['down', 'went down'], ['mid', 'agrees or within noise (the band around 1)'], ['up', 'went up'], ['aside', 'across zero, from or to zero, near zero, missing: no ratio']].forEach(function (k) {
        node.appendChild(el('span', null, [el('span', { cls: 'sd-bin-key ' + k[0] }), k[1]]));
      });
    }
    function binWords(bin) {
      if (bin[0] === 'band') return bin[1];
      return bin[1] + (SAID[bin[1]] ? ' (' + SAID[bin[1]] + ')' : '');
    }

    // after ÷ before at its 10th, 50th and 90th percentile, over the values of one indicator
    // that have a ratio (the same sign on both sides, neither zero nor near it). Only from
    // every item: the listed ones are the furthest apart, and would make a median of them
    // say more than the whole holds.
    function quantiles(indicator, k) {
      var held = M || (D.items_count.listed === D.items_count.all && D.tier !== 'counts' ? LISTED : null);
      if (!held) return null;
      var found = [];
      held.forEach(function (row) {
        var cls = row.classes[indicator][k];
        if (RATIO_CLASSES.indexOf(cls) < 0) return;
        var pair = pairOf(row, indicator, k);
        if (pair[0] === null || pair[1] === null || pair[0] === 0 || pair[1] === 0 || (pair[0] > 0) !== (pair[1] > 0)) return;
        var r = pair[1] / pair[0];
        if (isFinite(r)) found.push(r);
      });
      if (!found.length) return { n: 0 };
      found.sort(function (a, b) { return a - b; });
      var at = function (p) { // linear between the two nearest ranks
        var x = p * (found.length - 1), lo = Math.floor(x), hi = Math.ceil(x);
        return found[lo] + (found[hi] - found[lo]) * (x - lo);
      };
      return { n: found.length, p10: at(0.1), median: at(0.5), p90: at(0.9) };
    }

    // the card of the indicator the matrix is sorted by is marked, wherever the sort was chosen
    function markChosenCard() {
      var cards = q('dist-cards').childNodes;
      for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        var chosen = card.getAttribute('data-indicator') === view.sort;
        card.className = card.className.replace(/ sd-chosen/g, '') + (chosen ? ' sd-chosen' : '');
        var button = card.childNodes[0].childNodes[0];
        button.setAttribute('aria-pressed', chosen ? 'true' : 'false');
      }
    }

    // one card per indicator, in the order of the matrix's columns: a histogram of the classes
    // and bands of the comparison chosen above, each card on the scale of its own tallest bar
    function renderDistributions() {
      var comp = view.comp;
      var k = stepIndex(comp);
      var blocks = blocksOf(comp);
      var held = M || (D.items_count.listed === D.items_count.all && D.tier !== 'counts');
      q('dist-said').textContent = 'How many ' + D.item.many + ' fall in each band of after ÷ before, in the comparison chosen above, one card per ' + indWord(false) +
        ' in the order of the matrix: from across zero, through down by more than ten times, the band around 1 (dark), to up by more than ten times; then the values with no ratio. ' +
        (view.distScale === 'one' ? 'Every card is drawn on one scale, the share of all values, so that a bar of one height means as many in each; ' :
          'Each card is drawn on the scale of its own tallest bar, so that a few values that moved are seen beside many that agree; ') + 'a bar\'s title holds its count. ' +
        (held ? 'The median and percentiles are of after ÷ before over every ' + D.item.one + ' with a ratio, in as many digits as keep apart the ones that differ. '
          : 'The median and percentiles need every ' + D.item.one + ', and this page holds the ' + groupThousands(D.items_count.listed) + ' listed, the furthest apart: it gives none. ') +
        'Choose a card to sort the matrix by that ' + indWord(false) + '.';
      var box = clear(q('dist-cards'));
      var countsOf = function (block) {
        return distBins(block).map(function (b) { return (b[0] === 'band' ? block.bands[b[1]] : block.classes[b[1]]) || 0; });
      };
      // on one scale: the largest share of any bar of any card is the full height
      var topShare = 0;
      D.indicators.forEach(function (ind) {
        var block = blocks[ind.id];
        if (block.pairs) topShare = Math.max(topShare, Math.max.apply(null, countsOf(block)) / block.pairs);
      });
      columns(comp).forEach(function (c) {
        var ind = c.ind, block = blocks[ind.id];
        var bins = distBins(block);
        var counts = countsOf(block);
        var top = view.distScale === 'one' ? Math.max(1e-12, topShare) * block.pairs : Math.max.apply(null, counts.concat([1]));
        var said = bins.map(function (b, i) { return b[1] + ': ' + groupThousands(counts[i]); }).join('; ');
        var bars = bins.map(function (b, i) {
          return el('span', { cls: 'sd-bin ' + b[2] + (i && bins[i - 1][2] !== b[2] && (b[2] === 'aside' || bins[i - 1][2] === 'aside') ? ' sd-gap' : ''),
            style: 'height:' + (counts[i] ? Math.max(2, 100 * counts[i] / top).toFixed(1) : 0) + '%',
            title: binWords(b) + ': ' + groupThousands(counts[i]) + ' of ' + groupThousands(block.pairs) });
        });
        var qs = quantiles(ind.id, k);
        var meta = c.active ? capital(activeSaid(c)) + ', of ' + groupThousands(block.pairs) : 'Nothing moved';
        var said3 = qs && qs.n ? quantileTexts(qs) : null;
        var left = qs ? block.pairs - qs.n : 0;
        var stats = qs === null ? null : (said3
          ? 'Median of ' + groupThousands(qs.n) + ' ' + (qs.n === 1 ? 'ratio' : 'ratios') + ' ' + said3[1] + ', 10th percentile ' + said3[0] + ', 90th ' + said3[2] +
            (left ? '; ' + groupThousands(left) + ' without a ratio' : '')
          : 'No value with a ratio');
        var button = el('button', { type: 'button', cls: 'sd-dist-pick', 'aria-pressed': view.sort === ind.id ? 'true' : 'false',
          title: 'Sort the matrix by ' + ind.name }, [ind.name]);
        button.addEventListener('click', function () {
          view.sort = view.sort === ind.id ? 'worst' : ind.id;
          view.limit = PAGE;
          renderGrid();
          markChosenCard();
          var region = q('grid-region');
          if (region && region.scrollIntoView) region.scrollIntoView({ block: 'start', behavior: 'smooth' });
        });
        box.appendChild(el('div', { cls: 'sd-dist' + (c.active ? '' : ' sd-still') + (view.sort === ind.id ? ' sd-chosen' : ''), 'data-indicator': ind.id }, [
          el('h4', null, [button]),
          el('p', { cls: 'sd-top', 'aria-hidden': 'true', text: view.distScale === 'one'
            ? 'full height: ' + groupThousands(Math.round(top)) + ' of ' + groupThousands(block.pairs)
            : 'tallest bar: ' + groupThousands(Math.max.apply(null, counts)) }),
          el('div', { cls: 'sd-hist', role: 'img', 'aria-label': said }, bars),
          axis(bins),
          el('p', { cls: 'sd-dist-meta' }, [el('strong', { text: meta }), stats ? el('br') : null, stats])
        ]));
      });
    }

    function sizeSaid() {
      return view.size ? ' Only changes by a factor of at least ' + view.size + ' are shown, with every zero, sign change and missing value: a filter of yours, which changes no count.' : '';
    }

    function renderWorst() {
      var k = stepIndex(view.comp);
      var found = [];
      rows().forEach(function (row) {
        D.indicators.forEach(function (ind) {
          if (view.worstIndicator && ind.id !== view.worstIndicator) return;
          var cls = row.classes[ind.id][k];
          if (QUIET.indexOf(cls) >= 0) return;
          if (!sizeAtLeast(cls, bandAt(row, ind.id, k), view.size)) return;
          var pair = pairOf(row, ind.id, k);
          found.push({ row: row, ind: ind.id, key: severityKey(pair[0], pair[1], cls).concat([row.id, ind.id]) });
        });
      });
      found.sort(function (a, b) { return compareKeys(a.key, b.key); });
      var shown = found.slice(0, view.worstN);
      q('worst-said').textContent = D.tier === 'counts'
        ? 'This file holds counts only: it names no ' + D.item.one + '.'
        : 'Showing ' + shown.length + ' of the ' + groupThousands(found.length) + ' values that moved or are missing in ' + compLabel(view.comp) +
          ', among ' + heldSaid() + '. Ordered by class (sign change, zero reference, zero result, beyond 10x, differs, missing), then by how far the two sizes lie apart.' + sizeSaid();
      var table = clear(q('worst-table'));
      var head = ['#', capital(D.item.one), capital(indWord(false)), 'Class', 'Before', 'After', 'Change', 'Verdict'];
      table.appendChild(el('thead', null, [el('tr', null, head.map(function (h) { return el('th', { scope: 'col', text: h }); }))]));
      var body = el('tbody');
      shown.forEach(function (one, i) {
        var pair = pairOf(one.row, one.ind, k);
        body.appendChild(el('tr', { cls: 'sd-row', tabindex: '0', 'data-item': one.row.id }, [
          el('td', { cls: 'num', text: String(i + 1) }),
          el('td', { text: one.row.name + (one.row.place ? ' (' + one.row.place + ')' : '') }),
          el('td', { text: indicatorName(one.ind) }),
          el('td', { text: one.row.classes[one.ind][k] }),
          el('td', { cls: 'num', text: formatNumber(pair[0]), title: String(pair[0]) }),
          el('td', { cls: 'num', text: formatNumber(pair[1]), title: String(pair[1]) }),
          valueCell(one.row, one.ind, k, false),
          el('td', { text: verdictOf(one.row, one.ind, k) || '—' })
        ]));
      });
      table.appendChild(body);
    }

    function gridRows() {
      var k = stepIndex(view.comp);
      var find = view.find.toLowerCase();
      var ids = indicatorIds();
      var found = rows().filter(function (row) {
        if (find && (row.name + ' ' + (row.place || '') + ' ' + row.id).toLowerCase().indexOf(find) < 0) return false;
        if (view.group && row.group !== view.group) return false;
        if (view.cls && !ids.some(function (id) { return row.classes[id][k] === view.cls; })) return false;
        if (view.verdict && !ids.some(function (id) { return verdictOf(row, id, k) === view.verdict; })) return false;
        if (view.size && !ids.some(function (id) { return QUIET.indexOf(row.classes[id][k]) < 0 && sizeAtLeast(row.classes[id][k], bandAt(row, id, k), view.size); })) return false;
        return true;
      });
      var keyed = found.map(function (row, at) {
        if (view.sort === 'name') return { row: row, key: [row.name.toLowerCase(), row.place || '', at] };
        if (view.sort === 'worst') return { row: row, key: worstKey(row, k, ids).concat([at]) };
        var pair = pairOf(row, view.sort, k);
        return { row: row, key: severityKey(pair[0], pair[1], row.classes[view.sort][k]).concat([at]) };
      });
      keyed.sort(function (a, b) { return compareKeys(a.key, b.key); });
      return keyed.map(function (one) { return one.row; });
    }

    // where a row stands when the grid opens: the largest factor between its two results over
    // every indicator, among the values that moved and have a ratio, the furthest from 1
    // first; a row whose moves have no ratio (from or to zero, a sign change) follows, by its
    // worst value as severityKey orders values; a row that did not move comes last. Kept on
    // the row per comparison.
    function worstKey(row, k, ids) {
      if (row.worst && row.worst.k === k) return row.worst.key;
      var furthest = 0, worst = null;
      ids.forEach(function (id) {
        var pair = pairOf(row, id, k), cls = row.classes[id][k];
        if (cls === 'differs' || cls === 'beyond 10x') furthest = Math.max(furthest, distance(pair[0], pair[1]));
        var one = severityKey(pair[0], pair[1], cls);
        if (worst === null || compareKeys(one, worst) < 0) worst = one;
      });
      var key = [-furthest].concat(worst);
      row.worst = { k: k, key: key };
      return key;
    }

    // a heading sorts by itself; a second click goes back to the furthest apart first
    function sortButton(label, key, title) {
      var button = el('button', { type: 'button', cls: 'sd-sort', text: label, title: title });
      button.addEventListener('click', function () {
        view.sort = view.sort === key ? 'worst' : key;
        view.limit = PAGE;
        renderGrid();
        markChosenCard();
      });
      return button;
    }

    // the columns of the matrix: the indicators in which the comparison moved most first, so
    // that what a step did is in view without scrolling; the file's order among equals, and
    // an indicator in which nothing moved last, quietened
    function columns(comp) {
      var blocks = blocksOf(comp);
      // a missing value is a finding, not stillness: it counts with what moved
      return D.indicators.map(function (ind, at) {
        var block = blocks[ind.id];
        return { ind: ind, moved: moved(block), missing: block.classes.missing || 0, at: at };
      }).map(function (c) { c.active = c.moved + c.missing; return c; })
        .sort(function (a, b) { return b.active - a.active || a.at - b.at; });
    }

    function activeSaid(c) {
      if (!c.active) return 'nothing moved and nothing is missing';
      return [c.moved ? groupThousands(c.moved) + ' moved' : null, c.missing ? groupThousands(c.missing) + ' missing' : null].filter(Boolean).join(', ');
    }

    function renderGrid() {
      var k = stepIndex(view.comp);
      var cols = columns(view.comp);
      var found = gridRows();
      var shown = found.slice(0, view.limit);
      q('grid-said').textContent = D.tier === 'counts'
        ? 'This file holds counts only: it names no ' + D.item.one + '.'
        : 'Showing ' + groupThousands(shown.length) + ' of ' + groupThousands(found.length) + ' ' + many(found.length) +
          (M ? '' : ', among ' + heldSaid()) + '.' + sizeSaid();
      q('grid-region').setAttribute('aria-label', 'After divided by before, per ' + D.item.one + ' and ' + indWord(false) + ': ' + compLabel(view.comp) +
        (view.sort === 'worst' ? ', the furthest apart first' : ''));
      var table = clear(q('grid-table'));
      var sorted = function (key) { return view.sort === key ? (key === 'name' ? 'ascending' : 'descending') : null; };
      var head = [
        el('th', { scope: 'col', cls: 'sd-name', 'aria-sort': sorted('name') }, [sortButton(capital(D.item.one), 'name', 'Sort by name')]),
        el('th', { scope: 'col', cls: 'sd-group', text: 'Group' })
      ];
      cols.forEach(function (c) {
        var ind = c.ind;
        head.push(el('th', { scope: 'col', cls: 'num' + (c.active ? '' : ' sd-still'), 'aria-sort': sorted(ind.id),
          title: ind.name + (ind.unit ? ' (' + ind.unit + ')' : '') + ': ' + activeSaid(c) + ' here' },
          [sortButton(indicatorName(ind.id), ind.id, 'Sort by how far the two lie apart, the furthest first')]));
      });
      table.appendChild(el('thead', null, [el('tr', null, head)]));
      var body = el('tbody');
      shown.forEach(function (row) {
        var name = row.name + (row.place ? ' (' + row.place + ')' : '');
        var cells = [
          el('th', { scope: 'row', title: name + ', per ' + (row.unit || 'unknown unit') }, [M && row.item ? el('span', { cls: 'sd-listed', title: 'listed in this file' }) : null, name]),
          el('td', { cls: 'sd-group', text: row.group || '' })
        ];
        cols.forEach(function (c) {
          var td = valueCell(row, c.ind.id, k, true);
          if (!c.active) td.className += ' sd-still';
          cells.push(td);
        });
        body.appendChild(el('tr', { cls: 'sd-row', tabindex: '0', 'data-item': row.id, 'aria-current': view.open === row.id ? 'true' : null }, cells));
      });
      table.appendChild(body);
      var more = q('grid-more');
      more.hidden = found.length <= shown.length;
      more.textContent = 'Show ' + groupThousands(Math.min(PAGE, found.length - shown.length)) + ' more';
    }

    function fillSelect(select, options, chosen) {
      clear(select);
      options.forEach(function (o) { select.appendChild(el('option', { value: o[0], text: o[1] })); });
      select.value = chosen;
    }

    function renderFilters() {
      var k = stepIndex(view.comp);
      var classes = {}, verdicts = {}, groups = {};
      var ids = indicatorIds();
      rows().forEach(function (row) {
        ids.forEach(function (id) {
          classes[row.classes[id][k]] = 1;
          var v = verdictOf(row, id, k);
          if (v) verdicts[v] = 1;
        });
        if (row.group) groups[row.group] = 1;
      });
      var any = [['', 'Any']];
      fillSelect(q('grid-class'), any.concat(Object.keys(classes).sort().map(function (c) { return [c, c]; })), view.cls);
      fillSelect(q('grid-verdict'), any.concat(Object.keys(verdicts).sort().map(function (c) { return [c, c]; })), view.verdict);
      fillSelect(q('grid-group'), any.concat(Object.keys(groups).sort().map(function (c) { return [c, c]; })), view.group);
      q('grid-verdict').disabled = !Object.keys(verdicts).length;
      fillSelect(q('worst-indicator'), [['', 'All']].concat(D.indicators.map(function (i) { return [i.id, indicatorName(i.id)]; })), view.worstIndicator);
    }

    function badge(by) {
      if (!by) return el('span', { cls: 'badge', text: 'author not said' });
      if (by.kind === 'person') return el('span', { cls: 'badge person', text: 'Person: ' + by.name });
      if (by.kind === 'code') return el('span', { cls: 'badge', text: 'Code: ' + by.name });
      if (by.kind === 'model') return el('span', { cls: 'badge model', text: 'Model: ' + by.model + ', run by ' + by.run_by + '. A claim, not checked by a person' });
      return el('span', { cls: 'badge', text: String(by.kind) });
    }

    function aboutText(about) {
      var parts = [];
      if (about.step) parts.push(about.step === 'total' ? 'the whole way' : 'step ' + stepNo(stepIndex(about.step)) + ': ' + D.steps[stepIndex(about.step)].label);
      if (about.indicator) parts.push(indicatorName(about.indicator));
      if (about.item) {
        var row = rowById(about.item);
        parts.push(row ? row.name : about.item);
      }
      return parts.length ? 'About ' + parts.join(', ') + '. ' : 'About the whole file. ';
    }

    function explanationNode(one, scope) {
      return el('li', null, [
        scope ? el('span', { cls: 'sd-scope', text: scope }) : null,
        badge(one.by), el('span', { cls: 'sd-quiet', text: aboutText(one.about) }),
        one.finding === 'none found' ? el('strong', { text: 'Looked, found no reason: ' }) : null, one.text,
        one.not_checked ? el('div', { cls: 'sd-quiet', text: 'Not checked: ' + one.not_checked }) : null,
        one.source ? el('div', { cls: 'sd-quiet' }, [safeLink(one.source.link) ? el('a', { href: safeLink(one.source.link), text: one.source.link }) : null, one.source.doc ? ' ' + one.source.doc : null]) : null
      ]);
    }

    function renderExplanations() {
      var list = clear(q('explanation-list'));
      if (!D.explanations.length) list.appendChild(el('li', { cls: 'sd-quiet', text: 'The file holds no explanation.' }));
      D.explanations.forEach(function (one) { list.appendChild(explanationNode(one)); });
    }

    function renderRule() {
      var body = clear(q('rule-body'));
      body.appendChild(el('p', null, ['Every value is put into one class by one rule, in this order: missing, near zero, agrees, within noise (both only where the two share a sign), zero reference, zero result, sign change, beyond 10x, differs. ' +
        'Direction is up where the result after is larger as a signed number, down otherwise; colour follows the direction only. ' +
        'Beyond 10x: one size more than ' + D.rule.beyond + ' times the other. The whole way is counted with a tolerance of ' + D.rule.total_tolerance + ', the largest of the steps, and no noise; ' +
        'so is a run of steps chosen together, with the largest tolerance of its steps. ' + rangesSaid() + ' ' +
        'The matrix shows the result after divided by the result before; the ratio and the strength of its colour are a display, and change no class.']));
      var stepsTable = el('table', null, [el('thead', null, [el('tr', null, ['Step', 'Tolerance', 'Basis', 'Note', 'Noise'].map(function (h) { return el('th', { scope: 'col', text: h }); }))])]);
      var tb = el('tbody');
      D.steps.forEach(function (s) {
        var noise = noiseText(s.noise, indicatorIds(), indWord(true)) + (s.noise.measured ? ': ' + Object.keys(s.noise.by).map(function (k) { return indicatorName(k) + ' ' + formatNumber(s.noise.by[k]); }).join(', ') : '');
        tb.appendChild(el('tr', null, [el('td', { text: s.label }), el('td', { cls: 'num', text: String(s.tolerance.value) }), el('td', { text: s.tolerance.basis }), el('td', { text: s.tolerance.note || '' }), el('td', { text: noise })]));
      });
      stepsTable.appendChild(tb);
      body.appendChild(el('div', { cls: 'sd-wrap' }, [stepsTable]));
      body.appendChild(el('h4', { text: 'Floors' }));
      body.appendChild(el('p', { cls: 'sd-quiet', text: 'One floor per ' + indWord(false) + ' and reference unit: ' + D.rule.floor_factor + ' times the median size of the results of ' + D.states[stateIndex(D.rule.floors_from)].label + ' in that unit, unless declared. Units are never pooled.' }));
      var floors = el('table', null, [el('thead', null, [el('tr', null, [capital(indWord(false)), 'Unit', 'Floor', 'Basis', 'From results'].map(function (h) { return el('th', { scope: 'col', text: h }); }))])]);
      var fb = el('tbody');
      D.rule.floors.forEach(function (f) {
        fb.appendChild(el('tr', null, [el('td', { text: indicatorName(f.indicator) }), el('td', { text: f.unit || 'unknown' }), el('td', { cls: 'num', text: formatNumber(f.value), title: String(f.value) }), el('td', { text: f.basis }), el('td', { cls: 'num', text: n(f.n) })]));
      });
      floors.appendChild(fb);
      body.appendChild(el('div', { cls: 'sd-wrap' }, [floors]));
      var notes = clear(q('notes'));
      D.notes.forEach(function (text) { notes.appendChild(el('li', { text: text })); });
      if (!D.notes.length) notes.appendChild(el('li', { cls: 'sd-quiet', text: 'None.' }));
    }

    // ---------------------------------------------------------------- the item drawer

    // whether a row moved in a comparison and indicator an explanation is about; an
    // explanation that names neither is about every one
    function movedUnder(row, about) {
      var ids = about.indicator ? [about.indicator] : indicatorIds();
      var ks = about.step ? [stepIndex(about.step)] : D.steps.map(function (s, k) { return k; }).concat([D.steps.length]);
      return ids.some(function (id) {
        return row.classes[id] && ks.some(function (k) { return MOVES.indexOf(row.classes[id][k]) >= 0; });
      });
    }

    function whyNode(row) {
      var list = el('ul', { cls: 'sd-why' });
      var own = D.explanations.filter(function (e) { return e.about.item === row.id; });
      var wider = D.explanations.filter(function (e) { return !e.about.item && movedUnder(row, e.about); });
      own.forEach(function (e) { list.appendChild(explanationNode(e, 'This ' + D.item.one)); });
      wider.forEach(function (e) { list.appendChild(explanationNode(e, e.about.step && e.about.indicator ? 'Its step and ' + indWord(false) : e.about.step ? 'A step it moved in' : e.about.indicator ? capital(article(indWord(false))) + ' it moved in' : 'The whole file')); });
      if (!own.length && !wider.length) {
        var any = movedUnder(row, {});
        list.appendChild(el('li', { cls: 'sd-none', text: any
          ? 'None given: no explanation in this file is about this ' + D.item.one + ', or about a step or ' + indWord(false) + ' in which it moved.'
          : 'It moved in no comparison, and no explanation in this file is about it.' }));
      }
      return list;
    }

    function itemTable(row, ind) {
      var values = row.values[ind.id];
      var first = values[0], last = values[values.length - 1];
      var totalCls = row.classes[ind.id][D.steps.length];
      var table = el('table', { 'data-indicator': ind.id }, [el('thead', null, [el('tr', null, ['Step', 'Before', 'After', 'Change', 'Verdict', 'Share of the whole difference'].map(function (h) { return el('th', { scope: 'col', text: h }); }))])]);
      var tb = el('tbody');
      var split = splitOf(values, D.steps.map(function (s) { return s.explained; }), totalCls);
      var run = view.comp === 'total' ? null : runOf(view.comp);
      D.steps.forEach(function (s, k) {
        var b = values[k], a = values[k + 1];
        var share = split.state === 'split' ? shareText(split.shares[k]) : '—';
        tb.appendChild(el('tr', { cls: run && k >= run[0] && k <= run[1] ? 'sd-in-run' : null }, [
          el('td', null, ['Step ' + stepNo(k) + ': ' + s.label, s.explained ? null : el('div', { cls: 'sd-error', text: 'nothing explains it' })]),
          el('td', { cls: 'num', text: formatNumber(b), title: String(b) }),
          el('td', { cls: 'num', text: formatNumber(a), title: String(a) }),
          valueCell(row, ind.id, k, false),
          el('td', { text: verdictOf(row, ind.id, k) || '—' }),
          el('td', { cls: 'num', text: share })
        ]));
      });
      tb.appendChild(el('tr', null, [
        el('th', { scope: 'row', text: 'The whole way' }),
        el('td', { cls: 'num', text: formatNumber(first), title: String(first) }),
        el('td', { cls: 'num', text: formatNumber(last), title: String(last) }),
        valueCell(row, ind.id, D.steps.length, false),
        el('td', { text: '—' }),
        el('td', { cls: 'num', text: splitText(split) })
      ]));
      var j = rangeAt(view.comp);
      if (j >= 0) {
        var at = D.steps.length + 1 + j, pair = pairOf(row, ind.id, at);
        tb.appendChild(el('tr', { cls: 'sd-in-run' }, [
          el('th', { scope: 'row', text: 'Steps ' + stepNo(run[0]) + ' to ' + stepNo(run[1]) + ' together' }),
          el('td', { cls: 'num', text: formatNumber(pair[0]), title: String(pair[0]) }),
          el('td', { cls: 'num', text: formatNumber(pair[1]), title: String(pair[1]) }),
          valueCell(row, ind.id, at, false),
          el('td', { text: '—' }),
          el('td', { text: '' })
        ]));
      }
      table.appendChild(tb);
      return el('div', { cls: 'sd-wrap' }, [table]);
    }

    function renderItem(id, quiet) {
      var row = rowById(id);
      var drawer = q('item');
      if (!row) { closeItem(); return; }
      if (drawer.hidden) lastFocus = doc.activeElement || null;
      view.open = row.id;
      drawer.hidden = false;
      q('item-title').textContent = row.name;
      q('item-meta').textContent = [row.id, row.place, row.group, row.unit ? 'per ' + row.unit : 'unit unknown',
        row.item ? null : 'from the matrix: not listed in this file'].filter(Boolean).join(' · ');
      var body = clear(q('item-body'));
      body.appendChild(el('h4', { text: 'Why it differs' }));
      body.appendChild(whyNode(row));
      body.appendChild(el('p', { cls: 'sd-quiet', text: 'The explanations about this ' + D.item.one + ' first, then those about a step or ' + indWord(false) + ' in which it moved: those may not be about it. An explanation is a claim; it changes no class.' }));
      // the indicators, the one whose whole way lies furthest apart first
      var last = D.steps.length;
      var order = D.indicators.slice().sort(function (a, b) {
        var pa = pairOf(row, a.id, last), pb = pairOf(row, b.id, last);
        return compareKeys(severityKey(pa[0], pa[1], row.classes[a.id][last]), severityKey(pb[0], pb[1], row.classes[b.id][last]));
      });
      order.forEach(function (ind) {
        body.appendChild(el('h4', { text: ind.name + (ind.unit ? ' (' + ind.unit + ' per ' + (row.unit || 'unit') + ')' : '') }));
        body.appendChild(itemTable(row, ind));
      });
      var named = row.item ? row.item.breakdowns || {} : {};
      Object.keys(named).forEach(function (comp) {
        var name = named[comp];
        var holder = el('div');
        body.appendChild(el('h4', { text: 'What it is made of: ' + compLabel(comp) }));
        body.appendChild(holder);
        var found = B[name];
        if (found) {
          if (breakdownFits(found, row.id, comp)) breakdownInto(holder, found);
          else holder.appendChild(el('p', { cls: 'sd-error', text: 'The breakdown ' + name + ' is of another ' + D.item.one + ' or another step: not drawn.' }));
          return;
        }
        holder.appendChild(el('p', { cls: 'sd-quiet', text: 'The breakdown ' + name + ' is not with this page.' }));
        if (safeName(name) && /^https?:$/.test(win.location.protocol)) {
          win.fetch(base + name).then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
            .then(function (data) { if (!breakdownFits(data, row.id, comp)) throw new Error(); clear(holder); breakdownInto(holder, data); })
            .catch(function () { /* the sentence above stays */ });
        }
      });
      markOpen();
      var title = q('item-title');
      if (!quiet && title.focus) title.focus();
    }

    function markOpen() {
      var table = q('grid-table');
      var trs = table.querySelectorAll ? table.querySelectorAll('tr[data-item]') : [];
      for (var i = 0; i < trs.length; i++) {
        if (trs[i].getAttribute('data-item') === view.open) trs[i].setAttribute('aria-current', 'true');
        else if (trs[i].removeAttribute) trs[i].removeAttribute('aria-current');
      }
    }

    function closeItem() {
      var drawer = q('item');
      if (!drawer || drawer.hidden) return;
      drawer.hidden = true;
      view.open = null;
      markOpen();
      if (hashParts().item) setHash({ step: view.comp });
      if (lastFocus && lastFocus.focus && root.contains && root.contains(lastFocus)) lastFocus.focus();
      lastFocus = null;
    }

    // a breakdown is drawn only under the item and the step that it breaks down
    function breakdownFits(data, itemId, comp) {
      if (!data || data.format !== 'sentier-diagnostics-breakdown/1' || data.item !== itemId) return false;
      var k = stepIndex(comp);
      var from = comp === 'total' ? D.states[0].id : D.steps[k].from;
      var to = comp === 'total' ? D.states[D.states.length - 1].id : D.steps[k].to;
      return data.from === from && data.to === to && !!data.indicators && typeof data.indicators === 'object';
    }

    function breakdownInto(holder, data) {
      Object.keys(data.indicators).forEach(function (key) {
        var entry = data.indicators[key];
        holder.appendChild(el('h4', { text: indicatorName(key) + (entry.unit ? ' (' + entry.unit + ')' : '') }));
        var table = el('table', null, [el('thead', null, [el('tr', null, ['Part', 'Kind', 'Before', 'After', 'Change'].map(function (h) { return el('th', { scope: 'col', text: h }); }))])]);
        var tb = el('tbody');
        var line = function (label, kind, pair, strong) {
          var d = pair[1] - pair[0];
          return el('tr', null, [el(strong ? 'th' : 'td', { text: label }), el('td', { text: kind || '' }),
            el('td', { cls: 'num', text: formatNumber(pair[0]), title: String(pair[0]) }),
            el('td', { cls: 'num', text: formatNumber(pair[1]), title: String(pair[1]) }),
            el('td', { cls: 'num cell ' + (d > 0 ? 'tone-up' : d < 0 ? 'tone-down' : 'tone-none'), style: '--s:0.4', text: d === 0 ? '=' : (d > 0 ? '+' : '−') + formatNumber(Math.abs(d)) })]);
        };
        entry.parts.forEach(function (p) { tb.appendChild(line(p.label, p.kind, p.values, false)); });
        tb.appendChild(line(entry.parts_not_listed ? 'The other ' + entry.parts_not_listed + ' parts' : 'No other part', '', entry.rest, false));
        tb.appendChild(line('Total', '', entry.total, true));
        table.appendChild(tb);
        holder.appendChild(el('div', { cls: 'sd-wrap' }, [table]));
        var cover = function (side) {
          var listed = entry.parts.reduce(function (a, p) { return a + p.values[side]; }, 0);
          return entry.total[side] ? shareText(listed / entry.total[side]) : 'none (the total is 0)';
        };
        holder.appendChild(el('p', { cls: 'sd-quiet', text: (entry.parts_not_listed
          ? 'The first ' + entry.parts.length + ' parts make ' + cover(0) + ' of the total before and ' + cover(1) + ' after; the other ' + entry.parts_not_listed + ' are summed in one line. '
          : 'Every part is listed. ') +
          'Parts are listed by the larger of their two sizes, so that a part large on one side only is listed. The listed parts and the others add up to the total.' }));
      });
    }

    // ---------------------------------------------------------------- the matrix

    function matrixSaid() {
      var node = q('matrix-said');
      if (!node) return;
      var c = D.items_count;
      var text = {
        none: D.tier === 'counts' ? '' : 'This file lists ' + groupThousands(c.listed) + ' of its ' + groupThousands(c.all) + ' ' + D.item.many + ' and names no matrix of every ' + D.item.one + ': the grid shows the listed ones.',
        loading: 'Loading the matrix of every ' + D.item.one + ' (' + matrix.said + '); the grid shows the listed ones until it is here.',
        loaded: 'The matrix of all ' + groupThousands(M ? M.length : 0) + ' ' + D.item.many + ' is loaded; a dot marks the ' + groupThousands(c.listed) + ' listed in this file.',
        refused: 'The matrix was not loaded: ' + matrix.said + '. The grid shows the ' + groupThousands(c.listed) + ' ' + D.item.many + ' listed in this file.'
      }[matrix.state];
      node.textContent = text;
    }

    function takeMatrix(m) {
      if (!D) return;
      var problem = checkMatrix(m, D);
      if (problem) { matrix.state = 'refused'; matrix.said = problem; matrixSaid(); return; }
      M = matrixRows(m, D);
      matrix.state = 'loaded';
      matrix.said = '';
      view.limit = PAGE;
      tierSaid();
      renderComparison();
      matrixSaid();
      if (view.open) renderItem(view.open);
      else route();
    }

    function refuseMatrix(said) { matrix.state = 'refused'; matrix.said = said; matrixSaid(); }

    // the matrix comes after the page is drawn: from a global, or from the file the root or
    // the diagnostics file names, as a script beside the page (which opens from disk too) or
    // as JSON over http
    function loadMatrix() {
      if (given.matrix) { takeMatrix(given.matrix); return; }
      if (win.SENTIER_DIAGNOSTICS_MATRIX) { takeMatrix(win.SENTIER_DIAGNOSTICS_MATRIX); return; }
      var name = root.getAttribute('data-sd-matrix') || (D.matrix ? D.matrix.file : null);
      if (!name || D.tier === 'counts') { matrixSaid(); return; }
      if (!safeName(name)) { refuseMatrix('its name is not a plain file name beside the page'); return; }
      matrix.state = 'loading';
      matrix.said = name;
      matrixSaid();
      if (/\.js$/.test(name)) {
        var script = doc.createElement('script');
        script.setAttribute('src', base + name);
        script.onload = function () {
          if (win.SENTIER_DIAGNOSTICS_MATRIX) takeMatrix(win.SENTIER_DIAGNOSTICS_MATRIX);
          else refuseMatrix(name + ' holds no matrix');
        };
        script.onerror = function () { refuseMatrix(name + ' is not beside the page'); };
        (doc.head || doc.body || root).appendChild(script);
        return;
      }
      if (!/^https?:$/.test(win.location.protocol)) {
        refuseMatrix(name + ' is read over http only; `sentier-diagnostics page` writes it beside the page as a script, which opens from disk');
        return;
      }
      win.fetch(base + name).then(function (r) {
        if (!r.ok) throw new Error(name + ' could not be read (' + r.status + ')');
        return r.text();
      }).then(function (text) {
        if (text.length > MATRIX_MAX_BYTES) throw new Error(name + ' is larger than ' + groupThousands(MATRIX_MAX_BYTES) + ' bytes');
        var m;
        try { m = JSON.parse(text); } catch (error) { throw new Error(name + ' is not JSON'); }
        takeMatrix(m);
      }).catch(function (error) { refuseMatrix(error.message || (name + ' could not be read')); });
    }

    // ---------------------------------------------------------------- drawing a file

    function renderComparison() {
      renderFilters();
      renderDistributions();
      renderWorst();
      renderGrid();
    }

    // a file the page cannot draw draws nothing: not even the part it drew before it failed
    function refuse(problem) {
      D = null; M = null; LISTED = [];
      if (standalone) doc.title = 'Diagnostics';
      ['title', 'about', 'tier', 'audience', 'unchecked', 'matrix-said'].forEach(function (name) {
        var node = q(name);
        if (node) node.textContent = '';
      });
      ['audience', 'unchecked', 'item'].forEach(function (name) { if (q(name)) q(name).hidden = true; });
      if (q('states')) clear(q('states'));
      showLoad();
      q('content').hidden = true;
      q('load-error').textContent = problem;
    }

    // `checked`: the file came with the page, which `sentier-diagnostics page` writes only
    // after the validator passed it. A file chosen here or named in the address was not
    // checked: the page checks its shape only, and says so above everything it draws.
    function show(data, checked) {
      var problem = checkShape(data);
      if (problem) { refuse(problem); return; }
      D = data;
      M = null;
      LISTED = D.items.map(listedRow);
      matrix = { state: 'none', said: '' };
      view.comp = 'total';
      view.limit = PAGE;
      q('load').hidden = true;
      q('content').hidden = false;
      var unchecked = q('unchecked');
      if (unchecked) {
        unchecked.hidden = !!checked;
        unchecked.textContent = checked ? '' : 'Opened in the browser: this page checked the shape of the file, not its counts. ' +
          'Run sentier-diagnostics check on it before relying on what it shows.';
      }
      try {
        renderHeader();
        renderSteps();
        renderExplanations();
        renderRule();
        legend(q('grid-legend'), true);
        distLegend();
        renderComparison();
        matrixSaid();
        route();
      } catch (error) {
        refuse('The file is JSON of the right format, but a part of it is missing or not what the format says (' + error.message + '). Run sentier-diagnostics check on it.');
        return;
      }
      if (checked) loadMatrix();
    }

    // the address holds the chosen step and the open item, `#step=<id>&item=<id>`, each
    // optional, so that a reviewer can send someone to exactly what they look at
    function hashParts() {
      var out = {};
      (win.location.hash || '').slice(1).split('&').forEach(function (part) {
        var at = part.indexOf('=');
        if (at > 0) out[part.slice(0, at)] = decodeURIComponent(part.slice(at + 1));
      });
      return out;
    }
    function setHash(parts) {
      var said = [];
      if (parts.step && parts.step !== 'total') said.push('step=' + encodeURIComponent(parts.step));
      if (parts.item) said.push('item=' + encodeURIComponent(parts.item));
      var wanted = said.join('&');
      if ((win.location.hash || '').replace(/^#/, '') === wanted) return false;
      if (wanted) win.location.hash = wanted;
      else if (win.history && win.history.replaceState) win.history.replaceState(null, '', win.location.pathname + win.location.search);
      return true;
    }

    // every step of the steps a to b
    function stepsFrom(a, b) {
      var out = [];
      for (var k = a; k <= b; k++) out.push(k);
      return out;
    }

    // `picked`: the steps chosen by hand, of a run; the others of it lie between. Without
    // it, a new comparison has every step of it picked and the same one keeps what it had
    function choose(comp, picked) {
      var same = comp === view.comp;
      if (picked) view.picked = picked;
      else if (!same) view.picked = comp === 'total' ? [] : stepsFrom(runOf(comp)[0], runOf(comp)[1]);
      view.comp = comp;
      markChips();
      renderStepSaid();
      if (same) return;
      view.cls = ''; view.verdict = ''; view.limit = PAGE; view.sort = 'worst';
      renderComparison();
      if (view.open) renderItem(view.open, true);
    }

    // a click on a step's chip ("one"): that step alone. "to" (Shift): every step from the one
    // chosen before to this one. "toggle" (⌘ or Ctrl, or a plain click with "Several steps"
    // on): the chosen steps grown to this one or, where it is an end of them, shrunk by it;
    // what lies between steps chosen apart is taken in, and the step line says so. A run the
    // file does not compare is said, and nothing changes.
    function pick(k, how) {
      var run = view.comp === 'total' ? null : runOf(view.comp);
      var a = k, b = k, picked = [k];
      if (how === 'to' && view.anchor !== null) {
        a = Math.min(view.anchor, k); b = Math.max(view.anchor, k); picked = stepsFrom(a, b);
      } else if (how === 'toggle' && run) {
        if (k < run[0] || k > run[1]) {
          a = Math.min(run[0], k); b = Math.max(run[1], k); picked = view.picked.concat([k]);
        } else if (run[0] === run[1]) {
          view.notice = ''; view.anchor = null;
          choose('total');
          setHash({ step: view.comp, item: view.open });
          return;
        } else if (k === run[0] || k === run[1]) {
          a = k === run[0] ? k + 1 : run[0]; b = k === run[1] ? k - 1 : run[1];
          picked = view.picked.filter(function (x) { return x !== k; });
        } else {
          view.notice = 'Step ' + stepNo(k) + ' lies inside the steps ' + stepNo(run[0]) + ' to ' + stepNo(run[1]) + ', which are compared as a whole: take off a step at one of their ends, or click a step alone.';
          renderStepSaid();
          return;
        }
      }
      var comp = compOfRun(a, b);
      if (comp === null) {
        view.notice = 'Steps ' + stepNo(a) + ' to ' + stepNo(b) + ' together are not compared in this file. ' + rangesSaid();
        renderStepSaid();
        return;
      }
      view.notice = '';
      if (how === 'one' || view.anchor === null) view.anchor = k;
      choose(comp, picked.filter(function (x) { return x >= a && x <= b; }).concat([a, b]));
      setHash({ step: view.comp, item: view.open });
    }

    // what the page says of an address that names no comparison of this file
    function unknownSaid(said) {
      for (var a = 0; a < D.steps.length; a++) {
        for (var b = a + 1; b < D.steps.length; b++) {
          if (D.steps[a].id + '..' + D.steps[b].id === said) {
            return 'The address asks for steps ' + stepNo(a) + ' to ' + stepNo(b) + ' together, which this file does not compare. ' + rangesSaid() + ' The whole way is shown.';
          }
        }
      }
      return 'The address asks for "' + said + '", which is no step and no run of steps of this file. The whole way is shown.';
    }

    function route() {
      if (!D) return;
      var parts = hashParts();
      var said = parts.step || 'total';
      var step = isComp(said) ? said : 'total';
      view.notice = step === said ? '' : unknownSaid(said);
      if (step !== view.comp) view.anchor = step === 'total' ? null : runOf(step)[0];
      choose(step);
      if (parts.item) renderItem(parts.item);
      else closeItem();
    }

    function openFrom(event) {
      var row = event.target.closest ? event.target.closest('tr[data-item]') : null;
      if (!row) return;
      var id = row.getAttribute('data-item');
      if (!setHash({ step: view.comp, item: id })) renderItem(id);
    }

    function readScript(name) {
      var node = q(name);
      if (!node || !node.textContent || !/\S/.test(node.textContent)) return undefined;
      return JSON.parse(node.textContent);
    }

    function start() {
      q('comparison').addEventListener('click', function (e) {
        var chip = e.target.closest ? e.target.closest('button[data-comp]') : null;
        if (!chip || !D) return;
        var comp = chip.getAttribute('data-comp');
        if (comp === 'total') {
          view.notice = ''; view.anchor = null;
          choose('total');
          setHash({ step: view.comp, item: view.open });
          return;
        }
        pick(stepIndex(comp), e.shiftKey ? 'to' : e.metaKey || e.ctrlKey || view.several ? 'toggle' : 'one');
      });
      // the arrow keys move between the chips; with Shift they grow or shrink the run at the
      // end away from where it started
      q('comparison').addEventListener('keydown', function (e) {
        if (!D || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
        var step = e.key === 'ArrowRight' ? 1 : -1;
        var comps = ['total'].concat(D.steps.map(function (s) { return s.id; }));
        var to;
        if (e.shiftKey && view.comp !== 'total') {
          var run = runOf(view.comp);
          var k = (view.anchor === run[0] ? run[1] : run[0]) + step;
          if (k < 0 || k >= D.steps.length) return;
          pick(k, 'to');
          to = D.steps[k].id;
        } else {
          var at = (view.comp === 'total' ? 0 : 1 + runOf(view.comp)[step > 0 ? 1 : 0]) + step;
          if (at < 0 || at >= comps.length) return;
          to = comps[at];
          if (to === 'total') { view.anchor = null; view.notice = ''; choose('total'); setHash({ step: view.comp, item: view.open }); }
          else pick(stepIndex(to), 'one');
        }
        if (e.preventDefault) e.preventDefault();
        var next = q('comparison').querySelector('button[data-comp="' + to + '"]');
        if (next && next.focus) next.focus();
      });
      if (q('pick-several')) {
        q('pick-several').addEventListener('change', function (e) { view.several = !!e.target.checked; pickSaid(); });
      }
      q('size').addEventListener('change', function (e) { view.size = +e.target.value; view.limit = PAGE; renderWorst(); renderGrid(); });
      q('worst-n').addEventListener('change', function (e) { view.worstN = +e.target.value; renderWorst(); });
      q('dist-scale').addEventListener('change', function (e) { view.distScale = e.target.value === 'one' ? 'one' : 'card'; renderDistributions(); });
      q('worst-indicator').addEventListener('change', function (e) { view.worstIndicator = e.target.value; renderWorst(); });
      q('grid-find').addEventListener('input', function (e) { view.find = e.target.value; view.limit = PAGE; renderGrid(); });
      q('grid-class').addEventListener('change', function (e) { view.cls = e.target.value; view.limit = PAGE; renderGrid(); });
      q('grid-verdict').addEventListener('change', function (e) { view.verdict = e.target.value; view.limit = PAGE; renderGrid(); });
      q('grid-group').addEventListener('change', function (e) { view.group = e.target.value; view.limit = PAGE; renderGrid(); });
      q('grid-more').addEventListener('click', function () { view.limit += PAGE; renderGrid(); });
      q('item-close').addEventListener('click', closeItem);
      root.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeItem(); });
      ['grid-table', 'worst-table'].forEach(function (name) {
        q(name).addEventListener('click', openFrom);
        q(name).addEventListener('keydown', function (e) { if (e.key === 'Enter') openFrom(e); });
      });
      win.addEventListener('hashchange', route);
      q('file').addEventListener('change', function (e) {
        var file = e.target.files[0];
        if (!file) return;
        var reader = new win.FileReader();
        reader.onload = function () {
          var data;
          try { data = JSON.parse(reader.result); } catch (error) { refuse('The file is not JSON: ' + error.message); return; }
          show(data, false);
        };
        reader.readAsText(file);
      });
      try {
        var breakdowns = given.breakdowns || readScript('breakdowns');
        B = breakdowns || win.SENTIER_DIAGNOSTICS_BREAKDOWNS || {};
        var data = given.data || readScript('data');
        if (data === undefined) data = win.SENTIER_DIAGNOSTICS;
      } catch (error) {
        refuse('The data of this page is not JSON: ' + error.message);
        return;
      }
      if (data) { show(data, true); return; }
      var wanted = new win.URLSearchParams(win.location.search).get('file');
      if (wanted && safeName(wanted) && /\.json$/.test(wanted) && /^https?:$/.test(win.location.protocol)) {
        win.fetch(base + wanted).then(function (r) { return r.json(); }).then(function (got) { show(got, false); }, function () {
          refuse('Could not read ' + wanted + ' as JSON.');
        });
        return;
      }
      showLoad();
    }

    // the place for a file: a page of its own offers to open one; a host's page never does,
    // and shows only why nothing is drawn
    function showLoad() {
      q('load').hidden = false;
      q('load-choose').hidden = !standalone;
      if (!standalone && !q('load-error').textContent) q('load-error').textContent = 'No diagnostics file came with this page.';
    }

    start();
    return { show: show, close: closeItem, open: renderItem };
  }

  // every root of the document not yet mounted, but those a host mounts itself
  function mountAll(doc) {
    var roots = (doc || global.document).querySelectorAll('[data-sentier-diagnostics]');
    for (var i = 0; i < roots.length; i++) {
      if (roots[i].getAttribute('data-sentier-diagnostics') !== 'manual') mount(roots[i]);
    }
  }

  var api = { expandValues: expandValues, formatNumber: formatNumber, percentText: percentText, shareText: shareText, ratioText: ratioText, ratioShort: ratioShort, noiseText: noiseText,
    sizeAtLeast: sizeAtLeast, cellView: cellView, ratioView: ratioView, severityKey: severityKey, compareKeys: compareKeys,
    bandStep: bandStep, bandOf: bandOf, checkShape: checkShape, checkMatrix: checkMatrix, matrixRows: matrixRows,
    safeLink: safeLink, safeName: safeName, splitOf: splitOf, splitText: splitText, distance: distance, quantileTexts: quantileTexts, RANK: RANK,
    mount: mount, mountAll: mountAll };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else if (typeof global.document !== 'undefined') {
    global.SentierDiagnostics = api;
    if (global.document.readyState === 'loading') global.document.addEventListener('DOMContentLoaded', function () { mountAll(); });
    else mountAll();
  }
})(typeof window !== 'undefined' ? window : this);
