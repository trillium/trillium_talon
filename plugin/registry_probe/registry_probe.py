"""Registry probe — reusable JSONL snapshot of Talon's registry / scope / grammar.

Sibling of ``scope_probe``: where scope_probe streams change events and per-phrase
matcher state, registry_probe answers a single, fundamental question on demand —

    "At the moment this was called, which Contexts did Talon consider active,
    and what did their `matches` headers look like?"

That is the ground-truth answer to "why did rule X bind?" — by inspecting
``registry.contexts`` Talon itself, not by reading ``.talon`` files and
reasoning about what they ought to do.

Persistence
-----------
Every snapshot is appended as one JSONL line to::

    ~/.talon/registry_probe.jsonl

so snapshots survive Talon restarts and can be diffed / grep'd post-mortem.

Call from anywhere in Python
----------------------------
::

    actions.user.registry_probe_dump(
        "po_anomaly_canvas_closed",
        {"action_name": action_name, "target_type": type(target).__name__},
    )

The action returns the snapshot dict so callers can also branch on it
in-line (e.g. to bail out of an action body when an anomaly is detected).

Voice surface (see sibling ``registry_probe.talon``)::

    "registry probe dump"   -> actions.user.registry_probe_dump("voice")
    "registry probe clear"  -> actions.user.registry_probe_clear()

Filters
-------
``CONTEXT_NAME_FILTERS`` is a list of substrings; if any matches a context's
``path`` (or registered name), that context's full record is included in the
snapshot. The default set covers the cursorless vs prose-overlay surface that
spawned this tool. ``registry_probe_watch`` / ``registry_probe_unwatch`` mutate
the filter set without a reload. Empty filter set ⇒ dump *every* context (large
but sometimes what you want).
"""

import json
import os
from datetime import datetime

from talon import Module, actions, app, registry, scope, ui

LOG = os.path.expanduser("~/.talon/registry_probe.jsonl")

# Substring filters applied to each context's path. Anything matching is
# included in the snapshot. Mutable via the watch/unwatch actions below.
CONTEXT_NAME_FILTERS: list[str] = [
    "prose_overlay",
    "cursorless",
]

# Lists whose current value chain is always captured (independent of filters).
ALWAYS_DUMP_LISTS: list[str] = [
    "user.cursorless_simple_action",
    "user.cursorless_bring_move_action",
    "user.cursorless_reformat_action",
    "user.cursorless_callback_action",
    "user.cursorless_experimental_action",
    "user.cursorless_custom_action",
]

mod = Module()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _focused() -> dict:
    try:
        a = ui.active_app()
        w = ui.active_window()
        return {
            "name": getattr(a, "name", None),
            "bundle": getattr(a, "bundle", None),
            "title": getattr(w, "title", None),
        }
    except Exception as e:
        return {"err": str(e)}


def _scope_snapshot() -> dict:
    out: dict = {}
    try:
        out["scope_get_tag"] = sorted(scope.get("tag") or ())
    except Exception as e:
        out["scope_get_tag_err"] = str(e)
    try:
        out["scope_get_mode"] = sorted(scope.get("mode") or ())
    except Exception as e:
        out["scope_get_mode_err"] = str(e)
    try:
        out["scope_tags_attr"] = sorted(getattr(scope, "tags", []) or [])
    except Exception as e:
        out["scope_tags_attr_err"] = str(e)
    return out


def _safe_getattr(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _context_record(name: str, ctx) -> dict:
    """Serialize one registry.contexts entry to JSON-safe shape.

    The exact attribute names on Talon's internal Context record can vary
    across Talon builds; we try several known shapes defensively so a Talon
    update doesn't silently produce empty snapshots.
    """
    rec: dict = {"name": name}
    for attr in ("path", "filename", "_path", "talon_path"):
        v = _safe_getattr(ctx, attr)
        if v:
            rec["path"] = str(v)
            break
    # Matches header — most Talon versions expose it as a string source
    # plus a parsed structure. We capture both when available.
    for attr in ("matches", "matches_str", "match_source", "match_text"):
        v = _safe_getattr(ctx, attr)
        if v:
            rec["matches_raw"] = str(v)
            break
    # The truthy-bit we care about most: is this context currently considered
    # active by Talon's scope/grammar machinery? Try a few names.
    for attr in ("active", "is_active", "_active"):
        v = _safe_getattr(ctx, attr, None)
        if v is not None:
            rec["active"] = bool(v)
            break
    # Tag / setting / action contributions this context would inject if active.
    try:
        tags_val = _safe_getattr(ctx, "tags", None)
        if tags_val is not None:
            rec["assigns_tags"] = list(tags_val)
    except Exception:
        pass
    # Command count — useful for spotting empty / stub contexts.
    for attr in ("commands", "rules", "_commands"):
        v = _safe_getattr(ctx, attr, None)
        if v is not None:
            try:
                rec["command_count"] = len(v)
            except Exception:
                pass
            break
    return rec


def _contexts_snapshot(filters: list[str]) -> list[dict]:
    out: list[dict] = []
    try:
        contexts = getattr(registry, "contexts", None) or {}
    except Exception as e:
        return [{"err": f"registry.contexts unavailable: {e}"}]
    # contexts may be a dict-like mapping name -> ContextRecord
    try:
        items = contexts.items()
    except Exception:
        try:
            items = [(n, contexts[n]) for n in contexts]
        except Exception as e:
            return [{"err": f"registry.contexts not iterable: {e}"}]
    for name, ctx in items:
        try:
            name_s = str(name)
            path_s = str(_safe_getattr(ctx, "path", "") or "")
            blob = name_s + " " + path_s
            if filters and not any(f in blob for f in filters):
                continue
            out.append(_context_record(name_s, ctx))
        except Exception as e:
            out.append({"name": str(name), "err": str(e)})
    return out


def _list_chain(name: str) -> dict:
    """Capture the override-chain Talon currently holds for a list.

    Returns the chain count, the active (top-of-chain) value, and the chain
    sources where introspectable. Tail values come from later context-overrides;
    head is the base mod.list. Useful for verifying that
    `{user.cursorless_simple_action}` actually contains "take" at probe time.
    """
    out: dict = {"name": name}
    try:
        chain = registry.lists.get(name) if hasattr(registry.lists, "get") else None
        if chain is None:
            chain = registry.lists[name]
    except Exception as e:
        return {"name": name, "err": str(e)}
    try:
        out["chain_len"] = len(chain)
    except Exception:
        pass
    try:
        active = chain[-1] if chain else None
        if active is None:
            out["active_value"] = None
            return out
        # Talon ListValue is dict-like; coerce keys to a sorted list of strings.
        try:
            keys = sorted(active.keys())
        except Exception:
            try:
                keys = sorted(active)
            except Exception:
                keys = None
        if keys is not None:
            out["active_keys_count"] = len(keys)
            out["active_keys_sample"] = keys[:20]
    except Exception as e:
        out["active_err"] = str(e)
    return out


def _registered_tags_snapshot() -> dict:
    out: dict = {}
    try:
        tags = registry.tags
    except Exception as e:
        return {"err": str(e)}
    try:
        names = sorted(list(tags.keys())) if hasattr(tags, "keys") else sorted(list(tags))
    except Exception as e:
        return {"err": str(e)}
    out["count"] = len(names)
    out["names_sample"] = [n for n in names if "prose_overlay" in n or "cursorless" in n][:40]
    return out


def _po_introspection() -> dict:
    """Mirror of scope_probe's prose_overlay-instance introspection so a
    registry_probe snapshot stands on its own as a diagnostic."""
    import sys
    out: dict = {}
    try:
        candidate_names = [
            n for n in sys.modules
            if n.endswith("prose_overlay_instance")
        ]
        out["candidate_modules"] = candidate_names
        per_module = []
        for n in candidate_names:
            mod_ = sys.modules.get(n)
            inst = getattr(mod_, "instance", None) if mod_ else None
            entry: dict = {"module": n}
            if inst is not None:
                ctx = getattr(inst, "ctx", None)
                ctx_auto = getattr(inst, "ctx_auto", None)
                canvas = getattr(inst, "canvas", None)
                entry["ctx_tags"] = list(getattr(ctx, "tags", None) or []) if ctx is not None else None
                entry["ctx_auto_tags"] = list(getattr(ctx_auto, "tags", None) or []) if ctx_auto is not None else None
                entry["canvas_is_showing"] = bool(getattr(canvas, "is_showing", False)) if canvas is not None else None
                entry["auto_dictation"] = bool(getattr(inst, "auto_dictation", False))
            per_module.append(entry)
        out["per_module"] = per_module
    except Exception as e:
        out["err"] = str(e)
    return out


def _emit(record: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"registry_probe: emit failed ({e})")


# ---------------------------------------------------------------------------
# Public action surface
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
    def registry_probe_dump(label: str, extras: dict = None) -> dict:
        """Append a one-line JSONL snapshot of Talon's registry/scope to
        ~/.talon/registry_probe.jsonl and return the snapshot dict.

        ``label`` is a short caller-defined string ("voice", "manual",
        "po_anomaly_canvas_closed", "<test-name>"). ``extras`` is an optional
        dict of caller-specific fields merged into the snapshot under
        ``extras``. The dump filters contexts by CONTEXT_NAME_FILTERS by
        default; pass an empty filter set via registry_probe_set_filters([])
        to capture every context.

        Useful for answering "at the moment X happened, was context Y active
        per Talon's own bookkeeping?" — bypassing all reasoning about what
        the .talon header says it should be.
        """
        snap = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "label": label,
            "extras": extras or {},
            "focused": _focused(),
            "scope": _scope_snapshot(),
            "filters": list(CONTEXT_NAME_FILTERS),
            "contexts": _contexts_snapshot(list(CONTEXT_NAME_FILTERS)),
            "lists": [_list_chain(n) for n in ALWAYS_DUMP_LISTS],
            "registered_tags": _registered_tags_snapshot(),
            "po_introspection": _po_introspection(),
        }
        _emit(snap)
        return snap

    def registry_probe_clear():
        """Truncate ~/.talon/registry_probe.jsonl. Returns True on success."""
        try:
            open(LOG, "w").close()
            return True
        except Exception as e:
            print(f"registry_probe: clear failed ({e})")
            return False

    def registry_probe_watch(substring: str):
        """Add a substring to CONTEXT_NAME_FILTERS — contexts whose path or
        name contains ``substring`` will be included in the next snapshot."""
        if substring and substring not in CONTEXT_NAME_FILTERS:
            CONTEXT_NAME_FILTERS.append(substring)
        print(f"registry_probe: filters={CONTEXT_NAME_FILTERS}")

    def registry_probe_unwatch(substring: str):
        """Remove a substring from CONTEXT_NAME_FILTERS."""
        try:
            CONTEXT_NAME_FILTERS.remove(substring)
        except ValueError:
            pass
        print(f"registry_probe: filters={CONTEXT_NAME_FILTERS}")

    def registry_probe_set_filters(filters: list):
        """Replace CONTEXT_NAME_FILTERS wholesale. Pass [] to capture every
        context (large output — use sparingly)."""
        CONTEXT_NAME_FILTERS.clear()
        for s in filters:
            if s:
                CONTEXT_NAME_FILTERS.append(s)
        print(f"registry_probe: filters={CONTEXT_NAME_FILTERS}")
