# Bunk Calculator

Shows each subject's attendance and tells you how many classes you can skip, or
how many in a row you must attend to get back to the minimum (default 75%).

It only **reads** your own attendance. It never changes anything on the portal.

## Pick the easiest way in

| Way | Effort | Needs portal-specific setup? | Works on phone? |
|---|---|---|---|
| **1. Paste** into `web/index.html` | Copy table, paste | No | Yes |
| **2. Bookmarklet** "Bunk it!" | One click on the portal page | No (if attendance is an HTML table) | Desktop: yes. Mobile: awkward |
| **3. Python** `bunk.py` (HAR or live login) | DevTools once, then a command | `live` mode: yes | Via Telegram alerts |

Start with 1 or 2. Use 3 only if you want automatic alerts.

### 1. Paste (works with any portal)

Open `web/index.html` in a browser. Select the attendance table on your portal,
copy it, paste it into the box and click **Read table**. Lines such as
`Maths 18/24`, `Maths 18 24` or `Maths, 18, 24` work too. You can edit numbers
afterwards. Data stays in your browser's local storage.

### 2. Bookmarklet (one click, no copy-paste)

On `web/index.html`, drag **Bunk it!** to your bookmarks bar. Log in to the
portal, open the attendance page and click the bookmark. A panel appears with
results. It reads only the page you are already viewing (including
same-origin frames) and sends nothing anywhere.

It will not find anything if the portal draws attendance as a chart or an image,
puts it in a cross-origin frame, or uses unusual column names. Use mode 1 then.

### 3. Python: find the endpoint, then automate

Standard library only (Python 3.10+).

**a. HAR mode: let the script find the attendance request for you.**
In DevTools, open Network, load the attendance page, right-click and choose
**Save all as HAR**. Then run:

```sh
python bunk.py har portal.har
```

It prints the URL that returned the attendance (this is the endpoint you would
otherwise hunt for by hand) and the results.

> A HAR file contains your cookies and often your password. Never share or
> commit it. Delete it when you are done.

**b. Live mode: log in and fetch, read-only, cached.**
Copy `portal.example.json`, fill in the URLs and form field names you saw in
DevTools, and keep credentials in environment variables:

```sh
export PORTAL_USER=... PORTAL_PASS=...
python bunk.py live my-portal.json             # exit code 1 if any subject is short
python bunk.py live my-portal.json --notify    # Telegram alert when short
```

Results are cached in `.bunk-cache.txt` and the portal is contacted at most
once every 30 minutes (`--min-interval`). For alerts, create a bot with
@BotFather and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Run it from cron
once or twice a day, not more.

Live mode will not work if the login has a CAPTCHA, OTP or encrypts the
password in JavaScript. Use HAR mode or modes 1 and 2 instead.

Other inputs: `python bunk.py text|html|json FILE`.

## The maths

With `a` attended out of `t` held and target `p`:

- can skip `k` = largest k with `a / (t + k) >= p`, which is `floor(a/p - t)`
- must attend `n` = smallest n with `(a + n) / (t + n) >= p`, which is `ceil((p*t - a) / (1 - p))`

Both use integer arithmetic in basis points, so 18/24 at 75% is exactly "on the
edge" instead of a rounding accident. Tests check every `a <= t < 40` at several
targets against a brute-force count.

## Rules to stay inside

- Only your own login, read-only. Never touch other students' data.
- Check your college's IT / acceptable-use policy first. Showing it to the
  admin is better still.
- Keep request rates low (the cache does this for you).

## Tests

```sh
python3 -I python/tests/test_bunk.py
node --test web/bunk.test.js
```
