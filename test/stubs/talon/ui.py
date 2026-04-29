"""Talon UI stubs — screens, windows, rectangles.

In real Talon, `talon.ui` provides:
- Screen enumeration
- Window management
- Rect/Point geometry types
- Event registration (win_open, win_close, win_focus, etc.)
"""

from talon.types.point import Point2d


class Rect:
    """UI rectangle (used for window/screen geometry)."""

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


class UIErr(Exception):
    """UI operation error."""

    pass


class Window:
    """Mock window object."""

    def __init__(self, title="", app=None, id=0):
        self.title = title
        self.app = app
        self.id = id
        self.rect = Rect(0, 0, 800, 600)
        self.hidden = False
        self.focused = False

    def focus(self):
        self.focused = True

    def __repr__(self):
        return f"Window(title={self.title!r}, id={self.id})"


class Screen:
    """Mock screen (display) object."""

    def __init__(self, x=0, y=0, width=1920, height=1080, dpi=1.0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.dpi = dpi
        self.rect = Rect(x, y, width, height)
        self.visible_rect = Rect(x, y, width, height)


# Module-level state
_screens = [Screen()]
_windows = []
_callbacks = {}


def screens():
    """Return list of available screens."""
    return list(_screens)


def windows():
    """Return list of open windows."""
    return list(_windows)


def active_window():
    """Return the currently focused window."""
    for w in _windows:
        if w.focused:
            return w
    return Window(title="<none>")


def register(event, callback):
    """Register for UI events (win_open, win_close, win_focus, etc.)."""
    _callbacks.setdefault(event, []).append(callback)


def unregister(event, callback):
    """Unregister UI event callback."""
    if event in _callbacks:
        _callbacks[event] = [cb for cb in _callbacks[event] if cb != callback]
