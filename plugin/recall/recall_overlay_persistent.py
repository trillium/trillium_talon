"""Recall Overlay Persistent - Persistent window border + name tab for ALL saved windows.

Uses a full-screen Canvas.from_screen() for rendering (blocks_mouse=False).
Per-pill Canvas.from_rect() canvases with blocks_mouse=True handle clicks.
Click canvases are rebuilt only on save/forget/redraw — never on a timer.

A focus lock prevents the win_focus cascade that occurs after w.focus():
when a pill click explicitly focuses a window, subsequent focus events are
suppressed for a short window so the highlight doesn't bounce.
"""

import time

from talon import cron, ui
from talon.canvas import Canvas
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from .recall_overlay_draw import draw_persistent
from .recall_overlay_shared import _get_saved_windows


def _pill_rects_equal(a, b) -> bool:
    """Compare two pill-rect lists by coordinate values, not object identity.

    Talon Rect objects don't implement __eq__ by value, so a plain != check
    always returns True even when positions are identical. We compare the
    (name, x, y, w, h) tuples explicitly.
    """
    if a is None or b is None:
        return a is b
    if len(a) != len(b):
        return False
    for (n1, r1), (n2, r2) in zip(a, b):
        if n1 != n2:
            return False
        if (r1.x, r1.y, r1.width, r1.height) != (r2.x, r2.y, r2.width, r2.height):
            return False
    return True


_persistent_canvas: Canvas = None
_persistent_window = None
_persistent_name: str = ""
_redraw_job = None

# Per-pill click canvases: list of Canvas objects
_click_canvases: list = []

# Debug: draw green overlay on click target areas (set True to visualize)
DEBUG_SHOW_CLICK_AREAS = False

# Cached pill rects from the last draw, used to position click canvases.
# List of (name, pill_rect) tuples.
_pill_hit_rects: list = []

# Tracks last-drawn rects so on_draw_persistent can skip redundant rebuilds
# when Talon's canvas redraws fire with no positional change.
_previous_pill_rects = None

# Focus lock: when a pill click calls w.focus(), store the timestamp.
# _on_focus_change in recall.py checks this to suppress the bounce.
_focus_lock_until: float = 0.0
FOCUS_LOCK_DURATION = 0.3  # seconds


def is_focus_locked() -> bool:
    """Check if a pill-click focus lock is active."""
    return time.monotonic() < _focus_lock_until


def _set_focus_lock():
    """Set a short focus lock after an explicit pill click."""
    global _focus_lock_until
    _focus_lock_until = time.monotonic() + FOCUS_LOCK_DURATION


def _make_click_handler(entry_name: str):
    """Create a mouse handler for a specific pill."""
    def _handler(e):
        print(f"[recall-diag] click handler fired for '{entry_name}': event={e.event} button={e.button}")
        if e.event != "mousedown" or e.button != 0:
            return
        saved_windows, find_window_by_id = _get_saved_windows()
        info = saved_windows.get(entry_name)
        if info:
            w = find_window_by_id(info.get("id"))
            if w:
                try:
                    _set_focus_lock()
                    show_persistent_highlight(w, entry_name)
                    w.focus()
                except Exception:
                    pass
    return _handler


def _close_click_canvases():
    """Close and discard all per-pill click canvases."""
    global _click_canvases
    for cc in _click_canvases:
        try:
            cc.close()
        except Exception:
            pass
    _click_canvases = []


def _rebuild_click_canvases():
    """Create per-pill click canvases from cached pill rects."""
    _close_click_canvases()
    for name, pill_rect in _pill_hit_rects:
        cc = Canvas.from_rect(pill_rect)
        cc.blocks_mouse = True
        cc.register("mouse", _make_click_handler(name))
        cc.freeze()
        # freeze() pushes canvases below the menu bar; move() corrects it.
        cc.move(pill_rect.x, pill_rect.y)
        _click_canvases.append(cc)


# AI Added: reads the armed Herdr panel map (None = yesterday's behavior).
def _take_herdr_map():
    """Armed Herdr panel map for the pill strip, or None. Absence keeps the
    draw bit-identical to before."""
    try:
        from .recall_herdr_panels import take_active_map
        return take_active_map()
    except Exception:
        return None


# Model cache: expensive resolves happen here on a throttle, NOT in on_draw.
# _cached_win_snapshot: id->window dict from snapshot_windows_by_id().
# _cached_sessions: {"window_sessions": {...}} or None.
# _model_time: last successful refresh (monotonic). Draw reuses the model
# while fresh so Talon's multi-per-second redraw spam stays cheap.
_cached_win_snapshot: dict | None = None
_cached_sessions: dict | None = None
_model_time: float = 0.0
_MODEL_TTL_S = 0.5


def _refresh_model():
    """Refresh window snapshot + session states off the draw path."""
    global _cached_win_snapshot, _cached_sessions, _model_time
    try:
        from .recall_commands import snapshot_windows_by_id
        _cached_win_snapshot = snapshot_windows_by_id()
    except Exception:
        _cached_win_snapshot = {}
    try:
        from .recall_session_state import (
            get_session_status, get_session_by_tty, get_session_for_path,
        )
        from . import recall_state as _rs
        window_sessions = {}
        for name, info in list(_rs.saved_windows.items()):
            session = None
            stored_id = info.get('claude_session_id')
            if stored_id:
                session = get_session_status(stored_id)
            if session is None:
                tty = info.get('claude_tty')
                if tty:
                    session = get_session_by_tty(tty)
            if session is None:
                path = info.get('path')
                if path:
                    session = get_session_for_path(path)
            if session:
                window_sessions[name] = session
        _cached_sessions = {"window_sessions": window_sessions} if window_sessions else None
    except Exception:
        _cached_sessions = None
    _model_time = time.monotonic()


def _ensure_model_fresh():
    """Refresh the model if stale. Never raises into the draw callback."""
    try:
        if _cached_win_snapshot is None or (time.monotonic() - _model_time) >= _MODEL_TTL_S:
            _refresh_model()
    except Exception:
        pass


def invalidate_model():
    """Force the next draw to re-resolve (call on save/forget/focus)."""
    global _model_time
    _model_time = 0.0


def on_draw_persistent(c: SkiaCanvas):
    """Canvas draw callback — fast path only. No AX scans, no file IO.

    Expensive work (window snapshot, session JSONL) happens in _refresh_model()
    on a throttled cron interval. Talon re-fires draw many times/sec even with
    no movement; this callback reuses the cached model unless it is stale
    (> _MODEL_TTL_S) or invalidated by save/forget/focus change."""
    global _pill_hit_rects, _previous_pill_rects
    _ensure_model_fresh()
    active_id = _persistent_window.id if _persistent_window else None
    # AI Added: feed the armed Herdr map into the pill draw.
    _pill_hit_rects = draw_persistent(c, active_id, session_states=_cached_sessions,
                                   herdr_map=_take_herdr_map(),
                                   _win_cache=_cached_win_snapshot)
    if DEBUG_SHOW_CLICK_AREAS:
        c.paint.color = "00ff0059"  # green 35% opacity
        c.paint.style = c.paint.Style.FILL
        for _, pill_rect in _pill_hit_rects:
            c.draw_rect(pill_rect)
    # Rebuild click canvases after draw so _pill_hit_rects is populated.
    # Deferred slightly so the draw completes before creating new canvases.
    # Only rebuild when positions actually changed — Talon's canvas system
    # fires this callback many times per second even when nothing moved.
    if not _pill_rects_equal(_pill_hit_rects, _previous_pill_rects):
        _previous_pill_rects = _pill_hit_rects
        cron.after("16ms", _rebuild_click_canvases)


def _do_redraw():
    """Freeze the persistent canvas to trigger a redraw."""
    global _redraw_job
    _redraw_job = None
    if _persistent_canvas:
        _persistent_canvas.freeze()


def _schedule_redraw():
    """Schedule a redraw after a short delay to let the window manager settle."""
    global _redraw_job, _previous_pill_rects
    if _redraw_job:
        cron.cancel(_redraw_job)
    # Invalidate the rebuild cache so the next on_draw_persistent always
    # rebuilds click canvases — callers use _schedule_redraw() precisely
    # because pill positions may have changed.
    _previous_pill_rects = None
    invalidate_model()
    _redraw_job = cron.after("50ms", _do_redraw)


def refresh_click_canvases():
    """Called from recall_save.py on save/forget to update pill positions."""
    _schedule_redraw()


# Kill switch (captain 2026-10-29): borders render partially / off-window, so they
# default to OFF. Voice: "recall border switch" / "recall borders switch" flips it;
# the marker file survives Talon reloads (present = borders allowed).
from pathlib import Path as _Path
_BORDERS_ALLOWED_FLAG = _Path(__file__).parent / ".borders_allowed"
DISABLE_PERSISTENT_BORDERS = not _BORDERS_ALLOWED_FLAG.exists()


def show_persistent_highlight(window, name: str):
    """Update the persistent highlight to track the given window."""
    if DISABLE_PERSISTENT_BORDERS:
        hide_persistent_highlight()
        return
    global _persistent_canvas, _persistent_window, _persistent_name
    _persistent_window = window
    _persistent_name = name
    if not _persistent_canvas:
        screen = ui.main_screen()
        _persistent_canvas = Canvas.from_screen(screen)
        _persistent_canvas.register("draw", on_draw_persistent)
    # Keep _persistent_highlight_enabled in sync with canvas state so
    # _on_focus_change in recall.py actively maintains the overlay while
    # it's showing, and so hot-reload restores it from JSON.
    from . import recall_state as _rs
    _rs._persistent_highlight_enabled = True
    _rs.save_to_disk()
    _schedule_redraw()


def hide_persistent_highlight():
    """Destroy the persistent canvas and all click canvases."""
    global _persistent_canvas, _persistent_window, _persistent_name, _pill_hit_rects, _previous_pill_rects
    _close_click_canvases()
    if _persistent_canvas:
        _persistent_canvas.unregister("draw", on_draw_persistent)
        _persistent_canvas.close()
        _persistent_canvas = None
    _persistent_window = None
    _persistent_name = ""
    _pill_hit_rects = []
    _previous_pill_rects = None
    # Clear the flag + persist so _on_focus_change stops maintaining the
    # overlay and hot-reload doesn't try to restore it.
    from . import recall_state as _rs
    _rs._persistent_highlight_enabled = False
    _rs.save_to_disk()


def clear_persistent_highlight():
    """Clear the active window but keep canvas alive."""
    global _persistent_window, _persistent_name
    _persistent_window = None
    _persistent_name = ""
    _schedule_redraw()


def rebuild_persistent_canvas():
    """Rebuild the persistent canvas on a new screen."""
    global _persistent_canvas
    if not _persistent_canvas:
        return
    _close_click_canvases()
    _persistent_canvas.unregister("draw", on_draw_persistent)
    _persistent_canvas.close()
    screen = ui.main_screen()
    _persistent_canvas = Canvas.from_screen(screen)
    _persistent_canvas.register("draw", on_draw_persistent)
    _schedule_redraw()


def _hot_reload_recovery():
    """Re-create the canvas after a hot-reload resets module state.

    Restores the overlay whenever there are any saved windows, regardless of
    the _persistent_highlight_enabled flag in JSON. The flag is only written
    when the user explicitly toggles persistent mode and saves — but the
    overlay can be visually active via direct voice commands without that
    flag ever being True in JSON. If the user has saved windows, they want
    the pills back after a hot-reload.
    """
    if _persistent_canvas:
        return  # already showing, nothing to restore
    saved_windows, _ = _get_saved_windows()
    if not saved_windows:
        return  # nothing to show
    try:
        from .recall_state import find_name_for_window_id
        window = ui.active_window()
        name = find_name_for_window_id(window.id)
        show_persistent_highlight(window, name or "")
    except Exception:
        pass


# Schedule recovery after a short delay so sibling modules finish reloading.
cron.after("200ms", _hot_reload_recovery)

# Background model refresh: keeps session colors + window snapshot warm at 2s
# cadence so draws hit cache even when Talon isn't re-firing draw callbacks.
# Cheap when idle (one AX pass + one cached JSONL stat); invalidated draws
# still force-fresh via invalidate_model().
cron.interval("2s", _refresh_model)
