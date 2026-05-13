"""
Recall Overlay Prompt - Prompt overlay used by combine/rename/alias two-step commands.
"""

from talon import cron, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect
from .recall_overlay_shared import (
    HELP_BG_COLOR,
    HELP_PANEL_COLOR,
    HELP_NAME_SIZE,
    HELP_DETAIL_SIZE,
    HELP_DIM_COLOR,
    HELP_ACCENT,
    HELP_TEXT_COLOR,
    HELP_PANEL_PAD,
    _draw_rounded_rect,
    set_overlay_active,
)

PROMPT_DURATION = "15s"
PROMPT_CORNER_RADIUS = 16

_prompt_canvas: Canvas = None
_prompt_hide_job = None
_prompt_title: str = ""
_prompt_subtitle: str = ""


def on_draw_prompt(c: SkiaCanvas):
    screen = ui.main_screen()
    sr = screen.rect

    # Dim background
    c.paint.style = c.paint.Style.FILL
    c.paint.color = HELP_BG_COLOR
    c.draw_rect(Rect(sr.x, sr.y, sr.width, sr.height))

    # Centered prompt panel
    panel_w = sr.width * 0.4
    panel_h = 180
    panel_x = sr.x + (sr.width - panel_w) / 2
    panel_y = sr.y + (sr.height - panel_h) / 2

    c.paint.color = HELP_PANEL_COLOR
    prompt_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    _draw_rounded_rect(c, prompt_rect, PROMPT_CORNER_RADIUS)

    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = HELP_ACCENT
    _draw_rounded_rect(c, prompt_rect, PROMPT_CORNER_RADIUS)
    c.paint.style = c.paint.Style.FILL

    cx = panel_x + HELP_PANEL_PAD
    cy = panel_y + HELP_PANEL_PAD

    # Title
    c.paint.textsize = HELP_NAME_SIZE
    c.paint.color = HELP_TEXT_COLOR
    c.draw_text(_prompt_title, cx, cy + HELP_NAME_SIZE)
    cy += HELP_NAME_SIZE + 20

    # Subtitle
    c.paint.textsize = HELP_DETAIL_SIZE
    c.paint.color = HELP_DIM_COLOR
    c.draw_text(_prompt_subtitle, cx, cy + HELP_DETAIL_SIZE)
    cy += HELP_DETAIL_SIZE + 16

    c.paint.textsize = HELP_DETAIL_SIZE
    c.paint.color = HELP_DIM_COLOR
    c.draw_text('"recall close" to cancel', cx, cy + HELP_DETAIL_SIZE)


def show_prompt(title: str, subtitle: str):
    """Show a prompt overlay with custom title and subtitle."""
    global _prompt_canvas, _prompt_hide_job, _prompt_title, _prompt_subtitle
    _prompt_title = title
    _prompt_subtitle = subtitle

    if _prompt_hide_job:
        cron.cancel(_prompt_hide_job)
        _prompt_hide_job = None

    if _prompt_canvas:
        _prompt_canvas.unregister("draw", on_draw_prompt)
        _prompt_canvas.close()
        _prompt_canvas = None

    screen: Screen = ui.main_screen()
    _prompt_canvas = Canvas.from_screen(screen)
    _prompt_canvas.register("draw", on_draw_prompt)
    _prompt_canvas.freeze()

    _prompt_hide_job = cron.after(PROMPT_DURATION, hide_prompt)
    set_overlay_active("prompt", True)


def hide_prompt():
    """Hide the prompt overlay and cancel pending state."""
    global _prompt_canvas, _prompt_hide_job
    if _prompt_hide_job:
        cron.cancel(_prompt_hide_job)
        _prompt_hide_job = None
    if _prompt_canvas:
        _prompt_canvas.unregister("draw", on_draw_prompt)
        _prompt_canvas.close()
        _prompt_canvas = None
    from .recall_state import _cancel_pending
    _cancel_pending()
    set_overlay_active("prompt", False)
