"""Cursorless Scope Support Overlay - Bubbles for the live scope-support list.

Self-contained: drawing primitives are inlined rather than imported from
core/overlay_kit, because Talon's user-dir runtime does not support the
deep relative imports the kit was using.

Voice surface (see scope_support.talon):

    "scope support"          -> show overlay (filtered)
    "scope support show all" -> show including hidden / obvious scopes
    "scope support hide"     -> hide overlay
"""

from talon import Context, Module, actions, app, cron, skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

# ── Talon ctx + tag ────────────────────────────────────────────────────
mod = Module()
mod.tag(
    "cursorless_scope_overlay_visible",
    desc="The cursorless scope-support overlay is currently showing",
)
ctx = Context()

OVERLAY_TAG = "user.cursorless_scope_overlay_visible"
# Refresh cadence while the overlay is on. Each tick fetches both RPCs
# and triggers a Skia redraw. 500ms is responsive enough to feel "live"
# as the cursor moves and cheap enough that local-IPC overhead is fine.
REFRESH_INTERVAL = "500ms"

# ── Styling (panel) ────────────────────────────────────────────────────
# Compact strip that sits inside VS Code's header area (below the macOS
# title bar, around where the editor tab strip lives). No frame chrome.
PANEL_BG_COLOR = "0e0e22cc"
PANEL_BORDER_COLOR = "5050a8"
PANEL_CORNER_RADIUS = 8
PANEL_PAD = 0
PANEL_HORIZONTAL_PAD = 12
# Pills sit flush against the VS Code window's top border. Traffic lights
# on macOS occupy the left-most ~80px of the title bar; the pill row
# begins just past them and extends right across the top of the window.
VSCODE_HEADER_TOP_OFFSET = 0
# Left margin from window's left edge — clears the macOS traffic lights.
VSCODE_LEFT_MARGIN = 90
# Right margin from window's right edge — keeps clear of the window
# control affordances on the right side of the title bar.
VSCODE_RIGHT_MARGIN = 20
SECTION_HEADER_SIZE = 11
SECTION_HEADER_COLOR = "9999aaff"

# ── Styling (pills) ────────────────────────────────────────────────────
PILL_FONT_SIZE = 12
PILL_TEXT_COLOR_LIGHT = "ffffffff"
PILL_TEXT_COLOR_DARK = "1a1a1aff"
PILL_PAD_X = 8
PILL_PAD_Y = 3
PILL_GAP_X = 5
PILL_GAP_Y = 4
PILL_CORNER_RADIUS = 8

# Support-level → fill color.
# Amber = present in this document (but cursor isn't currently inside one
# of these scopes). Reads as "available nearby — move to use".
SUPPORT_COLORS: dict[str, str] = {
    "supportedAndPresentInEditor": "ffaa00ee",
    "supportedButNotPresentInEditor": "566a8acc",
    "supportedLegacy": "c98a2bcc",
    "unsupported": "33333399",
}
SUPPORT_TEXT_COLORS: dict[str, str] = {
    "supportedAndPresentInEditor": PILL_TEXT_COLOR_DARK,
    "supportedButNotPresentInEditor": PILL_TEXT_COLOR_LIGHT,
    "supportedLegacy": PILL_TEXT_COLOR_DARK,
    "unsupported": "aaaaaacc",
}
# Only show scopes that are actually present in the current document.
# We drop "supportedButNotPresentInEditor" entirely (not actionable right
# now) and "supportedLegacy" (rare). Trim to the one section that matters.
SUPPORT_SECTION_ORDER: list[str] = [
    "supportedAndPresentInEditor",
]
SUPPORT_SECTION_LABELS: dict[str, str] = {
    "supportedAndPresentInEditor": "",  # no header — pills alone
}

# Cursor-aware highlight: scope whose range contains the cursor right
# now. Green = "go / active / right here". Higher saturation than the
# amber present-elsewhere pills so it pops.
AT_CURSOR_SECTION_LABEL = "At cursor right now"
AT_CURSOR_BG_COLOR = "3aa84cee"
AT_CURSOR_TEXT_COLOR = PILL_TEXT_COLOR_LIGHT

# Scope types whose spoken form is so obvious / always-available that
# showing them in the overlay is noise. Edit to taste.
HIDDEN_SCOPE_TYPE_NAMES: set[str] = {
    "file",
    "document",
    "character",
    "word",
    "token",
    "line",
}

ERROR_PREFIX = "(!) "

# ── Module state ───────────────────────────────────────────────────────
_canvas: Canvas | None = None
_refresh_job = None
_scope_entries: list[dict] = []
_at_cursor_entries: list[dict] = []
_load_error: str | None = None
_show_all: bool = False


# ── Inlined drawing primitives ─────────────────────────────────────────


def _draw_rounded_rect(c: SkiaCanvas, rect: Rect, radius: float):
    # NOTE: newer Talon builds removed Path.add_rounded_rect, so the shape
    # is built as an SVG path instead (same uniform-radius geometry).
    r = min(radius, rect.width / 2, rect.height / 2)
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    if r <= 0:
        c.draw_rect(rect)
        return
    path = skia.Path.from_svg(
        f"M {x + r} {y} "
        f"L {x + w - r} {y} "
        f"A {r} {r} 0 0 1 {x + w} {y + r} "
        f"L {x + w} {y + h - r} "
        f"A {r} {r} 0 0 1 {x + w - r} {y + h} "
        f"L {x + r} {y + h} "
        f"A {r} {r} 0 0 1 {x} {y + h - r} "
        f"L {x} {y + r} "
        f"A {r} {r} 0 0 1 {x + r} {y} Z"
    )
    c.draw_path(path)


def _draw_panel_frame(c: SkiaCanvas, rect: Rect):
    c.paint.style = c.paint.Style.FILL
    c.paint.color = PANEL_BG_COLOR
    _draw_rounded_rect(c, rect, PANEL_CORNER_RADIUS)
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = PANEL_BORDER_COLOR
    _draw_rounded_rect(c, rect, PANEL_CORNER_RADIUS)
    c.paint.style = c.paint.Style.FILL


def _set_active(active: bool):
    ctx.tags = [OVERLAY_TAG] if active else []


def _vscode_is_active() -> bool:
    """True iff the currently focused window's app is VS Code.

    Used to suppress the overlay entirely when the user is in another
    app — the panel is only meaningful while editing in VS Code.
    """
    try:
        active = ui.active_window()
        if active is None or active.app is None:
            return False
        return active.app.name == "Code"
    except Exception:
        return False


def _find_vscode_rect() -> Rect | None:
    """Best-effort lookup of VS Code's window rect, for pinning the strip.

    Prefers the active window if it's VS Code; falls back to scanning all
    windows. Returns None if no VS Code window is open or all probes raise.
    """
    try:
        active = ui.active_window()
        if active is not None:
            try:
                if active.app is not None and active.app.name == "Code":
                    return active.rect
            except Exception:
                pass
    except Exception:
        pass
    try:
        for w in ui.windows():
            try:
                if w.app is not None and w.app.name == "Code":
                    r = w.rect
                    if r.width > 200 and r.height > 100:
                        return r
            except Exception:
                continue
    except Exception:
        pass
    return None


# ── Data fetch ─────────────────────────────────────────────────────────


def _fetch_scope_support() -> tuple[list[dict], str | None]:
    try:
        getter = actions.user.cursorless_get_scope_support
    except (AttributeError, KeyError):
        return [], "Talon action user.cursorless_get_scope_support is not declared. Check that cursorless-talon is loaded."
    try:
        data = getter()
        if isinstance(data, list):
            return data, None
        return [], f"Unexpected payload shape: {type(data).__name__}"
    except Exception as e:
        return [], f"cursorless_get_scope_support raised: {e!r}"


def _fetch_scopes_at_cursor() -> list[dict]:
    try:
        getter = actions.user.cursorless_get_scopes_at_cursor
    except (AttributeError, KeyError):
        return []
    try:
        data = getter()
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ── Entry helpers ──────────────────────────────────────────────────────


def _scope_type_name(entry: dict) -> str:
    st = entry.get("scopeType")
    if isinstance(st, dict):
        return str(st.get("type") or "")
    return str(st or "")


def _is_obvious(entry: dict) -> bool:
    return _scope_type_name(entry) in HIDDEN_SCOPE_TYPE_NAMES


def _entry_display_text(entry: dict) -> tuple[str, bool]:
    spoken_form = entry.get("spokenForm") or {}
    if spoken_form.get("type") == "success":
        forms = spoken_form.get("spokenForms") or []
        forms = [f for f in forms if isinstance(f, str) and f]
        if forms:
            return ", ".join(forms), False
        return ERROR_PREFIX + str(entry.get("humanReadableName", "<unnamed>")), True
    name = entry.get("humanReadableName") or _scope_type_name(entry) or "<unnamed>"
    return ERROR_PREFIX + str(name), True


def _filter_entries(entries: list[dict]) -> list[dict]:
    """Keep only entries that are actually actionable right now:
    supported AND present in the editor, and not in HIDDEN_SCOPE_TYPE_NAMES."""
    filtered: list[dict] = []
    for entry in entries:
        if entry.get("support") != "supportedAndPresentInEditor":
            continue
        if not _show_all and _is_obvious(entry):
            continue
        filtered.append(entry)
    return filtered


def _group_by_support(entries: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        groups.setdefault(entry.get("support", "unsupported"), []).append(entry)
    return groups


# ── Drawing ────────────────────────────────────────────────────────────


def _measure_pill(c: SkiaCanvas, text: str) -> tuple[float, float]:
    c.paint.textsize = PILL_FONT_SIZE
    tr = c.paint.measure_text(text)[1]
    return tr.width + PILL_PAD_X * 2, tr.height + PILL_PAD_Y * 2


def _draw_pill(c: SkiaCanvas, x: float, y: float, w: float, h: float, text: str, bg: str, fg: str, is_error: bool):
    rect = Rect(x, y, w, h)
    c.paint.style = c.paint.Style.FILL
    c.paint.color = bg
    _draw_rounded_rect(c, rect, PILL_CORNER_RADIUS)

    c.paint.style = c.paint.Style.FILL
    c.paint.color = fg
    c.paint.textsize = PILL_FONT_SIZE
    tr = c.paint.measure_text(text)[1]
    text_h = tr.height
    if is_error:
        c.paint.style = c.paint.Style.STROKE_AND_FILL
        c.paint.stroke_width = 0.6
    c.draw_text(text, x + PILL_PAD_X, y + PILL_PAD_Y + text_h)
    c.paint.style = c.paint.Style.FILL
    c.paint.stroke_width = 0


def _flow_layout(
    c: SkiaCanvas,
    entries: list[dict],
    content_x: float,
    content_y: float,
    content_w: float,
    at_cursor_types: set[str] | None = None,
    draw: bool = True,
) -> float:
    """Lay out pills strictly left-to-right in a single row. No wrapping —
    if pills overflow content_w they simply extend further right (the
    overlay sits in the title bar where this is OK)."""
    if not entries:
        return content_y
    cx = content_x
    cy = content_y
    row_h = 0.0
    types = at_cursor_types or set()
    for entry in entries:
        text, is_error = _entry_display_text(entry)
        pw, ph = _measure_pill(c, text)
        if draw:
            if _scope_type_name(entry) in types:
                bg = AT_CURSOR_BG_COLOR
                fg = AT_CURSOR_TEXT_COLOR
            else:
                support = entry.get("support", "unsupported")
                bg = SUPPORT_COLORS.get(support, SUPPORT_COLORS["unsupported"])
                fg = SUPPORT_TEXT_COLORS.get(support, PILL_TEXT_COLOR_LIGHT)
            _draw_pill(c, cx, cy, pw, ph, text, bg, fg, is_error)
        cx += pw + PILL_GAP_X
        if ph > row_h:
            row_h = ph
    return cy + row_h


def _on_draw(c: SkiaCanvas):
    # Suppress everything when VS Code is not the focused app — the
    # overlay is meaningless in other apps and shouldn't take screen real
    # estate while you're in Terminal/browser/etc.
    if not _vscode_is_active():
        return

    # Pin the strip to the top of VS Code's window if it's open; fall back
    # to the main screen's top-center when VS Code isn't found (so debugging
    # still produces a visible overlay).
    # Container we'll clamp panel_h against (so we never paint off-screen).
    sr = ui.main_screen().rect

    vscode_rect = _find_vscode_rect()
    if vscode_rect is not None:
        panel_x = vscode_rect.x + VSCODE_LEFT_MARGIN
        panel_w = vscode_rect.width - VSCODE_LEFT_MARGIN - VSCODE_RIGHT_MARGIN
        panel_y = vscode_rect.y + VSCODE_HEADER_TOP_OFFSET
    else:
        panel_x = sr.x + VSCODE_LEFT_MARGIN
        panel_w = sr.width - VSCODE_LEFT_MARGIN - VSCODE_RIGHT_MARGIN
        panel_y = sr.y + 40

    content_x = panel_x + PANEL_HORIZONTAL_PAD
    content_w = panel_w - PANEL_HORIZONTAL_PAD * 2

    # No big title block anymore — strip is compact.
    header_h = 0

    # Cursor scope-type names: pills with these types get amber-highlighted
    # inside whatever support section they appear in (no separate section).
    at_cursor_types = {
        _scope_type_name(e)
        for e in _at_cursor_entries
        if e.get("atCursor") and not _is_obvious(e)
    }

    # Pre-measure each section to size the panel.
    if _load_error is not None:
        body_h = PILL_FONT_SIZE * 6 + 12
    else:
        filtered = _filter_entries(_scope_entries)
        groups = _group_by_support(filtered)

        probe_y = 0.0
        for support_key in SUPPORT_SECTION_ORDER:
            section_entries = groups.get(support_key, [])
            if not section_entries:
                continue
            probe_y += SECTION_HEADER_SIZE + 8
            probe_y = _flow_layout(
                c, section_entries, content_x, probe_y, content_w, draw=False,
            )
            probe_y += PILL_GAP_Y * 2
        body_h = max(probe_y, PILL_FONT_SIZE)

    panel_h = PANEL_PAD + header_h + body_h + PANEL_PAD
    if panel_h > sr.height - 80:
        panel_h = sr.height - 80

    # No frame, no clip — just pills floating over VS Code.
    cy = panel_y + PANEL_PAD + header_h

    if _load_error is not None:
        # Quietly skip render on error — the overlay is always-on; spamming
        # an error panel into VS Code's header is more annoying than helpful.
        # The error will clear itself on the next refresh tick if the RPC
        # comes back online.
        return

    # Show ONLY pills whose scope range contains the cursor right now.
    # Everything else (present-but-not-at-cursor) is suppressed so the
    # row exactly answers "what can I target at my cursor?".
    at_cursor_pills = [
        e for e in _at_cursor_entries
        if e.get("atCursor") and not _is_obvious(e)
    ]
    if at_cursor_pills:
        _flow_layout(
            c, at_cursor_pills, content_x, cy, content_w,
            at_cursor_types=at_cursor_types,
        )


# ── Show / hide ────────────────────────────────────────────────────────


def _refresh_data():
    """Refetch both RPCs and force a canvas redraw."""
    global _scope_entries, _at_cursor_entries, _load_error
    # Skip the RPC poll when VS Code isn't the focused app — _on_draw is
    # already a no-op in that state, and the cursorless command server is
    # the slowest to respond exactly when its host editor is unfocused.
    # Polling anyway was the dominant source of watchdog "@2.0s" warnings.
    if not _vscode_is_active():
        return
    _scope_entries, _load_error = _fetch_scope_support()
    _at_cursor_entries = _fetch_scopes_at_cursor()
    if _canvas is not None:
        # Re-freezing a Skia canvas triggers a fresh paint with the new state.
        _canvas.freeze()


def show_overlay(show_all: bool = False):
    """Show the overlay and start the refresh loop. No auto-hide — this is
    designed to stay on. Call hide_overlay() to turn it off."""
    global _canvas, _refresh_job, _show_all

    if _refresh_job:
        cron.cancel(_refresh_job)
        _refresh_job = None
    if _canvas:
        _canvas.unregister("draw", _on_draw)
        _canvas.close()
        _canvas = None

    _show_all = show_all
    _refresh_data()  # initial fetch before first paint

    screen: Screen = ui.main_screen()
    _canvas = Canvas.from_screen(screen)
    _canvas.register("draw", _on_draw)
    _canvas.freeze()

    _refresh_job = cron.interval(REFRESH_INTERVAL, _refresh_data)
    _set_active(True)


def hide_overlay():
    """Tear down the overlay and stop refreshing."""
    global _canvas, _refresh_job
    if _refresh_job:
        cron.cancel(_refresh_job)
        _refresh_job = None
    if _canvas:
        _canvas.unregister("draw", _on_draw)
        _canvas.close()
        _canvas = None
    _set_active(False)


def _on_talon_ready():
    """Auto-show the overlay shortly after Talon finishes startup.

    Deferred a moment so cursorless-talon has time to register its actions
    before our first fetch hits them. If the actions aren't there yet,
    _fetch_scope_support returns an error and we'll still keep retrying
    on every refresh tick.
    """
    cron.after("1500ms", lambda: show_overlay(show_all=False))


# Auto-show disabled (overlay not working properly); say "scope support" to show it.
# app.register("ready", _on_talon_ready)


# ── Voice actions ──────────────────────────────────────────────────────


@mod.action_class
class Actions:
    def cursorless_scope_support_show():
        """Show the cursorless scope-support overlay (filtered)."""
        show_overlay(show_all=False)

    def cursorless_scope_support_show_all():
        """Show the cursorless scope-support overlay including obvious scopes."""
        show_overlay(show_all=True)

    def cursorless_scope_support_hide():
        """Hide the cursorless scope-support overlay."""
        hide_overlay()
