"""Activity overlay — process monitor UI with DismissibleOverlay lifecycle."""

import os
import signal
import string

from talon import cron, storage
from talon.skia.canvas import Canvas as SkiaCanvas

from ...trillium.utils.overlay_kit import DismissibleOverlay
from .activity_data import ProcessRow, _get_processes
from .activity_draw import draw_panel

# ── Module state ──
_rows: list[ProcessRow] = []
_killed_index: int | None = None
_kill_message: str | None = None
_kill_clear_job = None
_sort_mode: str = storage.get("activity-sort-mode", "cpu")  # "cpu", "mem", or "combined"
_auto_refresh_job = None

# ── Stable letter selectors ──
_LETTER_POOL = list(string.ascii_lowercase)
_pid_to_letter: dict[int, str] = {}


def _assign_letters(rows: list[ProcessRow]):
    """Assign stable letters to PIDs, recycling when processes disappear."""
    global _pid_to_letter
    current_pids = {r.pid for r in rows}
    # Remove letters for dead PIDs
    _pid_to_letter = {
        pid: letter for pid, letter in _pid_to_letter.items()
        if pid in current_pids
    }
    # Assign letters to new PIDs
    used = set(_pid_to_letter.values())
    for r in rows:
        if r.pid not in _pid_to_letter:
            for letter in _LETTER_POOL:
                if letter not in used:
                    _pid_to_letter[r.pid] = letter
                    used.add(letter)
                    break


def get_row_labels() -> list[str]:
    """Return the letter label for each row, in row order."""
    return [_pid_to_letter.get(r.pid, "?") for r in _rows]


def gather():
    """Gather fresh process data."""
    global _rows, _killed_index, _kill_message
    _rows = _get_processes(sort_by=_sort_mode)
    _assign_letters(_rows)
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
    storage.set("activity-sort-mode", mode)
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
    """Kill the process selected by letter (n = 0-based letter index).

    Resolves the letter back to the correct row via PID mapping,
    so stable selectors work even after sort/reorder.
    """
    global _killed_index, _kill_message, _kill_clear_job
    target_letter = chr(ord("a") + n) if 0 <= n < 26 else None
    row = None
    row_index = None
    if target_letter:
        for i, r in enumerate(_rows):
            if _pid_to_letter.get(r.pid) == target_letter:
                row = r
                row_index = i
                break
    if row is None:
        label = target_letter or str(n + 1)
        return False, f"No process for selector '{label}'"
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
    _killed_index = row_index
    _kill_message = msg
    _overlay.freeze()
    if _kill_clear_job:
        cron.cancel(_kill_clear_job)
    _kill_clear_job = cron.after("1s", _clear_kill_and_refresh)
    return success, msg


# ── Drawing callback ──


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    labels = get_row_labels()
    draw_panel(c, overlay, _rows, _sort_mode, _killed_index, _kill_message, labels)


# ── Overlay instance ──

_on_hide_callback = None


def _on_overlay_hide():
    _stop_auto_refresh()
    if _on_hide_callback:
        _on_hide_callback()


_overlay = DismissibleOverlay(
    on_draw=_on_draw, auto_hide="30s", on_hide=_on_overlay_hide
)


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
