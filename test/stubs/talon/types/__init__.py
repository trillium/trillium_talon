"""Talon types stubs."""

from talon.types.point import Point2d


class Rect:
    """Mock Rect type used throughout Talon for geometry."""

    def __init__(self, x=0, y=0, width=0, height=0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    @property
    def left(self):
        return self.x

    @property
    def top(self):
        return self.y

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def center(self):
        return Point2d(self.x + self.width / 2, self.y + self.height / 2)

    def __repr__(self):
        return f"Rect(x={self.x}, y={self.y}, width={self.width}, height={self.height})"

    def __eq__(self, other):
        if not isinstance(other, Rect):
            return NotImplemented
        return (
            self.x == other.x
            and self.y == other.y
            and self.width == other.width
            and self.height == other.height
        )
