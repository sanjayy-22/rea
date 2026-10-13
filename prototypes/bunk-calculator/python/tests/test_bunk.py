import json
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
FIXTURES = HERE.parent / "fixtures"

import bunk  # noqa: E402


def brute_skip(a, t, p):
    k = 0
    while 100 * a >= p * (t + k + 1):
        k += 1
    return k


def brute_attend(a, t, p):
    n = 0
    while 100 * (a + n) < p * (t + n):
        n += 1
    return n


class CalcTest(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(bunk.calc(18, 24, 75).can_skip, 0)  # exactly 75%
        self.assertEqual(bunk.calc(20, 24, 75).can_skip, 2)  # 20/26 ok, 20/27 not
        self.assertEqual(bunk.calc(15, 24, 75).must_attend, 12)  # 27/36
        self.assertEqual(bunk.calc(0, 0, 75).status, "safe")
        self.assertEqual(bunk.calc(9, 10, 100).status, "impossible")
        self.assertEqual(bunk.calc(5, 10, 0).can_skip, math.inf)

    def test_matches_definition(self):
        for p in (50, 60, 65, 75, 80, 85, 99):
            for t in range(0, 40):
                for a in range(0, t + 1):
                    r = bunk.calc(a, t, p)
                    if r.status == "safe":
                        self.assertEqual(r.can_skip, brute_skip(a, t, p), (a, t, p))
                    else:
                        self.assertEqual(r.must_attend, brute_attend(a, t, p), (a, t, p))

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            bunk.calc(5, 4, 75)
        with self.assertRaises(ValueError):
            bunk.calc(1, 4, 101)


EXPECTED = [("Data Structures", 18, 24), ("Operating Systems", 30, 36), ("Discrete Maths", 17, 28)]


def triples(subjects):
    return [(s.subject, s.attended, s.total) for s in subjects]


class ParseTest(unittest.TestCase):
    def test_html_picks_attendance_table_and_drops_total_row(self):
        self.assertEqual(triples(bunk.parse_html((FIXTURES / "attendance.html").read_text())), EXPECTED)

    def test_json(self):
        self.assertEqual(triples(bunk.parse_json(json.loads((FIXTURES / "attendance.json").read_text()))), EXPECTED)

    def test_text(self):
        self.assertEqual(triples(bunk.parse_text((FIXTURES / "attendance.txt").read_text())), EXPECTED)

    def test_tab_separated_copy_from_browser(self):
        text = "Subject\tHeld\tAttended\tAttendance %\nPhysics\t20\t15\t75\nChemistry\t20\t12\t60\n"
        self.assertEqual(triples(bunk.parse_text(text)), [("Physics", 15, 20), ("Chemistry", 12, 20)])

    def test_absent_only_columns(self):
        rows = [["Subject", "Total", "Absent"], ["Physics", "20", "5"]]
        self.assertEqual(triples(bunk.parse_rows(rows)), [("Physics", 15, 20)])

    def test_har_reports_source_url(self):
        subjects, url = bunk.parse_har(json.loads((FIXTURES / "portal.har").read_text()))
        self.assertEqual(triples(subjects), EXPECTED)
        self.assertEqual(url, "https://portal.example.edu/api/attendance/summary")


class CliTest(unittest.TestCase):
    def test_exit_code_signals_shortfall(self):
        self.assertEqual(bunk.main(["text", str(FIXTURES / "attendance.txt"), "--target", "75"]), 1)
        self.assertEqual(bunk.main(["text", str(FIXTURES / "attendance.txt"), "--target", "50"]), 0)


if __name__ == "__main__":
    unittest.main()
