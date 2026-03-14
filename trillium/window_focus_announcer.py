from talon import Module, actions, app, cron, ui
from talon.canvas import Canvas
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.types import Rect

from .utils.overlay_kit import draw_rounded_rect

mod = Module()

_canvas = None
_hide_job = None
_label = ""

MAX_LEN = 30
FONT_SIZE = 13
PAD_X = 8
PAD_Y = 3
BG_COLOR = "000000cc"
TEXT_COLOR = "ffffffff"
CORNER_RADIUS = 4


def _format_label(app_name: str, title: str) -> str:
    if not title or title == app_name:
        label = app_name
    else:
        label = f"{app_name} \u00b7 {title}"
    if len(label) > MAX_LEN:
        label = label[: MAX_LEN - 1] + "\u2026"
    return label


def _draw(c: SkiaCanvas):
    c.paint.textsize = FONT_SIZE
    c.paint.font.embolden = True
    text_rect = c.paint.measure_text(_label)[1]

    pill_w = text_rect.width + PAD_X * 2
    pill_h = text_rect.height + PAD_Y * 2
    pill_x = c.rect.x
    pill_y = c.rect.y

    bg_rect = Rect(pill_x, pill_y, pill_w, pill_h)

    c.paint.style = c.paint.Style.FILL
    c.paint.color = BG_COLOR
    draw_rounded_rect(c, bg_rect, CORNER_RADIUS)

    c.paint.color = TEXT_COLOR
    c.draw_text(_label, pill_x + PAD_X, pill_y + PAD_Y + text_rect.height)


def _hide():
    global _canvas, _hide_job
    _hide_job = None
    if _canvas:
        _canvas.close()
        _canvas = None


def _show(label: str, screen: ui.Screen):
    global _canvas, _hide_job, _label

    if _hide_job:
        cron.cancel(_hide_job)
        _hide_job = None
    if _canvas:
        _canvas.close()
        _canvas = None

    _label = label
    _canvas = Canvas.from_screen(screen)
    _canvas.register("draw", _draw)
    _canvas.freeze()

    _hide_job = cron.after("2s", _hide)


def announce_window_focus(window: ui.Window):
    try:
        app_name = window.app.name
        title = window.title
        label = _format_label(app_name, title)
        _show(label, window.screen)
    except Exception as e:
        actions.user.boolean_print("window_focus_announcer", f"Error: {e}")


def on_ready():
    ui.register("win_focus", announce_window_focus)


app.register("ready", on_ready)
