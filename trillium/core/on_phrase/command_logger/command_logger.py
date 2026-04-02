"""Command Logger v2.1 — Logs structured command data from AnalyzedPhrase.

Writes append-only JSONL to ~/.talon/recordings/command_history.jsonl
Also writes per-command JSON files to ~/.talon/recordings/commands/

Voice and sound-triggered entries share the same shape. Sound entries
inherit the phrase and commands from the last voice entry so consumers
see equivalent records regardless of input source.
"""

from datetime import datetime
from pathlib import Path
import json
import re

from talon import actions, scope, ui

from ..analyze_phrase.types import AnalyzedPhrase
from .schema import SCHEMA_VERSION

# Only log in these modes
_LOGGABLE_MODES = {"command", "dictation"}

COMMANDS_RECORDINGS_DIR = Path.home() / ".talon" / "recordings" / "commands"
COMMANDS_JSONL = Path.home() / ".talon" / "recordings" / "command_history.jsonl"

# Last voice entry data — sound-triggered entries inherit from this
_last_voice_phrase = ""
_last_voice_commands = []


def get_safe_microphone():
    try:
        return actions.sound.active_microphone()
    except Exception:
        return "unknown"


def get_context_data():
    """Gather context information about the current state."""
    context = {
        "app": {},
        "window": {},
        "microphone": get_safe_microphone(),
        "mode": [],
        "tags": [],
    }

    try:
        active_app = ui.active_app()
        context["app"] = {
            "name": active_app.name,
            "bundle": active_app.bundle if hasattr(active_app, "bundle") else None,
        }
    except Exception:
        pass

    try:
        active_window = ui.active_window()
        context["window"] = {
            "title": active_window.title if hasattr(active_window, "title") else None,
            "id": active_window.id if hasattr(active_window, "id") else None,
        }
    except Exception:
        pass

    try:
        current_mode = scope.get("mode")
        if current_mode:
            context["mode"] = list(current_mode) if isinstance(current_mode, set) else current_mode
    except Exception:
        pass

    try:
        current_tags = scope.get("tag")
        if current_tags:
            context["tags"] = list(current_tags) if isinstance(current_tags, set) else current_tags
    except Exception:
        pass

    try:
        context["hostname"] = actions.user.talon_get_hostname()
    except Exception:
        context["hostname"] = None

    return context


def _command_name_for_filename(phrase: str) -> str:
    """Convert spoken phrase to snake_case for filename."""
    if not phrase:
        return "unknown"
    cleaned = re.sub(r"[^\w\s]", "", phrase)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("_").lower()
    if len(cleaned) > 50:
        cleaned = cleaned[:50]
    return cleaned if cleaned else "unknown"


def _build_commands(analyzed: AnalyzedPhrase) -> list[dict]:
    """Build serializable command entries from an AnalyzedPhrase."""
    commands = []
    for cmd in analyzed.commands:
        commands.append({
            "phrase": cmd.phrase,
            "rule": cmd.rule,
            "code": cmd.code,
            "path": cmd.path,
            "line": cmd.line,
            "captures": [
                {"phrase": cap.phrase, "value": str(cap.value), "name": cap.name}
                for cap in cmd.captures
            ],
        })
    return commands


def _write_jsonl(payload: dict):
    """Append a payload to the JSONL file."""
    with open(COMMANDS_JSONL, "a") as f:
        f.write(json.dumps(payload, default=str) + "\n")


def log_analyzed_phrase(analyzed: AnalyzedPhrase):
    """Log an analyzed phrase to JSONL and per-file JSON."""
    global _last_voice_phrase, _last_voice_commands
    try:
        modes = scope.get("mode", set())
        if not (_LOGGABLE_MODES & set(modes)):
            return

        if not analyzed.commands:
            return

        timestamp = datetime.now()
        commands = _build_commands(analyzed)

        # Store for sound-triggered entries to inherit
        _last_voice_phrase = analyzed.phrase
        _last_voice_commands = commands

        payload = {
            "version": SCHEMA_VERSION,
            "action_type": "command",
            "source": "voice",
            "timestamp": timestamp.isoformat(),
            "phrase": analyzed.phrase,
            "words": [{"text": w.text, "start": w.start, "end": w.end} for w in analyzed.words],
            "commands": commands,
            "context": get_context_data(),
            "metadata": {
                "success": True,
            },
        }

        # Write per-file JSON
        COMMANDS_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        command_name = _command_name_for_filename(analyzed.phrase)
        timestamp_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S-%f")
        filename = f"{command_name}__{timestamp_str}.json"
        filepath = COMMANDS_RECORDINGS_DIR / filename
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2, default=str)

        _write_jsonl(payload)

    except Exception:
        pass


def log_parrot_command(
    command_trigger: str,
    display: str = "",
    sound: str = "",
    action: str = "",
    confidence: float = None,
):
    """Log a sound-triggered action to JSONL.

    Inherits phrase and commands from the last voice entry so the record
    is equivalent to a voice command. Source encodes the sound name
    (e.g. "sound_tongue_click", "sound_cmere").

    Args:
        command_trigger: The command rule being repeated/reversed
        display: Human-readable form of the command (fallback)
        sound: Sound name (e.g. "tongue_click", "cmere")
        action: What the sound did ("repeat" or "reverse")
        confidence: Detection confidence score
    """
    try:
        modes = scope.get("mode", set())
        if not (_LOGGABLE_MODES & set(modes)):
            return

        timestamp = datetime.now()

        # Use last voice entry's phrase/commands, fall back to trigger
        phrase_text = _last_voice_phrase or display or command_trigger
        commands = _last_voice_commands if _last_voice_commands else [{
            "phrase": display or command_trigger,
            "rule": command_trigger,
            "code": None,
            "path": None,
            "line": None,
            "captures": [],
        }]

        source = f"sound_{sound}" if sound else "sound"

        payload = {
            "version": SCHEMA_VERSION,
            "action_type": "command",
            "source": source,
            "timestamp": timestamp.isoformat(),
            "phrase": phrase_text,
            "words": [],
            "commands": commands,
            "sound": {
                "action": action,
                "confidence": confidence,
            },
            "context": get_context_data(),
            "metadata": {
                "success": True,
            },
        }
        _write_jsonl(payload)
    except Exception:
        pass
