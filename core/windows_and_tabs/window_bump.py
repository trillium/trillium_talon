"""Bump, widen, and narrow the active window in small steps.

Activated automatically after any snap or recall command. Deactivates after
60 seconds or when any unrelated command is spoken.
"""

from talon import Context, Module, actions, cron, settings, speech_system, ui

mod = Module()
mod.tag("window_bumping", desc="Active after a snap/move command, enables bump/widen/narrow commands")
mod.setting(
    "window_bump_step",
    type=float,
    default=0.03,
    desc="Fraction of screen width per bump step (default 0.03 = 3%)",
)
mod.setting(
    "window_resize_step",
    type=float,
    default=0.03,
    desc="Fraction of screen width per widen/narrow step (default 0.03 = 3%)",
)

BUMP_TIMEOUT_S = 60

_timeout_job = None
_just_activated = False
ctx = Context()


def _bump_step():
    return settings.get("user.window_bump_step")


def _resize_step():
    return settings.get("user.window_resize_step")


def _activate():
    global _timeout_job, _just_activated
    _just_activated = True
    ctx.tags = ["user.window_bumping"]
    if _timeout_job:
        cron.cancel(_timeout_job)
    _timeout_job = cron.after(f"{BUMP_TIMEOUT_S}s", _deactivate)


def _deactivate():
    global _timeout_job
    ctx.tags = []
    if _timeout_job:
        cron.cancel(_timeout_job)
        _timeout_job = None


def _on_post_phrase(phrase):
    """Deactivate bumping if the user speaks a non-bump, non-snap command."""
    global _just_activated
    if "user.window_bumping" not in ctx.tags:
        return
    # Skip the phrase that just activated us (the snap command itself)
    if _just_activated:
        _just_activated = False
        return
    try:
        last_cmd, _ = actions.core.last_command()
    except (IndexError, Exception):
        return
    trigger = last_cmd.trigger or "" if last_cmd else ""
    # Stay active for bump/widen/narrow and snap commands
    if "window_bump" in trigger or "window_resize" in trigger or "snap" in trigger:
        return
    _deactivate()


speech_system.register("post:phrase", _on_post_phrase)


@mod.action_class
class Actions:
    def window_bump_activate():
        """Activate window bumping mode after a snap/move command."""
        _activate()

    def window_bump_show_settings():
        """Show the window bump settings overlay."""
        from . import window_bump_overlay
        window_bump_overlay.show()

    def window_bump(direction: str, steps: int = 1):
        """Bump the active window left or right by a percentage of screen width."""
        window = ui.active_window()
        screen = window.screen.visible_rect
        offset = round(screen.width * _bump_step() * steps)

        rect = window.rect
        if direction == "left":
            new_x = rect.x - offset
        elif direction == "right":
            new_x = rect.x + offset
        else:
            return

        window.rect = ui.Rect(round(new_x), round(rect.y), round(rect.width), round(rect.height))
        _activate()

    def window_resize(direction: str, steps: int = 1):
        """Widen or narrow the window symmetrically by a percentage of screen width."""
        window = ui.active_window()
        screen = window.screen.visible_rect
        delta = round(screen.width * _resize_step() * steps)

        rect = window.rect
        if direction == "widen":
            new_width = rect.width + delta * 2
        elif direction == "narrow":
            new_width = rect.width - delta * 2
            if new_width < 100:
                return
        else:
            return

        # Test if the OS will actually accept the new width before moving x
        window.rect = ui.Rect(round(rect.x), round(rect.y), round(new_width), round(rect.height))
        actual_width = window.rect.width
        if abs(actual_width - rect.width) < 2:
            # OS refused the resize — restore and bail
            window.rect = rect
            return

        # Width changed, now center the window around the new width
        width_change = actual_width - rect.width
        new_x = rect.x - round(width_change / 2)
        window.rect = ui.Rect(round(new_x), round(rect.y), round(actual_width), round(rect.height))
        _activate()
