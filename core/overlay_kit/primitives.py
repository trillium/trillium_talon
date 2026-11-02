"""Overlay primitives — pure drawing helpers shared by every overlay.

Extracted from plugin/recall/recall_overlay_shared.py during the
recall->kit refactor (2026-06-09).

Nothing here knows about recall, cursorless, or any specific overlay
domain. All callers pass in their own colors, sizes, text, and rects.

Public API:
    draw_rounded_rect(c, rect, radius)
    draw_panel_frame(c, rect, *, bg_color, border_color,
                     corner_radius, border_width=2)
    draw_close_hint(c, panel_x, panel_y, panel_w, *, font_size,
                    color, text='"close" or Esc',
                    panel_pad=DEFAULT_PANEL_PAD)
    pills_overlap(a, b) -> bool
"""

from talon import skia
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from .styling import DEFAULT_PANEL_PAD


def draw_rounded_rect(c: SkiaCanvas, rect: Rect, radius: float):
    """Draw a rounded rectangle using a Skia path.

    The radius is clamped so it never exceeds half the smaller dimension,
    which prevents Skia from drawing a degenerate path.
    """
    r = min(radius, rect.width / 2, rect.height / 2)
    # NOTE: newer Talon builds removed Path.add_rounded_rect, so the shape
    # is built as an SVG path instead (same uniform-radius geometry).
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
    c: SkiaCanvas,
    rect: Rect,
    *,
    bg_color: str,
    border_color: str,
    corner_radius: float,
    border_width: float = 2,
):
    """Draw a panel: filled rounded rectangle + stroked border.

    Restores paint.style to FILL on exit so subsequent draws inherit
    the same convention every recall overlay assumed.
    """
    c.paint.style = c.paint.Style.FILL
    c.paint.color = bg_color
    draw_rounded_rect(c, rect, corner_radius)
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = border_width
    c.paint.color = border_color
    draw_rounded_rect(c, rect, corner_radius)
    c.paint.style = c.paint.Style.FILL


def draw_close_hint(
    c: SkiaCanvas,
    panel_x: float,
    panel_y: float,
    panel_w: float,
    *,
    font_size: float,
    color: str,
    text: str = '"close" or Esc',
    panel_pad: float = DEFAULT_PANEL_PAD,
):
    """Draw a close hint text + X glyph in the top-right of a panel.

    The X is drawn from two stroked diagonal lines at a fixed 14 px size,
    matching the original recall styling. paint.style is restored to FILL
    on exit.
    """
    c.paint.textsize = font_size
    c.paint.color = color
    close_w = c.paint.measure_text(text)[1].width
    x_size = 14
    gap = 10
    total_hint_w = close_w + gap + x_size
    close_x = panel_x + panel_w - panel_pad - total_hint_w
    c.draw_text(text, close_x, panel_y + panel_pad + font_size)

    x_x = close_x + close_w + gap
    x_cy = panel_y + panel_pad + font_size / 2
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = color
    c.draw_line(x_x, x_cy - x_size / 2, x_x + x_size, x_cy + x_size / 2)
    c.draw_line(x_x, x_cy + x_size / 2, x_x + x_size, x_cy - x_size / 2)
    c.paint.style = c.paint.Style.FILL


def pills_overlap(a: Rect, b: Rect) -> bool:
    """Return True if rectangles a and b overlap (touching edges do not count)."""
    return (
        a.x < b.x + b.width
        and a.x + a.width > b.x
        and a.y < b.y + b.height
        and a.y + a.height > b.y
    )
