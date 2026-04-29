"""Activity overlay — process monitor UI with DismissibleOverlay lifecycle."""

import os
import signal

from talon import cron, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...trillium.utils.overlay_kit import (
    DismissibleOverlay,
    draw_dim_backdrop,
    draw_panel_frame,
    draw_rounded_rect,
    draw_separator,
)
from .activity_data import ProcessRow, _human_mem, _get_processes

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

# ── Module state ──
_rows: list[ProcessRow] = []
_killed_index: int | None = None
_kill_message: str | None = None
_kill_clear_job = None


def gather():
    """Gather fresh process data."""
    global _rows, _killed_index, _kill_message
    _rows = _get_processes()
    _killed_index = None
    _kill_message = None


def get_rows() -> list[ProcessRow]:
    return _rows


def _clear_kill_and_refresh():
    """Clear kill feedback and refresh data."""
    global _killed_index, _kill_message, _kill_clear_job
    _killed_index = None
    _kill_message = None
    _kill_clear_job = None
    gather()
    _overlay.freeze()


def kill_by_index(n: int) -> tuple[bool, str]:
    """Kill the process at row index n (1-based). Returns (success, message)."""
    global _killed_index, _kill_message, _kill_clear_job
    if n < 1 or n > len(_rows):
        return False, f"No process at row {n}"
    row = _rows[n - 1]
    try:
        os.kill(row.pid, signal.SIGTERM)
        msg = f"Killed {row.name} (PID {row.pid})"
        success = True
    except ProcessLookupError:
        msg = f"{row.name} (PID {row.pid}) already gone"
        success = True
    except PermissionError:
        msg = f"Permission denied: {row.name} (PID {row.pid})"
        success = False
    _killed_index = n - 1
    _kill_message = msg
    _overlay.freeze()
    if _kill_clear_job:
        cron.cancel(_kill_clear_job)
    _kill_clear_job = cron.after("1s", _clear_kill_and_refresh)
    return success, msg


# ── Drawing ──

def _cpu_color(cpu: float) -> str:
    if cpu >= 50:
        return CPU_HIGH_COLOR
    elif cpu >= 15:
        return CPU_MED_COLOR
    return TEXT_COLOR


def _draw_row(c: SkiaCanvas, row: ProcessRow, i: int, cx: float, cy: float, content_w: float):
    """Draw a single process row at the given y position."""
    is_killed = (_killed_index == i)
    col_x = cx
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
    c.draw_text(str(i + 1), col_x, cy + FONT_SIZE)
    c.paint.font.embolden = False
    col_x += NUM_COL_W
    # Process name
    c.paint.textsize = FONT_SIZE
    c.paint.color = "ffffff" if is_killed else TEXT_COLOR
    display_name = row.name[:24] + "\u2026" if len(row.name) > 25 else row.name
    c.draw_text(display_name, col_x, cy + FONT_SIZE)
    col_x += NAME_COL_W
    # CPU%
    c.paint.color = "ffffff" if is_killed else _cpu_color(row.cpu)
    c.draw_text(f"{row.cpu:.1f}%", col_x, cy + FONT_SIZE)
    col_x += CPU_COL_W
    # Memory
    c.paint.color = "ffffff" if is_killed else TEXT_COLOR
    c.draw_text(_human_mem(row.mem_rss), col_x, cy + FONT_SIZE)
    col_x += MEM_COL_W
    # Ports
    if row.ports:
        c.paint.color = "ffffff" if is_killed else PORT_COLOR
        port_strs = [f":{p}" for p in sorted(set(row.ports))[:3]]
        c.draw_text(", ".join(port_strs), col_x, cy + FONT_SIZE)


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    screen = ui.main_screen()
    sr = screen.rect
    draw_dim_backdrop(c, sr, DIM_BG)
    row_count = len(_rows)
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
    c.paint.textsize = SUBTITLE_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text(f'{row_count} processes  \u00b7  "activity close" or esc to dismiss  \u00b7  "kill <n>" to SIGTERM', cx, cy + SUBTITLE_SIZE)
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
        for i, row in enumerate(_rows):
            _draw_row(c, row, i, cx, cy, content_w)
            cy += ROW_HEIGHT

    # Kill message or bottom hint
    cy += 8
    c.paint.textsize = HINT_SIZE
    if _kill_message:
        c.paint.color = CPU_HIGH_COLOR
        c.draw_text(_kill_message, cx, cy + HINT_SIZE)
    else:
        c.paint.color = DIM_COLOR
        c.draw_text('"refresh" to update', cx, cy + HINT_SIZE)
    c.restore()


_on_hide_callback = None
_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide="30s", on_hide=lambda: _on_hide_callback and _on_hide_callback())


def set_on_hide(callback):
    """Register a callback for when the overlay is dismissed."""
    global _on_hide_callback
    _on_hide_callback = callback


def show():
    gather()
    _overlay.show()

def hide():
    _overlay.hide()

def refresh():
    gather()
    _overlay.freeze()

def is_showing() -> bool:
    return _overlay.is_showing
