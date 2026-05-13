"""
Recall Overlay Status - Saved-windows status panel overlay.
"""

from talon import cron, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect
from .recall_overlay_shared import (
    HELP_BG_COLOR,
    HELP_HEADER_SIZE,
    HELP_NAME_SIZE,
    HELP_DETAIL_SIZE,
    HELP_TEXT_COLOR,
    HELP_DIM_COLOR,
    HELP_GREEN,
    HELP_RED,
    HELP_ACCENT,
    HELP_LINE_COLOR,
    HELP_PANEL_PAD,
    HELP_ROW_PAD,
    _draw_panel_frame,
    _draw_close_hint,
    _get_saved_windows,
    _resolve_command_display,
    _resolve_command_shell,
    set_overlay_active,
)

_status_canvas: Canvas = None
_status_hide_job = None


def on_draw_status(c: SkiaCanvas):
    saved_windows, find_window_by_id = _get_saved_windows()
    screen = ui.main_screen()
    sr = screen.rect

    # Full-screen dim background
    c.paint.style = c.paint.Style.FILL
    c.paint.color = HELP_BG_COLOR
    c.draw_rect(Rect(sr.x, sr.y, sr.width, sr.height))

    # Centered panel
    panel_w = sr.width * 0.55

    # Sort: alphabetically by name, active windows first within that
    window_names = sorted(
        saved_windows.keys(),
        key=lambda n: (0 if find_window_by_id(saved_windows[n]["id"]) else 1, n.lower()),
    )

    # Pre-calculate panel height
    panel_h = HELP_PANEL_PAD  # top padding
    panel_h += HELP_HEADER_SIZE + 20  # header + gap
    for name in window_names:
        info = saved_windows[name]
        panel_h += HELP_NAME_SIZE + 8
        if info.get("path") or info.get("command"):
            panel_h += HELP_DETAIL_SIZE + 4
        panel_h += HELP_ROW_PAD
    panel_h += HELP_PANEL_PAD  # bottom padding

    # Clamp to screen
    if panel_h > sr.height - 40:
        panel_h = sr.height - 40

    panel_x = sr.x + (sr.width - panel_w) / 2
    panel_y = sr.y + (sr.height - panel_h) / 2

    # Draw panel
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    _draw_panel_frame(c, panel_rect)

    c.save()
    c.clip_rect(panel_rect)

    cx = panel_x + HELP_PANEL_PAD
    cy = panel_y + HELP_PANEL_PAD
    content_w = panel_w - HELP_PANEL_PAD * 2

    # Header
    c.paint.textsize = HELP_HEADER_SIZE
    c.paint.color = HELP_TEXT_COLOR
    c.draw_text("Recall Windows", cx, cy + HELP_HEADER_SIZE)

    _draw_close_hint(c, panel_x, panel_y, panel_w)

    cy += HELP_HEADER_SIZE + 20

    # Window rows
    for name in window_names:
        info = saved_windows[name]
        window = find_window_by_id(info["id"])

        # Status dot
        dot_radius = 5
        dot_x = cx + dot_radius
        dot_y = cy + HELP_NAME_SIZE / 2 + 2
        c.paint.color = HELP_GREEN if window else HELP_RED
        c.draw_circle(dot_x, dot_y, dot_radius)

        # Name line: name / aliases    AppName    [command_name]
        name_x = cx + dot_radius * 2 + 12
        aliases = info.get("aliases", [])
        all_names = " / ".join([name] + aliases)
        app_name = info.get("app", "")
        command = info.get("command")

        name_part = all_names
        if app_name:
            name_part += f"    {app_name}"

        c.paint.textsize = HELP_NAME_SIZE
        c.paint.color = HELP_TEXT_COLOR
        c.draw_text(name_part, name_x, cy + HELP_NAME_SIZE)

        if command:
            display_cmd = _resolve_command_display(command)
            name_part_w = c.paint.measure_text(name_part)[1].width
            c.paint.color = HELP_ACCENT
            c.draw_text(f"    {display_cmd}", name_x + name_part_w, cy + HELP_NAME_SIZE)

        cy += HELP_NAME_SIZE + 8

        # Detail line
        path = info.get("path")
        if command and path:
            shell_cmd = _resolve_command_shell(command)
            c.paint.textsize = HELP_DETAIL_SIZE
            c.paint.color = HELP_DIM_COLOR
            c.draw_text(f"cd {path} && {shell_cmd}", name_x, cy + HELP_DETAIL_SIZE)
            cy += HELP_DETAIL_SIZE + 4
        elif command:
            shell_cmd = _resolve_command_shell(command)
            c.paint.textsize = HELP_DETAIL_SIZE
            c.paint.color = HELP_DIM_COLOR
            c.draw_text(f"$ {shell_cmd}", name_x, cy + HELP_DETAIL_SIZE)
            cy += HELP_DETAIL_SIZE + 4
        elif path:
            c.paint.textsize = HELP_DETAIL_SIZE
            c.paint.color = HELP_DIM_COLOR
            c.draw_text(path, name_x, cy + HELP_DETAIL_SIZE)
            cy += HELP_DETAIL_SIZE + 4

        cy += HELP_ROW_PAD

        # Separator line
        c.paint.style = c.paint.Style.STROKE
        c.paint.stroke_width = 1
        c.paint.color = HELP_LINE_COLOR
        c.draw_line(cx, cy - HELP_ROW_PAD / 2, cx + content_w, cy - HELP_ROW_PAD / 2)
        c.paint.style = c.paint.Style.FILL

    c.restore()


def show_status():
    """Show the status overlay with all saved windows."""
    global _status_canvas, _status_hide_job

    from .recall_overlay_help import hide_help
    hide_help()

    if _status_hide_job:
        cron.cancel(_status_hide_job)
        _status_hide_job = None

    if _status_canvas:
        _status_canvas.unregister("draw", on_draw_status)
        _status_canvas.close()
        _status_canvas = None

    screen: Screen = ui.main_screen()
    _status_canvas = Canvas.from_screen(screen)
    _status_canvas.register("draw", on_draw_status)
    set_overlay_active("status", True)


def hide_status():
    """Hide and destroy the status overlay canvas."""
    global _status_canvas, _status_hide_job
    if _status_hide_job:
        cron.cancel(_status_hide_job)
        _status_hide_job = None
    if _status_canvas:
        _status_canvas.unregister("draw", on_draw_status)
        _status_canvas.close()
        _status_canvas = None
    set_overlay_active("status", False)
