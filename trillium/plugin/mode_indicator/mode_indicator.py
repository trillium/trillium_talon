import json
from pathlib import Path

from talon import Module, app, registry, resource, settings, skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.skia.imagefilter import ImageFilter
from talon.types.point import Point2d
from talon.ui import Rect

canvas: Canvas = None
mod = Module()

TOP_LINE_THICKNESS = 35

state_path = str(Path(__file__).parent / "mode_indicator_state.json")

_state = {
    "mode": "",
    "microphone": "",
    "parrot_on": False,
    "command_text": "",
    "opposite_text": "",
    "bar_color_override": None,
    "week_percent": 0,
    "week_remaining": "",
    "static_percent": "?%",
}


mod.setting(
    "mode_indicator_show",
    type=bool,
    default=False,
    desc="If true the mode indicator is shown",
)
mod.setting(
    "mode_indicator_show_mic_name",
    type=bool,
    default=False,
    desc="Show first two letters of microphone name if true",
)
mod.setting(
    "mode_indicator_size",
    type=float,
    desc="Mode indicator diameter in pixels",
)
mod.setting(
    "mode_indicator_x",
    type=float,
    desc="Mode indicator center X-position in percentages(0-1). 0=left, 1=right",
)
mod.setting(
    "mode_indicator_y",
    type=float,
    desc="Mode indicator center Y-position in percentages(0-1). 0=top, 1=bottom",
)
mod.setting(
    "mode_indicator_color_alpha",
    type=float,
    desc="Mode indicator alpha/opacity in percentages(0-1). 0=fully transparent, 1=fully opaque",
)
mod.setting(
    "mode_indicator_color_gradient",
    type=float,
    desc="Mode indicator gradient brightness in percentages(0-1). 0=darkest, 1=brightest",
)
mod.setting("mode_indicator_color_text", type=str)
mod.setting("mode_indicator_color_mute", type=str)
mod.setting("mode_indicator_color_sleep", type=str)
mod.setting("mode_indicator_color_dictation", type=str)
mod.setting("mode_indicator_color_mixed", type=str)
mod.setting("mode_indicator_color_command", type=str)
mod.setting("mode_indicator_color_other", type=str)
mod.setting("mode_indicator_color_friction", type=str, default="ff0000", desc="Color when friction capture mode is active")

setting_paths = {
    "user.mode_indicator_show",
    "user.mode_indicator_size",
    "user.mode_indicator_x",
    "user.mode_indicator_y",
    "user.mode_indicator_color_alpha",
    "user.mode_indicator_color_gradient",
    "user.mode_indicator_color_mute",
    "user.mode_indicator_color_sleep",
    "user.mode_indicator_color_dictation",
    "user.mode_indicator_color_mixed",
    "user.mode_indicator_color_command",
    "user.mode_indicator_color_other",
}


def get_mode_color() -> str:
    """Get color based on current Talon mode (for circle indicator)."""
    if _state["microphone"] == "None":
        return settings.get("user.mode_indicator_color_mute")
    mode = _state["mode"]
    if mode == "sleep":
        return settings.get("user.mode_indicator_color_sleep")
    elif mode == "dictation":
        return settings.get("user.mode_indicator_color_dictation")
    elif mode == "mixed":
        return settings.get("user.mode_indicator_color_mixed")
    elif mode == "command":
        return settings.get("user.mode_indicator_color_command")
    else:
        return settings.get("user.mode_indicator_color_other")


def get_bar_color() -> str:
    """Get color for top bar (supports override for friction mode, etc.)."""
    if _state["bar_color_override"]:
        return _state["bar_color_override"]
    return get_mode_color()


def get_alpha_color() -> str:
    return f"{int(settings.get('user.mode_indicator_color_alpha') * 255):02x}"


def get_gradient_color(color: str) -> str:
    factor = settings.get("user.mode_indicator_color_gradient")
    (r, g, b) = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = int(r * factor), int(g * factor), int(b * factor)
    return f"{r:02x}{g:02x}{b:02x}"


def on_draw(c: SkiaCanvas):
    screen: Screen = ui.main_screen()
    rect = screen.rect
    scale = screen.scale if app.platform != "mac" else 1

    # --- Draw top bar FIRST (so circle renders on top) ---
    bar_color = get_bar_color()
    bar_alpha = "44"  # 30% opacity
    c.paint.style = c.paint.Style.FILL
    c.paint.color = f"#{bar_color}{bar_alpha}"
    bar_height = TOP_LINE_THICKNESS * scale
    c.draw_rect(Rect(rect.left, rect.top, rect.width, bar_height))

    # Draw command text on the top line
    c.paint.shader = None
    c.paint.style = c.paint.Style.FILL
    c.paint.color = "ffffffff"  # White
    c.paint.textsize = 14

    text_base_x = rect.width * 0.35

    command_text = _state["command_text"]
    if command_text:
        display_text = command_text
        if len(display_text) > 20:
            display_text = display_text[:17] + "..."
        c.draw_text(display_text, text_base_x, 20)

    opposite_text = _state["opposite_text"]
    if opposite_text:
        display_text = opposite_text
        if len(display_text) > 20:
            display_text = display_text[:17] + "..."
        c.draw_text(display_text, text_base_x, 35)

    # Draw usage + week info just right of the mode indicator
    text_right_x = rect.width * 0.45
    c.draw_text(str(_state['static_percent']), text_right_x, 20)
    week_remaining = _state.get("week_remaining", "")
    week_text = f"{_state['week_percent']}%  {week_remaining}" if week_remaining else f"{_state['week_percent']}%"
    c.draw_text(week_text, text_right_x, 35)

    # --- Draw circle SECOND (on top of bar) ---
    circle_color = get_mode_color()
    circle_gradient = get_gradient_color(circle_color)
    circle_alpha = get_alpha_color()
    text_color = settings.get("user.mode_indicator_color_text")

    radius = settings.get("user.mode_indicator_size") * scale / 2
    circle_x = rect.left + min(
        max(settings.get("user.mode_indicator_x") * rect.width, radius),
        rect.width - radius,
    )
    circle_y = rect.top + min(
        max(settings.get("user.mode_indicator_y") * rect.height, radius),
        rect.height - radius,
    )

    c.paint.shader = skia.Shader.radial_gradient(
        Point2d(circle_x, circle_y), radius, [f"{circle_color}{circle_alpha}", circle_gradient]
    )
    c.paint.imagefilter = ImageFilter.drop_shadow(1, 1, 1, 1, circle_gradient)
    c.paint.style = c.paint.Style.FILL
    c.paint.color = f"{circle_color}{circle_alpha}"
    c.draw_circle(circle_x, circle_y, radius)

    # Draw ring around the indicator (green if parrot is on, red if off)
    c.paint.shader = None
    c.paint.imagefilter = None
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    if _state["parrot_on"]:
        c.paint.color = "00aa00ff"  # Green
    else:
        c.paint.color = "aa0000ff"  # Red
    c.draw_circle(circle_x, circle_y, radius)

    # Draw mic name text
    if settings.get("user.mode_indicator_show_mic_name"):
        c.paint.shader = None
        c.paint.style = c.paint.Style.FILL
        c.paint.color = text_color
        mic = _state["microphone"]
        text = mic[:2] if mic else ""
        text_rect = c.paint.measure_text(text)[1]
        c.draw_text(
            text,
            circle_x - text_rect.center.x,
            circle_y - text_rect.center.y,
        )


def show_indicator():
    global canvas
    screen: Screen = ui.main_screen()
    canvas = Canvas.from_screen(screen)
    canvas.register("draw", on_draw)


def hide_indicator():
    global canvas
    if canvas:
        canvas.unregister("draw", on_draw)
        canvas.close()
        canvas = None


def update_indicator():
    if settings.get("user.mode_indicator_show"):
        if not canvas:
            show_indicator()
        canvas.freeze()
    elif canvas:
        hide_indicator()


def rebuild_indicator():
    """Destroy and recreate the canvas (for screen changes, settings that affect geometry)."""
    if canvas:
        hide_indicator()
    update_indicator()


@resource.watch(state_path)
def on_state_change(f):
    """Reload state from JSON and redraw."""
    global _state
    try:
        data = json.load(f)
        _state.update(data)
    except Exception:
        return
    update_indicator()


def on_update_settings(updated_settings: set[str]):
    if setting_paths & updated_settings:
        rebuild_indicator()


def on_ready():
    registry.register("update_settings", on_update_settings)
    ui.register("screen_change", lambda _: rebuild_indicator())


app.register("ready", on_ready)
