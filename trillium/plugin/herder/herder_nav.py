"""
Crew Nav — voice navigation over herdr panes / tabs / workspaces.

Companion to herder.py. Maps a compact verb+target grammar onto the real herdr CLI,
so tabs / panes / agents / workspaces are all swappable by voice:

  "pane left|right|up|down"  -> herdr pane focus --direction <dir> --current
  "pane zoom"                -> herdr pane zoom --toggle --current
  "split right|down"         -> herdr pane split --current --direction <dir> --focus
  "space next|back|new"      -> cycle / create herdr workspaces

The herder_tab_* actions below (cycle / new / close) are no longer bound to local
.talon grammar. They're invoked by wezterm.py's app.tab_* overrides, which the generic
core/windows_and_tabs/tabs.talon vocabulary ("tab next/open/close/previous") drives when
tag: user.tabs is active (set in herder_panel.py). Logic here is unchanged.

(Agent focus + status-rotate live in herder.py: "herder <name>", "herder next working".)

Grounded entirely in verified herdr verbs + JSON shapes (2026-07-15):
`herdr tab list` -> result.tabs[] and `herdr workspace list` -> result.workspaces[],
each entry carrying `focused` + a *_id; cycling finds the focused entry and focuses
its neighbor. Everything routes through actions.user.system_command_nb (non-blocking),
same bridge herder.py uses.
"""

import json
import shlex
import subprocess

from talon import Module, actions

mod = Module()

# GUI-process PATH safety (see herder.py): full path for subprocess, PATH prefix for shell.
_HERDR = "/opt/homebrew/bin/herdr"
_ENV = 'PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH" '


def _herdr_result(args: list[str]) -> dict:
    """Run a herdr subcommand and return its parsed `result` object ({} on failure)."""
    try:
        r = subprocess.run([_HERDR, *args], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            print(f"[herder_nav] herdr {' '.join(args)} -> rc={r.returncode} {(r.stderr or r.stdout).strip()[:200]}")
        return json.loads(r.stdout).get("result", {})
    except Exception as e:
        print(f"[herder_nav] herdr {' '.join(args)} failed: {e}")
        return {}


def _cycle(items: list[dict], id_key: str, focus_argv: list[str], delta: int) -> None:
    """Focus the neighbor (delta) of the currently-focused entry, cyclically."""
    if not items:
        return
    idx = next((i for i, it in enumerate(items) if it.get("focused")), 0)
    target_id = items[(idx + delta) % len(items)].get(id_key)
    if target_id:
        actions.user.system_command_nb(
            _ENV + "herdr " + " ".join(focus_argv) + f" {shlex.quote(target_id)}"
        )


def _screen_order(pane_ids: list[str], rects: dict) -> list[str]:
    """Pane ids sorted left-to-right then top-to-bottom; list order if no rects."""
    if not all(pid in rects for pid in pane_ids):
        return list(pane_ids)
    return sorted(pane_ids, key=lambda pid: (rects[pid]["x"], rects[pid]["y"]))


def _direction(cur: dict, tgt: dict) -> str:
    """Direction from one pane rect toward another (centre to centre)."""
    dx = (tgt["x"] + tgt["width"] / 2) - (cur["x"] + cur["width"] / 2)
    dy = (tgt["y"] + tgt["height"] / 2) - (cur["y"] + cur["height"] / 2)
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"


def _walk_to(current: str, target: str, rects: dict, max_hops: int = 4) -> None:
    """Reach a plain-shell pane (herdr agent focus only knows agent panes) by
    stepping directionally; stops when the focused pane is the target."""
    if current not in rects or target not in rects:
        return
    for _ in range(max_hops):
        _herdr_result(
            ["pane", "focus", "--pane", current, "--direction",
             _direction(rects[current], rects[target])]
        )
        panes = _herdr_result(["pane", "list"]).get("panes", [])
        now = next((p["pane_id"] for p in panes if p.get("focused")), None)
        if now in (target, None):
            return
        if now == current:
            return  # no neighbour that way; avoid looping
        current = now


@mod.action_class
class Actions:
    def herder_pane_focus(direction: str):
        """Focus the pane in a direction (left/right/up/down)."""
        actions.user.system_command_nb(
            _ENV + f"herdr pane focus --direction {shlex.quote(direction)} --current"
        )

    def herder_pane_zoom():
        """Toggle zoom on the current pane."""
        actions.user.system_command_nb(_ENV + "herdr pane zoom --toggle --current")

    def herder_pane_split(direction: str):
        """Split the current pane (right/down) and focus the new one."""
        actions.user.system_command_nb(
            _ENV + f"herdr pane split --current --direction {shlex.quote(direction)} --focus"
        )

    def herder_pane_cycle(delta: int):
        """Focus the next (+1) / previous (-1) pane inside the current tab, in
        on-screen order (left-to-right, then top-to-bottom), wrapping."""
        panes = _herdr_result(["pane", "list"]).get("panes", [])
        focused = next((p for p in panes if p.get("focused")), None)
        if focused is None:
            return
        tab_id = focused.get("tab_id")
        tab_panes = {p["pane_id"]: p for p in panes if p.get("tab_id") == tab_id}
        if len(tab_panes) < 2:
            return
        layout = _herdr_result(["pane", "layout", "--pane", focused["pane_id"]]).get(
            "layout", {}
        )
        rects = {c["pane_id"]: c["rect"] for c in layout.get("panes", []) if c.get("rect")}
        order = _screen_order(list(tab_panes), rects)
        target = order[(order.index(focused["pane_id"]) + delta) % len(order)]
        print(f"[herder_nav] pane_cycle {delta:+d}: {focused['pane_id']} -> {target} (order {order})")
        if "agent" in tab_panes[target]:
            _herdr_result(["agent", "focus", target])
            return
        _walk_to(focused["pane_id"], target, rects)

    def herder_tab_cycle(delta: int):
        """Focus the next (+1) / previous (-1) tab."""
        _cycle(_herdr_result(["tab", "list"]).get("tabs", []), "tab_id", ["tab", "focus"], delta)

    def herder_tab_new():
        """Create and focus a new tab."""
        actions.user.system_command_nb(_ENV + "herdr tab create --focus")

    def herder_tab_close():
        """Close the currently-focused tab."""
        tabs = _herdr_result(["tab", "list"]).get("tabs", [])
        focused = next((t for t in tabs if t.get("focused")), None)
        target_id = focused.get("tab_id") if focused else None
        if target_id:
            actions.user.system_command_nb(
                _ENV + "herdr tab close " + shlex.quote(target_id)
            )

    def herder_ws_cycle(delta: int):
        """Focus the next (+1) / previous (-1) workspace."""
        _cycle(
            _herdr_result(["workspace", "list"]).get("workspaces", []),
            "workspace_id",
            ["workspace", "focus"],
            delta,
        )

    def herder_ws_new():
        """Create and focus a new workspace."""
        actions.user.system_command_nb(_ENV + "herdr workspace create --focus")

    def herder_history_prev():
        """Go to the previously visited pane (back in focus history)."""
        actions.user.system_command_nb(_ENV + "herdr-nav --prev")

    def herder_history_next():
        """Go forward in pane focus history (undo a herder_history_prev)."""
        actions.user.system_command_nb(_ENV + "herdr-nav --next")

    def herder_history_pick():
        """Open an fzf pane history picker in a new herdr tab."""
        actions.user.system_command_nb(_ENV + "herdr-nav --pick")
