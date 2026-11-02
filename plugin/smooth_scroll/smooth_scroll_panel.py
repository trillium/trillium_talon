"""Live panel for the smooth scroll numbers; redraws whenever a value changes."""

from talon import Module, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...trillium.utils.overlay_kit import (
    HIGHLIGHT_SELECTED,
    DismissibleOverlay,
    draw_panel_frame,
    draw_separator,
)
from . import smooth_scroll

mod = Module()

PANEL_BG = "1a2e2eee"
PANEL_BORDER = "4a8a7a"
TEXT = "ffffffff"
DIM = "aaaaaa"
ACCENT = "5ab5a0"
PAD = 28
CHART_H = 90
ROW_H = 30
PANEL_W = 460
TITLE_SIZE = 24
FONT = 17

# (stats key, label, unit)
SETTING_ROWS = [
    ("pixels", "Pixels per frame", "px"),
    ("frames", "Finger frames", ""),
    ("frame_ms", "Frame interval", "ms"),
    ("decay", "Glide decay", ""),
    ("min_pixels", "Glide stops at", "px"),
]
RESULT_ROWS = [
    ("finger_px", "Finger distance", "px"),
    ("glide_frames", "Glide frames", ""),
    ("glide_px", "Glide distance", "px"),
    ("total_px", "Total distance", "px"),
    ("total_ms", "Total time", "ms"),
    ("speed_pxs", "Scroll speed", "px/s"),
]

_prev: dict = {}
_changed_keys: set = set()
_current: dict = {}


def _refresh():
    """Listener: diff against the last numbers and redraw."""
    global _prev, _changed_keys, _current
    new = smooth_scroll.stats()
    if _current:
        _prev = _current
        _changed_keys = {
            k for k, v in new.items() if _prev.get(k) != v and k != "overridden"
        }
    _current = new
    if _overlay.is_showing:
        _overlay.freeze()


def _fmt(v) -> str:
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return str(v)


def _draw_rows(c: SkiaCanvas, rows, x: float, y: float, w: float) -> float:
    for key, label, unit in rows:
        changed = key in _changed_keys
        c.paint.textsize = FONT
        c.paint.color = DIM
        c.draw_text(label, x, y)
        value = f"{_fmt(_current[key])} {unit}".strip()
        c.paint.color = HIGHLIGHT_SELECTED if changed else TEXT
        vw = c.paint.measure_text(value)[1].width
        c.draw_text(value, x + w - vw, y)
        if changed:
            was = f"was {_fmt(_prev.get(key))}"
            c.paint.textsize = FONT - 4
            c.paint.color = DIM
            ww = c.paint.measure_text(was)[1].width
            c.draw_text(was, x + w - vw - ww - 14, y)
        y += ROW_H
    return y


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    if not _current:
        _refresh()
    screen = ui.main_screen().rect
    run = smooth_scroll.last_run()
    extra = (ROW_H * 3 + CHART_H + 40) if run else 0
    h = (
        PAD * 2
        + TITLE_SIZE
        + 24
        + ROW_H * (len(SETTING_ROWS) + len(RESULT_ROWS))
        + 56
        + extra
    )
    rect = Rect(screen.x + screen.width - PANEL_W - 40, screen.y + 60, PANEL_W, h)
    overlay.set_panel_rect(rect)
    draw_panel_frame(c, rect, 16, PANEL_BG, PANEL_BORDER)

    x, w = rect.x + PAD, rect.width - PAD * 2
    y = rect.y + PAD + TITLE_SIZE
    c.paint.textsize = TITLE_SIZE
    c.paint.color = TEXT
    c.draw_text("Smooth scroll", x, y)
    c.paint.textsize = 13
    c.paint.color = DIM
    c.draw_text("voice-set" if _current["overridden"] else "defaults", x + w - 70, y)
    y += 34
    y = _draw_rows(c, SETTING_ROWS, x, y, w)
    y += 6
    draw_separator(c, x, x + w, y - ROW_H / 2 + 8, "3a5a5a")
    y += 10
    y = _draw_rows(c, RESULT_ROWS, x, y, w)
    if run:
        y += 14
        draw_separator(c, x, x + w, y - ROW_H / 2 + 8, "3a5a5a")
        y += 10
        measured = [
            ("Measured interval (avg)", f"{run['avg_ms']} ms"),
            ("Measured interval (min / max)", f"{run['min_ms']} / {run['max_ms']} ms"),
            ("Measured total", f"{run['total_px']} px in {run['total_ms']} ms"),
        ]
        for label, value in measured:
            c.paint.textsize = FONT
            c.paint.color = DIM
            c.draw_text(label, x, y)
            c.paint.color = TEXT
            vw = c.paint.measure_text(value)[1].width
            c.draw_text(value, x + w - vw, y)
            y += ROW_H
        # Pixels per event across real time: the bars show what was delivered when.
        events = run["events"]
        span = max(1, events[-1][0])
        peak = max(1, max(abs(dy) for _, dy, _ in events))
        base = y + CHART_H
        for t_ms, dy, tag in events:
            bx = x + w * t_ms / span
            bh = CHART_H * abs(dy) / peak
            c.paint.color = ACCENT if tag == "f" else HIGHLIGHT_SELECTED
            c.draw_rect(Rect(bx, base - bh, max(2, w / len(events) - 1), bh))
        c.paint.textsize = 12
        c.paint.color = DIM
        c.draw_text(
            "teal = finger, amber = glide; bar height = pixels per event, x = real time",
            x,
            base + 18,
        )
        y = base + 24
    c.paint.textsize = 13
    c.paint.color = ACCENT
    c.draw_text('"demo farther / shorter / distance 8"   "demo panel close"', x, y + 10)


# blocks_mouse=False so the pointer still reaches the window you are scrolling.
_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide=None, blocks_mouse=False)
smooth_scroll._listeners.append(_refresh)


@mod.action_class
class Actions:
    def smooth_scroll_panel_show():
        """Show the live smooth scroll numbers panel"""
        _refresh()
        _overlay.show()

    def smooth_scroll_panel_hide():
        """Hide the smooth scroll numbers panel"""
        _overlay.hide()
