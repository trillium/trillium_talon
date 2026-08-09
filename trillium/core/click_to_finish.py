"""Pondering mode: block Talon command recognition, defer to SuperWhisper.

When enabled, fully disables Talon speech (speech.disable → mode:sleep) so Talon
takes NO action on anything spoken; SuperWhisper becomes the sole listener.

Entry:  voice "pondering" (Talon opens SuperWhisper for you), or physically
        pressing the SuperWhisper hotkey — observed *passively* so it falls
        through to SuperWhisper while Talon just syncs pondering state.
Exit:   the tongue-click parrot sound (finish), pressing the SuperWhisper hotkey
        again, "stop pondering" (only if speech is on), or Escape. NOTE: cmere no
        longer exits — it is the re-enter sound and is inert while pondering.
Visual indicator: purple bar header + timer while active.

Sound-only submit / re-enter (task-rg2q + task-1rxa) — built on repeater.py's
NATIVE "line up the next action" facility, not a custom state machine:

    (pondering) tongue-click -> finish pondering + write text
    On finish we LINE UP the next repeat/opposite actions via repeater:
        next tongue-click (repeat)  -> submit (default: key Enter)
        next cmere       (opposite) -> re-enter pondering
    So click-click submits and leaves pondering; the opposite sound (cmere)
    drops you back into pondering. repeater executes the lined-up action with
    its own handler, so there is no competing context to lose — the earlier
    tag-gated override kept losing the tongue-click to repeater's repeat.
"""

from talon import Module, Context, actions, cron, scope

mod = Module()

mod.tag("pondering", desc="Pondering mode — command recognition blocked, SuperWhisper active")

# Pondering mode indicator color (deep purple)
PONDERING_COLOR = "7b2fff"

# SuperWhisper activation/submit hotkey — pressing it again submits the dictation.
SUPERWHISPER_TOGGLE_KEY = "ctrl-alt-cmd-shift-space"

# What the lined-up "submit" (next tongue-click after a finish) presses. Defaults
# to Enter; a voice command can SET/REPEAT it (Talon-repeat style).
DEFAULT_SUBMIT_KEY = "enter"
_submit_key = DEFAULT_SUBMIT_KEY

# Debounce so an accidental fast double tongue-click can't double-submit.
SUBMIT_DEBOUNCE_S = 1.0

# State
enabled = False
toggle_ctx = Context()

# Whether pondering was entered while Talon was asleep. On exit we restore the
# pre-entry state — sleep stays sleep, command mode stays command mode — instead
# of always bouncing back to command mode.
_entered_from_sleep = False

# When WE synthesize the SuperWhisper key (voice/sound/toggle paths), this
# suppresses the passive hotkey observer briefly so our own key event isn't
# mistaken for a physical press and doesn't re-toggle pondering.
_suppress_hotkey = False


def _clear_suppress():
    global _suppress_hotkey
    _suppress_hotkey = False


def _submit_superwhisper():
    """Synthesize the SuperWhisper toggle key (paths with no physical press).

    Guards the passive hotkey observer so this synthesized event doesn't get
    read back as a user press and flip pondering the wrong way.
    """
    global _suppress_hotkey
    _suppress_hotkey = True
    actions.key(SUPERWHISPER_TOGGLE_KEY)
    cron.after("300ms", _clear_suppress)


# Context for pondering-scoped noise overrides. Two match clauses so it beats
# parrot.py's single-tag base handler; repeater.py's repeat/reverse overrides
# require mode:command/dictation and can't match here (pondering == mode:sleep).
noise_ctx = Context()
noise_ctx.matches = r"""
mode: sleep
and tag: user.pondering
"""


def enable():
    """Enter pondering — pure state, NO SuperWhisper key.

    The voice path relays the key via _submit_superwhisper(); the passive
    hotkey path relies on the physical press falling through to SuperWhisper.
    """
    global enabled, _entered_from_sleep
    # Capture the mode BEFORE speech.disable() drops us into mode:sleep — on
    # exit we restore whichever state we came from (sleep vs command mode).
    _entered_from_sleep = "sleep" in scope.get("mode", set())
    enabled = True
    toggle_ctx.tags = ["user.pondering"]
    actions.speech.disable()
    actions.user.mode_indicator_set_color(PONDERING_COLOR)
    actions.user.mode_indicator_set_pondering(0)
    print("[pondering] enabled — Talon speech disabled")


def disable():
    """Exit pondering — pure state, NO SuperWhisper key."""
    global enabled, _entered_from_sleep
    enabled = False
    toggle_ctx.tags = []
    actions.speech.enable()
    if _entered_from_sleep:
        # Started asleep (e.g. via repeater's sleep sound) — return to sleep,
        # not command mode.
        actions.speech.disable()
    else:
        actions.user.command_mode()
    _entered_from_sleep = False
    actions.user.mode_indicator_clear_pondering()
    actions.user.mode_indicator_clear_color()
    print("[pondering] disabled — Talon speech restored")


@mod.action_class
class Actions:
    def pondering_toggle():
        """Toggle pondering (voice/programmatic — drives SuperWhisper via key)"""
        if enabled:
            _submit_superwhisper()
            disable()
        else:
            enable()
            _submit_superwhisper()

    def pondering_enable():
        """Enable pondering (voice) — Talon opens SuperWhisper for you"""
        enable()
        _submit_superwhisper()

    def pondering_disable():
        """Disable pondering mode"""
        disable()

    def click_submit_now():
        """Press the lined-up submit key (default Enter). This is the action a
        follow-up tongue-click fires via repeater's repeat override."""
        if _submit_key:
            actions.key(_submit_key)
            print(f"[click] submit -> key({_submit_key})")

    def click_submit_key_set(keys: str):
        """Set what the follow-up click submits (Talon key sequence, e.g. 'enter')"""
        global _submit_key
        _submit_key = keys
        print(f"[click] submit key set to key({keys})")

    def click_submit_key_reset():
        """Reset the follow-up-click submit key to the default (Enter)"""
        global _submit_key
        _submit_key = DEFAULT_SUBMIT_KEY
        print(f"[click] submit key reset to key({DEFAULT_SUBMIT_KEY})")

    def pondering_hotkey():
        """Physical SuperWhisper hotkey observed passively — sync pondering only.

        The key is bound with `:passive`, so it falls through to SuperWhisper on
        its own; Talon does NOT relay a key here. We ignore the event if we just
        synthesized it ourselves (voice/sound paths).
        """
        if _suppress_hotkey:
            return
        if enabled:
            disable()
        else:
            enable()


def _arm_followups():
    """Arm the lined-up follow-up sounds via repeater's native override facility:
      • repeat sound (next tongue-click) -> user.click_submit_now (press Enter)
      • opposite sound (next cmere)      -> user.pondering_enable (re-dictate)
    repeater runs the lined-up action with its own handler, so no competing
    context can steal the sound.

    These persist deterministically — NOT time-gated. repeater's `on_post_phrase`
    only clears overrides when the last command is *trackable*, and the commands
    that fire around a pondering finish (`<phrase>` raw dictation, `pondering …`)
    are excluded from tracking in repeater/excluded_commands.csv. So the override
    survives until the user's next sound, however long that takes (hands-free
    friendly). A real spoken command still clears them, as intended.
    """
    actions.user.set_next_repeat_action("user", "click_submit_now", [], SUBMIT_DEBOUNCE_S)
    print("[click] armed repeat -> user.click_submit_now")
    actions.user.set_next_opposite_action("user", "pondering_enable", [])
    print("[click] armed opposite -> user.pondering_enable")


def _submit_and_exit():
    """Finish: submit the in-progress SuperWhisper dictation, leave pondering, then
    arm the follow-up sounds (submit / re-enter) — synchronously, since the
    dictation `<phrase>` that used to clear them is now excluded from tracking.

    The dictated text is now in the input box (SuperWhisper submit lands text but
    does NOT submit the form).
    """
    _submit_superwhisper()
    disable()
    _arm_followups()


@noise_ctx.action_class("user")
class PonderingNoiseActions:
    # While pondering, the tongue-click is the hands-free finish: submit
    # SuperWhisper + end pondering, then line up the follow-up submit / re-enter
    # actions (see _submit_and_exit).
    def noise_tongue_click():
        print("[pondering] tongue-click — submit SuperWhisper + exit pondering")
        _submit_and_exit()

    # cmere is the RE-ENTER sound (fired via repeater's opposite override when NOT
    # pondering). While pondering it must be inert — otherwise repeating cmere
    # toggles pondering off, which Trillium depends on staying on. So we swallow
    # it here (no exit) instead of finishing.
    def noise_cmere():
        print("[pondering] cmere — ignored (re-enter sound; does not end pondering)")
