"""Modal list for Sidecar lists (panes, views, controls, requests): pick by number."""

from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...utils.overlay_kit import (
    DismissibleOverlay,
    draw_close_hint,
    draw_dim_backdrop,
    draw_panel_frame,
)
from ...utils.overlay_selector import overlay_labels

DIM_BG = "000000cc"
PANEL_COLOR = "1a2e2eee"
PANEL_BORDER = "4a8a7a"
TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
ACCENT = "5ab5a0"
PAD = 36
ROW_H = 28

_title = ""
_rows: list[dict] = []
_footer = ""


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    sr = ui.main_screen().rect
    draw_dim_backdrop(c, sr, DIM_BG)
    w = sr.width * 0.4
    h = min(sr.height - 40, PAD * 2 + 56 + 40 + max(1, len(_rows)) * ROW_H)
    rect = Rect(sr.x + (sr.width - w) / 2, sr.y + (sr.height - h) / 2, w, h)
    draw_panel_frame(c, rect, 16, PANEL_COLOR, PANEL_BORDER)
    c.save()
    c.clip_rect(rect)
    x, y = rect.x + PAD, rect.y + PAD
    c.paint.textsize = 30
    c.paint.color = TEXT_COLOR
    c.draw_text(_title, x, y + 30)
    draw_close_hint(c, '"close"', 16, DIM_COLOR, rect.x, rect.y, w, PAD)
    y += 56
    c.paint.textsize = 18
    if not _rows:
        c.paint.color = DIM_COLOR
        c.draw_text("Nothing to show.", x, y + 18)
    for label, row in zip(overlay_labels(len(_rows), "letter"), _rows):
        c.paint.color = ACCENT
        if row.get("header"):
            c.draw_text(row["name"].upper(), x, y + 18)
            y += ROW_H
            continue
        c.draw_text(f"{label.upper()}.", x, y + 18)
        c.paint.color = TEXT_COLOR
        c.draw_text(row["name"], x + 40, y + 18)
        if row.get("current"):
            c.paint.color = ACCENT
            nw = c.paint.measure_text(row["name"])[1].width
            c.draw_text("● current", x + 40 + nw + 14, y + 18)
        if row.get("detail"):
            c.paint.color = DIM_COLOR
            c.paint.textsize = 14 if row.get("current") is not None else 18
            tw = c.paint.measure_text(row["detail"])[1].width
            c.draw_text(row["detail"], rect.x + w - PAD - tw, y + 18)
        c.paint.textsize = 18
        y += ROW_H
    if _footer:
        c.paint.textsize = 16
        c.paint.color = ACCENT
        c.draw_text(_footer, x, rect.y + h - PAD + 8)
    c.restore()
    overlay.set_panel_rects([rect])


_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide=None)


def show(title: str, rows: list[dict], footer: str = ""):
    global _title, _rows, _footer
    _title, _rows, _footer = title, rows, footer
    _overlay.show()


def hide():
    _overlay.hide()
