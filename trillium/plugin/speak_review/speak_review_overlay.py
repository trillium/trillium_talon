"""
Speak Review Overlay - Persistent canvas showing current rewrite entry

Full-screen dimmed backdrop with a centered panel showing the current
entry details, progress counter, and voice command hints.
Follows the recall overlay visual patterns with a warm teal/amber palette.
Uses DismissibleOverlay for lifecycle management.
"""

from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas

from ...utils.overlay_kit import DismissibleOverlay, draw_close_hint, draw_dim_backdrop, draw_panel_frame, draw_separator
from talon.ui import Rect

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


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    screen = ui.main_screen()
    sr = screen.rect

    # Full-screen dim backdrop
    draw_dim_backdrop(c, sr, DIM_BG)

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
    c.draw_text("Rewrite Review", cx, cy + HEADER_SIZE)

    draw_close_hint(c, '"stop review"', HINT_DETAIL_SIZE, DIM_COLOR, panel_x, panel_y, panel_w, PANEL_PAD)

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
    draw_separator(c, cx, cx + content_w, cy, LINE_COLOR)
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


_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide=None)


def update(section: str, key: str, value: str, current: int, total: int):
    """Update overlay state and re-freeze the canvas."""
    global _section, _key, _value, _current, _total
    _section = section
    _key = key
    _value = value
    _current = current
    _total = total
    _overlay.freeze()


def show():
    """Create and show the overlay canvas."""
    _overlay.show()


def hide():
    """Destroy the overlay canvas."""
    _overlay.hide()
