"""
Speak History Overlay - Persistent canvas showing paginated history entries

Full-screen dimmed backdrop with two panels: a main content panel showing
history entries, and a smaller command reference panel to the right.
Reuses the speak_review teal/amber palette.
"""

from talon import ui
from talon.canvas import Canvas, MouseEvent
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...utils.overlay_kit import draw_close_hint, draw_dim_backdrop, draw_panel_frame, draw_separator

_canvas: Canvas = None
_main_rect: Rect = None
_cmd_rect: Rect = None

# ── Color palette (same teal / amber as speak_review) ──

DIM_BG = "000000cc"
PANEL_COLOR = "1a2e2eee"
PANEL_BORDER = "4a8a7a"
CORNER_RADIUS = 16
PANEL_PAD = 40
CMD_PAD = 24  # tighter padding for command panel

TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
ACCENT = "5ab5a0"
SECTION_COLOR = "8abfa5"
LINE_COLOR = "3a5a5a"

# ── Font sizes ──

HEADER_SIZE = 36
SUBTITLE_SIZE = 16
ROW_NUM_SIZE = 16
CALLER_SIZE = 16
TIME_SIZE = 14
ENTRY_TEXT_SIZE = 16
HINT_CMD_SIZE = 16
HINT_DETAIL_SIZE = 16
CMD_HEADER_SIZE = 20

ROW_PAD = 12
ENTRY_GAP = 8
PANEL_GAP = 16  # gap between main and command panels

# ── State ──

_entries: list[dict] = []
_page: int = 0
_total_pages: int = 0
_total_count: int = 0
_caller_filter: str = ""

HINTS = [
    ('"next"', "next page"),
    ('"previous"', "previous page"),
    ('"replay <number>"', "re-speak entry"),
    ('"replay last <number>"', "re-speak last N"),
    ('"skip"', "skip audio"),
    ('"spoken sudo kill"', "stop all audio"),
    ('"spoken sudo restart"', "restart daemon"),
    ('"show <caller>"', "filter by caller"),
    ('"show all"', "clear filter"),
    ('"spoken close"', "close"),
]

TEXT_INDENT = 16
LINE_HEIGHT = ENTRY_TEXT_SIZE + 4




def _wrap_text(c: SkiaCanvas, text: str, max_width: float) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = current + " " + word
        w = c.paint.measure_text(candidate)[1].width
        if w <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _entry_text_height(line_count: int) -> float:
    return line_count * LINE_HEIGHT


def _calc_cmd_panel_size(c: SkiaCanvas) -> tuple[float, float]:
    """Calculate the command panel width and height."""
    # Measure widest hint row
    max_cmd_w = 0
    max_desc_w = 0
    c.paint.textsize = HINT_CMD_SIZE
    for cmd, desc in HINTS:
        cmd_w = c.paint.measure_text(cmd)[1].width
        desc_w = c.paint.measure_text(desc)[1].width
        max_cmd_w = max(max_cmd_w, cmd_w)
        max_desc_w = max(max_desc_w, desc_w)

    cmd_col_gap = 12
    w = CMD_PAD * 2 + max_cmd_w + cmd_col_gap + max_desc_w

    h = CMD_PAD
    h += CMD_HEADER_SIZE + 12  # "Commands" header + gap
    h += len(HINTS) * (HINT_CMD_SIZE + 8)
    h += CMD_PAD

    return w, h


def _draw_cmd_panel(c: SkiaCanvas, rect: Rect):
    """Draw the command reference panel."""
    draw_panel_frame(c, rect, CORNER_RADIUS, PANEL_COLOR, PANEL_BORDER)

    c.save()
    c.clip_rect(rect)

    cx = rect.x + CMD_PAD
    cy = rect.y + CMD_PAD

    # Header
    c.paint.textsize = CMD_HEADER_SIZE
    c.paint.color = SECTION_COLOR
    c.draw_text("Commands", cx, cy + CMD_HEADER_SIZE)
    cy += CMD_HEADER_SIZE + 12

    # Measure cmd column width for alignment
    max_cmd_w = 0
    c.paint.textsize = HINT_CMD_SIZE
    for cmd, _ in HINTS:
        w = c.paint.measure_text(cmd)[1].width
        max_cmd_w = max(max_cmd_w, w)
    cmd_col_w = max_cmd_w + 12

    for cmd, desc in HINTS:
        c.paint.textsize = HINT_CMD_SIZE
        c.paint.color = TEXT_COLOR
        c.draw_text(cmd, cx, cy + HINT_CMD_SIZE)
        c.paint.color = DIM_COLOR
        c.draw_text(desc, cx + cmd_col_w, cy + HINT_CMD_SIZE)
        cy += HINT_CMD_SIZE + 8

    c.restore()


def _on_draw(c: SkiaCanvas):
    screen = ui.main_screen()
    sr = screen.rect

    # Full-screen dim backdrop
    draw_dim_backdrop(c, sr, DIM_BG)

    entry_count = len(_entries)

    # Calculate command panel size first
    cmd_w, cmd_h = _calc_cmd_panel_size(c)

    # Main panel sizing
    main_w = sr.width * 0.50
    content_w = main_w - PANEL_PAD * 2
    text_wrap_w = content_w - TEXT_INDENT

    # Pre-wrap all entry texts
    c.paint.textsize = ENTRY_TEXT_SIZE
    wrapped_entries: list[list[str]] = []
    for entry in _entries:
        lines = _wrap_text(c, entry.get("text", ""), text_wrap_w)
        wrapped_entries.append(lines)

    # Calculate main panel height (no hints now)
    main_h = PANEL_PAD
    main_h += HEADER_SIZE + 8
    main_h += SUBTITLE_SIZE + 16

    if entry_count == 0:
        main_h += ENTRY_TEXT_SIZE + ROW_PAD
    else:
        for lines in wrapped_entries:
            main_h += ROW_NUM_SIZE + ENTRY_GAP
            main_h += _entry_text_height(len(lines))
            main_h += ROW_PAD + 1 + ROW_PAD

    main_h += PANEL_PAD

    if main_h > sr.height - 40:
        main_h = sr.height - 40

    # Position both panels centered as a group
    total_w = main_w + PANEL_GAP + cmd_w
    group_x = sr.x + (sr.width - total_w) / 2

    main_x = group_x
    main_y = sr.y + (sr.height - main_h) / 2

    cmd_x = group_x + main_w + PANEL_GAP
    cmd_y = sr.y + (sr.height - cmd_h) / 2

    # ── Draw main panel ──
    global _main_rect, _cmd_rect
    main_rect = Rect(main_x, main_y, main_w, main_h)
    _main_rect = main_rect
    draw_panel_frame(c, main_rect, CORNER_RADIUS, PANEL_COLOR, PANEL_BORDER)

    c.save()
    c.clip_rect(main_rect)

    cx = main_x + PANEL_PAD
    cy = main_y + PANEL_PAD

    # Header
    c.paint.textsize = HEADER_SIZE
    c.paint.color = TEXT_COLOR
    c.draw_text("Speak History", cx, cy + HEADER_SIZE)

    draw_close_hint(c, '"spoken close"', HINT_DETAIL_SIZE, DIM_COLOR, main_x, main_y, main_w, PANEL_PAD)
    cy += HEADER_SIZE + 8

    # Subtitle
    c.paint.textsize = SUBTITLE_SIZE
    c.paint.color = DIM_COLOR
    parts = []
    if _caller_filter:
        parts.append(f"caller: {_caller_filter}")
    parts.append(f"{_total_count} entries")
    if _total_pages > 1:
        parts.append(f"page {_page + 1}/{_total_pages}")
    c.draw_text("  \u00b7  ".join(parts), cx, cy + SUBTITLE_SIZE)
    cy += SUBTITLE_SIZE + 16

    # Entry rows
    if entry_count == 0:
        c.paint.textsize = ENTRY_TEXT_SIZE
        c.paint.color = DIM_COLOR
        c.draw_text("No entries found.", cx, cy + ENTRY_TEXT_SIZE)
    else:
        for i, entry in enumerate(_entries):
            row_num = i + 1
            lines = wrapped_entries[i]

            c.paint.textsize = ROW_NUM_SIZE
            c.paint.color = SECTION_COLOR
            num_text = f"{row_num}."
            c.draw_text(num_text, cx, cy + ROW_NUM_SIZE)
            num_w = c.paint.measure_text(num_text)[1].width + 8

            c.paint.color = ACCENT
            caller_text = entry.get("caller", "") or ""
            c.draw_text(caller_text, cx + num_w, cy + ROW_NUM_SIZE)

            c.paint.textsize = TIME_SIZE
            c.paint.color = DIM_COLOR
            time_text = entry.get("relative_time", "")
            time_w = c.paint.measure_text(time_text)[1].width
            c.draw_text(time_text, cx + content_w - time_w, cy + ROW_NUM_SIZE)

            cy += ROW_NUM_SIZE + ENTRY_GAP

            c.paint.textsize = ENTRY_TEXT_SIZE
            c.paint.color = TEXT_COLOR
            for line in lines:
                c.draw_text(line, cx + TEXT_INDENT, cy + ENTRY_TEXT_SIZE)
                cy += LINE_HEIGHT

            cy += ROW_PAD

            draw_separator(c, cx, cx + content_w, cy, LINE_COLOR)
            cy += ROW_PAD

    c.restore()

    # ── Draw command panel ──
    cmd_rect = Rect(cmd_x, cmd_y, cmd_w, cmd_h)
    _cmd_rect = cmd_rect
    _draw_cmd_panel(c, cmd_rect)


def update(
    entries: list[dict],
    page: int,
    total_pages: int,
    total_count: int,
    caller_filter: str,
):
    """Update overlay state and re-freeze the canvas."""
    global _entries, _page, _total_pages, _total_count, _caller_filter
    _entries = entries
    _page = page
    _total_pages = total_pages
    _total_count = total_count
    _caller_filter = caller_filter
    if _canvas:
        _canvas.freeze()


def _on_mouse(e: MouseEvent):
    """Dismiss overlay when clicking outside both panels."""
    if e.event == "mousedown" and e.button == 0:
        in_main = _main_rect and _main_rect.contains(e.gpos)
        in_cmd = _cmd_rect and _cmd_rect.contains(e.gpos)
        if not in_main and not in_cmd:
            hide()


def show():
    """Create and show the overlay canvas."""
    global _canvas
    if _canvas:
        hide()
    screen: Screen = ui.main_screen()
    _canvas = Canvas.from_screen(screen)
    _canvas.blocks_mouse = True
    _canvas.register("draw", _on_draw)
    _canvas.register("mouse", _on_mouse)
    _canvas.freeze()


def hide():
    """Destroy the overlay canvas."""
    global _canvas
    if _canvas:
        _canvas.unregister("draw", _on_draw)
        _canvas.unregister("mouse", _on_mouse)
        _canvas.close()
        _canvas = None
