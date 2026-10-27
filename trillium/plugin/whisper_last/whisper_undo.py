"""OpenSuperWhisper undo bridge.

OpenSuperWhisper auto-pastes transcribed text by clipboard, bypassing Talon's
dictation pipeline, so the text never lands in Talon's phrase history and the
existing `destroy` command has nothing to delete. This module closes that gap —
the OpenSuperWhisper analog of trillium/superwhisper_undo.py.

Unlike SuperWhisper (one meta.json file per recording), OpenSuperWhisper stores
every transcription as a row in ONE growing SQLite database
(~/Library/Application Support/ru.starmel.OpenSuperWhisper/recordings.sqlite).
SQLite in WAL mode commits into sibling -wal/-shm files rather than the main .db
file, so we `fs.watch` the database's PARENT DIRECTORY (a watch on the .sqlite
file alone would miss WAL commits) and, on each change event, re-query
whisper_data for rows newer than a "last consumed" cursor. Each new
transcription is pushed into the same phrase-history buffer `destroy` already
consumes (`actions.user.add_phrase_to_history`). After that the existing
`destroy` (delete last phrase) and `destroy <word>` (clear_back_to_word in
trillium/clear_text_commands.py) commands delete the OpenSuperWhisper insertion
for free — with pure backspaces, so it works in a raw TUI (WezTerm, shells)
where Cmd-Z / ctrl-_ do not.

Cursor column — `timestamp`, not `id`: the `recordings.id` column is a
non-monotonic UUID/BLOB primary key and is useless as a cursor. `timestamp` is
stored as a fixed-width 'YYYY-MM-DD HH:MM:SS.fff' string, which is
lexicographically (hence chronologically) ordered, and is the same column
whisper_data already orders by. It is the direct analog of the template's
numeric `_last_consumed_epoch`.

No double-push on replays: `whisper_last` and the `whisper_show` picker replay a
past transcription with `actions.user.paste_transient(text)`, which inserts NO
new sqlite row. A cursor keyed on new rows therefore never re-sees a replay, so
no special-casing is needed.

No new voice commands and no new delete logic: this only feeds the existing undo
machinery in core/text/phrase_history.py and trillium/clear_text_commands.py.
This file declares no actions/tags/settings, so it needs no talon.Module.
"""

import logging

from talon import actions, app, fs

from . import whisper_data

# --- Trailing whitespace: OpenSuperWhisper adds it INCONSISTENTLY ------------
# OpenSuperWhisper sometimes auto-pastes a trailing space beyond what the
# `transcription` column records, and sometimes doesn't — observed directly
# (destroy left one stray character behind on some dictations but not others).
# The sqlite schema has no column recording the literal as-pasted string, so a
# fixed suffix can never be right for both cases.
#
# Fix: OpenSuperWhisper pastes via the system clipboard, so right after a new
# row lands, the clipboard still holds the exact text it just pasted —
# including any trailing space. We compare it against `transcription` and use
# whichever of ("", " ") actually matches, per row. If the clipboard has since
# changed (something else copied in the meantime) neither matches and we fall
# back to the conservative "" suffix — never worse than the old static behavior.
TRAILING_INSERT_FALLBACK = ""


def _resolve_trailing_insert(transcription: str) -> str:
    """Detect the real trailing insert for one row via the clipboard.

    OpenSuperWhisper pastes from the clipboard, so immediately after a new
    sqlite row appears the clipboard should still equal exactly what was
    pasted. Comparing it to the recorded transcription tells us, per row,
    whether a trailing space was actually inserted — instead of guessing with
    one static suffix for every row.
    """
    try:
        clipboard_text = actions.clip.text()
    except Exception:
        return TRAILING_INSERT_FALLBACK
    if clipboard_text is None:
        return TRAILING_INSERT_FALLBACK
    if clipboard_text == transcription + " ":
        return " "
    if clipboard_text == transcription:
        return ""
    return TRAILING_INSERT_FALLBACK


# -----------------------------------------------------------------------------

# Watch the DB's PARENT directory, not the file itself: SQLite WAL commits land
# in sibling -wal/-shm files, so a watch on the .sqlite file alone would miss
# newly written transcriptions.
WATCH_DIR = whisper_data.DB_PATH.parent

# Newest transcription timestamp already pushed into phrase history. Seeded to
# the newest existing row at startup so a Talon reload never replays old
# transcriptions into the buffer. "" sorts below every real 'YYYY-...' timestamp
# and is used only when the DB is empty or absent, where there is nothing to
# replay anyway. Direct analog of the template's `_last_consumed_epoch = -1`.
_last_consumed_ts = ""


def _consume_new_recordings():
    """Push any not-yet-seen OpenSuperWhisper insertions into phrase history.

    get_transcriptions_since returns rows strictly newer than the cursor, oldest
    first, with empty/in-progress transcriptions already filtered out — so we
    push in dictation order and advance the cursor to the newest as we go. An
    in-progress row (empty transcription) is not returned, so it does not advance
    the cursor; the later write that fills in its text fires another fs event and
    is picked up then.
    """
    global _last_consumed_ts
    for row in whisper_data.get_transcriptions_since(_last_consumed_ts):
        trailing_insert = _resolve_trailing_insert(row.transcription)
        actions.user.add_phrase_to_history(row.transcription + trailing_insert)
        _last_consumed_ts = row.timestamp
        logging.debug(
            "whisper_undo: recorded %d chars from transcription at %s (trailing=%r)",
            len(row.transcription) + len(trailing_insert),
            row.timestamp,
            trailing_insert,
        )


def _on_db_change(path: str, flags):
    """fs.watch callback — a file changed under the OpenSuperWhisper db dir."""
    _consume_new_recordings()


def on_ready():
    """Initialize the cursor and start watching on Talon startup."""
    global _last_consumed_ts
    _last_consumed_ts = whisper_data.get_latest_timestamp() or ""
    if WATCH_DIR.is_dir():
        fs.watch(str(WATCH_DIR), _on_db_change)
        print(
            f"[whisper_undo] Ready - watching {WATCH_DIR} "
            f"(baseline timestamp {_last_consumed_ts!r})"
        )
    else:
        print(
            f"[whisper_undo] OpenSuperWhisper db dir not found ({WATCH_DIR}); "
            "OpenSuperWhisper undo inactive"
        )


app.register("ready", on_ready)
