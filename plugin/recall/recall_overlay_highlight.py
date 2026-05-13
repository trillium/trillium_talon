"""
Recall Overlay Highlight - Brief window capture highlight.
"""

from talon import cron, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect
from .recall_overlay_shared import _draw_rounded_rect

HIGHLIGHT_DURATION = "800ms"
HIGHLIGHT_COLOR = "6a6aff"
HIGHLIGHT_STROKE = 4
HIGHLIGHT_LABEL_SIZE = 16
HIGHLIGHT_LABEL_PAD_X = 10
HIGHLIGHT_LABEL_PAD_Y = 6

_highlight_canvas: Canvas = None
_highlight_hide_job = None
_highlight_window = None
_highlight_name: str = ""
_highlight_show_job = None


def on_draw_highlight(c: SkiaCanvas):
    if not _highlight_window:
        return
    try:
        r = _highlight_window.rect
    except Exception:
        return
    if r.width <= 0 or r.height <= 0:
        return

    # Border around the window (live rect)
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = HIGHLIGHT_STROKE
    c.paint.color = HIGHLIGHT_COLOR
    c.draw_rect(Rect(r.x, r.y, r.width, r.height))
    c.paint.style = c.paint.Style.FILL

    # Name label pill at top-center of window
    if _highlight_name:
        c.paint.textsize = HIGHLIGHT_LABEL_SIZE
        text_rect = c.paint.measure_text(_highlight_name)[1]
        text_w = text_rect.width
        text_h = text_rect.height

        pill_w = text_w + HIGHLIGHT_LABEL_PAD_X * 2
        pill_h = text_h + HIGHLIGHT_LABEL_PAD_Y * 2
        pill_x = r.x + r.width / 2 - pill_w / 2
        pill_y = r.y - pill_h - 2

        # Clamp above screen top
        if pill_y < 0:
            pill_y = r.y + 4

        # Background
        c.paint.color = HIGHLIGHT_COLOR
        pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)
        _draw_rounded_rect(c, pill_rect, 6)

        # Text
        c.paint.color = "ffffffff"
        c.draw_text(_highlight_name, pill_x + HIGHLIGHT_LABEL_PAD_X, pill_y + HIGHLIGHT_LABEL_PAD_Y + text_h)


def highlight_window(window, name: str):
    """Briefly highlight a window border to confirm capture.

    Delays 50ms to let the window manager finish positioning,
    then draws a single frozen frame at the window's settled rect.
    """
    global _highlight_window, _highlight_name, _highlight_show_job

    _highlight_window = window
    _highlight_name = name

    # Cancel any pending show/hide from a previous highlight
    if _highlight_show_job:
        cron.cancel(_highlight_show_job)
    hide_highlight()

    # Delay canvas creation so the WM has time to position the window
    _highlight_show_job = cron.after("100ms", _show_highlight)


def _show_highlight():
    """Create and freeze the highlight canvas."""
    global _highlight_canvas, _highlight_hide_job, _highlight_show_job
    _highlight_show_job = None

    if _highlight_canvas:
        _highlight_canvas.unregister("draw", on_draw_highlight)
        _highlight_canvas.close()
        _highlight_canvas = None

    screen: Screen = ui.main_screen()
    _highlight_canvas = Canvas.from_screen(screen)
    _highlight_canvas.register("draw", on_draw_highlight)
    _highlight_canvas.freeze()

    _highlight_hide_job = cron.after(HIGHLIGHT_DURATION, hide_highlight)


def hide_highlight():
    """Hide the window highlight."""
    global _highlight_canvas, _highlight_hide_job
    if _highlight_hide_job:
        cron.cancel(_highlight_hide_job)
        _highlight_hide_job = None
    if _highlight_canvas:
        _highlight_canvas.unregister("draw", on_draw_highlight)
        _highlight_canvas.close()
        _highlight_canvas = None
