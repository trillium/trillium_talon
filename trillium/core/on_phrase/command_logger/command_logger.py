"""Command Logger v2 — Logs structured command data from AnalyzedPhrase.

Schema version 2.0 — captures raw spoken words per command.

Writes append-only JSONL to ~/.talon/recordings/command_history.jsonl
Also writes per-command JSON files to ~/.talon/recordings/commands/
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


def log_analyzed_phrase(analyzed: AnalyzedPhrase):
    """Log an analyzed phrase to JSONL and per-file JSON."""
    try:
        modes = scope.get("mode", set())
        if not (_LOGGABLE_MODES & set(modes)):
            return

        if not analyzed.commands:
            return

        timestamp = datetime.now()
        context = get_context_data()

        # Build per-command entries
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

        payload = {
            "version": SCHEMA_VERSION,
            "action_type": "command",
            "source": "voice",
            "timestamp": timestamp.isoformat(),
            "phrase": analyzed.phrase,
            "words": [{"text": w.text, "start": w.start, "end": w.end} for w in analyzed.words],
            "commands": commands,
            "context": context,
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

        # Append to JSONL
        with open(COMMANDS_JSONL, "a") as f:
            f.write(json.dumps(payload, default=str) + "\n")

    except Exception:
        pass


def log_parrot_command(
    command_trigger: str,
    display: str = "",
    sound: str = "",
    action: str = "",
    confidence: float = None,
):
    """Log a parrot-triggered action to JSONL.

    Args:
        command_trigger: The command rule being repeated/reversed
        display: Human-readable form of the command
        sound: Parrot sound name (e.g. "tongue_click", "cmere")
        action: What the sound did ("repeat" or "reverse")
        confidence: Parrot detection confidence score
    """
    try:
        modes = scope.get("mode", set())
        if not (_LOGGABLE_MODES & set(modes)):
            return

        timestamp = datetime.now()
        phrase_text = display or command_trigger

        parrot_data = {}
        if sound:
            parrot_data["sound"] = sound
        if action:
            parrot_data["action"] = action
        if confidence is not None:
            parrot_data["confidence"] = confidence

        payload = {
            "version": SCHEMA_VERSION,
            "action_type": "command",
            "source": "parrot",
            "timestamp": timestamp.isoformat(),
            "phrase": phrase_text,
            "words": [],
            "commands": [{
                "phrase": phrase_text,
                "rule": command_trigger if command_trigger != phrase_text else None,
                "code": None,
                "path": None,
                "line": None,
                "captures": [],
            }],
            "parrot": parrot_data if parrot_data else None,
            "context": get_context_data(),
            "metadata": {
                "success": True,
            },
        }
        with open(COMMANDS_JSONL, "a") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
