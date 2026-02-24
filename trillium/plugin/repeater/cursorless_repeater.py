from talon import Context, Module, actions, speech_system
from typing import Any

mod = Module()
ctx = Context()

# Only activate when Cursorless is available
ctx.matches = r"""
tag: user.cursorless
"""

# Track last Cursorless basic action and modifiers
last_cursorless_instruction = None
last_cursorless_modifiers = None


@mod.action_class
class Actions:
    def cursorless_same_target(new_target: Any):  # pyright: ignore [reportGeneralTypeIssues]
        """Repeat the last Cursorless action with a new target"""
        # Default implementation (will be overridden by context)
        pass


def on_post_phrase(j):
    """Track Cursorless commands after execution

    Only updates stored command when a cursorless command is detected.
    Non-cursorless commands will not overwrite the stored values,
    allowing the user to run other commands and still use 'same'.
    """
    global last_cursorless_instruction, last_cursorless_modifiers

    try:
        last_cmd, capture = actions.core.last_command()

        # Check if it's the basic Cursorless pattern
        if (
            last_cmd
            and last_cmd.trigger
            == "<user.cursorless_action_or_ide_command> <user.cursorless_target>"
        ):
            # capture is a tuple: (instruction_dict, target_object)
            # Store the instruction: {"type": "cursorless_action", "value": "setSelection"}
            last_cursorless_instruction = capture[0]

            # Store the modifiers from the original target
            # The target is capture[1] and has .modifiers attribute
            original_target = capture[1]

            # Handle different target types (PrimitiveTarget, ListTarget, RangeTarget)
            if hasattr(original_target, "modifiers"):
                # PrimitiveTarget has .modifiers
                last_cursorless_modifiers = original_target.modifiers
            elif (
                hasattr(original_target, "elements")
                and len(original_target.elements) > 0
            ):
                # ListTarget - use modifiers from first element
                if hasattr(original_target.elements[0], "modifiers"):
                    last_cursorless_modifiers = original_target.elements[0].modifiers
                else:
                    last_cursorless_modifiers = None
            else:
                # RangeTarget or other - no modifiers to extract
                last_cursorless_modifiers = None

            actions.user.boolean_print(
                "cursorless_repeater",
                f"Stored cursorless action: {last_cursorless_instruction}, modifiers: {last_cursorless_modifiers}",
            )
        else:
            # Non-cursorless command - preserve existing stored values
            actions.user.boolean_print(
                "cursorless_repeater",
                f"Non-cursorless command '{last_cmd.trigger if last_cmd else 'None'}' - preserving stored action",
            )
    except Exception as e:
        # Ignore errors (command might not have captures)
        actions.user.boolean_print(
            "cursorless_repeater",
            f"Error tracking command: {e}",
        )


# Register the post-phrase hook
speech_system.register("post:phrase", on_post_phrase)


@ctx.action_class("user")
class UserActions:
    def cursorless_same_target(new_target: Any):  # pyright: ignore [reportGeneralTypeIssues]
        """Repeat the last Cursorless action with a new target"""
        global last_cursorless_instruction, last_cursorless_modifiers

        if not last_cursorless_instruction:
            actions.user.boolean_print(
                "cursorless_repeater", "No Cursorless action to repeat"
            )
            return

        # Apply the stored modifiers to the new target
        # The new_target comes from the grammar and might have its own modifiers
        # We want to replace the mark but keep the original modifiers
        modified_target = new_target

        # Handle different target types
        if hasattr(new_target, "mark"):
            # PrimitiveTarget - replace modifiers with stored ones
            # Create a new target with the new mark and stored modifiers
            target_type = type(new_target)

            modified_target = target_type(
                mark=new_target.mark,  # Use the new mark
                modifiers=last_cursorless_modifiers,  # Use the stored modifiers
            )

            actions.user.boolean_print(
                "cursorless_repeater",
                f"Created modified target with new mark and stored modifiers: {last_cursorless_modifiers}",
            )
        elif hasattr(new_target, "elements"):
            # ListTarget - apply modifiers to each element
            # For now, just use the target as-is and warn
            actions.user.boolean_print(
                "cursorless_repeater",
                "Warning: List targets not fully supported for 'same' command",
            )

        # Execute the stored action with the modified target
        actions.user.boolean_print(
            "cursorless_repeater",
            f"Repeating {last_cursorless_instruction} with modified target",
        )

        actions.user.private_cursorless_action_or_ide_command(
            last_cursorless_instruction, modified_target
        )
