"""Talon Skia Canvas stubs.

The skia Canvas is what draw callbacks receive. It provides the actual
drawing primitives (draw_circle, draw_rect, draw_text, etc.).
"""

from talon.skia import Paint


class Canvas:
    """Mock Skia Canvas — records all draw operations for test assertions.

    Usage in tests:
        canvas = Canvas()
        my_draw_function(canvas)
        assert len(canvas.circles()) == 3
        assert canvas.texts()[0][3] == "Hello"
    """

    def __init__(self, width=1920, height=1080):
        self.width = width
        self.height = height
        self.drawings = []
        self._save_count = 0
        self._translate_x = 0
        self._translate_y = 0
        self._paint = Paint()

    @property
    def paint(self):
        return self._paint

    @paint.setter
    def paint(self, value):
        self._paint = value

    def save(self):
        self._save_count += 1

    def restore(self):
        self._save_count = max(0, self._save_count - 1)

    def translate(self, dx, dy):
        self._translate_x += dx
        self._translate_y += dy

    def scale(self, sx, sy=None):
        pass

    def rotate(self, degrees):
        pass

    def clip_rect(self, rect):
        pass

    def draw_circle(self, cx, cy, radius, paint=None):
        p = paint or self._paint
        self.drawings.append(("circle", cx, cy, radius, p.snapshot()))

    def draw_line(self, x1, y1, x2, y2, paint=None):
        p = paint or self._paint
        self.drawings.append(("line", x1, y1, x2, y2, p.snapshot()))

    def draw_rect(self, rect, paint=None):
        p = paint or self._paint
        self.drawings.append(("rect", rect, p.snapshot()))

    def draw_rrect(self, rrect, paint=None):
        p = paint or self._paint
        self.drawings.append(("rrect", rrect, p.snapshot()))

    def draw_text(self, text, x, y, paint=None):
        p = paint or self._paint
        self.drawings.append(("text", x, y, text, p.snapshot()))

    def draw_path(self, path, paint=None):
        p = paint or self._paint
        self.drawings.append(("path", path, p.snapshot()))

    def draw_image(self, image, x, y, paint=None):
        p = paint or self._paint
        self.drawings.append(("image", x, y, image, p.snapshot()))

    def draw_image_rect(self, image, src, dst, paint=None):
        p = paint or self._paint
        self.drawings.append(("image_rect", image, src, dst, p.snapshot()))

    # Test helper methods

    def circles(self):
        """Return all circle draw operations."""
        return [d for d in self.drawings if d[0] == "circle"]

    def lines(self):
        """Return all line draw operations."""
        return [d for d in self.drawings if d[0] == "line"]

    def texts(self):
        """Return all text draw operations."""
        return [d for d in self.drawings if d[0] == "text"]

    def rects(self):
        """Return all rect draw operations."""
        return [d for d in self.drawings if d[0] == "rect"]

    def paths(self):
        """Return all path draw operations."""
        return [d for d in self.drawings if d[0] == "path"]

    def clear(self):
        """Clear all recorded drawings."""
        self.drawings.clear()
