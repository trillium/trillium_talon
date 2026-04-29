"""Talon grammar stubs.

Provides mock types for speech grammar processing:
- Phrase: represents a spoken phrase
- Capture: represents a captured grammar match
"""


class Phrase:
    """A spoken phrase from the speech engine."""

    def __init__(self, words=None):
        self._words = words or []

    def __iter__(self):
        return iter(self._words)

    def __len__(self):
        return len(self._words)

    def __str__(self):
        return " ".join(str(w) for w in self._words)


class Capture:
    """A grammar capture match."""

    def __init__(self, value=None):
        self.value = value

    def __str__(self):
        return str(self.value) if self.value else ""


class vm:
    """Grammar VM types."""

    Phrase = Phrase

    class VMCapture:
        """VM-level capture."""

        def __init__(self, value=None):
            self.value = value
