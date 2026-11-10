"""
Recall Overlay Flash - Flash notification pill.
"""

from talon import cron, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect
from .recall_overlay_shared import _draw_rounded_rect

FLASH_DURATION = "2500ms"
FLASH_FONT_SIZE = 20
FLASH_SUB_SIZE = 14
FLASH_PAD_X = 28
FLASH_PAD_Y = 16
FLASH_BG = "1a1a2eee"
FLASH_BORDER = "6a6aff"
FLASH_TEXT = "ffffffff"
FLASH_SUB_COLOR = "aaaaaa"
FLASH_CORNER = 12

_flash_canvas: Canvas = None
_flash_hide_job = None
_flash_message: str = ""
_flash_subtitle: str = ""


def on_draw_flash(c: SkiaCanvas):
    screen = ui.main_screen()
    sr = screen.rect

    c.paint.textsize = FLASH_FONT_SIZE
    text_rect = c.paint.measure_text(_flash_message)[1]
    text_w = text_rect.width
    text_h = text_rect.height

    # Measure subtitle if present
    sub_w = 0
    sub_h = 0
    if _flash_subtitle:
        c.paint.textsize = FLASH_SUB_SIZE
        sub_rect = c.paint.measure_text(_flash_subtitle)[1]
        sub_w = sub_rect.width
        sub_h = sub_rect.height

    pill_w = max(text_w, sub_w) + FLASH_PAD_X * 2
    pill_h = text_h + FLASH_PAD_Y * 2
    if _flash_subtitle:
        pill_h += sub_h + 8  # gap between lines

    pill_x = sr.x + (sr.width - pill_w) / 2
    pill_y = sr.y + sr.height * 0.35 - pill_h / 2

    # Background
    c.paint.style = c.paint.Style.FILL
    c.paint.color = FLASH_BG
    pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)
    _draw_rounded_rect(c, pill_rect, FLASH_CORNER)

    # Border
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = FLASH_BORDER
    _draw_rounded_rect(c, pill_rect, FLASH_CORNER)
    c.paint.style = c.paint.Style.FILL

    # Main text
    c.paint.color = FLASH_TEXT
    c.paint.textsize = FLASH_FONT_SIZE
    text_x = pill_x + FLASH_PAD_X
    text_y = pill_y + FLASH_PAD_Y + text_h
    c.draw_text(_flash_message, text_x, text_y)

    # Subtitle
    if _flash_subtitle:
        c.paint.color = FLASH_SUB_COLOR
        c.paint.textsize = FLASH_SUB_SIZE
        c.draw_text(_flash_subtitle, text_x, text_y + sub_h + 8)


def flash(message: str, subtitle: str = ""):
    """Show a brief centered notification pill with optional subtitle."""
    global _flash_canvas, _flash_hide_job, _flash_message, _flash_subtitle
    _flash_message = message
    _flash_subtitle = subtitle

    if _flash_hide_job:
        cron.cancel(_flash_hide_job)
        _flash_hide_job = None

    if _flash_canvas:
        _flash_canvas.unregister("draw", on_draw_flash)
        _flash_canvas.close()
        _flash_canvas = None

    screen: Screen = ui.main_screen()
    _flash_canvas = Canvas.from_screen(screen)
    _flash_canvas.register("draw", on_draw_flash)
    _flash_canvas.freeze()

    _flash_hide_job = cron.after(FLASH_DURATION, hide_flash)


def hide_flash():
    """Hide the flash notification."""
    global _flash_canvas, _flash_hide_job
    if _flash_hide_job:
        cron.cancel(_flash_hide_job)
        _flash_hide_job = None
    if _flash_canvas:
        _flash_canvas.unregister("draw", on_draw_flash)
        _flash_canvas.close()
        _flash_canvas = None
