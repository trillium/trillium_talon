"""
Recall Overlay Persistent - Persistent window border + name tab for ALL saved windows.
"""

from talon import cron, skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
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
_persistent_last_rect = None
_persistent_poll_job = None


def on_draw_persistent(c: SkiaCanvas):
    saved_windows, find_window_by_id = _get_saved_windows()
    if not saved_windows:
        return

    active_id = _persistent_window.id if _persistent_window else None

    # Pass 1 — compute pill positions with collision avoidance
    entries = []  # (window, name, pill_rect, text_w, text_h)
    placed = []

    for name, info in saved_windows.items():
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

    # Pass 2 — draw borders and tabs
    for window, name, wid, pill_rect, text_w, text_h in entries:
        is_active = (active_id is not None and wid == active_id)
        tab_color = (PERSISTENT_COLOR_ACTIVE + PERSISTENT_ALPHA_ACTIVE if is_active
                     else PERSISTENT_COLOR_INACTIVE + PERSISTENT_ALPHA_INACTIVE)

        try:
            r = window.rect
        except Exception:
            continue

        # Border — active window only
        if is_active:
            c.paint.style = c.paint.Style.STROKE
            c.paint.stroke_width = PERSISTENT_STROKE
            c.paint.color = PERSISTENT_COLOR_ACTIVE + PERSISTENT_ALPHA_ACTIVE
            c.draw_rect(Rect(r.x, r.y, r.width, r.height))
            c.paint.style = c.paint.Style.FILL

        # Tab — rounded top, flat bottom
        display_name = name.title()
        pill_x, pill_y = pill_rect.x, pill_rect.y
        pill_w, pill_h = pill_rect.width, pill_rect.height

        c.paint.color = tab_color
        rad = 6
        path = skia.Path()
        path.move_to(pill_x, pill_y + rad)
        path.arc_to_with_oval(
            Rect(pill_x, pill_y, rad * 2, rad * 2),
            180, 90, False,
        )
        path.line_to(pill_x + pill_w - rad, pill_y)
        path.arc_to_with_oval(
            Rect(pill_x + pill_w - rad * 2, pill_y, rad * 2, rad * 2),
            270, 90, False,
        )
        path.line_to(pill_x + pill_w, pill_y + pill_h)
        path.line_to(pill_x, pill_y + pill_h)
        path.close()
        c.draw_path(path)

        # Text — bold via stroke+fill thickening
        c.paint.color = "ffffffff"
        c.paint.style = c.paint.Style.STROKE_AND_FILL
        c.paint.stroke_width = 0.8
        c.draw_text(display_name, pill_x + PERSISTENT_LABEL_PAD_X, pill_y + PERSISTENT_LABEL_PAD_Y + text_h)
        c.paint.style = c.paint.Style.FILL
        c.paint.stroke_width = 0


def _all_windows_rect_tuple():
    """Return a tuple of (id, x, y, w, h) for every live saved window."""
    saved_windows, find_window_by_id = _get_saved_windows()
    result = []
    for name, info in saved_windows.items():
        w = find_window_by_id(info["id"])
        if w is not None:
            try:
                r = w.rect
                result.append((w.id, r.x, r.y, r.width, r.height))
            except Exception:
                pass
    return tuple(result)


def _persistent_check_geometry():
    """Cron interval callback: re-freeze canvas if any tracked window moved/resized."""
    global _persistent_last_rect
    if not _persistent_canvas:
        return
    current = _all_windows_rect_tuple()
    if current != _persistent_last_rect:
        _persistent_last_rect = current
        _persistent_canvas.freeze()


def show_persistent_highlight(window, name: str):
    """Update the persistent highlight to track the given window."""
    global _persistent_canvas, _persistent_window, _persistent_name
    global _persistent_last_rect, _persistent_poll_job

    _persistent_window = window
    _persistent_name = name
    _persistent_last_rect = _all_windows_rect_tuple()

    if not _persistent_canvas:
        screen = ui.main_screen()
        _persistent_canvas = Canvas.from_screen(screen)
        _persistent_canvas.register("draw", on_draw_persistent)

    _persistent_canvas.freeze()

    if not _persistent_poll_job:
        _persistent_poll_job = cron.interval(PERSISTENT_POLL_INTERVAL, _persistent_check_geometry)


def hide_persistent_highlight():
    """Destroy the persistent canvas and stop polling entirely (feature toggled off)."""
    global _persistent_canvas, _persistent_window, _persistent_name
    global _persistent_last_rect, _persistent_poll_job

    if _persistent_poll_job:
        cron.cancel(_persistent_poll_job)
        _persistent_poll_job = None
    if _persistent_canvas:
        _persistent_canvas.unregister("draw", on_draw_persistent)
        _persistent_canvas.close()
        _persistent_canvas = None
    _persistent_window = None
    _persistent_name = ""
    _persistent_last_rect = None


def clear_persistent_highlight():
    """Clear the active window but keep canvas alive — other tabs still draw dimly."""
    global _persistent_window, _persistent_name, _persistent_last_rect
    _persistent_window = None
    _persistent_name = ""
    _persistent_last_rect = _all_windows_rect_tuple()
    if _persistent_canvas:
        _persistent_canvas.freeze()


def rebuild_persistent_canvas():
    """Rebuild the persistent canvas on a new screen (e.g. monitor change)."""
    global _persistent_canvas
    if not _persistent_canvas:
        return
    _persistent_canvas.unregister("draw", on_draw_persistent)
    _persistent_canvas.close()
    screen = ui.main_screen()
    _persistent_canvas = Canvas.from_screen(screen)
    _persistent_canvas.register("draw", on_draw_persistent)
    _persistent_canvas.freeze()
