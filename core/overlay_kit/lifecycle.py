"""Overlay lifecycle — active-overlay registry + Talon tag toggling.

This is Option B from the refactor brief: every named overlay registers
its (ctx, tag) target up front, and `set_overlay_active(name, active)`
looks the target up. The four legacy recall overlays are pre-registered
on import so existing callers keep working without code changes.

Public API:
    register_overlay_ctx(name, ctx, tag)
    set_overlay_active(name, active)
    is_overlay_active(name) -> bool

Why a registry instead of a single recall-state global:
    The old helper hard-coded recall_state.overlay_ctx and the
    "user.recall_overlay_visible" tag. That meant any new overlay
    (e.g. cursorless_scope_support) would have had to either
    contaminate recall's tag or fork the helper. With the registry,
    each consumer owns its own ctx + tag and the lifecycle logic
    is shared.

If a name is registered but its target ctx hasn't been imported yet,
we fall through to the recall ctx for backward compatibility. The
recall registration is intentionally lazy so importing this module
does not force `recall_state` to load (lifecycle stays usable from
non-recall code paths and during early Talon boot).
"""

from typing import Any

# Per-overlay-name set of activation flags. We track names individually
# so we can toggle each one independently and recompute the union per ctx.
_active_overlays: set[str] = set()

# Registry: {overlay_name: (ctx, tag_string)}
_overlay_targets: dict[str, tuple[Any, str]] = {}

# Lazy-registered recall names — populated on first set_overlay_active
# call for any of them to avoid forcing recall_state to import on
# module load. Once populated, the entries land in _overlay_targets.
_RECALL_DEFAULTS: tuple[str, ...] = ("labels", "status", "help", "prompt")


def register_overlay_ctx(name: str, ctx: Any, tag: str):
    """Bind an overlay name to a Talon Context + tag string.

    Subsequent calls to set_overlay_active(name, True) will flip
    that tag on `ctx`. A name can be re-registered (last write wins)
    — useful during Talon module reloads.
    """
    _overlay_targets[name] = (ctx, tag)


def _ensure_recall_defaults():
    """Lazy-register the recall overlay names on first use.

    Safe to call repeatedly; only does work if any recall name is
    still missing from the registry. Import is deferred to here so
    that this module stays importable from non-recall contexts.
    """
    if all(name in _overlay_targets for name in _RECALL_DEFAULTS):
        return
    try:
        # Relative import to match the repo convention used by
        # core/system/activity_overlay.py and friends.
        from ...plugin.recall.recall_state import overlay_ctx as recall_ctx
    except Exception:
        # Recall not available in this Talon process (or import failed).
        # Callers under a recall name will still error visibly below.
        return
    for name in _RECALL_DEFAULTS:
        _overlay_targets.setdefault(name, (recall_ctx, "user.recall_overlay_visible"))


def set_overlay_active(name: str, active: bool):
    """Register or deregister `name` as a currently-visible overlay.

    After updating the active set, recomputes the tag state for every
    distinct (ctx, tag) target so that turning off the last overlay
    bound to a ctx clears its tag, and turning on the first re-asserts.
    """
    if name in _RECALL_DEFAULTS:
        _ensure_recall_defaults()
    if active:
        _active_overlays.add(name)
    else:
        _active_overlays.discard(name)
    _refresh_all_tags()


def is_overlay_active(name: str) -> bool:
    """True iff `name` is currently in the active set."""
    return name in _active_overlays


def _refresh_all_tags():
    """Recompute the tag state for every registered (ctx, tag) pair.

    Groups active overlays by their target (ctx, tag). For each
    distinct ctx, if any overlay bound to a tag on that ctx is
    active, sets that tag; otherwise clears all tags on that ctx
    that this module owns.

    We do not blanket-clear ctx.tags because a ctx may carry tags
    set by code outside the overlay kit — instead we compute the
    union of tags this kit wants set, and assign that as ctx.tags.
    Callers should not share a ctx with non-kit code if they care
    about preserving other tags. (The recall ctx is only used by
    the overlay kit, so this is safe in practice.)
    """
    # Group by ctx -> set of tags this kit wants ON for that ctx.
    desired: dict[int, tuple[Any, set[str]]] = {}
    # First, walk every registered target so even ctxs with zero
    # active overlays get their tags cleared.
    for name, (ctx, tag) in _overlay_targets.items():
        key = id(ctx)
        if key not in desired:
            desired[key] = (ctx, set())
        if name in _active_overlays:
            desired[key][1].add(tag)
    for ctx, tags in desired.values():
        ctx.tags = sorted(tags)
