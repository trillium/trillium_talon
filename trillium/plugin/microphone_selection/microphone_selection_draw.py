"""Drawing functions for the mic selection overlay."""
from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...utils.overlay_kit import DismissibleOverlay, draw_panel_frame
from ...utils.overlay_selector import overlay_labels

# Styling constants
PANEL_BG = "1a1a2eee"
PANEL_BORDER = "4a8a4a"
CORNER_RADIUS = 16
PANEL_PAD = 40
ROW_HEIGHT = 40
FONT_SIZE = 24
HEADER_SIZE = 36
CURRENT_COLOR = "44cc66ff"  # Green for active mic
INACTIVE_COLOR = "ccccccff"
HEADER_COLOR = "888888ff"
HINT_COLOR = "aaaaaa"
HINT_SIZE = 16
DOT_RADIUS = 6
MIN_PANEL_W = 450
EXCLUDED_COLOR = "666666aa"
EXCLUDED_HEADER_COLOR = "777777aa"


def _draw_mic_rows(c, mics, active, start_y, panel_x, num_w):
    """Draw active mic rows. Returns y after last row."""
    labels = overlay_labels(len(mics))
    y = start_y
    for i, mic in enumerate(mics):
        is_current = mic == active
        row_y = y + ROW_HEIGHT * 0.7
        col_x = panel_x + PANEL_PAD

        c.paint.textsize = FONT_SIZE
        c.paint.color = CURRENT_COLOR if is_current else HEADER_COLOR
        c.paint.font.embolden = is_current
        c.draw_text(f"{labels[i]}.", col_x, row_y)

        if is_current:
            c.paint.color = CURRENT_COLOR
            c.draw_circle(
                col_x + num_w + DOT_RADIUS, row_y - FONT_SIZE * 0.3, DOT_RADIUS
            )

        c.paint.textsize = FONT_SIZE
        c.paint.color = CURRENT_COLOR if is_current else INACTIVE_COLOR
        c.paint.font.embolden = is_current
        c.draw_text(mic, col_x + num_w + DOT_RADIUS * 2 + 10, row_y)
        c.paint.font.embolden = False

        y += ROW_HEIGHT
    return y


def _draw_excluded_section(c, excluded, start_y, panel_x):
    """Draw greyed-out excluded mics section. Returns y after section."""
    y = start_y + 12
    c.paint.textsize = HINT_SIZE
    c.paint.color = EXCLUDED_HEADER_COLOR
    c.draw_text("Excluded", panel_x + PANEL_PAD, y + HINT_SIZE)
    y += HINT_SIZE + 8

    for mic in excluded:
        row_y = y + ROW_HEIGHT * 0.6
        c.paint.textsize = FONT_SIZE - 4
        c.paint.color = EXCLUDED_COLOR
        c.paint.font.embolden = False
        c.draw_text(f"  {mic}", panel_x + PANEL_PAD, row_y)
        y += ROW_HEIGHT - 8
    return y


def draw_overlay(c: SkiaCanvas, overlay: DismissibleOverlay,
                 mics: list[str], excluded: list[str], active: str):
    """Main draw function for the mic selection overlay."""
    screen = ui.main_screen()
    rect = screen.rect

    if not mics and not excluded:
        return

    # Calculate panel dimensions
    c.paint.textsize = FONT_SIZE
    all_names = mics + excluded
    max_text_w = max(c.paint.measure_text(m)[1].width for m in all_names)
    num_w = 48
    panel_w = max(
        max_text_w + PANEL_PAD * 2 + num_w + DOT_RADIUS * 2 + 16,
        MIN_PANEL_W,
    )
    excluded_h = 0
    if excluded:
        excluded_h = 12 + HINT_SIZE + 8 + (ROW_HEIGHT - 8) * len(excluded)
    panel_h = (
        PANEL_PAD * 2 + HEADER_SIZE + 8
        + ROW_HEIGHT * len(mics) + excluded_h
        + 20 + HINT_SIZE
    )

    panel_x = rect.x + (rect.width - panel_w) / 2
    panel_y = rect.y + (rect.height - panel_h) / 2
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    overlay.set_panel_rect(panel_rect)

    draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_BG, PANEL_BORDER)

    # Header
    c.paint.textsize = HEADER_SIZE
    c.paint.color = HEADER_COLOR
    c.draw_text("Microphones", panel_x + PANEL_PAD, panel_y + PANEL_PAD + HEADER_SIZE)
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)

    # Active mic rows
    y = panel_y + PANEL_PAD + HEADER_SIZE + 8
    y = _draw_mic_rows(c, mics, active, y, panel_x, num_w)

    # Excluded section
    if excluded:
        y = _draw_excluded_section(c, excluded, y, panel_x)

    # Usage hint
    c.paint.textsize = HINT_SIZE
    c.paint.color = HINT_COLOR
    c.draw_text(
        '"microphone pick <number>" to switch',
        panel_x + PANEL_PAD,
        y + 20 + HINT_SIZE,
    )
