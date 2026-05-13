"""
Recall Overlay Labels - Name-label pill overlay triggered by "recall list".
"""

from talon import cron, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect
from .recall_overlay_shared import (
    PILL_CORNER_RADIUS,
    _draw_rounded_rect,
    _get_saved_windows,
    _pills_overlap,
    set_overlay_active,
)

PAD_X = 20
PAD_Y = 12
FONT_SIZE = 48
SHOW_DURATION = "7s"
MISSING_GAP = 10  # vertical gap between stacked missing-window labels

canvas: Canvas = None
_hide_job = None


def on_draw(c: SkiaCanvas):
    saved_windows, find_window_by_id = _get_saved_windows()
    screen = ui.main_screen()

    try:
        active_id = ui.active_window().id
    except Exception:
        active_id = None

    missing_y_offset = 80  # start below top bar area

    # First pass: compute pill positions
    pills = []  # [(name, pill_rect, text_x, text_y, bg_color, text_color)]
    for name, info in saved_windows.items():
        window = find_window_by_id(info["id"])

        c.paint.textsize = FONT_SIZE
        text_rect = c.paint.measure_text(name)[1]
        text_w = text_rect.width
        text_h = text_rect.height

        pill_w = text_w + PAD_X * 2
        pill_h = text_h + PAD_Y * 2

        if window is not None:
            rect = window.rect
            if rect.width <= 0 or rect.height <= 0:
                continue

            is_active = (info["id"] == active_id)

            # Center label on window
            center_x = rect.x + rect.width / 2
            center_y = rect.y + rect.height / 2
            pill_x = center_x - pill_w / 2
            pill_y = center_y - pill_h / 2
            text_x = center_x - text_w / 2
            text_y = center_y + text_h / 2
            bg_color = "6a6affcc" if is_active else "000000bb"
            text_color = "ffffffff"
        else:
            is_active = False
            display = f"{name} (not found)"
            c.paint.textsize = FONT_SIZE
            text_rect = c.paint.measure_text(display)[1]
            text_w = text_rect.width
            text_h = text_rect.height
            pill_w = text_w + PAD_X * 2
            pill_h = text_h + PAD_Y * 2

            center_x = screen.rect.x + screen.rect.width / 2
            pill_x = center_x - pill_w / 2
            pill_y = missing_y_offset
            text_x = center_x - text_w / 2
            text_y = missing_y_offset + PAD_Y + text_h
            bg_color = "aa0000cc"
            text_color = "ffffffff"
            name = display
            missing_y_offset += pill_h + MISSING_GAP

        pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)

        # Nudge if overlapping any existing pill
        for _, existing_rect, _, _, _, _ in pills:
            if _pills_overlap(pill_rect, existing_rect):
                # Shift below the existing pill
                pill_y = existing_rect.y + existing_rect.height + MISSING_GAP
                text_y = pill_y + PAD_Y + text_h
                pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)

        pills.append((name, pill_rect, text_x, text_y, bg_color, text_color))

    # Second pass: draw
    for name, pill_rect, text_x, text_y, bg_color, text_color in pills:
        c.paint.style = c.paint.Style.FILL
        c.paint.color = bg_color
        _draw_rounded_rect(c, pill_rect, PILL_CORNER_RADIUS)

        c.paint.style = c.paint.Style.FILL
        c.paint.color = text_color
        c.paint.textsize = FONT_SIZE
        c.draw_text(name, pill_rect.x + PAD_X, text_y)


def show_overlay():
    """Show labels on all saved windows for 5 seconds."""
    global canvas, _hide_job

    # Cancel any pending hide
    if _hide_job:
        cron.cancel(_hide_job)
        _hide_job = None

    # Tear down existing canvas before creating new one
    if canvas:
        canvas.unregister("draw", on_draw)
        canvas.close()
        canvas = None

    saved_windows, _ = _get_saved_windows()
    if not saved_windows:
        return

    screen: Screen = ui.main_screen()
    canvas = Canvas.from_screen(screen)
    canvas.register("draw", on_draw)
    canvas.freeze()

    # Auto-hide after duration
    _hide_job = cron.after(SHOW_DURATION, hide_overlay)
    set_overlay_active("labels", True)


def hide_overlay():
    """Hide and destroy the overlay canvas."""
    global canvas, _hide_job
    if _hide_job:
        cron.cancel(_hide_job)
        _hide_job = None
    if canvas:
        canvas.unregister("draw", on_draw)
        canvas.close()
        canvas = None
    set_overlay_active("labels", False)
