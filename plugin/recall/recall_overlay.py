"""
Recall Overlay - Thin coordinator that imports and re-exports the full public API.

Shows a name tag on each saved window for 5 seconds,
triggered by "recall list" / "list recalls".
Windows that can't be found are shown in red at the top of the screen.

"recall help" shows a full-screen panel with all saved windows,
their metadata, and a command reference. Auto-hides after 30s.
"""

from .recall_overlay_flash import flash, hide_flash
from .recall_overlay_help import hide_help, show_help
from .recall_overlay_highlight import hide_highlight, highlight_window
from .recall_overlay_labels import hide_overlay, show_overlay
from .recall_overlay_persistent import (
    clear_persistent_highlight,
    hide_persistent_highlight,
    rebuild_persistent_canvas,
    show_persistent_highlight,
)
from .recall_overlay_prompt import hide_prompt, show_prompt
from .recall_overlay_status import hide_status, show_status

__all__ = [
    "show_overlay",
    "hide_overlay",
    "show_status",
    "hide_status",
    "show_help",
    "hide_help",
    "show_prompt",
    "hide_prompt",
    "flash",
    "hide_flash",
    "highlight_window",
    "hide_highlight",
    "show_persistent_highlight",
    "hide_persistent_highlight",
    "clear_persistent_highlight",
    "rebuild_persistent_canvas",
    "hide_any",
]


def hide_any():
    """Hide whichever overlay is currently active."""
    hide_overlay()
    hide_status()
    hide_help()
    hide_prompt()
