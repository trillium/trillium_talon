"""
Main mouse clock rendering functions.

Top-level drawing functions for the complete mouse clock visualization.
"""

from ...core import config
from .utils import setup_paint, get_screen_dimensions, calculate_clock_position
from .rings import draw_concentric_rings, draw_clock_position_dots
from .edge import draw_edge_distance_dots


def draw_clock_letters(canvas, center_x: float, center_y: float, radius: float, text_color: str):
    """
    Draw the clock position letters (A-L) around the outer ring.

    Args:
        canvas: Talon canvas object
        center_x: X coordinate of clock center
        center_y: Y coordinate of clock center
        radius: Radius at which to place letters
        text_color: Color hex string for the letter text
    """
    paint = canvas.paint
    paint.color = text_color

    for i, letter in enumerate(config.CLOCK_LETTERS.upper(), start=1):
        x, y = calculate_clock_position(i, radius, center_x, center_y)
        canvas.draw_text(letter, x, y)


def draw_mouse_clock(
    canvas,
    center_x: float,
    center_y: float,
    radius: float,
    color_list: list[str],
    active_color: str,
    text_color: str,
    style: str = "rings",
    dot_radius: float = None,
    screen_width: float = None,
    screen_height: float = None
):
    """
    Draw the mouse clock visualization with concentric circles and clock position letters.

    Args:
        canvas: Talon canvas object
        center_x: X coordinate of clock center
        center_y: Y coordinate of clock center
        radius: Outer radius of the clock
        color_list: List of color hex strings for the concentric rings
        active_color: Color hex string for active elements
        text_color: Color hex string for letter labels
        style: Drawing style - "rings", "dots", or "edge"
        dot_radius: Radius of dots when style="dots" or "edge" (defaults to DEFAULT_DOT_RADIUS)
        screen_width: Screen width (optional, auto-detected if not provided)
        screen_height: Screen height (optional, auto-detected if not provided)
    """
    if dot_radius is None:
        dot_radius = config.DEFAULT_DOT_RADIUS

    setup_paint(canvas, active_color)

    if style == "edge":
        # Auto-detect screen dimensions if not provided
        if screen_width is None or screen_height is None:
            screen_width, screen_height = get_screen_dimensions(center_x, center_y)
        draw_edge_distance_dots(canvas, center_x, center_y, screen_width, screen_height, color_list, dot_radius)
    elif style == "dots":
        draw_clock_position_dots(canvas, center_x, center_y, radius, color_list, dot_radius)
    else:  # Default to "rings"
        draw_concentric_rings(canvas, center_x, center_y, radius, color_list)

    draw_clock_letters(canvas, center_x, center_y, radius, text_color)
