"""
Rowing Pacer — Drop-in module for mode indicator

Animates a dot traversing the rounded rectangle border of the mode indicator bar
at a configurable pace (strokes per minute). Registers its own draw hook on the
existing canvas — no modifications to mode_indicator.py needed.

State is managed via the mode_indicator_state.json pattern for consistency.
"""

import json
import math
import time
from pathlib import Path

from talon import Module, app, cron, registry, settings, skia, ui
from talon.ui import Rect

from . import mode_indicator as mi

mod = Module()

# Path to shared state file (written by mode_indicator_state.py)
STATE_FILE = Path(__file__).parent / "mode_indicator_state.json"

# Local pacer state — merged with mode_indicator state on disk
_pacer_state = {
    "pacer_active": False,
    "pacer_spm": 18,  # Strokes per minute
}

_animator = None  # Global animator instance


class BorderPath:
    """
    U-shaped path for the rowing pacer dot.

    top-left → down left edge → bottom-left arc →
    across bottom → bottom-right arc → up right edge → top-right.
    Then teleports back to start.
    """

    def __init__(self, bar_left: float, bar_top: float, bar_right: float, bar_height: float, radius: float = 8):
        self.bx = bar_left
        self.by = bar_top
        self.bw = bar_right - bar_left
        self.bh = bar_height
        self.r = radius

        self.left = self.bh - self.r
        self.bl_arc = math.pi * self.r / 2
        self.bottom = self.bw - 2 * self.r
        self.br_arc = math.pi * self.r / 2
        self.right = self.bh - self.r

        self.total = self.left + self.bl_arc + self.bottom + self.br_arc + self.right

    def position_at_fraction(self, fraction: float) -> tuple[float, float]:
        """Get (x, y) at fraction. 0 = top-left, 1 = top-right."""
        d = max(0.0, min(1.0, fraction)) * self.total

        # 1. Left edge: top-left down
        if d <= self.left:
            return self.bx, self.by + d
        d -= self.left

        # 2. Bottom-left arc
        if d <= self.bl_arc:
            angle = d / self.bl_arc * (math.pi / 2)
            cx = self.bx + self.r
            cy = self.by + self.bh - self.r
            return cx - self.r * math.cos(angle), cy + self.r * math.sin(angle)
        d -= self.bl_arc

        # 3. Bottom edge: left to right
        if d <= self.bottom:
            return self.bx + self.r + d, self.by + self.bh
        d -= self.bottom

        # 4. Bottom-right arc
        if d <= self.br_arc:
            angle = d / self.br_arc * (math.pi / 2)
            cx = self.bx + self.bw - self.r
            cy = self.by + self.bh - self.r
            return cx + self.r * math.sin(angle), cy + self.r * math.cos(angle)
        d -= self.br_arc

        # 5. Right edge: bottom up to top-right
        return self.bx + self.bw, self.by + self.bh - self.r - d


class PacerAnimator:
    """Manages timing and animation state for the rowing pacer."""

    def __init__(self, spm: float = 18):
        self.spm = spm
        self.period_seconds = 60.0 / spm
        self.start_time = time.time()

    def get_fraction(self) -> float:
        """Return current position as fraction (0-1) along the U path."""
        elapsed = time.time() - self.start_time
        return (elapsed % self.period_seconds) / self.period_seconds

    def set_spm(self, spm: float):
        """Update pace; restart the cycle to align with new rate."""
        self.spm = spm
        self.period_seconds = 60.0 / spm
        self.start_time = time.time()


def _load_pacer_state():
    """Load pacer state from shared state file."""
    try:
        data = json.loads(STATE_FILE.read_text())
        for key in _pacer_state:
            if key in data:
                _pacer_state[key] = data[key]
    except Exception:
        pass


def _save_pacer_state():
    """Merge pacer state into shared state file."""
    try:
        on_disk = json.loads(STATE_FILE.read_text())
    except Exception:
        on_disk = {}
    on_disk.update(_pacer_state)
    with open(STATE_FILE, "w") as f:
        json.dump(on_disk, f, indent=2)


def on_pacer_draw(c):
    """Draw callback registered on the mode indicator canvas."""
    global _animator

    if not _pacer_state["pacer_active"]:
        return

    # Get current screen and bar geometry
    screen = ui.main_screen()
    rect = screen.rect
    scale = screen.scale if app.platform != "mac" else 1

    bar_height = settings.get("user.mode_indicator_bar_height") * scale
    bar_left = rect.width * settings.get("user.mode_indicator_bar_left_x")
    bar_right = rect.width * settings.get("user.mode_indicator_bar_right_x")
    radius = 8  # Matches mode_indicator.py's rad=8

    # Create animator on first draw, or if SPM changed
    if _animator is None or _animator.spm != _pacer_state["pacer_spm"]:
        _animator = PacerAnimator(_pacer_state["pacer_spm"])

    # Get current position along border
    border = BorderPath(bar_left, rect.top, bar_right, bar_height, radius)
    fraction = _animator.get_fraction()
    dot_x, dot_y = border.position_at_fraction(fraction)

    # Draw the dot
    c.paint.shader = None
    c.paint.imagefilter = None
    c.paint.style = c.paint.Style.FILL
    c.paint.color = "00ff00ff"  # Bright green
    c.draw_circle(dot_x, dot_y, 3)  # 3-pixel radius


_hooked_canvas = None  # Track which canvas we've registered on


def _ensure_hooked():
    """Re-register draw callback if mode indicator canvas was recreated."""
    global _hooked_canvas
    if mi.canvas and mi.canvas is not _hooked_canvas:
        mi.canvas.register("draw", on_pacer_draw)
        _hooked_canvas = mi.canvas


@mod.action_class
class PacerActions:
    def rowing_pacer_start(spm: int = 18):
        """Start the rowing pacer at given strokes per minute (default 18)"""
        _pacer_state["pacer_active"] = True
        _pacer_state["pacer_spm"] = max(10, min(120, spm))
        _save_pacer_state()
        global _animator
        _animator = PacerAnimator(_pacer_state["pacer_spm"])
        # Trigger redraw
        if mi.canvas:
            mi.canvas.freeze()

    def rowing_pacer_stop():
        """Stop the rowing pacer"""
        _pacer_state["pacer_active"] = False
        _save_pacer_state()
        if mi.canvas:
            mi.canvas.freeze()

    def rowing_pacer_set_pace(spm: int):
        """Set pacer rate in strokes per minute (10-120 range)"""
        if _pacer_state["pacer_active"]:
            _pacer_state["pacer_spm"] = max(10, min(120, spm))
            _save_pacer_state()
            global _animator
            if _animator:
                _animator.set_spm(_pacer_state["pacer_spm"])
            if mi.canvas:
                mi.canvas.freeze()

    def rowing_pacer_toggle():
        """Toggle pacer on/off"""
        _pacer_state["pacer_active"] = not _pacer_state.get("pacer_active", False)
        _save_pacer_state()
        if mi.canvas:
            mi.canvas.freeze()


def _tick():
    """Animation tick — ensure hook and trigger redraw."""
    _ensure_hooked()
    if mi.canvas and _pacer_state["pacer_active"]:
        mi.canvas.freeze()


def on_ready():
    """Initialize pacer on app ready."""
    _load_pacer_state()
    cron.interval("16ms", _tick)


app.register("ready", on_ready)
