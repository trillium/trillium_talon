"""core.overlay_kit — shared low-level overlay primitives.

This kit is the home for drawing helpers and lifecycle plumbing that
multiple overlays need (recall, cursorless scope support, future
plugins). It deliberately does NOT compete with
``trillium/utils/overlay_kit.py``, which is the higher-level
``DismissibleOverlay`` class for activity-style panels. This kit
sits one layer below — pure functions plus a tiny registry — so the
recall overlays (which have their own bespoke show/hide logic) can
share primitives without inheriting an unwanted base class.

Public API:

    from core.overlay_kit import (
        draw_rounded_rect,
        draw_panel_frame,
        draw_close_hint,
        pills_overlap,
        set_overlay_active,
        register_overlay_ctx,
        is_overlay_active,
        DEFAULT_CORNER_RADIUS,
        DEFAULT_PANEL_CORNER_RADIUS,
        DEFAULT_PANEL_PAD,
    )

Lifecycle model (Option B from the refactor brief):

    Each named overlay binds itself to a Talon Context + tag string
    via ``register_overlay_ctx(name, ctx, tag)``. Subsequent calls
    to ``set_overlay_active(name, active)`` flip that tag based on
    whether any overlay bound to it is currently active. The four
    legacy recall overlays ("labels", "status", "help", "prompt")
    are lazily auto-registered to recall_state.overlay_ctx with the
    tag "user.recall_overlay_visible", so existing recall callers
    keep working unchanged.
"""

from .lifecycle import (
    is_overlay_active,
    register_overlay_ctx,
    set_overlay_active,
)
from .primitives import (
    draw_close_hint,
    draw_panel_frame,
    draw_rounded_rect,
    pills_overlap,
)
from .styling import (
    DEFAULT_CORNER_RADIUS,
    DEFAULT_PANEL_CORNER_RADIUS,
    DEFAULT_PANEL_PAD,
)

__all__ = [
    "DEFAULT_CORNER_RADIUS",
    "DEFAULT_PANEL_CORNER_RADIUS",
    "DEFAULT_PANEL_PAD",
    "draw_close_hint",
    "draw_panel_frame",
    "draw_rounded_rect",
    "is_overlay_active",
    "pills_overlap",
    "register_overlay_ctx",
    "set_overlay_active",
]
