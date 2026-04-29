"""Activity overlay drawing — layout and rendering for the process monitor UI."""

from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...trillium.utils.overlay_kit import (
    DismissibleOverlay,
    draw_dim_backdrop,
    draw_panel_frame,
    draw_rounded_rect,
    draw_separator,
)
from ...trillium.utils.overlay_selector import overlay_labels
from .activity_data import ProcessRow, _human_mem

# ── Colors ──
DIM_BG = "000000cc"
PANEL_BG = "1a2e2eee"
PANEL_BORDER = "4a8a7a"
CORNER_RADIUS = 16
PANEL_PAD = 40
TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
ACCENT = "5ab5a0"
PORT_COLOR = "d4a55a"
HEADER_COLOR = "ffffffff"
LINE_COLOR = "3a5a5a"
CPU_HIGH_COLOR = "ff6b6b"
CPU_MED_COLOR = "ffa94d"
MEM_HIGH_COLOR = "ff6b6b"
MEM_MED_COLOR = "c59aff"
HOG_DOT_COLOR = "ff6b6b"
HOG_DOT_RADIUS = 4

# ── Resource hog thresholds ──
CPU_HOG_THRESHOLD = 10.0   # % CPU to flag when sorting by mem
MEM_HOG_THRESHOLD = 500_000  # ~500MB RSS in KB, flag when sorting by cpu

# ── Font sizes ──
HEADER_SIZE = 32
SUBTITLE_SIZE = 14
ROW_HEIGHT = 32
FONT_SIZE = 16
NUM_SIZE = 18
HINT_SIZE = 14

# ── Column widths ──
NUM_COL_W = 40
NAME_COL_W = 200
CPU_COL_W = 80
MEM_COL_W = 80
PORT_COL_W = 120


def cpu_color(cpu: float) -> str:
    if cpu >= 50:
        return CPU_HIGH_COLOR
    elif cpu >= 15:
        return CPU_MED_COLOR
    return TEXT_COLOR


def mem_color(mem_rss: int) -> str:
    if mem_rss >= 2_000_000:  # 2GB+
        return MEM_HIGH_COLOR
    elif mem_rss >= 500_000:  # 500MB+
        return MEM_MED_COLOR
    return TEXT_COLOR


def is_cpu_hog(cpu: float) -> bool:
    return cpu >= CPU_HOG_THRESHOLD


def is_mem_hog(mem_rss: int) -> bool:
    return mem_rss >= MEM_HOG_THRESHOLD


def draw_row(
    c: SkiaCanvas, row: ProcessRow, i: int, label: str,
    cx: float, cy: float, content_w: float,
    killed_index: int | None, sort_mode: str = "cpu",
):
    """Draw a single process row at the given y position."""
    is_killed = (killed_index == i)
    col_x = cx
    # Flag processes that are hogs in the non-sorted dimension
    flag_cpu = sort_mode == "mem" and is_cpu_hog(row.cpu)
    flag_mem = sort_mode == "cpu" and is_mem_hog(row.mem_rss)
    if is_killed:
        kill_rect = Rect(cx - 4, cy - 2, content_w + 8, ROW_HEIGHT)
        c.paint.color = "ff4444"
        c.paint.style = c.paint.Style.FILL
        draw_rounded_rect(c, kill_rect, 4)
        c.paint.style = c.paint.Style.FILL
    # Selector number
    c.paint.textsize = NUM_SIZE
    c.paint.color = "ffffff" if is_killed else ACCENT
    c.paint.font.embolden = True
    c.draw_text(label, col_x, cy + FONT_SIZE)
    c.paint.font.embolden = False
    col_x += NUM_COL_W
    # Process name
    c.paint.textsize = FONT_SIZE
    c.paint.color = "ffffff" if is_killed else TEXT_COLOR
    display_name = row.name[:24] + "\u2026" if len(row.name) > 25 else row.name
    c.draw_text(display_name, col_x, cy + FONT_SIZE)
    col_x += NAME_COL_W
    # CPU% — always color-coded, add hog dot when sorting by mem
    c.paint.color = "ffffff" if is_killed else cpu_color(row.cpu)
    c.draw_text(f"{row.cpu:.1f}%", col_x, cy + FONT_SIZE)
    if flag_cpu and not is_killed:
        _draw_hog_dot(c, col_x - 8, cy + FONT_SIZE / 2 + 2)
    col_x += CPU_COL_W
    # Memory — now color-coded, add hog dot when sorting by cpu
    c.paint.color = "ffffff" if is_killed else mem_color(row.mem_rss)
    c.draw_text(_human_mem(row.mem_rss), col_x, cy + FONT_SIZE)
    if flag_mem and not is_killed:
        _draw_hog_dot(c, col_x - 8, cy + FONT_SIZE / 2 + 2)
    col_x += MEM_COL_W
    # Ports
    if row.ports:
        c.paint.color = "ffffff" if is_killed else PORT_COLOR
        port_strs = [f":{p}" for p in sorted(set(row.ports))[:3]]
        c.draw_text(", ".join(port_strs), col_x, cy + FONT_SIZE)


def _draw_hog_dot(c: SkiaCanvas, x: float, y: float):
    """Draw a small colored dot to flag a resource hog."""
    c.paint.color = HOG_DOT_COLOR
    c.paint.style = c.paint.Style.FILL
    c.draw_circle(x, y, HOG_DOT_RADIUS)


def draw_panel(
    c: SkiaCanvas, overlay: DismissibleOverlay,
    rows: list[ProcessRow], sort_mode: str,
    killed_index: int | None, kill_message: str | None,
):
    """Draw the full activity monitor panel."""
    screen = ui.main_screen()
    sr = screen.rect
    draw_dim_backdrop(c, sr, DIM_BG)
    row_count = len(rows)
    c.paint.textsize = FONT_SIZE

    panel_w = PANEL_PAD * 2 + NUM_COL_W + NAME_COL_W + CPU_COL_W + MEM_COL_W + PORT_COL_W
    panel_h = (
        PANEL_PAD + HEADER_SIZE + 8 + SUBTITLE_SIZE + 16
        + ROW_HEIGHT + ROW_HEIGHT * max(row_count, 1)
        + 16 + HINT_SIZE + PANEL_PAD
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

    # Header
    c.paint.textsize = HEADER_SIZE
    c.paint.color = HEADER_COLOR
    c.draw_text("Activity Monitor", cx, cy + HEADER_SIZE)
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)
    cy += HEADER_SIZE + 8

    # Subtitle
    sort_label = {"cpu": "CPU", "mem": "MEM", "combined": "CPU+MEM"}.get(sort_mode, sort_mode.upper())
    c.paint.textsize = SUBTITLE_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text(
        f'{row_count} processes  \u00b7  sort: {sort_label}  \u00b7  "kill <n>" to SIGTERM',
        cx, cy + SUBTITLE_SIZE,
    )
    cy += SUBTITLE_SIZE + 16

    # Column headers
    col_x = cx
    c.paint.textsize = FONT_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text("#", col_x, cy + FONT_SIZE)
    col_x += NUM_COL_W
    c.draw_text("PROCESS", col_x, cy + FONT_SIZE)
    col_x += NAME_COL_W
    c.draw_text("CPU%", col_x, cy + FONT_SIZE)
    col_x += CPU_COL_W
    c.draw_text("MEM", col_x, cy + FONT_SIZE)
    col_x += MEM_COL_W
    c.draw_text("PORT", col_x, cy + FONT_SIZE)
    cy += ROW_HEIGHT
    draw_separator(c, cx, cx + panel_w - PANEL_PAD * 2, cy - 8, LINE_COLOR)

    # Data rows
    if row_count == 0:
        c.paint.textsize = FONT_SIZE
        c.paint.color = DIM_COLOR
        c.draw_text("No processes found.", cx, cy + FONT_SIZE)
    else:
        content_w = panel_w - PANEL_PAD * 2
        labels = overlay_labels(len(rows))
        for i, row in enumerate(rows):
            draw_row(c, row, i, labels[i], cx, cy, content_w, killed_index, sort_mode)
            cy += ROW_HEIGHT

    # Kill message or bottom hint
    cy += 8
    c.paint.textsize = HINT_SIZE
    if kill_message:
        c.paint.color = CPU_HIGH_COLOR
        c.draw_text(kill_message, cx, cy + HINT_SIZE)
    else:
        c.paint.color = DIM_COLOR
        c.draw_text('"sort cpu" / "sort memory" / "sort hogs" to change sort', cx, cy + HINT_SIZE)
    c.restore()
