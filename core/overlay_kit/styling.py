"""Overlay styling constants — generic defaults only.

Domain-specific styling (recall's HELP_* colors, sizes, paddings) stays
in plugin/recall/recall_overlay_shared.py because it is tuned for the
recall UX. Only put truly generic, sane defaults here that any overlay
might want to fall back on.
"""

# Default corner radius for pill-shaped controls (small).
DEFAULT_CORNER_RADIUS = 12

# Default corner radius for full panels (large).
DEFAULT_PANEL_CORNER_RADIUS = 16

# Default panel padding (used by draw_close_hint when caller doesn't override).
DEFAULT_PANEL_PAD = 40
