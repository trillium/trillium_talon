"""OBS scene list overlay — compact panel showing all scenes with current highlighted."""
import string

from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...trillium.utils.overlay_kit import DismissibleOverlay, draw_panel_frame

from .obs_scene_state import get_scenes, get_current_scene, load_scenes

# Styling
PANEL_BG = "1a1a2eee"
PANEL_BORDER = "4a4a8a"
CORNER_RADIUS = 16
PANEL_PAD = 40
ROW_HEIGHT = 40
FONT_SIZE = 24
HEADER_SIZE = 36
CURRENT_COLOR = "aa44ffff"   # Purple for active scene
INACTIVE_COLOR = "ccccccff"  # Light gray
HEADER_COLOR = "888888ff"
HINT_COLOR = "aaaaaa"
HINT_SIZE = 16
DOT_RADIUS = 6
MIN_PANEL_W = 400


def _on_draw(c: SkiaCanvas, overlay: DismissibleOverlay):
    screen = ui.main_screen()
    rect = screen.rect

    scenes = get_scenes()
    current = get_current_scene()

    if not scenes:
        return

    # Letter label column width
    LETTER_W = 36

    # Calculate panel dimensions
    c.paint.textsize = FONT_SIZE
    max_text_w = max(c.paint.measure_text(s)[1].width for s in scenes)
    panel_w = max(max_text_w + PANEL_PAD * 2 + LETTER_W + DOT_RADIUS * 2 + 16, MIN_PANEL_W)
    panel_h = PANEL_PAD * 2 + HEADER_SIZE + 8 + ROW_HEIGHT * len(scenes) + 20 + HINT_SIZE

    # Position: centered
    panel_x = rect.x + (rect.width - panel_w) / 2
    panel_y = rect.y + (rect.height - panel_h) / 2

    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    overlay.set_panel_rect(panel_rect)

    # Panel frame
    draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_BG, PANEL_BORDER)

    # Header
    c.paint.textsize = HEADER_SIZE
    c.paint.color = HEADER_COLOR
    c.draw_text("OBS Scenes", panel_x + PANEL_PAD, panel_y + PANEL_PAD + HEADER_SIZE)

    # Close hint
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)

    # Scene rows
    letters = string.ascii_uppercase
    y = panel_y + PANEL_PAD + HEADER_SIZE + 8
    for i, scene in enumerate(scenes):
        is_current = scene == current
        row_y = y + ROW_HEIGHT * 0.7
        letter = letters[i] if i < len(letters) else "?"
        col_x = panel_x + PANEL_PAD

        # Letter label
        c.paint.textsize = FONT_SIZE
        c.paint.color = CURRENT_COLOR if is_current else HEADER_COLOR
        c.paint.font.embolden = is_current
        c.draw_text(f"{letter}.", col_x, row_y)

        # Active dot
        if is_current:
            c.paint.color = CURRENT_COLOR
            c.draw_circle(col_x + LETTER_W + DOT_RADIUS, row_y - FONT_SIZE * 0.3, DOT_RADIUS)

        # Scene name
        c.paint.textsize = FONT_SIZE
        c.paint.color = CURRENT_COLOR if is_current else INACTIVE_COLOR
        c.paint.font.embolden = is_current
        c.draw_text(scene, col_x + LETTER_W + DOT_RADIUS * 2 + 10, row_y)
        c.paint.font.embolden = False

        y += ROW_HEIGHT

    # Usage hint
    c.paint.textsize = HINT_SIZE
    c.paint.color = HINT_COLOR
    c.draw_text('"broadcast <letter>" or "<name>" to switch', panel_x + PANEL_PAD, y + 20 + HINT_SIZE)


_overlay = DismissibleOverlay(on_draw=_on_draw, auto_hide="10s")


def show():
    # Dismiss memory overlay if open (shared canvas — only one panel at a time)
    try:
        from ...trillium.memory import memory
        memory.Actions.memory_hide()
    except Exception:
        pass
    load_scenes()  # Refresh from disk before showing
    _overlay.show()


def hide():
    _overlay.hide()


def is_showing() -> bool:
    return _overlay.is_showing
