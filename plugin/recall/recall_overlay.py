"""
Recall Overlay - Temporary window name labels + help screen

Shows a name tag on each saved window for 5 seconds,
triggered by "recall list" / "list recalls".
Windows that can't be found are shown in red at the top of the screen.

"recall help" shows a full-screen panel with all saved windows,
their metadata, and a command reference. Auto-hides after 30s.
"""

from talon import cron, registry, skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

canvas: Canvas = None
_hide_job = None

# Padding and styling constants
PAD_X = 20
PAD_Y = 12
FONT_SIZE = 48
SHOW_DURATION = "5s"
MISSING_GAP = 10  # vertical gap between stacked missing-window labels

# Status overlay globals
_status_canvas: Canvas = None
_status_hide_job = None

# Help overlay globals
_help_canvas: Canvas = None
_help_hide_job = None

# Help overlay styling
HELP_BG_COLOR = "000000cc"
HELP_PANEL_COLOR = "1a1a2eee"
HELP_PANEL_BORDER = "4a4a8a"
HELP_HEADER_SIZE = 36
HELP_NAME_SIZE = 24
HELP_DETAIL_SIZE = 16
HELP_CMD_SIZE = 16
HELP_SECTION_SIZE = 20
HELP_TEXT_COLOR = "ffffffff"
HELP_DIM_COLOR = "aaaaaa"
HELP_GREEN = "44cc44"
HELP_RED = "cc4444"
HELP_ACCENT = "6a6aff"
HELP_LINE_COLOR = "4a4a6a"
HELP_PANEL_PAD = 40
HELP_ROW_PAD = 16
HELP_CORNER_RADIUS = 16
PILL_CORNER_RADIUS = 12
COMBINE_CORNER_RADIUS = 16


def _draw_rounded_rect(c: SkiaCanvas, rect: Rect, radius: float):
    """Draw a rounded rectangle using a Skia path."""
    r = min(radius, rect.width / 2, rect.height / 2)
    path = skia.Path()
    path.add_rounded_rect(rect, r, r, skia.Path.Direction.CW)
    c.draw_path(path)


def _get_saved_windows():
    """Import saved_windows lazily to avoid circular imports."""
    from .recall_state import saved_windows
    from .recall_commands import find_window_by_id
    return saved_windows, find_window_by_id


def _resolve_command_display(stored: str) -> str:
    """Resolve a stored command to its spoken name for display.
    If stored as a shell command, reverse-lookup the spoken name."""
    from .recall_state import ctx
    commands = ctx.lists.get("user.recall_commands", {})
    if stored in commands:
        return stored
    for spoken, shell_cmd in commands.items():
        if shell_cmd == stored:
            return spoken
    return stored


def _resolve_command_shell(stored: str) -> str | None:
    """Resolve a stored command to the actual shell command it will run."""
    from .recall_state import ctx
    commands = ctx.lists.get("user.recall_commands", {})
    if stored in commands:
        return commands[stored]
    for spoken, shell_cmd in commands.items():
        if shell_cmd == stored:
            return shell_cmd
    return stored


def _update_overlay_tag():
    """Set or clear the overlay_visible tag based on active canvases."""
    from .recall_state import overlay_ctx
    if canvas or _status_canvas or _help_canvas or _prompt_canvas:
        overlay_ctx.tags = ["user.recall_overlay_visible"]
    else:
        overlay_ctx.tags = []


def _pills_overlap(a: Rect, b: Rect) -> bool:
    """Check if two pill rects overlap."""
    return (a.x < b.x + b.width and a.x + a.width > b.x and
            a.y < b.y + b.height and a.y + a.height > b.y)


def on_draw(c: SkiaCanvas):
    saved_windows, find_window_by_id = _get_saved_windows()
    screen = ui.main_screen()

    try:
        active_id = ui.active_window().id
    except Exception:
        active_id = None

    missing_y_offset = 80  # start below top bar area

    # First pass: compute pill positions
    pills = []  # [(name, pill_rect, text_x, text_y, bg_color, text_color)]
    for name, info in saved_windows.items():
        window = find_window_by_id(info["id"])

        c.paint.textsize = FONT_SIZE
        text_rect = c.paint.measure_text(name)[1]
        text_w = text_rect.width
        text_h = text_rect.height

        pill_w = text_w + PAD_X * 2
        pill_h = text_h + PAD_Y * 2

        if window is not None:
            rect = window.rect
            if rect.width <= 0 or rect.height <= 0:
                continue

            is_active = (info["id"] == active_id)

            # Center label on window
            center_x = rect.x + rect.width / 2
            center_y = rect.y + rect.height / 2
            pill_x = center_x - pill_w / 2
            pill_y = center_y - pill_h / 2
            text_x = center_x - text_w / 2
            text_y = center_y + text_h / 2
            bg_color = "6a6affcc" if is_active else "000000bb"
            text_color = "ffffffff"
        else:
            is_active = False
            display = f"{name} (not found)"
            c.paint.textsize = FONT_SIZE
            text_rect = c.paint.measure_text(display)[1]
            text_w = text_rect.width
            text_h = text_rect.height
            pill_w = text_w + PAD_X * 2
            pill_h = text_h + PAD_Y * 2

            center_x = screen.rect.x + screen.rect.width / 2
            pill_x = center_x - pill_w / 2
            pill_y = missing_y_offset
            text_x = center_x - text_w / 2
            text_y = missing_y_offset + PAD_Y + text_h
            bg_color = "aa0000cc"
            text_color = "ffffffff"
            name = display
            missing_y_offset += pill_h + MISSING_GAP

        pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)

        # Nudge if overlapping any existing pill
        for _, existing_rect, _, _, _, _ in pills:
            if _pills_overlap(pill_rect, existing_rect):
                # Shift below the existing pill
                pill_y = existing_rect.y + existing_rect.height + MISSING_GAP
                text_y = pill_y + PAD_Y + text_h
                pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)

        pills.append((name, pill_rect, text_x, text_y, bg_color, text_color))

    # Second pass: draw
    for name, pill_rect, text_x, text_y, bg_color, text_color in pills:
        c.paint.style = c.paint.Style.FILL
        c.paint.color = bg_color
        _draw_rounded_rect(c, pill_rect, PILL_CORNER_RADIUS)

        c.paint.style = c.paint.Style.FILL
        c.paint.color = text_color
        c.paint.textsize = FONT_SIZE
        c.draw_text(name, pill_rect.x + PAD_X, text_y)


def show_overlay():
    """Show labels on all saved windows for 5 seconds."""
    global canvas, _hide_job

    # Cancel any pending hide
    if _hide_job:
        cron.cancel(_hide_job)
        _hide_job = None

    # Tear down existing canvas before creating new one
    if canvas:
        canvas.unregister("draw", on_draw)
        canvas.close()
        canvas = None

    saved_windows, _ = _get_saved_windows()
    if not saved_windows:
        return

    screen: Screen = ui.main_screen()
    canvas = Canvas.from_screen(screen)
    canvas.register("draw", on_draw)
    canvas.freeze()

    # Auto-hide after duration
    _hide_job = cron.after(SHOW_DURATION, hide_overlay)
    _update_overlay_tag()


def hide_overlay():
    """Hide and destroy the overlay canvas."""
    global canvas, _hide_job
    if _hide_job:
        cron.cancel(_hide_job)
        _hide_job = None
    if canvas:
        canvas.unregister("draw", on_draw)
        canvas.close()
        canvas = None
    _update_overlay_tag()


# ── Help overlay ──────────────────────────────────────────────────────

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


def _draw_panel_frame(c: SkiaCanvas, rect: Rect):
    """Draw panel background + border."""
    c.paint.style = c.paint.Style.FILL
    c.paint.color = HELP_PANEL_COLOR
    _draw_rounded_rect(c, rect, HELP_CORNER_RADIUS)
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = HELP_PANEL_BORDER
    _draw_rounded_rect(c, rect, HELP_CORNER_RADIUS)
    c.paint.style = c.paint.Style.FILL


def _draw_close_hint(c: SkiaCanvas, panel_x: float, panel_y: float, panel_w: float):
    """Draw the close hint text + X in the top-right of a panel."""
    close_text = '"recall close" or Esc'
    c.paint.textsize = HELP_DETAIL_SIZE
    c.paint.color = HELP_DIM_COLOR
    close_w = c.paint.measure_text(close_text)[1].width
    x_size = 14
    gap = 10
    total_hint_w = close_w + gap + x_size
    close_x = panel_x + panel_w - HELP_PANEL_PAD - total_hint_w
    c.draw_text(close_text, close_x, panel_y + HELP_PANEL_PAD + HELP_DETAIL_SIZE)

    x_x = close_x + close_w + gap
    x_cy = panel_y + HELP_PANEL_PAD + HELP_DETAIL_SIZE / 2
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = HELP_DIM_COLOR
    c.draw_line(x_x, x_cy - x_size / 2, x_x + x_size, x_cy + x_size / 2)
    c.draw_line(x_x, x_cy + x_size / 2, x_x + x_size, x_cy - x_size / 2)
    c.paint.style = c.paint.Style.FILL


# ── Status overlay (saved windows panel) ─────────────────────────────

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

    # Sort: active windows first, then missing
    window_names = sorted(
        saved_windows.keys(),
        key=lambda n: 0 if find_window_by_id(saved_windows[n]["id"]) else 1,
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


# ── Help overlay (commands reference panel) ──────────────────────────

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
    panel_h += HELP_SECTION_SIZE + 16  # "Commands" header + gap
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


def show_status():
    """Show the status overlay with all saved windows."""
    global _status_canvas, _status_hide_job

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
    _update_overlay_tag()


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
    _update_overlay_tag()


def show_help():
    """Show the help overlay with command reference."""
    global _help_canvas, _help_hide_job

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
    _update_overlay_tag()


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
    _update_overlay_tag()


def hide_any():
    """Hide whichever overlay is currently active."""
    hide_overlay()
    hide_status()
    hide_help()
    hide_prompt()


# ── Prompt overlay (used by combine, rename, alias) ──────────────────

_prompt_canvas: Canvas = None
_prompt_hide_job = None
_prompt_title: str = ""
_prompt_subtitle: str = ""
PROMPT_DURATION = "15s"
PROMPT_CORNER_RADIUS = 16


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
    _update_overlay_tag()


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
    _update_overlay_tag()


# ── Flash notification ────────────────────────────────────────────────

_flash_canvas: Canvas = None
_flash_hide_job = None
_flash_message: str = ""
_flash_subtitle: str = ""
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


# ── Window capture highlight ─────────────────────────────────────────

_highlight_canvas: Canvas = None
_highlight_hide_job = None
_highlight_window = None
_highlight_name: str = ""
HIGHLIGHT_DURATION = "800ms"
HIGHLIGHT_COLOR = "6a6aff"
HIGHLIGHT_STROKE = 4
HIGHLIGHT_LABEL_SIZE = 16
HIGHLIGHT_LABEL_PAD_X = 10
HIGHLIGHT_LABEL_PAD_Y = 6


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


_highlight_show_job = None


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


# ── Persistent window highlight ──────────────────────────────────────

_persistent_canvas: Canvas = None
_persistent_window = None
_persistent_name: str = ""
_persistent_last_rect = None
_persistent_poll_job = None

PERSISTENT_COLOR = "6a6aff"
PERSISTENT_ALPHA = "88"
PERSISTENT_STROKE = 2
PERSISTENT_LABEL_SIZE = 13
PERSISTENT_LABEL_PAD_X = 8
PERSISTENT_LABEL_PAD_Y = 4
PERSISTENT_POLL_INTERVAL = "200ms"


def on_draw_persistent(c: SkiaCanvas):
    if not _persistent_window:
        return
    try:
        r = _persistent_window.rect
    except Exception:
        return
    if r.width <= 0 or r.height <= 0:
        return

    # Border around the window
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = PERSISTENT_STROKE
    c.paint.color = PERSISTENT_COLOR + PERSISTENT_ALPHA
    c.draw_rect(Rect(r.x, r.y, r.width, r.height))
    c.paint.style = c.paint.Style.FILL

    # Name label tab — 1/4 from left, above window, rounded top, flat bottom
    if _persistent_name:
        display_name = _persistent_name.title()
        c.paint.textsize = PERSISTENT_LABEL_SIZE
        text_rect = c.paint.measure_text(display_name)[1]
        text_w = text_rect.width
        text_h = text_rect.height

        pill_w = text_w + PERSISTENT_LABEL_PAD_X * 2
        pill_h = text_h + PERSISTENT_LABEL_PAD_Y * 2
        pill_x = r.x + r.width / 4 - pill_w / 2
        pill_y = r.y - pill_h  # above the window, bottom flush with top edge

        # Background — rounded top, straight bottom
        c.paint.color = PERSISTENT_COLOR + "ff"
        rad = 6
        path = skia.Path()
        path.move_to(pill_x, pill_y + rad)
        path.arc_to_with_oval(
            Rect(pill_x, pill_y, rad * 2, rad * 2),
            180, 90, False,
        )
        path.line_to(pill_x + pill_w - rad, pill_y)
        path.arc_to_with_oval(
            Rect(pill_x + pill_w - rad * 2, pill_y, rad * 2, rad * 2),
            270, 90, False,
        )
        path.line_to(pill_x + pill_w, pill_y + pill_h)
        path.line_to(pill_x, pill_y + pill_h)
        path.close()
        c.draw_path(path)

        # Text
        c.paint.color = "ffffffff"
        c.draw_text(display_name, pill_x + PERSISTENT_LABEL_PAD_X, pill_y + PERSISTENT_LABEL_PAD_Y + text_h)


def _persistent_check_geometry():
    """Cron interval callback: re-freeze canvas if the tracked window moved/resized."""
    global _persistent_last_rect
    if not _persistent_window or not _persistent_canvas:
        return
    try:
        r = _persistent_window.rect
    except Exception:
        return
    current = (r.x, r.y, r.width, r.height)
    if current != _persistent_last_rect:
        _persistent_last_rect = current
        _persistent_canvas.freeze()


def show_persistent_highlight(window, name: str):
    """Update the persistent highlight to track the given window."""
    global _persistent_canvas, _persistent_window, _persistent_name
    global _persistent_last_rect, _persistent_poll_job

    _persistent_window = window
    _persistent_name = name

    try:
        r = window.rect
        _persistent_last_rect = (r.x, r.y, r.width, r.height)
    except Exception:
        _persistent_last_rect = None

    # Create canvas if needed
    if not _persistent_canvas:
        screen = ui.main_screen()
        _persistent_canvas = Canvas.from_screen(screen)
        _persistent_canvas.register("draw", on_draw_persistent)

    _persistent_canvas.freeze()

    # Start geometry polling if not already running
    if not _persistent_poll_job:
        _persistent_poll_job = cron.interval(PERSISTENT_POLL_INTERVAL, _persistent_check_geometry)


def hide_persistent_highlight():
    """Destroy the persistent canvas and stop polling entirely (feature toggled off)."""
    global _persistent_canvas, _persistent_window, _persistent_name
    global _persistent_last_rect, _persistent_poll_job

    if _persistent_poll_job:
        cron.cancel(_persistent_poll_job)
        _persistent_poll_job = None
    if _persistent_canvas:
        _persistent_canvas.unregister("draw", on_draw_persistent)
        _persistent_canvas.close()
        _persistent_canvas = None
    _persistent_window = None
    _persistent_name = ""
    _persistent_last_rect = None


def clear_persistent_highlight():
    """Clear the tracked window but keep the canvas alive (non-recall window focused)."""
    global _persistent_window, _persistent_name, _persistent_last_rect
    _persistent_window = None
    _persistent_name = ""
    _persistent_last_rect = None
    if _persistent_canvas:
        _persistent_canvas.freeze()


def rebuild_persistent_canvas():
    """Rebuild the persistent canvas on a new screen (e.g. monitor change)."""
    global _persistent_canvas
    if not _persistent_canvas:
        return
    _persistent_canvas.unregister("draw", on_draw_persistent)
    _persistent_canvas.close()
    screen = ui.main_screen()
    _persistent_canvas = Canvas.from_screen(screen)
    _persistent_canvas.register("draw", on_draw_persistent)
    _persistent_canvas.freeze()
