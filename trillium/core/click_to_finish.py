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

import re
import time

from talon import Context, Module, actions, cron, scope, ui

mod = Module()

mod.tag(
    "sleep_cmere_relaunches_pondering",
    desc="OPT-IN (off by default): while asleep, kitty-cmere consumes the armed opposite action / re-launches pondering (opens SuperWhisper). Enable with tag(): in a .talon file.",
)

mod.tag(
    "pondering",
    desc="Pondering mode — command recognition blocked, SuperWhisper active",
)

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

# When WE synthesize the SuperWhisper key (voice/sound/toggle paths), the passive
# hotkey observer is ignored until this monotonic deadline so our own key event
# isn't mistaken for a physical press and doesn't re-toggle pondering. A time
# window (not a cron-cleared flag) so back-to-back synthesized keys just extend it.
SUPPRESS_HOTKEY_S = 0.8
_suppress_until = 0.0

# Noise events can arrive twice a few ms apart (see task-umnrph). Ignore a repeat
# of the same handler inside this window so one sound = one action.
NOISE_DEBOUNCE_S = 0.4
_last_fired: dict = {}

# Lined-up follow-ups (click->Enter, cmere->pondering) expire after this long and
# are cleared as soon as one is used, so a stale arm can't hijack a later sound.
FOLLOWUP_TTL = "9s"
_followup_job = None


def _debounced(key: str) -> bool:
    """True if `key` already fired within NOISE_DEBOUNCE_S (caller should skip)."""
    now = time.monotonic()
    if now - _last_fired.get(key, -1e9) < NOISE_DEBOUNCE_S:
        print(f"[pondering] {key} ignored — duplicate within {NOISE_DEBOUNCE_S}s")
        return True
    _last_fired[key] = now
    return False


def _submit_superwhisper():
    """Synthesize the SuperWhisper toggle key (paths with no physical press).

    Guards the passive hotkey observer so this synthesized event doesn't get
    read back as a user press and flip pondering the wrong way. The guard is
    armed before the key and held for SUPPRESS_HOTKEY_S after it.
    """
    global _suppress_until
    _suppress_until = time.monotonic() + SUPPRESS_HOTKEY_S
    actions.key(SUPERWHISPER_TOGGLE_KEY)
    _suppress_until = time.monotonic() + SUPPRESS_HOTKEY_S


# Context for pondering-scoped noise overrides. Two match clauses so it beats
# parrot.py's single-tag base handler; repeater.py's repeat/reverse overrides
# require mode:command/dictation and can't match here (pondering == mode:sleep).
noise_ctx = Context()
noise_ctx.matches = r"""
mode: sleep
and tag: user.pondering
"""


# Submit method used by the click-to-finish Enter, only when focused app is Pi.
# "follow" = follow-on message (alt-enter, delivered after the agent finishes),
# "steer"  = steering message (plain enter, delivered mid-run).
SUBMIT_METHODS = {"follow": "alt-enter", "steer": "enter"}
submit_method = "follow"

# Pi sets its terminal title to "π - <cwd>"; detect from the window title only.
_PI_TITLE_RE = re.compile(r"^\s*(π|pi)\b", re.IGNORECASE)


def _is_pi_terminal() -> bool:
    """True when the focused window title looks like a Pi terminal."""
    try:
        title = ui.active_window().title or ""
    except Exception:
        return False
    return bool(_PI_TITLE_RE.match(title))


def _setting_word(words):
    """Return "follow"/"steer" if the phrase is exactly that one word, else None."""
    if len(words) != 1:
        return None
    word = str(words[0]).split("\\")[0].strip().lower()
    return word if word in SUBMIT_METHODS else None


def _set_submit_method(method: str):
    global submit_method
    submit_method = method
    print(f"[pondering] submit method set to {method}")


def _submit():
    """Send the finishing Enter; in a Pi terminal use the chosen submit method."""
    if _is_pi_terminal():
        actions.key(SUBMIT_METHODS[submit_method])
    else:
        actions.key("enter")


def enable():
    """Enter pondering — pure state, NO SuperWhisper key.

    The voice path relays the key via _submit_superwhisper(); the passive
    hotkey path relies on the physical press falling through to SuperWhisper.
    """
    global enabled, _entered_from_sleep
    if enabled:
        return  # already pondering — a repeat must not re-capture the (now sleep) mode
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
    if not enabled:
        return  # already out of pondering
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
        _clear_followups()
        if enabled:
            return  # already pondering: don't send the toggle key again (it would close it)
        enable()
        _submit_superwhisper()

    def pondering_disable():
        """Disable pondering mode"""
        disable()

    def pondering_set_submit_method(method: str):
        """Set the Pi submit method for the pondering Enter click: follow or steer"""
        if method in SUBMIT_METHODS:
            _set_submit_method(method)

    def click_submit_now():
        """Press the lined-up submit key (default Enter). This is the action a
        follow-up tongue-click fires via repeater's repeat override."""
        _clear_followups()  # one-shot: used up
        if _submit_key == DEFAULT_SUBMIT_KEY:
            _submit()  # Enter, or the chosen follow/steer key in a Pi terminal
            print("[click] submit -> default submit")
        elif _submit_key:
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
        if time.monotonic() < _suppress_until:
            return
        if enabled:
            disable()
        else:
            enable()


def _clear_followups():
    """Drop the lined-up follow-ups and their expiry timer."""
    global _followup_job
    if _followup_job is not None:
        cron.cancel(_followup_job)
        _followup_job = None
    actions.user.clear_repeat_overrides()


def _expire_followups():
    global _followup_job
    _followup_job = None
    actions.user.clear_repeat_overrides()
    print("[click] follow-ups expired")


def _arm_followups():
    """Arm the lined-up follow-up sounds via repeater's native override facility:
      • repeat sound (next tongue-click) -> user.click_submit_now (press Enter)
      • opposite sound (next cmere)      -> user.pondering_enable (re-dictate)
    repeater runs the lined-up action with its own handler, so no competing
    context can steal the sound.

    They are time-limited: cleared after FOLLOWUP_TTL, and as soon as either is
    used (click_submit_now / pondering_enable). Left armed indefinitely, a later
    stray cmere or click in any app re-opened SuperWhisper / sent a stray Enter.
    A real spoken command still clears them too (repeater.on_post_phrase).
    """
    global _followup_job
    if _followup_job is not None:
        cron.cancel(_followup_job)
    actions.user.set_next_repeat_action("user", "click_submit_now", [])
    print("[click] armed repeat -> user.click_submit_now")
    actions.user.set_next_opposite_action("user", "pondering_enable", [])
    print("[click] armed opposite -> user.pondering_enable")
    _followup_job = cron.after(FOLLOWUP_TTL, _expire_followups)


def _submit_and_exit():
    """Finish: submit the in-progress SuperWhisper dictation, leave pondering, then
    arm the follow-up sounds (submit / re-enter) — synchronously, since the
    dictation `<phrase>` that used to clear them is now excluded from tracking.

    The dictated text is now in the input box (SuperWhisper submit lands text but
    does NOT submit the form).
    """
    if _debounced("submit_and_exit"):
        return
    _submit_superwhisper()
    disable()
    _arm_followups()


@noise_ctx.action_class("user")
class PonderingNoiseActions:
    # While pondering, the tongue-click is the hands-free finish: submit
    # SuperWhisper + end pondering, then line up the follow-up submit / re-enter
    # actions (see _submit_and_exit).
    def noise_tongue_click():
        if _debounced("noise_tongue_click"):
            return
        print("[pondering] tongue-click — submit SuperWhisper + exit pondering")
        _submit_and_exit()

    # cmere is the RE-ENTER sound (fired via repeater's opposite override when NOT
    # pondering). While pondering it must be inert — otherwise repeating cmere
    # toggles pondering off, which Trillium depends on staying on. So we swallow
    # it here (no exit) instead of finishing.
    def noise_cmere():
        if _debounced("noise_cmere"):
            return
        print("[pondering] cmere — ignored (re-enter sound; does not end pondering)")
