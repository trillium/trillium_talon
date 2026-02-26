"""
Clock letters layout calculations.

Functions for calculating letter positions in the grid.
Rows = letters, Columns = colors.
"""

# Import from shared - clock_letters uses edge-to-edge column layout
from ..shared.layout import calculate_row_positions
from ..shared.layout import calculate_column_positions as _calculate_column_positions

__all__ = ['calculate_row_positions', 'calculate_column_positions']


def calculate_column_positions(
    screen_left: float,
    screen_right: float,
    num_cols: int
):
    """
    Calculate X positions for each color column.

    First column (red) at left edge, last column (teal) at right edge.

    Args:
        screen_left: Left edge of screen
        screen_right: Right edge of screen
        num_cols: Number of columns (colors)

    Returns:
        List of X coordinates for each column
    """
    return _calculate_column_positions(
        screen_left, screen_right, num_cols,
        edge_to_edge=True
    )
