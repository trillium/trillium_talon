"""
Composer cursorless bridge — reuses cursorless-talon's own grammar/target
parsing (pure grammar, no engine RPC required to parse speech) to drive
composer.py's @-ref syntax, instead of a real Cursorless-connected editor.

composer.py renders its own hats and has no live awareness inside Talon's
process. This bridge only needs the SPOKEN target (hat color + character +
optional ordinal modifier) — it maps that onto composer's own
@<letter><tier>.<ordinal> reference syntax and types it into the composer
pane as text, the same way herder_send (herder.py) types text into agent
panes.

composer.py's hat allocation is now driven by the real Cursorless engine
(see composer.py's HatEngine / hat_engine.ts), so its HAT_TIERS matches
Cursorless's own HAT_COLORS names (default/red/blue/green/pink/yellow) —
_COLOR_TO_TIER_SUFFIX below must stay in lockstep with that list.

"bring <target>" grammar is scoped via a `tag: user.herdr_composer_focused`
.talon context header (composer_bring.talon). That tag is toggled below by
polling `herdr pane current` against a sentinel file composer.py writes/
removes for its own pane id (FOCUSED_PANE_PATH) — NOT via `win.title`, which
was tried first and proven architecturally impossible: herdr renders all of
its virtual panes/tabs inside a single real OS-level WezTerm window and
continuously repaints that one window's title itself (format "[N/M]
herdr"), so no external title-set call (herdr's own `terminal title set` or
a direct `wezterm cli set-window-title`) can ever make a win.title
predicate matching composer's pane stick — confirmed live via
~/.talon/talon.log's focus_change tracking across a forced focus-change
event.
"""

import base64
import json
import shlex
import subprocess
import time

from talon import Context, Module, actions, cron

mod = Module()
mod.tag(
    "herdr_composer_focused",
    desc="A herdr composer overlay pane is currently the focused pane",
)
_focus_ctx = Context()
FOCUS_TAG = "user.herdr_composer_focused"
FOCUS_POLL_INTERVAL = "300ms"

# Mirrors composer.py's own FOCUSED_PANE_PATH constant (composer.py resolves
# it via HERDR_PLUGIN_STATE_DIR, which is only set in the pane subprocess's
# environment - this file runs inside Talon's process instead, so the path
# is fixed here the same way _LOG_PATH already is below).
FOCUSED_PANE_PATH = "/Users/trilliumsmith/.local/state/herdr/plugins/trillium.hello-panel/focused_pane_id"

_HERDR = "/opt/homebrew/bin/herdr"
_ENV = 'PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH" '

# Same file composer.py itself logs to (composer.py resolves this path via
# HERDR_PLUGIN_STATE_DIR, which is only set in the pane subprocess's own
# environment - this file runs inside Talon's process instead, so the path
# is fixed here rather than recomputed). This exists to answer one question
# directly instead of guessing at it: did Talon actually dispatch a spoken
# "bring"/"copy" command to OUR action at all, and if so, what target/ref
# did it build? A silent live failure with nothing in this log means
# dispatch never reached this file - a Talon-grammar/context question, not a
# bug in this bridge or in composer.py.
_LOG_PATH = "/Users/trilliumsmith/.local/state/herdr/plugins/trillium.hello-panel/composer.log"


def _log(msg):
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} composer_cursorless: {msg}\n")
    except Exception:
        pass

# composer.py's HAT_TIERS order (index 0 = default, no suffix) — maps a
# spoken cursorless hat color onto composer's numeric @-ref tier suffix.
_COLOR_TO_TIER_SUFFIX = {
    "default": "",
    "red": "2",
    "blue": "3",
    "green": "4",
    "pink": "5",
    "yellow": "6",
}


def _encode_modifiers(modifiers):
    """Base64url-encode a real Cursorless target's `modifiers` list so it
    can travel as one shell-safe word inside composer's @-ref syntax (see
    composer.py's _decode_modifiers/_resolve_one_ref) - composer.py hands
    this straight to the real Cursorless engine rather than this bridge
    trying to interpret ordinals/scopes itself."""
    raw = json.dumps(modifiers, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _build_ref(target, copy):
    """Encode a single PrimitiveTarget as one composer.py @-ref string, or
    return None if it can't be represented (e.g. a RangeTarget, which spans
    an anchor/active pair and has no single .mark to hang a ref off of)."""
    mark = getattr(target, "mark", None)
    if mark is None:
        return None
    color = mark.get("symbolColor", "default")
    letter = mark.get("character", "")
    if not letter:
        return None
    tier_suffix = _COLOR_TO_TIER_SUFFIX.get(color, "")
    modifiers = getattr(target, "modifiers", None) or []
    # Forward cursorless-talon's own modifiers list verbatim (ordinalScope
    # for "first/third word", containingScope for "line"/"paragraph"/
    # "sentence"/surrounding pairs, relativeScope for "next pair", etc.)
    # rather than hand-translating it here - composer.py's HatEngine asks
    # the real Cursorless engine to resolve it, the same engine that
    # produced this modifiers list's shape in the first place.
    scope_suffix = f"%{_encode_modifiers(modifiers)}" if modifiers else ""
    bang = "!" if copy else ""
    return f"@{letter}{tier_suffix}{scope_suffix}{bang} "


def _type_target_ref(target, copy):
    """Shared body for composer_bring_target/composer_copy_target: encode a
    spoken cursorless target as composer.py's @-ref syntax and type it into
    the composer pane. `copy=True` appends the "!" marker (see
    try_live_resolve_word in composer.py) so composer.py puts the resolved
    text on the system clipboard instead of inserting it into its buffer."""
    _log(f"fired copy={copy} mark={getattr(target, 'mark', None)!r} "
         f"modifiers={getattr(target, 'modifiers', None)!r} elements={getattr(target, 'elements', None)!r}")
    pane_id = _pane_current().get("pane_id")
    if not pane_id:
        _log("aborted: _pane_current() returned no pane_id")
        return
    elements = getattr(target, "elements", None)
    if elements is not None:
        # ListTarget ("token X and token Y") - cursorless-talon's own
        # connective grammar (targets/target.py) builds this from a plain
        # "and" between two targets. There's no single .mark to hang one ref
        # off of, so type one ref per element instead of silently dropping
        # the whole utterance - this was the original "bring two tokens"
        # failure (each had to be brought individually). RangeTarget
        # elements (a span, e.g. "token x past token z") still have no
        # single .mark either; _build_ref returns None for those and they're
        # skipped rather than crashing the whole list.
        ref = "".join(r for r in (_build_ref(el, copy) for el in elements) if r is not None)
    else:
        ref = _build_ref(target, copy)
    if not ref:
        _log("aborted: built ref was empty (no .mark/.character on target)")
        return
    cmd = _ENV + f"{_HERDR} pane send-text {shlex.quote(pane_id)} {shlex.quote(ref)}"
    _log(f"sending ref={ref!r} to pane_id={pane_id!r}")
    actions.user.system_command_nb(cmd)


def _pane_current():
    try:
        out = subprocess.run(
            [_HERDR, "pane", "current"], capture_output=True, text=True, timeout=2
        ).stdout
        return json.loads(out).get("result", {}).get("pane", {})
    except Exception:
        return {}


_focus_poll_job = None
_focus_tag_active = False


def _read_focused_pane_sentinel():
    try:
        with open(FOCUSED_PANE_PATH) as f:
            return f.read().strip()
    except OSError:
        return ""


def _poll_composer_focus():
    """Toggle FOCUS_TAG on/off based on whether the pane composer.py wrote
    to FOCUSED_PANE_PATH (its own pane id, present only while its overlay is
    open) is the pane herdr currently reports as focused. Runs on a cron
    tick rather than a focus-change callback because composer.py's overlay
    pane is a herdr-internal concept, not a real OS window Talon's own
    focus-change events would ever fire for."""
    global _focus_tag_active
    sentinel_pane_id = _read_focused_pane_sentinel()
    should_be_active = bool(sentinel_pane_id) and sentinel_pane_id == _pane_current().get("pane_id")
    if should_be_active != _focus_tag_active:
        _focus_tag_active = should_be_active
        _focus_ctx.tags = [FOCUS_TAG] if should_be_active else []


def _start_focus_poll():
    global _focus_poll_job
    if _focus_poll_job is None:
        _focus_poll_job = cron.interval(FOCUS_POLL_INTERVAL, _poll_composer_focus)


_start_focus_poll()


@mod.action_class
class Actions:
    def composer_open():
        """Open the composer overlay on the currently focused herdr pane."""
        pane_id = _pane_current().get("pane_id")
        if not pane_id:
            return
        actions.user.system_command_nb(
            _ENV + f"{_HERDR} plugin pane open --plugin trillium.hello-panel "
            f"--entrypoint composer --placement overlay "
            f'--env "HERDR_SOURCE_PANE={pane_id}" --focus'
        )

    def composer_bring_target(target: object):
        """Insert a spoken cursorless target as an @-ref at the composer cursor."""
        _type_target_ref(target, copy=False)

    def composer_copy_target(target: object):
        """Resolve a spoken cursorless target and put it on the system
        clipboard instead of inserting it into the composer buffer - "copy
        token/block/pair <hat>" to paste into another pane."""
        _type_target_ref(target, copy=True)
