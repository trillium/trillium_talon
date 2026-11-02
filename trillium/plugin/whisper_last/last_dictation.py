"""Pick the most recent dictation across Whisper and Handy.

Pure logic, no Talon imports. Each source is a callable returning
(unix_seconds, text) or None, so tests can inject fakes.
"""

import calendar
import time
from typing import Callable

from . import handy_data, whisper_data

Source = Callable[[], "tuple[float, str] | None"]


def _whisper_timestamp_to_unix(ts: str) -> float | None:
    """OpenSuperWhisper stores 'YYYY-MM-DD HH:MM:SS.fff' (assumed UTC, GRDB default)."""
    try:
        whole, _, frac = ts.partition(".")
        base = calendar.timegm(time.strptime(whole, "%Y-%m-%d %H:%M:%S"))
        return base + (float(f"0.{frac}") if frac else 0.0)
    except ValueError:
        return None


def whisper_source() -> "tuple[float, str] | None":
    """Newest Whisper recording, with the original behaviour: its text must be non-empty."""
    text = whisper_data.get_latest_transcription()
    ts = whisper_data.get_latest_timestamp()
    if not text or not ts:
        return None
    unix = _whisper_timestamp_to_unix(ts)
    return (unix, text) if unix is not None else None


def handy_source() -> "tuple[float, str] | None":
    return handy_data.get_latest()


def latest_dictation(
    whisper: Source = whisper_source, handy: Source = handy_source
) -> str | None:
    """Return the newest dictation text across sources; Whisper wins ties."""
    candidates = [c for c in (whisper(), handy()) if c]
    if not candidates:
        return None
    best = candidates[0]
    for c in candidates[1:]:
        if c[0] > best[0]:
            best = c
    return best[1]
