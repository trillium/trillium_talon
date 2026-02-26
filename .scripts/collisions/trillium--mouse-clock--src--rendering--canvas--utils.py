"""
Canvas utility functions for the mouse clock.

Helper functions for screen dimensions, paint setup, and ring calculations.
"""

import math
from talon.skia import Paint
from talon import ui

from ...core import config


def get_screen_dimensions(center_x: float, center_y: float) -> tuple[int, int]:
    """
    Get the screen dimensions for the screen containing the given point.

    Args:
        center_x: X coordinate of the point
        center_y: Y coordinate of the point

    Returns:
        Tuple of (width, height) for the screen containing the point
    """
    from talon.types.point import Point2d

    screens = ui.screens()
    point = Point2d(center_x, center_y)

    for screen in screens:
        if screen.rect.contains(point):
            return screen.rect.width, screen.rect.height

    # Fallback to first screen if point not found
    if screens:
        return screens[0].rect.width, screens[0].rect.height

    # Ultimate fallback
    return config.DEFAULT_SCREEN_WIDTH, config.DEFAULT_SCREEN_HEIGHT


def setup_paint(canvas, color: str, stroke_width: int = None):
    """
    Configure canvas paint settings.

    Args:
        canvas: Talon canvas object
        color: Color hex string to set
        stroke_width: Width of stroke lines (defaults to DEFAULT_STROKE_WIDTH)

    Returns:
        Configured paint object
    """
    if stroke_width is None:
        stroke_width = config.DEFAULT_STROKE_WIDTH

    paint = canvas.paint
    paint.color = color
    paint.style = Paint.Style.STROKE
    paint.stroke_width = stroke_width
    return paint


def calculate_ring_radius(ring_index: int, total_rings: int, outer_radius: float) -> float:
    """
    Calculate the radius for a specific ring in the concentric circle pattern.

    Args:
        ring_index: Index of the ring (0 = center)
        total_rings: Total number of rings
        outer_radius: Radius of the outermost ring

    Returns:
        Radius for the specified ring
    """
    if ring_index == 0:
        return 0
    return outer_radius * ring_index / (total_rings - 1)


def calculate_clock_position(letter_index: int, radius: float, center_x: float, center_y: float) -> tuple[float, float]:
    """
    Calculate the (x, y) position for a clock letter.

    Args:
        letter_index: Index of the letter (1-12, where 1 = A at 12 o'clock)
        radius: Radius at which to place the letter
        center_x: X coordinate of clock center
        center_y: Y coordinate of clock center

    Returns:
        Tuple of (x, y) coordinates
    """
    # 30 degrees per hour, starting at -90 (12 o'clock position)
    angle = math.radians(30 * letter_index - 90)
    x = center_x + radius * math.cos(angle)
    y = center_y + radius * math.sin(angle)
    return x, y
