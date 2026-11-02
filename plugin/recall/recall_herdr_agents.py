# AI Added: entire file (cached Herdr agent feed for recall pills).
"""Herdr agents as recall pill source (phase 1 of the named-agents upgrade).

Read-only fetcher with a short TTL cache. The pill draw calls get_agent_tabs()
every frame, so this module NEVER runs a subprocess on the draw path — refresh
happens at most once per _CACHE_TTL seconds, everything else serves cache.

Phase 1 wiring (compose, don't replace): agent tabs render as ADDITIONAL pills
alongside OS-window pills; spoken names stay window-first; agent pills focus
via click + the existing herdr_tab_alias jumps. Voice resolution of agent
names is a later phase, after the captain has seen the pills.
"""

import json
import subprocess
import time

HERDR = "herdr"  # on PATH (/opt/homebrew/bin/herdr)
_CACHE_TTL = 10.0  # seconds between live refreshes at most

_cache = {"at": 0.0, "tabs": []}


def _fetch_agents():
    """One live `herdr agent list`. Returns agent records or []. Never raises."""
    try:
        out = subprocess.run(
            [HERDR, "agent", "list"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        agents = json.loads(out).get("result", {}).get("agents", [])
        return agents if isinstance(agents, list) else []
    except Exception as e:
        print(f"[recall_herdr_agents] agent list failed: {e}")
        return []


def get_agent_tabs():
    """Return cached agent tab descriptors, refreshing at most every TTL.

    Each descriptor: {"key", "label", "pane_id", "tab_id", "focused",
    "status"}. Key is "agent:<name or pane_id>" — never a bare pane id, so a
    later voice phase can't collide with OS-window names. Never raises.
    """
    global _cache
    try:
        now = time.time()
        if now - _cache.get("at", 0.0) < _CACHE_TTL:
            return list(_cache.get("tabs", []))
        tabs = []
        for a in _fetch_agents():
            name = a.get("name") or ""
            pane_id = a.get("pane_id") or ""
            if not pane_id and not name:
                continue
            label = name or pane_id
            tabs.append({
                "key": f"agent:{name or pane_id}",
                "label": str(label)[:16],
                "pane_id": pane_id,
                "tab_id": a.get("tab_id") or "",
                "focused": bool(a.get("focused")),
                "status": a.get("agent_status") or "",
            })
        _cache = {"at": now, "tabs": tabs}
        return list(tabs)
    except Exception as e:
        print(f"[recall_herdr_agents] get_agent_tabs failed: {e}")
        try:
            return list(_cache.get("tabs", []))
        except Exception:
            return []
