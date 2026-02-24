"""
Parrot Logger - Logs metadata when repeat/reverse parrot sounds are used

Schema version 1.1 - unified with command_logger
"""

from talon import actions, ui, scope
from datetime import datetime
from pathlib import Path
import json
import re


# Path to the parrot recordings directory
PARROT_RECORDINGS_DIR = Path.home() / ".talon" / "recordings" / "parrot"

# Schema version - bump when format changes
SCHEMA_VERSION = "1.1"


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

    return context


def format_command_name_for_filename(command_trigger, capture=None):
    """
    Convert command trigger to snake_case for filename

    Examples:
        "go <user.navigation_step>+" with capture -> "go_up_3"
        "tail" -> "tail"
        "<user.special_key>" with "pagedown" -> "pagedown"
    """
    if not command_trigger:
        return "unknown"

    # Handle navigation steps
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


def check_opposite_exists(command_trigger):
    """Check if a command has an opposite defined"""
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
    else:
        return {"exists": False, "trigger": None, "reversible": False}


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


def generate_json_payload(action_type, last_cmd, capture, success=True, confidence=None):
    """Generate the complete JSON payload for logging (unified schema v1.1)"""
    timestamp = datetime.now()

    # Get context data
    context = get_context_data()

    # Get command info
    command_trigger = last_cmd.trigger if last_cmd else "unknown"
    command_rule = None
    if last_cmd and hasattr(last_cmd, "rule") and hasattr(last_cmd.rule, "rule"):
        command_rule = last_cmd.rule.rule

    # Build complete payload (unified schema)
    payload = {
        "version": SCHEMA_VERSION,
        "action_type": action_type,
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
        "context": context,
        "metadata": {
            "success": success,
        },
    }

    # Add parrot confidence if available (parrot-specific field)
    if confidence is not None:
        payload["parrot_confidence"] = round(confidence, 2)

    return payload, timestamp


def log_parrot_action(action_type, last_cmd, capture, success=True, confidence=None):
    """
    Main logging function - creates a JSON file for the parrot action

    Args:
        action_type: "repeat" or "reverse"
        last_cmd: The command object from actions.core.last_command()
        capture: The capture data from the command
        success: Whether the action executed successfully
        confidence: The parrot confidence score (0-100) for the sound detection
    """
    try:
        # Ensure directory exists
        PARROT_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

        # Generate payload
        payload, timestamp = generate_json_payload(
            action_type, last_cmd, capture, success, confidence
        )

        # Format command name for filename
        command_trigger = last_cmd.trigger if last_cmd else "unknown"
        command_name = format_command_name_for_filename(command_trigger, capture)

        # Create filename: {action_type}__{command}__{timestamp}.json
        timestamp_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S-%f")
        filename = f"{action_type}__{command_name}__{timestamp_str}.json"
        filepath = PARROT_RECORDINGS_DIR / filename

        # Write JSON file
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2, default=str)

        actions.user.boolean_print(
            "parrot_logger", f"Logged {action_type} action to: {filename}"
        )

    except Exception as e:
        # Don't let logging errors break the repeat/reverse functionality
        actions.user.boolean_print("parrot_logger", f"Failed to log parrot action: {e}")
