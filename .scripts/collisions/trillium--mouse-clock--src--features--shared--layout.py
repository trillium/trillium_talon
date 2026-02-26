"""
Shared layout calculation functions.

Row and column position distribution for overlay grids.
"""

from typing import List


def calculate_row_positions(
    screen_top: float,
    screen_bottom: float,
    num_rows: int
) -> List[float]:
    """
    Calculate Y positions for each row, evenly distributed with margin.

    Args:
        screen_top: Top of screen
        screen_bottom: Bottom of screen
        num_rows: Number of rows to position

    Returns:
        List of Y coordinates for each row
    """
    if num_rows <= 1:
        return [(screen_top + screen_bottom) / 2]

    spacing = (screen_bottom - screen_top) / (num_rows + 1)
    return [screen_top + spacing * (i + 1) for i in range(num_rows)]


def calculate_column_positions(
    screen_left: float,
    screen_right: float,
    num_cols: int,
    offset_x: float = 0.0,
    edge_to_edge: bool = False
) -> List[float]:
    """
    Calculate X positions for each column.

    Args:
        screen_left: Left edge of screen
        screen_right: Right edge of screen
        num_cols: Number of columns to position
        offset_x: Horizontal offset to apply (default 0)
        edge_to_edge: If True, first column at left edge, last at right edge.
                      If False, columns have equal margin at edges.

    Returns:
        List of X coordinates for each column
    """
    if num_cols <= 1:
        return [(screen_left + screen_right) / 2]

    if edge_to_edge:
        # First column at left edge, last at right edge
        spacing = (screen_right - screen_left) / (num_cols - 1)
        return [screen_left + spacing * i + offset_x for i in range(num_cols)]
    else:
        # Equal margin at edges
        spacing = (screen_right - screen_left) / (num_cols + 1)
        return [screen_left + spacing * (i + 1) + offset_x for i in range(num_cols)]
