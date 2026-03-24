"""Pondering mode: extended speech listening with click-to-finish.

When enabled, speech.timeout is extended so the listening window
stays open longer. A single tongue-click forces the phrase to end
by momentarily dropping the VAD timeout to near-zero, then restoring it.

Toggle with voice command: "pondering"
Visual indicator: purple bar header when active.
"""

from talon import Module, Context, actions, clip, cron, scope, settings, speech_system

mod = Module()

mod.tag("pondering", desc="Pondering mode — tongue-click ends the speech listening window")

mod.setting(
    "pondering_timeout",
    type=float,
    default=59.0,
    desc="Speech timeout when pondering mode is active (seconds).",
)

# Pondering mode indicator color (deep purple)
PONDERING_COLOR = "7b2fff"

# State
enabled = False
exiting = False  # True when tongue click initiated exit, prevents double-exit
parrot_was_on = False
restore_job = None
timer_job = None
pondering_seconds = 0
toggle_ctx = Context()

# Override dictation_insert in pondering context to use clipboard paste (faster)
pondering_dictation_ctx = Context()
pondering_dictation_ctx.matches = r"""
tag: user.pondering
"""


@pondering_dictation_ctx.action_class("user")
class PonderingDictationActions:
    def insert_between(before: str, after: str):
        """Paste text via clipboard instead of typing keystrokes."""
        text = f"{before}{after}"
        if text:
            with clip.revert():
                clip.set_text(text)
                actions.edit.paste()
                actions.sleep("150ms")
            for _ in after:
                actions.edit.left()
        print(f"[pondering] pasted {len(text)} chars via clipboard")


# Override noise_tongue_click in pondering context (more specific than parrot_on alone)
pondering_ctx = Context()
pondering_ctx.matches = r"""
tag: user.pondering
tag: user.parrot_on
mode: command
mode: dictation
"""


@pondering_ctx.action_class("user")
class PonderingUserActions:
    def noise_tongue_click():
        """Tongue click exits pondering — slam timeout low to flush speech, then restore normal"""
        global timer_job, exiting
        print("[pondering] click — exiting pondering mode")
        exiting = True
        speech_system.vad.set_timeout(0.01)
        # Keep pondering tag active until post:phrase so clipboard paste override stays matched
        if timer_job:
            cron.cancel(timer_job)
            timer_job = None
        actions.user.mode_indicator_clear_pondering()
        actions.user.mode_indicator_clear_color()


def _tick_timer(_=None):
    global pondering_seconds
    if enabled:
        pondering_seconds += 1
        actions.user.mode_indicator_set_pondering(pondering_seconds)


_skip_next_post_phrase = False


def _on_post_phrase(d):
    """Handle phrase end during pondering — either from tongue click or natural timeout."""
    global enabled, exiting, _skip_next_post_phrase
    if _skip_next_post_phrase:
        _skip_next_post_phrase = False
        print("[pondering] post:phrase — skipped (activation phrase)")
        return
    if not enabled and not exiting:
        return
    speech_system.unregister("post:phrase", _on_post_phrase)
    toggle_ctx.tags = []
    enabled = False
    speech_system.vad.set_timeout(0.3)
    if not parrot_was_on:
        actions.user.parrot_disable()
    if exiting:
        # Tongue click exit — send enter after paste
        exiting = False
        actions.key("enter")
        print("[pondering] post:phrase (click) — pasted, sent enter, restored 0.3s")
    else:
        # Natural timeout — just exit the mode
        actions.user.mode_indicator_clear_pondering()
        actions.user.mode_indicator_clear_color()
        if timer_job:
            cron.cancel(timer_job)
        actions.key("enter")
        print("[pondering] post:phrase (timeout) — exited, sent enter, restored 0.3s")


def enable():
    global enabled, exiting, parrot_was_on, timer_job, pondering_seconds, _skip_next_post_phrase
    enabled = True
    exiting = False
    _skip_next_post_phrase = True
    pondering_seconds = 0
    parrot_was_on = "user.parrot_on" in scope.get("tag", [])
    if not parrot_was_on:
        actions.user.parrot_enable()
    toggle_ctx.tags = ["user.pondering"]
    timeout = settings.get("user.pondering_timeout", 59.0)
    speech_system.vad.set_timeout(timeout)
    actions.user.mode_indicator_set_color(PONDERING_COLOR)
    actions.user.mode_indicator_set_pondering(0)
    timer_job = cron.interval("1s", _tick_timer)
    speech_system.register("post:phrase", _on_post_phrase)


def disable():
    global enabled, exiting, restore_job, timer_job
    enabled = False
    exiting = False
    toggle_ctx.tags = []
    if restore_job:
        cron.cancel(restore_job)
        restore_job = None
    if timer_job:
        cron.cancel(timer_job)
        timer_job = None
    try:
        speech_system.unregister("post:phrase", _on_post_phrase)
    except Exception:
        pass
    speech_system.vad.set_timeout(0.3)
    if not parrot_was_on:
        actions.user.parrot_disable()
    actions.user.mode_indicator_clear_pondering()
    actions.user.mode_indicator_clear_color()


def end_phrase():
    """Single click — force phrase end."""
    global restore_job

    print("[pondering] click — forcing phrase end")

    speech_system.vad.set_timeout(0.01)

    if restore_job:
        cron.cancel(restore_job)

    def restore(_=None):
        global restore_job
        restore_job = None
        if enabled:
            timeout = settings.get("user.pondering_timeout", 5.0)
            speech_system.vad.set_timeout(timeout)
            print(f"[pondering] timeout restored to {timeout}s")

    restore_job = cron.after("300ms", restore)


@mod.action_class
class Actions:
    def pondering_toggle():
        """Toggle pondering mode"""
        if enabled:
            disable()
        else:
            enable()

    def pondering_enable():
        """Enable pondering mode"""
        enable()

    def pondering_disable():
        """Disable pondering mode"""
        disable()

    def pondering_end_phrase():
        """Force end the current phrase"""
        end_phrase()
