// Run with: node --test prototypes/bunk-calculator/web/
const test = require('node:test');
const assert = require('node:assert/strict');
const Bunk = require('./bunk.js');

test('calc matches the brute-force definition', () => {
  for (const p of [50, 60, 65, 75, 80, 85, 99]) {
    for (let t = 0; t < 40; t++) {
      for (let a = 0; a <= t; a++) {
        const r = Bunk.calc(a, t, p);
        if (r.status === 'safe') {
          let k = 0;
          while (100 * a >= p * (t + k + 1)) k++;
          assert.equal(r.canSkip, k, `${a}/${t}@${p}`);
        } else {
          let n = 0;
          while (100 * (a + n) < p * (t + n)) n++;
          assert.equal(r.mustAttend, n, `${a}/${t}@${p}`);
        }
      }
    }
  }
});

test('edge cases', () => {
  assert.equal(Bunk.calc(18, 24, 75).canSkip, 0);
  assert.equal(Bunk.calc(9, 10, 100).status, 'impossible');
  assert.equal(Bunk.calc(5, 10, 0).canSkip, Infinity);
  assert.ok(Bunk.calc(5, 4, 75).error);
});

const triples = (xs) => xs.map((s) => [s.subject, s.attended, s.total]);
const EXPECTED = [['Data Structures', 18, 24], ['Operating Systems', 30, 36], ['Discrete Maths', 17, 28]];

test('parseText handles bare lines', () => {
  assert.deepEqual(triples(Bunk.parseText('Data Structures 18/24\nOperating Systems 30 36\nDiscrete Maths, 17, 28')), EXPECTED);
});

test('parseText handles a table copied from a browser', () => {
  const text = 'Course Code\tCourse Name\tClasses Held\tClasses Attended\tAttendance %\n' +
    'CS201\tData Structures\t24\t18\t75.00\nCS202\tOperating Systems\t36\t30\t83.33\n' +
    'MA201\tDiscrete Maths\t28\t17\t60.71\n\tTotal\t88\t65\t73.86';
  assert.deepEqual(triples(Bunk.parseText(text)), EXPECTED);
});

test('bookmarklet source is self-contained', () => {
  // The bookmarklet is BunkModule serialized; evaluating it without the outer scope must work.
  const fresh = new Function('return (' + Bunk.BunkModule.toString() + ')()')();
  assert.equal(fresh.calc(20, 24, 75).canSkip, 2);
  const url = 'javascript:' + encodeURIComponent('(' + Bunk.BunkModule.toString() + ')().overlay();void 0');
  assert.ok(url.length < 64000, `bookmarklet is ${url.length} chars`);
});
