"""Quota panel data: `quota-axi --json` parsed into one display cell per subscription.

Pure Python, no talon import, so it unit-tests without the Talon runtime.

quota-axi reports `percentRemaining` (what is LEFT, 0-100). Per provider the
headline is `quotaSemantics.effectiveAvailability` (already the minimum over
the windows that bound that scope), not the raw windows: Antigravity repeats
window ids, so windows are only a fallback.
"""

from __future__ import annotations

from datetime import datetime, timezone

# quota-axi provider id -> short panel label, in display order. ChatGPT Plus is
# reported under the Codex CLI's provider id.
LABELS = {
    "claude": "CC",
    "opencode-go": "OC",
    "codex": "GPT",
    "grok": "GRK",
    "agy": "AGY",
}
DEFAULT_PROVIDERS = ",".join(LABELS)

# Percent LEFT thresholds (>=): green 50, yellow 25, orange 10, else red.
GREEN, YELLOW, ORANGE, RED, GRAY = "33cc66", "e6c229", "ff8c1a", "ff3333", "888888"
_RAMP = [(50, GREEN), (25, YELLOW), (10, ORANGE)]
_SEVERITY = [GREEN, YELLOW, ORANGE, RED]  # worst last

# A scope that covers everything the subscription sells, preferred as headline.
_OVERALL_SCOPES = ("all_models", "all_products")


class Row:
    """One provider's parsed quota. `percent` is None when there is no number."""

    __slots__ = (
        "provider",
        "label",
        "percent",
        "color",
        "note",
        "resets_at",
        "dot",
        "stale",
    )

    def __init__(self, provider, percent=None, color=GRAY, note="", resets_at=None):
        self.provider = provider
        self.label = label_for(provider)
        self.percent = percent
        self.color = color
        self.note = note  # "login" / "setup" / "n/a" when percent is None
        self.resets_at = resets_at
        self.dot = False  # another scope (e.g. one model) is at 0
        self.stale = False


class Cell:
    """What one panel cell draws; built from a Row plus the poll health."""

    __slots__ = ("label", "value", "sub", "color", "frac", "dim", "dot", "exhausted")

    def __init__(self, label, value, sub, color, frac, dim, dot, exhausted):
        self.label, self.value, self.sub, self.color = label, value, sub, color
        self.frac, self.dim, self.dot, self.exhausted = frac, dim, dot, exhausted


def label_for(provider: str) -> str:
    return LABELS.get(provider) or str(provider)[:3].upper()


def parse_providers(spec) -> list[str]:
    """Comma list -> provider ids (lowercase, [a-z0-9-] only, no duplicates)."""
    out = []
    for part in str(spec or "").split(","):
        p = part.strip().lower()
        if p and all(ch.isalnum() or ch == "-" for ch in p) and p not in out:
            out.append(p)
    return out or list(LABELS)


def parse_iso(value):
    """ISO-8601 string (with Z or an offset) -> aware datetime, else None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def format_reset(resets_at, now=None) -> str:
    """Time until `resets_at` as '3d4h' or '5h12m'; '' when unknown, '0h' once past."""
    if resets_at is None:
        return ""
    now = now or datetime.now(timezone.utc)
    secs = int((resets_at - now).total_seconds())
    if secs <= 0:
        return "0h"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    if days:
        return f"{days}d{hours}h"
    return f"{hours}h{rem // 60}m"


def format_age(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 3600:
        return f"{max(1, s // 60)}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def color_for(percent, runway=None) -> str:
    """Headroom color. Runway bumps: projected exhaustion is at least orange,
    exhausted now is red."""
    if percent is None:
        return GRAY
    color = RED
    for floor, ramp_color in _RAMP:
        if percent >= floor:
            color = ramp_color
            break
    if runway == "exhausted_now":
        color = RED
    elif runway == "projected_exhaustion":
        color = max(color, ORANGE, key=_SEVERITY.index)
    return color


def _pct(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(round(max(0, min(100, value))))


def _entries(provider: dict) -> list[dict]:
    sem = provider.get("quotaSemantics")
    items = sem.get("effectiveAvailability") if isinstance(sem, dict) else None
    out = []
    for e in items if isinstance(items, list) else []:
        if isinstance(e, dict) and _pct(e.get("effectivePercentRemaining")) is not None:
            out.append(e)
    return out


def _windows(provider: dict) -> list[dict]:
    wins = provider.get("windows")
    return [w for w in wins if isinstance(w, dict)] if isinstance(wins, list) else []


def _runway(entry) -> str | None:
    runway = entry.get("runway") if isinstance(entry, dict) else None
    return runway.get("status") if isinstance(runway, dict) else None


def _limiting_reset(provider, entry):
    """resetsAt of the window that limits `entry` (the tightest one if the id repeats)."""
    ids = entry.get("limitingWindowIds") or []
    wins = [w for w in _windows(provider) if w.get("id") in ids]
    wins = [w for w in wins if parse_iso(w.get("resetsAt"))]
    if not wins:
        return None
    tight = min(wins, key=lambda w: _pct(w.get("percentRemaining")) or 0)
    return parse_iso(tight.get("resetsAt"))


def _note(provider: dict) -> str:
    """Short reason a provider has no usable reading ('' when it is fine)."""
    state = provider.get("state") if isinstance(provider.get("state"), dict) else {}
    status = state.get("status")
    if provider.get("notSetUp"):
        return "setup"
    if status == "auth_required":
        return "login"
    if status == "unavailable":
        auth = str(state.get("authStatus") or "")
        return "login" if auth.startswith("expired") else "n/a"
    return ""


def parse_provider(provider: dict) -> Row:
    """One entry of quota-axi's `providers` array -> Row."""
    name = str(provider.get("provider") or "")
    row = Row(name)
    state = provider.get("state") if isinstance(provider.get("state"), dict) else {}
    row.stale = bool(state.get("stale"))
    note = _note(provider)
    if note:
        row.note = note
        return row

    entries = _entries(provider)
    if entries:
        overall = [e for e in entries if e.get("scope") in _OVERALL_SCOPES]
        head = overall[0] if overall else min(
            entries, key=lambda e: _pct(e["effectivePercentRemaining"])
        )
        row.percent = _pct(head["effectivePercentRemaining"])
        row.color = color_for(row.percent, _runway(head))
        row.resets_at = _limiting_reset(provider, head)
        row.dot = any(
            e is not head and _pct(e["effectivePercentRemaining"]) == 0
            for e in entries
        )
        return row

    wins = [w for w in _windows(provider) if _pct(w.get("percentRemaining")) is not None]
    if wins:
        low = min(wins, key=lambda w: _pct(w["percentRemaining"]))
        row.percent = _pct(low["percentRemaining"])
        row.color = color_for(row.percent)
        row.resets_at = parse_iso(low.get("resetsAt"))
        return row

    row.note = "n/a"
    return row


def parse(raw, providers=None) -> list[Row]:
    """quota-axi JSON (already decoded) -> one Row per wanted provider, in order.
    A provider missing from the output, or junk input, gives a gray 'n/a' row."""
    wanted = list(providers) if providers else list(LABELS)
    found = {}
    items = raw.get("providers") if isinstance(raw, dict) else None
    for p in items if isinstance(items, list) else []:
        if isinstance(p, dict) and p.get("provider") not in found:
            found[p.get("provider")] = p
    rows = []
    for name in wanted:
        if name in found:
            rows.append(parse_provider(found[name]))
        else:
            row = Row(name)
            row.note = "n/a"
            rows.append(row)
    return rows


STALE_AFTER_INTERVALS = 3


def build_cells(rows, wanted, now, last_ok, interval, failed=False) -> list[Cell]:
    """Cells to draw. `rows` is None until a first successful poll; `last_ok` is
    the epoch of the last success; `failed` means the latest poll failed."""
    if rows is None:
        sub = "err" if failed else "…"
        return [
            Cell(label_for(p), "—", sub, GRAY, None, False, False, False)
            for p in wanted
        ]
    age = now - last_ok if last_ok else 0
    stale_run = age > STALE_AFTER_INTERVALS * interval
    cells = []
    for row in rows:
        dim = failed or stale_run or row.stale
        if row.percent is None:
            value, sub, color, frac = "—", row.note, GRAY, None
        else:
            value, color, frac = f"{row.percent}%", row.color, row.percent / 100.0
            sub = format_reset(row.resets_at, datetime.fromtimestamp(now, timezone.utc))
        if stale_run:
            sub = f"stale {format_age(age)}"
        elif failed:
            sub = f"! {sub}".strip()
        elif row.stale:
            sub = f"stale {sub}".strip()
        cells.append(
            Cell(
                row.label,
                value,
                sub,
                color,
                frac,
                dim,
                row.dot,
                row.percent == 0,
            )
        )
    return cells
