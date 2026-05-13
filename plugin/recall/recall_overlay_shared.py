"""
Recall Overlay Shared - Imports, constants, and utilities shared by all overlay submodules.
"""

from talon import skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

# Help overlay styling
HELP_BG_COLOR = "000000cc"
HELP_PANEL_COLOR = "1a1a2eee"
HELP_PANEL_BORDER = "4a4a8a"
HELP_HEADER_SIZE = 36
HELP_NAME_SIZE = 24
HELP_DETAIL_SIZE = 16
HELP_CMD_SIZE = 16
HELP_SECTION_SIZE = 20
HELP_TEXT_COLOR = "ffffffff"
HELP_DIM_COLOR = "aaaaaa"
HELP_GREEN = "44cc44"
HELP_RED = "cc4444"
HELP_ACCENT = "6a6aff"
HELP_LINE_COLOR = "4a4a6a"
HELP_PANEL_PAD = 40
HELP_ROW_PAD = 16
HELP_CORNER_RADIUS = 16
PILL_CORNER_RADIUS = 12
COMBINE_CORNER_RADIUS = 16

# Active overlay registry — only labels/status/help/prompt call set_overlay_active
_active_overlays: set = set()


def set_overlay_active(name: str, active: bool):
    """Register or deregister an overlay name, then update the Talon tag."""
    if active:
        _active_overlays.add(name)
    else:
        _active_overlays.discard(name)
    _update_overlay_tag()


def _update_overlay_tag():
    """Set or clear the overlay_visible tag based on active overlays."""
    from .recall_state import overlay_ctx
    if _active_overlays:
        overlay_ctx.tags = ["user.recall_overlay_visible"]
    else:
        overlay_ctx.tags = []


def _draw_rounded_rect(c: SkiaCanvas, rect: Rect, radius: float):
    """Draw a rounded rectangle using a Skia path."""
    r = min(radius, rect.width / 2, rect.height / 2)
    path = skia.Path()
    path.add_rounded_rect(rect, r, r, skia.Path.Direction.CW)
    c.draw_path(path)


def _get_saved_windows():
    """Import saved_windows lazily to avoid circular imports."""
    from .recall_state import saved_windows
    from .recall_commands import find_window_by_id
    return saved_windows, find_window_by_id


def _resolve_command_display(stored: str) -> str:
    """Resolve a stored command to its spoken name for display.
    If stored as a shell command, reverse-lookup the spoken name."""
    from .recall_state import ctx
    commands = ctx.lists.get("user.recall_commands", {})
    if stored in commands:
        return stored
    for spoken, shell_cmd in commands.items():
        if shell_cmd == stored:
            return spoken
    return stored


def _resolve_command_shell(stored: str) -> str | None:
    """Resolve a stored command to the actual shell command it will run."""
    from .recall_state import ctx
    commands = ctx.lists.get("user.recall_commands", {})
    if stored in commands:
        return commands[stored]
    for spoken, shell_cmd in commands.items():
        if shell_cmd == stored:
            return shell_cmd
    return stored


def _pills_overlap(a: Rect, b: Rect) -> bool:
    """Check if two pill rects overlap."""
    return (a.x < b.x + b.width and a.x + a.width > b.x and
            a.y < b.y + b.height and a.y + a.height > b.y)


def _draw_panel_frame(c: SkiaCanvas, rect: Rect):
    """Draw panel background + border."""
    c.paint.style = c.paint.Style.FILL
    c.paint.color = HELP_PANEL_COLOR
    _draw_rounded_rect(c, rect, HELP_CORNER_RADIUS)
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = HELP_PANEL_BORDER
    _draw_rounded_rect(c, rect, HELP_CORNER_RADIUS)
    c.paint.style = c.paint.Style.FILL


def _draw_close_hint(c: SkiaCanvas, panel_x: float, panel_y: float, panel_w: float):
    """Draw the close hint text + X in the top-right of a panel."""
    close_text = '"recall close" or Esc'
    c.paint.textsize = HELP_DETAIL_SIZE
    c.paint.color = HELP_DIM_COLOR
    close_w = c.paint.measure_text(close_text)[1].width
    x_size = 14
    gap = 10
    total_hint_w = close_w + gap + x_size
    close_x = panel_x + panel_w - HELP_PANEL_PAD - total_hint_w
    c.draw_text(close_text, close_x, panel_y + HELP_PANEL_PAD + HELP_DETAIL_SIZE)

    x_x = close_x + close_w + gap
    x_cy = panel_y + HELP_PANEL_PAD + HELP_DETAIL_SIZE / 2
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = HELP_DIM_COLOR
    c.draw_line(x_x, x_cy - x_size / 2, x_x + x_size, x_cy + x_size / 2)
    c.draw_line(x_x, x_cy + x_size / 2, x_x + x_size, x_cy - x_size / 2)
    c.paint.style = c.paint.Style.FILL
