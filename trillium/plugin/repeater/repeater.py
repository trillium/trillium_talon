from talon import Context, Module, settings, actions, speech_system
from talon import resource
import time
import csv
from pathlib import Path
from .opposite_mappings import REVERSE_MODIFIERS, REVERSE_SPECIAL_KEYS, OPPOSITES
from . import parrot_logger
from ...core.on_phrase.command_logger import log_parrot_command

# Import parrot_integration to access confidence score
try:
    from ..parrot import parrot_integration
except ImportError:
    parrot_integration = None

mod = Module()
ctx = Context()


@mod.action_class
class Actions:
    def special_key_opposite():
        """Execute the opposite of the last special key press"""

    def set_next_repeat_action(namespace: str, action_name: str, args: list = None):
        """Set what action should run on the next repeat sound.

        Call this from any command to override what the pop sound does next.
        The override persists until a new trackable command is spoken.

        Args:
            namespace: Action namespace (e.g., "edit", "key", "user")
            action_name: Action name (e.g., "left", "delete")
            args: List of arguments to pass to the action
        """
        global override_repeat_action
        override_repeat_action = (namespace, action_name, tuple(args) if args else ())
        actions.user.boolean_print(
            "repeater", f"Set next repeat action: {namespace}.{action_name}({args})"
        )

    def set_next_opposite_action(namespace: str, action_name: str, args: list = None):
        """Set what action should run on the next opposite sound.

        Call this from any command to override what the cmere sound does next.
        The override persists until a new trackable command is spoken.

        Args:
            namespace: Action namespace (e.g., "edit", "key", "user")
            action_name: Action name (e.g., "right", "undo")
            args: List of arguments to pass to the action
        """
        global override_opposite_action
        override_opposite_action = (namespace, action_name, tuple(args) if args else ())
        actions.user.boolean_print(
            "repeater", f"Set next opposite action: {namespace}.{action_name}({args})"
        )

    def clear_repeat_overrides():
        """Clear any programmatically set repeat/opposite overrides"""
        global override_repeat_action, override_opposite_action
        override_repeat_action = None
        override_opposite_action = None
        actions.user.boolean_print("repeater", "Cleared repeat/opposite overrides")

    def repeater_get_state() -> dict:
        """Get current repeater state for persistence across restarts."""
        state = {}

        if last_repeatable_cmd:
            state["trigger"] = last_repeatable_cmd.trigger
            state["display"] = format_command_for_display(
                last_repeatable_cmd.trigger, last_repeatable_capture
            )

            # Save navigation steps if applicable
            if last_repeatable_cmd.trigger == "go <user.navigation_step>+" and last_repeatable_capture:
                steps = []
                for i in range(1, len(last_repeatable_capture)):
                    item = last_repeatable_capture[i]
                    if hasattr(item, "modifier") and hasattr(item, "count"):
                        steps.append({"modifier": item.modifier, "count": item.count})
                if steps:
                    state["navigation_steps"] = steps

            # Save special key if applicable
            if last_repeatable_cmd.trigger == "<user.special_key>" and last_repeatable_capture:
                state["special_key"] = str(last_repeatable_capture).strip()

        return state

    def repeater_restore_state(state: dict):
        """Restore repeater state after restart."""
        if not state:
            return

        trigger = state.get("trigger")
        display = state.get("display", trigger)

        # Restore navigation steps
        if "navigation_steps" in state:
            steps = state["navigation_steps"]
            # Set override to perform these navigation steps
            actions.user.set_next_repeat_action("user", "repeater_perform_navigation", [steps])

            # Set opposite to perform reversed steps
            reversed_steps = []
            for step in steps:
                rev_mod = REVERSE_MODIFIERS.get(step["modifier"])
                if rev_mod:
                    reversed_steps.append({"modifier": rev_mod, "count": step["count"]})
            if reversed_steps:
                actions.user.set_next_opposite_action("user", "repeater_perform_navigation", [reversed_steps])

            actions.user.boolean_print("repeater", f"Restored navigation: {display}")

        # Restore special key
        elif "special_key" in state:
            key = state["special_key"]
            actions.user.set_next_repeat_action("key", key, [])

            # Set opposite if we have a reverse mapping
            opposite_key = REVERSE_SPECIAL_KEYS.get(key)
            if opposite_key:
                actions.user.set_next_opposite_action("key", opposite_key, [])

            actions.user.boolean_print("repeater", f"Restored special key: {key}")

        # Update mode indicator
        try:
            opposite_text = "reverse" if "navigation_steps" in state or REVERSE_SPECIAL_KEYS.get(state.get("special_key")) else ""
            actions.user.mode_indicator_set_command_text(display, opposite_text)
        except Exception:
            pass

    def repeater_perform_navigation(steps: list):
        """Perform navigation steps from a list of dicts."""
        try:
            for step in steps:
                modifier = step["modifier"]
                count = step.get("count", 1)

                for _ in range(count):
                    if modifier == "wordLeft":
                        actions.edit.word_left()
                    elif modifier == "wordRight":
                        actions.edit.word_right()
                    elif modifier == "word":
                        actions.edit.word_right()
                    elif modifier == "left":
                        actions.edit.left()
                    elif modifier == "right":
                        actions.edit.right()
                    elif modifier == "lineUp":
                        actions.edit.up()
                    elif modifier == "lineDown":
                        actions.edit.down()
        except Exception as e:
            actions.user.boolean_print("repeater", f"Failed to perform navigation: {e}")


# Commands to exclude from repeater (raw dictation, etc)
# This will be populated from excluded_commands.csv
excluded_commands_set = set()

# Path to the excluded commands CSV file in the repeater folder
EXCLUDED_COMMANDS_PATH = Path(__file__).parent / "excluded_commands.csv"


def load_excluded_commands(file):
    """Load excluded commands from CSV file"""
    global excluded_commands_set
    excluded_commands_set = set()
    rows = list(csv.reader(file))

    if len(rows) >= 2:
        # Skip header row
        for row in rows[1:]:
            if len(row) == 0:
                continue
            # First column is the command trigger
            command_trigger = row[0].strip()
            if command_trigger:
                excluded_commands_set.add(command_trigger)

    actions.user.boolean_print(
        "repeater",
        f"Loaded {len(excluded_commands_set)} excluded commands: {excluded_commands_set}",
    )


@resource.watch(str(EXCLUDED_COMMANDS_PATH))
def on_excluded_commands_update(f):
    """Update the set of excluded commands when CSV changes"""
    load_excluded_commands(f)


# Track the last repeatable command separately
last_repeatable_cmd = None
last_repeatable_capture = None

# Override actions that commands can set programmatically
# When set, these take priority over the normal repeat/opposite behavior
# Format: (namespace, action_name, args) e.g. ("edit", "left", ())
override_repeat_action = None
override_opposite_action = None


def should_track_command(command_name):
    """Check if a command should be tracked by the repeater"""
    return command_name not in excluded_commands_set


def on_post_phrase(j):
    """Called after every phrase/command is executed"""
    global last_repeatable_cmd, last_repeatable_capture
    global override_repeat_action, override_opposite_action
    # Get the last command that was executed
    try:
        last_cmd, capture = actions.core.last_command()
    except IndexError:
        # No command history yet
        return
    actions.user.boolean_print(
        "repeater",
        f"on_post_phrase: last_cmd={last_cmd.trigger if last_cmd else 'None'}, should_track={should_track_command(last_cmd.trigger) if last_cmd else 'N/A'}",
    )
    if last_cmd and should_track_command(last_cmd.trigger):
        # Clear any programmatic overrides when a new trackable command is spoken
        if override_repeat_action or override_opposite_action:
            actions.user.boolean_print(
                "repeater", "Clearing repeat/opposite overrides due to new command"
            )
            override_repeat_action = None
            override_opposite_action = None
        # Store this as the last repeatable command
        last_repeatable_cmd = last_cmd
        last_repeatable_capture = capture
        actions.user.boolean_print(
            "repeater", f"Stored repeatable command: {last_cmd.trigger}"
        )
        update_mode_indicator_with_last_command(last_cmd, capture)


speech_system.register("post:phrase", on_post_phrase)


def format_command_for_display(command_name, capture=None):
    """Format a command name for display, handling navigation steps"""
    if command_name == "go <user.navigation_step>+":
        if capture and len(capture) > 1:
            # Build a readable string from navigation steps
            parts = ["go"]
            for i in range(1, len(capture)):
                item = capture[i]
                if hasattr(item, "modifier") and hasattr(item, "count"):
                    count_str = str(item.count) if item.count > 1 else ""
                    parts.append(f"{item.modifier} {count_str}".strip())
            return " ".join(parts)
    return command_name


def update_mode_indicator_with_last_command(last_cmd, capture):
    """Update the mode indicator with the last command and its opposite"""
    command_name = last_cmd.trigger

    # Format the command for display
    last_text = format_command_for_display(command_name, capture)

    # Check if there's an opposite
    opposite_text = ""
    if command_name == "go <user.navigation_step>+":
        opposite_text = "reverse"
    elif command_name in OPPOSITES:
        opposite = OPPOSITES[command_name]
        opposite_text = opposite.get("trigger", "reverse")

    # Debug logging
    actions.user.boolean_print(
        "repeater", f"Command: '{last_text}', Opposite: '{opposite_text}'"
    )

    # Update the mode indicator
    try:
        actions.user.mode_indicator_set_command_text(last_text, opposite_text)
        actions.user.boolean_print(
            "repeater", "Successfully called mode_indicator_set_command_text"
        )
    except Exception as e:
        # Mode indicator might not be loaded
        actions.user.boolean_print("repeater", f"Failed to update mode indicator: {e}")
        pass


ctx.matches = r"""
tag: user.parrot_on
mode: command
mode: dictation
"""

# Acceleration state for rapid repeats
accel_command = None      # Command trigger being accelerated (e.g. "wheel down")
accel_count = 0           # Number of repeats in current window
accel_last_time = 0       # Timestamp of last accelerated action
ACCEL_WINDOW = 1.0        # Seconds before acceleration resets
ACCEL_COMMANDS = {"wheel up", "wheel down"}  # Commands that support acceleration


def get_accel_multiplier(count: int) -> int:
    """Get scroll multiplier based on repeat count. No cap — keeps growing."""
    if count <= 3:
        return 1
    if count <= 6:
        return 2
    if count <= 9:
        return 3
    if count <= 12:
        return 5
    if count <= 15:
        return 8
    return 12


def notify_accel_tier_change(old_mult: int, new_mult: int):
    """Stub for future tier change notification."""
    # TODO: Implement visual/audio feedback (filed as ops ticket)
    pass


def update_accel_state(command: str) -> int:
    """Update acceleration state and return current multiplier."""
    global accel_command, accel_count, accel_last_time
    now = time.time()

    if command in ACCEL_COMMANDS:
        # Check if continuing same command within window
        if command == accel_command and (now - accel_last_time) < ACCEL_WINDOW:
            accel_count += 1
        else:
            accel_command = command
            accel_count = 1
        accel_last_time = now
        multiplier = get_accel_multiplier(accel_count)
        actions.user.boolean_print("repeater", f"Accel: {command} count={accel_count} mult={multiplier}x")
        return multiplier
    else:
        # Non-accelerating command resets state
        accel_command = None
        accel_count = 0
        return 1


def execute_accelerated_scroll(command: str, multiplier: int):
    """Execute scroll command with acceleration multiplier."""
    if command == "wheel down":
        actions.user.mouse_scroll_down(multiplier)
        opposite = "wheel up"
    elif command == "wheel up":
        actions.user.mouse_scroll_up(multiplier)
        opposite = "wheel down"
    else:
        return

    # Update mode indicator with multiplier
    try:
        label = f"{command} {multiplier}x"
        actions.user.mode_indicator_set_command_text(label, opposite)
    except Exception:
        pass


def reverse_navigation_steps(capture):
    """
    Reverse navigation steps from a go command capture.
    capture[0] is the word "go"
    capture[1:] are NavigationStep objects with .modifier and .count attributes
    """

    # Extract all NavigationStep objects (skip the "go" word at index 0)
    steps = []
    for i in range(1, len(capture)):
        item = capture[i]
        # Check if it's a NavigationStep object
        if hasattr(item, "modifier") and hasattr(item, "count"):
            # Reverse the modifier
            reversed_modifier = REVERSE_MODIFIERS.get(item.modifier)
            if reversed_modifier:
                # Create a new NavigationStep with reversed modifier, same count
                # Get the NavigationStep class from the item's type
                NavigationStepClass = type(item)
                reversed_step = NavigationStepClass(
                    modifier=reversed_modifier, count=item.count
                )
                steps.append(reversed_step)
            else:
                actions.user.boolean_print(
                    "repeater",
                    f"Warning: No reverse mapping for modifier '{item.modifier}'",
                )

    # Execute the reversed navigation steps
    if steps:
        actions.user.perform_navigation_steps(steps)
        return True
    else:
        actions.user.boolean_print("repeater", "No navigation steps to reverse")
        return False


def get_parrot_confidence():
    """Get the last parrot confidence score if available"""
    if parrot_integration and hasattr(parrot_integration, 'last_parrot_confidence'):
        return parrot_integration.last_parrot_confidence
    return None


def repeat_last_repeatable(cmd_to_log=None, capture_to_log=None, confidence=None, sound="tongue_click"):
    """Repeat the last repeatable command (excluding filtered commands)

    Args:
        cmd_to_log: The command to log (captured at action entry point)
        capture_to_log: The capture to log (captured at action entry point)
        confidence: The parrot confidence score (captured at action entry point)
        sound: The parrot sound that triggered this repeat
    """
    # Check if there's a programmatic override set
    if override_repeat_action:
        namespace, action_name, args = override_repeat_action
        actions.user.boolean_print(
            "repeater", f"Using override repeat action: {namespace}.{action_name}({args})"
        )
        success = True
        try:
            action_func = getattr(getattr(actions, namespace), action_name)
            action_func(*args)
        except Exception as e:
            actions.user.boolean_print("repeater", f"Failed to execute override: {e}")
            success = False

        # Log the repeat action
        try:
            parrot_logger.log_parrot_action(
                "repeat", cmd_to_log, capture_to_log, success, confidence
            )
            if success:
                log_parrot_command(f"{namespace}.{action_name}", sound=sound, action="repeat", confidence=confidence)
        except Exception as e:
            actions.user.boolean_print("repeater", f"Failed to log repeat action: {e}")
        return

    # Check what the actual last command was
    try:
        actual_last_cmd, _ = actions.core.last_command()
    except IndexError:
        actions.user.boolean_print("repeater", "No command history yet")
        return

    if not actual_last_cmd:
        actions.user.boolean_print("repeater", "No command to repeat")
        return

    # If the actual last command is excluded, try to use our stored repeatable command
    if actual_last_cmd.trigger in excluded_commands_set:
        # The last command was excluded (e.g., prose), so repeat the stored one instead
        if last_repeatable_cmd:
            actions.user.boolean_print(
                "repeater",
                f"'{actual_last_cmd.trigger}' excluded, repeating stored command '{last_repeatable_cmd.trigger}'",
            )
            # Use native repeat if our stored command is still in recent history
            # For now, we'll just inform the user and skip
            actions.user.boolean_print(
                "repeater",
                f"Cannot repeat through excluded command. Last repeatable was: {last_repeatable_cmd.trigger}",
            )
        else:
            actions.user.boolean_print("repeater", "No repeatable command stored")
    else:
        # Last command is not excluded, use native repeat
        success = True
        command_trigger = actual_last_cmd.trigger

        # Check if this is an acceleratable command
        if command_trigger in ACCEL_COMMANDS:
            try:
                multiplier = update_accel_state(command_trigger)
                execute_accelerated_scroll(command_trigger, multiplier)
            except Exception as e:
                actions.user.boolean_print("repeater", f"Failed to execute accelerated scroll: {e}")
                success = False
        else:
            try:
                actions.core.repeat_phrase(1)
            except Exception as e:
                actions.user.boolean_print("repeater", f"Failed to repeat: {e}")
                success = False

        # Log the repeat action using the values captured at entry point
        try:
            parrot_logger.log_parrot_action(
                "repeat", cmd_to_log, capture_to_log, success, confidence
            )
            if success:
                display = format_command_for_display(command_trigger) if command_trigger else ""
                log_parrot_command(command_trigger, display, sound=sound, action="repeat", confidence=confidence)
        except Exception as e:
            actions.user.boolean_print("repeater", f"Failed to log repeat action: {e}")


def reverse_special_key():
    """Reverse the last special key that was pressed"""
    global last_repeatable_capture
    if not last_repeatable_capture:
        actions.user.boolean_print("repeater", "No special key to reverse")
        return False

    # The capture for <user.special_key> is a string with the key value
    special_key = str(last_repeatable_capture).strip()
    actions.user.boolean_print("repeater", f"Reversing special key: '{special_key}'")

    # Look up the opposite key
    opposite_key = REVERSE_SPECIAL_KEYS.get(special_key)
    if opposite_key:
        actions.user.boolean_print(
            "repeater", f"Pressing opposite key: '{opposite_key}'"
        )
        actions.key(opposite_key)
        return True
    else:
        actions.user.boolean_print(
            "repeater", f"No reverse mapping for special key: '{special_key}'"
        )
        return False


def opposite(cmd_to_log=None, capture_to_log=None, confidence=None, sound="cmere"):
    """Execute the opposite of the last repeatable command

    Args:
        cmd_to_log: The command to log (captured at action entry point)
        capture_to_log: The capture to log (captured at action entry point)
        confidence: The parrot confidence score (captured at action entry point)
        sound: The parrot sound that triggered this reverse
    """
    # Check if there's a programmatic override set
    if override_opposite_action:
        namespace, action_name, args = override_opposite_action
        actions.user.boolean_print(
            "repeater", f"Using override opposite action: {namespace}.{action_name}({args})"
        )
        success = True
        try:
            action_func = getattr(getattr(actions, namespace), action_name)
            action_func(*args)
        except Exception as e:
            actions.user.boolean_print("repeater", f"Failed to execute override: {e}")
            success = False

        # Log the reverse action
        try:
            parrot_logger.log_parrot_action(
                "reverse", cmd_to_log, capture_to_log, success, confidence
            )
            if success:
                log_parrot_command(f"{namespace}.{action_name}", sound=sound, action="reverse", confidence=confidence)
        except Exception as e:
            actions.user.boolean_print("repeater", f"Failed to log reverse action: {e}")
        return

    # Use passed-in command or fall back to global
    cmd = cmd_to_log if cmd_to_log else last_repeatable_cmd
    capture = capture_to_log if capture_to_log else last_repeatable_capture

    if not cmd:
        actions.user.boolean_print("repeater", "No repeatable command to reverse")
        return

    command_name = cmd.trigger
    success = True

    try:
        # Special handling for go navigation commands
        if command_name == "go <user.navigation_step>+":
            if not reverse_navigation_steps(capture):
                actions.user.boolean_print(
                    "repeater", "Failed to reverse navigation steps"
                )
                success = False
        else:
            # Regular opposite handling from OPPOSITES dictionary
            opposite_mapping = OPPOSITES.get(command_name)
            if opposite_mapping:
                # Check if this is an acceleratable wheel command
                if command_name in ACCEL_COMMANDS:
                    # Get the opposite command name for acceleration state
                    opposite_trigger = opposite_mapping.get("trigger")
                    multiplier = update_accel_state(opposite_trigger)
                    execute_accelerated_scroll(opposite_trigger, multiplier)
                else:
                    namespace, action_name, args = opposite_mapping["action"]
                    action_func = getattr(getattr(actions, namespace), action_name)
                    action_func(*args)
            else:
                actions.user.boolean_print(
                    "repeater", f"No opposite defined for: {command_name}"
                )
                success = False
    except Exception as e:
        actions.user.boolean_print("repeater", f"Failed to execute opposite: {e}")
        success = False

    # Log the reverse action using the values captured at entry point
    try:
        parrot_logger.log_parrot_action(
            "reverse", cmd_to_log, capture_to_log, success, confidence
        )
        if success:
            opposite_trigger = ""
            if command_name in OPPOSITES:
                opposite_trigger = OPPOSITES[command_name].get("trigger", command_name)
            log_parrot_command(opposite_trigger or command_name, sound=sound, action="reverse", confidence=confidence)
    except Exception as e:
        actions.user.boolean_print("repeater", f"Failed to log reverse action: {e}")


@ctx.action_class("user")
class UserActions:
    def special_key_opposite():
        """Execute the opposite of the last special key press"""
        reverse_special_key()

    def noise_tongue_click():
        # Capture command/capture/confidence at entry point to avoid race condition
        cmd_to_log = last_repeatable_cmd
        capture_to_log = last_repeatable_capture
        confidence = get_parrot_confidence()

        actions.user.notify("tongue pop")
        repeat_last_repeatable(cmd_to_log, capture_to_log, confidence)

    def noise_cmere():
        # Capture command/capture/confidence at entry point to avoid race condition
        cmd_to_log = last_repeatable_cmd
        capture_to_log = last_repeatable_capture
        confidence = get_parrot_confidence()

        actions.user.notify("kitty cmere")
        opposite(cmd_to_log, capture_to_log, confidence)

    def noise_lip_pop():
        actions.user.notify("lip pop")
