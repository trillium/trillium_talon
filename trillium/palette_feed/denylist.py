"""Rules a phone must never trigger. Checked against the spoken phrase and the matched rule."""

import re

# `sudo` is this repo's prefix for system-level voice commands (restart talon, wifi, ...).
_PATTERNS = (
    r"\bsudo\b",
    r"\b(restart|quit|exit|kill) talon\b",
    r"\btalon (restart|quit)\b",
    r"\b(shut ?down|shut her down|shutter down|reboot|log ?out)\b",
    r"\bsystem command\b",
    r"\bkill all\b",
)
_COMPILED = tuple(re.compile(p) for p in _PATTERNS)


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def denied_by(*texts: str) -> str | None:
    """Return the pattern that blocks any of `texts`, or None if all are allowed."""
    for text in texts:
        normalized = _normalize(text)
        for pattern in _COMPILED:
            if pattern.search(normalized):
                return pattern.pattern
    return None
