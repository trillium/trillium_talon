"""
Recall Revive - Archive, revive, restore, number, mimic, and dictate actions.
"""

import os
import time
from talon import actions, ui
from . import recall_overlay
from . import recall_state
from .recall_state import (
    mod, saved_windows, archived_windows,
    save_to_disk, update_window_list,
)
from .recall_terminal import is_terminal, _launch_terminal
from .recall_commands import _resolve_command, _run_when_ready


@mod.action_class
class Actions:
    def recall_revive(name: str):
        """Relaunch an archived window (terminal at saved path) and re-register it"""
        if name not in archived_windows:
            recall_overlay.flash(f'"{name}" not in archive')
            return

        info = archived_windows[name]
        app_name = info.get("app", "")
        path = info.get("path")

        if not is_terminal(app_name) or not path:
            recall_overlay.flash(f'"{name}" has no terminal path to restore')
            return

        if not os.path.isdir(path):
            recall_overlay.flash(f'"{name}" path no longer exists: {path}')
            return

        # Collect existing window IDs to detect the new one
        existing_ids = set()
        for a in ui.apps(background=False):
            if a.name == app_name:
                for w in a.windows():
                    existing_ids.add(w.id)

        _launch_terminal(app_name, path)

        # Poll for the new window (~2s)
        new_window = None
        for _ in range(20):
            time.sleep(0.1)
            for a in ui.apps(background=False):
                if a.name == app_name:
                    for w in a.windows():
                        if w.id not in existing_ids and w.rect.width > 0:
                            new_window = w
                            break
                if new_window:
                    break
            if new_window:
                break

        if new_window:
            # Move from archive to active
            archived_windows.pop(name)
            revived = dict(info)
            revived.pop("forgotten_at", None)
            revived["id"] = new_window.id
            revived["title"] = new_window.title
            saved_windows[name] = revived
            save_to_disk()
            update_window_list()
            actions.user.switcher_focus_window(new_window)
            if not recall_state._persistent_highlight_enabled:
                recall_overlay.highlight_window(new_window, name)

            # Run default command
            command_name = revived.get("command")
            if command_name:
                shell_cmd = _resolve_command(command_name)
                if shell_cmd:
                    _run_when_ready(new_window, shell_cmd, revived.get("path"))
        else:
            recall_overlay.flash(f'"{name}" timed out waiting for window')

    def recall_list_archive():
        """Show archived window names"""
        if not archived_windows:
            recall_overlay.flash("archive is empty")
            return
        names = ", ".join(archived_windows.keys())
        recall_overlay.flash(f"archive: {names}")

    def recall_purge(name: str):
        """Permanently delete an archived window"""
        if name not in archived_windows:
            recall_overlay.flash(f'"{name}" not in archive')
            return

        del archived_windows[name]
        save_to_disk()
        recall_overlay.flash(f'purged "{name}" permanently')

    def restore_window(name: str):
        """Restore a saved terminal window by launching a new one at the saved path"""
        if name not in saved_windows:
            return

        info = saved_windows[name]
        app_name = info.get("app", "")
        path = info.get("path")

        if app_name == "Code" and path:
            import subprocess
            if not os.path.isdir(path):
                print(f"[recall] restore: VS Code path no longer exists: {path}")
                actions.user.recall_window(name)
                return

            # Collect existing window IDs for VS Code
            existing_ids = set()
            for a in ui.apps(background=False):
                if a.name == app_name:
                    for w in a.windows():
                        existing_ids.add(w.id)

            subprocess.Popen(["code", path])
        elif not is_terminal(app_name) or not path:
            # Non-terminal or no path — just try re-match
            actions.user.recall_window(name)
            return
        else:
            if not os.path.isdir(path):
                print(f"[recall] restore: path no longer exists: {path}")
                actions.user.recall_window(name)
                return

            # Collect existing window IDs for this app
            existing_ids = set()
            for a in ui.apps(background=False):
                if a.name == app_name:
                    for w in a.windows():
                        existing_ids.add(w.id)

            # Launch new terminal at the saved path
            _launch_terminal(app_name, path)

        # Poll for the new window (~4s)
        new_window = None
        for _ in range(40):
            time.sleep(0.1)
            for a in ui.apps(background=False):
                if a.name == app_name:
                    for w in a.windows():
                        if w.id not in existing_ids and w.rect.width > 0:
                            new_window = w
                            break
                if new_window:
                    break
            if new_window:
                break

        if new_window:
            info["id"] = new_window.id
            info["title"] = new_window.title
            save_to_disk()
            actions.user.switcher_focus_window(new_window)

            # Run default command
            command_name = info.get("command")
            if command_name:
                shell_cmd = _resolve_command(command_name)
                if shell_cmd:
                    _run_when_ready(new_window, shell_cmd, info.get("path"))
                else:
                    print(f"[recall] restore: unknown command '{command_name}'")
        else:
            print("[recall] restore: timed out waiting for new window")

    def recall_detach(name: str):
        """Detach a saved window from its live window without forgetting it.
        Clears the window ID but keeps name, app, path, aliases, etc."""
        if name not in saved_windows:
            return
        saved_windows[name]["id"] = None
        save_to_disk()
        recall_overlay.flash(f'{name}: detached')

    def recall_number(name: str, number: int):
        """Focus a saved window and press a number key"""
        actions.user.recall_window(name)
        actions.sleep("50ms")
        actions.key(str(number))

    def recall_window_and_mimic(name: str, text: str):
        """Focus a saved window, wait for context update, then mimic remaining words"""
        actions.user.recall_window(name)
        actions.sleep("25ms")
        actions.mimic(text)

    def dictate_to_window(name: str, text: str):
        """Focus a saved window and type dictated text into it"""
        actions.user.recall_window(name)
        actions.user.dictation_insert(text)

    def dictate_to_window_and_enter(name: str, text: str):
        """Focus a saved window, type dictated text, and press Enter"""
        actions.user.recall_window(name)
        actions.user.dictation_insert(text)
        actions.sleep("50ms")
        actions.key("enter")
