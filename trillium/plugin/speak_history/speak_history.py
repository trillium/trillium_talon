"""
Speak History - Voice-driven browser for speak history entries

Reads the speak SQLite history database directly (read-only) and presents
paginated entries via overlay. Supports caller filtering and replay.
"""

import os
import sqlite3
import subprocess
from datetime import datetime, timezone

from talon import Module, Context, actions, cron

from . import speak_history_overlay as overlay

mod = Module()

mod.tag("speak_history_active", desc="Speak history overlay is active")
mod.list("speak_history_caller", desc="Caller name mappings for speak history filter")

history_ctx = Context()

SPEAK = "/Users/trilliumsmith/code/speak/bin/speak"
DB_PATH = f"/tmp/speak-{os.environ.get('USER', 'trilliumsmith')}-history.db"
PAGE_SIZE = 8

_env = os.environ.copy()
_env["PATH"] = ":".join([
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/Users/trilliumsmith/.local/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
    _env.get("PATH", ""),
])

_page: int = 0
_caller_filter: str = ""
_entries: list[dict] = []
_total_count: int = 0
_poll_job = None
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


def _query_entries() -> tuple[list[dict], int]:
    """Query the history database for the current page and filter."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError:
        return [], 0

    try:
        if _caller_filter:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM history WHERE caller = ?",
                (_caller_filter,),
            ).fetchone()
            total = count_row[0]

            rows = conn.execute(
                "SELECT id, text, spoken_at, caller FROM history "
                "WHERE caller = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (_caller_filter, PAGE_SIZE, _page * PAGE_SIZE),
            ).fetchall()
        else:
            count_row = conn.execute("SELECT COUNT(*) FROM history").fetchone()
            total = count_row[0]

            rows = conn.execute(
                "SELECT id, text, spoken_at, caller FROM history "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (PAGE_SIZE, _page * PAGE_SIZE),
            ).fetchall()

        entries = [
            {
                "id": row["id"],
                "text": row["text"],
                "caller": row["caller"],
                "relative_time": _relative_time(row["spoken_at"]),
            }
            for row in rows
        ]
        return entries, total
    finally:
        conn.close()


def _refresh():
    """Re-query and update the overlay."""
    global _entries, _total_count
    _entries, _total_count = _query_entries()
    total_pages = max(1, (_total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    overlay.update(
        entries=_entries,
        page=_page,
        total_pages=total_pages,
        total_count=_total_count,
        caller_filter=_caller_filter,
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
        global _page, _caller_filter, _entries, _total_count
        _page = 0
        _caller_filter = ""
        _entries = []
        _total_count = 0
        _stop_polling()
        history_ctx.tags = []
        overlay.hide()

    def speak_history_next():
        """Go to the next page of history"""
        global _page
        total_pages = max(1, (_total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        if _page < total_pages - 1:
            _page += 1
            _refresh()

    def speak_history_previous():
        """Go to the previous page of history"""
        global _page
        if _page > 0:
            _page -= 1
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
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.OperationalError:
            return

        try:
            if _caller_filter:
                rows = conn.execute(
                    "SELECT id FROM history WHERE caller = ? "
                    "ORDER BY id DESC LIMIT ?",
                    (_caller_filter, count),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM history ORDER BY id DESC LIMIT ?",
                    (count,),
                ).fetchall()
        finally:
            conn.close()

        # Reverse so they play oldest-first (chronological order)
        for row in reversed(rows):
            subprocess.Popen(
                [SPEAK, "--replay-id", str(row["id"])],
                start_new_session=True,
                env=_env,
            )
