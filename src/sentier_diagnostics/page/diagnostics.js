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
  // what a column's heading sorts by, in the words of its title (furthestKey)
  var COLUMN_ORDER = 'Sort by this column: the moves that have no factor first (from or to zero, a sign change), then the largest factor between the two results, then the rest';
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
    var between = noise.between ? ' between ' + noise.between.join(' and ') : ' at its two states';
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

  // ------------------------------------------------------------------ steps together

  // the counting rule, as rule.judge: the class, direction and band of one pair. The page
  // judges with it only what no file holds, a run of steps, and only after it has judged each
  // step of the run again and found the file's own class on every item. Held to the Python
  // rule by the shared cases and the boundaries the Python writes (tests/test_boundaries.py).
  var BEYOND_FACTOR = 10; // rule.BEYOND_FACTOR; the validator holds every file to it
  function classify(before, after, floor, tolerance, noise) {
    if (before === null || after === null) return 'missing';
    var smallBefore = Math.abs(before) <= floor, smallAfter = Math.abs(after) <= floor;
    if (smallBefore && smallAfter) return 'near zero';
    var sameSign = (before > 0 && after > 0) || (before < 0 && after < 0);
    var size = Math.max(Math.abs(before), Math.abs(after));
    var gap = size ? Math.abs(after - before) / size : 0;
    if (sameSign && gap <= tolerance) return 'agrees';
    if (sameSign && noise && gap <= noise) return 'within noise';
    if (smallBefore) return 'zero reference';
    if (smallAfter) return 'zero result';
    if (!sameSign) return 'sign change';
    if (size > BEYOND_FACTOR * Math.min(Math.abs(before), Math.abs(after))) return 'beyond 10x';
    return 'differs';
  }
  function judge(before, after, floor, tolerance, noise) {
    var cls = classify(before, after, floor, tolerance, noise);
    var dir = MOVES.indexOf(cls) >= 0 ? (after > before ? 'up' : 'down') : null;
    return [cls, dir, bandOf(before, after, cls, dir)];
  }

  // the runs of a set of steps (their places, in order), each [first, last]
  function runsOf(set) {
    var out = [];
    set.forEach(function (k) {
      var last = out[out.length - 1];
      if (last && last[1] === k - 1) last[1] = k;
      else out.push([k, k]);
    });
    return out;
  }

  // the pair of a run of steps in one indicator, from its results over the states: the result
  // before its first step and the result after its last, two built states, never a sum. Steps
  // apart are not compared on a chain: each step was measured with every step before it
  // applied, so its difference belongs to that place in the order (SPEC section 3).
  function runPair(values, first, last) { return [values[first], values[last + 1]]; }

  // whether a file says the noise of each built state (SPEC 5.3); one made before noise
  // belonged to a state says a noise per step, never which state it was measured on. The
  // published results carry none: they are exact (fileformat.states_carry_noise)
  function statesCarryNoise(d) {
    return d.states.every(function (s) { return s.kind === 'published' || (s.noise !== undefined && s.noise !== null); });
  }

  // the noise two states are compared with, per indicator: the sum of the noise of the two,
  // since rebuilding both ends moves their difference by up to the sum of theirs. The
  // published results are exact and add nothing; an indicator measured at no end is left
  // out, not measured (fileformat.noise_of_states, summed in the same order)
  function noiseOfStates(first, last) {
    var out = {}, any = false;
    [first, last].forEach(function (s) {
      if (s.kind === 'published' || !s.noise || !s.noise.measured) return;
      any = true;
      Object.keys(s.noise.by || {}).forEach(function (key) {
        out[key] = (Object.prototype.hasOwnProperty.call(out, key) ? out[key] : 0) + s.noise.by[key];
      });
    });
    return any ? out : null;
  }

  // at how many of two ends the noise of one indicator is known: the published results
  // (exact) or a build that measured it (fileformat.ends_known)
  function endsKnown(first, last, key) {
    return [first, last].filter(function (s) {
      return s.kind === 'published' || (s.noise && s.noise.measured && Object.prototype.hasOwnProperty.call(s.noise.by || {}, key));
    }).length;
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
  // a display; the class stays the file's. A pair that moved never reads as one that agrees:
  // where three digits round its ratio to "1.00", it is written as ratioText writes it
  // ("1 + 2e−4", "1.004"), so that the text, not only the tint, says it moved.
  var RATIO_CLASSES = ['agrees', 'within noise', 'differs', 'beyond 10x'];
  function ratioView(before, after, cls, dir, band) {
    var view = cellView(before, after, cls, dir, band);
    var ratio = before !== null && after !== null && before !== 0 && after !== 0 && (before > 0) === (after > 0);
    if (ratio && RATIO_CLASSES.indexOf(cls) >= 0) {
      view.text = ratioShort(before, after);
      if (MOVES.indexOf(cls) >= 0 && view.text === '1.00') view.text = ratioText(before, after);
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

  // whether numbers add up to a total as a breakdown must: to within 1e-9 of the largest of
  // them, summed from the left (breakdown.CLOSURE and breakdown._adds_up)
  var CLOSURE = 1e-9;
  function addsUp(parts, total) {
    var size = Math.abs(total), sum = 0;
    parts.forEach(function (p) { size = Math.max(size, Math.abs(p)); sum += p; });
    return Math.abs(sum - total) <= CLOSURE * size;
  }

  function compareKeys(a, b) {
    for (var i = 0; i < Math.min(a.length, b.length); i++) {
      if (a[i] < b[i]) return -1;
      if (a[i] > b[i]) return 1;
    }
    return a.length - b.length;
  }

  // The relative luminance of a colour as CSS writes it (WCAG 2), or null where it cannot be
  // read. Hex, rgb(), oklab() and oklch() are read here: the browser gives a host's colour in
  // one of these where the host wrote it in sRGB or in OKLab (Tailwind 4 writes every colour
  // in oklch). Any other form (lab(), color() ...) is drawn on a canvas of one pixel and read
  // back. A canvas keeps its colour when it is given one it cannot read (light-dark(), a bare
  // "0 0% 100%"): set over two different colours, such a text leaves two different colours,
  // and is unknown, never black. A browser that hides what a canvas holds (against
  // fingerprinting) gives back blank or altered pixels: a known colour that does not come
  // back as it went says that nothing drawn can be read, and the colour is unknown.
  function luminance(text, doc) {
    text = String(text || '').trim();
    var rgb = null, m;
    if ((m = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(text))) {
      var h = m[1].length <= 4 ? m[1].replace(/(.)/g, '$1$1') : m[1];
      rgb = [0, 2, 4].map(function (at) { return parseInt(h.slice(at, at + 2), 16); });
    } else if ((m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(text))) {
      rgb = [+m[1], +m[2], +m[3]];
    } else if ((m = OKLAB.exec(text))) {
      return oklabLuminance(m);
    } else if (text && doc && doc.createElement) {
      try {
        var canvas = doc.createElement('canvas');
        canvas.width = canvas.height = 1;
        var context = canvas.getContext('2d');
        var taken = ['#010203', '#fdfeff'].map(function (over) {
          context.fillStyle = over; context.fillStyle = text;
          return String(context.fillStyle);
        });
        if (taken[0] !== taken[1]) return null;
        var drawn = function (fill) {
          context.clearRect(0, 0, 1, 1);
          context.fillStyle = fill;
          context.fillRect(0, 0, 1, 1);
          var d = context.getImageData(0, 0, 1, 1).data;
          return [d[0], d[1], d[2]];
        };
        if (drawn('#010203').join() !== '1,2,3') return null;
        rgb = drawn(text);
      } catch (error) { return null; }
    }
    if (!rgb || rgb.some(function (v) { return !isFinite(v); })) return null;
    var lin = rgb.map(function (v) { v = Math.min(255, v) / 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  }

  // oklab(L a b) and oklch(L C H), as CSS Color 4 writes them: L a number or a percentage of
  // 1, a, b and C a number or a percentage of 0.4, H in degrees (or deg, grad, rad, turn),
  // "none" as zero; an alpha after "/" is left aside, as rgb() leaves it
  var OKNUM = '(none|[+-]?(?:\\d+\\.?\\d*|\\.\\d+)(?:e[+-]?\\d+)?(?:%|deg|grad|rad|turn)?)';
  var OKLAB = new RegExp('^okl(ab|ch)\\(\\s*' + OKNUM + '\\s+' + OKNUM + '\\s+' + OKNUM + '\\s*(?:\\/[^)]*)?\\)$', 'i');
  var TURN = { deg: 1, grad: 0.9, rad: 180 / Math.PI, turn: 360 };
  function oklabLuminance(m) {
    function part(t, whole) {
      if (/^none$/i.test(t)) return 0;
      var unit = /[a-z%]+$/i.exec(t), v = parseFloat(t);
      if (!unit) return v;
      if (unit[0] === '%') return whole === undefined ? NaN : v / 100 * whole;
      return whole === undefined ? v * TURN[unit[0].toLowerCase()] : NaN; // an angle only in a hue
    }
    var lch = m[1].toLowerCase() === 'ch';
    var L = part(m[2], 1), a, b;
    if (lch) {
      var C = part(m[3], 0.4), hue = part(m[4]) * Math.PI / 180;
      a = C * Math.cos(hue); b = C * Math.sin(hue);
    } else {
      a = part(m[3], 0.4); b = part(m[4], 0.4);
    }
    if (![L, a, b].every(isFinite)) return null;
    // OKLab to linear sRGB (Ottosson 2020), clipped to sRGB as a canvas draws it
    var l = Math.pow(L + 0.3963377774 * a + 0.2158037573 * b, 3);
    var mm = Math.pow(L - 0.1055613458 * a - 0.0638541728 * b, 3);
    var s = Math.pow(L - 0.0894841775 * a - 1.2914855480 * b, 3);
    var lin = [
      4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * mm + 1.7076147010 * s,
    ].map(function (v) { return Math.min(1, Math.max(0, v)); });
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  }

  // Whether the host's tokens make a dark page: a light ink (whatever its ground), or a dark
  // ground where no ink can be read. A token that is no colour the page can read says
  // nothing: it is never taken for black. Light and dark part where a colour contrasts as
  // much with black as with white, at a relative luminance of about 0.179.
  var SCHEME_PARTS = Math.sqrt(1.05 * 0.05) - 0.05;

  // the keys a host may name a page by in the address (`data-sd-key`), and the page's own
  var KEY_LONGEST = 40;
  var KEY_WORD = new RegExp('^[A-Za-z][A-Za-z0-9_-]{0,' + (KEY_LONGEST - 1) + '}$');
  var OWN_KEY = /^sd[0-9]*$/i;
  function schemeIsDark(ink, surface, lum) {
    function read(text) {
      text = String(text || '').trim();
      var l = text ? lum(text) : null;
      return l === null || l === undefined || !isFinite(l) ? null : l;
    }
    var l = read(ink);
    if (l !== null) return l > SCHEME_PARTS;
    l = read(surface);
    return l !== null && l < SCHEME_PARTS;
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
    if (!Array.isArray(d.rule.floors)) return 'the floors of the file are not a list';
    var noise = d.rule.total_noise;
    if (noise !== undefined && (!noise || typeof noise !== 'object' || Array.isArray(noise) ||
        Object.keys(noise).some(function (key) { return typeof noise[key] !== 'number'; }))) return 'the noise of the whole way is not a number per indicator';
    if (noise !== undefined && !statesCarryNoise(d)) return 'the noise of the whole way is that of its first and last state, and the states of the file carry none';
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
        !sameList(of.indicators, ids) || !sameList(of.steps, d.steps.map(function (s) { return s.id; }))) {
      return 'it is the matrix of another file: its title, states, indicators or steps differ';
    }
    if (!Array.isArray(m.items) || m.items.length > MATRIX_MAX_ITEMS) return 'its items are not a list of at most ' + groupThousands(MATRIX_MAX_ITEMS);
    var n = m.items.length;
    if (d.matrix && d.matrix.items !== n) return 'the file says ' + d.matrix.items + ' items, the matrix holds ' + n;
    var claimed = d.steps.some(function (s) { return !!s.claim; });
    if (!Array.isArray(m.values) || m.values.length !== n || !Array.isArray(m.classes) || m.classes.length !== n) return 'its values or classes are not one row per item';
    if (claimed ? !Array.isArray(m.verdicts) || m.verdicts.length !== n : m.verdicts !== null) return 'its verdicts are not one row per item, or null where no step has a claim';
    var ns = d.states.length, nk = d.steps.length, ni = ids.length, nc = nk + 1;
    for (var at = 0; at < n; at++) {
      var row = m.items[at];
      if (!Array.isArray(row) || row.length !== 5 || typeof row[0] !== 'string' || typeof row[1] !== 'string') return 'item ' + at + ' is not [id, name, place, group, unit]';
      var values = m.values[at];
      if (!Array.isArray(values) || values.length !== ni * ns) return 'item ' + row[0] + ': not one result per indicator and state';
      for (var v = 0; v < values.length; v++) if (values[v] !== null && values[v] !== SAME && (typeof values[v] !== 'number' || !isFinite(values[v]))) return 'item ' + row[0] + ': a result that is not a number';
      if (!expandValues(values, ns)) return 'item ' + row[0] + ': "=" first in ' + 'an indicator, or after a missing result';
      var codes = m.classes[at];
      if (typeof codes !== 'string' || codes.length !== ni * nc) return 'item ' + row[0] + ': not one class code per indicator, step and the whole way';
      for (var c = 0; c < codes.length; c++) if (!CODES.hasOwnProperty(codes[c])) return 'item ' + row[0] + ': an unknown class code';
      if (claimed) {
        var said = m.verdicts[at];
        if (typeof said !== 'string' || said.length !== ni * nk) return 'item ' + row[0] + ': not one verdict code per indicator and step';
        for (var s = 0; s < said.length; s++) if (said[s] !== NO_CLAIM && !VERDICT_CODES.hasOwnProperty(said[s])) return 'item ' + row[0] + ': an unknown verdict code';
      }
    }
    return listedDiffer(matrixRows(m, d), d);
  }

  // A matrix says of every item this file lists what the file says: its name, place, group and
  // unit, its results, classes, directions and verdicts. A matrix left over from another run of
  // the same chain has the same title, states, steps and count, and other numbers; the page
  // would draw them in place of the file's.
  function listedDiffer(rows, d) {
    var ids = d.indicators.map(function (i) { return i.id; });
    var found = 0;
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r], item = row.item;
      if (!item) continue;
      found++;
      if (row.name !== item.name || row.place !== item.place || row.group !== item.group || row.unit !== item.unit) {
        return 'item ' + row.id + ': its name, place, group or unit differ from what this file lists';
      }
      for (var x = 0; x < ids.length; x++) {
        var id = ids[x];
        var verdicts = row.verdicts && item.verdicts ? sameList(row.verdicts[id], item.verdicts[id] || []) : !row.verdicts === !item.verdicts;
        if (!sameList(row.values[id], item.values[id] || []) || !sameList(row.classes[id], item.classes[id] || []) ||
            !sameList(row.directions[id], item.directions[id] || []) || !verdicts) {
          return 'item ' + row.id + ', ' + id + ': its results or classes differ from what this file lists for it';
        }
      }
    }
    return found === d.items.length ? null : (d.items.length - found) + ' of the items this file lists are not in it';
  }

  // the rows of a checked matrix, in the shape of a listed item: values, classes, directions
  // and verdicts per indicator. A listed item keeps its own record beside the row.
  function matrixRows(m, d) {
    var ids = d.indicators.map(function (i) { return i.id; });
    var ns = d.states.length, nk = d.steps.length, nc = nk + 1;
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

  // ------------------------------------------------------------------ what the pages share

  // A weak reference: one that lets what it names be collected once nothing else holds it.
  // Where the browser has no WeakRef, it holds what it names, as a plain reference does.
  function weakly(value) {
    var Ref = global.WeakRef;
    return typeof Ref === 'function' ? new Ref(value) : { deref: function () { return value; } };
  }

  // A function called through a weak reference, for something that outlives a page (a
  // script element left in the head) to call it: once the page is collected, the call does
  // nothing. The page holds the function itself, so that it lives as long as the page does.
  function weakCall(react) {
    var ref = weakly(react);
    return function () {
      var held = ref.deref();
      return held ? held.apply(this, arguments) : undefined;
    };
  }

  var DARK_READER = '(prefers-color-scheme: dark)';
  var WATCHED = { attributes: true, childList: true, subtree: true };

  // The listeners every page of this script shares (issue 40). A page in a host listens to
  // the window (the address), to the reader's colour scheme, and to the document and each
  // shadow root it sits in (what changes there, and what finishes loading). Were each page
  // to listen itself, the window and the document would hold every page a host removed
  // without unmount() for as long as the window is open, its file and its matrix with it, and
  // the browser would record every change to the document once for each of them, and wake
  // each of them. So there is one listener of each kind, and one observer
  // of the document, for all the pages; they hold each page weakly. A page nobody holds any
  // more (out of the document, its element and what `mount` returned dropped by the host) is
  // collected without unmount(), and the shared listeners leave it at their next call. A page
  // out of the document that its host still holds is still told, so that it works again once
  // it is put back. Once no page is left, the listeners are taken off. Where the browser has
  // no WeakRef, the pages are held until unmount(), as each page held itself before.
  var shared = null;
  function sharedListeners() {
    if (shared) return shared;
    var win = global;
    var pages = []; // a weak reference to each page that joined: {changed, look, address}
    var tops = []; // a weak reference to the document and each shadow root watched
    var observer = null, reader = null, armed = false, queued = false;
    var frame = function (f) { if (win.requestAnimationFrame) win.requestAnimationFrame(f); else f(); };
    // the pages still held; those collected are forgotten here. A page unmounted while the
    // pages are told answers nothing (released), so it may be told once more.
    function live() {
      var out = [];
      pages = pages.filter(function (ref) {
        var page = ref.deref();
        if (page) out.push(page);
        return !!page;
      });
      return out;
    }
    function settle() { if (armed && !pages.length) disarm(); }
    // a look once a frame, however much changed, for every page
    function look() {
      queued = false;
      live().forEach(function (page) { page.look(); });
      settle();
    }
    function later() { if (armed && !queued) { queued = true; frame(look); } }
    function changed() {
      live().forEach(function (page) { page.changed(); });
      later();
      settle();
    }
    function address() {
      live().forEach(function (page) { page.address(); });
      settle();
    }
    function arm() {
      if (armed) return;
      armed = true;
      if (win.addEventListener) win.addEventListener('hashchange', address);
      reader = win.matchMedia ? win.matchMedia(DARK_READER) : null;
      if (reader && reader.addEventListener) reader.addEventListener('change', later);
      if (!observer && win.MutationObserver) observer = new win.MutationObserver(changed);
    }
    function disarm() {
      armed = false;
      if (win.removeEventListener) win.removeEventListener('hashchange', address);
      if (reader && reader.removeEventListener) reader.removeEventListener('change', later);
      reader = null;
      if (observer) observer.disconnect();
      tops.forEach(function (ref) {
        var top = ref.deref();
        if (top && top.removeEventListener) top.removeEventListener('load', later, true);
      });
      tops = [];
    }
    shared = {
      // a page joins; what it is given back makes it leave
      join: function (page) {
        arm();
        var ref = weakly(page);
        pages.push(ref);
        return function () {
          pages = pages.filter(function (other) { return other !== ref; });
          settle();
        };
      },
      // a root the page sits in, watched for changes and for loads (a load does not leave a
      // shadow root) from now on, once whichever pages sit in it
      watch: function (top) {
        for (var i = 0; i < tops.length; i++) if (tops[i].deref() === top) return;
        tops = tops.filter(function (ref) { return ref.deref(); });
        tops.push(weakly(top));
        if (observer) observer.observe(top, WATCHED);
        if (top.addEventListener) top.addEventListener('load', later, true);
      }
    };
    return shared;
  }

  // ------------------------------------------------------------------ one mounted page

  function mount(root, given) {
    if (!root || root.getAttribute('data-sd-mounted') !== null) return null;
    root.setAttribute('data-sd-mounted', '');
    given = given || {};
    // the document the page lives in: its root's, but for a root a host built from a
    // <template>, whose document is inert (no window) until the host puts it in the page's
    var doc = root.ownerDocument && root.ownerDocument.defaultView ? root.ownerDocument : global.document;
    var win = global;
    var standalone = root.getAttribute('data-sd-standalone') !== null;
    var base = root.getAttribute('data-sd-base') || '';

    var D = null, B = {}, LISTED = [], M = null;
    var matrix = { state: 'none', said: '' };
    // what the grid is sorted by: the page's own orders and an indicator's column are kept in
    // two spaces, so that an indicator called "name" or "worst" is a column like any other
    var WORST = { by: 'worst' }, BY_NAME = { by: 'name' };
    function byColumn(id) { return { by: 'indicator', id: id }; }
    var view = { set: [], anchor: null, notice: '', pickOpen: false, pickFind: '', pickMoved: false, worstN: 20, worstIndicator: '', find: '', cls: '', verdict: '', group: '', limit: PAGE, size: 0, sort: WORST, open: null, distScale: 'card' };
    function sortIs(sort) { return view.sort.by === sort.by && view.sort.id === sort.id; }
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
    // ---------------------------------------------------------------- the steps chosen

    // What is compared is a run of steps, by their places in the chain: one step, every step
    // (the whole way), or a run of two or more short of every step. The file holds the first
    // two, an item's lists one entry per step and then the whole way; a run this page judges
    // from every item's results in the two states it lies between (`judgeRun`), and it stands
    // at SET, which no list of the file holds.
    var SET = -1;
    function isSet(k) { return k === SET; }
    function allSteps() { var out = []; for (var k = 0; k < D.steps.length; k++) out.push(k); return out; }
    function posOf(set) { return set.length === D.steps.length ? D.steps.length : set.length === 1 ? set[0] : SET; }
    function kNow() { return posOf(view.set); }
    // the comparison chosen as the file names its own: 'total', the id of a step, or 'set'
    function compNow() {
      var k = kNow();
      return isSet(k) ? 'set' : k === D.steps.length ? 'total' : D.steps[k].id;
    }
    function stepAt(id) {
      for (var i = 0; i < D.steps.length; i++) if (D.steps[i].id === id) return i;
      return -1;
    }
    // the place of a step, or of the whole way ('total'), in an item's lists
    function stepIndex(comp) {
      var k = comp === 'total' ? -1 : stepAt(comp);
      return k < 0 ? D.steps.length : k;
    }
    function blocksOf(comp) {
      if (comp === 'set') return C.blocks;
      return comp === 'total' ? D.counts.total : D.counts.steps[comp];
    }
    function blocksNow() { return blocksOf(compNow()); }
    function stateIndex(stateId) {
      for (var i = 0; i < D.states.length; i++) if (D.states[i].id === stateId) return i;
      return 0;
    }
    // a comparison the file holds: the whole way or one step
    function compLabel(comp) {
      if (comp === 'total') return 'The whole way: ' + D.states[0].label + ' → ' + D.states[D.states.length - 1].label;
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
    function listWords(parts) {
      return parts.length === 1 ? parts[0] : parts.slice(0, -1).join(', ') + ' and ' + parts[parts.length - 1];
    }
    // runs in words: "2, 3, 5 to 9 and 12" (a run of two is its two steps)
    function runWords(runs) {
      var parts = [];
      runs.forEach(function (r) {
        if (r[1] - r[0] === 1) parts.push(String(stepNo(r[0])), String(stepNo(r[1])));
        else parts.push(r[0] === r[1] ? String(stepNo(r[0])) : stepNo(r[0]) + ' to ' + stepNo(r[1]));
      });
      return listWords(parts);
    }
    function stepList(ks) { return runWords(ks.map(function (k) { return [k, k]; })); }
    // what a run of steps is called: "The whole way", "Step 4", "Steps 2 and 3 together",
    // "Steps 3 to 9 together"
    function setWords(set) {
      if (set.length === D.steps.length) return 'The whole way';
      if (set.length === 1) return 'Step ' + stepNo(set[0]);
      return 'Steps ' + runWords([[set[0], set[set.length - 1]]]) + ' together';
    }
    // the steps an address or a reader asked for, which need not be a run
    function askedWords(set) { return set.length === 1 ? 'step ' + stepNo(set[0]) : 'steps ' + runWords(runsOf(set)); }
    // the comparison chosen, in words for a heading or a sentence
    function nowLabel() {
      return isSet(kNow()) ? setWords(view.set) + ' (' + view.set.length + ' of ' + D.steps.length + ' steps)' : compLabel(compNow());
    }
    function clsAt(row, indicator, k) { return isSet(k) ? row.together.cls[indicator] : row.classes[indicator][k]; }
    function dirAt(row, indicator, k) { return isSet(k) ? row.together.dir[indicator] : row.directions[indicator][k]; }
    function pairOf(row, indicator, k) {
      if (isSet(k)) return row.together.pair[indicator];
      var values = row.values[indicator];
      return k === D.steps.length ? [values[0], values[values.length - 1]] : [values[k], values[k + 1]];
    }
    function verdictOf(row, indicator, k) {
      if (!row.verdicts || isSet(k) || k >= D.steps.length) return null;
      return row.verdicts[indicator][k];
    }
    function bandAt(row, indicator, k) {
      if (isSet(k)) return row.together.band[indicator];
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
      var cls = clsAt(row, indicator, k);
      var v = (ratio ? ratioView : cellView)(pair[0], pair[1], cls, dirAt(row, indicator, k), bandAt(row, indicator, k));
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
      renderPicker();
      renderStepSaid();
    }

    // ---------------------------------------------------------------- a run, judged

    // the floor of an indicator and a reference unit, as the file holds it; null where it
    // holds none, and the page then judges no run in that indicator
    var FLOORS = {};
    function floorKey(indicator, unit) { return JSON.stringify([indicator, unit === undefined ? null : unit]); }
    function floorOf(indicator, unit) {
      var key = floorKey(indicator, unit);
      return Object.prototype.hasOwnProperty.call(FLOORS, key) ? FLOORS[key] : null;
    }
    function stepNoise(s, indicator) {
      var by = s.noise && s.noise.measured ? s.noise.by || {} : {};
      return typeof by[indicator] === 'number' ? by[indicator] : null;
    }
    // every item's results, which a run of steps is judged from: the matrix, or the file
    // where it lists every item; null where the page holds only some
    function heldAll() {
      if (M) return M;
      return D.tier !== 'counts' && D.items_count.listed === D.items_count.all ? LISTED : null;
    }
    // why no run of steps can be judged now; null where one can
    function runRefused() {
      if (D.tier === 'counts') return 'This file holds counts only: a run of steps is judged from every ' + D.item.one + '\'s results, which it does not hold.';
      if (heldAll()) return null;
      var c = D.items_count;
      var need = 'A run of steps is judged from every ' + D.item.one + '\'s results';
      if (matrix.state === 'loading') return need + ': the matrix that holds them is loading.';
      if (matrix.state === 'refused') return need + ', and the matrix that holds them was not loaded (' + matrix.said + ').';
      return need + ': this file lists ' + groupThousands(c.listed) + ' of its ' + groupThousands(c.all) + ' and names no matrix of them. One step and the whole way are the file\'s own.';
    }

    // The page holds its rule to the file's before it judges a run with it: each chosen step is
    // judged again on every item, and must give the file's own class and direction every time.
    // Once per step; a step where it does not refuses every run that takes it in.
    var CHECKED = {}, C = null;
    function checkStep(k) {
      if (Object.prototype.hasOwnProperty.call(CHECKED, k)) return CHECKED[k];
      var s = D.steps[k], ids = indicatorIds(), held = heldAll(), said = null;
      for (var r = 0; r < held.length && said === null; r++) {
        var row = held[r];
        for (var x = 0; x < ids.length; x++) {
          var id = ids[x], values = row.values[id], floor = floorOf(id, row.unit);
          if (floor === null) { said = row.id + ', ' + indicatorName(id) + ': the file holds no floor for its unit'; break; }
          var got = judge(values[k], values[k + 1], floor, s.tolerance.value, stepNoise(s, id));
          if (got[0] !== row.classes[id][k] || got[1] !== row.directions[id][k]) {
            said = row.id + ', ' + indicatorName(id) + ': the file says ' + row.classes[id][k] + (row.directions[id][k] ? ', ' + row.directions[id][k] : '') +
              ', this page\'s rule ' + got[0] + (got[1] ? ', ' + got[1] : '');
            break;
          }
        }
      }
      CHECKED[k] = said;
      return said;
    }

    // a block of counts, as the file holds one per step, for a run of steps: no verdicts (each
    // claim is judged in its own step), and no closer or further, which the page shows for no
    // comparison (together.counts has them, for a reader of the file's blocks)
    function emptyBlock(indicator) {
      var like = D.counts.total[indicator];
      var zeros = function (table) { var out = {}; Object.keys(table).forEach(function (key) { out[key] = 0; }); return out; };
      return { pairs: 0, classes: zeros(like.classes), missing: zeros(like.missing), directions: zeros(like.directions), bands: zeros(like.bands),
        verdicts: null, closer: null, further: null };
    }

    // a run of steps judged over every item, with the rule of the file: its pair (the two
    // built states it lies between), its class with the largest tolerance of its steps and the
    // sum of the noise of those two states (none of a state inside it), and its counts. Kept
    // until another run is chosen.
    // Returns why it cannot be, or null.
    function judgeRun(set) {
      var key = set.join(',');
      if (C && C.key === key) return null;
      var why = runRefused();
      if (why) return why;
      for (var i = 0; i < set.length; i++) {
        var problem = checkStep(set[i]);
        if (problem) return 'This page\'s rule does not give the file\'s classes in step ' + stepNo(set[i]) + ' (' + problem + '), so it judges no run of steps that takes it in. Run sentier-diagnostics check on the file.';
      }
      var steps = set.map(function (k) { return D.steps[k]; });
      var tolerance = Math.max.apply(null, steps.map(function (s) { return s.tolerance.value; }));
      var first = set[0], last = set[set.length - 1], ids = indicatorIds();
      var noise = statesCarryNoise(D) ? noiseOfStates(D.states[first], D.states[last + 1]) || {} : {};
      var blocks = {};
      ids.forEach(function (id) { blocks[id] = emptyBlock(id); });
      heldAll().forEach(function (row) {
        var t = { key: key, cls: {}, dir: {}, band: {}, pair: {} };
        ids.forEach(function (id) {
          var values = row.values[id], pair = runPair(values, first, last);
          var got = judge(pair[0], pair[1], floorOf(id, row.unit), tolerance, Object.prototype.hasOwnProperty.call(noise, id) ? noise[id] : null);
          t.pair[id] = pair; t.cls[id] = got[0]; t.dir[id] = got[1]; t.band[id] = got[2];
          var b = blocks[id];
          b.pairs += 1;
          b.classes[got[0]] += 1;
          if (got[0] === 'missing') b.missing[pair[0] === null && pair[1] === null ? 'both' : pair[0] === null ? 'before' : 'after'] += 1;
          if (got[2]) b.bands[got[2]] += 1;
          if (got[1]) b.directions[got[1]] += 1;
        });
        row.together = t;
      });
      C = { key: key, set: set, tolerance: tolerance, noise: noise, blocks: blocks };
      return null;
    }

    // ---------------------------------------------------------------- choosing steps

    // The steps are chosen in two places that show one choice. The strip has one cell per
    // step in the order of the chain, its bar as high as what moved in that step, so that a
    // long chain fits in one line and shows where things moved. The list finds steps by
    // number, name or kind, or those where something moved. Either chooses one step, or with
    // Shift every step from the one chosen before: a run.
    function stepMoved(k) { return sumOver(D.steps[k].id, moved); }
    function looksOf(s) {
      if (!s.claim) return [];
      return LOOK.map(function (name) { return [name, sumOver(s.id, function (b) { return b.verdicts[name]; })]; }).filter(function (p) { return p[1]; });
    }
    function stepTitle(k) {
      var s = D.steps[k], m = stepMoved(k);
      var said = ['Step ' + stepNo(k) + ': ' + s.label, (m === 1 ? '1 value' : n(m) + ' values') + ' moved'];
      if (!s.explained) said.push('nothing explains it');
      looksOf(s).forEach(function (p) { said.push(n(p[1]) + ' ' + p[0]); });
      return said.join('. ') + '.';
    }
    // consecutive steps of one kind are one group of the list
    function groupsOf() {
      var out = [];
      D.steps.forEach(function (s, k) {
        var last = out[out.length - 1];
        if (last && last.kind === s.kind) last.steps.push(k);
        else out.push({ kind: s.kind, steps: [k] });
      });
      return out;
    }
    function shownInList(k) {
      var s = D.steps[k];
      if (view.pickMoved && !stepMoved(k)) return false;
      var find = view.pickFind.trim().toLowerCase();
      if (!find) return true;
      return [String(stepNo(k)), s.id, s.label, s.kind, s.about || ''].join(' ').toLowerCase().indexOf(find) >= 0;
    }

    function renderPicker() {
      var strip = clear(q('comparison'));
      var top = 0;
      D.steps.forEach(function (s, k) { top = Math.max(top, stepMoved(k)); });
      // a number under each cell where they fit; a long chain draws its cells thinner, and
      // scrolls within the strip where even those do not fit
      var numbered = D.steps.length <= 40;
      strip.className = 'sd-strip' + (numbered ? ' sd-numbered' : '') + (D.steps.length > 60 ? ' sd-dense' : '');
      strip.appendChild(el('button', { type: 'button', cls: 'sd-whole', 'data-comp': 'total', 'aria-pressed': 'false',
        title: compLabel('total') + '. ' + n(sumOver('total', moved)) + ' values moved.' }, [el('span', { text: 'The whole way' })]));
      var cells = el('span', { cls: 'sd-cells' });
      D.steps.forEach(function (s, k) {
        var m = stepMoved(k);
        var height = m ? 18 + 82 * Math.log(1 + m) / Math.log(1 + top) : 0;
        cells.appendChild(el('button', { type: 'button', cls: 'sd-cell' + (s.explained ? '' : ' sd-unexplained') + (looksOf(s).length ? ' sd-look' : ''),
          'data-comp': s.id, 'aria-pressed': 'false', title: stepTitle(k), 'aria-label': stepTitle(k) }, [
          el('span', { cls: 'sd-cell-bar' + (m ? '' : ' sd-none'), style: 'height:' + height.toFixed(1) + '%' }),
          numbered ? el('span', { cls: 'sd-cell-no', text: String(stepNo(k)) }) : null
        ]));
      });
      strip.appendChild(cells);
      var open = q('pick-open');
      if (open) open.setAttribute('aria-expanded', view.pickOpen ? 'true' : 'false');
      if (q('pick-panel')) q('pick-panel').hidden = !view.pickOpen;
      if (q('pick-moved')) q('pick-moved').checked = view.pickMoved;
      renderPickList();
    }

    function renderPickList() {
      var list = q('pick-list');
      if (!list) { markPicker(); return; }
      clear(list);
      var shown = 0;
      groupsOf().forEach(function (g) {
        var ks = g.steps.filter(shownInList);
        if (!ks.length) return;
        shown += ks.length;
        var first = g.steps[0], last = g.steps[g.steps.length - 1];
        // a group of one step is a row with its kind; a group of several has a head that
        // chooses its run
        var head = first === last ? null : el('div', { cls: 'sd-pick-group' }, [
          el('button', { type: 'button', cls: 'sd-pick-run', 'data-group': String(first), 'aria-pressed': 'false',
            title: 'Steps ' + stepNo(first) + ' to ' + stepNo(last) + ' together' }, [
            el('strong', { text: capital(g.kind) }),
            el('span', { cls: 'sd-quiet', text: ' steps ' + stepNo(first) + ' to ' + stepNo(last) })]),
          el('span', { cls: 'sd-quiet sd-pick-count', 'data-group-count': String(first) })
        ]);
        if (head) list.appendChild(head);
        ks.forEach(function (k) {
          var s = D.steps[k], m = stepMoved(k);
          list.appendChild(el('button', { type: 'button', cls: 'sd-pick-row', 'data-row': String(k), 'data-pick': String(k), 'aria-pressed': 'false',
            title: (s.about ? s.about + ' ' : '') + 'Click for this step alone, Shift-click for every step from the one chosen before.' }, [
            el('span', { cls: 'sd-pick-name' }, [
              el('span', { cls: 'sd-pick-no', text: String(stepNo(k)) }),
              el('span', { cls: 'sd-pick-label', text: s.label }),
              head ? null : el('span', { cls: 'sd-pick-kind', text: s.kind }),
              s.explained ? null : el('span', { cls: 'sd-pick-flag', text: '!', title: 'nothing explains it' })
            ]),
            el('span', { cls: 'sd-pick-moved' + (m ? '' : ' sd-quiet'), text: m ? n(m) + ' moved' : 'nothing moved' }),
            el('span', { cls: 'sd-pick-marks', text: looksOf(s).map(function (p) { return LOOK_MARK[p[0]]; }).join(' '),
              title: looksOf(s).map(function (p) { return n(p[1]) + ' ' + p[0]; }).join(', ') || null })
          ]));
        });
      });
      if (!shown) list.appendChild(el('p', { cls: 'sd-quiet', text: 'No step ' + (view.pickMoved ? 'where something moved ' : '') + (view.pickFind.trim() ? 'matches "' + view.pickFind.trim() + '"' : '') + '.' }));
      if (q('pick-shown')) q('pick-shown').textContent = shown === D.steps.length ? '' : 'Showing ' + shown + ' of ' + D.steps.length + ' steps.';
      markPicker();
    }

    // the strip, the list and the line beside them show the steps chosen
    function markPicker() {
      var whole = view.set.length === D.steps.length;
      var cells = q('comparison').querySelectorAll('button[data-comp]');
      for (var i = 0; i < cells.length; i++) {
        var comp = cells[i].getAttribute('data-comp');
        var on = comp === 'total' ? whole : view.set.indexOf(stepIndex(comp)) >= 0;
        cells[i].setAttribute('aria-pressed', on ? 'true' : 'false');
      }
      var locked = runRefused();
      var list = q('pick-list');
      if (list) {
        var rowsShown = list.querySelectorAll('button[data-pick]');
        for (var j = 0; j < rowsShown.length; j++) {
          rowsShown[j].setAttribute('aria-pressed', !whole && view.set.indexOf(+rowsShown[j].getAttribute('data-pick')) >= 0 ? 'true' : 'false');
        }
        var byFirst = {};
        groupsOf().forEach(function (g) { byFirst[g.steps[0]] = g.steps; });
        var groups = list.querySelectorAll('button[data-group]');
        for (var gi = 0; gi < groups.length; gi++) {
          var ks = byFirst[groups[gi].getAttribute('data-group')] || [];
          groups[gi].setAttribute('aria-pressed', sameList(ks, view.set) ? 'true' : 'false');
        }
        var counts = list.querySelectorAll('span[data-group-count]');
        for (var ci = 0; ci < counts.length; ci++) {
          var gs = byFirst[counts[ci].getAttribute('data-group-count')] || [];
          var chosen = whole ? 0 : gs.filter(function (x) { return view.set.indexOf(x) >= 0; }).length;
          counts[ci].textContent = chosen ? chosen + ' of ' + gs.length + ' chosen' : gs.length + ' steps';
        }
      }
      if (q('pick-locked')) { q('pick-locked').textContent = locked || ''; q('pick-locked').hidden = !locked; }
      if (q('pick-summary')) q('pick-summary').textContent = whole ? 'Every step: ' + D.steps.length
        : view.set.length + ' of ' + D.steps.length + ' steps';
    }

    // what a step claims, who claimed it, and what the claim found in that step: every verdict
    // on a move, "as claimed" first, each with its count; the ones worth a look carry their
    // mark. No colour: a verdict is not an approval (ADR 0010).
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

    // what one state's noise is: the published results are exact; a build's was measured or not
    function endSaid(s) {
      return s.label + ' ' + (s.kind === 'published' ? 'exact' : s.noise && s.noise.measured ? 'measured' : 'not measured');
    }
    // the noise two states are compared with, in words: the sum of theirs, at how many ends it
    // was measured, and its size; "not measured" where no end measured it, never "identical".
    // Null for a file whose states carry no noise.
    function pairNoiseSaid(first, last) {
      if (!statesCarryNoise(D)) return null;
      var a = D.states[first], b = D.states[last];
      var by = noiseOfStates(a, b) || {};
      var keys = Object.keys(by);
      var head = 'the sum of its two ends\' (' + endSaid(a) + ', ' + endSaid(b) + ')';
      if (!keys.length) return head + ': not measured';
      var all = indicatorIds().length;
      var known = Math.min.apply(null, keys.map(function (k) { return endsKnown(a, b, k); }));
      var largest = Math.max.apply(null, keys.map(function (k) { return by[k]; }));
      return head + (known < 2 ? ', measured at ' + known + ' of 2 ends' : '') +
        (keys.length < all ? ', for ' + keys.length + ' of ' + all + ' ' + indWord(true) + ' (not measured for the others)' : '') +
        (largest === 0 ? ': identical builds' : largest > LARGE_NOISE ? '; large: up to ' + formatNumber(largest * 100) + ' %' : '');
    }
    function totalNoiseSaid() {
      if (!('total_noise' in D.rule)) return 'none: this file was made before noise belonged to a state';
      return pairNoiseSaid(0, D.states.length - 1);
    }
    function runNoiseSaid(first, last) {
      return pairNoiseSaid(first, last + 1) || 'none: this file says the noise of each step, never of the state it was measured on, so a run of steps is compared without noise';
    }
    // a step's noise in words: that of its two states, or, in a file made before noise
    // belonged to a state, its own
    function stepNoiseSaid(k) {
      return pairNoiseSaid(k, k + 1) || noiseText(D.steps[k].noise, indicatorIds(), indWord(true));
    }

    // under the strip: what the chosen comparison is, the claim of its step and who made it,
    // and its rule, so that a reviewer reads what a step said beside what it did. For several
    // steps: what they did together, each step's claim with what it found in that step alone
    function renderStepSaid() {
      var node = q('step-said');
      if (!node) return;
      clear(node);
      if (view.notice) node.appendChild(el('p', { cls: 'sd-notice', text: view.notice }));
      var k = kNow();
      if (k === D.steps.length) {
        node.appendChild(el('p', null, [el('strong', { text: 'The whole way: ' }), D.states[0].label + ' → ' + D.states[D.states.length - 1].label + '. ',
          el('span', { cls: 'sd-quiet', text: 'Each cell holds the last result divided by the first. Choose one step to see what one change did, or any steps to see what they did together; "Steps and the whole way" below splits the whole difference between them.' })]));
        node.appendChild(el('p', { cls: 'sd-quiet', text: 'Tolerance ' + D.rule.total_tolerance + ', the largest of the steps. Noise ' + totalNoiseSaid() + '.' }));
        return;
      }
      if (isSet(k)) { renderSetSaid(node); return; }
      var s = D.steps[k];
      var line = [el('strong', { text: 'Step ' + stepNo(k) + ': ' + s.label + '. ' }), el('span', { cls: 'sd-quiet', text: D.states[k].label + ' → ' + D.states[k + 1].label + '. ' })];
      if (s.about) line.push(el('span', { cls: 'sd-quiet', text: s.about }));
      node.appendChild(el('p', null, line));
      if (k === 0 && D.states[0].kind === 'published') {
        node.appendChild(el('p', { cls: 'sd-quiet', text: 'What moves here was not reproduced within the tolerance: the residual the chain starts from, not a regression.' }));
      }
      if (!s.explained) node.appendChild(el('p', { cls: 'sd-error', text: 'Nothing explains this step.' }));
      node.appendChild(el('p', { cls: 'sd-claim' }, [el('span', { cls: 'sd-claim-label', text: 'Claim' })].concat(claimParts(s))));
      node.appendChild(el('p', { cls: 'sd-quiet', text: 'Tolerance ' + s.tolerance.value + ' (' + s.tolerance.basis + '). Noise ' + stepNoiseSaid(k) + '.' }));
    }

    function renderSetSaid(node) {
      var set = view.set, first = set[0], last = set[set.length - 1];
      node.appendChild(el('p', null, [el('strong', { text: setWords(set) + '. ' }), el('span', { cls: 'sd-quiet', text:
        D.states[first].label + ' → ' + D.states[last + 1].label + '. Each cell holds the result after the last of these steps divided by the result before the first: two built states, what the steps did together.' })]));
      // the steps where something moved or was judged come first; the quiet ones (explained,
      // nothing moved, no verdict, with a claim or without) fold into one line, each still
      // there to open: a set of hundreds of steps is mostly these
      var list = el('ul', { cls: 'sd-claims' });
      var quiet = [], folded = el('ul', { cls: 'sd-claims' });
      set.forEach(function (k) {
        var s = D.steps[k];
        var alone = stepMoved(k);
        var row = el('li', null, [el('strong', { text: 'Step ' + stepNo(k) + ': ' + s.label + '. ' }),
          s.explained ? null : el('span', { cls: 'sd-error', text: 'Nothing explains it. ' }),
          el('span', { cls: 'sd-claim-label', text: 'Claim' })].concat(claimParts(s),
          [el('span', { cls: 'sd-quiet', text: ' In this step alone: ' + (alone === 1 ? '1 value' : n(alone) + ' values') + ' moved.' })]));
        if (s.explained && !alone && !(s.claim && verdictsOf(s).length)) { quiet.push(k); folded.appendChild(row); }
        else list.appendChild(row);
      });
      if (quiet.length < 2) { while (folded.childNodes.length) list.appendChild(folded.childNodes[0]); quiet = []; }
      if (list.childNodes.length) node.appendChild(list);
      if (quiet.length) {
        var claimed = quiet.every(function (k) { return D.steps[k].claim; });
        node.appendChild(el('details', { cls: 'sd-quiet-steps' }, [el('summary', { text: 'Steps ' + runWords(runsOf(quiet)) +
          ': nothing moved in any of them' + (claimed ? ', as each claims.' : '.') }), folded]));
      }
      node.appendChild(el('p', { cls: 'sd-quiet', text: 'Tolerance ' + C.tolerance + ', the largest of these steps. Noise ' + runNoiseSaid(C.set[0], C.set[C.set.length - 1]) +
        '. No verdict: each claim is judged in its own step. This page works out the classes with the rule of the file, from the two states, after holding it to the file\'s own class of each of these steps for every ' + D.item.one + '.' }));
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
        var noise = stepNoiseSaid(k);
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
      var held = heldAll();
      if (!held) return null;
      var found = [];
      held.forEach(function (row) {
        var cls = clsAt(row, indicator, k);
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
        var chosen = sortIs(byColumn(card.getAttribute('data-indicator')));
        card.className = card.className.replace(/ sd-chosen/g, '') + (chosen ? ' sd-chosen' : '');
        var button = card.childNodes[0].childNodes[0];
        button.setAttribute('aria-pressed', chosen ? 'true' : 'false');
      }
    }

    // one card per indicator, in the order of the matrix's columns: a histogram of the classes
    // and bands of the comparison chosen above, each card on the scale of its own tallest bar
    function renderDistributions() {
      var k = kNow();
      var blocks = blocksNow();
      var held = !!heldAll();
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
      columns().forEach(function (c) {
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
        var column = byColumn(ind.id);
        var button = el('button', { type: 'button', cls: 'sd-dist-pick', 'aria-pressed': sortIs(column) ? 'true' : 'false',
          title: 'Sort the matrix by ' + ind.name }, [ind.name]);
        button.addEventListener('click', function () {
          if (released) return; // drawn by a page since unmounted: another may be mounted here
          view.sort = sortIs(column) ? WORST : column;
          view.limit = PAGE;
          renderGrid();
          markChosenCard();
          var region = q('grid-region');
          if (region && region.scrollIntoView) region.scrollIntoView({ block: 'start', behavior: 'smooth' });
        });
        box.appendChild(el('div', { cls: 'sd-dist' + (c.active ? '' : ' sd-still') + (sortIs(column) ? ' sd-chosen' : ''), 'data-indicator': ind.id }, [
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
      var k = kNow();
      var found = [];
      rows().forEach(function (row) {
        D.indicators.forEach(function (ind) {
          if (view.worstIndicator && ind.id !== view.worstIndicator) return;
          var cls = clsAt(row, ind.id, k);
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
        : 'Showing ' + shown.length + ' of the ' + groupThousands(found.length) + ' values that moved or are missing in ' + nowLabel() +
          ', among ' + heldSaid() + '. Ordered by class (sign change, zero reference, zero result, beyond 10x, differs, missing), then by how far the two sizes lie apart.' + sizeSaid();
      var table = clear(q('worst-table'));
      var head = ['#', capital(D.item.one), capital(indWord(false)), 'Class', 'Before', 'After', 'Change', 'Verdict'];
      table.appendChild(el('thead', null, [el('tr', null, head.map(function (h) { return el('th', { scope: 'col', text: h }); }))]));
      var body = el('tbody');
      shown.forEach(function (one, i) {
        var pair = pairOf(one.row, one.ind, k);
        body.appendChild(el('tr', { cls: 'sd-row', tabindex: i ? '-1' : '0', 'data-item': one.row.id }, [
          el('td', { cls: 'num', text: String(i + 1) }),
          el('td', { text: one.row.name + (one.row.place ? ' (' + one.row.place + ')' : '') }),
          el('td', { text: indicatorName(one.ind) }),
          el('td', { text: clsAt(one.row, one.ind, k) }),
          el('td', { cls: 'num', text: formatNumber(pair[0]), title: String(pair[0]) }),
          el('td', { cls: 'num', text: formatNumber(pair[1]), title: String(pair[1]) }),
          valueCell(one.row, one.ind, k, false),
          el('td', { text: verdictOf(one.row, one.ind, k) || '—' })
        ]));
      });
      table.appendChild(body);
    }

    function gridRows() {
      var k = kNow();
      var find = view.find.toLowerCase();
      var ids = indicatorIds();
      var found = rows().filter(function (row) {
        if (find && (row.name + ' ' + (row.place || '') + ' ' + row.id).toLowerCase().indexOf(find) < 0) return false;
        if (view.group && row.group !== view.group) return false;
        if (view.cls && !ids.some(function (id) { return clsAt(row, id, k) === view.cls; })) return false;
        if (view.verdict && !ids.some(function (id) { return verdictOf(row, id, k) === view.verdict; })) return false;
        if (view.size && !ids.some(function (id) { var cls = clsAt(row, id, k); return QUIET.indexOf(cls) < 0 && sizeAtLeast(cls, bandAt(row, id, k), view.size); })) return false;
        return true;
      });
      var keyed = found.map(function (row, at) {
        if (view.sort.by === 'name') return { row: row, key: [row.name.toLowerCase(), row.place || '', at] };
        if (view.sort.by === 'worst') return { row: row, key: worstKey(row, k, ids).concat([at]) };
        return { row: row, key: furthestKey(row, k, [view.sort.id]).concat([at]) };
      });
      keyed.sort(function (a, b) { return compareKeys(a.key, b.key); });
      return keyed.map(function (one) { return one.row; });
    }

    // where a row stands over the indicators `ids`: a move that has no factor (from or to
    // zero, a sign change) lies further apart than any factor, so such a row comes first;
    // then the largest factor between its two results, among the values that moved, the
    // furthest from 1 first; a row that did not move comes last; among equals, by its worst
    // value as severityKey orders values. Over every indicator it is the order the grid opens
    // in; over one, the order of that column's heading: one order, the one the titles say.
    var NO_FACTOR = ['zero reference', 'zero result', 'sign change'];
    function furthestKey(row, k, ids) {
      var furthest = 0, worst = null;
      ids.forEach(function (id) {
        var pair = pairOf(row, id, k), cls = clsAt(row, id, k);
        if (NO_FACTOR.indexOf(cls) >= 0) furthest = Infinity;
        else if (cls === 'differs' || cls === 'beyond 10x') furthest = Math.max(furthest, distance(pair[0], pair[1]));
        var one = severityKey(pair[0], pair[1], cls);
        if (worst === null || compareKeys(one, worst) < 0) worst = one;
      });
      return [-furthest].concat(worst);
    }

    // the order the grid opens in, kept on the row per comparison
    function worstKey(row, k, ids) {
      var tag = isSet(k) ? 'set:' + C.key : k;
      if (row.worst && row.worst.k === tag) return row.worst.key;
      var key = furthestKey(row, k, ids);
      row.worst = { k: tag, key: key };
      return key;
    }

    // a heading sorts by itself; a second click goes back to the furthest apart first. The
    // headings are drawn anew, so the focus goes to the new button of the same heading, not
    // to the end of the page.
    function sortButton(label, sort, title) {
      var button = el('button', { type: 'button', cls: 'sd-sort', text: label, title: title });
      button.sdSort = sort;
      button.addEventListener('click', function () {
        if (released) return;
        var focused = doc.activeElement === button;
        view.sort = sortIs(sort) ? WORST : sort;
        view.limit = PAGE;
        renderGrid();
        markChosenCard();
        if (!focused) return;
        var again = q('grid-table').querySelectorAll('button[type="button"]');
        for (var i = 0; i < again.length; i++) {
          var other = again[i].sdSort;
          if (other && other.by === sort.by && other.id === sort.id) { again[i].focus(); break; }
        }
      });
      return button;
    }

    // the columns of the matrix: the indicators in which the comparison moved most first, so
    // that what a step did is in view without scrolling; the file's order among equals, and
    // an indicator in which nothing moved last, quietened
    function columns() {
      var blocks = blocksNow();
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
      var k = kNow();
      var cols = columns();
      var found = gridRows();
      var shown = found.slice(0, view.limit);
      q('grid-said').textContent = D.tier === 'counts'
        ? 'This file holds counts only: it names no ' + D.item.one + '.'
        : 'Showing ' + groupThousands(shown.length) + ' of ' + groupThousands(found.length) + ' ' + many(found.length) +
          (M ? '' : ', among ' + heldSaid()) + '.' + sizeSaid();
      q('grid-region').setAttribute('aria-label', 'After divided by before, per ' + D.item.one + ' and ' + indWord(false) + ': ' + nowLabel() +
        (view.sort.by === 'worst' ? ', the furthest apart first' : ''));
      var table = clear(q('grid-table'));
      var sorted = function (sort) { return sortIs(sort) ? (sort.by === 'name' ? 'ascending' : 'descending') : null; };
      var head = [
        el('th', { scope: 'col', cls: 'sd-name', 'aria-sort': sorted(BY_NAME) }, [sortButton(capital(D.item.one), BY_NAME, 'Sort by name')]),
        el('th', { scope: 'col', cls: 'sd-group', text: 'Group' })
      ];
      cols.forEach(function (c) {
        var ind = c.ind, column = byColumn(ind.id);
        head.push(el('th', { scope: 'col', cls: 'num' + (c.active ? '' : ' sd-still'), 'aria-sort': sorted(column),
          title: ind.name + (ind.unit ? ' (' + ind.unit + ')' : '') + ': ' + activeSaid(c) + ' here' },
          [sortButton(indicatorName(ind.id), column, COLUMN_ORDER)]));
      });
      table.appendChild(el('thead', null, [el('tr', null, head)]));
      var body = el('tbody');
      shown.forEach(function (row, i) {
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
        body.appendChild(el('tr', { cls: 'sd-row', tabindex: i ? '-1' : '0', 'data-item': row.id, 'aria-current': view.open === row.id ? 'true' : null }, cells));
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
      var k = kNow();
      var classes = {}, verdicts = {}, groups = {};
      var ids = indicatorIds();
      rows().forEach(function (row) {
        ids.forEach(function (id) {
          classes[clsAt(row, id, k)] = 1;
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
        'Beyond 10x: one size more than ' + D.rule.beyond + ' times the other. The whole way is counted with a tolerance of ' + D.rule.total_tolerance + ', the largest of the steps, and noise ' + totalNoiseSaid() + '. ' +
        'Noise belongs to a state: how far two builds of it differ. A step, a run of steps and the whole way are compared with the sum of the noise of their two ends, since rebuilding both moves the difference by up to the sum; a state inside a run adds nothing, as the pair holds none of its results. The published results are exact. ' +
        'Several steps chosen together are always a run: this page counts them with the same rule and the largest tolerance of their steps, from the result before the first chosen step and the result after the last; no verdict. ' +
        'The matrix shows the result after divided by the result before; the ratio and the strength of its colour are a display, and change no class.']));
      if (statesCarryNoise(D)) {
        var stateNoise = el('ul', { cls: 'sd-quiet' });
        D.states.forEach(function (st) {
          var said = st.kind === 'published' ? 'exact: the published results have no builds'
            : noiseText(st.noise, indicatorIds(), indWord(true)) + (st.noise.measured ? ': ' + Object.keys(st.noise.by).map(function (k) { return indicatorName(k) + ' ' + formatNumber(st.noise.by[k]); }).join(', ') : '');
          stateNoise.appendChild(el('li', { text: st.label + ': ' + said }));
        });
        body.appendChild(el('h4', { text: 'Noise of each state' }));
        body.appendChild(stateNoise);
      }
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
      // a file explains the items it lists only: for one that came from the matrix, no
      // explanation of its own was ever possible, which is not "none given"
      if (!row.item) {
        list.appendChild(el('li', { cls: 'sd-none', text: 'Not listed in this file, so it carries no explanation of its own: a file explains only the ' + D.item.many + ' it lists.' }));
      }
      own.forEach(function (e) { list.appendChild(explanationNode(e, 'This ' + D.item.one)); });
      wider.forEach(function (e) { list.appendChild(explanationNode(e, e.about.step && e.about.indicator ? 'Its step and ' + indWord(false) : e.about.step ? 'A step it moved in' : e.about.indicator ? capital(article(indWord(false))) + ' it moved in' : 'The whole file')); });
      if (!own.length && !wider.length) {
        var any = movedUnder(row, {});
        var text = !row.item
          ? (any ? 'No explanation in this file is about a step or ' + indWord(false) + ' in which it moved.' : 'It moved in no comparison.')
          : any ? 'None given: no explanation in this file is about this ' + D.item.one + ', or about a step or ' + indWord(false) + ' in which it moved.'
            : 'It moved in no comparison, and no explanation in this file is about it.';
        list.appendChild(el('li', { cls: 'sd-none', text: text }));
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
      var chosen = view.set.length === D.steps.length ? [] : view.set;
      D.steps.forEach(function (s, k) {
        var b = values[k], a = values[k + 1];
        var share = split.state === 'split' ? shareText(split.shares[k]) : '—';
        tb.appendChild(el('tr', { cls: chosen.indexOf(k) >= 0 ? 'sd-in-run' : null }, [
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
      if (isSet(kNow())) {
        var pair = pairOf(row, ind.id, SET);
        tb.appendChild(el('tr', { cls: 'sd-in-run' }, [
          el('th', { scope: 'row', text: setWords(view.set) }),
          el('td', { cls: 'num', text: formatNumber(pair[0]), title: String(pair[0]) }),
          el('td', { cls: 'num', text: formatNumber(pair[1]), title: String(pair[1]) }),
          valueCell(row, ind.id, SET, false),
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
      drawer.setAttribute('aria-label', row.name);
      showDrawer(drawer);
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
        var drawOrRefuse = function (data) {
          var problem = breakdownProblem(data, row, comp);
          clear(holder);
          if (problem) holder.appendChild(el('p', { cls: 'sd-error', text: 'The breakdown ' + name + ' ' + problem + ': not drawn.' }));
          else breakdownInto(holder, data);
        };
        if (B[name]) { drawOrRefuse(B[name]); return; }
        holder.appendChild(el('p', { cls: 'sd-quiet', text: 'The breakdown ' + name + ' is not with this page.' }));
        if (safeName(name) && /^https?:$/.test(win.location.protocol)) {
          win.fetch(base + name).then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
            .then(drawOrRefuse, function () { /* not read: the sentence above stays */ });
        }
      });
      markOpen();
      var title = q('item-title');
      // the title takes the focus without scrolling the host's page to wherever it stands
      if (!quiet && title.focus) title.focus({ preventScroll: true });
    }

    // The drawer is a dialog, drawn above everything on the host's page however the host
    // stacks or transforms what holds the page. On a wide window it opens as a popover, the
    // grid beside it still in use. Where it fills the window (a phone), or where the browser
    // knows no popovers, it opens as a modal dialog, the rest of the page inert behind it. A
    // browser that knows neither, or where showing it fails, shows it as a fixed element.
    //
    // A browser no longer draws an element above the rest once it is taken out of the
    // document, so a host that moves the page while the drawer is open leaves a popover
    // hidden and a modal dialog open but no longer modal. The page shows it above again
    // where it now stands (keepDrawer), at the change to the document that moved it, before
    // it is drawn.
    var NARROW = '(max-width: 47.99rem)'; // the width at which the style makes it the whole window
    var drawerAbove = false; // the drawer was last shown above the rest, not as the fixed element
    function popoverOpen(node) {
      try { return !!node.showPopover && node.matches(':popover-open'); } catch (error) { return false; }
    }
    // open as a modal dialog; a browser that knows no ":modal" is taken at its word
    function modalOpen(node) {
      if (!node.open) return false;
      try { return node.matches(':modal'); } catch (error) { return true; }
    }
    function showDrawer(node) {
      if (popoverOpen(node) || modalOpen(node)) return;
      var narrow = !!(win.matchMedia && win.matchMedia(NARROW).matches);
      try {
        // open but no longer modal (moved): closed first, as a dialog open is not shown modal
        if (node.open && node.close) node.close();
        if (node.showPopover && !(narrow && node.showModal)) node.showPopover();
        else if (node.showModal) node.showModal();
      } catch (error) { /* the fixed element stands */ }
      drawerAbove = popoverOpen(node) || modalOpen(node);
    }
    function hideDrawer(node) {
      try {
        if (popoverOpen(node)) node.hidePopover();
        if (node.open && node.close) node.close();
      } catch (error) { /* hidden as an element all the same */ }
    }
    // an open drawer the page had shown above the host's page, and the browser took out of it
    // when the host moved the page, shown there again; never one the page could not show so,
    // and not while the page is out of the document, where a browser shows nothing above (a
    // page of its own acts out of it too): it is shown once the page is back
    function keepDrawer() {
      var drawer = q('item');
      if (!acting || !inDocument() || !drawerAbove || !drawer || drawer.hidden || popoverOpen(drawer) || modalOpen(drawer)) return;
      showDrawer(drawer);
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
      hideDrawer(drawer);
      view.open = null;
      markOpen();
      if (hashParts().item) setHash(null);
      if (lastFocus && lastFocus.focus && root.contains && root.contains(lastFocus)) lastFocus.focus();
      lastFocus = null;
    }

    // Why a breakdown is not drawn under this item for this step, or null. It is drawn only
    // where it is this item's breakdown of this step, its parts and rest add up to its totals,
    // and its totals are the item's results in the two states: the checks of breakdown.errors
    // and breakdown.against, which a breakdown fetched over http has had no Python to pass.
    function breakdownProblem(data, row, comp) {
      if (!data || typeof data !== 'object' || data.format !== 'sentier-diagnostics-breakdown/1') return 'is not a breakdown';
      var k = stepIndex(comp);
      var from = comp === 'total' ? D.states[0].id : D.steps[k].from;
      var to = comp === 'total' ? D.states[D.states.length - 1].id : D.steps[k].to;
      if (data.item !== row.id || data.from !== from || data.to !== to) return 'is of another ' + D.item.one + ' or another step';
      if (!data.indicators || typeof data.indicators !== 'object' || Array.isArray(data.indicators) || !Object.keys(data.indicators).length) return 'holds no indicators';
      var sides = [D.states.map(function (s) { return s.id; }).indexOf(from), D.states.map(function (s) { return s.id; }).indexOf(to)];
      var pairOk = function (p) { return Array.isArray(p) && p.length === 2 && p.every(function (v) { return typeof v === 'number' && isFinite(v); }); };
      var keys = Object.keys(data.indicators);
      for (var i = 0; i < keys.length; i++) {
        var key = keys[i], entry = data.indicators[key];
        if (!row.values[key]) return 'names ' + article(indWord(false)) + ' this file does not hold, ' + key;
        if (!entry || !pairOk(entry.total) || !pairOk(entry.rest) || !Array.isArray(entry.parts) ||
            !entry.parts.every(function (p) { return p && pairOk(p.values); })) {
          return 'is not of the shape of a breakdown in ' + indicatorName(key);
        }
        for (var side = 0; side < 2; side++) {
          var parts = entry.parts.map(function (p) { return p.values[side]; }).concat([entry.rest[side]]);
          if (!addsUp(parts, entry.total[side])) return 'does not add up: in ' + indicatorName(key) + ' its parts are not its total ' + (side ? 'after' : 'before');
          var result = row.values[key][sides[side]];
          if (result === null || result === undefined || !addsUp([entry.total[side]], result)) {
            return 'is not of this file: its total in ' + indicatorName(key) + ' is not the ' + D.item.one + '\'s result in ' + D.states[sides[side]].id;
          }
        }
      }
      return null;
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
      if (!D) return; // none drawn, or the page was unmounted
      var problem = checkMatrix(m, D);
      if (problem) { refuseMatrix(problem); return; }
      M = matrixRows(m, D);
      matrix.state = 'loaded';
      matrix.said = '';
      // a run judged from the listed items is judged again from every item, and the
      // address, which may ask for a run the page could not judge before, is read again
      C = null; CHECKED = {};
      view.limit = PAGE;
      tierSaid();
      matrixSaid();
      var set = view.set;
      view.set = [];
      if (choose(set)) choose(allSteps());
      route();
    }

    function refuseMatrix(said) { if (released) return; matrix.state = 'refused'; matrix.said = said; matrixSaid(); if (D) markPicker(); }

    // The matrices handed to the pages of a document. A script `page.write` puts beside a
    // page adds an entry to a list, `SENTIER_DIAGNOSTICS_MATRICES`: the address it was loaded
    // from and its matrix. A document may hold several pages, each with its own script, so a
    // page takes the entry of the script it names, by its address, and no other. A host that
    // keeps a page's matrix in a script of its own sets one global instead,
    // `SENTIER_DIAGNOSTICS_MATRIX`, for one page.
    function handedAt(address) {
      var list = Array.isArray(win.SENTIER_DIAGNOSTICS_MATRICES) ? win.SENTIER_DIAGNOSTICS_MATRICES : [];
      for (var i = list.length - 1; i >= 0; i--) if (list[i] && list[i].src && list[i].src === address) return list[i].matrix;
      return null;
    }
    // Before loading: this file's matrix among the entries of the script named, at its
    // address or at it with another query or fragment (a host that put `matrix.js?v=3` in
    // its page to pass a cache). The check against the file keeps a stale matrix out, not
    // the address, which is as likely the stale copy. Where none is this file's, the entry at
    // the very address is taken (and refused, and said why); with none, the script is loaded.
    function handedFor(address) {
      var list = Array.isArray(win.SENTIER_DIAGNOSTICS_MATRICES) ? win.SENTIER_DIAGNOSTICS_MATRICES : [];
      var file = address.split(/[?#]/)[0];
      for (var i = list.length - 1; i >= 0; i--) {
        var entry = list[i];
        if (entry && typeof entry.src === 'string' && entry.src.split(/[?#]/)[0] === file && !checkMatrix(entry.matrix, D)) return entry.matrix;
      }
      return handedAt(address);
    }
    // the address a name beside the page is loaded from, as a script's `src` reads it
    function addressOf(name) {
      var a = doc.createElement('a');
      a.setAttribute('href', base + name);
      return a.href || base + name;
    }

    // The matrix comes after the page is drawn: the one handed over by the host where it is
    // this file's, or the file the root or the diagnostics file names, as a script beside the
    // page (which opens from disk too) or as JSON over http. A page that names no matrix
    // looks only at the host's global: another page's matrix in the list was never meant
    // for it.
    function loadMatrix() {
      if (given.matrix) { takeMatrix(given.matrix); return; }
      var hostMatrix = D.tier === 'counts' ? null : win.SENTIER_DIAGNOSTICS_MATRIX || null;
      if (hostMatrix && !checkMatrix(hostMatrix, D)) { takeMatrix(hostMatrix); return; }
      var name = root.getAttribute('data-sd-matrix') || (D.matrix ? D.matrix.file : null);
      if (!name || D.tier === 'counts') {
        if (hostMatrix) takeMatrix(hostMatrix); // refused, and said why
        else matrixSaid();
        return;
      }
      if (!safeName(name)) { refuseMatrix('its name is not a plain file name beside the page'); return; }
      if (/\.js$/.test(name)) {
        var there = handedFor(addressOf(name)); // a host that put the script in its page itself
        if (there) { takeMatrix(there); return; }
      }
      matrix.state = 'loading';
      matrix.said = name;
      matrixSaid();
      markPicker();
      if (/\.js$/.test(name)) {
        var script = doc.createElement('script');
        script.setAttribute('src', base + name);
        // the script stays in the head once it has run: it calls the page weakly, so that it
        // does not keep a page the host removed (issue 40)
        script.onload = hold(function () {
          var got = handedAt(script.src || addressOf(name));
          if (got) takeMatrix(got); // refused, and said why, if not this file's
          else if (win.SENTIER_DIAGNOSTICS_MATRIX && win.SENTIER_DIAGNOSTICS_MATRIX !== hostMatrix) takeMatrix(win.SENTIER_DIAGNOSTICS_MATRIX); // a script that sets the global
          else refuseMatrix(name + ' holds no matrix');
        });
        script.onerror = hold(function () { refuseMatrix(name + ' is not beside the page'); });
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
      if (released) return; // a file that failed to come after the page was unmounted
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
      if (released) return;
      shown = { data: data, checked: checked };
      if (waiting) return;
      var problem = checkShape(data);
      if (problem) { refuse(problem); return; }
      D = data;
      M = null;
      LISTED = D.items.map(listedRow);
      matrix = { state: 'none', said: '' };
      C = null; CHECKED = {}; FLOORS = {};
      (D.rule.floors || []).forEach(function (f) { FLOORS[floorKey(f.indicator, f.unit)] = f.value; });
      view.set = allSteps();
      view.anchor = null;
      view.notice = '';
      // a short chain shows its list of steps open; a long one opens it on a click
      view.pickOpen = D.steps.length <= 16;
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

    // The address holds the steps chosen and the open item, each optional, so that a reviewer
    // can send someone to exactly what they look at: `#step=<id>` for one step, nothing for
    // the whole way, `#steps=<id>:<id>,<id>` for any other set (a run as its first and last
    // step), and `&item=<id>`. The parts are kept as written, each id decoded on its own, so
    // that an id holding a comma or a colon is still one id.
    //
    // The address is the host's too, and may hold other pages: a page reads and writes only
    // its own parts, and leaves every other part where it was. A page of its own writes its
    // parts as above. A page in a host's page writes them after its key, so that it never
    // reads a host's own `item=` and two pages never take each other's step or item: the
    // host's name for it (`data-sd-key`), or else `sd.` for the first page in the document
    // and `sd2.`, `sd3.` … for the next, in the order they took them, not the order of their
    // places, so a page mounted later but placed earlier takes a key of its own.
    //
    // A key the host names is a plain word (a letter, then letters, digits, - or _), and not
    // one of the page's own (`sd`, `sd2` ...): anything else would write an address the page
    // cannot read back. The page refuses it and says why.
    //
    // A page takes its key in the document, never outside it: when it is mounted there, or
    // else when it is first found there (the document changed, the address changed, or it
    // is used). It holds the key while it is in the document, and a page that leaves it
    // keeps its key until a page in the document needs it. So a page drawn in place of one
    // removed takes the key it left, and an address made before still opens it; a page
    // built and dropped before it was ever put in takes none; and two pages built before
    // either is put in take one key each once they are in.
    //
    // A page out of the document answers no address. One put back takes its key again where
    // no page in the document took it, or else the next free one (an address made for it
    // before now opens the page that took its key); a page the host named waits, says why,
    // and is drawn once the other page with its name has left. Two pages in the document
    // never hold one key. `unmount()` takes a page's listeners off and gives its key up at
    // once. A page removed without it is let go once nothing holds it (see sharedListeners):
    // the list of keys and the list of pages waiting hold each page weakly, so a key whose
    // page was collected is free.
    var OWN_PARTS = ['step', 'steps', 'item'];
    var keyProblem = null; // a key the page can never hold: it is not a word, or it is one of the page's own
    var waiting = false; // another page in the document holds the key the host named: the page draws nothing
    // the key each page holds, by key: a weak reference to the page's entry
    //
    // Every copy of this script in a window reads these two lists, whatever its version, so
    // their shape is a contract between versions: an entry is an object whose deref() gives
    // the page's {root, wake}, or nothing once the page is gone. An entry of another shape
    // reads as free, so a version that changed it would let two pages take one key. A key
    // whose page was collected keeps its spent entry until the key is taken again.
    var keys = win.SENTIER_DIAGNOSTICS_KEYS = win.SENTIER_DIAGNOSTICS_KEYS || {};
    // the pages waiting for a key another holds: one that gives a key up wakes them, as no
    // change to the document may reach them (it left from inside a shadow root they do not
    // watch, or the page that left was mounted by another copy of this script)
    var waiters = win.SENTIER_DIAGNOSTICS_WAITERS = win.SENTIER_DIAGNOSTICS_WAITERS || [];
    var self = { root: root, wake: function () { present(); } }; // this page's entry in the list of keys
    var selfRef = weakly(self); // and how the lists hold it
    function holderOf(key) {
      var ref = keys[key];
      return ref && typeof ref.deref === 'function' ? ref.deref() || null : null;
    }
    var named = root.getAttribute('data-sd-key');
    var KEY = standalone ? '' : null; // what the page's parts start with, while it holds a key
    var lastKey = null;
    var teardown = [];
    var released = false;
    var acting = false; // in the document with its key, at the last look
    var routing = false;
    var shown = null; // the file last handed to the page, drawn once it may draw
    if (named !== null && !standalone) {
      if (!KEY_WORD.test(named)) keyProblem = 'The page\'s key, data-sd-key="' + named + '", is not a plain word: a letter, then up to ' + (KEY_LONGEST - 1) + ' letters, digits, - or _. An address could not hold it.';
      else if (OWN_KEY.test(named)) keyProblem = 'The page\'s key, data-sd-key="' + named + '", is one the page gives a page the host names none for (sd, sd2 ...): name it otherwise.';
    }
    function inDocument() { return root.isConnected !== false; }
    function holding() { return standalone || (lastKey !== null && holderOf(lastKey) === self); }
    function free(key) {
      var held = holderOf(key);
      return !held || held === self || held.root.isConnected === false;
    }
    function stopWaiting() { var at = waiters.indexOf(selfRef); if (at >= 0) waiters.splice(at, 1); }
    // each page still waiting, woken; one collected while it waited is taken off the list
    function wakeOthers() {
      waiters.slice().forEach(function (ref) {
        var other = ref && typeof ref.deref === 'function' ? ref.deref() : null;
        if (other) { other.wake(); return; }
        var at = waiters.indexOf(ref);
        if (at >= 0) waiters.splice(at, 1);
      });
    }
    function pick() {
      if (named !== null) return free(named) ? named : null;
      if (lastKey !== null && free(lastKey)) return lastKey;
      for (var n = 1; ; n++) {
        var key = 'sd' + (n > 1 ? n : '');
        if (free(key)) return key;
      }
    }
    function mayAct() {
      if (released || keyProblem) return false;
      if (standalone) return true;
      if (!inDocument()) return false;
      if (holding()) return true;
      var key = pick();
      if (key === null) {
        if (waiters.indexOf(selfRef) < 0) waiters.push(selfRef);
        if (!waiting) {
          waiting = true;
          refuse('Another page in the document has the key data-sd-key="' + named + '": two pages with one key would open on each other\'s items. Give each its own. This page is drawn once the other has left.');
        }
        return false;
      }
      keys[key] = selfRef;
      lastKey = key;
      KEY = key + '.';
      stopWaiting();
      return true;
    }
    // Whether the page may act on the address now: it is in the document and holds its key,
    // which it takes here if it holds none. A page that could not act before catches up: it
    // draws the file it waited to draw, or reads the address as it is now.
    function present() {
      var was = acting;
      acting = mayAct();
      if (was && !acting) wakeOthers(); // it left: its key is free for a page waiting for it
      if (acting && !was) {
        if (waiting) {
          waiting = false;
          q('load-error').textContent = '';
          if (shown) show(shown.data, shown.checked);
          else showLoad();
        } else if (D && !routing) route();
      }
      return acting;
    }
    // unmounted: the page answers nothing more, draws nothing more, and gives its key up;
    // the address keeps what it said, for a page mounted in its place. The element is left
    // free: a page may be mounted on it again (React's StrictMode does, on the same element)
    function release() {
      if (released) return;
      released = true;
      acting = false;
      while (teardown.length) teardown.pop()();
      stopWaiting();
      if (lastKey !== null && holderOf(lastKey) === self) delete keys[lastKey];
      closeItem();
      D = null; M = null; LISTED = []; shown = null;
      q('content').hidden = true;
      q('load').hidden = true;
      root.removeAttribute('data-sd-mounted');
      wakeOthers();
    }
    function hashList() {
      var text = (win.location.hash || '').replace(/^#/, '');
      return text ? text.split('&') : [];
    }
    function ownName(part) {
      var at = part.indexOf('=');
      if (KEY === null || !holding() || at <= 0 || part.slice(0, KEY.length) !== KEY) return null;
      var name = part.slice(KEY.length, at);
      return OWN_PARTS.indexOf(name) >= 0 ? name : null;
    }
    function hashParts() {
      var out = {};
      hashList().forEach(function (part) {
        var name = ownName(part);
        if (name) out[name] = part.slice(part.indexOf('=') + 1);
      });
      return out;
    }
    function decoded(text) {
      try { return decodeURIComponent(text); } catch (error) { return null; }
    }
    // a run in the address: its first and last step
    function setText(set) {
      return encodeURIComponent(D.steps[set[0]].id) + ':' + encodeURIComponent(D.steps[set[set.length - 1]].id);
    }
    // the steps an address names, and the ids it names that this file does not have
    function setFrom(text) {
      var set = [], unknown = [];
      text.split(',').forEach(function (part) {
        var ends = part.split(':').map(decoded);
        var ks = ends.map(function (id) { return id === null ? -1 : stepAt(id); });
        ends.forEach(function (id, i) { if (ks[i] < 0) unknown.push(id === null ? part : id); });
        if (ends.length > 2 || ks.some(function (k) { return k < 0; })) return;
        for (var k = Math.min(ks[0], ks[ks.length - 1]); k <= Math.max(ks[0], ks[ks.length - 1]); k++) if (set.indexOf(k) < 0) set.push(k);
      });
      return { set: set.sort(function (a, b) { return a - b; }), unknown: unknown };
    }
    function setHash(item) {
      if (!present()) return false; // out of the document, or without its key: the address is another's
      var said = [], k = kNow();
      if (isSet(k)) said.push(KEY + 'steps=' + setText(view.set));
      else if (k < D.steps.length) said.push(KEY + 'step=' + encodeURIComponent(D.steps[k].id));
      if (item) said.push(KEY + 'item=' + encodeURIComponent(item));
      var others = hashList().filter(function (part) { return ownName(part) === null; });
      var wanted = others.concat(said).join('&');
      if ((win.location.hash || '').replace(/^#/, '') === wanted) return false;
      if (wanted) win.location.hash = wanted;
      // nothing left to say: the address loses its "#", and the host keeps its history state
      else if (win.history && win.history.replaceState) win.history.replaceState(win.history.state, '', win.location.pathname + win.location.search);
      return true;
    }

    // the steps a to b, both taken in
    function stepsFrom(a, b) {
      var out = [];
      for (var k = Math.min(a, b); k <= Math.max(a, b); k++) out.push(k);
      return out;
    }

    var APART = 'Steps apart are not compared on a chain: each step was measured with every step before it applied, so adding up steps apart would use differences measured in a state the set never had. Choose one step, or a run (Shift).';
    // Choose a run of steps and draw what they did. A run the page cannot judge, or steps
    // that are not a run, are said and change nothing; returns why, or null.
    function choose(set) {
      set = set.filter(function (k, i) { return set.indexOf(k) === i; }).sort(function (a, b) { return a - b; });
      if (!set.length) return 'At least one step stays chosen: "The whole way" chooses every step.';
      if (set[set.length - 1] - set[0] + 1 !== set.length) return APART;
      if (isSet(posOf(set))) {
        var why = judgeRun(set);
        if (why) return why;
      }
      var same = sameList(set, view.set);
      view.set = set;
      markPicker();
      renderStepSaid();
      if (same) return null;
      view.cls = ''; view.verdict = ''; view.limit = PAGE; view.sort = WORST;
      renderComparison();
      if (view.open) renderItem(view.open, true);
      return null;
    }

    // a choice made on the page: drawn, or said and left as it was; the address follows it
    function pickSet(set) {
      view.notice = '';
      var why = choose(set);
      if (why) {
        view.notice = why;
        markPicker();
        renderStepSaid();
        return;
      }
      setHash(view.open);
    }

    // one step by hand. "one": that step alone. "to" (Shift, or ⌘ or Ctrl, on the strip or in
    // the list): every step from the one chosen before to this one.
    function pickStep(k, how) {
      var anchor = view.anchor === null ? k : view.anchor;
      if (how === 'to') pickSet(stepsFrom(anchor, k));
      else { view.anchor = k; pickSet([k]); }
    }

    // the run of a group of the list: every step of it
    function pickGroup(first) {
      var group = null;
      groupsOf().forEach(function (g) { if (g.steps[0] === first) group = g.steps; });
      if (!group) return;
      view.anchor = group[0];
      pickSet(group.slice());
    }

    // the address, read: what it names is chosen; what it names that the file does not have,
    // or that cannot be judged now, is said, and the whole way shown
    function route() {
      routing = true;
      try { present(); } finally { routing = false; }
      if (!D) return;
      var parts = hashParts();
      var wanted = allSteps(), said = '';
      if (parts.steps !== undefined) {
        var found = setFrom(parts.steps);
        if (found.unknown.length) said = 'The address names ' + (found.unknown.length === 1 ? 'a step' : 'steps') + ' this file does not have (' + found.unknown.join(', ') + '). The whole way is shown.';
        else if (found.set.length) wanted = found.set;
      } else if (parts.step !== undefined) {
        var id = decoded(parts.step), k = id === null ? -1 : stepAt(id);
        if (k < 0) said = 'The address asks for "' + (id === null ? parts.step : id) + '", which is no step of this file. The whole way is shown.';
        else wanted = [k];
      }
      var why = choose(wanted);
      if (why) {
        said = 'The address asks for ' + askedWords(wanted) + '. ' + why + ' The whole way is shown.';
        choose(allSteps());
      }
      view.notice = said;
      if (view.set.length !== D.steps.length) view.anchor = view.set[0];
      renderStepSaid();
      var item = parts.item !== undefined ? decoded(parts.item) : null;
      if (item) renderItem(item, view.open === item);
      else closeItem();
    }

    function openFrom(event) {
      var row = event.target.closest ? event.target.closest('tr[data-item]') : null;
      if (!row) return;
      takeStop(row, false);
      var id = row.getAttribute('data-item');
      if (!setHash(id)) renderItem(id);
    }

    // A table of items is one tab stop, the row last moved to (the first when it is drawn);
    // the arrow keys, Home and End move between its rows, so that Tab leaves the table in one
    // press however many rows it holds.
    var ROW_KEYS = { ArrowDown: 1, ArrowUp: -1, Home: -Infinity, End: Infinity };
    function moveRow(event) {
      if (!ROW_KEYS.hasOwnProperty(event.key)) return;
      var row = event.target.closest ? event.target.closest('tr[data-item]') : null;
      if (!row || !row.parentNode) return;
      var rows = row.parentNode.childNodes;
      var at = Array.prototype.indexOf.call(rows, row);
      var to = Math.max(0, Math.min(rows.length - 1, at + ROW_KEYS[event.key]));
      if (event.preventDefault) event.preventDefault();
      if (to !== at) takeStop(rows[to], true);
    }
    function takeStop(row, focus) {
      var rows = row.parentNode ? row.parentNode.childNodes : [row];
      for (var i = 0; i < rows.length; i++) rows[i].setAttribute('tabindex', rows[i] === row ? '0' : '-1');
      if (focus && row.focus) row.focus();
    }

    function readScript(name) {
      var node = q(name);
      if (!node || !node.textContent || !/\S/.test(node.textContent)) return undefined;
      return JSON.parse(node.textContent);
    }

    // The page's own colours follow the host's. A host that sets a light ink is a dark page:
    // the page takes its dark ground and its other dark colours for every token the host did
    // not set, so that the host's ink is never set on the page's white. A host that sets a
    // dark ground and no ink gets the light ink. A host that sets neither keeps the light
    // colours, the ground set with the ink. Read again when the reader's colour scheme
    // changes, as a host's tokens may follow it.
    // The page's own mark sets only its own tokens (`--sd-*`), never `--ink`, `--surface` or
    // `color-scheme`, so the host's are read with the mark in place, and the mark is changed
    // only where the answer changed: a host that watches the page sees nothing for a reading
    // that found what it found before.
    function matchScheme() {
      var style = win.getComputedStyle ? win.getComputedStyle(root) : null;
      if (!style || !style.getPropertyValue) return;
      var dark = schemeIsDark(tokenColour(style, '--ink'), tokenColour(style, '--surface'), function (text) {
        return luminance(text, doc);
      });
      if (dark === (root.getAttribute('data-sd-scheme') === 'dark')) return;
      if (dark) root.setAttribute('data-sd-scheme', 'dark');
      else root.removeAttribute('data-sd-scheme');
    }

    // What the scheme is read from, read without changing anything: the host's two tokens as
    // the browser computes them (another var() in them already put in), the colour scheme
    // they may resolve by (light-dark(), a system colour), and the reader's. Null for a page
    // out of the document, which has no host to read.
    function schemeSign() {
      if (root.isConnected === false || !win.getComputedStyle) return null;
      var style = win.getComputedStyle(root);
      if (!style || !style.getPropertyValue) return null;
      var reader = win.matchMedia ? win.matchMedia(DARK_READER) : null;
      return [style.getPropertyValue('--ink'), style.getPropertyValue('--surface'),
        style.getPropertyValue('color-scheme'), reader && reader.matches ? 'dark' : 'light'].join('\n');
    }

    // A host's colour token as the browser resolves it, set on a probe in the page, so that
    // whatever the host wrote (a name, light-dark(), another var()) comes back as a colour.
    // A token that is no colour (a bare "0 0% 100%", kept by some hosts for their own hsl())
    // leaves the probe the colour of its parent; under two parents of different colours it
    // is told apart, and is null. Without a browser's styles: the token as written.
    function tokenColour(style, name) {
      var said = String(style.getPropertyValue(name) || '').trim();
      if (!said) return '';
      var got = [];
      try {
        ['rgb(1, 2, 3)', 'rgb(4, 5, 6)'].forEach(function (parent) {
          var outer = doc.createElement('span'), probe = doc.createElement('span');
          outer.hidden = true;
          outer.style.setProperty('color', parent);
          probe.style.setProperty('color', 'var(' + name + ')');
          outer.appendChild(probe);
          root.appendChild(outer);
          try { got.push(String(win.getComputedStyle(probe).color || '')); } finally { root.removeChild(outer); }
        });
      } catch (error) { return said; }
      if (!got[0]) return said;
      return got[0] === got[1] ? got[0] : null;
    }

    // A listener on the page's own elements, taken off when the page is released: a page
    // mounted again on the same element would otherwise share it with this one. What the
    // page listens to outside itself it shares with the other pages (sharedListeners).
    function listen(target, type, react, capture) {
      if (!target || !target.addEventListener) return;
      target.addEventListener(type, react, capture);
      teardown.push(function () { if (target.removeEventListener) target.removeEventListener(type, react, capture); });
    }
    // what calls back into the page from outside it, held here, so that it lives as long as
    // the page does; held weakly there (weakCall, sharedListeners)
    var kept = [];
    function hold(react) { kept.push(react); return weakCall(react); }

    // Look again whenever the host may have switched its theme: the reader's colour scheme
    // changed, the document changed (a class or an attribute anywhere, an element put in or
    // taken out, the page itself put in after it was built), or a stylesheet finished
    // loading. Watched: the document and every shadow root the page sits in, for changes
    // and for loads (a load does not leave a shadow root). A look reads only what the
    // scheme is read from (schemeSign), once a frame however much changed, and reads the
    // scheme itself only where that changed. So the page's own probes, and a host's
    // observer that answers them, end after one look. Not seen: a rule a host adds or edits
    // through the CSS object model alone, which changes nothing in the document.
    //
    // A change to the document is also where a page put in after it was built, or put
    // back, is found: it takes its key there, before the next frame (`present`); and where a
    // page moved with its drawer open shows the drawer again (`keepDrawer`). The listeners
    // are the ones every page shares; this page's entry among them is `entry`.
    var entry = null;
    function followScheme() {
      var last = schemeSign();
      var listeners = sharedListeners();
      function tops() { // the document, and each shadow root from the page's out to it
        var out = [doc];
        for (var node = root; node && node.getRootNode; ) {
          var top = node.getRootNode();
          if (!top || top === doc || !top.host) break;
          out.push(top);
          node = top.host;
        }
        return out;
      }
      // the roots the page sits in now: put in, or moved, it may sit in others than before
      function observe() { tops().forEach(function (top) { listeners.watch(top); }); }
      entry = {
        changed: function () { present(); keepDrawer(); },
        look: function () {
          if (released) return;
          var sign = schemeSign();
          if (sign === null) return;
          observe();
          if (sign === last) return;
          last = sign;
          matchScheme();
        },
        // a page that takes its key here has read the address already
        address: function () { var was = acting; if (present() && was) route(); }
      };
      teardown.push(listeners.join(entry));
      observe();
    }

    function start() {
      if (keyProblem) { refuse(keyProblem); return; }
      present();
      matchScheme();
      followScheme();
      listen(q('comparison'), 'click', function (e) {
        var cell = e.target.closest ? e.target.closest('button[data-comp]') : null;
        if (!cell || !D) return;
        var comp = cell.getAttribute('data-comp');
        if (comp === 'total') { view.anchor = null; pickSet(allSteps()); return; }
        pickStep(stepIndex(comp), e.shiftKey || e.metaKey || e.ctrlKey ? 'to' : 'one');
      });
      // the arrow keys move along the strip, a step alone at a time; with Shift they grow or
      // shrink the steps chosen at the end away from where they started
      listen(q('comparison'), 'keydown', function (e) {
        if (!D || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
        var step = e.key === 'ArrowRight' ? 1 : -1;
        var whole = view.set.length === D.steps.length;
        var lo = view.set[0], hi = view.set[view.set.length - 1];
        var to;
        if (e.shiftKey && !whole) {
          var k = (view.anchor === lo ? hi : lo) + step;
          if (k < 0 || k >= D.steps.length) return;
          if (view.anchor === null) view.anchor = lo;
          pickStep(k, 'to');
          to = D.steps[k].id;
        } else {
          var at = (whole ? 0 : 1 + (step > 0 ? hi : lo)) + step;
          if (at < 0 || at > D.steps.length) return;
          if (at === 0) { to = 'total'; view.anchor = null; pickSet(allSteps()); }
          else { to = D.steps[at - 1].id; pickStep(at - 1, 'one'); }
        }
        if (e.preventDefault) e.preventDefault();
        var next = q('comparison').querySelector('button[data-comp="' + to + '"]');
        if (next && next.focus) next.focus();
      });
      if (q('pick-list')) {
        listen(q('pick-list'), 'click', function (e) {
          if (!D) return;
          var row = e.target.closest ? e.target.closest('button[data-pick]') : null;
          if (row) { pickStep(+row.getAttribute('data-pick'), e.shiftKey || e.metaKey || e.ctrlKey ? 'to' : 'one'); return; }
          var group = e.target.closest ? e.target.closest('button[data-group]') : null;
          if (group) pickGroup(+group.getAttribute('data-group'));
        });
      }
      if (q('pick-open')) {
        listen(q('pick-open'), 'click', function () {
          view.pickOpen = !view.pickOpen;
          q('pick-open').setAttribute('aria-expanded', view.pickOpen ? 'true' : 'false');
          q('pick-panel').hidden = !view.pickOpen;
        });
      }
      if (q('pick-find')) listen(q('pick-find'), 'input', function (e) { view.pickFind = e.target.value; renderPickList(); });
      if (q('pick-moved')) listen(q('pick-moved'), 'change', function (e) { view.pickMoved = !!e.target.checked; renderPickList(); });
      if (q('pick-all')) listen(q('pick-all'), 'click', function () { if (D) { view.anchor = null; pickSet(allSteps()); } });
      listen(q('size'), 'change', function (e) { view.size = +e.target.value; view.limit = PAGE; renderWorst(); renderGrid(); });
      listen(q('worst-n'), 'change', function (e) { view.worstN = +e.target.value; renderWorst(); });
      listen(q('dist-scale'), 'change', function (e) { view.distScale = e.target.value === 'one' ? 'one' : 'card'; renderDistributions(); });
      listen(q('worst-indicator'), 'change', function (e) { view.worstIndicator = e.target.value; renderWorst(); });
      listen(q('grid-find'), 'input', function (e) { view.find = e.target.value; view.limit = PAGE; renderGrid(); });
      listen(q('grid-class'), 'change', function (e) { view.cls = e.target.value; view.limit = PAGE; renderGrid(); });
      listen(q('grid-verdict'), 'change', function (e) { view.verdict = e.target.value; view.limit = PAGE; renderGrid(); });
      listen(q('grid-group'), 'change', function (e) { view.group = e.target.value; view.limit = PAGE; renderGrid(); });
      listen(q('grid-more'), 'click', function () { view.limit += PAGE; renderGrid(); });
      listen(q('item-close'), 'click', closeItem);
      listen(root, 'keydown', function (e) { if (e.key === 'Escape') closeItem(); });
      // a modal drawer the browser closed itself (a phone's back gesture) is closed here too;
      // one the page closed to show it again (keepDrawer) is open by the time this is heard
      listen(q('item'), 'close', function () { if (!q('item').hidden && !q('item').open) closeItem(); });
      ['grid-table', 'worst-table'].forEach(function (name) {
        listen(q(name), 'click', openFrom);
        listen(q(name), 'keydown', function (e) { if (e.key === 'Enter') openFrom(e); else moveRow(e); });
      });
      listen(q('file'), 'change', function (e) {
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
    // a page whose key is refused draws nothing and opens nothing, whoever asks it to: the
    // reason stays where it was said, never replaced by a fault of the file it was given
    if (keyProblem) {
      var still = function () { refuse(keyProblem); };
      return { show: still, close: still, open: still, unmount: release };
    }
    // an unmounted page does nothing a host asks of it: it has no file to show an item of
    return { show: show, close: closeItem, open: renderItem, unmount: release };
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
    judge: judge, runsOf: runsOf, runPair: runPair, noiseOfStates: noiseOfStates, endsKnown: endsKnown, statesCarryNoise: statesCarryNoise,
    luminance: luminance, schemeIsDark: schemeIsDark, mount: mount, mountAll: mountAll };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else if (typeof global.document !== 'undefined') {
    global.SentierDiagnostics = api;
    if (global.document.readyState === 'loading') global.document.addEventListener('DOMContentLoaded', function () { mountAll(); });
    else mountAll();
  }
})(typeof window !== 'undefined' ? window : this);
