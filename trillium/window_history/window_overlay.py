"""Window History Overlay — visual indicator in the menu bar area.

Shows the window navigation order as a horizontal strip across the top
of the screen while browsing. The current position is highlighted.
Non-interactive: does not block mouse events.

Called by window_history.py — no back-imports to avoid circular deps.
State is passed in via show()/refresh() calls.
"""

from talon import skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

_canvas: Canvas = None

# Snapshot of state for rendering (set by show/refresh)
_items: list[tuple[str, bool]] = []  # (label, is_active)

# Visual constants
BAR_HEIGHT = 26
BAR_Y = 0
PILL_RADIUS = 6
FONT_SIZE = 11
MAX_LABEL_CHARS = 16
PILL_H_PAD = 8
PILL_V_PAD = 3
ITEM_GAP = 4
BAR_H_PAD = 10

# Colors
BG_COLOR = "1a1a1acc"
ACTIVE_BG = "4488ddee"
ACTIVE_TEXT = "ffffffff"
INACTIVE_TEXT = "999999ff"
OVERFLOW_TEXT = "666666ff"


def _build_items(window_history, depth, total_navs, find_window_by_id):
    """Build display items from current window history state."""
    if not window_history:
        return []

    # Deduplicate window IDs preserving order
    seen_ids = []
    seen_set = set()
    for wid in window_history:
        if wid not in seen_set:
            seen_set.add(wid)
            seen_ids.append(wid)

    # Which window ID is currently focused
    active_index = depth + total_navs if depth > 0 else total_navs
    if 0 <= active_index < len(window_history):
        active_wid = window_history[active_index]
    elif window_history:
        active_wid = window_history[0]
    else:
        active_wid = None

    items = []
    for wid in seen_ids:
        win = find_window_by_id(wid)
        if win is None:
            continue
        label = win.app.name or "?"
        if len(label) > MAX_LABEL_CHARS:
            label = label[: MAX_LABEL_CHARS - 1] + "\u2026"
        items.append((label, wid == active_wid))

    return items


def _on_draw(c: SkiaCanvas):
    screen: Screen = ui.main_screen()
    rect = screen.rect
    items = _items
    if not items:
        return

    c.paint.textsize = FONT_SIZE
    c.paint.style = c.paint.Style.FILL

    # Measure all items
    measurements = []
    for label, _ in items:
        text_w = c.paint.measure_text(label)[1].width
        pill_w = text_w + PILL_H_PAD * 2
        measurements.append((label, pill_w, text_w))

    total_w = sum(pw for _, pw, _ in measurements) + ITEM_GAP * max(len(measurements) - 1, 0)
    max_bar_w = rect.width * 0.6

    # Truncate if too wide, show overflow count
    display = list(zip(items, measurements))
    overflow = 0
    while total_w > max_bar_w and len(display) > 2:
        _, (_, pw, _) = display.pop()
        overflow += 1
        overflow_label = f"+{overflow}"
        overflow_tw = c.paint.measure_text(overflow_label)[1].width
        overflow_pw = overflow_tw + PILL_H_PAD * 2
        total_w = (
            sum(m[1] for _, m in display)
            + ITEM_GAP * len(display)
            + overflow_pw
        )

    bar_w = total_w + BAR_H_PAD * 2
    bar_x = rect.left + (rect.width - bar_w) / 2
    bar_y = rect.top + BAR_Y

    # Bar background
    c.paint.color = BG_COLOR
    bar_rect = Rect(bar_x, bar_y, bar_w, BAR_HEIGHT)
    path = skia.Path()
    path.add_rounded_rect(bar_rect, PILL_RADIUS, PILL_RADIUS, skia.Path.Direction.CW)
    c.draw_path(path)

    # Draw each item
    x = bar_x + BAR_H_PAD
    pill_y = bar_y + (BAR_HEIGHT - FONT_SIZE - PILL_V_PAD * 2) / 2
    text_y = pill_y + PILL_V_PAD + FONT_SIZE

    for (label, is_active), (_, pill_w, text_w) in display:
        if is_active:
            c.paint.color = ACTIVE_BG
            pill_rect = Rect(x, pill_y, pill_w, FONT_SIZE + PILL_V_PAD * 2)
            pill_path = skia.Path()
            pill_path.add_rounded_rect(
                pill_rect, PILL_RADIUS, PILL_RADIUS, skia.Path.Direction.CW
            )
            c.draw_path(pill_path)
            c.paint.color = ACTIVE_TEXT
        else:
            c.paint.color = INACTIVE_TEXT

        c.paint.textsize = FONT_SIZE
        c.draw_text(label, x + PILL_H_PAD, text_y)
        x += pill_w + ITEM_GAP

    # Overflow indicator
    if overflow > 0:
        c.paint.color = OVERFLOW_TEXT
        c.paint.textsize = FONT_SIZE
        c.draw_text(f"+{overflow}", x + PILL_H_PAD, text_y)


def _update_state(window_history, depth, total_navs, find_window_by_id):
    """Snapshot the current items for rendering."""
    global _items
    _items = _build_items(window_history, depth, total_navs, find_window_by_id)


def show(window_history, depth, total_navs, find_window_by_id):
    """Show the window history overlay."""
    global _canvas
    _update_state(window_history, depth, total_navs, find_window_by_id)
    if _canvas:
        _canvas.freeze()
        return
    screen: Screen = ui.main_screen()
    _canvas = Canvas.from_screen(screen)
    _canvas.blocks_mouse = False
    _canvas.register("draw", _on_draw)
    _canvas.freeze()


def hide():
    """Hide the window history overlay."""
    global _canvas, _items
    _items = []
    if _canvas:
        _canvas.unregister("draw", _on_draw)
        _canvas.close()
        _canvas = None


def refresh(window_history, depth, total_navs, find_window_by_id):
    """Redraw the overlay with current state."""
    _update_state(window_history, depth, total_navs, find_window_by_id)
    if _canvas:
        _canvas.freeze()
