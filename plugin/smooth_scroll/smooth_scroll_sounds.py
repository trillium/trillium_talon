"""Hiss scrolls down, shh scrolls up, but only right after "demo down" / "demo up".

The last spoken command arms the sounds; any other command disarms them, and so
does 20 s of quiet. Unarmed, hiss and shh keep the default behaviour from
trillium/plugin/parrot/parrot.py, so a stray hiss scrolls nothing.
"""

import time

from talon import Context, actions, speech_system

EXPIRY_S = 20.0  # armed this long after the demo command, then back to normal
DEBOUNCE_S = 0.3  # hiss/shh re-fire faster than this restarts the gesture; ignore it
_DEMO_COMMANDS = {"demo down": "down", "demo up": "up"}  # cmd.trigger text -> direction

ctx = Context()
# More specific than the parrot.py context (same tag), so these overrides win.
ctx.matches = r"""
tag: user.parrot_on
mode: command
"""

_armed_at = None  # monotonic time of the last demo command, None when disarmed
_last_scroll = 0.0


def _on_post_phrase(_phrase):
    global _armed_at
    try:
        cmd, _capture = actions.core.last_command()
    except IndexError:
        return
    trigger = cmd.trigger if cmd else None
    _armed_at = time.monotonic() if trigger in _DEMO_COMMANDS else None


speech_system.register("post:phrase", _on_post_phrase)


def _armed() -> bool:
    return _armed_at is not None and time.monotonic() - _armed_at < EXPIRY_S


def _scroll(direction: str) -> bool:
    """Play the demo scroll if armed and not debounced; False means fall through."""
    global _last_scroll
    if not _armed():
        return False
    now = time.monotonic()
    if now - _last_scroll >= DEBOUNCE_S:
        _last_scroll = now
        actions.user.smooth_scroll_mimic(direction)
    return True


@ctx.action_class("user")
class UserActions:
    def noise_hiss():
        if not _scroll("down"):
            actions.next()

    def noise_shh():
        if not _scroll("up"):
            actions.next()
