"""Whisper show overlay — recent-transcription picker with DismissibleOverlay lifecycle.

Unlike the activity monitor, the row set only changes when a new recording is
made, so there is no auto-refresh cron: gather() runs once per show(). Picking a
row pastes its transcription and closes the overlay (one-shot), rather than
staying open for a multi-select session the way activity's kill does.
"""

from talon import actions
from talon.skia.canvas import Canvas as SkiaCanvas

from ...utils.overlay_kit import DismissibleOverlay
from ...utils.overlay_selector import overlay_labels
from . import whisper_data
from .whisper_data import WhisperRow
from .whisper_show_draw import draw_panel

# ── Module state ──
_rows: list[WhisperRow] = []


def gather():
    """Load the most recent transcriptions into module state."""
    global _rows
    _rows = whisper_data.get_transcriptions(whisper_data.MAX_ROWS)


def get_rows() -> list[WhisperRow]:
    return _rows


def pick_by_index(n: int) -> tuple[bool, str]:
    """Paste the transcription at 0-based index *n*, then hide the overlay.

    Returns (success, message). Hides the overlay in every path so a pick is
    never a silent no-op. Labels are assigned in row order each gather(), so
    the index from overlay_select maps directly onto _rows.
    """
    if n < 0 or n >= len(_rows):
        return False, f"No transcription for selector {n + 1}"
    text = _rows[n].transcription
    # Close first so the paste lands in the app underneath, not the overlay.
    hide()
    # Defensive: gather() filters empties, but a recording could be edited
    # between gather and pick. Don't paste an empty string.
    if not text:
        return False, "Selected transcription is empty"
    actions.user.paste_transient(text)
    return True, "Pasted transcription"


# ── Drawing callback ──

def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    labels = overlay_labels(len(_rows), mode="letter")
    draw_panel(c, overlay, _rows, labels)


# ── Overlay instance ──

_on_hide_callback = None


def _on_overlay_hide():
    if _on_hide_callback:
        _on_hide_callback()


_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide="30s", on_hide=_on_overlay_hide)


def set_on_hide(callback):
    """Register a callback for when the overlay is dismissed."""
    global _on_hide_callback
    _on_hide_callback = callback


# ── Public API ──

def show():
    gather()
    _overlay.show()


def hide():
    _overlay.hide()


def is_showing() -> bool:
    return _overlay.is_showing
