"""Recall Overlay Draw - Rendering logic for persistent window pills.

Extracted from recall_overlay_persistent.py to keep files under 250 lines.
Contains the on-draw callback and pill layout/rendering helpers.
"""

from talon import skia, ui
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


def _resolve_collisions(pill_rect, pill_w, pill_h, pill_y, placed, screen_w, base_x):
    """Nudge pill_rect to avoid collisions with already-placed pills.

    Returns the final Rect after resolving overlaps.
    """
    pill_x = pill_rect.x
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
            pill_x = base_x
            pill_y = top.y - pill_h - PERSISTENT_TAB_GAP
            pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)
            break
    return pill_rect


def _draw_pill(c, pill_rect, tab_color, display_name, text_h):
    """Draw a single pill: rounded-top rectangle background + label text."""
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


def draw_persistent(c: SkiaCanvas, active_window_id):
    """Main draw routine for persistent pills. Returns pill hit rects.

    Args:
        c: The Skia canvas to draw on.
        active_window_id: The id of the currently highlighted window, or None.

    Returns:
        List of (name, pill_rect) tuples for mouse hit-testing.
    """
    saved_windows, find_window_by_id = _get_saved_windows()
    if not saved_windows:
        return []

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
        base_x = r.x + r.width / 4 - pill_w / 2
        pill_y = r.y - pill_h
        pill_rect = Rect(base_x, pill_y, pill_w, pill_h)
        screen_w = ui.main_screen().rect.width

        pill_rect = _resolve_collisions(
            pill_rect, pill_w, pill_h, pill_y, placed, screen_w, base_x)
        placed.append(pill_rect)
        entries.append((window, name, info["id"], pill_rect, text_w, text_h))

    hit_rects = [(name, pill_rect) for _, name, _, pill_rect, _, _ in entries]

    for window, name, wid, pill_rect, text_w, text_h in entries:
        is_active = (active_window_id is not None and wid == active_window_id)
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

        _draw_pill(c, pill_rect, tab_color, name.title(), text_h)

    return hit_rects
