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
    print(f"[recall-diag] _rebuild_click_canvases: {len(_pill_hit_rects)} pills")
    for name, pill_rect in _pill_hit_rects:
        cc = Canvas.from_rect(pill_rect)
        cc.blocks_mouse = True
        cc.register("mouse", _make_click_handler(name))
        cc.freeze()
        # freeze() pushes canvases below the menu bar; move() corrects it.
        cc.move(pill_rect.x, pill_rect.y)
        _click_canvases.append(cc)


def on_draw_persistent(c: SkiaCanvas):
    """Canvas draw callback — delegates to draw module and caches hit rects."""
    global _pill_hit_rects
    active_id = _persistent_window.id if _persistent_window else None
    _pill_hit_rects = draw_persistent(c, active_id)
    if DEBUG_SHOW_CLICK_AREAS:
        c.paint.color = "00ff0059"  # green 35% opacity
        c.paint.style = c.paint.Style.FILL
        for _, pill_rect in _pill_hit_rects:
            c.draw_rect(pill_rect)


def _do_redraw():
    """Freeze the persistent canvas to trigger a redraw, then rebuild clicks."""
    global _redraw_job
    _redraw_job = None
    if _persistent_canvas:
        _persistent_canvas.freeze()
        # Defer click canvas rebuild so draw completes first and _pill_hit_rects
        # is populated with fresh positions.
        cron.after("30ms", _rebuild_click_canvases)


def _schedule_redraw():
    """Schedule a redraw after a short delay to let the window manager settle."""
    global _redraw_job
    if _redraw_job:
        cron.cancel(_redraw_job)
    _redraw_job = cron.after("50ms", _do_redraw)


def refresh_click_canvases():
    """Called from recall_save.py on save/forget to update pill positions."""
    _schedule_redraw()


def show_persistent_highlight(window, name: str):
    """Update the persistent highlight to track the given window."""
    global _persistent_canvas, _persistent_window, _persistent_name
    _persistent_window = window
    _persistent_name = name
    if not _persistent_canvas:
        screen = ui.main_screen()
        _persistent_canvas = Canvas.from_screen(screen)
        _persistent_canvas.register("draw", on_draw_persistent)
    _schedule_redraw()


def hide_persistent_highlight():
    """Destroy the persistent canvas and all click canvases."""
    global _persistent_canvas, _persistent_window, _persistent_name, _pill_hit_rects
    _close_click_canvases()
    if _persistent_canvas:
        _persistent_canvas.unregister("draw", on_draw_persistent)
        _persistent_canvas.close()
        _persistent_canvas = None
    _persistent_window = None
    _persistent_name = ""
    _pill_hit_rects = []


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
    """Re-create the canvas after a hot-reload resets module state."""
    from .recall_state import _persistent_highlight_enabled
    if _persistent_highlight_enabled and not _persistent_canvas:
        try:
            from .recall_state import find_name_for_window_id
            window = ui.active_window()
            name = find_name_for_window_id(window.id)
            if name:
                show_persistent_highlight(window, name)
            else:
                show_persistent_highlight(window, "")
        except Exception:
            pass


# Schedule recovery after a short delay so sibling modules finish reloading.
cron.after("200ms", _hot_reload_recovery)
