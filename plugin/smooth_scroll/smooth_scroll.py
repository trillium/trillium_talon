"""Trackpad-style smooth scroll: pixel events with gesture and momentum phases.

Posts the same event shape a two-finger trackpad scroll produces, using
CoreGraphics from a small Rust helper process (macOS only).
"""

import json
import subprocess
import time
from pathlib import Path

from talon import Module, app, cron, ctrl, settings, ui

mod = Module()

mod.setting(
    "smooth_scroll_pixels",
    type=int,
    default=11,
    desc="Pixels per frame while the simulated finger is down (also the glide's starting speed)",
)
mod.setting(
    "smooth_scroll_frames",
    type=int,
    default=30,
    desc="Frames of finger movement before the glide starts",
)
mod.setting(
    "smooth_scroll_frame_ms",
    type=int,
    default=16,
    desc="Milliseconds between scroll events",
)
mod.setting(
    "smooth_scroll_decay",
    type=float,
    default=0.92,
    desc="Glide speed multiplier per frame; closer to 1 glides longer",
)
mod.setting(
    "smooth_scroll_min_pixels",
    type=float,
    default=0.5,
    desc="Glide stops when its speed falls to this many pixels per frame",
)


HELPER = (
    Path(__file__).parent / "helper-rs" / "target" / "release" / "smooth-scroll-helper"
)
RESULT_FILE = Path(__file__).with_name("last_run.json")
RECORDER = (
    Path(__file__).parent / "recorder-rs" / "target" / "release" / "scroll-recorder"
)
RECORDING_FILE = Path(__file__).with_name("recording.jsonl")
HOLD_CONTROL = Path(__file__).with_name(
    "hold.touch"
)  # touched while the sound continues
HOLD_RESULT = Path(__file__).with_name("hold_run.json")
PROFILE_FILE = Path(__file__).with_name(
    "profile.jsonl"
)  # the captain's own short scroll

_last_run: dict = {}
_poll_job = None
_hold_proc = None
_hold_dir = None
_proc = None  # the most recent mimic helper, so a newer call can replace it
_park_proc = None  # the live helper that moved the pointer, if any
_park_origin = None  # where the pointer was before the first parked helper moved it
_OVERRIDES_FILE = Path(__file__).with_name("overrides.json")


def _load_overrides() -> dict:
    try:
        return json.loads(_OVERRIDES_FILE.read_text())
    except (OSError, ValueError):
        return {}


# Voice-set values; they win over the settings() block until reset.
_overrides = _load_overrides()


def _get(name: str):
    if name in _overrides:
        return _overrides[name]
    return settings.get(f"user.smooth_scroll_{name}")


# Callbacks run after any value changes (the panel registers one).
_listeners: list = []


def _changed():
    for fn in list(_listeners):
        try:
            fn()
        except Exception as e:  # a broken listener must not break scrolling
            print(f"smooth_scroll listener error: {e}")


def _set(name: str, value):
    _overrides[name] = value
    _OVERRIDES_FILE.write_text(json.dumps(_overrides))
    _changed()


def last_run() -> dict:
    """Measured numbers for the most recent gesture (empty before the first)."""
    return _last_run


def _poll_result(started: float):
    """Cron tick: pick up the helper's result file once it has written it."""
    global _poll_job, _last_run
    try:
        fresh = RESULT_FILE.stat().st_mtime >= started
    except OSError:
        fresh = False
    if fresh:
        try:
            _last_run = json.loads(RESULT_FILE.read_text())
        except (OSError, ValueError):
            return
        cron.cancel(_poll_job)
        _poll_job = None
        _changed()
    elif time.time() - started > 15:  # helper has a 10s cap; give up quietly
        cron.cancel(_poll_job)
        _poll_job = None


def stats() -> dict:
    """Current values plus the numbers they produce for one gesture."""
    pixels, frames = _get("pixels"), _get("frames")
    decay, min_px = float(_get("decay")), float(_get("min_pixels"))
    frame_ms = _get("frame_ms")
    glide_frames, glide_px, speed = 0, 0, float(pixels)
    while speed > min_px:
        glide_px += round(speed)
        speed *= decay
        glide_frames += 1
    finger_px = pixels * frames
    return {
        "pixels": pixels,
        "frames": frames,
        "frame_ms": frame_ms,
        "decay": round(decay, 3),
        "min_pixels": min_px,
        "finger_px": finger_px,
        "glide_frames": glide_frames,
        "glide_px": glide_px,
        "total_px": finger_px + glide_px,
        "total_ms": (frames + glide_frames) * frame_ms,
        "speed_pxs": round(pixels * 1000 / frame_ms),
        "overridden": sorted(_overrides),
    }


def _summary() -> str:
    return (
        f"distance {_get('pixels')}px x {_get('frames')} frames, "
        f"glide decay {float(_get('decay')):.2f}, event every {_get('frame_ms')}ms"
    )


_job = None


def _park_prepare(old_procs, park: bool) -> list:
    """Extra helper args to scroll over the focused window and put the pointer back after.

    The pointer's original spot survives a replaced helper: a killed helper never restores,
    so the next one inherits the origin instead of reading the already-parked pointer.
    """
    global _park_proc, _park_origin
    carrying = (
        _park_proc is not None
        and _park_proc.poll() is None
        and _park_origin is not None
    )
    if not park:
        if carrying:  # a killed parked helper left the pointer over the window
            ctrl.mouse_move(*_park_origin)
            _park_origin = None
        return []
    if not carrying:
        _park_origin = ctrl.mouse_pos()
    rect = ui.active_window().rect
    target = (rect.x + rect.width / 2, rect.y + rect.height / 2)
    return [
        "--park",
        f"{target[0]:.1f},{target[1]:.1f},{_park_origin[0]:.1f},{_park_origin[1]:.1f}",
    ]


@mod.action_class
class Actions:
    def smooth_scroll_demo(direction: str):
        """Play one trackpad-style smooth scroll gesture, 'down' or 'up'"""
        global _poll_job
        if app.platform != "mac":
            app.notify("smooth scroll demo is macOS only")
            return
        if not HELPER.exists():
            app.notify(
                "smooth scroll: build the helper (cargo build --release in helper-rs)"
            )
            return
        args = [
            direction,
            _get("pixels"),
            _get("frames"),
            _get("frame_ms"),
            float(_get("decay")),
            float(_get("min_pixels")),
            str(RESULT_FILE),
        ]
        # Fire and forget: the helper plays the gesture on its own clock and exits.
        subprocess.Popen(
            [str(HELPER)] + [str(a) for a in args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        started = time.time()
        if _poll_job is not None:
            cron.cancel(_poll_job)
        _poll_job = cron.interval("250ms", lambda: _poll_result(started))

    def smooth_scroll_scale(factor: float):
        """Make the scroll gesture longer or shorter by a factor (1.25 = 25% farther)"""
        _set("pixels", max(1, round(_get("pixels") * factor)))
        app.notify(f"smooth scroll: {_summary()}")

    def smooth_scroll_glide(longer: bool):
        """Make the glide after the gesture longer or shorter"""
        decay = float(_get("decay"))
        decay = 1 - (1 - decay) * (0.75 if longer else 1.33)
        _set("decay", round(min(0.99, max(0.5, decay)), 3))
        app.notify(f"smooth scroll: {_summary()}")

    def smooth_scroll_set(name: str, value: float):
        """Set one smooth scroll value by name: pixels, frames, frame_ms, decay, min_pixels"""
        if name not in ("pixels", "frames", "frame_ms", "decay", "min_pixels"):
            app.notify(f"smooth scroll: unknown setting {name}")
            return
        _set(name, value if name in ("decay", "min_pixels") else int(value))
        app.notify(f"smooth scroll: {_summary()}")

    def smooth_scroll_show():
        """Show the current smooth scroll values"""
        app.notify(f"smooth scroll: {_summary()}")

    def smooth_scroll_reset():
        """Discard voice-set smooth scroll values and use the settings block"""
        _overrides.clear()
        _OVERRIDES_FILE.unlink(missing_ok=True)
        _changed()
        app.notify(f"smooth scroll reset: {_summary()}")

    def smooth_scroll_record(seconds: int):
        """Record real scroll events for a few seconds into recording.jsonl, then stop by itself"""
        if not RECORDER.exists():
            app.notify(
                "smooth scroll: build the recorder (cargo build --release in recorder-rs)"
            )
            return
        subprocess.Popen(
            [str(RECORDER), str(seconds), str(RECORDING_FILE)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        app.notify(f"smooth scroll: recording {seconds}s, scroll now")

    def smooth_scroll_replay(index: int):
        """Replay one gesture from recording.jsonl (0 = first) with its original timing"""
        global _poll_job
        if not HELPER.exists() or not RECORDING_FILE.exists():
            app.notify(
                "smooth scroll: need the helper and a recording (say 'demo record')"
            )
            return
        subprocess.Popen(
            [str(HELPER), "replay", str(RECORDING_FILE), str(index), str(RESULT_FILE)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        started = time.time()
        if _poll_job is not None:
            cron.cancel(_poll_job)
        _poll_job = cron.interval("250ms", lambda: _poll_result(started))

    def smooth_scroll_mimic(direction: str):
        """Play the captain's recorded short scroll (profile.jsonl); distance follows the pixels setting"""
        _mimic(direction, False)

    def smooth_scroll_mimic_parked(direction: str):
        """Same scroll, but with the pointer moved over the focused window and put back after"""
        _mimic(direction, True)

    def smooth_scroll_stretch(factor: float):
        """Make the recorded scroll take longer (1.15 = 15% longer) or shorter, same distance"""
        _set("stretch", round(float(_overrides.get("stretch", 1.0)) * factor, 3))
        app.notify(f"smooth scroll: duration x{_overrides['stretch']}")

    def smooth_scroll_hold(direction: str):
        """Keep scrolling while this is called repeatedly (hiss); glide out when the calls stop"""
        _hold(direction, False)

    def smooth_scroll_hold_parked(direction: str):
        """Hold scroll with the pointer parked over the focused window, restored after the glide"""
        _hold(direction, True)


def _spawn(args: list):
    return subprocess.Popen(
        [str(HELPER)] + args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _mimic(direction: str, park: bool):
    global _poll_job, _proc, _park_proc
    if not HELPER.exists() or not PROFILE_FILE.exists():
        app.notify("smooth scroll: need the helper and profile.jsonl")
        return
    scale = (
        _get("pixels") / 11
    )  # 11 px/frame is the default, so 1.0 plays the recording as-is
    # Decide the pointer's origin while any parked helper is still alive.
    park_args = _park_prepare((_proc, _hold_proc), park)
    # A newer call replaces a gesture still playing: whatever the old one
    # already moved stands, and the new one plays in full from its own start.
    interrupted = False
    for old in (_proc, _hold_proc):
        if old is not None and old.poll() is None:
            old.kill()
            old.wait()
            interrupted = True
    stretch = float(_overrides.get("stretch", 1.0))
    _proc = _spawn(
        [
            "replay",
            str(PROFILE_FILE),
            "0",
            str(RESULT_FILE),
            direction,
            f"{scale:.3f}",
            f"{stretch:.3f}",
        ]
        + (["cancel"] if interrupted else [])
        + park_args
    )
    _park_proc = _proc if park else None
    started = time.time()
    if _poll_job is not None:
        cron.cancel(_poll_job)
    _poll_job = cron.interval("250ms", lambda: _poll_result(started))


def _hold(direction: str, park: bool):
    global _hold_proc, _hold_dir, _proc, _park_proc
    if not HELPER.exists():
        app.notify("smooth scroll: build the helper")
        return
    HOLD_CONTROL.touch()
    same = (
        _hold_proc is not None and _hold_proc.poll() is None and _hold_dir == direction
    )
    if same and (_park_proc is _hold_proc) == park:
        return  # already running; the touch keeps it going
    park_args = _park_prepare((_hold_proc, _proc), park)
    interrupted = False
    for old in (_hold_proc, _proc):
        if old is not None and old.poll() is None:
            old.kill()
            old.wait()
            interrupted = True
    _hold_dir = direction
    _hold_proc = _spawn(
        [
            "hold",
            direction,
            str(_get("pixels")),
            str(_get("frame_ms")),
            str(float(_get("decay"))),
            str(float(_get("min_pixels"))),
            str(HOLD_CONTROL),
            str(HOLD_RESULT),
        ]
        + (["cancel"] if interrupted else [])
        + park_args
    )
    _park_proc = _hold_proc if park else None
