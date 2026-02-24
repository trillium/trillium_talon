"""
Speak Review Overlay - Persistent canvas showing current rewrite entry

Full-screen dimmed backdrop with a centered panel showing the current
entry details, progress counter, and voice command hints.
Follows the recall overlay visual patterns with a warm teal/amber palette.
"""

from talon import skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

_canvas: Canvas = None

# ── Color palette (warm teal / amber — relaxing but distinct from recall) ──

DIM_BG = "000000cc"            # full-screen dim backdrop
PANEL_COLOR = "1a2e2eee"       # dark teal panel fill
PANEL_BORDER = "4a8a7a"        # muted teal border
CORNER_RADIUS = 16
PANEL_PAD = 40

TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
ACCENT = "5ab5a0"              # teal accent (value arrows, highlights)
SECTION_COLOR = "8abfa5"       # soft sage for section label
REMOVE_COLOR = "cc6644"        # warm red-orange for removals
LINE_COLOR = "3a5a5a"          # subtle separator lines

# ── Font sizes (matching recall tiers) ──

HEADER_SIZE = 36
SECTION_SIZE = 20
KEY_SIZE = 28
VALUE_SIZE = 20
COUNTER_SIZE = 16
HINT_CMD_SIZE = 16
HINT_DETAIL_SIZE = 16

ROW_PAD = 16

# ── State ──

_section: str = ""
_key: str = ""
_value: str = ""
_current: int = 0
_total: int = 0

HINTS = [
    ('"accept"', "accept this rewrite"),
    ('"reject"', "reject this rewrite"),
    ('"unnecessary"', "already sounds right"),
    ('"regenerate"', "LLM redo all rejects"),
    ('"fix <text>"', "change pronunciation"),
    ('"next"', "skip to next"),
    ('"previous"', "go back"),
    ('"replay"', "hear again"),
    ('"stop review"', "end session"),
]


def _draw_rounded_rect(c: SkiaCanvas, rect: Rect, radius: float):
    """Draw a rounded rectangle using a Skia path."""
    r = min(radius, rect.width / 2, rect.height / 2)
    path = skia.Path()
    path.add_rounded_rect(rect, r, r, skia.Path.Direction.CW)
    c.draw_path(path)


def _draw_panel_frame(c: SkiaCanvas, rect: Rect):
    """Draw panel background + border (recall pattern)."""
    c.paint.style = c.paint.Style.FILL
    c.paint.color = PANEL_COLOR
    _draw_rounded_rect(c, rect, CORNER_RADIUS)
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = PANEL_BORDER
    _draw_rounded_rect(c, rect, CORNER_RADIUS)
    c.paint.style = c.paint.Style.FILL


def _draw_close_hint(c: SkiaCanvas, panel_x: float, panel_y: float, panel_w: float):
    """Draw close hint text + X in the top-right of the panel."""
    close_text = '"stop review"'
    c.paint.textsize = HINT_DETAIL_SIZE
    c.paint.color = DIM_COLOR
    close_w = c.paint.measure_text(close_text)[1].width
    x_size = 14
    gap = 10
    total_hint_w = close_w + gap + x_size
    close_x = panel_x + panel_w - PANEL_PAD - total_hint_w
    c.draw_text(close_text, close_x, panel_y + PANEL_PAD + HINT_DETAIL_SIZE)

    # X mark
    x_x = close_x + close_w + gap
    x_cy = panel_y + PANEL_PAD + HINT_DETAIL_SIZE / 2
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = DIM_COLOR
    c.draw_line(x_x, x_cy - x_size / 2, x_x + x_size, x_cy + x_size / 2)
    c.draw_line(x_x, x_cy + x_size / 2, x_x + x_size, x_cy - x_size / 2)
    c.paint.style = c.paint.Style.FILL


def _on_draw(c: SkiaCanvas):
    screen = ui.main_screen()
    sr = screen.rect

    # Full-screen dim backdrop
    c.paint.style = c.paint.Style.FILL
    c.paint.color = DIM_BG
    c.draw_rect(Rect(sr.x, sr.y, sr.width, sr.height))

    # Pre-calculate panel height
    panel_h = PANEL_PAD                        # top padding
    panel_h += HEADER_SIZE + 20                # "Rewrite Review" header + gap
    panel_h += SECTION_SIZE + 12               # section label + gap
    panel_h += KEY_SIZE + 12                   # key + gap
    panel_h += VALUE_SIZE + 20                 # value + gap
    panel_h += COUNTER_SIZE + 20               # counter + gap before separator
    panel_h += 1 + ROW_PAD                     # separator + gap
    panel_h += len(HINTS) * (HINT_CMD_SIZE + 10)  # hint rows
    panel_h += PANEL_PAD                       # bottom padding

    panel_w = sr.width * 0.40

    # Clamp to screen
    if panel_h > sr.height - 40:
        panel_h = sr.height - 40

    panel_x = sr.x + (sr.width - panel_w) / 2
    panel_y = sr.y + (sr.height - panel_h) / 2

    # Draw panel frame
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    _draw_panel_frame(c, panel_rect)

    # Clip to panel
    c.save()
    c.clip_rect(panel_rect)

    cx = panel_x + PANEL_PAD
    cy = panel_y + PANEL_PAD
    content_w = panel_w - PANEL_PAD * 2

    # ── Header ──
    c.paint.textsize = HEADER_SIZE
    c.paint.color = TEXT_COLOR
    c.draw_text("Rewrite Review", cx, cy + HEADER_SIZE)

    _draw_close_hint(c, panel_x, panel_y, panel_w)

    cy += HEADER_SIZE + 20

    # ── Section label ──
    c.paint.textsize = SECTION_SIZE
    c.paint.color = SECTION_COLOR
    c.draw_text(_section, cx, cy + SECTION_SIZE)
    cy += SECTION_SIZE + 12

    # ── Key (the word/phrase being rewritten) ──
    c.paint.textsize = KEY_SIZE
    c.paint.color = TEXT_COLOR
    c.draw_text(_key, cx, cy + KEY_SIZE)
    cy += KEY_SIZE + 12

    # ── Value (what it rewrites to, or removal indicator) ──
    c.paint.textsize = VALUE_SIZE
    if _value:
        c.paint.color = ACCENT
        display_value = f"-> {_value}"
    else:
        c.paint.color = REMOVE_COLOR
        display_value = "-> (remove)"
    c.draw_text(display_value, cx, cy + VALUE_SIZE)
    cy += VALUE_SIZE + 20

    # ── Counter ──
    c.paint.textsize = COUNTER_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text(f"{_current} / {_total}", cx, cy + COUNTER_SIZE)
    cy += COUNTER_SIZE + 20

    # ── Separator line ──
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 1
    c.paint.color = LINE_COLOR
    c.draw_line(cx, cy, cx + content_w, cy)
    c.paint.style = c.paint.Style.FILL
    cy += ROW_PAD

    # ── Command hints ──
    cmd_col_w = content_w * 0.45
    for cmd, desc in HINTS:
        c.paint.textsize = HINT_CMD_SIZE
        c.paint.color = TEXT_COLOR
        c.draw_text(cmd, cx, cy + HINT_CMD_SIZE)
        c.paint.color = DIM_COLOR
        c.draw_text(desc, cx + cmd_col_w, cy + HINT_CMD_SIZE)
        cy += HINT_CMD_SIZE + 10

    c.restore()


def update(section: str, key: str, value: str, current: int, total: int):
    """Update overlay state and re-freeze the canvas."""
    global _section, _key, _value, _current, _total
    _section = section
    _key = key
    _value = value
    _current = current
    _total = total
    if _canvas:
        _canvas.freeze()


def show():
    """Create and show the overlay canvas."""
    global _canvas
    if _canvas:
        hide()
    screen: Screen = ui.main_screen()
    _canvas = Canvas.from_screen(screen)
    _canvas.register("draw", _on_draw)
    _canvas.freeze()


def hide():
    """Destroy the overlay canvas."""
    global _canvas
    if _canvas:
        _canvas.unregister("draw", _on_draw)
        _canvas.close()
        _canvas = None
