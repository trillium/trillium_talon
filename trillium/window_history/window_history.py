"""
Window History - Automatic tracking of window focus changes

Tracks the last focused window so "lasty" can return to the exact
previous window, not just the previous application. Saying "next"
after "lasty" steps further back through the history, "previous"
steps back toward more recent.

The history array mutates on every focus (on_window_focus inserts at
front), so we use index arithmetic rather than freezing the array:
  Forward:  index = (depth + 1) + total_navs
  Backward: index = total_navs - (depth - 1)
"""

from talon import Module, Context, actions, app, cron, ui

from . import window_overlay

mod = Module()
mod.tag("window_browsing", desc="Active after lasty — 'next'/'previous' navigate window history")

toggle_ctx = Context()

# Track recent windows: index 0 = current, 1 = previous, etc.
# Sized large enough to survive index growth from navigation insertions.
HISTORY_SIZE = 30
window_history = []

# Browsing state
_depth = 0          # position in the original history (0 = starting window)
_total_navs = 0     # number of focus changes since lasty
_timeout_job = None
BROWSE_TIMEOUT_MS = 3500


def find_window_by_id(window_id: int) -> ui.Window:
    """Find a window by its ID across all apps"""
    for app_item in ui.apps(background=False):
        for window in app_item.windows():
            if window.id == window_id:
                return window
    return None


def _focus_at_index(index: int) -> bool:
    """Focus the window at the given history index. Returns True on success."""
    if index < 0 or index >= len(window_history):
        return False
    target_id = window_history[index]
    target = find_window_by_id(target_id)
    if target is None:
        return False
    try:
        actions.user.switcher_focus_window(target)
        return True
    except Exception:
        return False


def _set_repeater_overrides():
    """Wire pop=next, cmere=previous for sound-based navigation."""
    try:
        actions.user.set_next_repeat_action("user", "window_browse_next")
        actions.user.set_next_opposite_action("user", "window_browse_previous")
    except Exception:
        pass


def _reset_timeout():
    """Reset the browsing auto-exit timer."""
    global _timeout_job
    if _timeout_job:
        cron.cancel(_timeout_job)
    _timeout_job = cron.after(f"{BROWSE_TIMEOUT_MS}ms", _stop_browsing)


def _overlay_show():
    """Show the window overlay with current state."""
    window_overlay.show(window_history, _depth, _total_navs, find_window_by_id)


def _overlay_refresh():
    """Refresh the window overlay with current state."""
    window_overlay.refresh(window_history, _depth, _total_navs, find_window_by_id)


def _start_browsing():
    """Enter browsing mode."""
    global _depth, _total_navs
    _depth = 0
    _total_navs = 0
    toggle_ctx.tags = ["user.window_browsing"]


def _stop_browsing():
    """Exit browsing mode."""
    global _depth, _total_navs, _timeout_job
    _depth = 0
    _total_navs = 0
    _timeout_job = None
    toggle_ctx.tags = []
    window_overlay.hide()


def on_window_focus(window: ui.Window):
    """Track window focus changes"""
    global window_history

    # Don't track if it's the same window
    if window_history and window_history[0] == window.id:
        return

    window_history.insert(0, window.id)
    window_history[:] = window_history[:HISTORY_SIZE]


def on_window_close(window: ui.Window):
    """Remove closed windows from history"""
    global window_history
    window_history = [wid for wid in window_history if wid != window.id]


@mod.action_class
class Actions:
    def switcher_focus_last_window():
        """Focus the exact previous window (not just previous app)"""
        if len(window_history) < 2:
            actions.key("cmd-tab")
            return

        previous_window_id = window_history[1]
        previous_window = find_window_by_id(previous_window_id)

        if previous_window is None:
            window_history[:] = [window_history[0]] if window_history else []
            actions.key("cmd-tab")
            return

        _start_browsing()

        try:
            actions.user.switcher_focus_window(previous_window)
        except Exception:
            _stop_browsing()
            actions.key("cmd-tab")
            return

        global _depth, _total_navs
        _depth = 1
        _total_navs = 1
        _reset_timeout()
        _set_repeater_overrides()
        _overlay_show()

    def window_browse_next():
        """Step one further back in window history"""
        global _depth, _total_navs
        index = (_depth + 1) + _total_navs
        if not _focus_at_index(index):
            return
        _depth += 1
        _total_navs += 1
        _reset_timeout()
        _set_repeater_overrides()
        _overlay_refresh()

    def window_browse_previous():
        """Step one forward (more recent) in window history"""
        global _depth, _total_navs
        if _depth <= 1:
            # Back to starting window
            index = _total_navs
            _focus_at_index(index)
            _stop_browsing()
            return
        index = _total_navs - (_depth - 1)
        if not _focus_at_index(index):
            return
        _depth -= 1
        _total_navs += 1
        _reset_timeout()
        _set_repeater_overrides()
        _overlay_refresh()

    def window_browse_stop():
        """Exit window browsing mode"""
        _stop_browsing()


def on_ready():
    """Initialize on Talon startup"""
    ui.register("win_focus", on_window_focus)
    ui.register("win_close", on_window_close)

    try:
        current = ui.active_window()
        window_history.append(current.id)
    except Exception:
        pass


app.register("ready", on_ready)
