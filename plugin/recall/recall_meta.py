"""
Recall Meta - Command, auto-assign, and border toggle actions.
"""

from pathlib import Path
from talon import actions
from . import recall_overlay
from . import recall_state
from .recall_state import mod, saved_windows, save_to_disk
from .recall_commands import _resolve_command


@mod.action_class
class Actions:
    def recall_set_command(name: str, command_name: str):
        """Set the default command to run when restoring a window.
        Stores the spoken name (e.g. 'yolo') so it resolves from the list at runtime."""
        if name not in saved_windows:
            return
        saved_windows[name]["command"] = command_name
        save_to_disk()
        shell_cmd = _resolve_command(command_name)
        path = saved_windows[name].get("path", "~")
        subtitle = f"cd {path} && {shell_cmd}" if shell_cmd else ""
        recall_overlay.flash(f'{name}: command = {command_name}', subtitle)

    def recall_clear_command(name: str):
        """Remove the default command from a saved window"""
        if name not in saved_windows:
            return
        saved_windows[name].pop("command", None)
        save_to_disk()
        recall_overlay.flash(f'{name}: command cleared')

    def recall_edit_commands():
        """Open the recall commands list in the default editor"""
        commands_file = Path(__file__).parent / "recall_commands.talon-list"
        actions.user.edit_text_file(str(commands_file))

    def recall_auto_assign(name: str):
        """Toggle auto-assign for a saved window. When enabled, the recall
        system will automatically re-attach to a matching window on focus."""
        if name not in saved_windows:
            return
        current = saved_windows[name].get("auto_assign", False)
        saved_windows[name]["auto_assign"] = not current
        save_to_disk()
        state = "ON" if not current else "OFF"
        recall_overlay.flash(f'{name}: auto-assign {state}')

    def recall_toggle_border():
        """Toggle the persistent window border on/off"""
        recall_state._persistent_highlight_enabled = not recall_state._persistent_highlight_enabled
        save_to_disk()
        if recall_state._persistent_highlight_enabled:
            from .recall import _activate_persistent_highlight
            _activate_persistent_highlight()
            recall_overlay.flash("recall border: ON")
        else:
            from .recall import _deactivate_persistent_highlight
            _deactivate_persistent_highlight()
            recall_overlay.flash("recall border: OFF")
