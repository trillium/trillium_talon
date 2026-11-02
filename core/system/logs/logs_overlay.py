"""Logs overlay — log viewer UI with DismissibleOverlay lifecycle."""

import json
import os

from talon import cron
from talon.skia.canvas import Canvas as SkiaCanvas

from ....trillium.utils.overlay_kit import (
    DismissibleOverlay,  # 4 dots: logs -> system -> core -> trillium_talon
)
from .logs_data import MAX_ROWS, LogEntry, filter_entries, parse_talon_log
from .logs_draw import draw_detail_panel, draw_panel

# ── Log file path ──
_LOG_PATH = "/Users/trilliumsmith/.talon/talon.log"
_IGNORE_PATH = os.path.join(os.path.dirname(__file__), "ignore_patterns.json")

# ── Module state ──
_entries: list[LogEntry] = []
_visible_entries: list[LogEntry] = []
_filter_level: str = "IO"  # default: hide DEBUG spam
_filter_category: str | None = None
_filter_search: str | None = None
_ignore_patterns: list[str] = []
_auto_refresh_job = None

# ── Detail overlay state ──
_detail_entry: LogEntry | None = None
_detail_mode: str = "entry"  # "entry" | "ignores"
_detail_on_hide_callback = None


def _load_ignore_patterns():
    global _ignore_patterns
    try:
        with open(_IGNORE_PATH, "r") as f:
            _ignore_patterns = json.load(f)
    except (OSError, json.JSONDecodeError):
        _ignore_patterns = []


def _save_ignore_patterns():
    try:
        with open(_IGNORE_PATH, "w") as f:
            json.dump(_ignore_patterns, f, indent=2)
    except OSError:
        pass


_load_ignore_patterns()


def gather():
    """Gather fresh log data and apply filters."""
    global _entries, _visible_entries
    _entries = parse_talon_log(_LOG_PATH)
    _visible_entries = filter_entries(
        _entries,
        level_min=_filter_level,
        category=_filter_category,
        search=_filter_search,
        ignore_patterns=_ignore_patterns if _ignore_patterns else None,
    )


def get_visible_entries() -> list[LogEntry]:
    return _visible_entries


def get_filter_level() -> str:
    return _filter_level


def get_filter_category() -> str | None:
    return _filter_category


def get_filter_search() -> str | None:
    return _filter_search


def set_filter_level(level: str):
    """Set minimum log level filter and refresh."""
    global _filter_level
    _filter_level = level.upper()
    gather()
    _overlay.freeze()


def set_filter_category(cat: str | None):
    """Set category filter and refresh."""
    global _filter_category
    _filter_category = cat
    gather()
    _overlay.freeze()


def set_filter_search(query: str | None):
    """Set search filter and refresh."""
    global _filter_search
    _filter_search = query
    gather()
    _overlay.freeze()


def add_ignore(pattern: str):
    """Add a substring to the persistent ignore list."""
    global _ignore_patterns
    pattern = pattern.strip()
    if pattern and pattern not in _ignore_patterns:
        _ignore_patterns.append(pattern)
        _save_ignore_patterns()
    gather()
    _overlay.freeze()


def ignore_by_index(n: int):
    """Add the message of the nth visible entry to the ignore list."""
    if 0 <= n < len(_visible_entries):
        add_ignore(_visible_entries[n].message)


def clear_ignores():
    """Remove all ignore patterns."""
    global _ignore_patterns
    _ignore_patterns = []
    _save_ignore_patterns()
    gather()
    _overlay.freeze()


def get_ignore_patterns() -> list[str]:
    return list(_ignore_patterns)


def clear_filters():
    """Reset all filters to defaults."""
    global _filter_level, _filter_category, _filter_search
    _filter_level = "IO"
    _filter_category = None
    _filter_search = None
    gather()
    _overlay.freeze()


def _auto_refresh_tick():
    """Cron callback: refresh data while overlay is visible."""
    if _overlay.is_showing:
        gather()
        _overlay.freeze()


# ── Main panel drawing callback ──


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    draw_panel(
        c,
        overlay,
        _visible_entries,
        _filter_level,
        _filter_category,
        _filter_search,
    )


# ── Main overlay instance ──

_on_hide_callback = None


def _on_overlay_hide():
    _stop_auto_refresh()
    if _on_hide_callback:
        _on_hide_callback()


_overlay = DismissibleOverlay(
    on_draw=_on_draw, auto_hide="60s", on_hide=_on_overlay_hide
)


def set_on_hide(callback):
    """Register a callback for when the overlay is dismissed."""
    global _on_hide_callback
    _on_hide_callback = callback


# ── Detail overlay drawing callback ──


def _on_detail_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    if _detail_mode == "entry" and _detail_entry is not None:
        header = f"{_detail_entry.timestamp}  {_detail_entry.level}"
        if _detail_entry.category:
            header += f"  [{_detail_entry.category}]"
        lines = [header, _detail_entry.message]
        for cl in _detail_entry.continuation_lines:
            lines.append(cl)
        draw_detail_panel(c, overlay, "Log Entry", lines, selectable=False)
    elif _detail_mode == "ignores":
        lines = list(_ignore_patterns) if _ignore_patterns else ["(no ignore patterns)"]
        draw_detail_panel(
            c, overlay, "Ignored Patterns", lines, selectable=bool(_ignore_patterns)
        )


def _on_detail_hide():
    if _detail_on_hide_callback:
        _detail_on_hide_callback()


_detail_overlay = DismissibleOverlay(
    on_draw=_on_detail_draw, auto_hide=None, on_hide=_on_detail_hide
)


def set_detail_on_hide(callback):
    """Register a callback for when the detail overlay is dismissed."""
    global _detail_on_hide_callback
    _detail_on_hide_callback = callback


def view_by_index(n: int):
    """Show full detail for the nth visible entry."""
    global _detail_entry, _detail_mode
    if 0 <= n < len(_visible_entries):
        _detail_entry = _visible_entries[n]
        _detail_mode = "entry"
        _detail_overlay.show()


def view_ignores():
    """Show the ignore patterns list in the detail overlay."""
    global _detail_mode
    _detail_mode = "ignores"
    _detail_overlay.show()


def close_detail():
    """Close the detail overlay."""
    _detail_overlay.hide()


def get_entry_for_copy(n: int) -> LogEntry | None:
    """Return the nth visible entry if valid, else None."""
    if 0 <= n < len(_visible_entries):
        return _visible_entries[n]
    return None


def get_entries_for_copy_range(start: int, count: int) -> list[LogEntry]:
    """Return up to `count` visible entries starting at index `start`."""
    end = min(start + count, len(_visible_entries))
    return _visible_entries[start:end]


def remove_ignore_by_index(n: int):
    """Remove the ignore pattern at index n."""
    global _ignore_patterns
    if 0 <= n < len(_ignore_patterns):
        _ignore_patterns.pop(n)
        _save_ignore_patterns()
        gather()
        _overlay.freeze()
        if _detail_overlay.is_showing and _detail_mode == "ignores":
            _detail_overlay.freeze()


def is_detail_showing() -> bool:
    """Return whether the detail overlay is currently visible."""
    return _detail_overlay.is_showing


def get_detail_mode() -> str:
    """Return the current detail overlay mode."""
    return _detail_mode


# ── Auto-refresh ──


def _start_auto_refresh():
    global _auto_refresh_job
    if _auto_refresh_job is None:
        _auto_refresh_job = cron.interval("2s", _auto_refresh_tick)


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
    if _detail_overlay.is_showing:
        _detail_overlay.hide()
    _overlay.hide()


def refresh():
    gather()
    _overlay.freeze()


def is_showing() -> bool:
    return _overlay.is_showing
