#!/usr/bin/env python3
"""Polls Anthropic OAuth usage API and updates the mode indicator state JSON.

Run in background:  nohup python3 poll_usage.py &
Or via cron/systemd timer.
"""

import csv
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(__file__).parent / "mode_indicator_state.json"
LOG_FILE = Path(__file__).parent / "usage_log.csv"
API_URL = "https://api.anthropic.com/api/oauth/usage"
INTERVAL = 300  # 5 minutes

LOG_FIELDS = [
    "timestamp",
    "five_hour_util",
    "five_hour_resets_at",
    "seven_day_util",
    "seven_day_resets_at",
]

_last_logged = (None, None)  # (five_hour_util, seven_day_util)


def get_token():
    raw = subprocess.check_output([
        "security", "find-generic-password",
        "-s", "Claude Code-credentials",
        "-w",
    ], text=True).strip()
    data = json.loads(raw)
    return data["claudeAiOauth"]["accessToken"]


def fetch_usage(token):
    req = urllib.request.Request(API_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    })
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def format_remaining(resets_at):
    if not resets_at:
        return ""
    try:
        reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        secs = int((reset_dt - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return "0h"
        d, rem = divmod(secs, 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        return f"{d}d{h}h" if d > 0 else f"{h}h{m}m"
    except Exception:
        return ""


def cycles_remaining(resets_at):
    """How many 5-hour windows remain in the 7-day cycle."""
    if not resets_at:
        return ""
    try:
        reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        secs = (reset_dt - datetime.now(timezone.utc)).total_seconds()
        if secs <= 0:
            return "0c"
        return f"{int(secs / 3600 / 5)}c"
    except Exception:
        return ""


def estimate_runway(current_7d):
    """Estimate time until 100% based on recent burn rate from the log."""
    if not LOG_FILE.exists():
        return ""
    try:
        now = datetime.now(timezone.utc)
        rows = list(csv.DictReader(LOG_FILE.open()))
        # Rolling 1-hour window
        recent = []
        for r in rows:
            t = datetime.fromisoformat(r["timestamp"])
            if (now - t).total_seconds() <= 3600:
                recent.append((t, float(r["seven_day_util"])))
        if len(recent) < 2:
            return ""
        first_t, first_v = recent[0]
        last_t, last_v = recent[-1]
        hours = (last_t - first_t).total_seconds() / 3600
        delta = last_v - first_v
        if hours <= 0 or delta <= 0:
            return ""
        rate = delta / hours
        remaining = 100 - current_7d
        hours_left = remaining / rate
        d, rem = divmod(int(hours_left * 3600), 86400)
        h = rem // 3600
        if d > 0:
            return f"~{d}d{h}h"
        return f"~{h}h"
    except Exception:
        return ""


def log_usage(usage):
    """Append a row to the CSV usage log, but only when utilization changes."""
    global _last_logged
    current = (usage["five_hour"]["utilization"], usage["seven_day"]["utilization"])
    if current == _last_logged:
        return
    _last_logged = current

    write_header = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "five_hour_util": usage["five_hour"]["utilization"],
            "five_hour_resets_at": usage["five_hour"].get("resets_at", ""),
            "seven_day_util": usage["seven_day"]["utilization"],
            "seven_day_resets_at": usage["seven_day"].get("resets_at", ""),
        })


def update_state(usage):
    five_h = round(usage["five_hour"]["utilization"])
    seven_d = round(usage["seven_day"]["utilization"])
    cycles = cycles_remaining(usage["seven_day"].get("resets_at"))
    runway = estimate_runway(seven_d)

    parts = [f"{seven_d}%"]
    if cycles:
        parts.append(cycles)
    text = "  ".join(parts)

    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception:
        state = {}

    state["static_percent"] = text
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    while True:
        try:
            token = get_token()
            usage = fetch_usage(token)
            log_usage(usage)
            update_state(usage)
        except Exception as e:
            print(f"[poll_usage] {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
