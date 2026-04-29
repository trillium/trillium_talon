"""Activity overlay — process monitor UI with DismissibleOverlay lifecycle."""

import os
import signal

from talon import cron
from talon.skia.canvas import Canvas as SkiaCanvas

from ...trillium.utils.overlay_kit import DismissibleOverlay
from .activity_data import ProcessRow, _get_processes
from .activity_draw import draw_panel

# ── Module state ──
_rows: list[ProcessRow] = []
_killed_index: int | None = None
_kill_message: str | None = None
_kill_clear_job = None
_sort_mode: str = "cpu"  # "cpu", "mem", or "combined"
_auto_refresh_job = None


def gather():
    """Gather fresh process data."""
    global _rows, _killed_index, _kill_message
    _rows = _get_processes(sort_by=_sort_mode)
    _killed_index = None
    _kill_message = None


def get_rows() -> list[ProcessRow]:
    return _rows


def get_sort_mode() -> str:
    return _sort_mode


def set_sort_mode(mode: str):
    """Set sort mode to 'cpu', 'mem', or 'combined' and refresh."""
    global _sort_mode
    _sort_mode = mode
    gather()
    _overlay.freeze()


def _auto_refresh_tick():
    """Cron callback: refresh data while overlay is visible."""
    if _overlay.is_showing and _killed_index is None:
        gather()
        _overlay.freeze()


def _clear_kill_and_refresh():
    """Clear kill feedback and refresh data."""
    global _killed_index, _kill_message, _kill_clear_job
    _killed_index = None
    _kill_message = None
    _kill_clear_job = None
    gather()
    _overlay.freeze()


def kill_by_index(n: int) -> tuple[bool, str]:
    """Kill the process at row index n (0-based). Returns (success, message)."""
    global _killed_index, _kill_message, _kill_clear_job
    if n < 0 or n >= len(_rows):
        return False, f"No process at row {n + 1}"
    row = _rows[n]
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
    _killed_index = n
    _kill_message = msg
    _overlay.freeze()
    if _kill_clear_job:
        cron.cancel(_kill_clear_job)
    _kill_clear_job = cron.after("1s", _clear_kill_and_refresh)
    return success, msg


# ── Drawing callback ──

def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    draw_panel(c, overlay, _rows, _sort_mode, _killed_index, _kill_message)


# ── Overlay instance ──

_on_hide_callback = None


def _on_overlay_hide():
    _stop_auto_refresh()
    if _on_hide_callback:
        _on_hide_callback()


_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide="30s", on_hide=_on_overlay_hide)


def set_on_hide(callback):
    """Register a callback for when the overlay is dismissed."""
    global _on_hide_callback
    _on_hide_callback = callback


# ── Auto-refresh ──

def _start_auto_refresh():
    global _auto_refresh_job
    if _auto_refresh_job is None:
        _auto_refresh_job = cron.interval("1s", _auto_refresh_tick)


def _stop_auto_refresh():
    global _auto_refresh_job
    if _auto_refresh_job:
        cron.cancel(_auto_refresh_job)
        _auto_refresh_job = None


# ── Public API ──

def show():
    gather()
    _overlay.show()
    _start_auto_refresh()

def hide():
    _stop_auto_refresh()
    _overlay.hide()

def refresh():
    gather()
    _overlay.freeze()

def is_showing() -> bool:
    return _overlay.is_showing
