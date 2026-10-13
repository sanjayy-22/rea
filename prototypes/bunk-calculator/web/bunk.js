/*
 * Bunk Calculator core.
 *
 * Everything lives inside BunkModule so the whole module can be serialized
 * into a bookmarklet (`javascript:(<BunkModule source>)().overlay()`) without
 * depending on anything outside its own closure.
 */
function BunkModule() {
  'use strict';

  var FULL = 10000; // 100% expressed in basis points

  // Percentages are compared in integer basis points so cases such as
  // 18/24 at 75% land exactly on the boundary instead of on 0.7499999.
  function calc(attended, total, targetPercent) {
    var a = Number(attended);
    var t = Number(total);
    var p = Math.round(Number(targetPercent) * 100);
    if (!Number.isInteger(a) || !Number.isInteger(t) || a < 0 || t < 0 || a > t) {
      return { error: 'attended and total must be whole numbers with attended <= total' };
    }
    if (!(p >= 0 && p <= FULL)) {
      return { error: 'target must be between 0 and 100' };
    }
    var result = { attended: a, total: t, target: p / 100, percent: t === 0 ? null : (a * 100) / t };
    if (FULL * a >= p * t) {
      // Largest k with a / (t + k) >= target.
      result.status = 'safe';
      result.canSkip = p === 0 ? Infinity : Math.floor((FULL * a - p * t) / p);
      result.mustAttend = 0;
    } else if (p === FULL) {
      // Once a class is missed, 100% can never be reached again.
      result.status = 'impossible';
      result.canSkip = 0;
      result.mustAttend = Infinity;
    } else {
      // Smallest n with (a + n) / (t + n) >= target.
      result.status = 'short';
      result.canSkip = 0;
      result.mustAttend = Math.ceil((p * t - FULL * a) / (FULL - p));
    }
    return result;
  }

  function summarize(subjects, targetPercent) {
    var attended = 0;
    var total = 0;
    var rows = subjects.map(function (s) {
      attended += s.attended;
      total += s.total;
      var r = calc(s.attended, s.total, targetPercent);
      r.subject = s.subject;
      return r;
    });
    var overall = calc(attended, total, targetPercent);
    overall.subject = 'Overall';
    return { subjects: rows, overall: overall };
  }

  function describe(r) {
    if (r.error) return r.error;
    if (r.status === 'impossible') return 'Cannot reach 100% any more';
    if (r.status === 'short') return 'Attend the next ' + r.mustAttend + ' to reach ' + r.target + '%';
    if (r.canSkip === Infinity) return 'No minimum set';
    if (r.canSkip === 0) return 'On the edge: do not skip the next class';
    return 'You can skip ' + r.canSkip + ' more';
  }

  // ---- Table recognition -------------------------------------------------

  function role(header) {
    var h = String(header).toLowerCase().replace(/\s+/g, ' ').trim();
    if (!h) return null;
    if (/%|percent|perc\b|ratio/.test(h)) return 'percent';
    if (/absent|\bab\b|missed|bunked/.test(h)) return 'absent';
    if (/attend|present|\bpr\b/.test(h)) return 'attended';
    if (/total|held|conducted|delivered|taken|classes|lectures|sessions|periods|hours/.test(h)) return 'total';
    if (/code/.test(h)) return 'code'; // before 'subject': "Course Code" is not the name
    if (/subject|course|paper|name|title/.test(h)) return 'subject';
    return null;
  }

  function toInt(cell) {
    var m = /^\s*(\d+)\s*$/.exec(String(cell));
    return m ? Number(m[1]) : null;
  }

  function toRatio(cell) {
    var m = /^\s*(\d+)\s*\/\s*(\d+)\b/.exec(String(cell));
    return m ? { attended: Number(m[1]), total: Number(m[2]) } : null;
  }

  var AGGREGATE = /^(grand\s+)?total\b|^overall\b|^aggregate\b/i;

  function findHeader(rows) {
    for (var i = 0; i < rows.length; i++) {
      var roles = rows[i].map(role);
      var hasCount = roles.indexOf('attended') >= 0 || roles.indexOf('total') >= 0 || roles.indexOf('absent') >= 0;
      var hasName = roles.indexOf('subject') >= 0 || roles.indexOf('code') >= 0;
      if (hasCount && hasName) return { index: i, roles: roles };
    }
    return null;
  }

  function column(roles, name) {
    return roles.indexOf(name);
  }

  function fromHeaderRow(cells, roles) {
    var nameCol = column(roles, 'subject') >= 0 ? column(roles, 'subject') : column(roles, 'code');
    var subject = String(cells[nameCol] || '').trim();
    var aCol = column(roles, 'attended');
    var tCol = column(roles, 'total');
    var xCol = column(roles, 'absent');
    var ratio = aCol >= 0 ? toRatio(cells[aCol]) : null;
    var a = ratio ? ratio.attended : aCol >= 0 ? toInt(cells[aCol]) : null;
    var t = ratio ? ratio.total : tCol >= 0 ? toInt(cells[tCol]) : null;
    var x = xCol >= 0 ? toInt(cells[xCol]) : null;
    if (a === null && t !== null && x !== null) a = t - x;
    if (t === null && a !== null && x !== null) t = a + x;
    return { subject: subject, attended: a, total: t };
  }

  // Header-less fallback: "Maths 18/24", "Maths, 18, 24", "Maths 18 24".
  function fromBareRow(cells) {
    var subject = '';
    var numbers = [];
    var ratio = null;
    cells.forEach(function (c) {
      var r = toRatio(c);
      var n = toInt(c);
      if (r && !ratio) ratio = r;
      else if (n !== null) numbers.push(n);
      else if (!subject && String(c).trim()) subject = String(c).trim();
    });
    if (ratio) return { subject: subject, attended: ratio.attended, total: ratio.total };
    if (numbers.length < 2) return { subject: subject, attended: null, total: null };
    var last = numbers.slice(-2);
    return { subject: subject, attended: Math.min(last[0], last[1]), total: Math.max(last[0], last[1]) };
  }

  function parseRows(rows) {
    var header = findHeader(rows);
    var body = header ? rows.slice(header.index + 1) : rows;
    var out = [];
    body.forEach(function (cells) {
      var s = header ? fromHeaderRow(cells, header.roles) : fromBareRow(cells);
      if (!s.subject || AGGREGATE.test(s.subject)) return;
      if (s.attended === null || s.total === null || s.attended > s.total) return;
      out.push(s);
    });
    return out;
  }

  function parseText(text) {
    var rows = String(text)
      .split(/\r?\n/)
      .filter(function (line) { return line.trim(); })
      .map(function (line) {
        if (line.indexOf('\t') >= 0) return line.split('\t');
        if (/,/.test(line) && !/\d\s*\/\s*\d/.test(line)) return line.split(',');
        if (/ {2,}/.test(line.trim())) return line.trim().split(/ {2,}/);
        // "Data Structures 18/24" or "Data Structures 18 24": peel numbers off the end.
        var m = /^(.*?)\s+(\d+\s*\/\s*\d+|\d+\s+\d+)\s*$/.exec(line.trim());
        if (m) return [m[1]].concat(m[2].indexOf('/') >= 0 ? [m[2]] : m[2].split(/\s+/));
        return [line];
      })
      .map(function (cells) { return cells.map(function (c) { return c.trim(); }); });
    return parseRows(rows);
  }

  function tableRows(table) {
    return Array.prototype.map.call(table.rows, function (tr) {
      return Array.prototype.map.call(tr.cells, function (td) { return td.textContent.trim(); });
    });
  }

  function documentsOf(win) {
    var docs = [win.document];
    for (var i = 0; i < win.frames.length; i++) {
      try { docs = docs.concat(documentsOf(win.frames[i])); } catch (e) { /* cross-origin frame */ }
    }
    return docs;
  }

  // Picks the table on the page (or same-origin frames) yielding the most subjects.
  function scanPage(win) {
    var best = [];
    documentsOf(win).forEach(function (doc) {
      Array.prototype.forEach.call(doc.querySelectorAll('table'), function (table) {
        var found = parseRows(tableRows(table));
        if (found.length > best.length) best = found;
      });
    });
    return best;
  }

  // ---- Bookmarklet overlay -----------------------------------------------

  function el(tag, text, style) {
    var node = document.createElement(tag);
    if (text !== undefined) node.textContent = text; // never innerHTML: portal text is untrusted
    if (style) node.setAttribute('style', style);
    return node;
  }

  function overlay() {
    var old = document.getElementById('bunk-overlay');
    if (old) old.remove();
    var subjects = scanPage(window);
    var box = el('div', undefined,
      'position:fixed;top:12px;right:12px;z-index:2147483647;max-width:min(440px,calc(100vw - 24px));' +
      'max-height:80vh;overflow:auto;background:#fff;color:#111;font:14px/1.4 system-ui,sans-serif;' +
      'border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.3);padding:14px');
    box.id = 'bunk-overlay';
    var bar = el('div', undefined, 'display:flex;gap:8px;align-items:center;margin-bottom:8px');
    bar.appendChild(el('strong', 'Bunk Calculator', 'flex:1'));
    var input = el('input', undefined, 'width:56px');
    input.type = 'number';
    input.min = '0';
    input.max = '100';
    input.value = '75';
    bar.appendChild(input);
    bar.appendChild(el('span', '%'));
    var close = el('button', '×', 'border:0;background:none;font-size:20px;cursor:pointer');
    close.onclick = function () { box.remove(); };
    bar.appendChild(close);
    box.appendChild(bar);
    var list = el('div');
    box.appendChild(list);

    function render() {
      list.textContent = '';
      if (!subjects.length) {
        list.appendChild(el('p', 'No attendance table found on this page. Open the page that lists your subject-wise attendance, then click the bookmarklet again.'));
        return;
      }
      var s = summarize(subjects, Number(input.value) || 0);
      s.subjects.concat([s.overall]).forEach(function (r) {
        var color = r.status !== 'safe' ? '#b42318' : r.canSkip === 0 ? '#a15c00' : '#0a7d32';
        var row = el('div', undefined, 'padding:6px 0;border-top:1px solid #eee');
        var pct = r.percent === null ? '–' : r.percent.toFixed(1) + '%';
        row.appendChild(el('div', r.subject + '  ·  ' + r.attended + '/' + r.total + '  ·  ' + pct, 'font-weight:600'));
        row.appendChild(el('div', describe(r), 'color:' + color));
        list.appendChild(row);
      });
    }
    input.oninput = render;
    render();
    document.body.appendChild(box);
  }

  return {
    calc: calc,
    summarize: summarize,
    describe: describe,
    role: role,
    parseRows: parseRows,
    parseText: parseText,
    scanPage: scanPage,
    overlay: overlay
  };
}

var Bunk = BunkModule();
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Bunk;
  module.exports.BunkModule = BunkModule;
}
