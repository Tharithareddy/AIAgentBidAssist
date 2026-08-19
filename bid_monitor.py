"""
Nellis Auction bid monitor.

Watches a list of item inventory numbers using your already-logged-in Chrome
session (via Chrome DevTools Protocol) and sends a Windows toast notification
when:
  - you've been outbid
  - the current bid has reached/exceeded your target price (time to let it go)
  - the auction is closing soon and you are not currently winning

It does NOT place bids. Nellis Auction already has a native "Max Bid" /
proxy-bid feature that auto-bids up to a cap you set on the item page — use
that for the actual bidding, and use this script to keep an eye on things
across many items at once. See README.md for details.

Usage:
    python start_chrome_debug.bat        (once, to launch Chrome with debugging)
    python bid_monitor.py                (run continuously)
    python bid_monitor.py --once         (single pass, useful for testing)
    python bid_monitor.py --debug        (print extracted page text per item)
"""

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page

from notifier import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bid_monitor")

ITEM_URL_TEMPLATE = "https://www.nellisauction.com/p/item/{inventory_number}"

PRICE_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")
CURRENT_BID_LABEL_RE = re.compile(r"current bid[^$]{0,20}(\$[\d,]+(?:\.\d{2})?)", re.I)

TIME_PATTERNS = [
    re.compile(r"(\d+)\s*d\s*(\d+)\s*h\s*(\d+)\s*m", re.I),
    re.compile(r"(\d+)\s*h\s*(\d+)\s*m\s*(\d+)\s*s", re.I),
    re.compile(r"\b(\d{1,2}):(\d{2}):(\d{2})\b"),
    re.compile(r"(\d+)\s*m\s*(\d+)\s*s", re.I),
]

WINNING_KEYWORDS = [
    "you're the highest bidder",
    "you are the highest bidder",
    "you're winning",
    "you are winning",
]
OUTBID_KEYWORDS = [
    "you've been outbid",
    "you have been outbid",
    "outbid",
]


@dataclass
class ItemState:
    last_status: Optional[str] = None  # "winning" | "outbid" | "unknown"
    notified_target_reached: bool = False
    notified_closing_soon: bool = False


def parse_price(text: str) -> Optional[float]:
    match = CURRENT_BID_LABEL_RE.search(text)
    if not match:
        # Fall back to the first dollar amount found on the page.
        all_prices = PRICE_RE.findall(text)
        if not all_prices:
            return None
        raw = all_prices[0]
    else:
        raw = match.group(1)
    return float(raw.replace("$", "").replace(",", ""))


def parse_time_left_seconds(text: str) -> Optional[int]:
    lowered = text.lower()
    for pattern in TIME_PATTERNS:
        match = pattern.search(lowered)
        if not match:
            continue
        parts = [int(g) for g in match.groups()]
        if len(parts) == 3 and pattern is TIME_PATTERNS[0]:
            days, hours, minutes = parts
            return days * 86400 + hours * 3600 + minutes * 60
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return hours * 3600 + minutes * 60 + seconds
        if len(parts) == 2:
            minutes, seconds = parts
            return minutes * 60 + seconds
    return None


def parse_status(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in OUTBID_KEYWORDS):
        return "outbid"
    if any(k in lowered for k in WINNING_KEYWORDS):
        return "winning"
    return "unknown"


def fetch_item(page: Page, inventory_number: str) -> dict:
    url = ITEM_URL_TEMPLATE.format(inventory_number=inventory_number)
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    # The page is a client-rendered React app; give it a moment to hydrate
    # and pull in bid data before reading the text.
    page.wait_for_timeout(2500)
    text = page.inner_text("body")
    return {
        "url": url,
        "text": text,
        "price": parse_price(text),
        "time_left_seconds": parse_time_left_seconds(text),
        "status": parse_status(text),
    }


def check_item(page: Page, item_config: dict, state: ItemState, closing_soon_threshold: int, debug: bool) -> None:
    label = item_config.get("label") or item_config["inventory_number"]
    target = float(item_config["target_price"])

    try:
        result = fetch_item(page, item_config["inventory_number"])
    except Exception as exc:  # noqa: BLE001 - log and keep monitoring other items
        logger.warning("Failed to check '%s': %s", label, exc)
        return

    if debug:
        logger.info("--- DEBUG: %s ---\n%s\n--- END DEBUG ---", label, result["text"][:2000])

    price, time_left, status = result["price"], result["time_left_seconds"], result["status"]
    logger.info(
        "%s: price=%s time_left=%s status=%s",
        label,
        f"${price:.2f}" if price is not None else "?",
        f"{time_left}s" if time_left is not None else "?",
        status,
    )

    if status == "outbid" and state.last_status != "outbid":
        notify(
            "Outbid on Nellis Auction",
            f"{label}: you've been outbid. Current bid {f'${price:.2f}' if price else '?'}.",
        )

    if price is not None and price >= target and status != "winning" and not state.notified_target_reached:
        notify(
            "Target price reached — letting it go",
            f"{label}: current bid ${price:.2f} has reached your target of ${target:.2f}.",
        )
        state.notified_target_reached = True

    if (
        time_left is not None
        and time_left <= closing_soon_threshold
        and status != "winning"
        and not state.notified_closing_soon
    ):
        notify(
            "Auction closing soon",
            f"{label}: closing in about {time_left // 60}m and you are not currently winning.",
        )
        state.notified_closing_soon = True

    if status != state.last_status:
        state.last_status = status
        if status == "winning":
            # Status flipped back to winning: allow future re-alerts for this item.
            state.notified_closing_soon = False


def load_config(path: Path) -> dict:
    if not path.exists():
        logger.error(
            "Config file '%s' not found. Copy config.example.json to config.json and edit it.",
            path,
        )
        sys.exit(1)
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor Nellis Auction items and send Windows alerts.")
    parser.add_argument("--config", default="config.json", help="Path to config JSON (default: config.json)")
    parser.add_argument("--once", action="store_true", help="Run a single check pass and exit")
    parser.add_argument("--debug", action="store_true", help="Print extracted page text for tuning selectors")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    port = config.get("chrome_debug_port", 9222)
    interval = config.get("check_interval_seconds", 60)
    closing_soon_threshold = config.get("closing_soon_threshold_seconds", 300)
    items = config["items"]

    states = {item["inventory_number"]: ItemState() for item in items}

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Could not connect to Chrome on port %s: %s\n"
                "Run start_chrome_debug.bat first (and make sure all other Chrome "
                "windows were closed before launching it).",
                port,
                exc,
            )
            sys.exit(1)

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

        logger.info("Connected to Chrome. Monitoring %d item(s) every %ds.", len(items), interval)
        try:
            while True:
                for item in items:
                    check_item(page, item, states[item["inventory_number"]], closing_soon_threshold, args.debug)
                if args.once:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
        finally:
            page.close()


if __name__ == "__main__":
    main()
