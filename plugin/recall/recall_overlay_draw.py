"""Recall Overlay Draw - Rendering logic for persistent window pills.

Extracted from recall_overlay_persistent.py to keep files under 250 lines.
Contains the on-draw callback and pill layout/rendering helpers.
"""

from talon import skia, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from .recall_overlay_shared import _get_saved_windows, _pills_overlap

PERSISTENT_COLOR_ACTIVE = "6a6aff"
PERSISTENT_COLOR_INACTIVE = "3535aa"
PERSISTENT_ALPHA_ACTIVE = "cc"
PERSISTENT_ALPHA_INACTIVE = "cc"
PERSISTENT_STROKE = 2
PERSISTENT_LABEL_SIZE = 13
PERSISTENT_LABEL_PAD_X = 8
PERSISTENT_LABEL_PAD_Y = 4
PERSISTENT_TAB_GAP = 4


def _resolve_collisions(pill_rect, pill_w, pill_h, pill_y, placed, screen_w, base_x):
    """Nudge pill_rect to avoid collisions with already-placed pills.

    Returns the final Rect after resolving overlaps.
    """
    pill_x = pill_rect.x
    for _ in range(len(placed) + 1):
        collision = next((e for e in placed if _pills_overlap(pill_rect, e)), None)
        if collision is None:
            break
        nudged_x = collision.x + collision.width + PERSISTENT_TAB_GAP
        if nudged_x + pill_w <= screen_w:
            pill_x = nudged_x
            pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)
        else:
            top = min(placed, key=lambda p: p.y)
            pill_x = base_x
            pill_y = top.y - pill_h - PERSISTENT_TAB_GAP
            pill_rect = Rect(pill_x, pill_y, pill_w, pill_h)
            break
    return pill_rect


def _draw_pill(c, pill_rect, tab_color, display_name, text_h,
               is_active: bool = False, status_color: str | None = None,
               badge_text: str = ""):
    """Draw a single pill: rounded-top rectangle background + label text.

    If status_color (6-char hex, no alpha) is provided and the pill is not
    active, it overrides tab_color (the active highlight still takes
    precedence). When status_color is None, tab_color is used verbatim,
    preserving byte-equivalent behavior with prior callers.

    If badge_text is non-empty, a small badge string is drawn in the
    bottom-right corner of the pill (font size 8, low-alpha white). When
    badge_text is "" (the default), no badge draw calls are made, keeping
    behavior byte-equivalent to prior callers.
    """
    pill_x, pill_y = pill_rect.x, pill_rect.y
    pill_w, pill_h = pill_rect.width, pill_rect.height

    if status_color and not is_active:
        fill_color = status_color + PERSISTENT_ALPHA_INACTIVE
    else:
        fill_color = tab_color
    c.paint.color = fill_color
    rad = 6
    # Newer Talon builds removed the Path builder methods
    # (move_to/line_to/arc_to), so build the same rounded-top pill as an
    # SVG path instead.
    path = skia.Path.from_svg(
        f"M {pill_x} {pill_y + rad} "
        f"A {rad} {rad} 0 0 1 {pill_x + rad} {pill_y} "
        f"L {pill_x + pill_w - rad} {pill_y} "
        f"A {rad} {rad} 0 0 1 {pill_x + pill_w} {pill_y + rad} "
        f"L {pill_x + pill_w} {pill_y + pill_h} "
        f"L {pill_x} {pill_y + pill_h} Z"
    )
    c.draw_path(path)

    c.paint.color = "ffffffff"
    c.paint.style = c.paint.Style.STROKE_AND_FILL
    c.paint.stroke_width = 0.8
    c.draw_text(display_name, pill_x + PERSISTENT_LABEL_PAD_X,
                pill_y + PERSISTENT_LABEL_PAD_Y + text_h)
    c.paint.style = c.paint.Style.FILL
    c.paint.stroke_width = 0

    if badge_text:
        c.paint.textsize = 8
        badge_rect = c.paint.measure_text(badge_text)[1]
        badge_w, badge_h = badge_rect.width, badge_rect.height
        badge_x = pill_x + pill_w - badge_w - 3
        # Vertically center the badge baseline in the bottom 1/3 of the pill.
        bottom_third_center_y = pill_y + pill_h - pill_h / 6
        badge_y = bottom_third_center_y + badge_h / 2
        c.paint.color = "ffffffaa"
        c.draw_text(badge_text, badge_x, badge_y)
        # Restore the larger label textsize so subsequent pills measure
        # correctly against PERSISTENT_LABEL_SIZE.
        c.paint.textsize = PERSISTENT_LABEL_SIZE


# AI Added: panel-map strip renderer for Herdr tabs.
def _draw_herdr_strip(c: SkiaCanvas, pill_rect, herdr_map):
    """Passive panel-map strip under a pill: one cell per Herdr pane, the
    live pane highlighted. Read-only render; never raises into the caller."""
    try:
        panes = herdr_map.get("panes", []) or []
        if not panes:
            return
        c.paint.textsize = 10
        x = pill_rect.x
        y = pill_rect.y + pill_rect.height + 3
        for pane in panes[:8]:
            label = str(pane.get("label", "?"))[:12]
            text_w = c.paint.measure_text(label)[1].width
            cell_w = text_w + 8
            cell = Rect(x, y, cell_w, 14)
            c.paint.style = c.paint.Style.FILL
            if pane.get("focused"):
                c.paint.color = PERSISTENT_COLOR_ACTIVE + PERSISTENT_ALPHA_ACTIVE
            else:
                c.paint.color = "222222cc"
            c.draw_rect(cell)
            c.paint.color = "ffffffff"
            c.draw_text(label, x + 4, y + 10)
            x += cell_w + 2
    except Exception as e:
        print(f"[recall_herdr_panels] strip draw failed: {e}")


# AI Added: herdr_map parameter threads the panel map into the pill draw.
def draw_persistent(c: SkiaCanvas, active_window_id, session_states: dict | None = None,
                    herdr_map: dict | None = None, _win_cache: dict | None = None):
    """Main draw routine for persistent pills. Returns pill hit rects.

    _win_cache is an optional id->window snapshot (see snapshot_windows_by_id).
    When None, one snapshot is taken per draw — never one scan per pill.
    Window rects are read ONCE per pill and reused for highlight drawing.

    Args:
        c: The Skia canvas to draw on.
        active_window_id: The id of the currently highlighted window, or None.
        session_states: Optional dict with a "window_sessions" key mapping
            saved-window names to their associated Claude session-state dicts
            (matched by working directory). When None or empty, no per-pill
            color/badge override is applied.
        herdr_map: Optional panel map from recall_herdr_panels for one saved
            window ({"name": str, "panes": [...]}). When present, a passive
            panel strip is drawn under that window's pill. None = no strip.

    Returns:
        List of (name, pill_rect) tuples for mouse hit-testing.
    """
    saved_windows, _ = _get_saved_windows()
    if not saved_windows:
        return []

    # P0 fix: single AX snapshot per draw (was: full ui.apps() scan per pill
    # via find_window_by_id -> ~39 x ~20 AX comparisons + rect IPC per draw).
    if _win_cache is None:
        try:
            from .recall_commands import snapshot_windows_by_id
            _win_cache = snapshot_windows_by_id()
        except Exception:
            _win_cache = {}

    # Hoist screen queries out of the per-pill loop (each is an IPC).
    try:
        _screen = ui.main_screen()
        _visible_y = _screen.visible_rect.y
        _screen_w = _screen.rect.width
    except Exception:
        return []

    entries, placed = [], []
    for name, info in list(saved_windows.items()):
        window = _win_cache.get(info.get("id"))
        if window is None:
            continue
        try:
            r = window.rect
        except Exception:
            continue
        if r.width <= 0 or r.height <= 0:
            continue

        display_name = name.title()
        c.paint.textsize = PERSISTENT_LABEL_SIZE
        text_rect = c.paint.measure_text(display_name)[1]
        text_w, text_h = text_rect.width, text_rect.height
        pill_w = text_w + PERSISTENT_LABEL_PAD_X * 2
        pill_h = text_h + PERSISTENT_LABEL_PAD_Y * 2
        base_x = r.x + r.width / 4 - pill_w / 2
        # Pin all pills to the top of the visible area (just above menu bar bottom),
        # matching the natural position of full-screen window pills.
        pill_y = _visible_y - pill_h
        pill_rect = Rect(base_x, pill_y, pill_w, pill_h)
        screen_w = _screen_w

        pill_rect = _resolve_collisions(
            pill_rect, pill_w, pill_h, pill_y, placed, screen_w, base_x)
        placed.append(pill_rect)
        entries.append((window, name, info["id"], pill_rect, text_w, text_h, r))

    hit_rects = [(name, pill_rect) for _, name, _, pill_rect, _, _, _ in entries]

    for window, name, wid, pill_rect, text_w, text_h, r in entries:
        is_active = (active_window_id is not None and wid == active_window_id)
        tab_color = (PERSISTENT_COLOR_ACTIVE + PERSISTENT_ALPHA_ACTIVE if is_active
                     else PERSISTENT_COLOR_INACTIVE + PERSISTENT_ALPHA_INACTIVE)
        if is_active:
            c.paint.style = c.paint.Style.STROKE
            c.paint.stroke_width = PERSISTENT_STROKE
            c.paint.color = PERSISTENT_COLOR_ACTIVE + PERSISTENT_ALPHA_ACTIVE
            c.draw_rect(Rect(r.x, r.y, r.width, r.height))
            c.paint.style = c.paint.Style.FILL

        status_color = None
        badge_text = ""
        if session_states:
            try:
                window_sessions = session_states.get("window_sessions", {})
                state = window_sessions.get(name)
                if state:
                    from .recall_pill_colors import (
                        status_to_color, derive_status, format_badge,
                    )
                    final_status = derive_status(
                        state.get("agent_count", 0),
                        state.get("monitor_count", 0),
                        state.get("status", "unknown"),
                    )
                    status_color = status_to_color(final_status)
                    badge_text = format_badge(
                        state.get("agent_count", 0),
                        state.get("monitor_count", 0),
                    )
            except Exception:
                status_color = None
                badge_text = ""

        _draw_pill(c, pill_rect, tab_color, name.title(), text_h,
                   is_active=is_active, status_color=status_color,
                   badge_text=badge_text)
        # AI Added: draw the Herdr strip under this window's pill.
        if herdr_map and name == herdr_map.get("name"):
            _draw_herdr_strip(c, pill_rect, herdr_map)

    return hit_rects
