"""Activity monitor — voice-triggered system process monitor.

Provides actions to show/hide/refresh the activity overlay and kill
processes by their displayed row number.
"""

from talon import Context, Module

from . import activity_overlay

mod = Module()
mod.tag("activity_active", desc="Activity monitor overlay is showing")

ctx = Context()


def _update_tag():
    """Sync the activity_active tag with overlay visibility."""
    if activity_overlay.is_showing():
        ctx.tags = ["user.activity_active"]
    else:
        ctx.tags = []


activity_overlay.set_on_hide(_update_tag)


@mod.action_class
class Actions:
    def activity_show():
        """Show the activity monitor overlay"""
        activity_overlay.show()
        _update_tag()

    def activity_hide():
        """Hide the activity monitor overlay"""
        activity_overlay.hide()
        _update_tag()

    def activity_refresh():
        """Refresh the activity monitor data"""
        activity_overlay.refresh()

    def activity_kill(n: int):
        """Kill process at row n (1-based) with SIGTERM"""
        success, message = activity_overlay.kill_by_index(n)
        print(f"[activity] {message}")
