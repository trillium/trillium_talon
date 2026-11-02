import datetime
import json
import math
import threading
import time
from pathlib import Path
from typing import Optional, Union

from talon import Module, actions, app, cron, ui
from talon.canvas import Canvas
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.types import Rect

from ..utils.overlay_kit import draw_rounded_rect

module = Module()

lock = threading.Lock()
start_time = None
current_duration = None
pomodoro_type = None
pause_time = None
finished = False
cancel_job = None

_canvas = None
_redraw_job = None

# Persisted wall-clock state for external readers (e.g. row.sh `row pomodoro`).
# Contract: {"active": bool, "end_iso": ISO8601, "end_epoch": int, "paused": bool}
# active=false when nothing is running. Rewritten on every state change.
STATE_FILE = Path.home() / ".talon" / "pomodoro-state.json"


def _write_state():
    """Persist the current pomodoro state to STATE_FILE (atomic write).

    The timer runs on time.monotonic() in-memory; here we convert the remaining
    duration into a wall-clock end time so external tools can read when it ends.
    Call OUTSIDE the module `lock` (it acquires the lock itself) — callers must
    not already hold it, or this deadlocks.
    """
    with lock:
        active = (
            pomodoro_type is not None
            and start_time is not None
            and current_duration is not None
        )
        paused = bool(pause_time)
        if active:
            ref = pause_time if pause_time else time.monotonic()
            remaining = current_duration - (ref - start_time)
            if remaining < 0:
                remaining = 0
            end_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                seconds=remaining
            )
            end_iso = end_utc.astimezone().replace(microsecond=0).isoformat()
            end_epoch = int(end_utc.timestamp())
        else:
            end_iso = ""
            end_epoch = 0

    state = {
        "active": active,
        "end_iso": end_iso,
        "end_epoch": end_epoch,
        "paused": paused,
    }
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(STATE_FILE)
    except Exception as e:
        print(f"[pomodoro] failed to write {STATE_FILE}: {e}")


# Style — matches window_focus_announcer pill but offset to the right
FONT_SIZE = 13
PAD_X = 8
PAD_Y = 3
BG_COLOR = "000000cc"
TEXT_COLOR = "ffffffff"
FINISHED_COLOR = "ff4444ff"
CORNER_RADIUS = 4
# Offset from left edge so it doesn't overlap the window announcer pill
PILL_OFFSET_X = 0
DOT_COLOR = "00ff00ff"
DOT_RADIUS = 3


class BorderPath:
    """U-shaped path around a rounded rect: top-left → down → across bottom → up → top-right."""

    def __init__(self, x: float, y: float, w: float, h: float, radius: float):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.r = min(radius, w / 2, h / 2)

        self.left = h - self.r
        self.bl_arc = math.pi * self.r / 2
        self.bottom = w - 2 * self.r
        self.br_arc = math.pi * self.r / 2
        self.right = h - self.r

        self.total = self.left + self.bl_arc + self.bottom + self.br_arc + self.right

    def position_at_fraction(self, fraction: float) -> tuple:
        """(x, y) at fraction 0→1 along the U path."""
        d = max(0.0, min(1.0, fraction)) * self.total

        # Left edge: top-left down
        if d <= self.left:
            return self.x, self.y + d
        d -= self.left

        # Bottom-left arc
        if d <= self.bl_arc:
            angle = d / self.bl_arc * (math.pi / 2)
            cx = self.x + self.r
            cy = self.y + self.h - self.r
            return cx - self.r * math.cos(angle), cy + self.r * math.sin(angle)
        d -= self.bl_arc

        # Bottom edge: left to right
        if d <= self.bottom:
            return self.x + self.r + d, self.y + self.h
        d -= self.bottom

        # Bottom-right arc
        if d <= self.br_arc:
            angle = d / self.br_arc * (math.pi / 2)
            cx = self.x + self.w - self.r
            cy = self.y + self.h - self.r
            return cx + self.r * math.sin(angle), cy + self.r * math.cos(angle)
        d -= self.br_arc

        # Right edge: bottom up to top-right
        return self.x + self.w, self.y + self.h - self.r - d


def _get_progress_fraction() -> float:
    """Return elapsed seconds within the current minute as fraction 0→1. One full lap per minute."""
    with lock:
        if start_time is None or current_duration is None:
            return 0.0
        current_time = pause_time if pause_time else time.monotonic()
        elapsed = current_time - start_time
        if elapsed >= current_duration:
            return 0.0
        return (elapsed % 60.0) / 60.0


def _get_display_text() -> str:
    with lock:
        if pomodoro_type is None:
            return ""
        current_time = pause_time if pause_time else time.monotonic()
        remaining_time = math.ceil((current_duration + start_time - current_time) / 60)
        if remaining_time <= 0:
            flashes_per_second = 1.5
            suffix = (
                "FINISHED" if int(time.monotonic() * flashes_per_second) % 2 else ""
            )
            return f"{pomodoro_type} -- {suffix}"
        else:
            return f"{pomodoro_type} {remaining_time:02d}"


def _draw(c: SkiaCanvas):
    text = _get_display_text()
    if not text:
        return

    c.paint.textsize = FONT_SIZE
    c.paint.font.embolden = True
    text_rect = c.paint.measure_text(text)[1]

    pill_w = text_rect.width + PAD_X * 2
    pill_h = text_rect.height + PAD_Y * 2
    pill_x = c.rect.x + PILL_OFFSET_X
    pill_y = c.rect.y

    bg_rect = Rect(pill_x, pill_y, pill_w, pill_h)

    c.paint.style = c.paint.Style.FILL
    c.paint.color = BG_COLOR
    draw_rounded_rect(c, bg_rect, CORNER_RADIUS)

    # Flash red when finished
    with lock:
        is_finished = (
            start_time is not None and time.monotonic() > start_time + current_duration
        )
    c.paint.color = FINISHED_COLOR if is_finished else TEXT_COLOR
    c.draw_text(text, pill_x + PAD_X, pill_y + PAD_Y + text_rect.height)

    # Progress dot traversing the pill border
    fraction = _get_progress_fraction()
    if fraction > 0.0 and not is_finished:
        border = BorderPath(pill_x, pill_y, pill_w, pill_h, CORNER_RADIUS)
        # Invert: fraction 1 = start (top-left), fraction 0 = done (top-right)
        dot_x, dot_y = border.position_at_fraction(1.0 - fraction)
        c.paint.shader = None
        c.paint.imagefilter = None
        c.paint.style = c.paint.Style.FILL
        c.paint.color = DOT_COLOR
        c.draw_circle(dot_x, dot_y, DOT_RADIUS)


def _show_canvas():
    global _canvas
    if _canvas:
        _canvas.close()
        _canvas = None

    screen = ui.main_screen()
    _canvas = Canvas.from_screen(screen)
    _canvas.register("draw", _draw)
    _canvas.freeze()


def _redraw():
    """Called every second to update the display."""
    if _canvas:
        _canvas.freeze()


def _hide_canvas():
    global _canvas, _redraw_job
    if _redraw_job:
        cron.cancel(_redraw_job)
        _redraw_job = None
    if _canvas:
        _canvas.close()
        _canvas = None


def delete_cancel_cron():
    global cancel_job
    try:
        cron.cancel(cancel_job)
    except:
        pass
    cancel_job = None


def check_pomodoro():
    with lock:
        if start_time and time.monotonic() > start_time + current_duration:
            delete_cancel_cron()
            finished = True
            actions.key("f20")


@module.action_class
class Actions:
    def pomodoro_start(
        type_: Optional[str] = "W",
        minutes_: Optional[Union[int, float]] = 25 * 60,
        seconds_: Optional[int] = 0,
    ):
        """Start a pomodoro of `type` of length `time`."""
        global start_time, pomodoro_type, pause_time, finished, cancel_job, current_duration, _redraw_job

        print("pomodoro", minutes_, seconds_)
        with lock:
            delete_cancel_cron()
            cancel_job = cron.interval("1s", check_pomodoro)

            start_time = time.monotonic()
            pomodoro_type = type_
            current_duration = int(round(minutes_)) + int(seconds_)
            pause_time = None
            finished = False

        _show_canvas()
        _redraw_job = cron.interval("1s", _redraw)
        _write_state()

    def pomodoro_pause():
        """Pause the active pomodoro."""
        global pause_time
        with lock:
            if not pause_time:
                pause_time = time.monotonic()
        _write_state()

    def pomodoro_unpause():
        """Unpause the active pomodoro."""
        global pause_time, start_time
        with lock:
            if pause_time:
                # Shift start_time forward by the paused span so `remaining`
                # (current_duration - (now - start_time)) is unchanged on resume.
                start_time += time.monotonic() - pause_time
                pause_time = None
        _write_state()

    def pomodoro_cancel():
        """Cancel the active pomodoro."""
        global start_time, pomodoro_type, pause_time, current_duration
        with lock:
            delete_cancel_cron()
            if not pomodoro_type:
                raise RuntimeError("No pomodoro running.")
            pomodoro_type = None
            start_time = None
            pause_time = None
            current_duration = None
        _hide_canvas()
        _write_state()

    def pomodoro_get_end_time(fmt: str = None) -> str:
        """Return the end time of the pomodoro"""
        global current_duration, start_time
        global start_time, pomodoro_type, pause_time, current_duration
        current_time = pause_time if pause_time else time.monotonic()
        remaining_time = math.ceil((current_duration + start_time - current_time) / 60)

        timestamp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=remaining_time
        )
        local_timestamp = timestamp.astimezone().replace(microsecond=0)

        if fmt is None:
            return local_timestamp.isoformat()
        return local_timestamp.strftime(fmt)

    def get_time_local(fmt: str = None) -> str:
        """Return the current local time with timezone info."""
        local_timestamp = datetime.datetime.now().astimezone().replace(microsecond=0)
        if fmt is None:
            return local_timestamp.isoformat()
        return local_timestamp.strftime(fmt)

    def get_time_local_ago(minutes: int, fmt: str = None) -> str:
        """Return the local time minus the given number of minutes."""
        local_timestamp = datetime.datetime.now().astimezone().replace(microsecond=0)
        ago_timestamp = local_timestamp - datetime.timedelta(minutes=minutes)
        if fmt is None:
            return ago_timestamp.isoformat()
        return ago_timestamp.strftime(fmt)

    def get_time_local_future(minutes: int, fmt: str = None) -> str:
        """Return the local time plus the given number of minutes."""
        local_timestamp = datetime.datetime.now().astimezone().replace(microsecond=0)
        future_timestamp = local_timestamp + datetime.timedelta(minutes=minutes)
        if fmt is None:
            return future_timestamp.isoformat()
        return future_timestamp.strftime(fmt)
