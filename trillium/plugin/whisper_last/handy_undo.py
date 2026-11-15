"""Handy undo bridge: the Handy analog of whisper_undo.py.

Handy pastes by clipboard, bypassing Talon's dictation pipeline, so `destroy`
had nothing to delete. This watches Handy's history DB directory (WAL commits
land in sibling files) and pushes each new transcription into the same
phrase-history buffer `destroy` consumes, using the same trailing-space
detection as whisper_undo. No new commands or delete logic.
"""

import logging

from talon import actions, app, fs

from . import handy_data
from .trailing_insert import resolve_trailing_insert

WATCH_DIR = handy_data.DB_PATH.parent

# Newest Handy timestamp (unix seconds) already pushed; seeded at startup so a
# reload never replays old dictations.
_last_consumed_ts = 0.0


def _consume_new_recordings():
    global _last_consumed_ts
    for ts, text in handy_data.get_since(_last_consumed_ts):
        trailing = resolve_trailing_insert(text)
        actions.user.add_phrase_to_history(text + trailing)
        _last_consumed_ts = ts
        logging.debug(
            "handy_undo: recorded %d chars at %s", len(text) + len(trailing), ts
        )


def _on_db_change(path: str, flags):
    _consume_new_recordings()


def on_ready():
    global _last_consumed_ts
    latest = handy_data.get_latest()
    _last_consumed_ts = latest[0] if latest else 0.0
    if WATCH_DIR.is_dir():
        fs.watch(str(WATCH_DIR), _on_db_change)
        print(f"[handy_undo] Ready - watching {WATCH_DIR} (baseline {_last_consumed_ts})")
    else:
        print(f"[handy_undo] Handy db dir not found ({WATCH_DIR}); Handy undo inactive")


app.register("ready", on_ready)
