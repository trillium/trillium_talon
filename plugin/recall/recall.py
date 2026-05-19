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

from talon import actions, app, ui
from . import recall_overlay
from . import recall_state
from .recall_state import (
    mod, saved_windows,
    _cancel_pending, find_name_for_window_id,
    load_saved_windows,
)
from .recall_terminal import is_terminal, _parse_title_path
from .recall_commands import find_window_by_id, rematch_window
from .recall_save import archive_window, cleanup_closed_windows  # noqa: F401

# Import split action modules so Talon picks up their @mod.action_class registrations
from . import recall_save    # noqa: F401
from . import recall_revive  # noqa: F401
from . import recall_alias   # noqa: F401
from . import recall_meta    # noqa: F401


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
            from .recall_state import save_to_disk
            info["id"] = wid
            info["title"] = window.title
            save_to_disk()
            break


def _on_focus_change(window: ui.Window):
    """When focus changes, try auto-assign and update persistent highlight."""
    try:
        app_name = window.app.name
        print(f"[recall-debug] focus_change: id={window.id}, app='{app_name}', title='{window.title[:60]}'")
    except Exception:
        print(f"[recall-debug] focus_change: (could not read window properties)")
        app_name = ""
    # Ignore Talon's own canvas windows — they fire focus events when
    # overlay canvases are created/clicked, causing wrong-window cascades.
    if app_name == "Talon":
        print(f"[recall-debug]   -> ignoring Talon canvas focus event")
        return
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


@mod.action_class
class Actions:
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
                from .recall_state import save_to_disk
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
                from .recall_state import save_to_disk
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


def _on_title_change(window: ui.Window):
    """When a saved window's title changes, update the path if the new title
    contains a parseable directory.  This captures the path *before* Claude Code
    or other programs overwrite the title."""
    from .recall_state import save_to_disk
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
