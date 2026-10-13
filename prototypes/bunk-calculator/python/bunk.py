#!/usr/bin/env python3
"""Bunk Calculator: attendance math plus three ways to load data from a portal.

  python bunk.py text  attendance.txt         # pasted/copied table
  python bunk.py har   portal.har             # DevTools "Save all as HAR"
  python bunk.py live  config.json [--notify] # log in and fetch (read-only)

Standard library only. See README.md for the portal config format.
"""

from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

FULL = 10_000  # 100% in basis points


@dataclass
class Subject:
    subject: str
    attended: int
    total: int


@dataclass
class Result:
    subject: str
    attended: int
    total: int
    target: float
    percent: float | None
    status: str  # safe | short | impossible
    can_skip: float  # int, or math.inf when the target is 0
    must_attend: float  # int, or math.inf when the target is 100 and a class was missed

    def describe(self) -> str:
        if self.status == "impossible":
            return "Cannot reach 100% any more"
        if self.status == "short":
            return f"Attend the next {self.must_attend} to reach {self.target:g}%"
        if self.can_skip == math.inf:
            return "No minimum set"
        if self.can_skip == 0:
            return "On the edge: do not skip the next class"
        return f"You can skip {self.can_skip} more"


def calc(attended: int, total: int, target_percent: float, subject: str = "") -> Result:
    """Integer basis-point math so 18/24 at 75% is exactly on the boundary."""
    if attended < 0 or total < 0 or attended > total:
        raise ValueError(f"{subject or 'subject'}: need 0 <= attended <= total, got {attended}/{total}")
    p = round(target_percent * 100)
    if not 0 <= p <= FULL:
        raise ValueError("target must be between 0 and 100")
    percent = None if total == 0 else attended * 100 / total
    base = dict(subject=subject, attended=attended, total=total, target=p / 100, percent=percent)
    if FULL * attended >= p * total:
        can_skip = math.inf if p == 0 else (FULL * attended - p * total) // p
        return Result(**base, status="safe", can_skip=can_skip, must_attend=0)
    if p == FULL:
        return Result(**base, status="impossible", can_skip=0, must_attend=math.inf)
    # Ceiling division on integers.
    must = -((FULL * attended - p * total) // (FULL - p))
    return Result(**base, status="short", can_skip=0, must_attend=must)


def summarize(subjects: list[Subject], target: float) -> tuple[list[Result], Result]:
    rows = [calc(s.attended, s.total, target, s.subject) for s in subjects]
    overall = calc(sum(s.attended for s in subjects), sum(s.total for s in subjects), target, "Overall")
    return rows, overall


# ---- Recognising attendance tables (mirrors web/bunk.js) -------------------


def role(header: str) -> str | None:
    h = " ".join(str(header).lower().split())
    if not h:
        return None
    if re.search(r"%|percent|perc\b|ratio", h):
        return "percent"
    if re.search(r"absent|\bab\b|missed|bunked", h):
        return "absent"
    if re.search(r"attend|present|\bpr\b", h):
        return "attended"
    if re.search(r"total|held|conducted|delivered|taken|classes|lectures|sessions|periods|hours", h):
        return "total"
    if "code" in h:  # before "subject": "Course Code" is not the name
        return "code"
    if re.search(r"subject|course|paper|name|title", h):
        return "subject"
    return None


def _int(cell) -> int | None:
    if isinstance(cell, bool):
        return None
    if isinstance(cell, int):
        return cell if cell >= 0 else None
    if isinstance(cell, float):
        return int(cell) if cell.is_integer() and cell >= 0 else None
    m = re.fullmatch(r"\s*(\d+)\s*", str(cell))
    return int(m.group(1)) if m else None


def _ratio(cell) -> tuple[int, int] | None:
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)\b", str(cell))
    return (int(m.group(1)), int(m.group(2))) if m else None


AGGREGATE = re.compile(r"^(grand\s+)?total\b|^overall\b|^aggregate\b", re.I)


def _from_roles(cells: list, roles: list[str | None]) -> tuple[str, int | None, int | None]:
    def col(name: str) -> int:
        return roles.index(name) if name in roles else -1

    name_col = col("subject") if col("subject") >= 0 else col("code")
    subject = str(cells[name_col]).strip() if 0 <= name_col < len(cells) else ""

    def cell(name: str):
        i = col(name)
        return cells[i] if 0 <= i < len(cells) else None

    ratio = _ratio(cell("attended")) if cell("attended") is not None else None
    a = ratio[0] if ratio else _int(cell("attended")) if cell("attended") is not None else None
    t = ratio[1] if ratio else _int(cell("total")) if cell("total") is not None else None
    x = _int(cell("absent")) if cell("absent") is not None else None
    if a is None and t is not None and x is not None:
        a = t - x
    if t is None and a is not None and x is not None:
        t = a + x
    return subject, a, t


def _from_bare(cells: list) -> tuple[str, int | None, int | None]:
    subject, numbers, ratio = "", [], None
    for c in cells:
        r, n = _ratio(c), _int(c)
        if r and not ratio:
            ratio = r
        elif n is not None:
            numbers.append(n)
        elif not subject and str(c).strip():
            subject = str(c).strip()
    if ratio:
        return subject, ratio[0], ratio[1]
    if len(numbers) < 2:
        return subject, None, None
    x, y = numbers[-2:]
    return subject, min(x, y), max(x, y)


def parse_rows(rows: list[list]) -> list[Subject]:
    header = None
    for i, cells in enumerate(rows):
        roles = [role(c) for c in cells]
        if {"attended", "total", "absent"} & set(roles) and {"subject", "code"} & set(roles):
            header = (i, roles)
            break
    body = rows[header[0] + 1 :] if header else rows
    out = []
    for cells in body:
        subject, a, t = _from_roles(cells, header[1]) if header else _from_bare(cells)
        if subject and not AGGREGATE.match(subject) and a is not None and t is not None and a <= t:
            out.append(Subject(subject, a, t))
    return out


def parse_text(text: str) -> list[Subject]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "\t" in line:
            cells = line.split("\t")
        elif "," in line and not re.search(r"\d\s*/\s*\d", line):
            cells = line.split(",")
        elif re.search(r" {2,}", line):
            cells = re.split(r" {2,}", line)
        elif m := re.fullmatch(r"(.*?)\s+(\d+\s*/\s*\d+|\d+\s+\d+)", line):
            cells = [m.group(1)] + ([m.group(2)] if "/" in m.group(2) else m.group(2).split())
        else:
            cells = [line]
        rows.append([c.strip() for c in cells])
    return parse_rows(rows)


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._stack: list[list[list[str]]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._stack and self._stack[-1]:
            self._stack[-1][-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_html(html: str) -> list[Subject]:
    p = _Tables()
    p.feed(html)
    return max((parse_rows(t) for t in p.tables), key=len, default=[])


def parse_json(data) -> list[Subject]:
    """Find the list of objects whose keys look like subject/attended/total."""
    best: list[Subject] = []

    def visit(node):
        nonlocal best
        if isinstance(node, list):
            dicts = [d for d in node if isinstance(d, dict)]
            if dicts:
                keys = list(dict.fromkeys(k for d in dicts for k in d))
                found = parse_rows([keys] + [[d.get(k, "") for k in keys] for d in dicts])
                if len(found) > len(best):
                    best = found
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            for v in node.values():
                visit(v)

    visit(data)
    return best


def parse_body(text: str) -> list[Subject]:
    try:
        return parse_json(json.loads(text))
    except (json.JSONDecodeError, ValueError):
        return parse_html(text)


def parse_har(har: dict) -> tuple[list[Subject], str | None]:
    """Return the subjects from the response that yields the most, and its URL."""
    best, source = [], None
    for entry in har.get("log", {}).get("entries", []):
        content = entry.get("response", {}).get("content", {})
        text = content.get("text")
        if not text:
            continue
        if content.get("encoding") == "base64":
            try:
                text = base64.b64decode(text).decode("utf-8", "replace")
            except ValueError:
                continue
        found = parse_body(text)
        if len(found) > len(best):
            best, source = found, entry.get("request", {}).get("url")
    return best, source


# ---- Live fetch (read-only, cached) ---------------------------------------


def _expand(value: str) -> str:
    """Replace ${NAME} with environment variables so passwords stay out of config files."""

    def sub(m):
        if m.group(1) not in os.environ:
            sys.exit(f"Set the {m.group(1)} environment variable")
        return os.environ[m.group(1)]

    return re.sub(r"\$\{(\w+)\}", sub, value)


def fetch_live(config: dict, cache_path: Path, min_interval_s: int) -> str:
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime < min_interval_s:
        return cache_path.read_text(encoding="utf-8")

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", config.get("user_agent", "bunk-calculator/0.1 (personal use)"))]
    fields = {k: _expand(v) for k, v in config.get("login_fields", {}).items()}

    if csrf := config.get("csrf"):
        page = opener.open(config.get("login_page_url", config["login_url"]), timeout=30).read().decode("utf-8", "replace")
        m = re.search(csrf["regex"], page)
        if not m:
            sys.exit("CSRF token not found on the login page; check csrf.regex")
        fields[csrf["field"]] = m.group(1)

    if config.get("login_url"):
        body = urllib.parse.urlencode(fields).encode()
        opener.open(urllib.request.Request(config["login_url"], data=body, method="POST"), timeout=30).read()

    req = urllib.request.Request(config["attendance_url"], headers=config.get("attendance_headers", {}))
    text = opener.open(req, timeout=30).read().decode("utf-8", "replace")
    cache_path.write_text(text, encoding="utf-8")
    return text


def notify_telegram(message: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        sys.exit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to use --notify")
    body = urllib.parse.urlencode({"chat_id": chat, "text": message}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=body, timeout=30).read()


# ---- CLI --------------------------------------------------------------------


def report(subjects: list[Subject], target: float) -> tuple[str, bool]:
    rows, overall = summarize(subjects, target)
    rows.sort(key=lambda r: (-r.must_attend, r.can_skip))
    width = max(len(r.subject) for r in rows + [overall])
    lines = []
    for r in rows + [overall]:
        pct = "   -  " if r.percent is None else f"{r.percent:5.1f}%"
        lines.append(f"{r.subject:<{width}}  {r.attended:>3}/{r.total:<3}  {pct}  {r.describe()}")
    lines.insert(len(rows), "-" * len(lines[0]))
    return "\n".join(lines), any(r.status != "safe" for r in rows + [overall])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", choices=["text", "html", "json", "har", "live"])
    ap.add_argument("path", type=Path, help="input file, or portal config JSON for 'live'")
    ap.add_argument("--target", type=float, default=75)
    ap.add_argument("--notify", action="store_true", help="send a Telegram alert when any subject is below target")
    ap.add_argument("--cache", type=Path, default=Path(".bunk-cache.txt"))
    ap.add_argument("--min-interval", type=int, default=1800, help="seconds before the portal is fetched again")
    args = ap.parse_args(argv)

    source_url = None
    if args.source == "live":
        config = json.loads(args.path.read_text(encoding="utf-8"))
        subjects = parse_body(fetch_live(config, args.cache, args.min_interval))
    elif args.source == "har":
        subjects, source_url = parse_har(json.loads(args.path.read_text(encoding="utf-8")))
    else:
        text = args.path.read_text(encoding="utf-8")
        subjects = {"text": parse_text, "html": parse_html, "json": lambda t: parse_json(json.loads(t))}[args.source](text)

    if not subjects:
        print("No attendance table recognised.", file=sys.stderr)
        return 2
    if source_url:
        print(f"Attendance found in response from: {source_url}\n")
    text, below = report(subjects, args.target)
    print(text)
    if args.notify and below:
        notify_telegram(f"Attendance alert (target {args.target:g}%)\n\n{text}")
    return 1 if below else 0


if __name__ == "__main__":
    sys.exit(main())
