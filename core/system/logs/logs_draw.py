"""Log viewer overlay drawing — layout and rendering for the log viewer UI."""

from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....trillium.utils.overlay_kit import (  # 4 dots: logs -> system -> core -> trillium_talon
    DismissibleOverlay,
    draw_dim_backdrop,
    draw_panel_frame,
    draw_separator,
)
from ....trillium.utils.overlay_selector import overlay_labels
from .logs_data import MAX_ROWS, LogEntry

# ── Colors ──
DIM_BG = "000000cc"
PANEL_BG = "1a1a2eee"
PANEL_BORDER = "4a5a8a"
CORNER_RADIUS = 16
PANEL_PAD = 40
TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
ACCENT = "5ab5a0"
HEADER_COLOR = "ffffffff"
LINE_COLOR = "3a4a6a"

# Level colors
LEVEL_COLORS = {
    "DEBUG": "555577ff",
    "IO": "7ab8d4ff",
    "WARNING": "ffa94dff",
    "ERROR": "ff6b6bff",
}

TIMESTAMP_COLOR = "888899ff"
CATEGORY_COLOR = "8ab4c0ff"
MESSAGE_COLOR = "d0d0e0ff"

# ── Font sizes ──
HEADER_SIZE = 32
SUBTITLE_SIZE = 14
ROW_HEIGHT = 28
FONT_SIZE = 14
HINT_SIZE = 14

# ── Column widths ──
LABEL_COL_W = 40
TIME_COL_W = 80  # HH:MM:SS
LEVEL_COL_W = 50  # 4-char padded level
CAT_COL_W = 110  # category
# message gets the rest

PANEL_W = 900
DETAIL_PANEL_W = 700

# ── Level display labels ──
LEVEL_LABELS = {
    "DEBUG": "DEBG",
    "IO": "IO  ",
    "WARNING": "WARN",
    "ERROR": "ERR ",
}


def _truncate(text: str, c: SkiaCanvas, max_width: float) -> str:
    """Truncate text to fit within max_width, adding ellipsis if needed."""
    if not text:
        return text
    measured = c.paint.measure_text(text)[1].width
    if measured <= max_width:
        return text
    # Binary search for truncation point
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid] + "\u2026"
        w = c.paint.measure_text(candidate)[1].width
        if w <= max_width:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return "\u2026"
    return text[:lo] + "\u2026"


def _format_time(timestamp: str) -> str:
    """Extract HH:MM:SS from a full timestamp string."""
    # timestamp format: "2026-05-17 05:28:52.844"
    parts = timestamp.split(" ")
    if len(parts) >= 2:
        time_part = parts[1]
        # Remove milliseconds
        dot = time_part.find(".")
        if dot >= 0:
            return time_part[:dot]
        return time_part
    return timestamp[:8]


def _word_wrap(text: str, c: SkiaCanvas, max_width: float) -> list[str]:
    """Split text into lines that fit within max_width at current paint settings."""
    if not text:
        return [""]
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
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


def draw_row(
    c: SkiaCanvas,
    entry: LogEntry,
    label: str,
    cx: float,
    cy: float,
    content_w: float,
):
    """Draw a single log entry row at the given y position."""
    col_x = cx

    # Label (selector letter/number)
    c.paint.textsize = FONT_SIZE
    c.paint.color = ACCENT
    c.paint.font.embolden = True
    c.draw_text(label, col_x, cy + FONT_SIZE)
    c.paint.font.embolden = False
    col_x += LABEL_COL_W

    # Timestamp (HH:MM:SS)
    c.paint.color = TIMESTAMP_COLOR
    c.draw_text(_format_time(entry.timestamp), col_x, cy + FONT_SIZE)
    col_x += TIME_COL_W

    # Level (4-char padded)
    level_color = LEVEL_COLORS.get(entry.level, MESSAGE_COLOR)
    c.paint.color = level_color
    c.paint.font.embolden = True
    c.draw_text(LEVEL_LABELS.get(entry.level, entry.level[:4]), col_x, cy + FONT_SIZE)
    c.paint.font.embolden = False
    col_x += LEVEL_COL_W

    # Category
    if entry.category:
        c.paint.color = CATEGORY_COLOR
        cat_display = _truncate(entry.category, c, CAT_COL_W - 8)
        c.draw_text(cat_display, col_x, cy + FONT_SIZE)
    col_x += CAT_COL_W

    # Message (rest of width)
    msg_max_w = content_w - (col_x - cx)
    if msg_max_w > 0:
        c.paint.color = MESSAGE_COLOR
        msg_display = _truncate(entry.message, c, msg_max_w)
        c.draw_text(msg_display, col_x, cy + FONT_SIZE)


def _build_subtitle(
    count: int,
    filter_level: str,
    filter_category: str | None,
    filter_search: str | None,
) -> str:
    """Build the subtitle string showing current filter state."""
    parts = [f"{count} entries"]

    if filter_level == "DEBUG":
        parts.append("level: all")
    else:
        parts.append(f"level: {filter_level}+")

    if filter_category:
        parts.append(f"cat: {filter_category}")

    if filter_search:
        parts.append(f'search: "{filter_search}"')

    return "  \u00b7  ".join(parts)


def draw_panel(
    c: SkiaCanvas,
    overlay: DismissibleOverlay,
    entries: list[LogEntry],
    filter_level: str,
    filter_category: str | None,
    filter_search: str | None,
    labels: list[str] | None = None,
):
    """Draw the full log viewer panel."""
    screen = ui.main_screen()
    sr = screen.rect
    draw_dim_backdrop(c, sr, DIM_BG)

    display_entries = entries[:MAX_ROWS]
    row_count = len(display_entries)
    c.paint.textsize = FONT_SIZE

    if labels is None:
        labels = overlay_labels(len(display_entries), mode="letter")

    panel_w = PANEL_W
    panel_h = (
        PANEL_PAD
        + HEADER_SIZE
        + 8
        + SUBTITLE_SIZE
        + 16
        + ROW_HEIGHT  # column headers
        + ROW_HEIGHT * max(row_count, 1)
        + 16
        + HINT_SIZE
        + PANEL_PAD
    )
    panel_x = sr.x + (sr.width - panel_w) / 2
    panel_y = sr.y + (sr.height - panel_h) / 2
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    overlay.set_panel_rect(panel_rect)
    draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_BG, PANEL_BORDER)

    c.save()
    c.clip_rect(panel_rect)
    cx = panel_x + PANEL_PAD
    cy = panel_y + PANEL_PAD
    content_w = panel_w - PANEL_PAD * 2

    # Header
    c.paint.textsize = HEADER_SIZE
    c.paint.color = HEADER_COLOR
    c.draw_text("Log Viewer", cx, cy + HEADER_SIZE)
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)
    cy += HEADER_SIZE + 8

    # Subtitle
    subtitle = _build_subtitle(
        len(entries), filter_level, filter_category, filter_search
    )
    c.paint.textsize = SUBTITLE_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text(subtitle, cx, cy + SUBTITLE_SIZE)
    cy += SUBTITLE_SIZE + 16

    # Column headers
    col_x = cx
    c.paint.textsize = FONT_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text("#", col_x, cy + FONT_SIZE)
    col_x += LABEL_COL_W
    c.draw_text("TIME", col_x, cy + FONT_SIZE)
    col_x += TIME_COL_W
    c.draw_text("LEVEL", col_x, cy + FONT_SIZE)
    col_x += LEVEL_COL_W
    c.draw_text("CATEGORY", col_x, cy + FONT_SIZE)
    col_x += CAT_COL_W
    c.draw_text("MESSAGE", col_x, cy + FONT_SIZE)
    cy += ROW_HEIGHT
    draw_separator(c, cx, cx + content_w, cy - 8, LINE_COLOR)

    # Data rows
    if row_count == 0:
        c.paint.textsize = FONT_SIZE
        c.paint.color = DIM_COLOR
        c.draw_text("No log entries match current filters.", cx, cy + FONT_SIZE)
    else:
        for i, entry in enumerate(display_entries):
            draw_row(c, entry, labels[i], cx, cy, content_w)
            cy += ROW_HEIGHT

    # Bottom hint
    cy += 8
    c.paint.textsize = HINT_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text('"view <letter>" / "copy <letter>" / "ignore view"', cx, cy + HINT_SIZE)
    c.restore()


def draw_detail_panel(
    c: SkiaCanvas,
    overlay: DismissibleOverlay,
    title: str,
    lines: list[str],
    selectable: bool = False,
):
    """Draw a narrower detail panel centered on screen.

    Renders title at top, word-wrapped lines below. If selectable=True,
    each line gets a letter label for selection.
    """
    screen = ui.main_screen()
    sr = screen.rect
    draw_dim_backdrop(c, sr, DIM_BG)

    panel_w = DETAIL_PANEL_W
    content_w = panel_w - PANEL_PAD * 2
    label_w = LABEL_COL_W if selectable else 0
    wrap_w = content_w - label_w

    # Pre-compute wrapped lines to determine panel height
    c.paint.textsize = FONT_SIZE
    wrapped_blocks: list[list[str]] = []
    for line in lines:
        wrapped = _word_wrap(line, c, wrap_w)
        wrapped_blocks.append(wrapped)

    total_text_lines = sum(len(block) for block in wrapped_blocks)
    # Add spacing between blocks (one extra line gap per block after the first)
    block_gaps = max(len(wrapped_blocks) - 1, 0) * 4

    panel_h = (
        PANEL_PAD
        + HEADER_SIZE
        + 16
        + FONT_SIZE * total_text_lines
        + 4 * max(total_text_lines - 1, 0)
        + block_gaps
        + 16
        + HINT_SIZE
        + PANEL_PAD
    )
    # Clamp to screen
    panel_h = min(panel_h, sr.height - 80)

    panel_x = sr.x + (sr.width - panel_w) / 2
    panel_y = sr.y + (sr.height - panel_h) / 2
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    overlay.set_panel_rect(panel_rect)
    draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_BG, PANEL_BORDER)

    c.save()
    c.clip_rect(panel_rect)
    cx = panel_x + PANEL_PAD
    cy = panel_y + PANEL_PAD

    # Title
    c.paint.textsize = HEADER_SIZE
    c.paint.color = HEADER_COLOR
    c.draw_text(title, cx, cy + HEADER_SIZE)
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)
    cy += HEADER_SIZE + 16

    # Lines
    sel_labels = overlay_labels(len(lines), mode="letter") if selectable else []
    line_h = FONT_SIZE + 4

    for block_idx, block in enumerate(wrapped_blocks):
        if block_idx > 0:
            cy += 4  # gap between blocks

        for sub_idx, sub_line in enumerate(block):
            if cy + FONT_SIZE > panel_y + panel_h - PANEL_PAD:
                break
            c.paint.textsize = FONT_SIZE
            text_x = cx
            # Draw label on first sub-line of each block
            if selectable and sub_idx == 0 and block_idx < len(sel_labels):
                c.paint.color = ACCENT
                c.paint.font.embolden = True
                c.draw_text(sel_labels[block_idx], text_x, cy + FONT_SIZE)
                c.paint.font.embolden = False
                text_x += label_w

            if not selectable:
                text_x = cx
            elif sub_idx > 0:
                text_x = cx + label_w

            c.paint.color = MESSAGE_COLOR
            c.draw_text(sub_line, text_x, cy + FONT_SIZE)
            cy += line_h

    # Close hint
    cy = panel_y + panel_h - PANEL_PAD
    c.paint.textsize = HINT_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text("esc to close", cx, cy + HINT_SIZE)
    c.restore()
