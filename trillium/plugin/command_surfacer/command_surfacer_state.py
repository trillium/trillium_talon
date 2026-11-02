"""Command Surfacer State -- pure state container, no Talon imports.

Stores a list of (phrase, description) tuples and tracks the current
index for rotation through the command list.
"""

import random


class CommandSurfacerState:
    """Holds the command list and current display index."""

    def __init__(self):
        self._commands: list[tuple[str, str]] = []
        self._index: int = 0

    def load_commands(self, commands_dict: dict):
        """Accept a dict of {phrase: description} and store as sorted tuples."""
        self._commands = sorted(commands_dict.items())
        if self._commands:
            # Start at a random position so it's not always the same on boot
            self._index = random.randint(0, len(self._commands) - 1)
        else:
            self._index = 0

    def current_command(self) -> tuple[str, str] | None:
        """Return the current (phrase, description) or None if empty."""
        if not self._commands:
            return None
        return self._commands[self._index]

    def next_command(self):
        """Advance to the next command, wrapping around."""
        if not self._commands:
            return
        self._index = (self._index + 1) % len(self._commands)

    def count(self) -> int:
        """Total number of commands loaded."""
        return len(self._commands)

    def index(self) -> int:
        """Current display index (0-based)."""
        return self._index
