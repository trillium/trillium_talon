"""Shared drawing primitives and dismissible overlay base for panels.

Each overlay keeps its own color constants and passes them in as arguments.
DismissibleOverlay provides shared lifecycle: click-outside-dismiss,
escape key, X close hint, auto-hide timer.
"""

from typing import Callable, Optional

from talon import Context, Module, cron, skia, ui
from talon.canvas import Canvas, MouseEvent
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

mod = Module()
mod.tag("overlay_visible", desc="A dismissible overlay is currently showing")

_overlay_ctx = Context()

# Registry of active overlays for shared escape handling
_active_overlays: list = []


def focused_screen() -> Screen:
    """Screen holding the focused window, else the main screen."""
    try:
        screen = ui.active_window().screen
        if screen is not None:
            return screen
    except Exception:
        pass
    return ui.main_screen()


def draw_rounded_rect(c: SkiaCanvas, rect: Rect, radius: float):
    """Draw a rounded rectangle using a Skia path.

    Newer Talon builds removed the Path builder methods (add_rounded_rect,
    move_to, ...), so the shape is built as an SVG path instead.
    """
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


def draw_panel_frame(
    c: SkiaCanvas, rect: Rect, radius: float, fill_color: str, border_color: str
):
    """Draw panel background + border."""
    c.paint.style = c.paint.Style.FILL
    c.paint.color = fill_color
    draw_rounded_rect(c, rect, radius)
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = border_color
    draw_rounded_rect(c, rect, radius)
    c.paint.style = c.paint.Style.FILL


def draw_close_hint(
    c: SkiaCanvas,
    close_text: str,
    hint_size: float,
    dim_color: str,
    panel_x: float,
    panel_y: float,
    panel_w: float,
    panel_pad: float,
):
    """Draw close hint text + X in the top-right of a panel."""
    c.paint.textsize = hint_size
    c.paint.color = dim_color
    close_w = c.paint.measure_text(close_text)[1].width
    x_size = 14
    gap = 10
    total_hint_w = close_w + gap + x_size
    close_x = panel_x + panel_w - panel_pad - total_hint_w
    c.draw_text(close_text, close_x, panel_y + panel_pad + hint_size)

    # X mark
    x_x = close_x + close_w + gap
    x_cy = panel_y + panel_pad + hint_size / 2
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = dim_color
    c.draw_line(x_x, x_cy - x_size / 2, x_x + x_size, x_cy + x_size / 2)
    c.draw_line(x_x, x_cy + x_size / 2, x_x + x_size, x_cy - x_size / 2)
    c.paint.style = c.paint.Style.FILL


def draw_dim_backdrop(c: SkiaCanvas, screen_rect: Rect, color: str = "000000cc"):
    """Draw a full-screen semi-transparent backdrop."""
    c.paint.style = c.paint.Style.FILL
    c.paint.color = color
    c.draw_rect(
        Rect(screen_rect.x, screen_rect.y, screen_rect.width, screen_rect.height)
    )


def draw_separator(c: SkiaCanvas, x1: float, x2: float, y: float, color: str):
    """Draw a horizontal separator line."""
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 1
    c.paint.color = color
    c.draw_line(x1, y, x2, y)
    c.paint.style = c.paint.Style.FILL


def _update_overlay_tag():
    """Set or clear the shared overlay_visible tag."""
    if _active_overlays:
        _overlay_ctx.tags = ["user.overlay_visible"]
    else:
        _overlay_ctx.tags = []


class DismissibleOverlay:
    """Shared base for canvas overlays with click-outside-dismiss, escape, and auto-hide.

    Usage:
        overlay = DismissibleOverlay(on_draw=my_draw_fn, auto_hide="10s")
        overlay.show()   # creates canvas, registers mouse, sets tag
        overlay.hide()   # tears down everything

    The on_draw callback receives (canvas, panel_rect_setter) where
    panel_rect_setter is a callable to report the panel rect for
    click-outside detection: panel_rect_setter(Rect(...))
    """

    def __init__(
        self,
        on_draw: Callable,
        auto_hide: Optional[str] = "10s",
        close_hint_text: str = "esc to close",
        close_hint_size: float = 14,
        close_hint_color: str = "aaaaaaff",
        on_hide: Optional[Callable] = None,
        blocks_mouse: bool = True,
        follow_focus: bool = False,
    ):
        self._user_on_draw = on_draw
        self._auto_hide = auto_hide
        self._close_hint_text = close_hint_text
        self._close_hint_size = close_hint_size
        self._close_hint_color = close_hint_color
        self._on_hide = on_hide
        self._blocks_mouse = blocks_mouse
        self._follow_focus = follow_focus
        self._screen: Optional[Screen] = None
        self._canvas: Canvas = None
        self._hide_job = None
        self._panel_rect: Rect = None
        self._panel_rects: list[Rect] = []

    @property
    def is_showing(self) -> bool:
        return self._canvas is not None

    @property
    def screen(self) -> Screen:
        """Screen the overlay is drawn on (chosen at show(); main screen before)."""
        return self._screen or ui.main_screen()

    def set_panel_rect(self, rect: Rect):
        """Call from on_draw to set the panel rect for click-outside detection."""
        self._panel_rect = rect

    def set_panel_rects(self, rects: list[Rect]):
        """Call from on_draw to set multiple panel rects for click-outside detection."""
        self._panel_rects = rects

    def freeze(self):
        """Re-freeze the canvas to trigger a redraw."""
        if self._canvas:
            self._canvas.freeze()

    def draw_close_hint(
        self,
        c: SkiaCanvas,
        panel_x: float,
        panel_y: float,
        panel_w: float,
        panel_pad: float,
    ):
        """Draw the X close hint in the top-right of the panel."""
        draw_close_hint(
            c,
            self._close_hint_text,
            self._close_hint_size,
            self._close_hint_color,
            panel_x,
            panel_y,
            panel_w,
            panel_pad,
        )

    def _on_draw(self, c: SkiaCanvas):
        self._user_on_draw(c, self)

    def _on_mouse(self, e: MouseEvent):
        """Dismiss when clicking outside the panel(s)."""
        if e.event == "mousedown" and e.button == 0:
            # Multi-rect mode: check all panel rects
            if self._panel_rects:
                if not any(r.contains(e.gpos) for r in self._panel_rects):
                    self.hide()
            # Single-rect mode
            elif self._panel_rect and not self._panel_rect.contains(e.gpos):
                self.hide()

    def show(self):
        """Create canvas with mouse dismiss, escape tag, and optional auto-hide."""
        if self._canvas:
            self._teardown()

        screen: Screen = focused_screen() if self._follow_focus else ui.main_screen()
        self._screen = screen
        self._canvas = Canvas.from_screen(screen)
        self._canvas.blocks_mouse = self._blocks_mouse
        self._canvas.register("draw", self._on_draw)
        self._canvas.register("mouse", self._on_mouse)
        self._canvas.freeze()

        _active_overlays.append(self)
        _update_overlay_tag()

        if self._auto_hide:
            self._hide_job = cron.after(self._auto_hide, self.hide)

    def _teardown(self):
        """Internal: tear down canvas without calling on_hide (used by show re-entry)."""
        if self._hide_job:
            cron.cancel(self._hide_job)
            self._hide_job = None
        if self._canvas:
            self._canvas.unregister("draw", self._on_draw)
            self._canvas.unregister("mouse", self._on_mouse)
            self._canvas.close()
            self._canvas = None
        self._panel_rect = None
        self._panel_rects = []
        if self in _active_overlays:
            _active_overlays.remove(self)
        _update_overlay_tag()

    def hide(self):
        """Tear down canvas, unregister handlers, clear tag."""
        was_showing = self._canvas is not None
        if self._hide_job:
            cron.cancel(self._hide_job)
            self._hide_job = None
        if self._canvas:
            self._canvas.unregister("draw", self._on_draw)
            self._canvas.unregister("mouse", self._on_mouse)
            self._canvas.close()
            self._canvas = None
        self._panel_rect = None
        self._panel_rects = []
        if self in _active_overlays:
            _active_overlays.remove(self)
        _update_overlay_tag()
        if was_showing and self._on_hide:
            self._on_hide()


# ── Semantic highlight palette ──────────────────────────────────
# Import these instead of defining locally per-panel.

HIGHLIGHT_PLAYING       = "5ab5a0"      # teal  — currently playing / system-active
HIGHLIGHT_PLAYING_FILL  = "1A6B5C59"   # teal ~35% alpha — playing row background
HIGHLIGHT_SELECTED      = "f5c518"     # amber — user-selected / focused
HIGHLIGHT_SELECTED_FILL = "f5c51820"   # amber ~12% alpha — selected row background
HIGHLIGHT_CURRENT       = "44cc66"     # green — system current (mic, mode)


def draw_left_bar(c, x: float, y: float, h: float, color: str, width: int = 4):
    """Colored left-border bar — signals playing or active state."""
    c.paint.color = color
    c.paint.style = c.paint.Style.FILL
    c.draw_rect(Rect(x, y, width, h))


def draw_row_highlight(c, x: float, y: float, w: float, h: float,
                       bar_color: str = None, fill_color: str = None,
                       bar_width: int = 4):
    """Highlight a row with optional background fill and/or left bar.

    playing  → bar_color=HIGHLIGHT_PLAYING,  fill_color=HIGHLIGHT_PLAYING_FILL
    selected → bar_color=HIGHLIGHT_SELECTED, fill_color=HIGHLIGHT_SELECTED_FILL
    current  → bar_color=HIGHLIGHT_CURRENT,  no fill
    """
    if fill_color:
        c.paint.color = fill_color
        c.paint.style = c.paint.Style.FILL
        c.draw_rect(Rect(x, y, w, h))
    if bar_color:
        draw_left_bar(c, x, y, h, bar_color, bar_width)


@mod.action_class
class Actions:
    def dismiss_overlay():
        """Dismiss the topmost active overlay (shared escape handler)"""
        if _active_overlays:
            _active_overlays[-1].hide()
