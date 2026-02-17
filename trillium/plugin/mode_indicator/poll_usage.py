#!/usr/bin/env python3
"""Polls Anthropic OAuth usage API and updates the mode indicator state JSON.

Run in background:  nohup python3 poll_usage.py &
Or via cron/systemd timer.
"""

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(__file__).parent / "mode_indicator_state.json"
CREDS_FILE = Path.home() / ".claude" / ".credentials.json"
API_URL = "https://api.anthropic.com/api/oauth/usage"
INTERVAL = 300  # 5 minutes


def get_token():
    data = json.loads(CREDS_FILE.read_text())
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


def update_state(usage):
    five_h = round(usage["five_hour"]["utilization"])
    seven_d = round(usage["seven_day"]["utilization"])
    remaining = format_remaining(usage["seven_day"].get("resets_at"))

    text = f"{seven_d}%"

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
            update_state(usage)
        except Exception as e:
            print(f"[poll_usage] {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
