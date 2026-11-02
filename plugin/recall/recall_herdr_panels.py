# AI Added: entire file (recall x Herdr panel surfacing).
"""Recall x Herdr panel surfacing.

Saying an already-saved window name keeps working exactly as before — no new
voice commands. When the recalled window turns out to host Herdr panes, recall
additionally ensures Herdr displays that tab's live pane and arms a passive
panel-map strip next to the window's pill. Anything else behaves bit-for-bit
as today: focus happens first and synchronously, and every Herdr step after it
degrades silently (a lookup failure changes nothing the captain already saw).

Read-only except the explicit focus ensure (herdr agent focus + foreground the
host terminal). Never closes panes, never sends input, never stores pane ids.
"""

import json
import re
import subprocess
import time

from talon import Module

mod = Module()

HERDR = "herdr"  # on PATH (/opt/homebrew/bin/herdr)
HERDR_HOST_APP = "WezTerm"  # the macOS app that hosts the herdr workspace
_SNAPSHOT_TIMEOUT = 5  # seconds, matching herdr_focus.py
_MAP_TTL = 60.0  # seconds a panel map stays armed for the pill draw

# Remote legs announce themselves in WezTerm titles: "mini1: ~", "[mosh] mini1: ~".
_HOST_TOKEN_RE = re.compile(r"(mini\d+|vps\d+)", re.IGNORECASE)

# Terminal apps whose windows may host Herdr panes (mirrors recall_terminal).
_HERDR_HOST_APPS = {"WezTerm", "Ghostty", "kitty", "Alacritty", "Terminal", "iTerm2"}

_active_map = None  # {"name": str, "panes": [{...}], "expires": float}


def should_probe(info, live_title=""):
    """Cheap gate: only WezTerm-family windows or remote-leg titles ever get a
    snapshot lookup, so every other recall keeps today's zero-overhead path."""
    app_name = (info or {}).get("app", "") or ""
    if app_name in _HERDR_HOST_APPS:
        return True
    return bool(_HOST_TOKEN_RE.search(live_title or ""))


def _detect_host(info):
    """Return the remote host token (mini1, vps01, ...) from the saved title,
    or None for a local window."""
    m = _HOST_TOKEN_RE.search((info or {}).get("title", "") or "")
    return m.group(1).lower() if m else None


def _run_snapshot(host=None):
    """One snapshot call, local CLI or over ssh. Returns parsed dict or None."""
    try:
        if host:
            out = subprocess.run(
                ["ssh", host, "herdr", "api", "snapshot"],
                capture_output=True, text=True, timeout=_SNAPSHOT_TIMEOUT,
            ).stdout
        else:
            out = subprocess.run(
                [HERDR, "api", "snapshot"],
                capture_output=True, text=True, timeout=_SNAPSHOT_TIMEOUT,
            ).stdout
        result = json.loads(out).get("result", {})
        snap = result.get("snapshot") if isinstance(result, dict) else None
        if isinstance(snap, dict):
            return snap
        if isinstance(result, dict) and isinstance(result.get("agents"), list):
            return result
        print("[recall_herdr_panels] snapshot: unexpected shape")
        return None
    except Exception as e:
        print(f"[recall_herdr_panels] snapshot failed ({host or 'local'}): {e}")
        return None


def _match_score(path, agent):
    """Specificity score for one agent: exact cwd wins over substring, and a
    live foreground_cwd beats a stale cwd. 0 = no match."""
    if not path:
        return 0
    best = 0
    for key, exact, partial in (("foreground_cwd", 4, 2), ("cwd", 3, 1)):
        current = agent.get(key) or ""
        if not current:
            continue
        if current == path:
            return exact
        if path in current:
            best = max(best, partial)
    return best


def resolve_for_window(info, name=""):
    """Match a saved window to its Herdr tab. Returns a panel map dict or None.

    Resolution is by saved path substring against agent cwd/foreground_cwd
    (the herdr_focus.py strategy — ids churn, so nothing is stored). The map
    carries host-namespaced pane ids for the focus step.
    """
    if not info:
        return None
    host = _detect_host(info)
    snap = _run_snapshot(host)
    if not snap:
        return None
    agents = snap.get("agents", []) or []
    layouts = {l.get("tab_id"): l for l in (snap.get("layouts", []) or []) if l.get("tab_id")}
    path = info.get("path") or ""
    scored = [(_match_score(path, a), a) for a in agents]
    top = max([s for s, _ in scored] or [0])
    if top <= 0:
        return None
    winners = [a for s, a in scored if s == top]
    tabs = {a.get("tab_id") for a in winners}
    if len(tabs) != 1:
        # Ambiguous across tabs (e.g. a broad saved path matching every pane
        # under ~/code): render nothing rather than the wrong tab.
        print(f"[recall_herdr_panels] ambiguous match for {name or 'window'}: "
              f"{len(winners)} panes across {len(tabs)} tabs, declining")
        return None
    match = winners[0]
    tab_id = match.get("tab_id")
    layout = layouts.get(tab_id, {})
    by_pane = {a.get("pane_id"): a for a in agents}
    panes = []
    for cell in layout.get("panes", []) or []:
        pid = cell.get("pane_id")
        agent = by_pane.get(pid, {})
        panes.append({
            "pane_id": pid,
            "host": host,
            "label": _pane_label(agent, pid),
            "focused": bool(cell.get("focused")),
            "status": agent.get("agent_status") or "",
        })
    if not panes:
        pid = match.get("pane_id")
        panes = [{
            "pane_id": pid, "host": host,
            "label": _pane_label(match, pid),
            "focused": True, "status": match.get("agent_status") or "",
        }]
    return {"name": name, "host": host, "tab_id": tab_id, "panes": panes}


def _pane_label(agent, pane_id):
    """Short strip label: hs_tab_dim token, then hs_tab, then the stripped
    terminal title, then the pane id. Token keys vary by agent."""
    tokens = (agent or {}).get("tokens") or {}
    for key in ("hs_tab_dim", "hs_tab"):
        value = tokens.get(key)
        if value:
            return str(value).strip()[:16]
    title = (agent or {}).get("terminal_title_stripped") or (agent or {}).get("terminal_title") or ""
    if title.strip():
        return str(title).strip()[:16]
    return str(pane_id or "?")


def _focus_live_pane(panel_map):
    """Ensure Herdr displays the tab's live pane + foreground the host app.
    Best-effort only; every failure is silent by design."""
    try:
        live = next((p for p in panel_map["panes"] if p["focused"]), panel_map["panes"][0])
    except Exception:
        return
    focus_arg = live.get("pane_id") or panel_map.get("tab_id")
    if not focus_arg:
        return
    host = panel_map.get("host")
    try:
        if host:
            subprocess.run(["ssh", host, HERDR, "agent", "focus", focus_arg],
                           check=False, timeout=_SNAPSHOT_TIMEOUT)
        else:
            subprocess.run([HERDR, "agent", "focus", focus_arg],
                           check=False, timeout=_SNAPSHOT_TIMEOUT)
    except Exception as e:
        print(f"[recall_herdr_panels] focus failed: {e}")
        return
    try:
        subprocess.run(["open", "-a", HERDR_HOST_APP], check=False, timeout=_SNAPSHOT_TIMEOUT)
    except Exception as e:
        print(f"[recall_herdr_panels] foreground failed: {e}")


def ensure_herdr_visible(info, name=""):
    """Post-focus step for recall_window: surface the Herdr panel for a Herdr
    host window and arm its map strip. Returns the map or None. Never raises."""
    try:
        panel_map = resolve_for_window(info, name)
    except Exception as e:
        print(f"[recall_herdr_panels] resolve failed: {e}")
        return None
    if not panel_map:
        return None
    _focus_live_pane(panel_map)
    global _active_map
    _active_map = dict(panel_map)
    _active_map["expires"] = time.time() + _MAP_TTL
    return panel_map


def take_active_map():
    """Hand the armed map to the pill draw (called every frame; expiry drops
    it so the strip vanishes on its own). Never raises."""
    global _active_map
    try:
        if _active_map and time.time() < _active_map.get("expires", 0):
            return _active_map
        _active_map = None
        return None
    except Exception:
        _active_map = None
        return None
