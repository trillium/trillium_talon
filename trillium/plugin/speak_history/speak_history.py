"""
Speak History - Voice-driven browser for speak history entries

Reads the speak SQLite history database directly (read-only) and presents
paginated entries via overlay. Supports caller filtering and replay.
"""

import json
import os
import subprocess
import sys as _sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from talon import Context, Module, actions, cron

from ...utils.overlay_selector import letter_to_index, shape_to_index
from . import speak_history_overlay as overlay

_SPEAK_LIB = os.path.expanduser("~/code/speak/lib")
if _SPEAK_LIB not in _sys.path:
    _sys.path.insert(0, _SPEAK_LIB)
from speakd.text import split_clauses

mod = Module()

mod.tag("speak_history_active", desc="Speak history overlay is active")
mod.list("speak_history_caller", desc="Caller name mappings for speak history filter")

history_ctx = Context()

SPEAK = "/Users/trilliumsmith/code/speak/bin/speak"
PAGE_SIZE = 8

_env = os.environ.copy()
_env["PATH"] = ":".join(
    [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/Users/trilliumsmith/.local/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
        _env.get("PATH", ""),
    ]
)

_page: int = 0
_caller_filter: str = ""
_entries: list[dict] = []
_total_count: int = 0
_playing_history_id: int | None = None
_playing_clause_idx: int | None = None
_poll_job = None
_selected_shape: str | None = None
_selected_shape_idx: int | None = None
_last_refresh_key: (
    tuple
) = ()  # (entries_ids_tuple, total, playing_history_id, clause_idx) — skip freeze when unchanged
POLL_INTERVAL = "3s"


def _relative_time(iso_str: str) -> str:
    """Format an ISO timestamp as a relative time string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"
    except (ValueError, TypeError):
        return ""


def _fetch_entries(count: int, offset: int) -> tuple[list[dict], int]:
    """Call the speak CLI and return (entries, total). Enriches entries with relative_time."""
    if _caller_filter:
        args = [
            SPEAK,
            "--caller-history",
            _caller_filter,
            str(count),
            "--offset",
            str(offset),
        ]
    else:
        args = [SPEAK, "--history", str(count), "--offset", str(offset)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=2, env=_env)
    data = json.loads(result.stdout)
    entries = data.get("entries", [])
    total = data.get("total", 0)
    for entry in entries:
        entry["relative_time"] = _relative_time(entry.get("spoken_at", ""))
    for entry in entries:
        try:
            entry["clauses"] = split_clauses(entry.get("text", ""))
        except Exception:
            entry["clauses"] = []
    return entries, total


def _fetch_playing_id() -> tuple[int | None, int | None]:
    """Call speak --queue and return (history_id, clause_idx) of currently playing entry, or (None, None)."""
    try:
        result = subprocess.run(
            [SPEAK, "--queue"],
            capture_output=True,
            text=True,
            timeout=0.5,
            env=_env,
        )
        data = json.loads(result.stdout)
        playing = data.get("playing", {})
        return playing.get("history_id"), playing.get("clause_idx")
    except Exception:
        return None, None


def _query_entries() -> tuple[list[dict], int]:
    """Query the speak CLI for the current page and filter."""
    try:
        return _fetch_entries(PAGE_SIZE, _page * PAGE_SIZE)
    except Exception as e:
        print(f"speak_history: query failed: {e}")
        return [], 0


def _refresh():
    """Re-query and update the overlay. Skips canvas freeze when data is unchanged."""
    global _entries, _total_count, _playing_history_id, _playing_clause_idx, _last_refresh_key
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_entries = ex.submit(_query_entries)
        f_playing = ex.submit(_fetch_playing_id)
        (entries, total), (playing_id, clause_idx) = (
            f_entries.result(),
            f_playing.result(),
        )
    refresh_key = (
        tuple(e["id"] for e in entries),
        total,
        playing_id,
        clause_idx,
        _selected_shape,
    )
    if refresh_key == _last_refresh_key:
        return
    _entries, _total_count, _playing_history_id, _playing_clause_idx = (
        entries,
        total,
        playing_id,
        clause_idx,
    )
    _last_refresh_key = refresh_key
    total_pages = max(1, (_total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    overlay.update(
        entries=_entries,
        page=_page,
        total_pages=total_pages,
        total_count=_total_count,
        caller_filter=_caller_filter,
        playing_history_id=_playing_history_id,
        playing_clause_idx=_playing_clause_idx,
        selected_shape=_selected_shape,
        selected_shape_idx=_selected_shape_idx,
    )


def _start_polling():
    global _poll_job
    if _poll_job is None:
        _poll_job = cron.interval(POLL_INTERVAL, _refresh)


def _stop_polling():
    global _poll_job
    if _poll_job:
        cron.cancel(_poll_job)
        _poll_job = None


@mod.action_class
class Actions:
    def speak_history_show(caller: str = ""):
        """Open the speak history overlay, optionally filtered by caller"""
        global _page, _caller_filter
        _page = 0
        _caller_filter = caller
        history_ctx.tags = ["user.speak_history_active"]
        overlay.show()
        _refresh()
        _start_polling()

    def speak_history_stop():
        """Close the speak history overlay"""
        global _page, _caller_filter, _entries, _total_count, _selected_shape, _selected_shape_idx
        _page = 0
        _caller_filter = ""
        _entries = []
        _total_count = 0
        _selected_shape = None
        _selected_shape_idx = None
        _stop_polling()
        history_ctx.tags = []
        overlay.hide()

    def speak_history_next():
        """Go to the next page of history"""
        global _page, _selected_shape, _selected_shape_idx
        total_pages = max(1, (_total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        if _page < total_pages - 1:
            _page += 1
            _selected_shape = None
            _selected_shape_idx = None
            _refresh()

    def speak_history_previous():
        """Go to the previous page of history"""
        global _page, _selected_shape, _selected_shape_idx
        if _page > 0:
            _page -= 1
            _selected_shape = None
            _selected_shape_idx = None
            _refresh()

    def speak_history_replay(row_number: int):
        """Re-speak a history entry by 0-based index on the current page"""
        idx = row_number
        if idx < 0 or idx >= len(_entries):
            return
        row_id = str(_entries[idx]["id"])
        subprocess.Popen(
            [SPEAK, "--replay-id", row_id],
            start_new_session=True,
            env=_env,
        )

    def speak_history_filter(caller: str):
        """Filter history to a specific caller"""
        global _page, _caller_filter
        _page = 0
        _caller_filter = caller
        _refresh()

    def speak_history_clear_filter():
        """Clear the caller filter and show all entries"""
        global _page, _caller_filter
        _page = 0
        _caller_filter = ""
        _refresh()

    def speak_history_pause():
        """Toggle pause/resume on speak playback"""
        subprocess.Popen(
            [SPEAK, "--pause"],
            start_new_session=True,
            env=_env,
        )

    def speak_history_resume():
        """Explicitly resume paused speak playback"""
        subprocess.Popen(
            [SPEAK, "--resume"],
            start_new_session=True,
            env=_env,
        )

    def speak_history_skip():
        """Skip the currently playing speak entry"""
        subprocess.Popen(
            [SPEAK, "--skip"],
            start_new_session=True,
            env=_env,
        )

    def speak_history_kill():
        """Kill all speak audio — skip current and clear queue"""
        subprocess.Popen(
            [SPEAK, "--clear"],
            start_new_session=True,
            env=_env,
        )
        subprocess.Popen(
            [SPEAK, "--skip"],
            start_new_session=True,
            env=_env,
        )

    def speak_history_restart():
        """Restart the speak daemon"""
        subprocess.Popen(
            [SPEAK, "--restart"],
            start_new_session=True,
            env=_env,
        )

    def speak_history_replay_last(count: int):
        """Replay the last N history entries in chronological order"""
        # Short-circuit: if count fits in the current page (already fetched), skip the subprocess
        if count <= len(_entries) and _page == 0:
            entries = _entries[-count:]
        else:
            try:
                entries, _ = _fetch_entries(count, 0)
            except Exception as e:
                print(f"speak_history: replay_last fetch failed: {e}")
                return

        # Reverse so they play oldest-first (chronological order)
        for entry in reversed(entries):
            subprocess.Popen(
                [SPEAK, "--replay-id", str(entry["id"])],
                start_new_session=True,
                env=_env,
            )

    def speak_history_select_shape(shape: str):
        """Select a shape entry — highlights entry and shows clause letters"""
        global _selected_shape, _selected_shape_idx
        idx = shape_to_index(shape)
        if idx < 0 or idx >= len(_entries):
            return
        _selected_shape = shape
        _selected_shape_idx = idx
        _refresh()

    def speak_history_select_clause(letter: str):
        """Play a clause within the currently shape-selected entry"""
        global _selected_shape, _selected_shape_idx
        if _selected_shape_idx is None or _selected_shape_idx >= len(_entries):
            return
        clause_idx = letter_to_index(letter)
        if clause_idx < 0:
            return
        entry = _entries[_selected_shape_idx]
        clauses = entry.get("clauses", [])
        if clause_idx >= len(clauses):
            return
        row_id = str(entry["id"])
        subprocess.Popen(
            [SPEAK, "--replay-id", row_id, "--clause", str(clause_idx)],
            start_new_session=True,
            env=_env,
        )

    def speak_history_shape_clause(shape: str, letter: str):
        """Combined one-breath command: select shape and play clause"""
        global _selected_shape, _selected_shape_idx
        idx = shape_to_index(shape)
        if idx < 0 or idx >= len(_entries):
            return
        _selected_shape = shape
        _selected_shape_idx = idx
        clause_idx = letter_to_index(letter)
        if clause_idx < 0:
            return
        entry = _entries[idx]
        clauses = entry.get("clauses", [])
        if clause_idx >= len(clauses):
            return
        row_id = str(entry["id"])
        subprocess.Popen(
            [SPEAK, "--replay-id", row_id, "--clause", str(clause_idx)],
            start_new_session=True,
            env=_env,
        )
        _refresh()
