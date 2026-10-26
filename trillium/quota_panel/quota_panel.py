"""
Quota panel - one status cell per AI subscription, right of the mode-indicator bar.

Cells (CC Claude Code, OC OpenCode Go, GPT ChatGPT Plus, GRK Grok, AGY
Antigravity) show percent left, time to reset and a headroom bar, colored by
headroom (quota_data.color_for). Data comes from `quota-axi --json`, run by
quota_run.QuotaRunner as a child process that a 1s cron tick polls: the draw
path never runs a subprocess and never waits on quota-axi. It replaces the
Claude-only usage text in the bar (user.mode_indicator_show_usage = false).
See docs/quota-panel.md.
"""

import time

from talon import Module, app, cron, settings, skia, ui
from talon.canvas import Canvas
from talon.ui import Rect

from . import quota_data
from .quota_run import QuotaRunner

mod = Module()
mod.setting(
    "quota_panel_show",
    type=bool,
    default=False,
    desc="If true the per-subscription quota panel is shown right of the mode indicator bar",
)
mod.setting(
    "quota_panel_interval",
    type=int,
    default=120,
    desc="Seconds between quota-axi reads (minimum 30)",
)
mod.setting(
    "quota_panel_providers",
    type=str,
    default=quota_data.DEFAULT_PROVIDERS,
    desc="Comma list of quota-axi providers to show, in order",
)
mod.setting(
    "quota_panel_cell_w",
    type=float,
    default=66,
    desc="Width of one subscription cell in pixels",
)
mod.setting(
    "quota_panel_left_x",
    type=float,
    default=0,
    desc="Left edge of the panel (0-1 fraction of screen width). 0 = just right of the mode indicator bar",
)

MIN_INTERVAL = 30
FIRST_POLL_DELAY = 3  # seconds after load before the first read
PAD = 4
PANEL_FILL = "222222cc"  # same as the mode indicator's stream panel
PANEL_BORDER = "4a4a6acc"
TEXT = "ffffff"

_runner = QuotaRunner()
_loaded_at = time.time()
_last_start = 0.0
_force = False
_rows = None  # list[quota_data.Row] after the first good read
_last_ok = 0.0
_failed = False
canvas = None


def _get(name, fallback):
    try:
        value = settings.get(name)
    except Exception:
        return fallback
    return fallback if value is None else value


def _providers():
    return quota_data.parse_providers(_get("user.quota_panel_providers", ""))


def _interval():
    return max(MIN_INTERVAL, int(_get("user.quota_panel_interval", 120)))


def _cells(now=None):
    return quota_data.build_cells(
        _rows, _providers(), now or time.time(), _last_ok, _interval(), _failed
    )


# ── Drawing ──


def _alpha(color, dim):
    return f"{color}{'66' if dim else 'ff'}"


def _draw_frame(c, rect):
    rr = skia.RoundRect.from_rect(rect, x=8, y=8)
    c.paint.style = c.paint.Style.FILL
    c.paint.color = PANEL_FILL
    c.draw_rrect(rr)
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 2
    c.paint.color = PANEL_BORDER
    c.draw_rrect(rr)
    c.paint.style = c.paint.Style.FILL


def panel_rect(screen_rect, n_cells):
    """Panel rect: the bar's height, starting 2px right of the bar unless
    user.quota_panel_left_x is set; shifted left if it would leave the screen."""
    bar_h = float(_get("user.mode_indicator_bar_height", 25))
    cell_w = float(_get("user.quota_panel_cell_w", 66))
    left_x = float(_get("user.quota_panel_left_x", 0))
    if left_x <= 0:
        x = screen_rect.left + screen_rect.width * float(
            _get("user.mode_indicator_bar_right_x", 0.51)
        ) + 2
    else:
        x = screen_rect.left + screen_rect.width * left_x
    w = n_cells * cell_w + PAD * 2
    x = min(x, screen_rect.left + screen_rect.width - w)
    return Rect(x, screen_rect.top, w, bar_h)


def draw_cells(c, panel, cells):
    cell_w = float(_get("user.quota_panel_cell_w", 66))
    text_y = float(_get("user.mode_indicator_text_y", 11))
    c.paint.shader = None
    c.paint.imagefilter = None
    for i, cell in enumerate(cells):
        x = panel.x + PAD + i * cell_w
        box = Rect(x, panel.y, cell_w, panel.height)
        c.save()
        c.clip_rect(box)
        c.paint.style = c.paint.Style.FILL
        if cell.exhausted:
            c.paint.color = "ff333344"
            c.draw_rect(box)
        c.paint.textsize = 9
        c.paint.color = _alpha(cell.color, cell.dim)
        c.draw_text(cell.label, x + 3, text_y)
        c.paint.textsize = 10
        c.paint.color = _alpha(TEXT, cell.dim)
        c.draw_text(cell.value, x + 3 + len(cell.label) * 6 + 3, text_y)
        c.paint.textsize = 9
        c.paint.color = _alpha("cccccc", cell.dim)
        c.draw_text(cell.sub, x + 3, text_y + 12)
        bar_y = text_y + 15
        if cell.frac is not None and bar_y + 2 <= panel.height:
            bar_w = cell_w - 8
            c.paint.color = "ffffff22"
            c.draw_rect(Rect(x + 3, bar_y, bar_w, 2))
            c.paint.color = _alpha(cell.color, cell.dim)
            c.draw_rect(Rect(x + 3, bar_y, bar_w * cell.frac, 2))
        if cell.dot:
            c.paint.color = _alpha(quota_data.RED, cell.dim)
            c.draw_circle(x + cell_w - 8, 5, 2.5)
        c.restore()


def on_draw(c):
    cells = _cells()
    panel = panel_rect(ui.main_screen().rect, len(cells))
    _draw_frame(c, panel)
    draw_cells(c, panel, cells)


# ── Canvas lifecycle ──


def _show():
    global canvas
    canvas = Canvas.from_screen(ui.main_screen())
    canvas.register("draw", on_draw)
    canvas.freeze()


def _hide():
    global canvas
    if canvas:
        canvas.unregister("draw", on_draw)
        canvas.close()
        canvas = None


def _redraw():
    if canvas:
        canvas.freeze()


def _sync_canvas():
    wanted = bool(_get("user.quota_panel_show", False))
    if wanted and not canvas:
        _show()
    elif not wanted and canvas:
        _hide()


def _rebuild(_=None):
    """Recreate the canvas (screen changed)."""
    if canvas:
        _hide()
    _sync_canvas()


# ── Polling ──


def _apply(result):
    global _rows, _last_ok, _failed
    if result.error:
        _failed = True
        print(f"[quota_panel] {result.error}")
    else:
        _rows = quota_data.parse(result.data, _providers())
        _last_ok = time.time()
        _failed = False
    _redraw()


def _tick():
    """Cron (1s): poll the runner, schedule reads, keep the canvas in sync.
    Never blocks."""
    global _last_start, _force
    try:
        _sync_canvas()
        result = _runner.tick()
        if result is not None:
            _apply(result)
        if not canvas or _runner.busy:
            return
        now = time.time()
        due = now - _last_start >= _interval()
        if _force or (due and now - _loaded_at >= FIRST_POLL_DELAY):
            _force = False
            _last_start = now
            failed = _runner.start(_providers())
            if failed is not None:
                _apply(failed)
    except Exception as e:
        print(f"[quota_panel] tick failed: {e}")


def _tick_redraw():
    """Cron (30s): reset countdowns and the stale label age without a new read."""
    _redraw()


cron.interval("1s", _tick)
cron.interval("30s", _tick_redraw)


def _on_ready():
    ui.register("screen_change", _rebuild)


app.register("ready", _on_ready)


@mod.action_class
class Actions:
    def quota_panel_refresh():
        """Read quota-axi again now"""
        global _force
        _force = True
