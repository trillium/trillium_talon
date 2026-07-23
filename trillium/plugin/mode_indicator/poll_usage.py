#!/usr/bin/env python3
"""Polls Anthropic OAuth usage API and updates the mode indicator state JSON.

Run in background:  nohup python3 poll_usage.py &
Or via cron/systemd timer.
"""

from __future__ import annotations

import csv
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_FILE = Path(__file__).parent / "mode_indicator_state.json"
LOG_FILE = Path(__file__).parent / "usage_log.csv"
SUB_END_FILE = Path(__file__).parent / "subscription_end.json"
SUB_OVERRIDE_FILE = Path(__file__).parent / "subscription_override.json"
STATUS_LOG_FILE = Path(__file__).parent / "subscription_status_log.csv"
ACCOUNTS_FILE = Path(__file__).parent / "accounts.json"
PULSE_DATA_FILE = Path.home() / "pulse-pages" / "ccjuggler" / "data.json"
API_URL = "https://api.anthropic.com/api/oauth/usage"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
INTERVAL = 60  # 1 minute
SEVEN_DAY_SECS = 7 * 86400

LOG_FIELDS = [
    "timestamp",
    "five_hour_util",
    "five_hour_resets_at",
    "seven_day_util",
    "seven_day_resets_at",
]

_last_logged = (None, None)  # (five_hour_util, seven_day_util)
_last_status = None  # subscription_status from previous poll (in-process)

USAGE_CACHE_TTL_SECS = 60  # 1 minute
_usage_cache: dict = {}        # name -> last successful usage response
_usage_cache_ts: dict = {}     # name -> datetime of last successful fetch
_usage_retry_after: dict = {}  # name -> datetime after which we may retry


def load_accounts() -> list[dict]:
    """Return list of account dicts from accounts.json, falling back to the
    built-in Claude Code credentials entry as a single-account default."""
    if ACCOUNTS_FILE.exists():
        try:
            return json.loads(ACCOUNTS_FILE.read_text()).get("accounts", [])
        except Exception:
            pass
    # Legacy single-account default
    return [{"name": "primary", "tier": "unknown",
              "keychain_service": "Claude Code-credentials",
              "token_format": "claude-credentials-json"}]


def get_token(account: dict | None = None) -> str:
    """Read OAuth token for the given account dict.

    token_format "claude-credentials-json" (default for the built-in entry):
        keychain value is JSON with claudeAiOauth.accessToken
    token_format "raw":
        keychain value is the token string directly
    """
    if account is None:
        account = {"keychain_service": "Claude Code-credentials",
                   "token_format": "claude-credentials-json"}
    service = account.get("keychain_service", "Claude Code-credentials")
    acct_arg = account.get("keychain_account")
    cmd = ["security", "find-generic-password", "-s", service, "-w"]
    if acct_arg:
        cmd += ["-a", acct_arg]
    raw = subprocess.check_output(cmd, text=True).strip()
    fmt = account.get("token_format", "claude-credentials-json")
    if fmt == "raw":
        return raw
    data = json.loads(raw)
    return data["claudeAiOauth"]["accessToken"]


def fetch_usage(token):
    req = urllib.request.Request(API_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    })
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def fetch_profile(token):
    """GET /api/oauth/profile — returns account + organization metadata.

    Critically exposes `organization.subscription_status` which flips when
    Anthropic actually revokes paid access. Treat that field as ground truth
    for the moment the subscription lapses; the displayed cancellation date
    on the billing page is a prediction.
    """
    req = urllib.request.Request(PROFILE_URL, headers={
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


def five_hour_elapsed_percent(resets_at: str) -> int:
    """How much of the current 5-hour window has elapsed (0-100).

    Window length is assumed to be 5h = 18000s. Derived from
    (window_length - time_remaining) / window_length.
    """
    if not resets_at:
        return 0
    try:
        reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        remaining_s = (reset_dt - datetime.now(timezone.utc)).total_seconds()
        return max(0, min(100, int((1 - remaining_s / 18000) * 100)))
    except Exception:
        return 0


def load_subscription_end_iso():
    """Return ISO datetime string of effective subscription end, or None.

    Priority:
    1. Admin override at subscription_override.json — used UNTIL its `ends_at`
       has passed. This lets the human pin a more accurate value than the
       scraped billing-page date when timezone semantics are unclear.
    2. Scraped value at subscription_end.json from check_subscription_end.py.
    3. None (auto-renewing or unknown).
    """
    now = datetime.now(timezone.utc)
    if SUB_OVERRIDE_FILE.exists():
        try:
            data = json.loads(SUB_OVERRIDE_FILE.read_text())
            ends_at = data.get("ends_at")
            if ends_at:
                end_dt = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
                if end_dt > now:
                    return ends_at
        except Exception:
            pass
    if SUB_END_FILE.exists():
        try:
            return json.loads(SUB_END_FILE.read_text()).get("ends_at")
        except Exception:
            pass
    return None


def effective_end_iso(seven_day_resets_at, account=None):
    """min(seven_day_resets_at, subscription_end) as ISO string.

    Returns the subscription-end timestamp when it's sooner than the rolling
    7-day reset (i.e. the subscription is going to lapse first). Otherwise
    returns the API's seven_day reset unchanged.

    When ``account`` is provided, prefer ``account["subscription_end"]`` as the
    source of the subscription-end timestamp. When ``account`` is None, fall
    back to ``load_subscription_end_iso()`` so the primary account keeps its
    file-based override behaviour (subscription_override.json / subscription_end.json).
    """
    if not seven_day_resets_at:
        return None
    if account is not None:
        sub_end = account.get("subscription_end") or None
    else:
        sub_end = load_subscription_end_iso()
    if not sub_end:
        return seven_day_resets_at
    try:
        seven_dt = datetime.fromisoformat(seven_day_resets_at.replace("Z", "+00:00"))
        sub_dt = datetime.fromisoformat(sub_end)
        # A subscription-end already in the past is stale (auto-renewing sub, or an
        # unrefreshed override/scrape) — don't cap the live 7-day window to it, or
        # week_percent wrongly pins to 100%.
        if sub_dt <= datetime.now(timezone.utc):
            return seven_day_resets_at
        return sub_end if sub_dt < seven_dt else seven_day_resets_at
    except Exception:
        return seven_day_resets_at


def remaining_text(end_iso):
    """Format time-remaining-until-end_iso as 'Xd Yh' or 'Xh Ym'."""
    if not end_iso:
        return ""
    try:
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        secs = int((end_dt - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return "0h"
        d, rem = divmod(secs, 86400)
        h = rem // 3600
        m = (rem % 3600) // 60
        return f"{d}d{h}h" if d > 0 else f"{h}h{m}m"
    except Exception:
        return ""


def week_percent_elapsed(end_iso):
    """How far through the rolling 7-day window we are (0-100).

    Calculated as ``(1 - time_until_end / 7d_window_length) * 100``. The
    percentage tracks the 7-day window irrespective of subscription clamping
    — if the subscription will lapse before the window resets, the displayed
    remaining text shrinks but this percent stays anchored to the rolling 7d.
    """
    if not end_iso:
        return 0
    try:
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        remaining = (end_dt - datetime.now(timezone.utc)).total_seconds()
        return max(0, min(100, int((1 - remaining / SEVEN_DAY_SECS) * 100)))
    except Exception:
        return 0


def log_status_change(status, baseline_from_disk):
    """Append to subscription_status_log.csv on any actual transition.

    `baseline_from_disk` is the status last written into mode_indicator_state.json
    — used to suppress a noisy fake transition on the first poll after a
    daemon restart, when our in-process `_last_status` is still None.
    """
    global _last_status
    baseline = _last_status if _last_status is not None else baseline_from_disk
    if status == baseline:
        _last_status = status
        return
    write_header = not STATUS_LOG_FILE.exists()
    with open(STATUS_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "previous_status", "current_status"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            baseline or "",
            status,
        ])
    _last_status = status


def _usage_snapshot(usage, profile=None, account=None) -> dict:
    """Build a flat dict of usage/profile fields for one account."""
    snap: dict = {}
    if usage and "five_hour" in usage and "seven_day" in usage:
        five_h = round(usage["five_hour"]["utilization"])
        five_h_elapsed = five_hour_elapsed_percent(usage["five_hour"].get("resets_at", ""))
        seven_d = round(usage["seven_day"]["utilization"])
        seven_resets = usage["seven_day"].get("resets_at", "")
        cycles = cycles_remaining(seven_resets)
        eff_end = effective_end_iso(seven_resets, account=account)
        week_pct = week_percent_elapsed(eff_end)
        week_rem = remaining_text(eff_end)
        parts = [f"{seven_d}%"]
        if cycles:
            parts.append(cycles)
        snap["static_percent"] = "  ".join(parts)
        snap["five_hour_percent"] = five_h
        snap["five_hour_elapsed_percent"] = five_h_elapsed
        snap["seven_day_percent"] = seven_d   # actual token utilization
        snap["week_percent"] = week_pct       # time elapsed through window
        snap["week_remaining"] = week_rem
        snap["five_hour_resets_at"] = usage["five_hour"].get("resets_at", "")
        snap["seven_day_resets_at"] = seven_resets
    if profile:
        org = profile.get("organization", {}) or {}
        acct = profile.get("account", {}) or {}
        snap["subscription_status"] = org.get("subscription_status", "") or ""
        snap["subscription_active"] = snap["subscription_status"] == "active"
        snap["subscription_type"] = org.get("organization_type", "") or ""
        snap["rate_limit_tier"] = org.get("rate_limit_tier", "") or ""
        snap["has_claude_max"] = bool(acct.get("has_claude_max"))
        snap["has_claude_pro"] = bool(acct.get("has_claude_pro"))
    return snap


def update_state(usage, profile=None, account_name: str = "primary", is_primary: bool = False):
    """Write usage snapshot for one account.

    Per-account data lands in state["accounts"][account_name].
    The PRIMARY account (``is_primary``) additionally writes the legacy top-level
    keys so existing consumers (mode_indicator.py) keep working unchanged.
    Primary is identified by position (first account), not by a magic name — so a
    single-subscription setup works with any account name.
    """
    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception:
        state = {}

    account = next(
        (a for a in load_accounts() if a.get("name") == account_name),
        None,
    )
    # The primary account uses the FILE-based subscription end (subscription_override.json
    # / subscription_end.json — human-pinnable) rather than its per-account date, matching
    # the original single-account behaviour; non-primary accounts use their own date.
    snap = _usage_snapshot(usage, profile, account=(None if is_primary else account))

    # Per-account block
    accounts_state = state.setdefault("accounts", {})
    existing = accounts_state.get(account_name, {})
    existing.update(snap)
    existing["last_updated"] = datetime.now(timezone.utc).isoformat()
    accounts_state[account_name] = existing

    # Legacy top-level keys for the primary account
    if is_primary:
        for k, v in snap.items():
            state[k] = v
        if profile:
            org = (profile.get("organization", {}) or {})
            baseline = state.get("subscription_status", "")
            new_status = org.get("subscription_status", "") or ""
            log_status_change(new_status, baseline)

    STATE_FILE.write_text(json.dumps(state, indent=2))


def write_pulse_data(accounts: list[dict]) -> None:
    """Write a combined snapshot for the Pulse dashboard at ~/pulse-pages/ccjuggler/data.json."""
    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception:
        return
    try:
        PULSE_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        # Annotate each account snapshot with live retry-after state
        accounts_state = state.get("accounts", {})
        for a in accounts:
            name = a.get("name", "")
            snap = accounts_state.get(name, {})
            ra_dt = _usage_retry_after.get(name)
            if ra_dt and ra_dt > now:
                snap["rate_limited_until"] = ra_dt.isoformat()
                snap["rate_limited_secs"] = int((ra_dt - now).total_seconds())
            else:
                snap.pop("rate_limited_until", None)
                snap.pop("rate_limited_secs", None)
            if name in accounts_state or ra_dt:
                accounts_state[name] = snap

        PULSE_DATA_FILE.write_text(json.dumps({
            "accounts_config": [
                {k: v for k, v in a.items() if k not in ("keychain_service", "keychain_account", "token_format")}
                for a in accounts
            ],
            "accounts": accounts_state,
            "generated_at": now.isoformat(),
        }, indent=2))
    except Exception as e:
        print(f"[poll_usage] pulse write: {e}")


def poll_account(account: dict, is_primary: bool = False) -> None:
    """Poll usage + profile for one account and update state.

    ``is_primary`` marks the account that drives the mode indicator's top-level
    usage keys (the first account in accounts.json)."""
    name = account.get("name", "primary")
    is_setup_token = account.get("token_format") == "raw"
    try:
        token = get_token(account)
    except Exception as e:
        print(f"[poll_usage] {name} token: {e}")
        return

    usage = None
    profile = None

    # Setup tokens are inference-scoped — usage API requires user:profile OAuth scope
    if is_setup_token:
        return

    # Per-account TTL cache: skip the API call when a fresh cached value exists.
    cached_usage = _usage_cache.get(name)
    cached_ts = _usage_cache_ts.get(name)
    now = datetime.now(timezone.utc)
    retry_after_dt = _usage_retry_after.get(name)
    if retry_after_dt is not None and retry_after_dt > now:
        remaining = int((retry_after_dt - now).total_seconds())
        print(f"[poll_usage] {name} usage: retry-after backoff, {remaining}s remaining")
        if cached_usage is not None:
            usage = cached_usage
        else:
            usage = None
    elif (
        cached_usage is not None
        and cached_ts is not None
        and (now - cached_ts).total_seconds() < USAGE_CACHE_TTL_SECS
    ):
        print(f"[poll_usage] {name} usage: cache hit")
        usage = cached_usage
    else:
        try:
            usage = fetch_usage(token)
            _usage_cache[name] = usage
            _usage_cache_ts[name] = datetime.now(timezone.utc)
            _usage_retry_after.pop(name, None)
            if is_primary:
                log_usage(usage)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after_val = None
                try:
                    headers = getattr(e, "headers", None)
                    if headers is not None:
                        retry_after_val = (
                            headers.get("retry-after")
                            or headers.get("Retry-After")
                        )
                except Exception:
                    retry_after_val = None
                if retry_after_val is not None:
                    try:
                        secs = int(str(retry_after_val).strip())
                        _usage_retry_after[name] = (
                            datetime.now(timezone.utc) + timedelta(seconds=secs)
                        )
                    except (ValueError, TypeError):
                        pass
                if cached_usage is not None:
                    print(f"[poll_usage] {name} usage: 429 rate-limited, using cache")
                    usage = cached_usage
                else:
                    print(f"[poll_usage] {name} usage: 429 rate-limited, no cache available")
                    usage = None
            else:
                print(f"[poll_usage] {name} usage: {e}")
        except Exception as e:
            print(f"[poll_usage] {name} usage: {e}")

    # Setup tokens are inference-scoped — profile endpoint returns 403
    if not is_setup_token:
        try:
            profile = fetch_profile(token)
        except Exception as e:
            print(f"[poll_usage] {name} profile: {e}")

    if usage or profile:
        try:
            update_state(usage or {}, profile, account_name=name, is_primary=is_primary)
        except Exception as e:
            print(f"[poll_usage] {name} update_state: {e}")


def main():
    while True:
        accounts = load_accounts()
        # First account is "primary" — it drives the mode indicator's top-level
        # usage keys. Works for a single subscription (the sole account is primary).
        for i, account in enumerate(accounts):
            poll_account(account, is_primary=(i == 0))
        write_pulse_data(accounts)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
