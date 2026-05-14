"""Recall Overlay Persistent - Persistent window border + name tab for ALL saved windows."""

from talon import cron, skia, ui
from talon.canvas import Canvas
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from .recall_overlay_shared import _get_saved_windows, _pills_overlap

PERSISTENT_COLOR_ACTIVE = "6a6aff"
PERSISTENT_COLOR_INACTIVE = "3535aa"
PERSISTENT_ALPHA_ACTIVE = "cc"
PERSISTENT_ALPHA_INACTIVE = "cc"
PERSISTENT_STROKE = 2
PERSISTENT_LABEL_SIZE = 13
PERSISTENT_LABEL_PAD_X = 8
PERSISTENT_LABEL_PAD_Y = 4
PERSISTENT_TAB_GAP = 4
PERSISTENT_POLL_INTERVAL = "200ms"

_persistent_canvas: Canvas = None
_persistent_window = None
_persistent_name: str = ""
_click_canvases: list = []
_click_sync_job = None


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


def _rebuild_click_canvases():
    """Close all click canvases and recreate from current pill positions."""
    global _click_canvases
    for canvas, _, _ in _click_canvases:
        try:
            canvas.close()
        except Exception:
            pass
    _click_canvases = []
    for window, name, pill_rect in _compute_pill_positions():
        c = Canvas.from_rect(pill_rect)
        c.blocks_mouse = True
        def _h(e, w=window):
            if e.event == "mousedown" and e.button == 0:
                try:
                    w.focus()
                except Exception:
                    pass
        c.register("mouse", _h)
        c.freeze()
        _click_canvases.append((c, window, name))


def _sync_click_canvases():
    positions = _compute_pill_positions()
    if len(positions) != len(_click_canvases):
        _rebuild_click_canvases()
        return
    for i, (window, name, pill_rect) in enumerate(positions):
        canvas, old_window, old_name = _click_canvases[i]
        if old_window != window or old_name != name:
            _rebuild_click_canvases()
            return
        canvas.move(pill_rect.x, pill_rect.y)
        canvas.resize(pill_rect.width, pill_rect.height)
        canvas.freeze()


def _close_click_canvases():
    global _click_canvases, _click_sync_job
    if _click_sync_job:
        cron.cancel(_click_sync_job)
        _click_sync_job = None
    for canvas, _, _ in _click_canvases:
        try:
            canvas.close()
        except Exception:
            pass
    _click_canvases = []


def on_draw_persistent(c: SkiaCanvas):
    saved_windows, find_window_by_id = _get_saved_windows()
    if not saved_windows:
        return
    active_id = _persistent_window.id if _persistent_window else None
    entries, placed = [], []
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
        c.paint.textsize = PERSISTENT_LABEL_SIZE
        text_rect = c.paint.measure_text(display_name)[1]
        text_w, text_h = text_rect.width, text_rect.height
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
        entries.append((window, name, info["id"], pill_rect, text_w, text_h))
    for window, name, wid, pill_rect, text_w, text_h in entries:
        is_active = (active_id is not None and wid == active_id)
        tab_color = (PERSISTENT_COLOR_ACTIVE + PERSISTENT_ALPHA_ACTIVE if is_active
                     else PERSISTENT_COLOR_INACTIVE + PERSISTENT_ALPHA_INACTIVE)
        try:
            r = window.rect
        except Exception:
            continue
        if is_active:
            c.paint.style = c.paint.Style.STROKE
            c.paint.stroke_width = PERSISTENT_STROKE
            c.paint.color = PERSISTENT_COLOR_ACTIVE + PERSISTENT_ALPHA_ACTIVE
            c.draw_rect(Rect(r.x, r.y, r.width, r.height))
            c.paint.style = c.paint.Style.FILL
        display_name = name.title()
        pill_x, pill_y = pill_rect.x, pill_rect.y
        pill_w, pill_h = pill_rect.width, pill_rect.height
        c.paint.color = tab_color
        rad = 6
        path = skia.Path()
        path.move_to(pill_x, pill_y + rad)
        path.arc_to_with_oval(Rect(pill_x, pill_y, rad * 2, rad * 2), 180, 90, False)
        path.line_to(pill_x + pill_w - rad, pill_y)
        path.arc_to_with_oval(
            Rect(pill_x + pill_w - rad * 2, pill_y, rad * 2, rad * 2), 270, 90, False)
        path.line_to(pill_x + pill_w, pill_y + pill_h)
        path.line_to(pill_x, pill_y + pill_h)
        path.close()
        c.draw_path(path)
        c.paint.color = "ffffffff"
        c.paint.style = c.paint.Style.STROKE_AND_FILL
        c.paint.stroke_width = 0.8
        c.draw_text(display_name, pill_x + PERSISTENT_LABEL_PAD_X,
                    pill_y + PERSISTENT_LABEL_PAD_Y + text_h)
        c.paint.style = c.paint.Style.FILL
        c.paint.stroke_width = 0


def show_persistent_highlight(window, name: str):
    """Update the persistent highlight to track the given window."""
    global _persistent_canvas, _persistent_window, _persistent_name, _click_sync_job
    _persistent_window = window
    _persistent_name = name
    if not _persistent_canvas:
        screen = ui.main_screen()
        _persistent_canvas = Canvas.from_screen(screen)
        _persistent_canvas.register("draw", on_draw_persistent)
    if not _click_sync_job:
        _rebuild_click_canvases()
        _click_sync_job = cron.interval(PERSISTENT_POLL_INTERVAL, _sync_click_canvases)


def hide_persistent_highlight():
    """Destroy the persistent canvas and stop polling entirely."""
    global _persistent_canvas, _persistent_window, _persistent_name
    _close_click_canvases()
    if _persistent_canvas:
        _persistent_canvas.unregister("draw", on_draw_persistent)
        _persistent_canvas.close()
        _persistent_canvas = None
    _persistent_window = None
    _persistent_name = ""


def clear_persistent_highlight():
    """Clear the active window but keep canvas alive."""
    global _persistent_window, _persistent_name
    _persistent_window = None
    _persistent_name = ""


def rebuild_persistent_canvas():
    """Rebuild the persistent canvas on a new screen."""
    global _persistent_canvas, _click_sync_job
    _close_click_canvases()
    if not _persistent_canvas:
        return
    _persistent_canvas.unregister("draw", on_draw_persistent)
    _persistent_canvas.close()
    screen = ui.main_screen()
    _persistent_canvas = Canvas.from_screen(screen)
    _persistent_canvas.register("draw", on_draw_persistent)
    _rebuild_click_canvases()
    _click_sync_job = cron.interval(PERSISTENT_POLL_INTERVAL, _sync_click_canvases)
