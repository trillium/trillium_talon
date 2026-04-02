"""Command History JSONL Schema v2.1

Canonical type definitions for the serialized command history format.
Import these for type-checking consumers of command_history.jsonl.

Usage (Python):
    from trillium.core.on_phrase.command_logger.schema import CommandHistoryEntry
"""

from typing import Optional
from typing_extensions import TypedDict


class WordEntry(TypedDict):
    text: str
    start: Optional[float]
    end: Optional[float]


class CaptureEntry(TypedDict):
    phrase: str
    value: str
    name: Optional[str]


class CommandEntry(TypedDict):
    phrase: str
    rule: Optional[str]
    code: Optional[str]
    path: Optional[str]
    line: Optional[int]
    captures: list[CaptureEntry]


class AppContext(TypedDict, total=False):
    name: str
    bundle: Optional[str]


class WindowContext(TypedDict, total=False):
    title: Optional[str]
    id: Optional[int]


class Context(TypedDict, total=False):
    app: AppContext
    window: WindowContext
    microphone: str
    mode: list[str]
    tags: list[str]
    hostname: Optional[str]


class Metadata(TypedDict):
    success: bool


class SoundInfo(TypedDict, total=False):
    """Present when source is "repeat" or "reverse"."""
    name: Optional[str]          # e.g. "tongue_click", "cmere"
    confidence: Optional[float]  # detection confidence


class CommandHistoryEntry(TypedDict):
    """One line of command_history.jsonl (v2.1).

    Voice and sound entries share the same shape. Sound entries inherit
    phrase and commands from the last voice entry.

    source — the only field a consumer needs to read:
    - "voice"   — user spoke a command
    - "repeat"  — sound triggered a repeat of the last command
    - "reverse" — sound triggered the reverse/opposite of the last command
    """
    version: str            # "2.1"
    action_type: str        # "command"
    source: str             # "voice" | "repeat" | "reverse"
    timestamp: str          # ISO 8601
    phrase: str             # Raw spoken words (same for voice and sound)
    words: list[WordEntry]  # Per-word timing (empty for sound entries)
    commands: list[CommandEntry]  # Per-command breakdown (inherited for sound)
    sound: Optional[SoundInfo]  # Present when source is "repeat" or "reverse"
    context: Context
    metadata: Metadata


# Version prefix for consumers to validate against (startswith check)
SCHEMA_VERSION_PREFIX = "2."
SCHEMA_VERSION = "2.1"
