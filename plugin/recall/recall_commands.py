"""
Recall Commands - Command resolution and window finding

Stateless utilities for:
- Finding windows by ID or re-matching by app/title/path
- Resolving stored command names to shell commands
- Polling a terminal until ready, then typing a command
"""

from talon import actions, cron, ui
from .recall_state import ctx


def find_window_by_id(window_id: int) -> ui.Window:
    """Find a window by its ID across all apps"""
    if window_id is None:
        return None
    for a in ui.apps(background=False):
        for window in a.windows():
            if window.id == window_id:
                return window
    return None


def rematch_window(info: dict) -> ui.Window:
    """Try to re-match a saved window by app name and path/title.
    Returns the matched window or None."""
    app_name = info.get("app")
    saved_path = info.get("path")
    saved_title = info.get("title", "")

    for a in ui.apps(background=False):
        if a.name != app_name:
            continue
        for window in a.windows():
            if window.rect.width <= 0 or window.rect.height <= 0:
                continue
            # Match by path in title
            if saved_path and saved_path in window.title:
                return window
            # Match by title prefix
            if saved_title and window.title.startswith(saved_title):
                return window
    return None


def _resolve_command(stored: str) -> str | None:
    """Resolve a stored command to its shell command from the recall_commands list.
    The stored value can be either a spoken name (key) or a shell command (value).
    Tries key lookup first, then reverse lookup by value, then treats it as a
    literal shell command."""
    commands = ctx.lists.get("user.recall_commands", {})
    # Try as spoken name first (key -> value)
    if stored in commands:
        return commands[stored]
    # Try reverse lookup (maybe stored as the old resolved value)
    for spoken, shell_cmd in commands.items():
        if shell_cmd == stored:
            return shell_cmd
    # Not in the list — treat as a literal shell command
    return stored


def _run_when_ready(window: ui.Window, command: str, path: str = None):
    """Type a command into a terminal window.
    If path is provided, prepends cd to ensure correct directory."""
    if path:
        full_cmd = f"cd {path} && {command}"
    else:
        full_cmd = command
    actions.user.switcher_focus_window(window)
    actions.sleep("50ms")
    actions.insert(full_cmd)
    actions.key("enter")
