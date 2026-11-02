"""Log viewer — voice-triggered Talon log viewer overlay.

Provides actions to show/hide/refresh the log viewer and control filters.
"""

from talon import Context, Module, actions

from . import logs_overlay

mod = Module()
mod.tag("logs_active", desc="Log viewer overlay is showing")
mod.tag("logs_entry_active", desc="Log entry detail overlay is showing")
mod.tag("logs_ignore_active", desc="Log ignore list overlay is showing")

ctx = Context()


def _update_tag():
    """Sync the logs_active tag with overlay visibility."""
    if logs_overlay.is_showing():
        tags = ["user.logs_active"]
        if logs_overlay.is_detail_showing():
            mode = logs_overlay.get_detail_mode()
            if mode == "entry":
                tags.append("user.logs_entry_active")
            elif mode == "ignores":
                tags.append("user.logs_ignore_active")
        ctx.tags = tags
    else:
        ctx.tags = []


def _update_detail_tag():
    """Update tags when detail overlay state changes."""
    _update_tag()


logs_overlay.set_on_hide(_update_tag)
logs_overlay.set_detail_on_hide(_update_detail_tag)


@mod.action_class
class Actions:
    def logs_show():
        """Show the log viewer overlay"""
        logs_overlay.show()
        _update_tag()

    def logs_hide():
        """Hide the log viewer overlay"""
        logs_overlay.hide()
        _update_tag()

    def logs_refresh():
        """Refresh the log viewer data"""
        logs_overlay.refresh()

    def logs_filter_level(level: str):
        """Set minimum log level filter"""
        logs_overlay.set_filter_level(level)

    def logs_filter_category(cat: str):
        """Set category filter"""
        logs_overlay.set_filter_category(cat)

    def logs_filter_search(query: str):
        """Set search text filter"""
        logs_overlay.set_filter_search(query)

    def logs_filter_clear():
        """Reset all filters to defaults"""
        logs_overlay.clear_filters()

    def logs_ignore(n: int):
        """Ignore the selected log entry by its selector index"""
        logs_overlay.ignore_by_index(n)

    def logs_ignore_clear():
        """Clear all ignore patterns"""
        logs_overlay.clear_ignores()

    def logs_view(n: int):
        """View full detail of a log entry"""
        logs_overlay.view_by_index(n)
        _update_detail_tag()

    def logs_copy(n: int):
        """Copy a log entry to clipboard"""
        entry = logs_overlay.get_entry_for_copy(n)
        if entry:
            full_text = entry.raw
            if entry.continuation_lines:
                full_text += "\n" + "\n".join(entry.continuation_lines)
            actions.clip.set_text(full_text)

    def logs_copy_range(count: int, start: int):
        """Copy N consecutive log entries starting at the selected index"""
        entries = logs_overlay.get_entries_for_copy_range(start, count)
        if not entries:
            return
        parts = []
        for e in entries:
            full = e.raw
            if e.continuation_lines:
                full += "\n" + "\n".join(e.continuation_lines)
            parts.append(full)
        actions.clip.set_text("\n".join(parts))

    def logs_ignore_view():
        """Show the ignore patterns list"""
        logs_overlay.view_ignores()
        _update_detail_tag()

    def logs_ignore_remove(n: int):
        """Remove ignore pattern at index n"""
        logs_overlay.remove_ignore_by_index(n)

    def logs_ignore_close():
        """Close the ignore list overlay"""
        logs_overlay.close_detail()
        _update_detail_tag()
