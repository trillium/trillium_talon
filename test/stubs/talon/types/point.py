"""Talon Point2d stub."""


class Point2d:
    """2D point used for screen coordinates, mouse positions, etc."""

    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

    def __repr__(self):
        return f"Point2d(x={self.x}, y={self.y})"

    def __eq__(self, other):
        if not isinstance(other, Point2d):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    def __add__(self, other):
        return Point2d(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Point2d(self.x - other.x, self.y - other.y)
