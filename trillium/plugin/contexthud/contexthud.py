"""
Context HUD — "what can I say here?" — the #1 voice-stall killer (forgetting the phrase).

Renders the live voice-command surface (from voice-commands.ts --json, the tool that
parses the shipped .talon plugins) as a dismissible LIST modal, grouped by plugin.
Re-implemented to use the overlay_kit DEFAULT idiom — the same pattern as
memory/memory_overlay.py: a centered panel over a dim backdrop, drawn with the kit's
shared helpers (draw_dim_backdrop, draw_panel_frame, draw_separator, draw_close_hint)
and the shared navy palette / spacing constants, rather than a private palette and
manual per-line drawing.

  "what can I say"   → show the panel
  "hide keys"        → dismiss (also: Esc, click outside, or auto-hide)

Data source is the SAME generator that keeps the cheat sheet current, so the HUD never
drifts from the actual grammar. Grouped by plugin.

NOTE (honest): loads clean and mirrors the working memory_overlay pattern; the live
visual render can only be confirmed by Trillium triggering it ("what can I say").
"""

import json
import subprocess

from talon import Module, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from trillium.utils.overlay_kit import (
    DismissibleOverlay,
    draw_close_hint,
    draw_dim_backdrop,
    draw_panel_frame,
    draw_separator,
)

mod = Module()

_BUN = "/Users/trilliumsmith/.bun/bin/bun"
_GEN = "/Users/trilliumsmith/code/voice-cockpit/voice-commands.ts"

# ── Color palette (overlay_kit default — matches memory_overlay) ──
DIM_BG = "000000cc"
PANEL_COLOR = "1a1a2eee"
PANEL_BORDER = "4a4a8a"
CORNER_RADIUS = 16
PANEL_PAD = 40

TEXT_COLOR = "ffffffff"
DIM_COLOR = "aaaaaa"
LINE_COLOR = "4a4a6a"

ACCENT_COLOR = "e879f9ee"  # muse pink — title accent (kit lets us set any per-draw color)

HEADER_SIZE = 36
PLUGIN_SIZE = 18
ROW_CMD_SIZE = 20
ROW_DESC_SIZE = 16
HINT_SIZE = 16

ROW_PAD = 12
GROUP_GAP = 16


def _load_commands() -> list[dict]:
    """Run the generator once and parse its JSON (cached by the caller)."""
    try:
        out = subprocess.run(
            [_BUN, _GEN, "--json"], capture_output=True, text=True, timeout=6
        ).stdout
        return json.loads(out)
    except Exception:
        return []


def _group(commands: list[dict]) -> dict[str, list[dict]]:
    """Group commands by plugin, preserving first-seen order."""
    groups: dict[str, list[dict]] = {}
    for cmd in commands:
        groups.setdefault(cmd.get("plugin", "?"), []).append(cmd)
    return groups


class _Hud:
    def __init__(self):
        self._commands: list[dict] = []
        self._overlay = DismissibleOverlay(
            on_draw=self._on_draw,
            auto_hide="20s",
            close_hint_text='"hide keys" or Esc',
            close_hint_size=HINT_SIZE,
            close_hint_color=DIM_COLOR,
            blocks_mouse=True,
        )

    @property
    def is_showing(self) -> bool:
        return self._overlay.is_showing

    def show(self):
        self._commands = _load_commands()
        if self._overlay.is_showing:
            self._overlay.freeze()
            return
        self._overlay.show()

    def hide(self):
        self._overlay.hide()

    def _on_draw(self, c: SkiaCanvas, overlay: DismissibleOverlay):
        screen = ui.main_screen()
        sr = screen.rect

        # Full-screen dim backdrop.
        draw_dim_backdrop(c, sr, DIM_BG)

        groups = _group(self._commands)

        # ── Pre-calculate panel height ──
        panel_h = PANEL_PAD                         # top padding
        panel_h += HEADER_SIZE + 20                 # header + gap
        if groups:
            for cmds in groups.values():
                panel_h += PLUGIN_SIZE + ROW_PAD    # plugin header
                panel_h += len(cmds) * (ROW_CMD_SIZE + ROW_PAD)
                panel_h += GROUP_GAP                # gap after group
        else:
            panel_h += ROW_CMD_SIZE + 20            # empty state
        panel_h += PANEL_PAD                        # bottom padding

        panel_w = sr.width * 0.50

        # Clamp to screen.
        if panel_h > sr.height - 40:
            panel_h = sr.height - 40

        panel_x = sr.x + (sr.width - panel_w) / 2
        panel_y = sr.y + (sr.height - panel_h) / 2

        # ── Panel frame ──
        # trillium.utils.overlay_kit signature: (c, rect, radius, fill_color, border_color)
        panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
        overlay.set_panel_rect(panel_rect)
        draw_panel_frame(c, panel_rect, CORNER_RADIUS, PANEL_COLOR, PANEL_BORDER)

        # Clip to panel.
        c.save()
        c.clip_rect(panel_rect)

        cx = panel_x + PANEL_PAD
        cy = panel_y + PANEL_PAD
        content_w = panel_w - PANEL_PAD * 2

        # ── Header (muse-pink accent) ──
        c.paint.textsize = HEADER_SIZE
        c.paint.color = ACCENT_COLOR
        c.draw_text("What can I say?", cx, cy + HEADER_SIZE)

        # Close hint — kit helper: (c, text, size, color, panel_x, panel_y, panel_w, panel_pad)
        draw_close_hint(
            c, '"hide keys" or Esc', HINT_SIZE, DIM_COLOR,
            panel_x, panel_y, panel_w, PANEL_PAD,
        )

        cy += HEADER_SIZE + 20

        if not groups:
            c.paint.textsize = ROW_CMD_SIZE
            c.paint.color = DIM_COLOR
            c.draw_text("No commands found (voice-commands.ts --json).", cx, cy + ROW_CMD_SIZE)
            c.restore()
            return

        # ── Grouped command rows ──
        cmd_col_w = content_w * 0.45
        first = True
        for plugin, cmds in groups.items():
            if not first:
                # Separator between groups.
                cy += GROUP_GAP / 2
                draw_separator(c, cx, cx + content_w, cy, LINE_COLOR)
                cy += GROUP_GAP / 2
            first = False

            # Plugin header.
            c.paint.textsize = PLUGIN_SIZE
            c.paint.color = DIM_COLOR
            c.draw_text(plugin, cx, cy + PLUGIN_SIZE)
            cy += PLUGIN_SIZE + ROW_PAD

            # Command / description columns.
            for cmd in cmds:
                spoken = cmd.get("spoken", "")
                desc = cmd.get("desc", "")

                c.paint.textsize = ROW_CMD_SIZE
                c.paint.color = TEXT_COLOR
                c.draw_text(spoken, cx, cy + ROW_CMD_SIZE)

                if desc:
                    c.paint.textsize = ROW_DESC_SIZE
                    c.paint.color = DIM_COLOR
                    c.draw_text(desc, cx + cmd_col_w, cy + ROW_CMD_SIZE)

                cy += ROW_CMD_SIZE + ROW_PAD

        c.restore()


_hud = _Hud()


@mod.action_class
class Actions:
    def contexthud_show():
        """Show the 'what can I say' voice-command HUD."""
        _hud.show()

    def contexthud_hide():
        """Hide the voice-command HUD."""
        _hud.hide()
