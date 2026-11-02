"""Scope probe — code-driven observer for the cursorless vs. prose-overlay matcher conflict.

Two streams now ride on the same module:

1. **Change stream** at ``~/.talon/scope_probe.jsonl`` — the original 250 ms
   polled emitter. Schema frozen. Tail with::

       tail -f ~/.talon/scope_probe.jsonl | jq -c '{ts, trigger, modes, tags: .monitored_tags, app: .focused.name, winner: .verdict.winner}'

2. **Phrase stream** at ``~/.talon/scope_probe.phrases.jsonl`` — every
   recognized phrase emits ONE merged line with both ``pre:phrase`` (before
   matcher dispatch) and ``phrase`` (after dispatch) scope snapshots, plus
   the parsed phrase and winning capture path. This is the sub-poll-window
   ground-truth instrument: it sees flickers the 250 ms poll cannot.

Force a snapshot from anywhere in Talon::

    actions.user.scope_probe_dump("manual")

Mutate the watch set live (immediate effect on the next 250 ms tick, no
restart)::

    actions.user.scope_probe_watch_tag("user.my_tag")
    actions.user.scope_probe_unwatch_tag("user.my_tag")
    actions.user.scope_probe_watch_mode("user.my_mode")
    actions.user.scope_probe_unwatch_mode("user.my_mode")
    actions.user.scope_probe_list_watch()  # -> {"tags": [...], "modes": [...]}

Given / When / Then assertion from the Talon REPL::

    # Given: capture the current scope as a baseline snapshot.
    baseline = actions.user.scope_assert_now()
    # -> {"tags": [...], "modes": [...], "canvas_showing": bool|None}

    # When: the operator performs some action (toggle prose overlay, switch
    # mode, focus another app, etc.).

    # Then: assert that the expected tags are present and the forbidden tags
    # are absent. Returns True on success; False (with a "scope_assert FAIL:
    # missing=[...] leaked=[...]" line printed) on mismatch.
    ok = actions.user.scope_assert(
        present=["user.cursorless", "user.prose_overlay_active"],
        absent=["user.mouse_clock_showing", "user.clock_ring_showing"],
    )
    assert ok, "prose-overlay-cursorless preconditions not met"

Voice surface (see sibling ``scope_probe.talon``)::

    "scope probe dump"          -> actions.user.scope_probe_dump("voice")
    "scope probe clear"         -> actions.user.scope_probe_clear()
    "scope probe phrase clear"  -> actions.user.scope_probe_phrase_clear()
    "scope assert now"          -> prints actions.user.scope_assert_now()

If the ``.talon`` file is unavailable, the equivalent ``mimic`` recipe is::

    actions.mimic("scope probe dump")
"""

import json
import os
import uuid
from datetime import datetime

from talon import Module, actions, app, cron, scope, speech_system, ui

LOG = os.path.expanduser("~/.talon/scope_probe.jsonl")
PHRASE_LOG = os.path.expanduser("~/.talon/scope_probe.phrases.jsonl")

# Tags relevant to the cursorless / prose-overlay matcher race.
# Mutable so scope_probe_watch_tag / scope_probe_unwatch_tag can affect the
# next 250 ms poll without a reload.
MONITORED_TAGS: set[str] = {
    "user.prose_overlay_active",
    "user.prose_overlay_auto",
    "user.cursorless",
    "user.cursorless_spoken_form_test",
    "user.mouse_clock_showing",
    "user.clock_ring_showing",
}

# Modes the conflict cares about. Mutable for the same reason.
MONITORED_MODES: set[str] = {
    "command",
    "dictation",
    "user.cursorless_spoken_form_test",
}

mod = Module()

_last_key = None
_started = False

# Per-phrase correlation table. Keyed by id(phrase) so the same dict-like
# object that arrives at pre:phrase can be retrieved at phrase-time. Each
# entry holds the corr id + the pre-snapshot captured synchronously inside
# the pre:phrase callback. We pop the entry inside _on_phrase so the table
# can never grow unbounded; a fall-through (pre fired, phrase didn't)
# leaves a stale entry which is acceptable noise — Talon does not promise
# 1:1 pre/phrase delivery in every edge case.
_pending_phrases: dict[int, dict] = {}


def _active_tags() -> set[str]:
    try:
        return set(scope.get("tag") or ())
    except Exception:
        return set()


def _active_modes() -> list[str]:
    try:
        return sorted(scope.get("mode") or ())
    except Exception:
        return []


def _focused() -> dict:
    try:
        return {
            "name": actions.app.name(),
            "bundle": actions.app.bundle() if app.platform == "mac" else None,
            "title": actions.win.title(),
        }
    except Exception:
        return {"name": None, "bundle": None, "title": None}


def _canvas_showing() -> "bool | None":
    """Read prose-overlay canvas state via the public action surface.

    We deliberately do NOT import ``prose_overlay.*`` — that would create a
    circular import risk and tie scope_probe to prose_overlay's reload
    timing. ``actions.user.prose_overlay_is_active`` may not exist; if it
    raises (KeyError on the action map, or anything else), we return None
    rather than crash the callback.
    """
    try:
        return bool(actions.user.prose_overlay_is_active())
    except Exception:
        return None


def _verdict(modes: set[str], tags: set[str]) -> dict:
    """Reproduce the two competing context matchers and report who wins.

    cursorless.talon:           mode:(command|user.cursorless_spoken_form_test)
                                tag:user.cursorless
                                not tag:user.mouse_clock_showing
                                not tag:user.clock_ring_showing
    prose_overlay_cursorless:   mode:(dictation|command)
                                tag:user.prose_overlay_active
                                tag:user.cursorless
                                not tag:user.mouse_clock_showing
                                not tag:user.clock_ring_showing
    """
    blocked = (
        "user.mouse_clock_showing" in tags
        or "user.clock_ring_showing" in tags
    )

    cursorless_mode_ok = (
        "command" in modes or "user.cursorless_spoken_form_test" in modes
    )
    prose_mode_ok = "dictation" in modes or "command" in modes

    cursorless_matches = (
        cursorless_mode_ok and "user.cursorless" in tags and not blocked
    )
    prose_matches = (
        prose_mode_ok
        and "user.prose_overlay_active" in tags
        and "user.cursorless" in tags
        and not blocked
    )

    if prose_matches and cursorless_matches:
        winner = "prose_overlay_cursorless.talon (6 matchers > 5)"
    elif prose_matches:
        winner = "prose_overlay_cursorless.talon"
    elif cursorless_matches:
        winner = "cursorless.talon"
    else:
        winner = None

    return {
        "cursorless_matches": cursorless_matches,
        "prose_overlay_matches": prose_matches,
        "winner": winner,
        "blocked_by": [
            t for t in ("user.mouse_clock_showing", "user.clock_ring_showing") if t in tags
        ],
    }


def _snapshot(trigger: str) -> dict:
    modes = _active_modes()
    tags = _active_tags()
    return {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "trigger": trigger,
        "modes": modes,
        "monitored_modes": {m: (m in set(modes)) for m in MONITORED_MODES},
        "monitored_tags": {t: (t in tags) for t in MONITORED_TAGS},
        "focused": _focused(),
        "verdict": _verdict(set(modes), tags),
    }


def _emit(trigger: str) -> None:
    try:
        line = json.dumps(_snapshot(trigger))
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"scope_probe: emit failed ({e})")


def _emit_phrase(record: dict) -> None:
    try:
        line = json.dumps(record)
        with open(PHRASE_LOG, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"scope_probe: phrase emit failed ({e})")


def _state_key() -> tuple:
    modes = tuple(_active_modes())
    tags = _active_tags()
    focused = _focused()
    return (
        modes,
        # Iterate the mutable set as a sorted tuple so equality is stable
        # even if the underlying set hashes shift between Python runs.
        tuple(sorted(t for t in MONITORED_TAGS if t in tags)),
        focused.get("bundle") or focused.get("name"),
    )


def _tick() -> None:
    """Polled observer — emits only when relevant state has shifted."""
    global _last_key
    try:
        key = _state_key()
    except Exception:
        return
    if key != _last_key:
        _last_key = key
        _emit("auto:change")


def _phrase_words(phrase: dict) -> list[str]:
    try:
        words = phrase.get("phrase") or []
        return [str(w) for w in words]
    except Exception:
        return []


def _phrase_parsed(phrase: dict) -> list[str]:
    """Best-effort serialization of the parsed capture tree."""
    try:
        parsed = phrase.get("parsed")
        if parsed is None:
            return []
        out: list[str] = []
        for node in parsed:
            try:
                out.append(repr(node))
            except Exception:
                out.append("<unrepr>")
        return out
    except Exception:
        return []


def _phrase_capture_path(phrase: dict) -> "str | None":
    """The winning capture path is not a first-class field on the phrase
    dict; we approximate it by the underscored ``_name`` of each parsed
    node, joined with '/'. This is enough to distinguish, e.g.,
    cursorless.talon's winner from prose_overlay_cursorless.talon's
    winner in post-hoc analysis.
    """
    try:
        parsed = phrase.get("parsed")
        if not parsed:
            return None
        names: list[str] = []
        for node in parsed:
            name = getattr(node, "_name", None)
            if name:
                names.append(str(name))
        return "/".join(names) if names else None
    except Exception:
        return None


def _on_pre_phrase(phrase: dict) -> None:
    """Captured synchronously before Talon dispatches matchers.

    Stashes a corr-id + pre-snapshot keyed by ``id(phrase)`` so the matching
    ``phrase`` callback can emit a single merged line.
    """
    try:
        corr = uuid.uuid4().hex
        pre_tag_set = _active_tags()
        _pending_phrases[id(phrase)] = {
            "corr": corr,
            "pre_tags": sorted(pre_tag_set),
            "pre_modes": _active_modes(),
            "canvas_showing": _canvas_showing(),
            "focused": _focused(),
            "prose_overlay_active": "user.prose_overlay_active" in pre_tag_set,
            "prose_overlay_auto": "user.prose_overlay_auto" in pre_tag_set,
        }
    except Exception as e:
        print(f"scope_probe: pre:phrase callback failed ({e})")


def _phrase_cmd_path(phrase: dict) -> "str | None":
    """Best-effort extraction of the source rule's origin path.

    Talon's phrase dict can carry a 'cmd' field whose item has a .rule attr
    pointing back to the .talon file that won. We dig for it defensively.
    """
    try:
        cmd = phrase.get("cmd")
        if cmd is None:
            return None
        for attr in ("rule", "path", "_path", "talon_path", "filename"):
            val = getattr(cmd, attr, None)
            if val:
                return str(val)
        return repr(cmd)[:200]
    except Exception:
        return None


def _raw_tag_introspection() -> dict:
    """Sample tag state via multiple independent paths to detect any divergence
    between scope.get('tag') (what context matchers nominally see), the
    scope.tags attribute, and the prose_overlay Context's own .tags list
    (the source of truth for prose_overlay's tag assertion).
    """
    out: dict = {}
    try:
        out["scope_get_tag"] = sorted(scope.get("tag") or ())
    except Exception as e:
        out["scope_get_tag_err"] = str(e)
    try:
        out["scope_tags_attr"] = sorted(getattr(scope, "tags", []) or [])
    except Exception as e:
        out["scope_tags_attr_err"] = str(e)
    # Direct introspection of prose_overlay's owning Context. This is the
    # ground truth — what _sync_tags() last assigned. If this disagrees with
    # scope.get("tag"), we have a stale-aggregation race.
    #
    # We walk sys.modules looking for a module whose `instance` attribute is the
    # initialized singleton (`ctx is not None`). That sidesteps the namespace
    # question of how Talon registers the user package.
    try:
        import sys
        candidate_names = [
            name for name in sys.modules
            if name.endswith("prose_overlay_instance")
        ]
        out["po_module_candidates"] = candidate_names
        chosen = None
        for name in candidate_names:
            mod = sys.modules.get(name)
            if mod is None:
                continue
            inst = getattr(mod, "instance", None)
            if inst is None:
                continue
            if getattr(inst, "ctx", None) is not None:
                chosen = (name, inst)
                break
            if chosen is None:
                chosen = (name, inst)  # remember uninitialized fallback
        # Dump ALL candidates so we can detect parallel-instance divergence.
        per_module = []
        for name in candidate_names:
            mod = sys.modules.get(name)
            entry = {"module": name, "mod_id": id(mod) if mod else None}
            inst = getattr(mod, "instance", None) if mod else None
            entry["inst_id"] = id(inst) if inst is not None else None
            if inst is not None:
                ctx = getattr(inst, "ctx", None)
                ctx_auto = getattr(inst, "ctx_auto", None)
                canvas = getattr(inst, "canvas", None)
                entry["ctx_id"] = id(ctx) if ctx is not None else None
                entry["ctx_is_none"] = ctx is None
                entry["ctx_tags"] = list(getattr(ctx, "tags", None) or []) if ctx is not None else None
                entry["ctx_auto_tags"] = list(getattr(ctx_auto, "tags", None) or []) if ctx_auto is not None else None
                entry["canvas_id"] = id(canvas) if canvas is not None else None
                entry["canvas_is_showing"] = bool(getattr(canvas, "is_showing", False)) if canvas is not None else None
                entry["auto_dictation"] = bool(getattr(inst, "auto_dictation", False))
            per_module.append(entry)
        out["po_per_module"] = per_module
        if chosen is None:
            out["po_introspection_err"] = "no prose_overlay_instance in sys.modules"
        else:
            name, inst = chosen
            out["po_chosen_module"] = name
            ctx = getattr(inst, "ctx", None)
            ctx_auto = getattr(inst, "ctx_auto", None)
            canvas = getattr(inst, "canvas", None)
            out["po_ctx_tags"] = list(getattr(ctx, "tags", None) or []) if ctx is not None else None
            out["po_ctx_auto_tags"] = list(getattr(ctx_auto, "tags", None) or []) if ctx_auto is not None else None
            out["po_canvas_is_showing"] = bool(getattr(canvas, "is_showing", False)) if canvas is not None else None
            out["po_auto_dictation"] = bool(getattr(inst, "auto_dictation", False))
            out["po_ctx_is_none"] = ctx is None
    except Exception as e:
        out["po_introspection_err"] = str(e)
    return out


def _on_phrase(phrase: dict) -> None:
    """Captured at phrase-eval time; merges the pre-snapshot and emits."""
    try:
        pending = _pending_phrases.pop(id(phrase), None)
        if pending is None:
            fallback_tags = _active_tags()
            pending = {
                "corr": uuid.uuid4().hex,
                "pre_tags": sorted(fallback_tags),
                "pre_modes": _active_modes(),
                "canvas_showing": _canvas_showing(),
                "focused": _focused(),
                "prose_overlay_active": "user.prose_overlay_active" in fallback_tags,
                "prose_overlay_auto": "user.prose_overlay_auto" in fallback_tags,
            }
        post_tag_set = _active_tags()
        try:
            phrase_keys = sorted(list(phrase.keys()))
        except Exception:
            phrase_keys = []
        try:
            phrase_repr = repr(phrase)[:600]
        except Exception:
            phrase_repr = "<unrepr>"
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "corr": pending["corr"],
            "words": _phrase_words(phrase),
            "parsed": _phrase_parsed(phrase),
            "capture_path": _phrase_capture_path(phrase),
            "cmd_path": _phrase_cmd_path(phrase),
            "phrase_keys": phrase_keys,
            "phrase_repr": phrase_repr,
            "focused": pending["focused"],
            "prose_overlay": {
                "active": pending["prose_overlay_active"],
                "auto": pending["prose_overlay_auto"],
                "canvas_showing": pending["canvas_showing"],
            },
            "pre_tags": pending["pre_tags"],
            "pre_modes": pending["pre_modes"],
            "canvas_showing": pending["canvas_showing"],
            "post_tags": sorted(post_tag_set),
            "post_modes": _active_modes(),
            "post_prose_overlay_active": "user.prose_overlay_active" in post_tag_set,
            "post_prose_overlay_auto": "user.prose_overlay_auto" in post_tag_set,
            "raw_tag_introspection": _raw_tag_introspection(),
        }
        _emit_phrase(record)
    except Exception as e:
        print(f"scope_probe: phrase callback failed ({e})")


def _register_speech_hooks() -> None:
    """Wrap registration so a Talon version that lacks one of these events
    does not block module load. We log and continue."""
    try:
        speech_system.register("pre:phrase", _on_pre_phrase)
    except Exception as e:
        print(f"scope_probe: pre:phrase registration failed ({e})")
    try:
        speech_system.register("phrase", _on_phrase)
    except Exception as e:
        print(f"scope_probe: phrase registration failed ({e})")


def _start_once() -> None:
    global _started
    if _started:
        return
    _started = True
    _emit("startup")
    # 250 ms polling: light, catches every state shift fast enough for human
    # reproduction loops; cheap because most ticks are no-ops.
    try:
        cron.interval("250ms", _tick)
    except Exception as e:
        print(f"scope_probe: cron registration failed ({e})")


# Defer startup until the Talon UI is ready so scope.get / actions.app.name
# don't fire before their providers exist.
try:
    app.register("ready", _start_once)
except Exception as e:
    print(f"scope_probe: ready hook failed ({e})")
    _start_once()

# Speech hooks are registered at module load — they are independent of the
# UI being ready (speech_system exists before "ready" fires) and we want to
# capture the very first phrase after a reload.
_register_speech_hooks()


@mod.action_class
class Actions:
    def scope_probe_dump(label: str = "manual"):
        """Force-write a scope-probe snapshot to ~/.talon/scope_probe.jsonl."""
        _emit(f"manual:{label}")
        print(f"scope_probe: dumped (label={label}) -> {LOG}")

    def scope_probe_clear():
        """Remove the scope-probe log."""
        try:
            os.remove(LOG)
            print(f"scope_probe: cleared {LOG}")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"scope_probe: clear failed ({e})")

    def scope_probe_path() -> str:
        """Return the path of the scope-probe log."""
        return LOG

    def scope_probe_phrase_dump_path() -> str:
        """Return the path of the phrase-time JSONL stream."""
        return PHRASE_LOG

    def scope_probe_phrase_clear() -> None:
        """Remove the phrase-time scope-probe log."""
        try:
            os.remove(PHRASE_LOG)
            print(f"scope_probe: phrase cleared {PHRASE_LOG}")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"scope_probe: phrase clear failed ({e})")

    def scope_probe_watch_tag(tag: str) -> None:
        """Add a tag to the live watch set — effect on next 250 ms tick."""
        MONITORED_TAGS.add(tag)
        print(f"scope_probe: watch tag {tag} (set size={len(MONITORED_TAGS)})")

    def scope_probe_unwatch_tag(tag: str) -> None:
        """Remove a tag from the live watch set (no-op if absent)."""
        MONITORED_TAGS.discard(tag)
        print(f"scope_probe: unwatch tag {tag} (set size={len(MONITORED_TAGS)})")

    def scope_probe_watch_mode(mode: str) -> None:
        """Add a mode to the live watch set — effect on next 250 ms tick."""
        MONITORED_MODES.add(mode)
        print(f"scope_probe: watch mode {mode} (set size={len(MONITORED_MODES)})")

    def scope_probe_unwatch_mode(mode: str) -> None:
        """Remove a mode from the live watch set (no-op if absent)."""
        MONITORED_MODES.discard(mode)
        print(f"scope_probe: unwatch mode {mode} (set size={len(MONITORED_MODES)})")

    def scope_probe_list_watch() -> dict:
        """Return the current watch set as ``{"tags": [...], "modes": [...]}`` (sorted)."""
        return {
            "tags": sorted(MONITORED_TAGS),
            "modes": sorted(MONITORED_MODES),
        }

    def scope_assert(present: list[str], absent: list[str]) -> bool:
        """Assert that ``present`` are all in scope and ``absent`` are all out.

        Reads ``scope.get("tag")`` and ``scope.get("mode")`` once each and
        unions them into a single active-set. Returns True iff every entry
        in ``present`` is in that set and every entry in ``absent`` is not.
        On False, prints ``scope_assert FAIL: missing=[...] leaked=[...]``
        for at-a-glance diagnosis.
        """
        active = _active_tags() | set(_active_modes())
        missing = [p for p in present if p not in active]
        leaked = [a for a in absent if a in active]
        if not missing and not leaked:
            return True
        print(f"scope_assert FAIL: missing={missing} leaked={leaked}")
        return False

    def scope_assert_now() -> dict:
        """Return the current scope as a Given-snapshot dict.

        Shape: ``{"tags": [...sorted...], "modes": [...sorted...],
        "canvas_showing": bool|None}``. Suitable for diffing against a
        later snapshot to reason about scope deltas.
        """
        return {
            "tags": sorted(_active_tags()),
            "modes": _active_modes(),
            "canvas_showing": _canvas_showing(),
        }
