"""Talon Canvas API stubs.

The Canvas is Talon's overlay drawing surface. It uses Skia under the hood.
Canvas callbacks receive a skia Canvas object for drawing.
"""


class MouseEvent:
    """Mouse event passed to canvas event handlers."""

    def __init__(self, x=0, y=0, button=0):
        self.x = x
        self.y = y
        self.button = button
        self.gpos = type("gpos", (), {"x": x, "y": y})()


class Canvas:
    """Mock Talon Canvas — the overlay drawing surface.

    Usage in Talon code:
        c = Canvas.from_screen(screen)
        c.register("draw", on_draw)
        c.register("mouse", on_mouse)
        c.freeze()  # or c.show()

    The draw callback receives a skia.Canvas object.
    """

    def __init__(self, x=0, y=0, width=1920, height=1080):
        self.rect = type("rect", (), {
            "x": x, "y": y, "width": width, "height": height,
        })()
        self._callbacks = {}
        self._visible = False
        self._frozen = False
        self.cursor_visible = True
        self.focused = False
        self.blocks_mouse = False

    @classmethod
    def from_screen(cls, screen):
        """Create canvas covering a screen."""
        return cls(screen.x, screen.y, screen.width, screen.height)

    @classmethod
    def from_rect(cls, rect):
        """Create canvas from a Rect."""
        return cls(rect.x, rect.y, rect.width, rect.height)

    def register(self, event, callback):
        """Register event callback (draw, mouse, key, focus)."""
        self._callbacks.setdefault(event, []).append(callback)

    def unregister(self, event, callback):
        """Unregister event callback."""
        if event in self._callbacks:
            self._callbacks[event] = [
                cb for cb in self._callbacks[event] if cb != callback
            ]

    def show(self):
        """Show the canvas (non-frozen, redraws on events)."""
        self._visible = True
        self._frozen = False

    def hide(self):
        """Hide the canvas."""
        self._visible = False

    def freeze(self):
        """Freeze the canvas (draw once, then static)."""
        self._visible = True
        self._frozen = True

    def close(self):
        """Close and destroy the canvas."""
        self._visible = False
        self._callbacks.clear()

    def move(self, x, y):
        """Move the canvas to new position."""
        self.rect.x = x
        self.rect.y = y

    def resize(self, width, height):
        """Resize the canvas."""
        self.rect.width = width
        self.rect.height = height

    # Test helpers

    def trigger_draw(self, skia_canvas):
        """Test helper: trigger draw callbacks with a mock skia canvas."""
        for cb in self._callbacks.get("draw", []):
            cb(skia_canvas)

    def trigger_mouse(self, event):
        """Test helper: trigger mouse callbacks."""
        for cb in self._callbacks.get("mouse", []):
            cb(event)
