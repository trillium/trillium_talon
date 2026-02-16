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
    "static_percent": 20,
}


def get_week_percent() -> int:
    """Get percentage of week elapsed since last Wednesday 7pm to next Wednesday 7pm."""
    now = datetime.now()
    days_since_wed = (now.weekday() - 2) % 7
    last_wed_7pm = now.replace(hour=19, minute=0, second=0, microsecond=0) - timedelta(
        days=days_since_wed
    )
    if last_wed_7pm > now:
        last_wed_7pm -= timedelta(weeks=1)
    next_wed_7pm = last_wed_7pm + timedelta(weeks=1)
    elapsed = (now - last_wed_7pm).total_seconds()
    total = (next_wed_7pm - last_wed_7pm).total_seconds()
    return int(elapsed / total * 100)


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
    """Write current state to JSON file."""
    with open(STATE_FILE, "w") as f:
        json.dump(_state, f, indent=2)


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


def _poll_microphone():
    try:
        microphone = actions.sound.active_microphone()
    except Exception:
        microphone = "unknown"
    update(microphone=microphone)


def _poll_week_percent():
    update(week_percent=get_week_percent())


def on_ready():
    # Flush initial state (with computed values)
    _state["week_percent"] = get_week_percent()
    _flush()

    registry.register("update_contexts", _on_update_contexts)
    cron.interval("500ms", _poll_microphone)
    cron.interval("60s", _poll_week_percent)


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
