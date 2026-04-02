"""Command History JSONL Schema v2.0

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


class ParrotSource(TypedDict, total=False):
    """Present when the entry was triggered by a parrot sound, not speech."""
    sound: str              # e.g. "tongue_click", "cmere"
    action: str             # "repeat" or "reverse"
    confidence: Optional[float]  # parrot detection confidence


class CommandHistoryEntry(TypedDict):
    """One line of command_history.jsonl (v2.0).

    Key differences from v1.x:
    - `phrase` is a top-level string (the raw spoken words), not {words, text}
    - `commands` is an array of CommandEntry (per-command breakdown), not a single `command` object
    - `words` has per-word timing data (start/end from speech engine)
    - v1 fields `command.trigger`, `command.display`, `opposite`, `capture` are removed
    - `source` distinguishes voice commands from parrot-triggered actions
    """
    version: str            # "2.0"
    action_type: str        # "command"
    source: str             # "voice" | "parrot"
    timestamp: str          # ISO 8601
    phrase: str             # Raw spoken words (voice), or repeated command display (parrot)
    words: list[WordEntry]  # Per-word with optional timing (empty for parrot)
    commands: list[CommandEntry]  # Per-command breakdown
    parrot: Optional[ParrotSource]  # Present when source="parrot"
    context: Context
    metadata: Metadata


# Version prefix for consumers to validate against
# Version prefix for consumers to validate against (startswith check)
SCHEMA_VERSION_PREFIX = "2."
SCHEMA_VERSION = "2.1"
