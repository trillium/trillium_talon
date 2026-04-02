"""
Command Logger - Logs metadata for every Talon command executed

Schema version 1.2 - added hostname to context

Creates a JSON file for each command in ~/.talon/recordings/commands/
This data is never cleaned up - it's a permanent record of Talon usage.
"""

from talon import actions, ui, scope, speech_system
from datetime import datetime
from pathlib import Path
import json
import re

# Modes where commands should be logged
_LOGGABLE_MODES = {"command", "dictation"}


COMMANDS_RECORDINGS_DIR = Path.home() / ".talon" / "recordings" / "commands"
COMMANDS_JSONL = Path.home() / ".talon" / "recordings" / "command_history.jsonl"

# Dedup: skip logging when last_command() hasn't changed
_last_logged_trigger = ""
_last_logged_timestamp = ""

# Schema version - bump when format changes
SCHEMA_VERSION = "1.2"


def get_safe_microphone():
    """Get the active microphone name safely"""
    try:
        return actions.sound.active_microphone()
    except Exception:
        return "unknown"


def get_context_data():
    """Gather context information about the current state"""
    context = {
        "app": {},
        "window": {},
        "microphone": get_safe_microphone(),
        "mode": [],
        "tags": [],
    }

    # Get app info
    try:
        active_app = ui.active_app()
        context["app"] = {
            "name": active_app.name,
            "bundle": active_app.bundle if hasattr(active_app, "bundle") else None,
        }
    except Exception:
        pass

    # Get window info
    try:
        active_window = ui.active_window()
        context["window"] = {
            "title": active_window.title if hasattr(active_window, "title") else None,
            "id": active_window.id if hasattr(active_window, "id") else None,
        }
    except Exception:
        pass

    # Get current mode
    try:
        current_mode = scope.get("mode")
        if current_mode:
            context["mode"] = list(current_mode) if isinstance(current_mode, set) else current_mode
    except Exception:
        pass

    # Get active tags
    try:
        current_tags = scope.get("tag")
        if current_tags:
            context["tags"] = list(current_tags) if isinstance(current_tags, set) else current_tags
    except Exception:
        pass

    # Get hostname
    try:
        context["hostname"] = actions.user.talon_get_hostname()
    except Exception:
        context["hostname"] = None

    return context


def get_phrase_words():
    """Get the words of the phrase that was spoken as a list"""
    try:
        last_phrase = actions.core.last_phrase()
        if last_phrase:
            return [str(word) for word in last_phrase]
    except Exception:
        pass
    return []


def get_phrase_text():
    """Get the text of the phrase that was spoken as a string"""
    words = get_phrase_words()
    return " ".join(words) if words else None


def format_command_name_for_filename(command_trigger, capture=None):
    """Convert command trigger to snake_case for filename"""
    if not command_trigger:
        return "unknown"

    # Handle navigation steps specially
    if command_trigger == "go <user.navigation_step>+":
        if capture and len(capture) > 1:
            parts = ["go"]
            for i in range(1, len(capture)):
                item = capture[i]
                if hasattr(item, "modifier") and hasattr(item, "count"):
                    parts.append(item.modifier.lower())
                    if item.count > 1:
                        parts.append(str(item.count))
            return "_".join(parts)
        return "go"

    # Handle special keys
    if command_trigger == "<user.special_key>":
        if capture:
            return str(capture).strip().lower().replace(" ", "_")
        return "special_key"

    # Remove capture syntax and convert to snake_case
    cleaned = re.sub(r"<[^>]+>", "", command_trigger)
    cleaned = re.sub(r"[\[\]\(\)\+\*\?]", "", cleaned)
    cleaned = re.sub(r"[\s\|]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("_").lower()

    # Truncate long names
    if len(cleaned) > 50:
        cleaned = cleaned[:50]

    return cleaned if cleaned else "unknown"


def format_command_for_display(command_trigger, capture=None):
    """Format a command name for human-readable display"""
    if command_trigger == "go <user.navigation_step>+":
        if capture and len(capture) > 1:
            parts = ["go"]
            for i in range(1, len(capture)):
                item = capture[i]
                if hasattr(item, "modifier") and hasattr(item, "count"):
                    count_str = str(item.count) if item.count > 1 else ""
                    parts.append(f"{item.modifier} {count_str}".strip())
            return " ".join(parts)
    elif command_trigger == "<user.special_key>":
        if capture:
            return f"special key: {capture}"

    return command_trigger


def extract_capture_data(capture):
    """Extract serializable data from capture"""
    if not capture:
        return None

    try:
        # Handle navigation steps
        if len(capture) > 1:
            steps = []
            for i in range(1, len(capture)):
                item = capture[i]
                if hasattr(item, "modifier") and hasattr(item, "count"):
                    steps.append({"modifier": item.modifier, "count": item.count})
            if steps:
                return {
                    "type": "navigation_steps",
                    "raw": str(capture),
                    "steps": steps,
                }

        # Generic capture
        return {
            "type": "generic",
            "raw": str(capture),
        }
    except Exception:
        return None


def check_opposite_exists(command_trigger):
    """Check if a command has an opposite defined"""
    try:
        from .opposite_mappings import OPPOSITES

        if command_trigger in OPPOSITES:
            opposite = OPPOSITES[command_trigger]
            return {
                "exists": True,
                "trigger": opposite.get("trigger", "unknown"),
                "reversible": True,
            }
        elif command_trigger == "go <user.navigation_step>+":
            return {"exists": True, "trigger": "reverse", "reversible": True}
    except Exception:
        pass

    return {"exists": False, "trigger": None, "reversible": False}


def log_command(phrase_info):
    """Log a command execution to JSON file"""
    try:
        # Only log in command or mixed mode (command+dictation), skip sleep
        modes = scope.get("mode", set())
        if not (_LOGGABLE_MODES & set(modes)):
            return

        # Get the last executed command
        try:
            last_cmd, capture = actions.core.last_command()
        except (IndexError, Exception):
            return

        if not last_cmd:
            return

        command_trigger = last_cmd.trigger
        timestamp = datetime.now()

        # Skip if last_command() hasn't changed — same trigger + same phrase text
        phrase_text = get_phrase_text() or ""
        dedup_key = f"{command_trigger}|{phrase_text}"
        global _last_logged_trigger, _last_logged_timestamp
        if dedup_key == _last_logged_trigger:
            return
        _last_logged_trigger = dedup_key

        # Get command rule
        command_rule = None
        if hasattr(last_cmd, "rule") and hasattr(last_cmd.rule, "rule"):
            command_rule = last_cmd.rule.rule

        # Build payload (unified schema v1.1)
        payload = {
            "version": SCHEMA_VERSION,
            "action_type": "command",
            "timestamp": timestamp.isoformat(),
            "command": {
                "trigger": command_trigger,
                "rule": command_rule,
                "display": format_command_for_display(command_trigger, capture),
            },
            "phrase": {
                "words": get_phrase_words(),
                "text": get_phrase_text(),
            },
            "capture": extract_capture_data(capture),
            "opposite": check_opposite_exists(command_trigger),
            "context": get_context_data(),
            "metadata": {
                "success": True,  # We only log after successful execution
            },
        }

        # Ensure directory exists
        COMMANDS_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

        # Create filename
        command_name = format_command_name_for_filename(command_trigger, capture)
        timestamp_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S-%f")
        filename = f"{command_name}__{timestamp_str}.json"
        filepath = COMMANDS_RECORDINGS_DIR / filename

        # Write JSON file
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2, default=str)

        # Append compact line to JSONL for fast tail-based reading
        with open(COMMANDS_JSONL, "a") as f:
            f.write(json.dumps(payload, default=str) + "\n")

    except Exception:
        # Never let logging break command execution
        pass


def log_parrot_command(command_trigger: str, display: str = ""):
    """Log a parrot-triggered action to JSONL as a regular command."""
    try:
        timestamp = datetime.now()
        payload = {
            "version": SCHEMA_VERSION,
            "action_type": "command",
            "timestamp": timestamp.isoformat(),
            "command": {
                "trigger": command_trigger,
                "rule": None,
                "display": display or command_trigger,
            },
            "phrase": {
                "words": [],
                "text": display or command_trigger,
            },
            "context": get_context_data(),
            "metadata": {
                "success": True,
            },
        }
        with open(COMMANDS_JSONL, "a") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


# Register the hook
speech_system.register("post:phrase", log_command)
