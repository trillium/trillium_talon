"""
Links Overlay - one Herdr tab's URLs, numbered for "link open <n>"

Dim backdrop with a centered panel, laid out like the memory overlay
(navy/blue palette). Rows are numbered across pages so a number always means
the same URL while the view is open. A green dot marks URLs seen in the
latest scan of the tab. No auto-hide. Uses DismissibleOverlay for lifecycle.
"""

import time

from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ..utils.overlay_kit import (
    DismissibleOverlay,
    draw_close_hint,
    draw_dim_backdrop,
    draw_panel_frame,
    draw_separator,
)
from . import links_data

# ── View state (set by update()) ──
_title = ""
_subtitle_host = ""
_rows: list[dict] = []  # {"url", "last_seen", "live"} in frozen display order
_page = 0
_status = ""

# ── Color palette (matches memory overlay) ──

DIM_BG = "000000cc"
PANEL_COLOR = "1a1a2eee"
PANEL_BORDER = "4a4a8a"
CORNER_RADIUS = 16
PANEL_PAD = 40

TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
LINE_COLOR = "4a4a6a"
LIVE_COLOR = "44cc44"
NUM_COLOR = "8888ff"

HEADER_SIZE = 36
ROW_SIZE = 20
HINT_SIZE = 16
ROW_PAD = 12
NUM_COL_W = 44
AGE_COL_W = 56


def _fit(c: SkiaCanvas, text: str, max_w: float) -> str:
    """Longest prefix of text (with an ellipsis) that fits max_w pixels."""
    if c.paint.measure_text(text)[1].width <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if c.paint.measure_text(text[:mid] + "…")[1].width <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    sr = ui.main_screen().rect
    draw_dim_backdrop(c, sr, DIM_BG)

    start, end = links_data.page_bounds(_page, len(_rows))
    shown = max(1, end - start)

    panel_h = PANEL_PAD + HEADER_SIZE + 12 + HINT_SIZE + 20
    panel_h += shown * (ROW_SIZE + ROW_PAD)
    panel_h += 20 + HINT_SIZE + PANEL_PAD
    panel_w = sr.width * 0.60
    panel_h = min(panel_h, sr.height - 40)
    panel_x = sr.x + (sr.width - panel_w) / 2
    panel_y = sr.y + (sr.height - panel_h) / 2

    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    overlay.set_panel_rect(panel_rect)
    draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_COLOR, PANEL_BORDER)

    c.save()
    c.clip_rect(panel_rect)
    cx = panel_x + PANEL_PAD
    cy = panel_y + PANEL_PAD
    content_w = panel_w - PANEL_PAD * 2

    # ── Header ──
    c.paint.textsize = HEADER_SIZE
    c.paint.color = TEXT_COLOR
    c.draw_text(f"Links › {_title}", cx, cy + HEADER_SIZE)
    draw_close_hint(
        c,
        '"links close" or Esc',
        HINT_SIZE,
        DIM_COLOR,
        panel_x,
        panel_y,
        panel_w,
        PANEL_PAD,
    )
    cy += HEADER_SIZE + 12

    # ── Subtitle: count, page, host, scan status ──
    pages = links_data.page_count(len(_rows))
    parts = [f"{len(_rows)} links"]
    if pages > 1:
        parts.append(f"page {min(_page, pages - 1) + 1}/{pages}")
    if _subtitle_host:
        parts.append(_subtitle_host)
    if _status:
        parts.append(_status)
    c.paint.textsize = HINT_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text(_fit(c, "  ·  ".join(parts), content_w), cx, cy + HINT_SIZE)
    cy += HINT_SIZE + 20

    # ── Rows ──
    now = time.time()
    if not _rows:
        c.paint.textsize = ROW_SIZE
        c.paint.color = DIM_COLOR
        c.draw_text("No links seen in this tab yet.", cx, cy + ROW_SIZE)
        cy += ROW_SIZE + ROW_PAD
    for i in range(start, end):
        row = _rows[i]
        c.paint.textsize = ROW_SIZE
        c.paint.color = NUM_COLOR
        c.draw_text(str(i + 1), cx, cy + ROW_SIZE)

        if row.get("live"):
            c.paint.color = LIVE_COLOR
            c.draw_circle(cx + NUM_COL_W - 14, cy + ROW_SIZE / 2 + 2, 4)

        url_x = cx + NUM_COL_W
        url_w = content_w - NUM_COL_W - AGE_COL_W
        c.paint.color = TEXT_COLOR if row.get("live") else DIM_COLOR
        c.draw_text(_fit(c, row["url"], url_w), url_x, cy + ROW_SIZE)

        c.paint.textsize = HINT_SIZE
        c.paint.color = DIM_COLOR
        age = links_data.short_age(now - row.get("last_seen", now))
        c.draw_text(age, cx + content_w - AGE_COL_W + 12, cy + ROW_SIZE)
        cy += ROW_SIZE + ROW_PAD

    # ── Footer ──
    cy += 8
    draw_separator(c, cx, cx + content_w, cy, LINE_COLOR)
    cy += 12
    c.paint.textsize = HINT_SIZE
    c.paint.color = DIM_COLOR
    hint = '"link open <n>"  ·  "link copy <n>"'
    if pages > 1:
        hint += '  ·  "next" / "previous"'
    c.draw_text(hint, cx, cy + HINT_SIZE)

    c.restore()


_on_hide_callback = None


def _on_overlay_hide():
    if _on_hide_callback:
        _on_hide_callback()


_overlay = DismissibleOverlay(
    on_draw=_on_draw, auto_hide=None, on_hide=_on_overlay_hide
)


def set_on_hide(callback):
    """Register a callback for when the overlay is dismissed."""
    global _on_hide_callback
    _on_hide_callback = callback


def update(title: str, host: str, rows: list[dict], page: int, status: str):
    """Replace the view state and redraw."""
    global _title, _subtitle_host, _rows, _page, _status
    _title, _subtitle_host, _rows, _page, _status = title, host, rows, page, status
    _overlay.freeze()


def show():
    _overlay.show()


def hide():
    _overlay.hide()


def is_showing() -> bool:
    return _overlay.is_showing
