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


class SoundSource(TypedDict, total=False):
    """Present when source starts with "sound_"."""
    action: str                  # "repeat" or "reverse"
    confidence: Optional[float]  # detection confidence


class CommandHistoryEntry(TypedDict):
    """One line of command_history.jsonl (v2.1).

    Voice and sound entries share the same shape. Sound entries inherit
    phrase and commands from the last voice entry.

    source values:
    - "voice"              — spoken command
    - "sound_tongue_click" — parrot tongue click (repeat)
    - "sound_cmere"        — parrot cmere sound (reverse)
    """
    version: str            # "2.1"
    action_type: str        # "command"
    source: str             # "voice" | "sound_{name}"
    timestamp: str          # ISO 8601
    phrase: str             # Raw spoken words (same for voice and sound)
    words: list[WordEntry]  # Per-word timing (empty for sound entries)
    commands: list[CommandEntry]  # Per-command breakdown (inherited for sound)
    sound: Optional[SoundSource]  # Present when source starts with "sound_"
    context: Context
    metadata: Metadata


# Version prefix for consumers to validate against (startswith check)
SCHEMA_VERSION_PREFIX = "2."
SCHEMA_VERSION = "2.1"
