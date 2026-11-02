"""Command Surfacer Canvas -- lifecycle management for the overlay canvas.

Thin DismissibleOverlay wrapper matching prose_overlay_canvas.py pattern.
Non-interactive: blocks_mouse=False so the user can click through.
Auto-hides after 15 seconds.
"""

from talon import actions
from talon.skia.canvas import Canvas as SkiaCanvas

from trillium.utils.overlay_kit import DismissibleOverlay

from .command_surfacer_draw import draw_panel
from .command_surfacer_state import CommandSurfacerState


class CommandSurfacerCanvas:
    """Manages the Talon canvas that renders the command surfacer panel.

    Wraps DismissibleOverlay for click-outside dismiss and auto-hide.
    """

    def __init__(self, state: CommandSurfacerState):
        self._state = state
        self._overlay = DismissibleOverlay(
            on_draw=self._on_draw,
            auto_hide="15s",
            close_hint_text='"hide commands"',
            close_hint_size=9,
            close_hint_color="666677cc",
            on_hide=self._handle_hide,
            blocks_mouse=False,
        )

    @property
    def is_showing(self) -> bool:
        return self._overlay.is_showing

    def show(self):
        """Create and show the canvas overlay."""
        if self._overlay.is_showing:
            self.refresh()
            return
        self._overlay.show()

    def refresh(self):
        """Re-freeze the canvas to trigger a redraw with current state."""
        self._overlay.freeze()

    def hide(self):
        """Tear down the canvas."""
        self._overlay.hide()

    def _handle_hide(self):
        """Called by DismissibleOverlay when dismissed (click-outside or auto-hide)."""
        actions.user.command_surfacer_hide()

    def _on_draw(self, c: SkiaCanvas, overlay: DismissibleOverlay):
        """Draw callback: delegates to the draw module, reports panel rect."""
        cmd = self._state.current_command()
        if cmd is None:
            return
        phrase, description = cmd
        panel_rect = draw_panel(
            c, phrase, description, self._state.index(), self._state.count()
        )
        if panel_rect:
            overlay.set_panel_rect(panel_rect)
