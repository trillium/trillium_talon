"""
Recall Overlay Help - Commands reference panel overlay.
"""

from talon import cron, registry, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect
from .recall_overlay_shared import (
    HELP_BG_COLOR,
    HELP_HEADER_SIZE,
    HELP_CMD_SIZE,
    HELP_TEXT_COLOR,
    HELP_DIM_COLOR,
    HELP_PANEL_PAD,
    _draw_panel_frame,
    _draw_close_hint,
    set_overlay_active,
)

_help_canvas: Canvas = None
_help_hide_job = None

HELP_COMMANDS = [
    ('"recall assign <name>"', "save focused window"),
    ('"<name>"', "switch to window"),
    ('"<name> <number>"', "press number key"),
    ('"<name> <dictation>"', "dictate into window"),
    ('"<name> <dictation> <ender>"', "dictate + Enter"),
    ('"recall restore <name>"', "relaunch terminal"),
    ('"recall alias <name> <alias>"', "add alias"),
    ('"recall unalias <alias>"', "remove alias"),
    ('"recall combine <a> <b>"', "merge b as alias of a"),
    ('"recall rename <name> <new>"', "rename window"),
    ('"recall promote <alias>"', "make alias the primary name"),
    ('"recall list"', "show labels on windows"),
    ('"recall status"', "window status panel"),
    ('"recall help"', "this screen"),
    ('"recall forget <name>"', "remove"),
    ('"recall forget all"', "clear all"),
    ('"recall close"', "dismiss overlay"),
]


def on_draw_help(c: SkiaCanvas):
    screen = ui.main_screen()
    sr = screen.rect

    # Full-screen dim background
    c.paint.style = c.paint.Style.FILL
    c.paint.color = HELP_BG_COLOR
    c.draw_rect(Rect(sr.x, sr.y, sr.width, sr.height))

    # Centered panel
    panel_w = sr.width * 0.50

    # Pre-calculate panel height
    panel_h = HELP_PANEL_PAD  # top padding
    panel_h += HELP_HEADER_SIZE + 20  # header + gap
    panel_h += len(HELP_COMMANDS) * (HELP_CMD_SIZE + 10)
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

    rx = panel_x + HELP_PANEL_PAD
    ry = panel_y + HELP_PANEL_PAD
    content_w = panel_w - HELP_PANEL_PAD * 2

    # Header
    c.paint.textsize = HELP_HEADER_SIZE
    c.paint.color = HELP_TEXT_COLOR
    c.draw_text("Commands", rx, ry + HELP_HEADER_SIZE)

    _draw_close_hint(c, panel_x, panel_y, panel_w)

    ry += HELP_HEADER_SIZE + 20

    # Build command list, replacing <ender> with actual ender words
    ender_words = sorted(registry.lists.get("user.dictation_ender", [{}])[-1].keys())
    if len(ender_words) > 1:
        ender_label = "(" + " | ".join(ender_words) + ")"
    elif ender_words:
        ender_label = ender_words[0]
    else:
        ender_label = "bravely"
    commands = [
        (cmd.replace("<ender>", ender_label), desc)
        for cmd, desc in HELP_COMMANDS
    ]

    # Command rows
    cmd_col_w = content_w * 0.55
    for cmd, desc in commands:
        c.paint.textsize = HELP_CMD_SIZE
        c.paint.color = HELP_TEXT_COLOR
        c.draw_text(cmd, rx, ry + HELP_CMD_SIZE)
        c.paint.color = HELP_DIM_COLOR
        c.draw_text(desc, rx + cmd_col_w, ry + HELP_CMD_SIZE)
        ry += HELP_CMD_SIZE + 10

    c.restore()


def show_help():
    """Show the help overlay with command reference."""
    global _help_canvas, _help_hide_job

    from .recall_overlay_status import hide_status
    hide_status()

    if _help_hide_job:
        cron.cancel(_help_hide_job)
        _help_hide_job = None

    if _help_canvas:
        _help_canvas.unregister("draw", on_draw_help)
        _help_canvas.close()
        _help_canvas = None

    screen: Screen = ui.main_screen()
    _help_canvas = Canvas.from_screen(screen)
    _help_canvas.register("draw", on_draw_help)
    set_overlay_active("help", True)


def hide_help():
    """Hide and destroy the help overlay canvas."""
    global _help_canvas, _help_hide_job
    if _help_hide_job:
        cron.cancel(_help_hide_job)
        _help_hide_job = None
    if _help_canvas:
        _help_canvas.unregister("draw", on_draw_help)
        _help_canvas.close()
        _help_canvas = None
    set_overlay_active("help", False)
