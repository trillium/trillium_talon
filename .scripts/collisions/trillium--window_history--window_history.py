"""
Window History - Automatic tracking of window focus changes

Tracks the last focused window so "lasty" can return to the exact
previous window, not just the previous application.
"""

from talon import Module, Context, actions, app, ui

mod = Module()
ctx = Context()

# Track the last two windows: [current, previous]
window_history = []


def find_window_by_id(window_id: int) -> ui.Window:
    """Find a window by its ID across all apps"""
    for app_item in ui.apps(background=False):
        for window in app_item.windows():
            if window.id == window_id:
                return window
    return None


def on_window_focus(window: ui.Window):
    """Track window focus changes"""
    global window_history

    # Don't track if it's the same window
    if window_history and window_history[0] == window.id:
        return

    # Update history: add new window and keep only last 2
    window_history.insert(0, window.id)
    window_history = window_history[:2]


def on_window_close(window: ui.Window):
    """Remove closed windows from history"""
    global window_history

    # Remove the closed window from history
    window_history = [wid for wid in window_history if wid != window.id]


@mod.action_class
class Actions:
    def switcher_focus_last_window():
        """Focus the exact previous window (not just previous app)"""
        global window_history

        # Need at least 2 windows in history
        if len(window_history) < 2:
            actions.key("cmd-tab")
            return

        # Get the previous window (index 1, since index 0 is current)
        previous_window_id = window_history[1]
        previous_window = find_window_by_id(previous_window_id)

        if previous_window is None:
            # Clean up history and fall back to Cmd+Tab
            window_history = [window_history[0]] if window_history else []
            actions.key("cmd-tab")
            return

        try:
            # Use the existing switcher_focus_window action
            actions.user.switcher_focus_window(previous_window)
        except Exception:
            # Fall back to Cmd+Tab if focusing fails
            actions.key("cmd-tab")


def on_ready():
    """Initialize on Talon startup"""
    # Register event handlers
    ui.register("win_focus", on_window_focus)
    ui.register("win_close", on_window_close)

    # Initialize with current active window
    try:
        current = ui.active_window()
        window_history.append(current.id)
    except Exception:
        pass


app.register("ready", on_ready)
