"""Pondering mode: extended speech listening with click-to-finish.

When enabled, speech.timeout is extended so the listening window
stays open longer. A single tongue-click forces the phrase to end
by momentarily dropping the VAD timeout to near-zero, then restoring it.

Toggle with voice command: "pondering"
Visual indicator: purple bar header when active.

Pondering never touches parrot on/off or command/dictation mode —
it only rescopes the tongue-click action and adjusts VAD timeout.
"""

from talon import Module, Context, actions, clip, cron, settings, speech_system

mod = Module()

mod.tag("pondering", desc="Pondering mode — extended speech listening active")
mod.tag("pondering_listening", desc="Pondering is listening — tongue-click routes to pondering exit")

mod.setting(
    "pondering_timeout",
    type=float,
    default=59.0,
    desc="Speech timeout when pondering mode is active (seconds).",
)

mod.setting(
    "default_speech_timeout",
    type=float,
    default=0.5,
    desc="Default speech timeout to restore after pondering ends (seconds).",
)

# Pondering mode indicator color (deep purple)
PONDERING_COLOR = "7b2fff"

# State
enabled = False
exiting = False  # True when tongue click initiated exit, prevents double-exit
restore_job = None
timer_job = None
safety_job = None  # Fallback to force-clear tags if post:phrase never fires
pondering_seconds = 0
toggle_ctx = Context()
listening_ctx = Context()

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


# Override noise_tongue_click when pondering is listening (more specific than parrot_on alone)
pondering_ctx = Context()
pondering_ctx.matches = r"""
tag: user.pondering_listening
tag: user.parrot_on
mode: command
mode: dictation
"""


@pondering_ctx.action_class("user")
class PonderingUserActions:
    def noise_tongue_click():
        """Tongue click exits pondering — slam timeout low to flush speech, then restore normal"""
        global timer_job, exiting, safety_job
        if exiting:
            print("[pondering] click — passing through to repeater")
            actions.next()
            return
        print("[pondering] click — exiting pondering mode")
        exiting = True
        # Immediately release tongue-click back to repeater
        listening_ctx.tags = []
        speech_system.vad.set_timeout(0.01)
        if timer_job:
            cron.cancel(timer_job)
            timer_job = None
        actions.user.mode_indicator_clear_pondering()
        actions.user.mode_indicator_clear_color()
        # Safety net: if post:phrase doesn't fire within 2s, force-clear everything
        if safety_job:
            cron.cancel(safety_job)
        safety_job = cron.after("2s", _safety_cleanup)


def _safety_cleanup(_=None):
    """Fallback: force-clear all pondering state if post:phrase never fired.

    Only clears tags and VAD — never touches parrot or mode.
    """
    global enabled, exiting, safety_job
    safety_job = None
    if not enabled and not exiting:
        return
    print("[pondering] safety net — post:phrase never fired, force-clearing")
    try:
        speech_system.unregister("post:phrase", _on_post_phrase)
    except Exception:
        pass
    toggle_ctx.tags = []
    listening_ctx.tags = []
    enabled = False
    exiting = False
    speech_system.vad.set_timeout(settings.get("user.default_speech_timeout", 0.5))


def _tick_timer(_=None):
    global pondering_seconds
    if enabled:
        pondering_seconds += 1
        actions.user.mode_indicator_set_pondering(pondering_seconds)


_skip_next_post_phrase = False


def _on_post_phrase(d):
    """Handle phrase end during pondering — either from tongue click or natural timeout."""
    global enabled, exiting, _skip_next_post_phrase, safety_job
    if _skip_next_post_phrase:
        _skip_next_post_phrase = False
        print("[pondering] post:phrase — skipped (activation phrase)")
        return
    if not enabled and not exiting:
        return
    speech_system.unregister("post:phrase", _on_post_phrase)
    toggle_ctx.tags = []
    listening_ctx.tags = []
    enabled = False
    if safety_job:
        cron.cancel(safety_job)
        safety_job = None
    speech_system.vad.set_timeout(settings.get("user.default_speech_timeout", 0.5))
    # Check if any text was actually captured
    phrase_words = d.get("phrase", [])
    has_text = bool(phrase_words)
    if exiting:
        exiting = False
        if has_text:
            actions.key("enter")
            print(f"[pondering] post:phrase (click) — pasted, sent enter")
        else:
            print("[pondering] post:phrase (click) — no text captured, skipping enter")
    else:
        # Natural timeout — just exit the mode
        actions.user.mode_indicator_clear_pondering()
        actions.user.mode_indicator_clear_color()
        if timer_job:
            cron.cancel(timer_job)
        if has_text:
            actions.key("enter")
            print(f"[pondering] post:phrase (timeout) — sent enter")
        else:
            print("[pondering] post:phrase (timeout) — no text captured, skipping enter")


def enable():
    global enabled, exiting, timer_job, pondering_seconds, _skip_next_post_phrase
    enabled = True
    exiting = False
    _skip_next_post_phrase = True
    pondering_seconds = 0
    toggle_ctx.tags = ["user.pondering"]
    listening_ctx.tags = ["user.pondering_listening"]
    timeout = settings.get("user.pondering_timeout", 59.0)
    speech_system.vad.set_timeout(timeout)
    actions.user.mode_indicator_set_color(PONDERING_COLOR)
    actions.user.mode_indicator_set_pondering(0)
    timer_job = cron.interval("1s", _tick_timer)
    speech_system.register("post:phrase", _on_post_phrase)


def disable():
    global enabled, exiting, restore_job, timer_job, safety_job
    enabled = False
    exiting = False
    toggle_ctx.tags = []
    listening_ctx.tags = []
    if safety_job:
        cron.cancel(safety_job)
        safety_job = None
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
    speech_system.vad.set_timeout(settings.get("user.default_speech_timeout", 0.5))
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
