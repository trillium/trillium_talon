"""Mic selection overlay — shows available microphones with current highlighted.

Supports two layers of exclusion:
  1. Setting-based (user.microphone_excluded) — static, comma-separated substrings
  2. Dynamic (voice commands) — persisted via talon.storage, exact mic names
"""
from talon import Module, actions, settings, storage
from talon.skia.canvas import Canvas as SkiaCanvas

from .microphone_selection_draw import draw_overlay
from ...utils.overlay_kit import DismissibleOverlay

mod = Module()
mod.setting(
    "microphone_excluded",
    type=str,
    default="",
    desc=(
        "Comma-separated list of microphone names to hide from the "
        "mic selection overlay. Substring matching is used, so "
        "'BlackHole' will exclude 'BlackHole 2ch' and 'BlackHole 16ch'."
    ),
)

# Mics always excluded (system entries that are never useful)
_ALWAYS_EXCLUDED = {"None"}

# Dynamic exclusions — persisted across restarts
_STORAGE_KEY = "microphone-selection.dynamic-exclusions"
_dynamic_exclusions: set[str] = set(storage.get(_STORAGE_KEY, []))


def _persist_dynamic():
    storage.set(_STORAGE_KEY, list(_dynamic_exclusions))


def add_dynamic_exclusion(mic_name: str):
    """Exclude a mic by exact name (persisted)."""
    _dynamic_exclusions.add(mic_name)
    _persist_dynamic()


def remove_dynamic_exclusion(mic_name: str):
    """Re-include a previously excluded mic."""
    _dynamic_exclusions.discard(mic_name)
    _persist_dynamic()


def clear_dynamic_exclusions():
    """Remove all dynamic exclusions."""
    _dynamic_exclusions.clear()
    _persist_dynamic()


# ── Exclusion logic ──────────────────────────────────────────


def _get_excluded_substrings() -> list[str]:
    """Parse the user.microphone_excluded setting into substrings."""
    raw = settings.get("user.microphone_excluded") or ""
    return [s.strip() for s in raw.split(",") if s.strip()]


def _is_excluded(mic: str, substrings: list[str]) -> bool:
    """Check if a mic matches any exclusion rule (setting or dynamic)."""
    if mic in _ALWAYS_EXCLUDED:
        return True
    if mic in _dynamic_exclusions:
        return True
    for sub in substrings:
        if sub in mic:
            return True
    return False


def _get_all_mics() -> list[str]:
    """Return all available microphones (no filtering)."""
    try:
        return [m for m in actions.sound.microphones() if m]
    except Exception:
        return []


def _get_mics() -> list[str]:
    """Return available microphones, excluding hidden entries."""
    all_mics = _get_all_mics()
    excluded = _get_excluded_substrings()
    return [m for m in all_mics if not _is_excluded(m, excluded)]


def _get_excluded_mics() -> list[str]:
    """Return mics hidden by exclusion rules (not always-excluded)."""
    all_mics = _get_all_mics()
    excluded_subs = _get_excluded_substrings()
    result = []
    for m in all_mics:
        if m in _ALWAYS_EXCLUDED:
            continue
        if m in _dynamic_exclusions:
            result.append(m)
        elif any(sub in m for sub in excluded_subs):
            result.append(m)
    return result


def _get_active_mic() -> str:
    try:
        return actions.sound.active_microphone()
    except Exception:
        return ""


# ── Overlay lifecycle ────────────────────────────────────────


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    draw_overlay(
        c, overlay,
        mics=_get_mics(),
        excluded=_get_excluded_mics(),
        active=_get_active_mic(),
    )


_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide="10s")

# Cache mic list for selection by number
_cached_mics: list[str] = []


def show():
    """Show mic selection overlay."""
    global _cached_mics
    _cached_mics = _get_mics()
    _overlay.show()


def hide():
    _overlay.hide()


def is_showing() -> bool:
    return _overlay.is_showing


def select(index: int):
    """Select a mic by 0-based index, then dismiss."""
    global _cached_mics
    if not _cached_mics:
        _cached_mics = _get_mics()
    if 0 <= index < len(_cached_mics):
        mic_name = _cached_mics[index]
        actions.sound.set_microphone(mic_name)
        actions.user.sound_microphone_enable_event()
        if _overlay.is_showing:
            _overlay.hide()


def exclude_by_index(index: int):
    """Exclude a mic by its 0-based overlay index."""
    global _cached_mics
    if not _cached_mics:
        _cached_mics = _get_mics()
    if 0 <= index < len(_cached_mics):
        mic_name = _cached_mics[index]
        add_dynamic_exclusion(mic_name)
        _cached_mics = _get_mics()
        if _overlay.is_showing:
            _overlay.show()


def include_by_index(index: int):
    """Re-include an excluded mic by its 0-based position in the excluded list."""
    excluded = _get_excluded_mics()
    if 0 <= index < len(excluded):
        remove_dynamic_exclusion(excluded[index])
        if _overlay.is_showing:
            show()


def reset_exclusions():
    """Remove all dynamic exclusions and refresh."""
    clear_dynamic_exclusions()
    if _overlay.is_showing:
        show()
