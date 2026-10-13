# Bunk Calculator: comparison of ways to get attendance data

Goal: the simplest way for a student to see "how many can I skip / must I
attend" per subject from a college ERP, without abusing the portal.

## Approaches prototyped (`prototypes/bunk-calculator/`)

| | Paste (web) | Bookmarklet | HAR replay (Python) | Live login (Python) |
|---|---|---|---|---|
| Setup per portal | none | none | none | URLs, form fields, CSRF regex |
| Credentials handled by us | never | never (uses existing session) | none stored, but the HAR contains them | env vars |
| Survives portal redesign | yes | if it is still an HTML table | yes, if it is still JSON/HTML | breaks on login changes |
| CAPTCHA / OTP login | fine | fine | fine | blocked |
| Automatic alerts | no | no | no | yes (Telegram + cron) |
| Server load | zero | zero | zero | one fetch per 30 min (cached) |

## What each one showed

- **Paste** is the floor: it works with every portal because the browser's
  copy of a table is tab-separated. Header-role recognition (code / subject /
  attended / total / absent / percent) handles most layouts. The only bug found:
  "Course Code" matched the subject rule, so `code` is now checked first.
- **Bookmarklet** removes the copy step and needs no credentials, because it
  runs inside the session the student already has. It is the best "simple
  access" answer on desktop. Limits: cross-origin frames, canvas charts,
  mobile browsers that make bookmarklets awkward, and portals with a strict
  CSP that blocks `javascript:` URLs (not tested).
- **HAR replay** automates the "find the request in DevTools" step: it tries
  every response body as JSON or HTML and reports the URL that yields the
  most subjects. Useful as a discovery tool before writing a live config.
- **Live login** is the only way to get alerts, and the most brittle. It is
  deliberately read-only, caches results and refuses to run without explicit
  env vars for secrets.

## Recommendation

Use the bookmarklet (with paste as fallback) day to day. Use HAR mode once to
discover the endpoint, and live mode only if alerts are wanted and the login is
plain form + cookie.

## Not verified

- Tested only with synthetic fixtures (`python/fixtures/`), not a real
  college portal. Real ERPs (e.g. Moodle, custom PHP/ASP.NET portals) may use
  header wording the role rules miss.
- Bookmarklet behaviour under strict Content-Security-Policy and on mobile
  browsers is untested.
- `live` mode and Telegram sending were not exercised against real servers.

## Next experiments

- A browser extension instead of a bookmarklet (survives CSP, works on
  Firefox Android, can show a badge).
- A "what if" planner: given the timetable, the latest date you can skip
  without dropping below target.
- Per-portal adapters keyed by hostname, shared between JS and Python as one
  JSON rule file so the two header heuristics cannot drift.
- Move this out of the REA repository into its own repo; it is unrelated to
  REA's reverse-engineering tooling.
