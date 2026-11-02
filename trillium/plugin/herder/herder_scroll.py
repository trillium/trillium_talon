"""
Rapid, eye-followable pane scroll — the herdr/WezTerm equivalent of Rango's
"upper"/"downer" (rapid visual shift of the visible content).

Delivery mechanism — `herdr terminal session control <pane_id>`, NOT osascript:
this CLI subcommand opens a live control connection to a pane and reads
newline-delimited JSON commands off stdin, including
`{"type":"terminal.scroll","direction":"up"|"down","lines":N}`, which calls
straight into herdr's TerminalRuntime.scroll_up()/scroll_down() — the same
scroll state `herdr pane get`/`list` reports as `scroll.offset_from_bottom`.
Confirmed via direct testing (isolated herdr session, not a live pane):
offset_from_bottom moved exactly N per command, in both directions, and a
multi-tick burst with real per-write delays produced the expected incremental
total — so the visible cascade is genuine, not a single silent jump.

This supersedes an earlier `pane send-keys`/`send-text` approach (rejected:
that API writes into the pane's pty INPUT stream, downstream of any
prefix-key/mouse/scroll dispatch — named PageUp/PageDown keys aren't even
accepted, and raw SGR mouse-wheel bytes or the documented copy-mode chord
both land as literal garbled text instead of triggering scroll) and an
even earlier osascript System Events key-code approach (rejected: relied on
a WezTerm-level `PageUp`/`PageDown` Lua keybinding that requires OS-level
keystroke delivery and Accessibility permissions, and never touched herdr's
own scroll state directly — herdr owns its own scrollback buffer per pane,
entirely separate from WezTerm's).

The per-write delay between JSON lines is what makes the cascade visible: if
all ticks are written to the subprocess's stdin at once, herdr processes them
effectively instantly (no OS-level pipe latency to space them out) — the
delay must come from real time.sleep() calls between writes on this end,
mirroring how a held physical key produces a stream of discrete repeat events
over time rather than one big jump.

herder_nav.talon binds bare "upper"/"downer" (tag: user.herder_panel, i.e.
only while WezTerm/herdr is focused) to herder_scroll_burst below — same
words Rango uses (apps/rango/../rango.talon, tag: browser), deliberately
reused per Trillium's request. The two never grammar-collide at speech time:
the tags are mutually exclusive (WezTerm focused vs. a browser focused).

They DO collide in trillium/plugin/repeater/opposite_mappings.py's OPPOSITES
dict, which is a flat table keyed on trigger text with no context awareness
(confirmed by reading repeater.py — it resolves the mapped action via plain
getattr(actions, namespace).name, not through Talon's context matcher). Only
one "upper"/"downer" entry can exist. upper_downer_opposite() below is the
fix: the single OPPOSITES entry for "upper"/"downer" now calls this
dispatcher, which branches on whether WezTerm is the focused app — the same
signal herder_panel.py's `app.name: WezTerm` uses — and picks
herder_scroll_burst or Rango's rango_command_without_target accordingly.
Repeat (saying "upper" again) needs no such dispatcher: Talon replays the
phrase itself, which re-enters the normal tag-scoped grammar and already
resolves correctly.
"""

import json
import subprocess
import time

from talon import Module, actions, ui

mod = Module()

_TICK_COUNT = 4
_TICK_DELAY_S = 0.12
_LINES_PER_TICK = 1

# app.name Talon reports for the herdr terminal — same signal herder_panel.py's
# `app.name: WezTerm` context match uses.
_HERDR_APP_NAME = "WezTerm"


def _focused_pane_id() -> str | None:
    """The pane_id of whatever herdr pane is currently visible/focused —
    confirmed empirically that exactly one entry across all workspaces
    reports focused: true (the active pane of the active workspace)."""
    try:
        result = subprocess.run(
            ["herdr", "pane", "list"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        panes = json.loads(result.stdout)["result"]["panes"]
    except Exception:
        return None
    for pane in panes:
        if pane.get("focused"):
            return pane.get("pane_id")
    return None


def _pane_dimensions(pane_id: str) -> tuple[int, int] | None:
    """Current (cols, rows) of *pane_id*, read from herdr's own split layout —
    passed to `terminal session control` below so the connection never has to
    guess/negotiate a size. Without an explicit --cols/--rows, that command
    resizes the pane's terminal grid to whatever default it picks on connect
    and back again on disconnect — visible as the pane briefly shrinking then
    snapping back to size."""
    try:
        result = subprocess.run(
            ["herdr", "pane", "layout", "--pane", pane_id],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        layout = json.loads(result.stdout)["result"]["layout"]
    except Exception:
        return None
    for pane in layout.get("panes", []):
        if pane.get("pane_id") == pane_id:
            rect = pane["rect"]
            return rect["width"], rect["height"]
    return None


def _scroll_burst(pane_id: str, direction: str, ticks: int):
    cmd = ["herdr", "terminal", "session", "control", pane_id]
    dims = _pane_dimensions(pane_id)
    if dims is not None:
        cols, rows = dims
        cmd += ["--cols", str(cols), "--rows", str(rows)]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return
    try:
        for _ in range(ticks):
            line = json.dumps(
                {
                    "type": "terminal.scroll",
                    "direction": direction,
                    "lines": _LINES_PER_TICK,
                }
            )
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            time.sleep(_TICK_DELAY_S)
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


@mod.action_class
class Actions:
    def herder_scroll_burst(direction: str, count: int = 1):
        """Rapid multi-tick scroll of the herdr pane (up/down) via herdr's own terminal session control channel.
        *count* multiplies the base tick count, same convention as Rango's "upper two"/"upper three".
        """
        pane_id = _focused_pane_id()
        if pane_id is None:
            return
        _scroll_burst(pane_id, direction, _TICK_COUNT * count)

    def upper_downer_opposite(direction: str):
        """Reverse-sound target for "upper"/"downer" — scroll *direction* ("up"/"down"),
        routed to herdr's rapid scroll or Rango's page scroll depending on which is
        focused. See opposite_mappings.py's "upper"/"downer" entries."""
        if ui.active_app().name == _HERDR_APP_NAME:
            actions.user.herder_scroll_burst(direction)
        else:
            rango_action = "scrollUpPage" if direction == "up" else "scrollDownPage"
            actions.user.rango_command_without_target(rango_action)
