"""Talon Screen API stubs."""

from talon.types.point import Point2d


class Screen:
    """Mock screen object representing a display."""

    def __init__(self, x=0, y=0, width=1920, height=1080, dpi=1.0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.dpi = dpi
        self.visible_rect = type("rect", (), {
            "x": x, "y": y, "width": width, "height": height,
        })()

    @property
    def rect(self):
        return type("rect", (), {
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
        })()


# Default screen list for testing
_screens = [Screen()]


def screens():
    """Return list of available screens."""
    return list(_screens)


def main_screen():
    """Return the main/primary screen."""
    return _screens[0] if _screens else None
