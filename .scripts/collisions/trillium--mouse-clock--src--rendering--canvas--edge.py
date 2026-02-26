"""
Edge distance visualization for the mouse clock.

Functions for drawing dots based on distance from screen edges.
"""

import math
from talon.skia import Paint

from ...core import config


def calculate_edge_distance(
    ring_index: int,
    total_rings: int,
    screen_dimension: float,
    current_position: float
) -> float:
    """
    Calculate distance from edge for a specific ring.

    Args:
        ring_index: Index of the ring (0 = at current position)
        total_rings: Total number of rings
        screen_dimension: Total screen dimension (width or height)
        current_position: Current mouse position in that dimension

    Returns:
        Distance from current position towards the edge
    """
    if ring_index == 0:
        return 0

    # Distance available to the edge
    distance_to_edge = screen_dimension - current_position

    # Divide the distance into equal segments
    return (distance_to_edge / total_rings) * ring_index


def draw_edge_distance_dots(
    canvas,
    center_x: float,
    center_y: float,
    screen_width: float,
    screen_height: float,
    color_list: list[str],
    dot_radius: float = None
):
    """
    Draw colored dots at clock positions, with colors representing distance from screen edge.

    Args:
        canvas: Talon canvas object
        center_x: X coordinate of clock center (current mouse position)
        center_y: Y coordinate of clock center (current mouse position)
        screen_width: Width of the screen
        screen_height: Height of the screen
        color_list: List of color hex strings for each distance ring
        dot_radius: Size of each dot (defaults to DEFAULT_DOT_RADIUS)
    """
    if dot_radius is None:
        dot_radius = config.DEFAULT_DOT_RADIUS

    paint = canvas.paint
    paint.style = Paint.Style.FILL

    num_rings = len(color_list)

    # For each color ring
    for ring_index in range(num_rings):
        paint.color = color_list[ring_index]

        # Draw a dot at each of the 12 clock positions
        for position in range(1, 13):  # 1-12 for clock positions
            angle = math.radians(30 * position - 90)

            # Calculate which edge we're heading towards
            dx = math.cos(angle)
            dy = math.sin(angle)

            # Determine the limiting dimension based on direction
            if abs(dx) > abs(dy):
                # Primarily horizontal movement
                if dx > 0:  # Moving right
                    edge_distance = screen_width - center_x
                else:  # Moving left
                    edge_distance = center_x
            else:
                # Primarily vertical movement
                if dy > 0:  # Moving down
                    edge_distance = screen_height - center_y
                else:  # Moving up
                    edge_distance = center_y

            # Calculate distance for this ring
            distance = (edge_distance / num_rings) * ring_index

            # Calculate final position
            x = center_x + distance * dx
            y = center_y + distance * dy

            canvas.draw_circle(x, y, dot_radius)
