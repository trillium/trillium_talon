"""Clipboard-based trailing-whitespace detection shared by the dictation-app
undo bridges (whisper_undo for OpenSuperWhisper, handy_undo for Handy).

Both apps paste via the system clipboard, so the clipboard right after a new
history row still holds the exact pasted string, trailing space included.
"""

from talon import actions

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


def resolve_trailing_insert(transcription: str) -> str:
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
