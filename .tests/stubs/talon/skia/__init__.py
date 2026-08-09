"""Talon Skia bindings stubs.

Talon uses Skia (Google's 2D graphics library) for all canvas rendering.
These stubs mock the Paint, Rect, Path, and related types.
"""


class _PaintStyle:
    FILL = "fill"
    STROKE = "stroke"
    STROKE_AND_FILL = "stroke_and_fill"


class Paint:
    """Mock Skia Paint — controls how shapes are drawn.

    In real Talon:
        paint = Paint()
        paint.color = "ff0000ff"  # RRGGBBAA hex
        paint.style = Paint.Style.FILL
        paint.stroke_width = 2
    """

    Style = _PaintStyle

    def __init__(self):
        self.color = "ffffffff"
        self.style = self.Style.FILL
        self.stroke_width = 1
        self.textsize = 16
        self.font = None
        self.antialias = True

    def measure_text(self, text):
        """Approximate text width. Real Skia measures using font metrics."""
        return [len(text) * self.textsize * 0.6]

    def snapshot(self):
        """Test helper: return paint state as dict for assertions."""
        return {
            "color": self.color,
            "style": self.style,
            "stroke_width": self.stroke_width,
            "textsize": self.textsize,
        }


class Rect:
    """Mock Skia Rect."""

    def __init__(self, x=0, y=0, width=0, height=0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    @classmethod
    def from_ltrb(cls, left, top, right, bottom):
        return cls(left, top, right - left, bottom - top)

    def __repr__(self):
        return f"Rect(x={self.x}, y={self.y}, width={self.width}, height={self.height})"


class Path:
    """Mock Skia Path for complex shapes."""

    def __init__(self):
        self._commands = []

    def move_to(self, x, y):
        self._commands.append(("move", x, y))
        return self

    def line_to(self, x, y):
        self._commands.append(("line", x, y))
        return self

    def arc_to(self, rx, ry, x_axis_rotation, large_arc, sweep, x, y):
        self._commands.append(("arc", rx, ry, x, y))
        return self

    def close(self):
        self._commands.append(("close",))
        return self
