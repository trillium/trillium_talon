"""Keep a hot-reloaded parrot_integration from running two ParrotSystems.

Talon re-executes parrot_integration.py on save but never tears down the old
ParrotSystem (it owns a live audio stream). Both then detect every noise and
dispatch it, so each parrot(...) trigger ran twice a few ms apart: a pop that
should repeat/submit also fired a second time and could land in the dictation
tool. The previous system is parked on `builtins` (it survives the re-exec),
its delegate is swapped for one that matches nothing, and its stream is stopped
when the API allows.
"""

import builtins
import logging

from talon.debug import log_exception
from talon.experimental.parrot import ParrotDelegate, ParrotFrame

_KEY = "_trillium_parrot_system"


class SilentDelegate(ParrotDelegate):
    """Delegate for a superseded ParrotSystem: matches nothing, so it never fires."""

    def set_class_names(self, classes: set[str]) -> None:
        pass

    def power_threshold(self, power: float) -> bool:
        return False

    def pattern_match(self, frame: ParrotFrame) -> set[str]:
        return set()


def retire_previous_system() -> bool:
    """Silence the ParrotSystem left over from before a reload; True if one existed."""
    prev = getattr(builtins, _KEY, None)
    if prev is None:
        return False
    try:
        prev.delegate = SilentDelegate()
    except Exception:
        log_exception("[parrot] could not silence previous ParrotSystem delegate")
    stream = getattr(prev, "stream", None)
    for name in ("stop", "close"):
        fn = getattr(stream, name, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
    logging.info("[parrot] retired previous ParrotSystem from before reload")
    return True


def remember_system(system) -> None:
    """Park the live system so the next reload can retire it."""
    setattr(builtins, _KEY, system)
