"""System monitor bar graph — CPU per-core bars + memory pressure line."""

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

BAR_W = 3       # width of each CPU bar in pixels
BAR_GAP = 1     # gap between bars
PADDING = 4     # padding around the graph area

# Cache last-known core count so width never drops to 0
_last_num_cores = 10


def measure_graph_width(num_cores: int) -> int:
    """Return a stable pixel width for the graph area.

    Caches the last positive core count so that frames where
    cpu_per_core is empty still reserve the correct width.
    """
    global _last_num_cores
    if num_cores > 0:
        _last_num_cores = num_cores
    return _last_num_cores * (BAR_W + BAR_GAP) + PADDING


def draw_graph(
    c: SkiaCanvas,
    x: float,
    top: float,
    bottom: float,
    cpu_per_core: list,
    mem_percent: float,
    mem_pressure: int,
) -> None:
    """Draw CPU bars and memory line into the given region.

    When *cpu_per_core* is empty (e.g. first frame), draws dim 1 px
    placeholder bars so the area is never blank.
    """
    graph_h = bottom - top

    if cpu_per_core:
        cursor = x
        for usage in cpu_per_core:
            pct = max(0.0, min(100.0, usage)) / 100.0
            bar_h = pct * graph_h
            bar_top = bottom - bar_h

            # Green at low, yellow at mid, red at high
            if pct < 0.5:
                r = int(pct * 2 * 255)
                g = 200
            else:
                r = 255
                g = int((1 - (pct - 0.5) * 2) * 200)
            b = 0

            c.paint.color = f"{r:02x}{g:02x}{b:02x}cc"
            c.paint.style = c.paint.Style.FILL
            c.draw_rect(Rect(cursor, bar_top, BAR_W, bar_h))
            cursor += BAR_W + BAR_GAP
    else:
        # Placeholder bars — dim grey, 1 px tall at the bottom
        cursor = x
        for _ in range(_last_num_cores):
            c.paint.color = "ffffff22"
            c.paint.style = c.paint.Style.FILL
            c.draw_rect(Rect(cursor, bottom - 1, BAR_W, 1))
            cursor += BAR_W + BAR_GAP

    # Memory line — horizontal across the graph area
    mem_pct = max(0, min(100, mem_percent)) / 100.0
    mem_y = bottom - (mem_pct * graph_h)

    if mem_pressure >= 4:
        mem_color = "ff3333ee"   # red = critical
    elif mem_pressure >= 2:
        mem_color = "ffaa33ee"   # orange = warn
    else:
        mem_color = "33ccffee"   # cyan = normal

    c.paint.color = mem_color
    c.paint.style = c.paint.Style.STROKE
    c.paint.stroke_width = 1.5
    line_right = x + _last_num_cores * (BAR_W + BAR_GAP)
    c.draw_line(x, mem_y, line_right, mem_y)
