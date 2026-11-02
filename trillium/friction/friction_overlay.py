"""Friction overlay — shows dictated text in real time during friction mode.

Displays a panel with the scope label, growing list of dictated lines,
and hint commands at the bottom. Non-interactive (doesn't block mouse).
"""

from talon import cron, skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------
PANEL_WIDTH = 420
PANEL_RADIUS = 12
PANEL_PAD = 16
PANEL_Y_OFFSET = 60  # from top of screen, below mode indicator

# Colors
BG_COLOR = "1a1a2add"
BORDER_COLOR = "4455aacc"
SCOPE_COLOR = "88aaffffcc"
TEXT_COLOR = "ddeeffee"
HINT_COLOR = "888899cc"
SEPARATOR_COLOR = "44556688"

# Font sizes
SCOPE_FONT_SIZE = 14
TEXT_FONT_SIZE = 16
HINT_FONT_SIZE = 12
LINE_SPACING = 6

# Hints shown at bottom
HINT_COMMANDS = [
    "friction end  -  finish and save",
    "just speak  -  append more text",
]

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_canvas: Canvas = None
_scope_label: str = ""
_lines: list[str] = []


def _on_draw(c: SkiaCanvas):
    if not _scope_label and not _lines:
        return

    screen: Screen = ui.main_screen()
    sr = screen.rect

    # Measure content height
    c.paint.textsize = SCOPE_FONT_SIZE
    scope_h = SCOPE_FONT_SIZE

    c.paint.textsize = TEXT_FONT_SIZE
    # Wrap lines that exceed panel width
    max_text_w = PANEL_WIDTH - PANEL_PAD * 2
    wrapped = []
    for line in _lines:
        wrapped.extend(_wrap_text(c, line, max_text_w))

    text_block_h = len(wrapped) * (TEXT_FONT_SIZE + LINE_SPACING) if wrapped else 0

    c.paint.textsize = HINT_FONT_SIZE
    hints_h = len(HINT_COMMANDS) * (HINT_FONT_SIZE + LINE_SPACING)

    # Separators: 2 lines (below scope, above hints)
    sep_gap = 12
    content_h = (
        PANEL_PAD
        + scope_h
        + sep_gap
        + max(text_block_h, TEXT_FONT_SIZE + LINE_SPACING)  # min 1 line height
        + sep_gap
        + hints_h
        + PANEL_PAD
    )

    panel_w = PANEL_WIDTH
    panel_h = content_h
    panel_x = sr.left + (sr.width - panel_w) / 2
    panel_y = sr.top + PANEL_Y_OFFSET
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)

    # Background (SVG: Path.add_rounded_rect is gone on new builds)
    c.paint.style = c.paint.Style.FILL
    c.paint.color = BG_COLOR
    pr_ = min(PANEL_RADIUS, panel_rect.width / 2, panel_rect.height / 2)
    px, py, pw, ph = panel_rect.x, panel_rect.y, panel_rect.width, panel_rect.height
    path = skia.Path.from_svg(
        f"M {px + pr_} {py} "
        f"L {px + pw - pr_} {py} "
        f"A {pr_} {pr_} 0 0 1 {px + pw} {py + pr_} "
        f"L {px + pw} {py + ph - pr_} "
        f"A {pr_} {pr_} 0 0 1 {px + pw - pr_} {py + ph} "
        f"L {px + pr_} {py + ph} "
        f"A {pr_} {pr_} 0 0 1 {px} {py + ph - pr_} "
        f"L {px} {py + pr_} "
        f"A {pr_} {pr_} 0 0 1 {px + pr_} {py} Z"
    )
    c.draw_path(path)

    # Border
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = BORDER_COLOR
    c.draw_path(path)
    c.paint.style = c.paint.Style.FILL

    y = panel_y + PANEL_PAD

    # Scope label
    c.paint.textsize = SCOPE_FONT_SIZE
    c.paint.color = SCOPE_COLOR
    c.draw_text(f"friction: {_scope_label}", panel_x + PANEL_PAD, y + SCOPE_FONT_SIZE)
    y += scope_h + sep_gap / 2

    # Separator below scope
    _draw_sep(c, panel_x + PANEL_PAD, panel_x + panel_w - PANEL_PAD, y)
    y += sep_gap / 2

    # Dictated text lines
    c.paint.textsize = TEXT_FONT_SIZE
    c.paint.color = TEXT_COLOR
    if wrapped:
        for wl in wrapped:
            y += TEXT_FONT_SIZE + LINE_SPACING
            c.draw_text(wl, panel_x + PANEL_PAD, y)
    else:
        y += TEXT_FONT_SIZE + LINE_SPACING
        c.paint.color = HINT_COLOR
        c.draw_text("listening...", panel_x + PANEL_PAD, y)

    y += sep_gap / 2

    # Separator above hints
    _draw_sep(c, panel_x + PANEL_PAD, panel_x + panel_w - PANEL_PAD, y)
    y += sep_gap / 2

    # Hint commands
    c.paint.textsize = HINT_FONT_SIZE
    c.paint.color = HINT_COLOR
    for hint in HINT_COMMANDS:
        y += HINT_FONT_SIZE + LINE_SPACING
        c.draw_text(hint, panel_x + PANEL_PAD, y)


def _draw_sep(c: SkiaCanvas, x1: float, x2: float, y: float):
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 1
    c.paint.color = SEPARATOR_COLOR
    c.draw_line(x1, y, x2, y)
    c.paint.style = c.paint.Style.FILL


def _wrap_text(c: SkiaCanvas, text: str, max_w: float) -> list[str]:
    """Word-wrap text to fit within max_w pixels."""
    words = text.split()
    if not words:
        return [text]
    lines = []
    current = words[0]
    for word in words[1:]:
        test = current + " " + word
        w = c.paint.measure_text(test)[1].width
        if w > max_w:
            lines.append(current)
            current = word
        else:
            current = test
    lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def show(scope: str):
    """Show the friction overlay with the given scope label."""
    global _canvas, _scope_label, _lines
    _scope_label = scope
    _lines = []

    if _canvas:
        _canvas.freeze()
        return

    screen: Screen = ui.main_screen()
    _canvas = Canvas.from_screen(screen)
    _canvas.blocks_mouse = False
    _canvas.register("draw", _on_draw)
    _canvas.freeze()


def append_line(text: str):
    """Add a dictated line and refresh the overlay."""
    global _canvas
    _lines.append(text)
    if _canvas:
        _canvas.freeze()


def hide():
    """Hide the friction overlay."""
    global _canvas, _scope_label, _lines
    _scope_label = ""
    _lines = []
    if _canvas:
        _canvas.unregister("draw", _on_draw)
        _canvas.close()
        _canvas = None
