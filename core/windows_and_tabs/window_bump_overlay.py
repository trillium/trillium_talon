"""Window bump settings overlay — shows current settings and available commands."""

from talon import settings, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...trillium.utils.overlay_kit import (
    DismissibleOverlay,
    draw_panel_frame,
    draw_separator,
)

# Styling (matches OBS scene overlay)
PANEL_BG = "1a1a2eee"
PANEL_BORDER = "4a4a8a"
CORNER_RADIUS = 16
PANEL_PAD = 40
ROW_HEIGHT = 36
FONT_SIZE = 24
HEADER_SIZE = 36
LABEL_COLOR = "888888ff"
VALUE_COLOR = "aa44ffff"
CMD_COLOR = "ccccccff"
DESC_COLOR = "888888ff"
HINT_COLOR = "aaaaaa"
HINT_SIZE = 16
MIN_PANEL_W = 520

COMMANDS = [
    ("bump left", "Move window left one step"),
    ("bump right", "Move window right one step"),
    ("bump left <n>", "Move window left n steps"),
    ("bump right <n>", "Move window right n steps"),
    ("widen", "Widen window one step"),
    ("narrow", "Narrow window one step"),
    ("widen <n>", "Widen window n steps"),
    ("narrow <n>", "Narrow window n steps"),
]


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    screen = ui.main_screen()
    rect = screen.rect

    bump_pct = settings.get("user.window_bump_step", 0.03) * 100
    resize_pct = settings.get("user.window_resize_step", 0.03) * 100

    # Calculate panel dimensions
    settings_rows = 2
    separator_gap = 20
    cmd_header_h = ROW_HEIGHT
    panel_h = (
        PANEL_PAD * 2
        + HEADER_SIZE + 16                          # header + gap
        + ROW_HEIGHT * settings_rows + 8             # settings rows
        + separator_gap                              # separator
        + cmd_header_h                               # "Commands" sub-header
        + ROW_HEIGHT * len(COMMANDS) + 4             # command rows
        + 16 + HINT_SIZE                             # timeout hint
    )

    # Measure widths for two-column command table
    c.paint.textsize = FONT_SIZE
    cmd_col_w = max(c.paint.measure_text(cmd)[1].width for cmd, _ in COMMANDS) + 40
    desc_col_w = max(c.paint.measure_text(desc)[1].width for _, desc in COMMANDS)
    panel_w = max(PANEL_PAD * 2 + cmd_col_w + desc_col_w, MIN_PANEL_W)

    # Center panel
    panel_x = rect.x + (rect.width - panel_w) / 2
    panel_y = rect.y + (rect.height - panel_h) / 2

    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    overlay.set_panel_rect(panel_rect)

    # Panel frame
    draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_BG, PANEL_BORDER)

    # Close hint
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)

    # Header
    y = panel_y + PANEL_PAD + HEADER_SIZE
    c.paint.textsize = HEADER_SIZE
    c.paint.color = LABEL_COLOR
    c.draw_text("Window Bump", panel_x + PANEL_PAD, y)

    # Settings section
    y += 16
    col_x = panel_x + PANEL_PAD

    # Bump step
    y += ROW_HEIGHT
    c.paint.textsize = FONT_SIZE
    c.paint.color = LABEL_COLOR
    c.draw_text("Bump step:", col_x, y)
    c.paint.color = VALUE_COLOR
    c.paint.font.embolden = True
    c.draw_text(f"{bump_pct:.0f}%", col_x + 220, y)
    c.paint.font.embolden = False

    # Resize step
    y += ROW_HEIGHT
    c.paint.color = LABEL_COLOR
    c.draw_text("Resize step:", col_x, y)
    c.paint.color = VALUE_COLOR
    c.paint.font.embolden = True
    c.draw_text(f"{resize_pct:.0f}%", col_x + 220, y)
    c.paint.font.embolden = False

    # Timeout line
    y += ROW_HEIGHT
    c.paint.color = LABEL_COLOR
    c.paint.textsize = HINT_SIZE
    c.draw_text("Timeout: 60s", col_x, y - 4)

    # Separator
    y += separator_gap // 2
    draw_separator(c, panel_x + PANEL_PAD, panel_x + panel_w - PANEL_PAD, y, PANEL_BORDER)

    # Commands sub-header
    y += cmd_header_h
    c.paint.textsize = FONT_SIZE
    c.paint.color = LABEL_COLOR
    c.paint.font.embolden = True
    c.draw_text("Commands", col_x, y)
    c.paint.font.embolden = False

    # Command rows
    for cmd, desc in COMMANDS:
        y += ROW_HEIGHT
        c.paint.textsize = FONT_SIZE
        c.paint.color = CMD_COLOR
        c.draw_text(cmd, col_x, y)
        c.paint.color = DESC_COLOR
        c.draw_text(desc, col_x + cmd_col_w, y)


_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide="30s")


def show():
    _overlay.show()


def hide():
    _overlay.hide()


def is_showing() -> bool:
    return _overlay.is_showing
