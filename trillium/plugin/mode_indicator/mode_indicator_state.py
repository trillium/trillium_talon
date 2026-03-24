"""
Mode Indicator State Writer

Detects mode, microphone, and parrot state changes and writes them
to a JSON file. The renderer (mode_indicator.py) watches this file
via @resource.watch() and redraws when it changes.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from talon import Module, actions, app, cron, registry, scope

STATE_FILE = Path(__file__).parent / "mode_indicator_state.json"

mod = Module()

_state = {
    "mode": "",
    "microphone": "",
    "parrot_on": False,
    "command_text": "",
    "opposite_text": "",
    "bar_color_override": None,
    "week_percent": 0,
    "week_remaining": "",
    "cpu_per_core": [],
    "mem_percent": 0,
    "mem_pressure": 0,
    "pondering_seconds": None,
}


def _week_bounds():
    """Return (last_thu_7pm, next_thu_7pm) bracketing now."""
    now = datetime.now()
    days_since_thu = (now.weekday() - 3) % 7
    last_thu_7pm = now.replace(hour=19, minute=0, second=0, microsecond=0) - timedelta(
        days=days_since_thu
    )
    if last_thu_7pm > now:
        last_thu_7pm -= timedelta(weeks=1)
    next_thu_7pm = last_thu_7pm + timedelta(weeks=1)
    return last_thu_7pm, next_thu_7pm


def get_week_percent() -> int:
    """Get percentage of week elapsed since last Thursday 7pm to next Thursday 7pm."""
    now = datetime.now()
    start, end = _week_bounds()
    elapsed = (now - start).total_seconds()
    total = (end - start).total_seconds()
    return int(elapsed / total * 100)


def get_week_remaining() -> str:
    """Get remaining time until next Thursday 7pm as 'Xd Yh' or 'Xh Ym'."""
    now = datetime.now()
    _, end = _week_bounds()
    remaining = int((end - now).total_seconds())
    if remaining <= 0:
        return "0h"
    days = remaining // 86400
    hours = (remaining % 86400) // 3600
    minutes = (remaining % 3600) // 60
    if days > 0:
        return f"{days}d{hours}h"
    return f"{hours}h{minutes}m"


def update(**kwargs):
    """Merge changes into state and flush to disk if anything changed."""
    changed = False
    for key, value in kwargs.items():
        if key in _state and _state[key] != value:
            _state[key] = value
            changed = True
    if changed:
        _flush()


def _flush():
    """Write current state to JSON file, preserving keys set by external scripts."""
    # Read existing file to preserve externally-managed keys
    try:
        on_disk = json.loads(STATE_FILE.read_text())
    except Exception:
        on_disk = {}
    on_disk.update(_state)
    with open(STATE_FILE, "w") as f:
        json.dump(on_disk, f, indent=2)


def _on_update_contexts():
    modes = scope.get("mode")
    if "sleep" in modes:
        mode = "sleep"
    elif "dictation" in modes:
        if "command" in modes:
            mode = "mixed"
        else:
            mode = "dictation"
    elif "command" in modes:
        mode = "command"
    else:
        mode = "other"

    tags = scope.get("tag", [])
    parrot_on = "user.parrot_on" in tags

    update(mode=mode, parrot_on=parrot_on)

    # Persist mode state for restoration on next boot/crash
    _save_mode_state(modes, tags)


# ── Mode persistence across boots ────────────────────────────────────

_MODE_STATE_FILE = Path.home() / ".talon" / "mode_state.json"
_last_saved_modes = None
_last_saved_tags = None


def _save_mode_state(modes, tags):
    """Save current mode and tags to disk, but only when they change."""
    global _last_saved_modes, _last_saved_tags
    modes_key = tuple(sorted(modes)) if modes else ()
    tags_to_save = tuple(t for t in (tags or []) if t in ("user.parrot_on",))

    if modes_key == _last_saved_modes and tags_to_save == _last_saved_tags:
        return

    _last_saved_modes = modes_key
    _last_saved_tags = tags_to_save

    try:
        state = {
            "modes": list(modes_key),
            "tags": list(tags_to_save),
        }
        _MODE_STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def _poll_microphone():
    try:
        microphone = actions.sound.active_microphone()
    except Exception:
        microphone = "unknown"
    update(microphone=microphone)


def _poll_week_percent():
    update(week_percent=get_week_percent(), week_remaining=get_week_remaining())


SYSMON_STATS = Path.home() / "code" / "system-monitor" / "data" / "stats.json"


def _poll_sysmon():
    """Read system monitor stats and merge CPU per-core + memory into state."""
    try:
        data = json.loads(SYSMON_STATS.read_text())
        cpu = data.get("cpu", {})
        mem = data.get("memory", {})
        per_core = cpu.get("per_core", [])
        mem_percent = mem.get("percent", 0)
        mem_pressure = mem.get("pressure", 0)
        update(
            cpu_per_core=per_core,
            mem_percent=mem_percent,
            mem_pressure=mem_pressure,
        )
    except Exception:
        pass


def on_ready():
    # Flush initial state (with computed values)
    _state["week_percent"] = get_week_percent()
    _state["week_remaining"] = get_week_remaining()
    _flush()

    registry.register("update_contexts", _on_update_contexts)
    cron.interval("500ms", _poll_microphone)
    cron.interval("60s", _poll_week_percent)
    cron.interval("1s", _poll_sysmon)


app.register("ready", on_ready)


@mod.action_class
class Actions:
    def mode_indicator_set_command_text(last_command: str, opposite_command: str = ""):
        """Set the last command and opposite command text for the mode indicator"""
        update(command_text=last_command, opposite_text=opposite_command)

    def mode_indicator_set_color(color: str):
        """Set a color override for the top bar (e.g., 'ff0000' for red). Circle keeps mode color."""
        update(bar_color_override=color)

    def mode_indicator_clear_color():
        """Clear the bar color override and return to normal mode-based coloring"""
        update(bar_color_override=None)

    def mode_indicator_set_pondering(seconds: int):
        """Set the pondering timer display in the circle"""
        update(pondering_seconds=seconds)

    def mode_indicator_clear_pondering():
        """Clear the pondering timer from the circle"""
        update(pondering_seconds=None)
