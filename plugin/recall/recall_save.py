"""
Recall Save - save_window, forget_window, forget_all_windows actions,
plus the archive_window and cleanup_closed_windows helpers.
"""

import time
from talon import actions, ui
from . import recall_overlay
from . import recall_state
from .recall_state import (
    mod, saved_windows, archived_windows,
    is_forbidden,
    save_to_disk, update_window_list,
    find_name_for_window_id,
)
from .recall_terminal import is_terminal, detect_terminal_path
from .recall_commands import find_window_by_id


def archive_window(name: str, info: dict):
    """Move a window entry to the archive, preserving its metadata."""
    info = dict(info)  # copy
    info["forgotten_at"] = time.time()
    archived_windows[name] = info


def cleanup_closed_windows(closed_window: ui.Window):
    """When a saved window closes, clear its ID but keep the entry.
    The name, path, app, and aliases are preserved so 'recall restore'
    can relaunch it later."""
    for name, info in saved_windows.items():
        if info["id"] == closed_window.id:
            info["id"] = None
            save_to_disk()
            # Clear persistent border if it was tracking this window
            if recall_state._persistent_highlight_enabled:
                recall_overlay.clear_persistent_highlight()
            break


@mod.action_class
class Actions:
    def save_window(name: str):
        """Save the currently focused window with the given name.
        If this window is already saved under a different name, the new
        name is automatically added as an alias of the existing entry."""
        if is_forbidden(name):
            recall_overlay.flash(f'"{name}" is a reserved word')
            return

        window = ui.active_window()
        app_name = window.app.name

        # Check if this window is already saved under a different name
        existing_name = find_name_for_window_id(window.id)
        if existing_name and existing_name != name:
            # Add as alias instead of creating a duplicate
            aliases = saved_windows[existing_name].get("aliases", [])
            if name not in aliases:
                aliases.append(name)
                saved_windows[existing_name]["aliases"] = aliases
                save_to_disk()
                update_window_list()
                recall_overlay.flash(f'alias: {name} -> {existing_name}')
            return

        # Detect path for terminals and VS Code
        path = None
        if is_terminal(app_name):
            path = detect_terminal_path(window)
        elif app_name == "Code":
            try:
                from trillium.workspace.workspace import _get_current_workspace_path
                path = _get_current_workspace_path()
            except Exception:
                pass

        # Preserve existing aliases if re-saving under the same name
        existing_aliases = saved_windows.get(name, {}).get("aliases", [])

        saved_windows[name] = {
            "id": window.id,
            "app": app_name,
            "title": window.title,
            "path": path,
            "aliases": existing_aliases,
        }

        save_to_disk()
        update_window_list()

        # Update persistent highlight if enabled, otherwise show brief highlight
        if recall_state._persistent_highlight_enabled:
            recall_overlay.show_persistent_highlight(window, name)
        else:
            recall_overlay.highlight_window(window, name)

    def forget_window(name: str):
        """Archive a saved window (remove from active, keep in history)"""
        if name not in saved_windows:
            return

        archive_window(name, saved_windows[name])
        del saved_windows[name]
        save_to_disk()
        update_window_list()
        recall_overlay.flash(f'forgot "{name}" (archived)')

        # Clear persistent highlight if the forgotten window was highlighted
        if recall_state._persistent_highlight_enabled:
            recall_overlay.clear_persistent_highlight()

    def forget_all_windows():
        """Archive all saved windows"""
        count = len(saved_windows)
        for name, info in saved_windows.items():
            archive_window(name, info)
        saved_windows.clear()
        save_to_disk()
        update_window_list()
        recall_overlay.flash(f"forgot all ({count} windows, archived)")
