"""Microphone selection voice command actions."""
from talon import Module

from . import microphone_selection_overlay

mod = Module()


@mod.action_class
class Actions:
    def microphone_selection_toggle():
        """Show or hide the microphone selection overlay"""
        if microphone_selection_overlay.is_showing():
            microphone_selection_overlay.hide()
        else:
            microphone_selection_overlay.show()

    def microphone_selection_hide():
        """Hide the microphone selection overlay"""
        microphone_selection_overlay.hide()

    def microphone_select(index: int):
        """Select a microphone by 0-based index from the overlay"""
        microphone_selection_overlay.select(index)

    def microphone_exclude(index: int):
        """Exclude a microphone by 0-based index from the overlay"""
        microphone_selection_overlay.exclude_by_index(index)

    def microphone_include(index: int):
        """Re-include an excluded microphone by 0-based index"""
        microphone_selection_overlay.include_by_index(index)

    def microphone_exclude_reset():
        """Remove all dynamic microphone exclusions"""
        microphone_selection_overlay.reset_exclusions()
