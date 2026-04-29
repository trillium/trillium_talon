"""Example: Testing canvas overlay plugins.

This demonstrates how to test plugins that draw overlays on screen.
Pattern: Use mock Skia Canvas, call draw function, assert on recorded operations.

Applicable to: mouse grids, hex grids, mode indicators, subtitles, any visual overlay
"""

import talon

if hasattr(talon, "test_mode"):
    from talon.canvas import Canvas as TalonCanvas
    from talon.screen import Screen
    from talon.skia import Paint
    from talon.skia.canvas import Canvas as SkiaCanvas

    # --- Simulated production code ---

    def draw_crosshair(canvas, cx, cy, size, color="ff0000ff"):
        """Draw a crosshair at the given position."""
        paint = Paint()
        paint.color = color
        paint.style = Paint.Style.STROKE
        paint.stroke_width = 2

        half = size / 2
        canvas.draw_line(cx - half, cy, cx + half, cy, paint)
        canvas.draw_line(cx, cy - half, cx, cy + half, paint)
        canvas.draw_circle(cx, cy, size / 4, paint)

    def draw_label(canvas, x, y, text, size=20):
        """Draw a text label."""
        paint = Paint()
        paint.color = "ffffffff"
        paint.textsize = size
        canvas.draw_text(text, x, y, paint)

    # --- Tests ---

    def test_crosshair_draws_lines_and_circle():
        """Verify crosshair creates exactly 2 lines and 1 circle."""
        canvas = SkiaCanvas()
        draw_crosshair(canvas, 100, 200, 40)

        assert len(canvas.lines()) == 2
        assert len(canvas.circles()) == 1

    def test_crosshair_position():
        """Verify crosshair is centered at the given coordinates."""
        canvas = SkiaCanvas()
        draw_crosshair(canvas, 500, 300, 100)

        lines = canvas.lines()
        # Horizontal line
        assert lines[0][1] == 450  # x1 = cx - half
        assert lines[0][2] == 300  # y1 = cy
        assert lines[0][3] == 550  # x2 = cx + half
        assert lines[0][4] == 300  # y2 = cy

    def test_crosshair_color():
        """Verify paint color is applied."""
        canvas = SkiaCanvas()
        draw_crosshair(canvas, 0, 0, 40, color="00ff00ff")

        circle = canvas.circles()[0]
        assert circle[4]["color"] == "00ff00ff"

    def test_label_text_content():
        """Verify text content is recorded."""
        canvas = SkiaCanvas()
        draw_label(canvas, 10, 20, "Hello Talon")

        texts = canvas.texts()
        assert len(texts) == 1
        assert texts[0][3] == "Hello Talon"

    def test_talon_canvas_from_screen():
        """Verify Canvas.from_screen creates correct dimensions."""
        screen = Screen(0, 0, 2560, 1440)
        canvas = TalonCanvas.from_screen(screen)

        assert canvas.rect.width == 2560
        assert canvas.rect.height == 1440

    def test_canvas_draw_callback():
        """Verify Canvas.trigger_draw fires registered callbacks."""
        talon_canvas = TalonCanvas()
        skia_canvas = SkiaCanvas()
        draw_calls = []

        def on_draw(c):
            draw_calls.append(c)

        talon_canvas.register("draw", on_draw)
        talon_canvas.trigger_draw(skia_canvas)

        assert len(draw_calls) == 1
        assert draw_calls[0] is skia_canvas
