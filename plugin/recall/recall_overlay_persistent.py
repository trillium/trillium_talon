"""Recall Overlay Persistent - Persistent window border + name tab for ALL saved windows.

Uses a single full-screen canvas (blocks_mouse=False) for rendering pills.
Click detection uses a fast cron poll on ctrl.mouse_buttons_down() + hit-testing
against cached pill rects — no canvas mouse handler needed, no blocks_mouse=True,
so all normal clicks pass through unimpeded.

No separate Canvas.from_rect() click canvases — those caused macOS focus-stealing.
"""

from talon import cron, ctrl, ui
from talon.canvas import Canvas
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from .recall_overlay_draw import (
    PERSISTENT_LABEL_PAD_X,
    PERSISTENT_LABEL_PAD_Y,
    PERSISTENT_LABEL_SIZE,
    PERSISTENT_TAB_GAP,
    draw_persistent,
)
from .recall_overlay_shared import _get_saved_windows, _pills_overlap

_persistent_canvas: Canvas = None
_persistent_window = None
_persistent_name: str = ""
_redraw_job = None
_click_poll_job = None

# Cached pill rects from the last draw, used for mouse hit-testing.
# List of (name, pill_rect) tuples — name is the saved_windows key.
_pill_hit_rects: list = []

# Track previous mouse button state so we detect the down-edge only.
_prev_mouse_down: bool = False


def _compute_pill_positions(measure_text_fn=None):
    """Compute pill positions. Returns [(window, name, pill_rect), ...]."""
    saved_windows, find_window_by_id = _get_saved_windows()
    if not saved_windows:
        return []
    results, placed = [], []
    for name, info in list(saved_windows.items()):
        window = find_window_by_id(info["id"])
        if window is None:
            continue
        try:
            r = window.rect
        except Exception:
            continue
        if r.width <= 0 or r.height <= 0:
            continue
        display_name = name.title()
        if measure_text_fn:
            text_w, text_h = measure_text_fn(display_name)
        else:
            text_w, text_h = len(display_name) * 8, PERSISTENT_LABEL_SIZE
        pill_w = text_w + PERSISTENT_LABEL_PAD_X * 2
        pill_h = text_h + PERSISTENT_LABEL_PAD_Y * 2
        pill_x = r.x + r.width / 4 - pill_w / 2
        pill_y = r.y - pill_h
        pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)
        screen_w = ui.main_screen().rect.width
        for _ in range(len(placed) + 1):
            collision = next((e for e in placed if _pills_overlap(pill_rect, e)), None)
            if collision is None:
                break
            nudged_x = collision.x + collision.width + PERSISTENT_TAB_GAP
            if nudged_x + pill_w <= screen_w:
                pill_x = nudged_x
                pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)
            else:
                top = min(placed, key=lambda p: p.y)
                pill_x = r.x + r.width / 4 - pill_w / 2
                pill_y = top.y - pill_h - PERSISTENT_TAB_GAP
                pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)
                break
        placed.append(pill_rect)
        results.append((window, name, pill_rect))
    return results


def _poll_click():
    """Fast poll: detect mouse-down edge, hit-test against pill rects."""
    global _prev_mouse_down
    buttons = ctrl.mouse_buttons_down()
    is_down = 0 in buttons
    if is_down and not _prev_mouse_down:
        # Mouse button just went down — hit-test
        mx, my = ctrl.mouse_pos()
        for name, pill_rect in _pill_hit_rects:
            if (pill_rect.x <= mx <= pill_rect.x + pill_rect.width and
                    pill_rect.y <= my <= pill_rect.y + pill_rect.height):
                saved_windows, find_window_by_id = _get_saved_windows()
                info = saved_windows.get(name)
                if info:
                    w = find_window_by_id(info.get("id"))
                    if w:
                        try:
                            w.focus()
                        except Exception:
                            pass
                break
    _prev_mouse_down = is_down


def on_draw_persistent(c: SkiaCanvas):
    """Canvas draw callback — delegates to draw module and caches hit rects."""
    global _pill_hit_rects
    active_id = _persistent_window.id if _persistent_window else None
    _pill_hit_rects = draw_persistent(c, active_id)


def _do_redraw():
    """Freeze the persistent canvas to trigger a redraw."""
    global _redraw_job
    _redraw_job = None
    if _persistent_canvas:
        _persistent_canvas.freeze()


def _schedule_redraw():
    """Schedule a redraw after a short delay to let the window manager settle."""
    global _redraw_job
    if _redraw_job:
        cron.cancel(_redraw_job)
    _redraw_job = cron.after("50ms", _do_redraw)


def refresh_click_canvases():
    """Legacy API — now just triggers a canvas redraw.
    Called from recall_save.py on save/forget to update pill positions."""
    _schedule_redraw()


def show_persistent_highlight(window, name: str):
    """Update the persistent highlight to track the given window."""
    global _persistent_canvas, _persistent_window, _persistent_name, _click_poll_job
    _persistent_window = window
    _persistent_name = name
    if not _persistent_canvas:
        screen = ui.main_screen()
        _persistent_canvas = Canvas.from_screen(screen)
        _persistent_canvas.register("draw", on_draw_persistent)
    if not _click_poll_job:
        _click_poll_job = cron.interval("16ms", _poll_click)
    _schedule_redraw()


def hide_persistent_highlight():
    """Destroy the persistent canvas entirely."""
    global _persistent_canvas, _persistent_window, _persistent_name
    global _pill_hit_rects, _click_poll_job
    if _click_poll_job:
        cron.cancel(_click_poll_job)
        _click_poll_job = None
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
    _persistent_canvas.unregister("draw", on_draw_persistent)
    _persistent_canvas.close()
    screen = ui.main_screen()
    _persistent_canvas = Canvas.from_screen(screen)
    _persistent_canvas.register("draw", on_draw_persistent)
    _schedule_redraw()


def _hot_reload_recovery():
    """Re-create the canvas after a hot-reload resets module state.
    Talon's app.register('ready') only fires once at startup, so when this
    module is reloaded, _persistent_canvas is None even though the feature
    is enabled in saved_windows.json.  This deferred call gives the rest of
    the recall package time to reload first."""
    from .recall_state import _persistent_highlight_enabled
    if _persistent_highlight_enabled and not _persistent_canvas:
        # Find the current focused window to seed the highlight
        try:
            from .recall_state import find_name_for_window_id
            window = ui.active_window()
            name = find_name_for_window_id(window.id)
            if name:
                show_persistent_highlight(window, name)
            else:
                # No saved window focused, but still activate the canvas
                show_persistent_highlight(window, "")
        except Exception:
            pass


# Schedule recovery after a short delay so sibling modules finish reloading.
cron.after("200ms", _hot_reload_recovery)
