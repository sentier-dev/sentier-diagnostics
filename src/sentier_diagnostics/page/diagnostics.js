/* sentier-diagnostics page: shows a diagnostics file (sentier-diagnostics/1) as it is.
 *
 * Plain JavaScript, no library, no network but the file itself. The page works out no
 * class, direction, band, verdict or count: they are in the file, checked by the
 * validator. It only orders and filters, formats numbers, and subtracts consecutive
 * results to show each step's share. Every text of the file is set as text, never as markup.
 */
(function (root) {
  'use strict';

  var FORMAT = 'sentier-diagnostics/1';
  var MOVES = ['differs', 'beyond 10x', 'zero reference', 'zero result', 'sign change'];
  var QUIET = ['agrees', 'within noise', 'near zero'];
  // the order of the classes from the worst: the same as the Python rule (rule.RANK)
  var RANK = {
    'sign change': 0, 'zero reference': 1, 'zero result': 2, 'beyond 10x': 3, 'differs': 4,
    'missing': 5, 'within noise': 6, 'agrees': 7, 'near zero': 8
  };
  var STRENGTH = { '1-1.1': 0.3, '1.1-1.25': 0.5, '1.25-2': 0.7, '2-10': 0.85, 'over 10': 1 };
  var LOOK = ['off claim', 'not claimed', 'claimed, not moved'];
  var SAID = {
    'agrees': 'the two results differ by no more than the tolerance',
    'within noise': 'they differ by no more than two builds of one state do',
    'differs': 'the results differ',
    'beyond 10x': 'one result is more than ten times the size of the other',
    'zero reference': 'the result before is zero or within the floor; the result after is not',
    'zero result': 'the result after is zero or within the floor; the result before is not',
    'sign change': 'the two results have different signs',
    'near zero': 'both results are within the floor of their indicator and unit: their ratio says nothing',
    'missing': 'a side has no result; it is not read as zero'
  };
  var SHORT = {
    'agrees': '=', 'within noise': '~', 'near zero': '≈ 0', 'missing': '∅',
    'zero reference': '0 →', 'zero result': '→ 0', 'sign change': '±'
  };

  // ------------------------------------------------------------------ pure helpers

  function groupThousands(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }

  // a result as a reader reads it: four significant digits; never "0" for a value that is not 0
  function formatNumber(v) {
    if (v === null || v === undefined) return 'missing';
    if (v === 0) return '0';
    var a = Math.abs(v);
    if (a >= 1e6 || a < 1e-3) {
      return v.toExponential(3).replace(/\.?0+e/, 'e').replace('e+', 'e').replace(/-/g, '\u2212');
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
    return (v > 0 ? '' : v < 0 ? '\u2212' : '') + text + ' %';
  }

  function bandStep(band) {
    if (!band) return null;
    var at = band.indexOf('factor ');
    return at < 0 ? null : band.slice(at + 7);
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
        var r = Math.abs(after) / Math.abs(before);
        view.text = r >= 1 ? 'size ×' + formatNumber(r) : 'size ÷' + formatNumber(1 / r);
        view.tone = dir; view.strength = 1; view.mark = '»'; break;
      case 'differs':
        view.text = percentText(before, after); view.tone = dir;
        view.strength = STRENGTH[bandStep(band)] || 0.5; break;
      default:
        view.text = String(cls);
    }
    return view;
  }

  // the key that orders values from the worst: the same as the Python rule (rule.severity)
  function severityKey(before, after, cls) {
    var rank = RANK.hasOwnProperty(cls) ? RANK[cls] : 9;
    if (before === null || after === null) return [rank, 0];
    var magnitude;
    if (before !== 0 && after !== 0 && (before > 0) === (after > 0)) {
      magnitude = Math.abs(Math.log10(Math.abs(after) / Math.abs(before)));
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
    if (d.steps.length !== d.states.length - 1) return 'the file has not one step fewer than states';
    return null;
  }

  // ------------------------------------------------------------------ the page

  var D = null, B = {};
  var view = { comp: null, worstN: 20, worstIndicator: '', find: '', cls: '', verdict: '', group: '', limit: 100, size: 0 };

  function el(tag, props, children) {
    var node = document.createElement(tag);
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
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    return node;
  }
  function q(id) { return document.getElementById(id); }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
  function n(x) { return x === null || x === undefined ? '—' : groupThousands(x); }

  function indicatorName(id) {
    for (var i = 0; i < D.indicators.length; i++) {
      if (D.indicators[i].id === id) return D.indicators[i].short || D.indicators[i].name;
    }
    return id;
  }
  function stepIndex(comp) { // the position of a comparison in an item's lists of classes
    if (comp === 'total') return D.steps.length;
    for (var i = 0; i < D.steps.length; i++) if (D.steps[i].id === comp) return i;
    return D.steps.length;
  }
  function compLabel(comp) {
    if (comp === 'total') return 'The whole way: ' + D.states[0].label + ' → ' + D.states[D.states.length - 1].label;
    var k = stepIndex(comp);
    return 'Step ' + k + ': ' + D.steps[k].label;
  }
  function pairOf(item, indicator, k) {
    var values = item.values[indicator];
    return k === D.steps.length ? [values[0], values[values.length - 1]] : [values[k], values[k + 1]];
  }
  function verdictOf(item, indicator, k) {
    if (!item.verdicts || k >= D.steps.length) return null;
    return item.verdicts[indicator][k];
  }

  function cell(item, indicator, k) {
    var pair = pairOf(item, indicator, k);
    var cls = item.classes[indicator][k];
    var v = cellView(pair[0], pair[1], cls, item.directions[indicator][k], item.bands[indicator][k]);
    var verdict = verdictOf(item, indicator, k);
    var title = v.title + (verdict ? ' Verdict: ' + verdict + '.' : '');
    var classes = 'cell tone-' + v.tone + (v.noRatio ? ' no-ratio' : '');
    var td = el('td', { cls: classes, title: title, style: v.strength ? '--s:' + v.strength : null, 'data-class': cls },
      [v.text, v.mark ? el('span', { cls: 'mark', text: v.mark, 'aria-hidden': 'true' }) : null]);
    if (verdict && LOOK.indexOf(verdict) >= 0) td.appendChild(el('span', { cls: 'mark verdict-look', text: verdict === 'claimed, not moved' ? '○' : verdict === 'off claim' ? '◐' : '■', title: verdict }));
    return td;
  }

  function legend(node) {
    clear(node);
    var keys = [
      ['tone-up', 'up', 'went up (as signed numbers)'],
      ['tone-down', 'down', 'went down: two results below zero that go further below zero went down'],
      ['tone-up no-ratio', '0 →', 'from zero, to zero or across zero: no ratio'],
      ['tone-none', '=', 'agrees within the tolerance'],
      ['tone-noise', '~', 'within the measured noise'],
      ['tone-near', '≈ 0', 'near zero on both sides'],
      ['tone-missing', 'missing', 'a side has no result']
    ];
    keys.forEach(function (k) {
      node.appendChild(el('span', null, [el('span', { cls: 'key ' + k[0], style: '--s:0.7', text: k[1] }), k[2]]));
    });
    node.appendChild(el('span', null, ['■ not claimed, ◐ off claim, ○ claimed, not moved']));
  }

  function renderHeader() {
    document.title = D.title;
    q('title').textContent = D.title;
    q('about').textContent = D.about || '';
    var states = clear(q('states'));
    D.states.forEach(function (s) {
      var identity = Object.keys(s.identity).map(function (k) { return k + ': ' + s.identity[k]; }).join(', ');
      var join = s.join ? n(s.join.compared) + ' compared, ' + n(s.join.unmatched) + ' unmatched, ' + n(s.join.ambiguous) + ' ambiguous' : '';
      states.appendChild(el('li', { title: (s.about || '') + (identity ? ' (' + identity + ')' : '') + (s.join && s.join.note ? ' ' + s.join.note : '') },
        [s.label + (s.kind === 'published' ? ' (published)' : ''), join ? el('span', { cls: 'quiet', text: ' · ' + join }) : null]));
    });
    var c = D.items_count;
    q('tier').textContent = groupThousands(c.all) + ' ' + D.item.many + ', ' + D.indicators.length + ' indicators. ' +
      (D.tier === 'counts' ? 'This file holds counts only: no single ' + D.item.one + ' is shown.'
        : groupThousands(c.listed) + ' of the ' + groupThousands(c.qualifying) + ' ' + D.item.many + ' worth a look are in this file' +
          (c.not_listed ? '; ' + groupThousands(c.not_listed) + ' are not.' : '.'));
    q('audience').textContent = D.audience === 'local'
      ? 'Local file: its writer has not said that it may be published.' : '';
    q('audience').hidden = D.audience !== 'local';
    q('made-by').textContent = 'Written by ' + D.made_by + '. ' + FORMAT + '.';
    var select = clear(q('comparison'));
    select.appendChild(el('option', { value: 'total', text: 'The whole way' }));
    D.steps.forEach(function (s, k) { select.appendChild(el('option', { value: s.id, text: 'Step ' + k + ': ' + s.label })); });
    select.value = view.comp;
  }

  function sumOver(comp, fn) {
    var blocks = comp === 'total' ? D.counts.total : D.counts.steps[comp];
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
      var noise = s.noise.measured ? 'between ' + s.noise.between.join(' and ') : 'not measured';
      body.appendChild(el('tr', null, [
        el('td', { cls: 'num', text: String(k) }),
        el('td', null, [s.link ? el('a', { href: s.link, text: s.label }) : s.label, s.about ? el('div', { cls: 'quiet', text: s.about }) : null]),
        el('td', { text: s.kind }),
        el('td', { text: s.explained ? 'yes' : 'no: nothing explains it', cls: s.explained ? null : 'error' }),
        el('td', null, [s.claim ? s.claim.text : 'no claim', s.claim && s.claim.by ? el('div', null, [badge(s.claim.by)]) : null,
          s.claim && s.claim.scope.some(function (e) { return e.items === null; })
            ? el('div', { cls: 'quiet', text: 'Its list of ' + D.item.many + ' is not in this file' + (s.claim.reach !== null ? ' (' + n(s.claim.reach) + ')' : '') + ': the verdicts were worked out by its writer and cannot be checked again here.' }) : null]),
        el('td', { cls: 'num', text: n(sumOver(s.id, moved)) }),
        el('td', { cls: 'num', text: n(sumOver(s.id, function (b) { return b.directions.up; })) }),
        el('td', { cls: 'num', text: n(sumOver(s.id, function (b) { return b.directions.down; })) }),
        el('td', { cls: 'num', text: verdict('as claimed') }),
        el('td', { cls: 'num', text: verdict('off claim') }),
        el('td', { cls: 'num', text: verdict('not claimed') }),
        el('td', { cls: 'num', text: verdict('claimed, not moved') }),
        el('td', { cls: 'num', text: verdict('within noise') }),
        el('td', { cls: 'num', text: n(sumOver(s.id, function (b) { return b.missing.before + b.missing.both; })) }),
        el('td', { cls: 'num', text: n(sumOver(s.id, function (b) { return b.missing.after; })) }),
        el('td', { cls: 'num', text: String(s.tolerance.value), title: s.tolerance.basis + (s.tolerance.note ? ': ' + s.tolerance.note : '') }),
        el('td', { text: noise })
      ]));
    });
    table.appendChild(body);

    var total = clear(q('total-table'));
    q('total-heading').textContent = 'The whole way: ' + D.states[0].label + ' → ' + D.states[D.states.length - 1].label;
    var classes = Object.keys(D.counts.total[D.indicators[0].id].classes);
    var cols = ['Indicator'].concat(classes, ['Up', 'Down', 'Largest step', 'Not attributable', 'Moved by what nothing explains']);
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
      row.push(el('td', { text: ranked.join(', ') || 'none' }));
      row.push(el('td', { cls: 'num', text: n(att.not_attributable), title: 'its total moved, and it has no result in a state between: its difference cannot be split' }));
      row.push(el('td', { cls: 'num', text: n(att.unexplained_moved), title: 'moved in a step that no cause explains' }));
      tbody.appendChild(el('tr', null, row));
    });
    total.appendChild(tbody);
  }

  function renderDistributions() {
    var comp = view.comp;
    var blocks = comp === 'total' ? D.counts.total : D.counts.steps[comp];
    var first = blocks[D.indicators[0].id];
    var bands = Object.keys(first.bands);
    var down = bands.filter(function (b) { return b.indexOf('down') === 0; });
    var up = bands.filter(function (b) { return b.indexOf('up') === 0; });
    var middle = ['agrees', 'within noise'];
    var aside = ['zero reference', 'zero result', 'sign change', 'near zero', 'missing'];
    var columns = down.map(function (b) { return ['band', b, 'down']; })
      .concat(middle.map(function (c) { return ['class', c, '']; }))
      .concat(up.map(function (b) { return ['band', b, 'up']; }))
      .concat(aside.map(function (c) { return ['class', c, '']; }));
    var table = clear(q('dist-table'));
    var head = [el('th', { scope: 'col', text: 'Indicator' })];
    columns.forEach(function (c) {
      var label = c[0] === 'band' ? (c[2] === 'up' ? '↑ ' : '↓ ') + bandStep(c[1]) : (SHORT[c[1]] || c[1]);
      head.push(el('th', { scope: 'col', cls: 'num', text: label, title: c[1] + (SAID[c[1]] ? ': ' + SAID[c[1]] : '') }));
    });
    table.appendChild(el('thead', null, [el('tr', null, head)]));
    var body = el('tbody');
    D.indicators.forEach(function (ind) {
      var block = blocks[ind.id];
      var row = [el('th', { scope: 'row', text: indicatorName(ind.id) })];
      columns.forEach(function (c) {
        var count = c[0] === 'band' ? block.bands[c[1]] : block.classes[c[1]];
        var share = block.pairs ? count / block.pairs : 0;
        var bar = el('div', { cls: 'bar ' + c[2] }, [el('span', { style: 'height:' + (count ? Math.max(1, Math.round(share * 100)) : 0) + '%' })]);
        row.push(el('td', { cls: 'bar-cell', title: c[1] + ': ' + count + ' of ' + block.pairs }, [bar, el('div', { cls: 'bar-n', text: groupThousands(count) })]));
      });
      body.appendChild(el('tr', null, row));
    });
    table.appendChild(body);
  }

  function renderWorst() {
    var k = stepIndex(view.comp);
    var rows = [];
    D.items.forEach(function (item) {
      D.indicators.forEach(function (ind) {
        if (view.worstIndicator && ind.id !== view.worstIndicator) return;
        var cls = item.classes[ind.id][k];
        if (QUIET.indexOf(cls) >= 0) return;
        if (!sizeAtLeast(cls, item.bands[ind.id][k], view.size)) return;
        var pair = pairOf(item, ind.id, k);
        rows.push({ item: item, ind: ind.id, key: severityKey(pair[0], pair[1], cls).concat([item.id, ind.id]) });
      });
    });
    rows.sort(function (a, b) { return compareKeys(a.key, b.key); });
    var shown = rows.slice(0, view.worstN);
    var c = D.items_count;
    q('worst-said').textContent = D.tier === 'counts'
      ? 'This file holds counts only: it names no ' + D.item.one + '.'
      : 'Showing ' + shown.length + ' of the ' + rows.length + ' values that moved or are missing in ' + compLabel(view.comp) +
        ', among the ' + groupThousands(c.listed) + ' ' + D.item.many + ' in this file' +
        (c.not_listed ? '. ' + groupThousands(c.not_listed) + ' more ' + D.item.many + ' worth a look are not in this file.' : '.') +
        ' Ordered by class (sign change, zero reference, zero result, beyond 10x, differs, missing), then by how far the two sizes lie apart.' + sizeSaid();
    var table = clear(q('worst-table'));
    var head = ['#', D.item.one.charAt(0).toUpperCase() + D.item.one.slice(1), 'Indicator', 'Class', 'Before', 'After', 'Change', 'Verdict'];
    table.appendChild(el('thead', null, [el('tr', null, head.map(function (h) { return el('th', { scope: 'col', text: h }); }))]));
    var body = el('tbody');
    shown.forEach(function (row, i) {
      var pair = pairOf(row.item, row.ind, k);
      var tr = el('tr', { cls: 'clickable', tabindex: '0', 'data-item': row.item.id }, [
        el('td', { cls: 'num', text: String(i + 1) }),
        el('td', { text: row.item.name + (row.item.place ? ' (' + row.item.place + ')' : '') }),
        el('td', { text: indicatorName(row.ind) }),
        el('td', { text: row.item.classes[row.ind][k] }),
        el('td', { cls: 'num', text: formatNumber(pair[0]), title: String(pair[0]) }),
        el('td', { cls: 'num', text: formatNumber(pair[1]), title: String(pair[1]) }),
        cell(row.item, row.ind, k),
        el('td', { text: verdictOf(row.item, row.ind, k) || '—' })
      ]);
      body.appendChild(tr);
    });
    table.appendChild(body);
  }

  function gridRows() {
    var k = stepIndex(view.comp);
    var find = view.find.toLowerCase();
    return D.items.filter(function (item) {
      if (find && (item.name + ' ' + (item.place || '') + ' ' + item.id).toLowerCase().indexOf(find) < 0) return false;
      if (view.group && item.group !== view.group) return false;
      var ids = D.indicators.map(function (i) { return i.id; });
      if (view.cls && !ids.some(function (id) { return item.classes[id][k] === view.cls; })) return false;
      if (view.verdict && !ids.some(function (id) { return verdictOf(item, id, k) === view.verdict; })) return false;
      if (view.size && !ids.some(function (id) { return QUIET.indexOf(item.classes[id][k]) < 0 && sizeAtLeast(item.classes[id][k], item.bands[id][k], view.size); })) return false;
      return true;
    });
  }

  function renderGrid() {
    var k = stepIndex(view.comp);
    var rows = gridRows();
    var shown = rows.slice(0, view.limit);
    var c = D.items_count;
    q('grid-said').textContent = D.tier === 'counts'
      ? 'This file holds counts only: it names no ' + D.item.one + '.'
      : 'Showing ' + shown.length + ' of ' + rows.length + ' ' + D.item.many + ' (' + groupThousands(c.listed) + ' in this file' +
        (c.not_listed ? '; ' + groupThousands(c.not_listed) + ' more worth a look are not in it' : '') + '). ' + compLabel(view.comp) + '.' + sizeSaid();
    var table = clear(q('grid-table'));
    var head = [el('th', { scope: 'col', text: D.item.one.charAt(0).toUpperCase() + D.item.one.slice(1) }), el('th', { scope: 'col', text: 'Unit' })];
    D.indicators.forEach(function (ind) { head.push(el('th', { scope: 'col', cls: 'num', text: indicatorName(ind.id), title: ind.name + (ind.unit ? ' (' + ind.unit + ')' : '') })); });
    table.appendChild(el('thead', null, [el('tr', null, head)]));
    var body = el('tbody');
    shown.forEach(function (item) {
      var row = [el('th', { scope: 'row', text: item.name + (item.place ? ' (' + item.place + ')' : '') }), el('td', { text: item.unit || '?' })];
      D.indicators.forEach(function (ind) { row.push(cell(item, ind.id, k)); });
      body.appendChild(el('tr', { cls: 'clickable', tabindex: '0', 'data-item': item.id }, row));
    });
    table.appendChild(body);
    var more = q('grid-more');
    more.hidden = rows.length <= shown.length;
    more.textContent = 'Show ' + Math.min(100, rows.length - shown.length) + ' more';
  }

  function sizeSaid() {
    return view.size ? ' Only changes by a factor of at least ' + view.size + ' are shown, with every zero, sign change and missing value: a filter of yours, which changes no count.' : '';
  }

  function fillSelect(select, options, chosen) {
    clear(select);
    options.forEach(function (o) { select.appendChild(el('option', { value: o[0], text: o[1] })); });
    select.value = chosen;
  }

  function renderFilters() {
    var k = stepIndex(view.comp);
    var classes = {}, verdicts = {}, groups = {};
    D.items.forEach(function (item) {
      D.indicators.forEach(function (ind) {
        classes[item.classes[ind.id][k]] = 1;
        var v = verdictOf(item, ind.id, k);
        if (v) verdicts[v] = 1;
      });
      if (item.group) groups[item.group] = 1;
    });
    fillSelect(q('grid-class'), [['', 'Any']].concat(Object.keys(classes).sort().map(function (c) { return [c, c]; })), view.cls);
    fillSelect(q('grid-verdict'), [['', 'Any']].concat(Object.keys(verdicts).sort().map(function (c) { return [c, c]; })), view.verdict);
    fillSelect(q('grid-group'), [['', 'Any']].concat(Object.keys(groups).sort().map(function (c) { return [c, c]; })), view.group);
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

  function explanationNode(one) {
    var about = [];
    if (one.about.step) about.push(one.about.step === 'total' ? 'the whole way' : 'step ' + D.steps[stepIndex(one.about.step)].label);
    if (one.about.indicator) about.push(indicatorName(one.about.indicator));
    if (one.about.item) {
      var item = D.items.filter(function (i) { return i.id === one.about.item; })[0];
      about.push(item ? item.name : one.about.item);
    }
    return el('li', null, [
      badge(one.by), el('span', { cls: 'quiet', text: 'About ' + about.join(', ') + '. ' }),
      one.finding === 'none found' ? el('strong', { text: 'Looked, found no reason: ' }) : null, one.text,
      one.not_checked ? el('div', { cls: 'quiet', text: 'Not checked: ' + one.not_checked }) : null,
      one.source ? el('div', { cls: 'quiet' }, [one.source.link ? el('a', { href: one.source.link, text: one.source.link }) : null, one.source.doc ? ' ' + one.source.doc : null]) : null
    ]);
  }

  function renderExplanations() {
    var list = clear(q('explanation-list'));
    if (!D.explanations.length) list.appendChild(el('li', { cls: 'quiet', text: 'The file holds no explanation.' }));
    D.explanations.forEach(function (one) { list.appendChild(explanationNode(one)); });
  }

  function renderRule() {
    var body = clear(q('rule-body'));
    body.appendChild(el('p', null, ['Every value is put into one class by one rule, in this order: missing, near zero, zero reference, zero result, sign change, agrees, within noise, beyond 10x, differs. ' +
      'Direction is up where the result after is larger as a signed number, down otherwise; colour follows the direction only. ' +
      'Beyond 10x: one size more than ' + D.rule.beyond + ' times the other. The whole way is counted with a tolerance of ' + D.rule.total_tolerance + ', the largest of the steps.']));
    var stepsTable = el('table', null, [el('thead', null, [el('tr', null, ['Step', 'Tolerance', 'Basis', 'Note', 'Noise'].map(function (h) { return el('th', { scope: 'col', text: h }); }))])]);
    var tb = el('tbody');
    D.steps.forEach(function (s) {
      var noise = s.noise.measured ? Object.keys(s.noise.by).map(function (k) { return indicatorName(k) + ' ' + formatNumber(s.noise.by[k]); }).join(', ') + ' (between ' + s.noise.between.join(' and ') + ')' : 'not measured';
      tb.appendChild(el('tr', null, [el('td', { text: s.label }), el('td', { cls: 'num', text: String(s.tolerance.value) }), el('td', { text: s.tolerance.basis }), el('td', { text: s.tolerance.note || '' }), el('td', { text: noise })]));
    });
    stepsTable.appendChild(tb);
    body.appendChild(el('div', { cls: 'table-wrap' }, [stepsTable]));
    body.appendChild(el('h3', { text: 'Floors' }));
    body.appendChild(el('p', { cls: 'quiet', text: 'One floor per indicator and reference unit: ' + D.rule.floor_factor + ' times the median size of the results of ' + D.states[stepIndex2(D.rule.floors_from)].label + ' in that unit, unless declared. Units are never pooled.' }));
    var floors = el('table', null, [el('thead', null, [el('tr', null, ['Indicator', 'Unit', 'Floor', 'Basis', 'From results'].map(function (h) { return el('th', { scope: 'col', text: h }); }))])]);
    var fb = el('tbody');
    D.rule.floors.forEach(function (f) {
      fb.appendChild(el('tr', null, [el('td', { text: indicatorName(f.indicator) }), el('td', { text: f.unit || 'unknown' }), el('td', { cls: 'num', text: formatNumber(f.value), title: String(f.value) }), el('td', { text: f.basis }), el('td', { cls: 'num', text: n(f.n) })]));
    });
    floors.appendChild(fb);
    body.appendChild(el('div', { cls: 'table-wrap' }, [floors]));
    var notes = clear(q('notes'));
    D.notes.forEach(function (text) { notes.appendChild(el('li', { text: text })); });
    if (!D.notes.length) notes.appendChild(el('li', { cls: 'quiet', text: 'None.' }));
  }
  function stepIndex2(stateId) {
    for (var i = 0; i < D.states.length; i++) if (D.states[i].id === stateId) return i;
    return 0;
  }

  function renderItem(id) {
    var item = D.items.filter(function (i) { return i.id === id; })[0];
    var section = q('item');
    if (!item) { section.hidden = true; return; }
    section.hidden = false;
    q('item-title').textContent = item.name;
    q('item-close').onclick = function () { section.hidden = true; history.replaceState(null, '', location.pathname + location.search + '#grid'); };
    q('item-meta').textContent = [item.id, item.place, item.group, item.unit ? 'per ' + item.unit : 'unit unknown'].filter(Boolean).join(' · ');
    var body = clear(q('item-body'));
    D.indicators.forEach(function (ind) {
      var values = item.values[ind.id];
      var first = values[0], last = values[values.length - 1];
      var whole = first !== null && last !== null ? last - first : null;
      var totalCls = item.classes[ind.id][D.steps.length];
      body.appendChild(el('h3', { text: ind.name + (ind.unit ? ' (' + ind.unit + ' per ' + (item.unit || 'unit') + ')' : '') }));
      var table = el('table', null, [el('thead', null, [el('tr', null, ['Step', 'Before', 'After', 'Change', 'Verdict', 'Share of the whole difference'].map(function (h) { return el('th', { scope: 'col', text: h }); }))])]);
      var tb = el('tbody');
      var unexplained = 0, splittable = whole !== null && MOVES.indexOf(totalCls) >= 0;
      D.steps.forEach(function (s, k) {
        var b = values[k], a = values[k + 1];
        var share = '—';
        if (splittable && b !== null && a !== null) {
          var part = (a - b) / whole;
          share = shareText(part);
          if (!s.explained) unexplained += part;
        } else if (splittable) {
          splittable = false;
        }
        tb.appendChild(el('tr', null, [
          el('td', null, ['Step ' + k + ': ' + s.label, s.explained ? null : el('div', { cls: 'error', text: 'nothing explains it' })]),
          el('td', { cls: 'num', text: formatNumber(b), title: String(b) }),
          el('td', { cls: 'num', text: formatNumber(a), title: String(a) }),
          cell(item, ind.id, k),
          el('td', { text: verdictOf(item, ind.id, k) || '—' }),
          el('td', { cls: 'num', text: share })
        ]));
      });
      tb.appendChild(el('tr', null, [
        el('th', { scope: 'row', text: 'The whole way' }),
        el('td', { cls: 'num', text: formatNumber(first), title: String(first) }),
        el('td', { cls: 'num', text: formatNumber(last), title: String(last) }),
        cell(item, ind.id, D.steps.length),
        el('td', { text: '—' }),
        el('td', { cls: 'num', text: MOVES.indexOf(totalCls) < 0 ? 'not split: it did not move' : splittable ? '100 %' + (unexplained ? ', of which nothing explains ' + shareText(unexplained) : '') : 'not split: missing in a state between' })
      ]));
      table.appendChild(tb);
      body.appendChild(el('div', { cls: 'table-wrap' }, [table]));
    });
    var mine = D.explanations.filter(function (e) { return e.about.item === item.id; });
    if (mine.length) {
      body.appendChild(el('h3', { text: 'Explanations' }));
      body.appendChild(el('ul', { cls: 'plain' }, mine.map(explanationNode)));
    }
    Object.keys(item.breakdowns || {}).forEach(function (comp) {
      var name = item.breakdowns[comp];
      var holder = el('div');
      body.appendChild(el('h3', { text: 'What it is made of: ' + compLabel(comp) }));
      body.appendChild(holder);
      var found = B[name];
      if (found) { breakdownInto(holder, found); return; }
      holder.appendChild(el('p', { cls: 'quiet', text: 'The breakdown ' + name + ' is not with this page.' }));
      if (location.protocol === 'http:' || location.protocol === 'https:') {
        fetch(name).then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
          .then(function (data) { if (data.format !== 'sentier-diagnostics-breakdown/1' || data.item !== item.id) throw new Error(); clear(holder); breakdownInto(holder, data); })
          .catch(function () { /* the sentence above stays */ });
      }
    });
    section.scrollIntoView({ block: 'start' });
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
      holder.appendChild(el('div', { cls: 'table-wrap' }, [table]));
      var cover = function (side) {
        var listed = entry.parts.reduce(function (a, p) { return a + p.values[side]; }, 0);
        return entry.total[side] ? shareText(listed / entry.total[side]) : 'none (the total is 0)';
      };
      holder.appendChild(el('p', { cls: 'quiet', text: (entry.parts_not_listed
        ? 'The first ' + entry.parts.length + ' parts make ' + cover(0) + ' of the total before and ' + cover(1) + ' after; the other ' + entry.parts_not_listed + ' are summed in one line. '
        : 'Every part is listed. ') +
        'Parts are listed by the larger of their two sizes, so that a part large on one side only is listed. The listed parts and the others add up to the total.' }));
    });
  }

  function renderComparison() {
    renderFilters();
    renderDistributions();
    renderWorst();
    renderGrid();
  }

  function show(data) {
    var problem = checkShape(data);
    if (problem) {
      q('load').hidden = false;
      q('content').hidden = true;
      q('load-error').textContent = problem;
      return;
    }
    D = data;
    view.comp = 'total';
    q('load').hidden = true;
    q('content').hidden = false;
    renderHeader();
    renderSteps();
    renderExplanations();
    renderRule();
    legend(q('grid-legend'));
    legend(q('dist-legend'));
    renderComparison();
    route();
  }

  function route() {
    var hash = decodeURIComponent(location.hash.slice(1));
    if (hash.indexOf('item=') === 0) renderItem(hash.slice(5));
  }

  function openFrom(event) {
    var row = event.target.closest ? event.target.closest('tr[data-item]') : null;
    if (row) location.hash = 'item=' + encodeURIComponent(row.getAttribute('data-item'));
  }

  function start() {
    B = root.SENTIER_DIAGNOSTICS_BREAKDOWNS || {};
    q('comparison').addEventListener('change', function (e) { view.comp = e.target.value; view.cls = ''; view.verdict = ''; view.limit = 100; renderComparison(); });
    q('size').addEventListener('change', function (e) { view.size = +e.target.value; view.limit = 100; renderWorst(); renderGrid(); });
    q('worst-n').addEventListener('change', function (e) { view.worstN = +e.target.value; renderWorst(); });
    q('worst-indicator').addEventListener('change', function (e) { view.worstIndicator = e.target.value; renderWorst(); });
    q('grid-find').addEventListener('input', function (e) { view.find = e.target.value; view.limit = 100; renderGrid(); });
    q('grid-class').addEventListener('change', function (e) { view.cls = e.target.value; view.limit = 100; renderGrid(); });
    q('grid-verdict').addEventListener('change', function (e) { view.verdict = e.target.value; view.limit = 100; renderGrid(); });
    q('grid-group').addEventListener('change', function (e) { view.group = e.target.value; view.limit = 100; renderGrid(); });
    q('grid-more').addEventListener('click', function () { view.limit += 100; renderGrid(); });
    ['grid-table', 'worst-table'].forEach(function (id) {
      q(id).addEventListener('click', openFrom);
      q(id).addEventListener('keydown', function (e) { if (e.key === 'Enter') openFrom(e); });
    });
    window.addEventListener('hashchange', route);
    q('file').addEventListener('change', function (e) {
      var file = e.target.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () {
        try { show(JSON.parse(reader.result)); } catch (error) { q('load-error').textContent = 'The file is not JSON: ' + error.message; }
      };
      reader.readAsText(file);
    });
    if (root.SENTIER_DIAGNOSTICS) { show(root.SENTIER_DIAGNOSTICS); return; }
    var wanted = new URLSearchParams(location.search).get('file');
    if (wanted && /^[A-Za-z0-9][A-Za-z0-9._\/-]*\.json$/.test(wanted) && wanted.indexOf('..') < 0 && location.protocol.indexOf('http') === 0) {
      fetch(wanted).then(function (r) { return r.json(); }).then(show).catch(function () {
        q('load').hidden = false; q('load-error').textContent = 'Could not read ' + wanted + '.';
      });
      return;
    }
    q('load').hidden = false;
  }

  var api = { formatNumber: formatNumber, percentText: percentText, shareText: shareText, sizeAtLeast: sizeAtLeast, cellView: cellView, severityKey: severityKey,
    compareKeys: compareKeys, bandStep: bandStep, checkShape: checkShape, RANK: RANK };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
  }
})(typeof window !== 'undefined' ? window : this);
