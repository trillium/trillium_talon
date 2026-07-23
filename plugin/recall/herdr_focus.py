"""Voice-alias jump to a specific herdr tab/pane.

Say an alias (e.g. "mayor", "firstmate", "edgar") to focus that agent's herdr tab
and bring the herdr host terminal to the front. Extends recall's "focus a thing
by name" idea to "focus a herdr tab", but is self-contained — it does NOT touch
recall's persistent overlay (which has a known focus bug), it just shells out to
the herdr CLI.

Targets are resolved DYNAMICALLY at command time (tab/pane ids change across
restarts): named agents focus by name; the firstmate/mayor tabs are nameless in
herdr, so they resolve by cwd to whatever pane currently holds them.
"""

import json
import subprocess

from talon import Module, actions

mod = Module()

# Spoken alias -> focus target token. Values are either a herdr agent NAME, or
# "cwd:<substring>" to resolve a nameless tab by its working directory.
# Edit herdr_tab_alias.talon-list to add/rename aliases.
mod.list("herdr_tab_alias", desc="Spoken alias -> herdr focus target (agent name or cwd:<substr>)")

HERDR = "herdr"          # on PATH (~/.local/bin/herdr)
HERDR_HOST_APP = "WezTerm"  # the macOS app that hosts the herdr workspace


def _resolve_target_by_cwd(substr: str):
    """Return the current pane_id (or tab_id) of the herdr agent whose cwd
    contains `substr`, or None. Used for nameless tabs (mayor/firstmate)."""
    try:
        out = subprocess.run(
            [HERDR, "agent", "list"], capture_output=True, text=True, timeout=5
        ).stdout
        agents = json.loads(out).get("result", {}).get("agents", [])
        for a in agents:
            if substr in (a.get("cwd") or ""):
                return a.get("pane_id") or a.get("tab_id")
    except Exception as e:
        print(f"[herdr_focus] agent list failed: {e}")
    return None


@mod.action_class
class Actions:
    def herdr_focus_tab(target: str):
        """Focus the herdr tab for `target` (agent name, or 'cwd:<substr>') and
        bring the herdr host app to the foreground."""
        focus_arg = target
        if target.startswith("cwd:"):
            focus_arg = _resolve_target_by_cwd(target[len("cwd:"):])
            if not focus_arg:
                print(f"[herdr_focus] no herdr tab found for {target}")
                return
        try:
            subprocess.run([HERDR, "agent", "focus", focus_arg], check=False, timeout=5)
        except Exception as e:
            print(f"[herdr_focus] focus '{focus_arg}' failed: {e}")
            return
        # Bring the herdr host terminal forward so the focused tab is visible.
        try:
            subprocess.run(["open", "-a", HERDR_HOST_APP], check=False, timeout=5)
        except Exception as e:
            print(f"[herdr_focus] foreground {HERDR_HOST_APP} failed: {e}")
