"""
Memory Overlay - Full-screen panel showing saved personal command reference

Dim backdrop with a centered panel listing command/description pairs.
Follows the recall help overlay visual patterns (navy/blue palette).
Supports pages for grouped display. No auto-hide — stays until dismissed.
Uses DismissibleOverlay for lifecycle management.
"""

from talon import registry, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ..utils.overlay_kit import DismissibleOverlay, draw_close_hint, draw_dim_backdrop, draw_panel_frame, draw_separator

_entries: list[dict] = []
_page: str = ""
_available_pages: list[str] = []
_context_tag: str = ""

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


def _on_hide():
    """Called when overlay is dismissed via click-outside or escape.
    Clears the memory_active tag directly (overlay is already hiding)."""
    from . import memory as mem
    mem._ctx.tags = []


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    screen = ui.main_screen()
    sr = screen.rect

    # Full-screen dim backdrop
    draw_dim_backdrop(c, sr, DIM_BG)

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
    overlay.set_panel_rect(panel_rect)
    draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_COLOR, PANEL_BORDER)

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

    # ── Context status badge ──
    if _context_tag:
        title_w = c.paint.measure_text(title)[1].width
        active = _context_tag in registry.tags
        badge_color = "44cc44" if active else "cc4444"
        badge_label = "Active" if active else "Inactive"
        dot_r = 5
        dot_x = cx + title_w + 16 + dot_r
        dot_cy = cy + HEADER_SIZE - HINT_SIZE / 2
        c.paint.color = badge_color
        c.draw_circle(dot_x, dot_cy, dot_r)
        c.paint.textsize = HINT_SIZE
        c.draw_text(badge_label, dot_x + dot_r + 6, cy + HEADER_SIZE)

    draw_close_hint(c, '"memory close" or Esc', HINT_SIZE, DIM_COLOR, panel_x, panel_y, panel_w, PANEL_PAD)

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
        draw_separator(c, cx, cx + content_w, cy, LINE_COLOR)
        cy += 12
        c.paint.textsize = HINT_SIZE
        c.paint.color = DIM_COLOR
        pages_text = "Pages: " + ", ".join(_available_pages)
        c.draw_text(pages_text, cx, cy + HINT_SIZE)
        cy += HINT_SIZE + 8
        c.draw_text('Say "memory show <page>" to view', cx, cy + HINT_SIZE)

    c.restore()


_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide=None, on_hide=_on_hide)


def update(entries: list[dict], page: str = "", available_pages: list[str] = None, context_tag: str = ""):
    """Update overlay entries and re-freeze the canvas."""
    global _entries, _page, _available_pages, _context_tag
    _entries = entries
    _page = page
    _available_pages = available_pages or []
    _context_tag = context_tag
    _overlay.freeze()


def show():
    """Create and show the overlay canvas."""
    _overlay.show()


def hide():
    """Destroy the overlay canvas."""
    _overlay.hide()


def _on_update_contexts():
    """Re-render overlay when contexts change so the status badge stays current."""
    if _overlay.is_showing and _context_tag:
        _overlay.freeze()


registry.register("update_contexts", _on_update_contexts)
