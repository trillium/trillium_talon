"""Command Surfacer Draw -- rendering logic for the command surfacer panel.

Draws a small panel anchored below the right edge of the mode indicator bar,
showing one voice command with its description and a counter.
Uses overlay_kit shared primitives for panel frame.
"""

from talon import settings, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from trillium.utils.overlay_kit import draw_panel_frame

# ---------------------------------------------------------------------------
# Visual constants (matching prose_overlay palette)
# ---------------------------------------------------------------------------
BG_COLOR = "1a1a2add"
BORDER_COLOR = "4488aacc"
PHRASE_COLOR = "eeeeffee"
DESC_COLOR = "888899cc"
COUNTER_COLOR = "666677cc"
CORNER_RADIUS = 8
PANEL_PAD_X = 10
PANEL_PAD_Y = 8
PHRASE_FONT_SIZE = 14
DESC_FONT_SIZE = 11
COUNTER_FONT_SIZE = 9
GAP_BELOW_BAR = 4
PANEL_WIDTH = 280


def draw_panel(
    c: SkiaCanvas,
    phrase: str,
    description: str,
    index: int,
    total: int,
) -> Rect:
    """Draw the command surfacer panel below the mode indicator bar.

    Returns the panel Rect for click-outside detection.
    """
    screen = ui.main_screen()
    sr = screen.rect

    # Position relative to mode indicator bar
    bar_right_x = settings.get("user.mode_indicator_bar_right_x")
    bar_height = settings.get("user.mode_indicator_bar_height")

    panel_right = sr.width * bar_right_x
    panel_left = panel_right - PANEL_WIDTH
    panel_top = bar_height + GAP_BELOW_BAR

    # Measure text to compute panel height
    c.paint.textsize = PHRASE_FONT_SIZE
    phrase_text_h = PHRASE_FONT_SIZE
    c.paint.textsize = DESC_FONT_SIZE
    desc_text_h = DESC_FONT_SIZE
    c.paint.textsize = COUNTER_FONT_SIZE
    counter_text_h = COUNTER_FONT_SIZE

    line_gap = 4
    counter_gap = 6
    panel_h = (
        PANEL_PAD_Y
        + phrase_text_h
        + line_gap
        + desc_text_h
        + counter_gap
        + counter_text_h
        + PANEL_PAD_Y
    )

    panel_rect = Rect(panel_left, panel_top, PANEL_WIDTH, panel_h)

    # Panel background + border
    draw_panel_frame(c, panel_rect, CORNER_RADIUS, BG_COLOR, BORDER_COLOR)

    # Phrase line (bright)
    c.paint.textsize = PHRASE_FONT_SIZE
    c.paint.color = PHRASE_COLOR
    phrase_y = panel_top + PANEL_PAD_Y + phrase_text_h
    c.draw_text(phrase, panel_left + PANEL_PAD_X, phrase_y)

    # Description line (dim)
    c.paint.textsize = DESC_FONT_SIZE
    c.paint.color = DESC_COLOR
    desc_y = phrase_y + line_gap + desc_text_h
    c.draw_text(description, panel_left + PANEL_PAD_X, desc_y)

    # Counter "N of M" in bottom-right
    counter_str = f"{index + 1} of {total}"
    c.paint.textsize = COUNTER_FONT_SIZE
    c.paint.color = COUNTER_COLOR
    counter_w = c.paint.measure_text(counter_str)[1].width
    counter_x = panel_left + PANEL_WIDTH - PANEL_PAD_X - counter_w
    counter_y = desc_y + counter_gap + counter_text_h
    c.draw_text(counter_str, counter_x, counter_y)

    return panel_rect
