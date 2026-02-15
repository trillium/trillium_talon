from talon import Module, actions, app, cron, registry, scope, settings, skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.skia.imagefilter import ImageFilter
from talon.types.point import Point2d
from talon.ui import Rect

canvas: Canvas = None
current_mode = ""
current_microphone = ""
current_parrot_on = False
last_command_text = ""
opposite_command_text = ""
_bar_color_override = None  # Event-driven color override for top bar only
mod = Module()

TOP_LINE_THICKNESS = 35


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
    if current_microphone == "None":
        return settings.get("user.mode_indicator_color_mute")
    if current_mode == "sleep":
        return settings.get("user.mode_indicator_color_sleep")
    elif current_mode == "dictation":
        return settings.get("user.mode_indicator_color_dictation")
    elif current_mode == "mixed":
        return settings.get("user.mode_indicator_color_mixed")
    elif current_mode == "command":
        return settings.get("user.mode_indicator_color_command")
    else:
        return settings.get("user.mode_indicator_color_other")


def get_bar_color() -> str:
    """Get color for top bar (supports override for friction mode, etc.)."""
    if _bar_color_override:
        return _bar_color_override
    return get_mode_color()


def get_alpha_color() -> str:
    return f"{int(settings.get('user.mode_indicator_color_alpha') * 255):02x}"


def get_gradient_color(color: str) -> str:
    factor = settings.get("user.mode_indicator_color_gradient")
    # hex -> rgb
    (r, g, b) = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
    # Darken rgb
    r, g, b = int(r * factor), int(g * factor), int(b * factor)
    # rgb -> hex
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

    if last_command_text:
        display_text = last_command_text
        if len(display_text) > 20:
            display_text = display_text[:17] + "..."
        c.draw_text(display_text, text_base_x, 20)

    if opposite_command_text:
        display_text = opposite_command_text
        if len(display_text) > 20:
            display_text = display_text[:17] + "..."
        c.draw_text(display_text, text_base_x, 35)

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
    if current_parrot_on:
        c.paint.color = "00aa00ff"  # Green
    else:
        c.paint.color = "aa0000ff"  # Red
    c.draw_circle(circle_x, circle_y, radius)

    # Draw mic name text
    if settings.get("user.mode_indicator_show_mic_name"):
        c.paint.shader = None
        c.paint.style = c.paint.Style.FILL
        c.paint.color = text_color
        text = current_microphone[:2]
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
        if canvas:
            hide_indicator()
        show_indicator()
        canvas.freeze()
    elif canvas:
        hide_indicator()


def on_update_contexts():
    global current_mode, current_parrot_on
    modes = scope.get("mode")
    if "sleep" in modes:
        mode = "sleep"
    elif "dictation" in modes:
        if "command" in modes:
            mode = "mixed"
        else:
            mode = "dictation"
    elif "command" in modes:
        mode = "command"
    else:
        mode = "other"

    # Check if parrot_on tag changed
    tags = scope.get("tag", [])
    parrot_on = "user.parrot_on" in tags

    # Update indicator if mode or parrot state changed
    if current_mode != mode or current_parrot_on != parrot_on:
        current_mode = mode
        current_parrot_on = parrot_on
        update_indicator()


def on_update_settings(updated_settings: set[str]):
    if setting_paths & updated_settings:
        update_indicator()


def poll_microphone():
    global current_microphone
    microphone = actions.sound.active_microphone()
    if current_microphone != microphone:
        current_microphone = microphone
        update_indicator()


def on_ready():
    registry.register("update_contexts", on_update_contexts)
    registry.register("update_settings", on_update_settings)
    ui.register("screen_change", lambda _: update_indicator)
    cron.interval("500ms", poll_microphone)


app.register("ready", on_ready)


@mod.action_class
class Actions:
    def mode_indicator_set_command_text(last_command: str, opposite_command: str = ""):
        """Set the last command and opposite command text for the mode indicator"""
        global last_command_text, opposite_command_text
        last_command_text = last_command
        opposite_command_text = opposite_command
        update_indicator()

    def mode_indicator_set_color(color: str):
        """Set a color override for the top bar (e.g., 'ff0000' for red). Circle keeps mode color."""
        global _bar_color_override
        _bar_color_override = color
        update_indicator()

    def mode_indicator_clear_color():
        """Clear the bar color override and return to normal mode-based coloring"""
        global _bar_color_override
        _bar_color_override = None
        update_indicator()
