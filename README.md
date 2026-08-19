# AIAgentBidAssist

A Windows tool that watches Nellis Auction listings you give it (by inventory
number) and pops up a desktop notification when something needs your
attention — you've been outbid, an auction is closing soon and you're not
winning, or the price has hit the ceiling you set for yourself.

## Why this exists (read this first)

Nellis Auction already has a built-in **Max Bid** (proxy bidding) feature:
you set the highest amount you're willing to pay on an item's page, and their
own system automatically raises your bid in $1 increments to stay in the lead
until either you win or your max is reached — exactly the "increase the bid
until my target, then let it go" behavior. **Use that for the actual
bidding.**

What Nellis doesn't give you is a way to watch a whole list of items at once
and get pinged the moment one of them needs a look. That's what this tool
does: it's a **monitor**, not an auto-bidder. It never clicks a bid button.

## How it works

1. You launch your normal Chrome with remote debugging enabled
   (`start_chrome_debug.bat`), using your existing profile — so it's already
   logged into Nellis Auction, no credentials are ever typed into this tool.
2. `bid_monitor.py` connects to that running Chrome tab-by-tab over the
   Chrome DevTools Protocol (CDP), navigates to each item page you listed in
   `config.json`, and reads the rendered page text (current bid, time left,
   whether you're winning or outbid).
3. On each check it compares the result to what it saw last time and fires a
   Windows toast notification for anything that changed and matters:
   outbid, closing soon while you're not winning, or price ≥ your target.
4. It sleeps for `check_interval_seconds`, then repeats, until you press
   Ctrl+C.

## Languages & libraries used

| Piece | Language / tool | Why |
|---|---|---|
| `bid_monitor.py`, `notifier.py` | **Python 3** | Simple, readable scripting for a small polling loop; easy to read/modify without a build step. |
| Browser control | **[Playwright](https://playwright.dev/python/) (Python bindings)**, connecting over the **Chrome DevTools Protocol (CDP)** | Nellis Auction is a client-rendered React/Next.js app — bid data isn't in the static HTML, it's drawn in by JavaScript after the page loads. Playwright drives a real Chrome tab so it sees the same rendered page you do. Connecting via CDP (`connect_over_cdp`) attaches to your *already-running, already-logged-in* Chrome instead of spawning a fresh automated browser, so it reuses your existing Nellis session and cookies without ever touching your password. |
| Page reading | Playwright's `inner_text()` + **regex** (Python `re`) | Rather than depending on exact CSS class names (which are unverified/guessed since this was built without an authenticated live session to inspect), the parser scans the rendered page text for dollar amounts and known phrases ("outbid", "highest bidder", countdown patterns). This is more resilient to markup changes but may need small pattern tweaks — see **Tuning the parser** below. |
| Chrome launch | **Windows Batch script** (`start_chrome_debug.bat`) | One-line, double-clickable way to relaunch Chrome with `--remote-debugging-port` on your existing user profile — no separate installer or automation framework needed. |
| Notifications | **[win10toast-click](https://pypi.org/project/win10toast-click/)** | Native Windows 10/11 toast popups, run on a background thread so a notification never blocks the next check. |
| Config | **JSON** (`config.json`) | Plain, human-editable list of inventory numbers, target prices, and timing settings. |

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
copy config.example.json config.json
```

Edit `config.json`:

```json
{
  "chrome_debug_port": 9222,
  "check_interval_seconds": 60,
  "closing_soon_threshold_seconds": 300,
  "items": [
    { "label": "Optional friendly name", "inventory_number": "61233133", "target_price": 50.00 }
  ]
}
```

`inventory_number` is the numeric ID at the end of the item's Nellis Auction
URL (e.g. `nellisauction.com/p/anything-here/61233133` → `61233133`). The
slug text before the number doesn't matter — the site routes by ID.

`target_price` here is **informational for the monitor** ("let me know when
it's not worth it anymore") — it does not place any bid. Set your real
ceiling using Nellis's own Max Bid field on the item page.

## Running it

1. Close **all** Chrome windows (check Task Manager for leftover `chrome.exe`
   processes — Chrome only opens the debug port if it's passed at startup).
2. Double-click `start_chrome_debug.bat`. This reopens Chrome with your normal
   profile (still logged into Nellis) plus remote debugging on port 9222.
3. In a terminal:
   ```bash
   python bid_monitor.py
   ```
   Leave it running. Stop it any time with Ctrl+C.

Useful flags:
- `python bid_monitor.py --once` — single check pass, then exit (good for a
  first test or for scheduling via Windows Task Scheduler instead of a
  long-running loop).
- `python bid_monitor.py --debug` — also prints the raw text it extracted
  from each item page, so you can see exactly what the parser is working
  with.

## Tuning the parser

This was built without an authenticated Nellis session to inspect live (the
"are you winning" state only shows once logged in), so the text patterns in
`bid_monitor.py` — `CURRENT_BID_LABEL_RE`, `TIME_PATTERNS`,
`WINNING_KEYWORDS`, `OUTBID_KEYWORDS` — are best-effort based on Nellis's
public documentation. If a run shows `price=?`, `time_left=?`, or
`status=unknown` for an item that clearly has that info on the page:

1. Run with `--debug` and look at the printed text for that item.
2. Note the exact wording/format Nellis actually uses.
3. Add or adjust the matching regex/keyword in `bid_monitor.py`.

## What this does *not* do

- It does not place, raise, or automate any bid — bidding stays on Nellis's
  own Max Bid system.
- It does not store or touch your Nellis password — it rides on your
  existing logged-in Chrome session via CDP.
- It only runs while your machine and the debug-enabled Chrome window are
  open.
