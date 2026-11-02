"""
Herder — voice verb+target orchestration over herdr + firstmate.

One compact grammar maps a spoken verb+agent onto the real herdr agent CLI:
  "herder muse"                       -> herdr agent focus muse
  "herder muse say <prose> bravely"   -> herdr agent send muse "<prose>" + Enter
  "herder next working"               -> herdr-rotate working

The sayable agent list (user.herder_targets) is auto-populated from live
`herdr agent list` every 60s (and on load), so any agent that spawns becomes
voiceable with zero manual editing — same cron pattern as command_surfacer.

Prototype v1 (2026-07-15): navigation (focus/rotate) + send. Spawn/merge/deploy
verbs are the next layer — they need arguments, so they are intentionally left
out of this first cut.
"""

import json
import shlex
import subprocess
from pathlib import Path

from talon import Context, Module, actions, app, cron

mod = Module()
ctx = Context()

# mod.list takes the bare name; Talon namespaces it to user.herder_targets. (Passing
# "user.herder_targets" here raises "names cannot contain dots" and breaks the whole plugin.)
mod.list("herder_targets", desc="Live herdr agent names, sayable as herder targets")

_LIST_FILE = Path(__file__).parent / "herder_targets.talon-list"
_REFRESH_INTERVAL = "60s"
_refresh_cron = None

# Talon.app is a GUI process; its subprocess PATH (launchd/GUI) usually lacks
# /opt/homebrew/bin and ~/.local/bin. Use a full path for list-form subprocess and a
# PATH prefix for shell commands, so herdr / herdr-rotate resolve regardless. (Same
# reason ticket/agent.py hard-codes /opt/homebrew/bin/claude.)
_HERDR = "/opt/homebrew/bin/herdr"
_ENV = 'PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH" '


def _herdr_agents() -> list[dict]:
    """Return the agent dicts from `herdr agent list` (JSON on stdout)."""
    try:
        out = subprocess.run(
            [_HERDR, "agent", "list"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
        return json.loads(out).get("result", {}).get("agents", [])
    except Exception:
        return []


def _named_agents() -> list[str]:
    """Distinct agent names — unnamed panes are not addressable by name."""
    seen: list[str] = []
    for a in _herdr_agents():
        name = a.get("name")
        if name and name not in seen:
            seen.append(name)
    return seen


def _pane_for(target: str) -> str | None:
    for a in _herdr_agents():
        if a.get("name") == target:
            return a.get("pane_id")
    return None


def _write_list_file(names: list[str]) -> None:
    """Persist the sayable list so it is inspectable and survives restart."""
    lines = ["list: user.herder_targets", "-"] + [f"{n}: {n}" for n in names]
    try:
        _LIST_FILE.write_text("\n".join(lines) + "\n")
    except Exception:
        pass


_pending_proc = None


def _refresh() -> None:
    """Fully NON-BLOCKING refresh — never stalls Talon's main thread.
    Spawns `herdr agent list` via Popen (returns instantly), then polls proc.poll() in
    short cron ticks (each an instant, non-blocking check) until it finishes and reads the
    already-buffered output. No blocking subprocess.run, no raw threading.Thread (which
    Talon warns about). This is the pattern for ALL these tools: zero cron stall, ever."""
    global _pending_proc
    if _pending_proc is not None:
        return  # a refresh is already in flight; don't stack them
    try:
        _pending_proc = subprocess.Popen(
            [_HERDR, "agent", "list"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except Exception:
        _pending_proc = None
        return
    cron.after("50ms", _poll_refresh)


def _poll_refresh() -> None:
    global _pending_proc
    p = _pending_proc
    if p is None:
        return
    if p.poll() is None:
        cron.after("50ms", _poll_refresh)  # still running — check again, instantly
        return
    _pending_proc = None
    try:
        out = p.stdout.read() if p.stdout else ""
        agents = json.loads(out).get("result", {}).get("agents", [])
    except Exception:
        return
    names: list[str] = []
    for a in agents:
        n = a.get("name")
        if n and n not in names:
            names.append(n)
    if names:
        ctx.lists["user.herder_targets"] = {n: n for n in names}
        _write_list_file(names)


@mod.action_class
class Actions:
    def herder_focus(target: str):
        """Focus a herdr agent pane by name."""
        actions.user.system_command_nb(_ENV + f"herdr agent focus {shlex.quote(target)}")

    def herder_send(target: str, text: str):
        """Send prose to a herdr agent pane (does not submit)."""
        actions.user.system_command_nb(
            _ENV + f"herdr agent send {shlex.quote(target)} {shlex.quote(text)}"
        )

    def herder_submit(target: str):
        """Press Enter in the target agent's pane."""
        pane = _pane_for(target)
        if pane:
            actions.user.system_command_nb(
                _ENV + f"herdr pane send-keys {shlex.quote(pane)} Enter"
            )

    def herder_rotate(status: str):
        """Cycle focus through agents by status via herdr-rotate."""
        actions.user.system_command_nb(_ENV + f"herdr-rotate {shlex.quote(status)}")

    def herder_refresh_targets():
        """Manually re-pull the sayable agent list from herdr."""
        _refresh()


def _start():
    """Idempotent startup: prime the list once, then refresh on an interval."""
    global _refresh_cron
    if _refresh_cron is not None:
        return
    _refresh()
    _refresh_cron = cron.interval(_REFRESH_INTERVAL, _refresh)


# Fire shortly after load so it works on hot-reload (already past "ready"),
# and also on a cold start. _start is idempotent, so this never double-arms.
cron.after("500ms", _start)
app.register("ready", _start)
