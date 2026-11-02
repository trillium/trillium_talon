"""Follow-on Hints — transient hint strip after primary commands.

Shows a horizontal strip near the top of the screen with available
follow-on actions (left-aligned) and optional preview text (right of pills,
wrapping to multiple lines if needed).

Non-interactive: does not block mouse events.

Usage from other modules:
    actions.user.show_follow_on_hints("nuke_left")
    actions.user.show_follow_on_hints("destroy", "the deleted text here")
"""

from talon import Module, actions, cron, skia, ui
from talon.canvas import Canvas
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

mod = Module()

# ---------------------------------------------------------------------------
# Hint registry: maps command names to lists of follow-on command labels
# ---------------------------------------------------------------------------
FOLLOW_ON_HINTS: dict[str, list[str]] = {
    "destroy": ["restore destroy", "restore nuke"],
    "friction": ["friction end"],
}

# ---------------------------------------------------------------------------
# Rendering state
# ---------------------------------------------------------------------------
_canvas: Canvas = None
_hide_job = None
_hints: list[str] = []
_preview_text: str = ""

# Visual constants
STRIP_Y_OFFSET = 28  # pixels from top — below mode indicator bar
PILL_RADIUS = 8
FONT_SIZE = 22
PILL_H_PAD = 10
PILL_V_PAD = 3
ITEM_GAP = 6
STRIP_H_PAD = 12
LINE_HEIGHT = 38
LINE_GAP = 4  # gap between wrapped lines

AUTO_HIDE_DURATION = "6s"

# Colors
STRIP_BG = "1a1a1acc"
PILL_BG = "334455dd"
PILL_TEXT = "ddeeffff"
LABEL_TEXT = "888888ff"
LABEL_PREFIX = "then: "
PREVIEW_LABEL_COLOR = "888888ff"
PREVIEW_TEXT_COLOR = "ffcc66ff"


def _wrap_text(text: str, max_width: float, paint) -> list[str]:
    """Break text into lines that fit within max_width."""
    if not text:
        return []
    words = text.split(" ")
    lines = []
    current_line = ""
    for word in words:
        candidate = f"{current_line} {word}" if current_line else word
        w = paint.measure_text(candidate)[1].width
        if w <= max_width and "\n" not in word:
            current_line = candidate
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def _on_draw(c: SkiaCanvas):
    hints = _hints
    if not hints:
        return

    screen: Screen = ui.main_screen()
    rect = screen.rect

    c.paint.style = c.paint.Style.FILL
    c.paint.textsize = FONT_SIZE

    # Measure pills
    measurements = []
    for label in hints:
        text_w = c.paint.measure_text(label)[1].width
        pill_w = text_w + PILL_H_PAD * 2
        measurements.append((label, pill_w, text_w))

    # Measure the "then:" prefix label
    label_w = c.paint.measure_text(LABEL_PREFIX)[1].width

    pills_w = sum(pw for _, pw, _ in measurements) + ITEM_GAP * max(
        len(measurements) - 1, 0
    )
    left_content_w = label_w + 6 + pills_w

    # Measure preview if present
    preview_lines = []
    preview_label = "deleted: "
    preview_label_w = 0
    if _preview_text:
        preview_label_w = c.paint.measure_text(preview_label)[1].width
        # Available width for preview text: screen width minus left content, padding, gaps
        right_margin = STRIP_H_PAD
        preview_gap = ITEM_GAP * 3  # gap between pills and preview
        available_w = (
            rect.width
            - STRIP_H_PAD * 2
            - left_content_w
            - preview_gap
            - preview_label_w
            - right_margin
        )
        if available_w > 50:
            preview_lines = _wrap_text(_preview_text, available_w, c.paint)

    # Calculate total strip dimensions
    num_lines = max(1, len(preview_lines)) if preview_lines else 1
    total_height = LINE_HEIGHT * num_lines + LINE_GAP * max(num_lines - 1, 0)

    # Full width strip, left-aligned content
    strip_w = rect.width - STRIP_H_PAD * 2
    strip_x = rect.left + STRIP_H_PAD
    strip_y = rect.top + STRIP_Y_OFFSET

    # Strip background (SVG: Path.add_rounded_rect is gone on new builds)
    c.paint.color = STRIP_BG
    strip_rect = Rect(strip_x, strip_y, strip_w, total_height)
    sr_ = min(PILL_RADIUS, strip_rect.width / 2, strip_rect.height / 2)
    sx, sy, sw, sh = strip_rect.x, strip_rect.y, strip_rect.width, strip_rect.height
    path = skia.Path.from_svg(
        f"M {sx + sr_} {sy} "
        f"L {sx + sw - sr_} {sy} "
        f"A {sr_} {sr_} 0 0 1 {sx + sw} {sy + sr_} "
        f"L {sx + sw} {sy + sh - sr_} "
        f"A {sr_} {sr_} 0 0 1 {sx + sw - sr_} {sy + sh} "
        f"L {sx + sr_} {sy + sh} "
        f"A {sr_} {sr_} 0 0 1 {sx} {sy + sh - sr_} "
        f"L {sx} {sy + sr_} "
        f"A {sr_} {sr_} 0 0 1 {sx + sr_} {sy} Z"
    )
    c.draw_path(path)

    # Vertical centering for first line
    pill_y = strip_y + (LINE_HEIGHT - FONT_SIZE - PILL_V_PAD * 2) / 2
    text_y = pill_y + PILL_V_PAD + FONT_SIZE

    # "then:" label
    c.paint.color = LABEL_TEXT
    label_x = strip_x + STRIP_H_PAD
    c.draw_text(LABEL_PREFIX, label_x, text_y)

    x = label_x + label_w + 6

    # Draw each pill
    for label, pill_w, text_w in measurements:
        # Pill background (SVG: Path.add_rounded_rect is gone on new builds)
        c.paint.color = PILL_BG
        pr = Rect(x, pill_y, pill_w, FONT_SIZE + PILL_V_PAD * 2)
        pr_ = min(PILL_RADIUS, pr.width / 2, pr.height / 2)
        qx, qy, qw, qh = pr.x, pr.y, pr.width, pr.height
        pp = skia.Path.from_svg(
            f"M {qx + pr_} {qy} "
            f"L {qx + qw - pr_} {qy} "
            f"A {pr_} {pr_} 0 0 1 {qx + qw} {qy + pr_} "
            f"L {qx + qw} {qy + qh - pr_} "
            f"A {pr_} {pr_} 0 0 1 {qx + qw - pr_} {qy + qh} "
            f"L {qx + pr_} {qy + qh} "
            f"A {pr_} {pr_} 0 0 1 {qx} {qy + qh - pr_} "
            f"L {qx} {qy + pr_} "
            f"A {pr_} {pr_} 0 0 1 {qx + pr_} {qy} Z"
        )
        c.draw_path(pp)

        # Pill text
        c.paint.color = PILL_TEXT
        c.draw_text(label, x + PILL_H_PAD, text_y)
        x += pill_w + ITEM_GAP

    # Draw preview text on the same line, after the pills
    if preview_lines:
        preview_x = x + ITEM_GAP * 2  # extra gap before preview

        for i, line in enumerate(preview_lines):
            line_y_offset = i * (LINE_HEIGHT + LINE_GAP)
            line_text_y = text_y + line_y_offset

            # "deleted:" label only on first line
            if i == 0:
                c.paint.color = PREVIEW_LABEL_COLOR
                c.draw_text(preview_label, preview_x, line_text_y)
                c.paint.color = PREVIEW_TEXT_COLOR
                c.draw_text(line, preview_x + preview_label_w, line_text_y)
            else:
                # Subsequent lines align with where text starts (after label)
                c.paint.color = PREVIEW_TEXT_COLOR
                c.draw_text(line, preview_x + preview_label_w, line_text_y)


def _show(hints: list[str], preview: str = ""):
    """Display the hint strip with the given labels and optional preview text."""
    global _canvas, _hide_job, _hints, _preview_text

    # Cancel any pending hide
    if _hide_job:
        cron.cancel(_hide_job)
        _hide_job = None

    _hints = hints
    _preview_text = preview

    if _canvas:
        _canvas.freeze()
    else:
        screen: Screen = ui.main_screen()
        _canvas = Canvas.from_screen(screen)
        _canvas.blocks_mouse = False
        _canvas.register("draw", _on_draw)
        _canvas.freeze()

    _hide_job = cron.after(AUTO_HIDE_DURATION, _hide)


def _hide():
    """Hide the hint strip."""
    global _canvas, _hide_job, _hints, _preview_text
    _hints = []
    _preview_text = ""
    if _hide_job:
        cron.cancel(_hide_job)
        _hide_job = None
    if _canvas:
        _canvas.unregister("draw", _on_draw)
        _canvas.close()
        _canvas = None


@mod.action_class
class Actions:
    def show_follow_on_hints(command_name: str, preview: str = ""):
        """Show follow-on hint pills for a given primary command.

        Optionally pass preview text to display on the same line after the pills.
        """
        hints = FOLLOW_ON_HINTS.get(command_name)
        if hints:
            _show(hints, preview)

    def hide_follow_on_hints():
        """Hide the follow-on hints strip immediately."""
        _hide()
