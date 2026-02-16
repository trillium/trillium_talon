"""
Recall Overlay - Temporary window name labels

Shows a name tag on each saved window for 5 seconds,
triggered by "recall list" / "list recalls".
Windows that can't be found are shown in red at the top of the screen.
"""

from talon import cron, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

canvas: Canvas = None
_hide_job = None

# Padding and styling constants
PAD_X = 20
PAD_Y = 12
FONT_SIZE = 48
SHOW_DURATION = "5s"
MISSING_GAP = 10  # vertical gap between stacked missing-window labels


def _get_saved_windows():
    """Import saved_windows lazily to avoid circular imports."""
    from .recall import saved_windows, find_window_by_id
    return saved_windows, find_window_by_id


def on_draw(c: SkiaCanvas):
    saved_windows, find_window_by_id = _get_saved_windows()
    screen = ui.main_screen()

    missing_y_offset = 80  # start below top bar area

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

            # Center label on window
            center_x = rect.x + rect.width / 2
            center_y = rect.y + rect.height / 2
            pill_x = center_x - pill_w / 2
            pill_y = center_y - pill_h / 2
            text_x = center_x - text_w / 2
            text_y = center_y + text_h / 2
            bg_color = "000000bb"
            text_color = "ffffffff"
        else:
            # Show missing windows at top-center of screen in red
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

        # Draw background
        c.paint.style = c.paint.Style.FILL
        c.paint.color = bg_color
        c.draw_rect(Rect(pill_x, pill_y, pill_w, pill_h))

        # Draw text
        c.paint.style = c.paint.Style.FILL
        c.paint.color = text_color
        c.draw_text(name, text_x, text_y)


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
