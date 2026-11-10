"""
SuperWhisper undo bridge.

SuperWhisper inserts transcribed text by clipboard paste, bypassing Talon's
dictation pipeline, so the text never lands in Talon's phrase history and the
existing `destroy` command has nothing to delete. This module closes that gap.

Every completed transcription writes a new directory
`~/Documents/superwhisper/recordings/<epoch>/meta.json` whose `result` field is
the exact inserted text (after replacements/formatting). We `fs.watch` the
recordings directory and, on each new transcription, push `result` into the
same phrase-history buffer `destroy` already consumes
(`actions.user.add_phrase_to_history`). After that, the existing
`destroy` / `restore destroy` commands delete or restore the SuperWhisper
insertion for free — with pure backspaces, so it works in a raw TUI (WezTerm,
shells) where Cmd-Z / ctrl-_ do not.

No new voice commands and no new delete logic: this only feeds the existing
undo machinery in core/text/phrase_history.py and trillium/clear_text_commands.py.
"""

import json
import logging
from pathlib import Path

from talon import Module, actions, app, fs

mod = Module()

RECORDINGS_DIR = Path.home() / "Documents" / "superwhisper" / "recordings"

# --- Trailing-whitespace unknown (needs live calibration) ---------------------
# SuperWhisper *may* paste a trailing space/newline beyond what meta.json.result
# records. If it does, `destroy` (which backspaces len(recorded_text) chars) will
# leave that trailing char behind — an off-by-N. We record `result +
# TRAILING_INSERT`, so the recorded length matches the real insertion.
#
# Default is "" because meta.json.result is documented as the cleaned text that
# actually gets pasted, so no trailing char is the conservative assumption. This
# MUST be confirmed with a keyboard-in-hand calibration (see module report /
# AGENTS): dictate a known phrase into a terminal, say "destroy", and check
# whether exactly the inserted text is removed. If a stray space/newline is left,
# set TRAILING_INSERT to that character (e.g. " " or "\n").
TRAILING_INSERT = ""
# -----------------------------------------------------------------------------

# Highest epoch (recording dir name) already pushed into phrase history. Set to
# the newest existing recording at startup so a Talon reload never replays old
# transcriptions into the buffer.
_last_consumed_epoch = -1


def _epoch_dirs() -> list[int]:
    """Return recording epoch ids (numeric dir names), newest first."""
    if not RECORDINGS_DIR.is_dir():
        return []
    epochs = []
    for child in RECORDINGS_DIR.iterdir():
        if child.is_dir() and child.name.isdigit():
            epochs.append(int(child.name))
    epochs.sort(reverse=True)
    return epochs


def _read_result(epoch: int) -> str | None:
    """Read the `result` string for a recording, or None if not ready/invalid."""
    meta_path = RECORDINGS_DIR / str(epoch) / "meta.json"
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # meta.json may be mid-write; a later fs event will re-trigger us.
        return None
    result = data.get("result")
    if not isinstance(result, str) or not result:
        return None
    return result


def _consume_new_recordings():
    """Push any not-yet-seen SuperWhisper insertions into phrase history."""
    global _last_consumed_epoch
    for epoch in _epoch_dirs():
        if epoch <= _last_consumed_epoch:
            # Sorted newest-first: once we hit a seen epoch, the rest are older.
            break
        result = _read_result(epoch)
        if result is None:
            # Newest dir exists but meta.json isn't ready yet — don't advance the
            # cursor; the write of meta.json will fire another fs event.
            continue
        actions.user.add_phrase_to_history(result + TRAILING_INSERT)
        _last_consumed_epoch = epoch
        logging.debug(
            "superwhisper_undo: recorded %d chars from recording %d",
            len(result) + len(TRAILING_INSERT),
            epoch,
        )


def _on_recordings_change(path: str, flags):
    """fs.watch callback — a file changed under the recordings directory."""
    _consume_new_recordings()


def on_ready():
    """Initialize the cursor and start watching on Talon startup."""
    global _last_consumed_epoch
    epochs = _epoch_dirs()
    _last_consumed_epoch = epochs[0] if epochs else -1
    if RECORDINGS_DIR.is_dir():
        fs.watch(str(RECORDINGS_DIR), _on_recordings_change)
        print(
            f"[superwhisper_undo] Ready - watching {RECORDINGS_DIR} "
            f"(baseline recording {_last_consumed_epoch})"
        )
    else:
        print(
            f"[superwhisper_undo] recordings dir not found ({RECORDINGS_DIR}); "
            "SuperWhisper undo inactive"
        )


app.register("ready", on_ready)
