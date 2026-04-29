"""Pluggable overlay row-selection via the `user.overlay_select` capture.

Defines a single Talon capture that accepts both number and letter input
and resolves to a 0-based row index. Panels use `<user.overlay_select>`
in their voice rules instead of raw `<number_small>`.

Also provides `overlay_labels(count)` for consistent label rendering
across all overlay panels.
"""

from talon import Module

mod = Module()

_LETTERS = [chr(ord("a") + i) for i in range(26)]


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

    mode "number": ["1", "2", "3", ...]
    mode "letter": ["a", "b", "c", ...]
    """
    if mode == "letter":
        return _LETTERS[:count]
    return [str(i + 1) for i in range(count)]
