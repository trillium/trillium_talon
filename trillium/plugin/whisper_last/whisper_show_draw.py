"""Whisper show drawing — layout and rendering for the transcription picker UI."""

from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...utils.overlay_kit import (
    DismissibleOverlay,
    draw_dim_backdrop,
    draw_panel_frame,
    draw_separator,
)
from ...utils.overlay_selector import overlay_labels
from .whisper_data import WhisperRow, short_time

# ── Colors ──
DIM_BG = "000000cc"
PANEL_BG = "1a2e2eee"
PANEL_BORDER = "4a8a7a"
CORNER_RADIUS = 16
PANEL_PAD = 40
TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
ACCENT = "5ab5a0"
TIME_COLOR = "d4a55a"
HEADER_COLOR = "ffffffff"
LINE_COLOR = "3a5a5a"

# ── Font sizes ──
HEADER_SIZE = 32
SUBTITLE_SIZE = 14
ROW_HEIGHT = 32
FONT_SIZE = 16
LABEL_SIZE = 18
HINT_SIZE = 14

# ── Column widths ──
# Wider than activity's panel: transcript previews are the main content.
LABEL_COL_W = 40
TIME_COL_W = 90
TRANSCRIPT_COL_W = 560

# Max characters of transcript to show before ellipsizing.
PREVIEW_MAX = 68


def _preview(text: str) -> str:
    """Collapse a transcript to a single ellipsized line for row display."""
    single = " ".join(text.split())
    if len(single) > PREVIEW_MAX:
        return single[:PREVIEW_MAX] + "…"
    return single


def draw_row(c: SkiaCanvas, row: WhisperRow, label: str, cx: float, cy: float):
    """Draw a single transcription row at the given y position."""
    col_x = cx
    # Selector letter
    c.paint.textsize = LABEL_SIZE
    c.paint.color = ACCENT
    c.paint.font.embolden = True
    c.draw_text(label, col_x, cy + FONT_SIZE)
    c.paint.font.embolden = False
    col_x += LABEL_COL_W
    # Timestamp
    c.paint.textsize = FONT_SIZE
    c.paint.color = TIME_COLOR
    c.draw_text(short_time(row.timestamp), col_x, cy + FONT_SIZE)
    col_x += TIME_COL_W
    # Transcript preview
    c.paint.color = TEXT_COLOR
    c.draw_text(_preview(row.transcription), col_x, cy + FONT_SIZE)


def draw_panel(
    c: SkiaCanvas,
    overlay: DismissibleOverlay,
    rows: list[WhisperRow],
    labels: list[str] | None = None,
):
    """Draw the full whisper transcription picker panel."""
    screen = ui.main_screen()
    sr = screen.rect
    draw_dim_backdrop(c, sr, DIM_BG)
    row_count = len(rows)
    c.paint.textsize = FONT_SIZE

    panel_w = PANEL_PAD * 2 + LABEL_COL_W + TIME_COL_W + TRANSCRIPT_COL_W
    panel_h = (
        PANEL_PAD
        + HEADER_SIZE
        + 8
        + SUBTITLE_SIZE
        + 16
        + ROW_HEIGHT
        + ROW_HEIGHT * max(row_count, 1)
        + 16
        + HINT_SIZE
        + PANEL_PAD
    )
    panel_x = sr.x + (sr.width - panel_w) / 2
    panel_y = sr.y + (sr.height - panel_h) / 2
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    overlay.set_panel_rect(panel_rect)
    draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_BG, PANEL_BORDER)

    c.save()
    c.clip_rect(panel_rect)
    cx = panel_x + PANEL_PAD
    cy = panel_y + PANEL_PAD

    # Header
    c.paint.textsize = HEADER_SIZE
    c.paint.color = HEADER_COLOR
    c.draw_text("Whisper Transcriptions", cx, cy + HEADER_SIZE)
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)
    cy += HEADER_SIZE + 8

    # Subtitle
    c.paint.textsize = SUBTITLE_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text(
        f'{row_count} recent  ·  "pick <letter>" to paste',
        cx,
        cy + SUBTITLE_SIZE,
    )
    cy += SUBTITLE_SIZE + 16

    # Column headers
    col_x = cx
    c.paint.textsize = FONT_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text("#", col_x, cy + FONT_SIZE)
    col_x += LABEL_COL_W
    c.draw_text("TIME", col_x, cy + FONT_SIZE)
    col_x += TIME_COL_W
    c.draw_text("TRANSCRIPT", col_x, cy + FONT_SIZE)
    cy += ROW_HEIGHT
    draw_separator(c, cx, cx + panel_w - PANEL_PAD * 2, cy - 8, LINE_COLOR)

    # Data rows
    if row_count == 0:
        c.paint.textsize = FONT_SIZE
        c.paint.color = DIM_COLOR
        c.draw_text("No transcriptions found.", cx, cy + FONT_SIZE)
    else:
        if labels is None:
            labels = overlay_labels(row_count, mode="letter")
        for i, row in enumerate(rows):
            draw_row(c, row, labels[i], cx, cy)
            cy += ROW_HEIGHT

    # Bottom hint
    cy += 8
    c.paint.textsize = HINT_SIZE
    c.paint.color = DIM_COLOR
    c.draw_text('"whisper show close" or esc to dismiss', cx, cy + HINT_SIZE)
    c.restore()
