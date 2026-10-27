"""Whisper data access — read-only queries against OpenSuperWhisper's SQLite DB.

Pure data layer with no Talon imports, shared by whisper_last (paste the
latest transcription) and the whisper_show overlay panel (list recent ones).
"""

import sqlite3
from pathlib import Path

DB_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "ru.starmel.OpenSuperWhisper"
    / "recordings.sqlite"
)

MAX_ROWS = 12


class WhisperRow:
    __slots__ = ("id", "timestamp", "transcription")

    def __init__(self, id: int, timestamp: str, transcription: str):
        self.id = id
        self.timestamp = timestamp
        self.transcription = transcription


def _query(sql: str, params: tuple) -> list[tuple]:
    """Run a read-only query, returning raw rows or [] on any failure.

    Opens the DB with mode=ro so a missing file, a locked DB, or a schema
    surprise surfaces as an empty result the UI can render, rather than
    raising up into a Talon action.
    """
    if not DB_PATH.exists():
        return []
    conn = None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if conn is not None:
            conn.close()


def get_transcriptions(limit: int = MAX_ROWS) -> list[WhisperRow]:
    """Return up to *limit* most recent non-empty transcriptions, newest first.

    Empty/in-progress recordings are filtered out so every listed row is a
    real transcription that can be pasted.
    """
    rows = _query(
        "SELECT id, timestamp, transcription FROM recordings "
        "WHERE transcription IS NOT NULL AND transcription != '' "
        "ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return [WhisperRow(r[0], r[1] or "", r[2] or "") for r in rows]


def get_latest_transcription() -> str | None:
    """Return the single most recent transcription text, or None.

    Mirrors the original whisper_last behavior exactly: take the most recent
    recording and return its transcription only if it has one.
    """
    rows = _query(
        "SELECT transcription FROM recordings ORDER BY timestamp DESC LIMIT 1",
        (),
    )
    if rows and rows[0][0]:
        return rows[0][0]
    return None


def get_latest_timestamp() -> str | None:
    """Return the newest recording's timestamp string, or None if DB empty/absent.

    Used by the undo bridge (whisper_undo) to seed its "last consumed" cursor at
    startup, so a Talon reload never replays existing transcriptions into phrase
    history. Uses `timestamp` (not `id`): the `id` column is a non-monotonic
    UUID/BLOB primary key, while `timestamp` is a fixed-width
    'YYYY-MM-DD HH:MM:SS.fff' string that is lexicographically (hence
    chronologically) ordered.
    """
    rows = _query("SELECT MAX(timestamp) FROM recordings", ())
    if rows and rows[0][0]:
        return rows[0][0]
    return None


def get_transcriptions_since(cursor: str) -> list[WhisperRow]:
    """Return non-empty transcriptions strictly newer than *cursor*, oldest first.

    *cursor* is a 'YYYY-MM-DD HH:MM:SS.fff' timestamp string. Because that format
    is fixed-width and zero-padded, a lexicographic '>' comparison is exactly a
    chronological one. Rows are returned oldest-first so a caller replaying
    several new transcriptions processes them in dictation order.

    Empty/in-progress recordings (transcription IS NULL or '') are filtered out,
    matching get_transcriptions, so an in-progress row does not advance a
    caller's cursor before its text exists.
    """
    rows = _query(
        "SELECT id, timestamp, transcription FROM recordings "
        "WHERE transcription IS NOT NULL AND transcription != '' "
        "AND timestamp > ? "
        "ORDER BY timestamp ASC",
        (cursor,),
    )
    return [WhisperRow(r[0], r[1] or "", r[2] or "") for r in rows]


def short_time(timestamp: str) -> str:
    """Format an 'YYYY-MM-DD HH:MM:SS.fff' timestamp as 'HH:MM'.

    Falls back gracefully if the stored format is unexpected.
    """
    parts = timestamp.split(" ")
    if len(parts) == 2:
        hms = parts[1].split(":")
        if len(hms) >= 2:
            return f"{hms[0]}:{hms[1]}"
    return timestamp[:5] if timestamp else "?"
