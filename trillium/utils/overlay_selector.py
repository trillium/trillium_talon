"""Pluggable overlay row-selection via the `user.overlay_select` capture.

Defines a single Talon capture that accepts both number and letter input
and resolves to a 0-based row index. Panels use `<user.overlay_select>`
in their voice rules instead of raw `<number_small>`.

Also provides `overlay_labels(count)` for consistent label rendering
across all overlay panels, and shape-based selection for speak history.
"""

from talon import Context, Module

mod = Module()
ctx = Context()

_LETTERS = [chr(ord("a") + i) for i in range(26)]

# Hat shapes used as entry labels in speak history (matches cursorless vocabulary)
SHAPES = ["bolt", "cross", "curve", "ex", "eye", "fox", "frame", "hole", "play", "wing"]
_SHAPE_TO_INDEX = {s: i for i, s in enumerate(SHAPES)}

# Talon list for shape selection in speak history
mod.list("speak_history_shape", desc="Hat shape names for speak history entry selection")
ctx.lists["user.speak_history_shape"] = {s: s for s in SHAPES}


@mod.capture(rule="<number_small> | <user.letter>")
def overlay_select(m) -> int:
    """Resolve overlay row selection to a 0-based index.

    Numbers: 1-based spoken -> 0-based index (e.g. "3" -> 2)
    Letters: positional (e.g. "air"/a -> 0, "bat"/b -> 1)
    """
    try:
        return int(m.number_small) - 1
    except AttributeError:
        letter = m.letter
        return ord(letter) - ord("a")


def overlay_labels(count: int, mode: str = "number") -> list[str]:
    """Return display labels for `count` rows.

    mode "number": ["1", "2", "3", ...] (default)
    mode "shape": ["bolt", "cross", "curve", ...]
    mode "letter": ["a", "b", "c", ...]
    """
    if mode == "shape":
        return SHAPES[:count]
    if mode == "letter":
        return _LETTERS[:count]
    return [str(i + 1) for i in range(count)]


def shape_to_index(shape: str) -> int:
    """Convert a shape name to its 0-based index. Returns -1 if not found."""
    return _SHAPE_TO_INDEX.get(shape, -1)


def letter_to_index(letter: str) -> int:
    """Convert a letter to its 0-based index. Returns -1 if not a-z."""
    if len(letter) == 1 and "a" <= letter <= "z":
        return ord(letter) - ord("a")
    return -1
