"""Wire parrot repeat/reverse to gaze_ocr disambiguation choices.

When the gaze_ocr disambiguation overlay is up (tag `user.gaze_ocr_disambiguation`):
- pop  (repeat action)  -> selects option #1 (green ring)
- cmere (reverse action) -> selects option #2 (red ring)

The overlay still draws numbers, so `choose <number>` continues to work for
3+ options. This module only owns the parrot integration so the upstream
gaze_ocr fork stays free of trillium-specific plumbing.

The 1-second debounce is opt-in via the repeater's `debounce_s` parameter —
it only affects these two armed overrides, not the global repeat/reverse
behavior. A stray second pop within 1s of the first becomes a no-op instead
of firing on the next disambiguation round.
"""

from talon import Module, actions, cron, registry, scope, speech_system

mod = Module()

_DISAMBIGUATION_TAG = "user.gaze_ocr_disambiguation"
_DEBOUNCE_S = 1.0
_was_active = False


def _disambiguation_active() -> bool:
    try:
        return _DISAMBIGUATION_TAG in (scope.get("tag") or set())
    except Exception:
        return False


def _arm():
    try:
        actions.user.set_next_repeat_action(
            "user", "choose_gaze_ocr_option", [1], _DEBOUNCE_S
        )
        actions.user.set_next_opposite_action(
            "user", "choose_gaze_ocr_option", [2], _DEBOUNCE_S
        )
    except Exception:
        pass


def _clear():
    try:
        actions.user.clear_repeat_overrides()
    except Exception:
        pass


def _on_update_contexts():
    global _was_active
    active = _disambiguation_active()
    if active:
        _arm()
    elif _was_active:
        _clear()
    _was_active = active


def _on_post_phrase(j):
    # The repeater clears overrides on every trackable phrase. Defer to the
    # next tick so this re-arm lands after the repeater's clear.
    if _disambiguation_active():
        cron.after("0ms", _arm)


registry.register("update_contexts", _on_update_contexts)
speech_system.register("post:phrase", _on_post_phrase)
