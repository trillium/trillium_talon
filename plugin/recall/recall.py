"""
Recall - Save and recall specific windows by name

Allows you to save specific windows and bring them back later by name,
solving the problem where "focus chrome" brings any Chrome window instead
of the specific one you care about.

Features:
- Save the focused window with a name: "recall assign edgar" or "recall save edgar"
- Switch to it by just saying the name: "edgar"
- Dictate into a named window: "edgar hello world"
- See all named windows: "recall list" (shows overlay labels for 5 seconds)
- Forget a named window: "recall forget edgar"
- Add an alias: "recall alias edgar ed" — "ed" now also switches to edgar's window
- Combine duplicates: "recall combine velma vilma" — merges vilma into velma as an alias
- Restore a terminal: "edgar restore" — launches new terminal at saved path
"""

import os
import time
from pathlib import Path
from talon import actions, app, ui
from . import recall_overlay
from . import recall_state
from .recall_state import (
    mod, saved_windows, archived_windows,
    pending_ctx, is_forbidden,
    save_to_disk, update_window_list, load_saved_windows,
    _cancel_pending, find_name_for_window_id,
)
from .recall_terminal import (
    is_terminal, detect_terminal_path, _parse_title_path, _launch_terminal,
)
from .recall_commands import (
    find_window_by_id, rematch_window, _resolve_command, _run_when_ready,
)


def _try_auto_assign(window: ui.Window):
    """If a saved window has auto_assign=True and id=None, and this window's
    app matches, automatically reassign the saved entry to this window."""
    try:
        app_name = window.app.name
        wid = window.id
    except Exception:
        return
    for name, info in saved_windows.items():
        if name.startswith("_"):
            continue
        if not info.get("auto_assign"):
            continue
        if info.get("id") is not None:
            # Already has a live window — check if it still exists
            if find_window_by_id(info["id"]) is not None:
                continue
        if info.get("app") == app_name:
            info["id"] = wid
            info["title"] = window.title
            save_to_disk()
            break


def _on_focus_change(window: ui.Window):
    """When focus changes, try auto-assign and update persistent highlight."""
    _try_auto_assign(window)
    if not recall_state._persistent_highlight_enabled:
        return
    try:
        wid = window.id
    except Exception:
        return
    name = find_name_for_window_id(wid)
    if name:
        recall_overlay.show_persistent_highlight(window, name)
    else:
        recall_overlay.clear_persistent_highlight()


def _activate_persistent_highlight():
    """Highlight the current window if it's a saved one."""
    try:
        window = ui.active_window()
        name = find_name_for_window_id(window.id)
        if name:
            recall_overlay.show_persistent_highlight(window, name)
    except Exception:
        pass


def _deactivate_persistent_highlight():
    """Turn off the persistent highlight entirely."""
    recall_overlay.hide_persistent_highlight()


def _on_screen_change(screen):
    """Rebuild persistent canvas when monitors change."""
    recall_overlay.rebuild_persistent_canvas()


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

    def recall_detach(name: str):
        """Detach a saved window from its live window without forgetting it.
        Clears the window ID but keeps name, app, path, aliases, etc."""
        if name not in saved_windows:
            return
        saved_windows[name]["id"] = None
        save_to_disk()
        recall_overlay.flash(f'{name}: detached')

    def recall_window(name: str):
        """Focus the saved window with the given name, with re-match fallback"""
        recall_overlay.hide_any()
        if name not in saved_windows:
            return

        info = saved_windows[name]
        window = find_window_by_id(info["id"])

        if window is None:
            # Try re-matching by app + path/title
            window = rematch_window(info)
            if window is not None:
                # Update stored ID silently
                info["id"] = window.id
                info["title"] = window.title
                save_to_disk()

        if window is None:
            recall_overlay.show_overlay()
            return

        # Refresh terminal path on focus — but only if the title shows a
        # parseable path (user@host: /path).  When Claude Code or other programs
        # override the title, the /proc fallback can't distinguish which shell
        # belongs to this window, so we keep the previously saved path.
        if is_terminal(info.get("app", "")):
            title_path = _parse_title_path(window.title)
            if title_path and title_path != info.get("path"):
                info["path"] = title_path
                save_to_disk()

        actions.user.switcher_focus_window(window)
        if not recall_state._persistent_highlight_enabled:
            recall_overlay.highlight_window(window, name)

    def recall_window_and_enter(name: str):
        """Focus the saved window and press enter"""
        actions.user.recall_window(name)
        actions.sleep("50ms")
        actions.key("enter")

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

    def list_saved_windows():
        """Show window name labels on each saved window for 5 seconds"""
        recall_overlay.show_overlay()

    def show_recall_status():
        """Show the status overlay with all saved windows"""
        recall_overlay.show_status()

    def show_recall_help():
        """Show the help overlay with command reference"""
        recall_overlay.show_help()

    def hide_recall_overlay():
        """Dismiss whichever recall overlay is currently active"""
        _cancel_pending()
        recall_overlay.hide_any()

    def recall_combine(primary: str, secondary: str):
        """Combine two saved windows: secondary becomes an alias of primary"""
        if primary not in saved_windows or secondary not in saved_windows:
            return
        if primary == secondary:
            return

        # Merge secondary's aliases into primary
        primary_info = saved_windows[primary]
        secondary_info = saved_windows[secondary]

        aliases = primary_info.get("aliases", [])
        # Add the secondary name itself as an alias
        if secondary not in aliases:
            aliases.append(secondary)
        # Also bring over any aliases the secondary had
        for alias in secondary_info.get("aliases", []):
            if alias not in aliases and alias != primary:
                aliases.append(alias)
        primary_info["aliases"] = aliases

        # Merge path if primary doesn't have one
        if not primary_info.get("path") and secondary_info.get("path"):
            primary_info["path"] = secondary_info["path"]

        # Remove secondary entry
        del saved_windows[secondary]

        save_to_disk()
        update_window_list()
        recall_overlay.flash(f'combined: {secondary} -> {primary}')
        print(f'[recall] combined: "{secondary}" is now an alias of "{primary}"')

    def recall_combine_start(primary: str):
        """Start two-step combine: show prompt and wait for second name"""
        if primary not in saved_windows:
            return

        recall_state._pending_mode = "combine"
        recall_state._pending_name = primary
        pending_ctx.tags = ["user.recall_pending_input"]
        recall_overlay.show_prompt(
            f'Combine with "{primary}"',
            "Say the name to merge as an alias...",
        )

    def recall_rename_start(name: str):
        """Start two-step rename: show prompt and wait for new name"""
        if name not in saved_windows:
            return

        recall_state._pending_mode = "rename"
        recall_state._pending_name = name
        pending_ctx.tags = ["user.recall_pending_input"]
        recall_overlay.show_prompt(
            f'Rename "{name}"',
            "Say the new name...",
        )

    def recall_alias_start(name: str):
        """Start two-step alias: show prompt and wait for alias"""
        print(f"[recall] alias_start: name={name!r}, pending_mode={recall_state._pending_mode!r}, pending_name={recall_state._pending_name!r}")

        # If we're already waiting for alias input, treat this as the alias
        if recall_state._pending_mode == "alias" and recall_state._pending_name:
            print(f"[recall] alias_start: already pending — treating {name!r} as alias for {recall_state._pending_name!r}")
            actions.user.recall_pending_finish(name)
            return

        if name not in saved_windows:
            print(f"[recall] alias_start: ABORT — name not found")
            return

        recall_state._pending_mode = "alias"
        recall_state._pending_name = name
        pending_ctx.tags = ["user.recall_pending_input"]
        print(f"[recall] alias_start: tag set, pending_mode={recall_state._pending_mode!r}, pending_name={recall_state._pending_name!r}")
        recall_overlay.show_prompt(
            f'Add alias for "{name}"',
            "Say the alias...",
        )

    def recall_pending_finish(spoken: str):
        """Complete whichever two-step command is pending"""
        print(f"[recall] pending_finish: raw spoken={spoken!r}, type={type(spoken).__name__}")

        # Normalize: <user.raw_prose> gives a Phrase/list, not a str
        if not isinstance(spoken, str):
            spoken = " ".join(str(w) for w in spoken)
        spoken = spoken.strip()

        print(f"[recall] pending_finish: normalized spoken={spoken!r}")

        mode = recall_state._pending_mode
        name = recall_state._pending_name
        print(f"[recall] pending_finish: mode={mode!r}, name={name!r}")
        _cancel_pending()
        recall_overlay.hide_prompt()

        if not mode or not name or not spoken:
            print(f"[recall] pending_finish: ABORT — empty mode/name/spoken")
            return

        print(f"[recall] pending_finish: dispatching mode={mode!r} name={name!r} spoken={spoken!r}")
        if mode == "combine":
            actions.user.recall_combine(name, spoken)
        elif mode == "rename":
            actions.user.recall_rename(name, spoken)
        elif mode == "alias":
            actions.user.add_recall_alias(name, spoken)

    def recall_promote(spoken_name: str):
        """Promote an alias to be the canonical name, demoting the old name to alias"""
        if is_forbidden(spoken_name):
            recall_overlay.flash(f'"{spoken_name}" is a reserved word')
            return

        spoken = spoken_name.lower().strip()

        # Find which canonical entry has this as an alias
        canonical = None
        for name, info in saved_windows.items():
            if name.lower() == spoken:
                # Already canonical, nothing to do
                return
            if spoken in [a.lower() for a in info.get("aliases", [])]:
                canonical = name
                break

        if canonical is None:
            print(f'[recall] promote: "{spoken_name}" is not a known alias')
            return

        info = saved_windows[canonical]

        # Remove the alias from the list
        aliases = info.get("aliases", [])
        aliases = [a for a in aliases if a.lower() != spoken]
        # Add the old canonical name as an alias
        aliases.append(canonical)
        info["aliases"] = aliases

        # Re-key the entry under the new name
        del saved_windows[canonical]
        saved_windows[spoken_name] = info

        save_to_disk()
        update_window_list()
        recall_overlay.flash(f'promoted: {spoken_name} (was {canonical})')
        print(f'[recall] promoted: "{spoken_name}" is now canonical (was alias of "{canonical}")')

    def recall_rename(name: str, new_name: str):
        """Rename a saved window to a completely new name"""
        if is_forbidden(new_name):
            recall_overlay.flash(f'"{new_name}" is a reserved word')
            return

        if name not in saved_windows:
            return

        info = saved_windows[name]
        del saved_windows[name]
        saved_windows[new_name] = info

        save_to_disk()
        update_window_list()
        recall_overlay.flash(f'renamed: {name} -> {new_name}')

    def add_recall_alias(name: str, alias: str):
        """Add an alias spoken form for a saved window"""
        print(f"[recall] add_alias: name={name!r}, alias={alias!r}")
        if is_forbidden(alias):
            print(f"[recall] add_alias: ABORT — forbidden")
            recall_overlay.flash(f'"{alias}" is a reserved word')
            return

        if name not in saved_windows:
            print(f"[recall] add_alias: ABORT — name not in saved_windows")
            return

        aliases = saved_windows[name].get("aliases", [])
        if alias not in aliases:
            aliases.append(alias)
            saved_windows[name]["aliases"] = aliases
            save_to_disk()
            update_window_list()
            recall_overlay.flash(f'alias: {alias} -> {name}')

    def remove_recall_alias(alias: str):
        """Remove an alias from whichever window owns it"""
        spoken = alias.lower().strip()

        for name, info in saved_windows.items():
            aliases = info.get("aliases", [])
            matching = [a for a in aliases if a.lower() == spoken]
            if matching:
                info["aliases"] = [a for a in aliases if a.lower() != spoken]
                save_to_disk()
                update_window_list()
                recall_overlay.flash(f'removed alias: {alias} (was {name})')
                return

        recall_overlay.flash(f'"{alias}" is not an alias')

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
            _activate_persistent_highlight()
            recall_overlay.flash("recall border: ON")
        else:
            _deactivate_persistent_highlight()
            recall_overlay.flash("recall border: OFF")

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


def _on_title_change(window: ui.Window):
    """When a saved window's title changes, update the path if the new title
    contains a parseable directory.  This captures the path *before* Claude Code
    or other programs overwrite the title."""
    wid = window.id
    for name, info in saved_windows.items():
        if info["id"] == wid:
            path = _parse_title_path(window.title)
            if path and path != info.get("path"):
                info["path"] = path
                info["title"] = window.title
                save_to_disk()
            break


def on_ready():
    """Initialize on Talon startup"""
    load_saved_windows()
    ui.register("win_close", cleanup_closed_windows)
    ui.register("win_title", _on_title_change)
    ui.register("win_focus", _on_focus_change)
    ui.register("screen_change", _on_screen_change)

    # Activate persistent highlight if it was enabled before restart
    if recall_state._persistent_highlight_enabled:
        _activate_persistent_highlight()


app.register("ready", on_ready)
