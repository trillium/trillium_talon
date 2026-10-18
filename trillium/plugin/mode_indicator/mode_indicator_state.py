"""
Mode Indicator State Writer

Detects mode, microphone, and parrot state changes and writes them
to a JSON file for external scripts, and pushes every change to the
renderer (mode_indicator.py) in-process through add_listener().

The slow pollers (OBS subprocess, sysmon file read, external-state file)
run on one daemon worker thread and post results back to Talon's main
thread with cron.after, so they never block the cron thread.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

from talon import Module, actions, app, cron, registry, scope, settings

# Outside ~/.talon so Talon's file watcher never sees our own writes.
# poll_usage.py and other external scripts write the same file.
STATE_FILE = Path(
    os.environ.get("TALON_MODE_INDICATOR_STATE")
    or Path.home() / ".cache" / "talon" / "mode_indicator_state.json"
)

mod = Module()
mod.setting(
    "week_reset_day",
    type=int,
    default=3,
    desc="Day of week the usage limit resets (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun)",
)
mod.setting(
    "week_reset_hour",
    type=int,
    default=12,
    desc="Hour of day the usage limit resets (0-23, e.g. 12=noon, 20=8pm)",
)

mod.setting(
    "mode_indicator_obs_python",
    type=str,
    default="",
    desc="Python interpreter with obsws_python installed, used to poll OBS. Empty = python3 on PATH, then Talon's own.",
)

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
    "obs_streaming": False,
    "obs_recording": False,
    "obs_scene": "",
}


def _week_bounds():
    """Return (last_reset, next_reset) bracketing now, based on settings."""
    day = settings.get("user.week_reset_day")
    hour = settings.get("user.week_reset_hour")
    now = datetime.now()
    days_since = (now.weekday() - day) % 7
    last_reset = now.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(
        days=days_since
    )
    if last_reset > now:
        last_reset -= timedelta(weeks=1)
    next_reset = last_reset + timedelta(weeks=1)
    return last_reset, next_reset


def get_week_percent() -> int:
    """Get percentage of week elapsed since last reset to next reset."""
    now = datetime.now()
    start, end = _week_bounds()
    elapsed = (now - start).total_seconds()
    total = (end - start).total_seconds()
    return int(elapsed / total * 100)


def get_week_remaining() -> str:
    """Get remaining time until next reset as 'Xd Yh' or 'Xh Ym'."""
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


_listeners = []
_external = {}  # keys written by external scripts (static_percent, stream_*)


def add_listener(fn):
    """Call fn(full_state_dict) after every state change. Main thread only."""
    _listeners.append(fn)


def snapshot() -> dict:
    """Own state merged over externally-managed keys."""
    return {**_external, **_state}


def _notify():
    data = snapshot()
    for fn in list(_listeners):
        try:
            fn(data)
        except Exception:
            pass


def update(**kwargs):
    """Merge changes into state, flush to disk and notify listeners if anything changed."""
    changed = False
    for key, value in kwargs.items():
        if key in _state and _state[key] != value:
            _state[key] = value
            changed = True
    if changed:
        _flush()
        _notify()


def _flush():
    """Write current state to JSON file, preserving keys set by external scripts."""
    # Read existing file to preserve externally-managed keys
    try:
        on_disk = json.loads(STATE_FILE.read_text())
    except Exception:
        on_disk = {}
    on_disk.update(_state)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(on_disk, indent=2))
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


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

# ── OBS streaming/recording status ──────────────────────────────────
# TODO: This polls OBS websocket every 2s even when not streaming.
#   Ideally we'd only poll when OBS is actually running, or switch to
#   an event-driven approach (OBS websocket supports event subscriptions).
#   The scene name fetch was added here for convenience but adds to the
#   polling overhead. Consider: start/stop polling based on OBS process
#   presence, or use a persistent websocket connection with event callbacks
#   instead of repeated subprocess spawns.

_OBS_POLL_SCRIPT = """
import json, subprocess
try:
    pw = subprocess.run(
        ["security", "find-generic-password", "-s", "obs-websocket", "-w"],
        capture_output=True, text=True, timeout=3,
    ).stdout.strip()
    import obsws_python as obs
    cl = obs.ReqClient(host="localhost", port=4455, password=pw, timeout=2)
    s = cl.get_stream_status()
    r = cl.get_record_status()
    sc = cl.get_current_program_scene()
    print(json.dumps({"streaming": s.output_active, "recording": r.output_active, "scene": sc.scene_name}))
except Exception:
    print(json.dumps({"streaming": False, "recording": False, "scene": ""}))
"""


def _obs_python() -> str:
    try:
        configured = settings.get("user.mode_indicator_obs_python")
    except Exception:
        configured = ""
    return configured or shutil.which("python3") or sys.executable


_OBS_OFF = {"obs_streaming": False, "obs_recording": False, "obs_scene": ""}


def _fetch_obs_status(python: str) -> dict:
    """Blocking: run the OBS query subprocess. Worker thread only."""
    try:
        result = subprocess.run(
            [python, "-c", _OBS_POLL_SCRIPT],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            return {
                "obs_streaming": data.get("streaming", False),
                "obs_recording": data.get("recording", False),
                "obs_scene": data.get("scene", ""),
            }
    except Exception:
        pass
    return dict(_OBS_OFF)


def _fetch_sysmon() -> dict:
    """Blocking: read system monitor stats. Worker thread only."""
    try:
        data = json.loads(SYSMON_STATS.read_text())
        cpu = data.get("cpu", {})
        mem = data.get("memory", {})
        return {
            "cpu_per_core": cpu.get("per_core", []),
            "mem_percent": mem.get("percent", 0),
            "mem_pressure": mem.get("pressure", 0),
        }
    except Exception:
        return {}


_external_mtime = None


def _fetch_external():
    """Blocking: re-read STATE_FILE if an external script changed it. Worker thread only."""
    global _external_mtime
    try:
        mtime = STATE_FILE.stat().st_mtime_ns
        if mtime == _external_mtime:
            return None
        data = json.loads(STATE_FILE.read_text())
        _external_mtime = mtime
        return {k: v for k, v in data.items() if k not in _state}
    except Exception:
        return None


def _apply_external(ext):
    if ext is not None and ext != _external:
        _external.clear()
        _external.update(ext)
        _notify()


OBS_INTERVAL_TICKS = 2  # worker ticks once per second

_stop = threading.Event()
_worker = None


def _worker_loop(post=None):
    """One daemon thread for every slow poll; results go back via cron.after."""
    post = post or (lambda fn: cron.after("0ms", fn))
    tick = 0
    while not _stop.is_set():
        try:
            python = _obs_python() if tick % OBS_INTERVAL_TICKS == 0 else None
            results = {}
            if python is not None:
                results.update(_fetch_obs_status(python))
            results.update(_fetch_sysmon())
            ext = _fetch_external()
            post(lambda r=results, e=ext: (update(**r), _apply_external(e)))
        except Exception:
            pass
        tick += 1
        _stop.wait(1.0)


def start_worker():
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    _stop.clear()
    _worker = threading.Thread(
        target=_worker_loop, name="mode_indicator_pollers", daemon=True
    )
    _worker.start()


def on_ready():
    # Flush initial state (with computed values)
    _state["week_percent"] = get_week_percent()
    _state["week_remaining"] = get_week_remaining()
    _flush()
    _notify()

    registry.register("update_contexts", _on_update_contexts)
    cron.interval("500ms", _poll_microphone)
    cron.interval("60s", _poll_week_percent)
    start_worker()


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
