"""Command Surfacer -- main module with actions, settings, and orchestration.

Passive HUD panel that surfaces voice commands the user has built,
with one-line descriptions. Rotates every 45 seconds, auto-hides
after 15 seconds, voice-controlled.
"""

from talon import Context, Module, actions, app, cron, registry, scope, settings

from .command_surfacer_canvas import CommandSurfacerCanvas
from .command_surfacer_state import CommandSurfacerState

mod = Module()

mod.setting(
    "command_surfacer_enabled",
    type=bool,
    default=True,
    desc="Enable command surfacer HUD",
)
mod.setting(
    "command_surfacer_interval",
    type=int,
    default=45,
    desc="Seconds between command rotations",
)

mod.list(
    "command_surfacer_commands",
    desc="Voice commands with descriptions for surfacer",
)

ctx = Context()

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_state = CommandSurfacerState()
_canvas = CommandSurfacerCanvas(_state)
_cron_job = None
_paused = False


def _is_sleep_mode() -> bool:
    """Check if Talon is currently in sleep mode."""
    modes = scope.get("mode", [])
    return "sleep" in modes


def _start_cron():
    """Start the rotation cron job."""
    global _cron_job
    if _cron_job is not None:
        return
    interval_s = settings.get("user.command_surfacer_interval")
    _cron_job = cron.interval(f"{interval_s}s", _rotate)


def _stop_cron():
    """Stop the rotation cron job."""
    global _cron_job
    if _cron_job is not None:
        cron.cancel(_cron_job)
        _cron_job = None


def _rotate():
    """Called by cron: advance to next command and show if enabled."""
    if not settings.get("user.command_surfacer_enabled"):
        return
    if _is_sleep_mode():
        return
    _state.next_command()
    _canvas.show()


def _on_update_contexts():
    """React to mode changes: pause in sleep, resume on wake."""
    global _paused
    if _is_sleep_mode():
        if not _paused:
            _paused = True
            _canvas.hide()
            _stop_cron()
    else:
        if _paused:
            _paused = False
            if settings.get("user.command_surfacer_enabled"):
                _start_cron()


def on_ready():
    """Initialize on Talon ready: load commands, register listeners, start cron."""
    # Load commands from the talon-list via registry
    commands = registry.lists.get("user.command_surfacer_commands", [{}])
    if commands:
        # registry.lists returns a list of dicts; take the first (latest)
        _state.load_commands(commands[0] if isinstance(commands[0], dict) else {})

    registry.register("update_contexts", _on_update_contexts)

    if settings.get("user.command_surfacer_enabled") and not _is_sleep_mode():
        _start_cron()


app.register("ready", on_ready)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
@mod.action_class
class Actions:
    def command_surfacer_show():
        """Show the command surfacer panel with the current command."""
        if _state.count() == 0:
            return
        _canvas.show()
        _start_cron()

    def command_surfacer_hide():
        """Hide the command surfacer panel and stop rotation."""
        _canvas.hide()
        _stop_cron()

    def command_surfacer_next():
        """Advance to the next command and refresh the panel."""
        if _state.count() == 0:
            return
        _state.next_command()
        _canvas.show()
