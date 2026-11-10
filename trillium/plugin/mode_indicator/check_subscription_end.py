#!/usr/bin/env python3
"""Check claude.ai/settings/billing for a subscription cancellation date.

Drives the real, logged-in Chrome session via the `interceptor` CLI so it
inherits cookies/auth. Writes the result to subscription_end.json next to
this file. If the page does not show a cancellation banner (i.e. the
subscription is auto-renewing), `ends_at` is null.

Typical schedule: run once a day. Subscription end-dates do not change
frequently; the polling cost is far cheaper than scraping every minute.

Manual run:
    python3 check_subscription_end.py
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
CACHE_FILE = HERE / "subscription_end.json"
BILLING_URL = "https://claude.ai/new#settings/billing"
LOCAL_TZ = ZoneInfo("America/Los_Angeles")

# Matches "Your subscription will be canceled on Jun 14, 2026."
CANCEL_RE = re.compile(
    r"Your subscription will be canceled on " r"([A-Z][a-z]+) (\d{1,2}), (\d{4})"
)

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def run(cmd: list[str], timeout: int = 30) -> str:
    """Run an interceptor CLI command and return stdout."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)} failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


# "Invoices" + "Link by Stripe" sit at the bottom of the billing panel —
# they only appear once the section has fully hydrated, so they're a reliable
# signal that the cancellation banner (further up the panel) has rendered too.
# Sidebar elements like "Resubscribe" appear immediately and would race.
BILLING_READY_MARKERS = ("Invoices", "Link by Stripe", "Update payment")
BILLING_TIMEOUT_S = 30


def fetch_billing_text() -> str:
    """Open the billing page in the real Chrome session and return visible text.

    Strategy: navigate, then poll `interceptor text` once per second for up to
    BILLING_TIMEOUT_S until a known billing-UI marker appears. This is more
    reliable than `wait-stable` because the billing section is hydrated late
    and the page reports DOM-stable before that final XHR returns.
    """
    import time

    run(["interceptor", "open", BILLING_URL, "--no-wait"])
    deadline = time.monotonic() + BILLING_TIMEOUT_S
    last_text = ""
    while time.monotonic() < deadline:
        try:
            last_text = run(["interceptor", "text"], timeout=10)
        except Exception:
            time.sleep(1)
            continue
        if any(marker in last_text for marker in BILLING_READY_MARKERS):
            return last_text
        time.sleep(1)
    return last_text  # Timeout — return whatever we got; parser handles empty


def parse_cancel_date(text: str) -> str | None:
    """Return ISO-8601 string for the subscription end (in LA local tz) or None."""
    m = CANCEL_RE.search(text)
    if not m:
        return None
    month_name, day, year = m.group(1), int(m.group(2)), int(m.group(3))
    month = MONTHS.get(month_name)
    if month is None:
        return None
    # End-of-day local time on the cancellation date — last moment of access.
    end_dt = datetime(year, month, day, 23, 59, 59, tzinfo=LOCAL_TZ)
    return end_dt.isoformat()


def main() -> int:
    try:
        text = fetch_billing_text()
    except Exception as e:
        print(f"[check_subscription_end] fetch failed: {e}", file=sys.stderr)
        return 1

    ends_at = parse_cancel_date(text)
    raw_match = CANCEL_RE.search(text)
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ends_at": ends_at,
        "raw_text": raw_match.group(0) if raw_match else None,
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2))
    if ends_at:
        print(f"Subscription ends at: {ends_at}")
    else:
        print("No cancellation banner — subscription is auto-renewing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
