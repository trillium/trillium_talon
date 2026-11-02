"""Handy data access — read-only queries against Handy's history SQLite DB.

Pure data layer with no Talon imports. Handy stores `timestamp` as unix
seconds (UTC) in `transcription_history`.
"""

import sqlite3
from pathlib import Path

DB_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "com.pais.handy"
    / "history.db"
)


def get_latest(db_path: Path | None = None) -> tuple[float, str] | None:
    """Return (unix_seconds, text) of Handy's newest non-empty dictation, or None.

    Opens the DB with mode=ro; a missing file, locked DB or schema surprise
    yields None so the caller falls back to Whisper.
    """
    path = db_path or DB_PATH
    if not path.exists():
        return None
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT timestamp, transcription_text FROM transcription_history "
            "WHERE transcription_text IS NOT NULL AND transcription_text != '' "
            "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        if conn is not None:
            conn.close()
    if not row:
        return None
    return float(row[0]), row[1]
