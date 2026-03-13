"""
Memory Overlay - Full-screen panel showing saved personal command reference

Dim backdrop with a centered panel listing command/description pairs.
Follows the recall help overlay visual patterns (navy/blue palette).
Supports pages for grouped display. No auto-hide — stays until dismissed.
"""

from talon import skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

_canvas: Canvas = None
_entries: list[dict] = []
_page: str = ""
_available_pages: list[str] = []

# ── Color palette (matches recall help overlay) ──

DIM_BG = "000000cc"
PANEL_COLOR = "1a1a2eee"
PANEL_BORDER = "4a4a8a"
CORNER_RADIUS = 16
PANEL_PAD = 40

TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
LINE_COLOR = "4a4a6a"

HEADER_SIZE = 36
ROW_CMD_SIZE = 20
ROW_DESC_SIZE = 16
HINT_SIZE = 16
EMPTY_SIZE = 20

ROW_PAD = 12


def _draw_rounded_rect(c: SkiaCanvas, rect: Rect, radius: float):
    """Draw a rounded rectangle using a Skia path."""
    r = min(radius, rect.width / 2, rect.height / 2)
    path = skia.Path()
    path.add_rounded_rect(rect, r, r, skia.Path.Direction.CW)
    c.draw_path(path)


def _draw_panel_frame(c: SkiaCanvas, rect: Rect):
    """Draw panel background + border."""
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
    close_text = '"memory close" or Esc'
    c.paint.textsize = HINT_SIZE
    c.paint.color = DIM_COLOR
    close_w = c.paint.measure_text(close_text)[1].width
    x_size = 14
    gap = 10
    total_hint_w = close_w + gap + x_size
    close_x = panel_x + panel_w - PANEL_PAD - total_hint_w
    c.draw_text(close_text, close_x, panel_y + PANEL_PAD + HINT_SIZE)

    # X mark
    x_x = close_x + close_w + gap
    x_cy = panel_y + PANEL_PAD + HINT_SIZE / 2
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
    panel_h += HEADER_SIZE + 20                # header + gap

    if _entries:
        panel_h += len(_entries) * (ROW_CMD_SIZE + ROW_PAD)
    else:
        panel_h += EMPTY_SIZE + 20             # empty state message

    if not _page and _available_pages:
        panel_h += 20 + HINT_SIZE + 8 + HINT_SIZE  # pages footer

    panel_h += PANEL_PAD                       # bottom padding

    panel_w = sr.width * 0.50

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
    title = f"Memory \u203a {_page}" if _page else "Memory"
    c.draw_text(title, cx, cy + HEADER_SIZE)

    _draw_close_hint(c, panel_x, panel_y, panel_w)

    cy += HEADER_SIZE + 20

    if not _entries:
        # ── Empty state ──
        c.paint.textsize = EMPTY_SIZE
        c.paint.color = DIM_COLOR
        c.draw_text("No entries yet. Add commands via agent or voice.", cx, cy + EMPTY_SIZE)
    else:
        # ── Entry rows ──
        cmd_col_w = content_w * 0.40
        for entry in _entries:
            cmd = entry.get("command", "")
            desc = entry.get("description", "")

            c.paint.textsize = ROW_CMD_SIZE
            c.paint.color = TEXT_COLOR
            c.draw_text(cmd, cx, cy + ROW_CMD_SIZE)

            c.paint.textsize = ROW_DESC_SIZE
            c.paint.color = DIM_COLOR
            c.draw_text(desc, cx + cmd_col_w, cy + ROW_CMD_SIZE)

            cy += ROW_CMD_SIZE + ROW_PAD

    # ── Pages footer (default view only) ──
    if not _page and _available_pages:
        cy += 8
        c.paint.color = LINE_COLOR
        c.paint.style = c.paint.Style.STROKE
        c.paint.stroke_width = 1
        c.draw_line(cx, cy, cx + content_w, cy)
        c.paint.style = c.paint.Style.FILL
        cy += 12
        c.paint.textsize = HINT_SIZE
        c.paint.color = DIM_COLOR
        pages_text = "Pages: " + ", ".join(_available_pages)
        c.draw_text(pages_text, cx, cy + HINT_SIZE)
        cy += HINT_SIZE + 8
        c.draw_text('Say "memory show <page>" to view', cx, cy + HINT_SIZE)

    c.restore()


def update(entries: list[dict], page: str = "", available_pages: list[str] = None):
    """Update overlay entries and re-freeze the canvas."""
    global _entries, _page, _available_pages
    _entries = entries
    _page = page
    _available_pages = available_pages or []
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
