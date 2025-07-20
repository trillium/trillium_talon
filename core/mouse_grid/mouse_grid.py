# TODO
# - Add north east south west for easier clicking on edges
# - Add applying grid to current mouse position
# - Add Click history
# - Add indication that the mapping is outside the screen in zoom-in mode

# courtesy of https://github.com/timo/
# see https://github.com/timo/talon_scripts
import math
from typing import Union

from talon import Context, Module, actions, canvas, cron, ctrl, screen, settings, ui
from talon.skia import Paint, Rect
from talon.types.point import Point2d

mod = Module()
mod.setting(
    "grid_narrow_expansion",
    type=int,
    default=0,
    desc="""After narrowing, grow the new region by this many pixels in every direction, to make things immediately on edges easier to hit, and when the grid is at its smallest, it allows you to still nudge it around""",
)
mod.setting(
    "grids_put_one_bottom_left",
    type=bool,
    default=False,
    desc="""Allows you to switch mouse grid and friends between a computer numpad and a phone numpad (the number one goes on the bottom left or the top left)""",
)

mod.tag("mouse_grid_showing", desc="Tag indicates whether the mouse grid is showing")
mod.tag(
    "mouse_grid_enabled",
    desc="Deprecated: do not use. Activates legacy m grid command",
)
ctx = Context()


class MouseSnapNine:
    def __init__(self):
        self.screen = None
        self.rect = None
        self.history = []
        self.img = None
        self.mcanvas = None
        self.active = False
        self.count = 0
        self.was_zoom_mouse_active = False
        self.was_control_mouse_active = False
        self.was_control1_mouse_active = False
        self.grid_stroke = 1

        self.rows = 5
        self.cols = 5
        self.chars = "abcdefghijklmnopqrstuvwxyz"
        self.crosses = False
        self.max_zoom = 3
        self.chars_map = {key: val for val, key in enumerate(self.chars, start=1)}

    def setup(self, *, rect: Rect = None, screen_num: int = None):
        screens = ui.screens()
        # each if block here might set the rect to None to indicate failure
        if rect is not None:
            try:
                screen = ui.screen_containing(*rect.center)
            except Exception:
                rect = None
        if rect is None and screen_num is not None:
            screen = screens[screen_num % len(screens)]
            rect = screen.rect
        if rect is None:
            screen = screens[0]
            rect = screen.rect
        self.rect = rect.copy()
        self.screen = screen
        self.count = 0
        self.img = None
        if self.mcanvas is not None:
            self.mcanvas.close()
        self.mcanvas = canvas.Canvas.from_screen(screen)
        if self.active:
            self.mcanvas.register("draw", self.draw)
            self.mcanvas.freeze()

    def show(self):
        if self.active:
            return
        # noinspection PyUnresolvedReferences
        if actions.tracking.control_zoom_enabled():
            self.was_zoom_mouse_active = True
            actions.tracking.control_zoom_toggle(False)
        if actions.tracking.control_enabled():
            self.was_control_mouse_active = True
            actions.tracking.control_toggle(False)
        if actions.tracking.control1_enabled():
            self.was_control1_mouse_active = True
            actions.tracking.control1_toggle(False)
        self.mcanvas.register("draw", self.draw)
        self.mcanvas.freeze()
        self.active = True
        return

    def close(self):
        if not self.active:
            return
        self.mcanvas.unregister("draw", self.draw)
        self.mcanvas.close()
        self.mcanvas = None
        self.img = None

        self.active = False

        if self.was_control_mouse_active and not actions.tracking.control_enabled():
            actions.tracking.control_toggle(True)
        if self.was_control1_mouse_active and not actions.tracking.control1_enabled():
            actions.tracking.control1_toggle(True)
        if self.was_zoom_mouse_active and not actions.tracking.control_zoom_enabled():
            actions.tracking.control_zoom_toggle(True)

        self.was_zoom_mouse_active = False
        self.was_control_mouse_active = False
        self.was_control1_mouse_active = False

    def draw(self, canvas):
        paint = canvas.paint

        def draw_grid(offset_x, offset_y, width, height):
            for line_vert in range(1, self.rows):
                canvas.draw_line(
                    offset_x + line_vert * width // self.rows,
                    offset_y,
                    offset_x + line_vert * width // self.rows,
                    offset_y + height,
                )

            for line_horz in range(1, self.cols):
                canvas.draw_line(
                    offset_x,
                    offset_y + line_horz * height // self.cols,
                    offset_x + width,
                    offset_y + line_horz * height // self.cols,
                )

        def draw_crosses(offset_x, offset_y, width, height):
            for row in range(0, 2):
                for col in range(0, 2):
                    cx = offset_x + width / 6 + (col + 0.5) * width / self.rows
                    cy = offset_y + height / 6 + (row + 0.5) * height / self.cols

                    canvas.draw_line(cx - 10, cy, cx + 10, cy)
                    canvas.draw_line(cx, cy - 10, cx, cy + 10)

        def draw_text(offset_x, offset_y, width, height):
            canvas.paint.text_align = canvas.paint.TextAlign.CENTER
            i = 0
            for row in range(self.rows):
                for col in range(self.cols):
                    text_string = f"{self.chars[i].upper()}"
                    text_rect = canvas.paint.measure_text(text_string)[1]
                    background_rect = text_rect.copy()
                    background_rect.center = Point2d(
                        offset_x + width / (self.rows * 2) + col * width / self.rows,
                        offset_y + height / (self.cols * 2) + row * height / self.cols,
                    )
                    background_rect = background_rect.inset(-4)
                    paint.color = "9999995f"
                    paint.style = Paint.Style.FILL
                    canvas.draw_rect(background_rect)
                    paint.color = "00ff00ff"
                    canvas.draw_text(
                        text_string,
                        offset_x + width / (self.rows * 2) + col * width / self.rows,
                        offset_y
                        + height / (self.cols * 2)
                        + row * height / self.cols
                        + text_rect.height / 2,
                    )
                    i = i + 1

        if self.count < 2:
            paint.color = "00ff007f"
            for which in range(1, 10):
                gap = 35 - self.count * 10
                if not self.active:
                    gap = 45
                # draw_crosses(*self.calc_narrow([which], self.rect))
                # todo deal with this later

        paint.stroke_width = self.grid_stroke
        if self.active:
            paint.color = "ff0000ff"
        else:
            paint.color = "000000ff"
        if self.count >= 2:
            aspect = self.rect.width / self.rect.height
            if aspect >= 1:
                w = self.screen.width / self.cols
                h = w / aspect
            else:
                h = self.screen.height / self.rows
                w = h * aspect
            x = self.screen.x + (self.screen.width - w) / 2
            y = self.screen.y + (self.screen.height - h) / 2
            self.draw_zoom(canvas, x, y, w, h)
            draw_grid(x, y, w, h)
            draw_text(x, y, w, h)
        else:
            draw_grid(self.rect.x, self.rect.y, self.rect.width, self.rect.height)

            paint.textsize += 12 - self.count * 3
            draw_text(self.rect.x, self.rect.y, self.rect.width, self.rect.height)

    def calc_narrow(self, boxes, rect):
        rect = rect.copy()
        # bdr = narrow_expansion.get()
        bdr = settings.get("user.grid_narrow_expansion")

        x_list = []
        y_list = []

        for coord in boxes:
            row = int(coord - 1) // self.rows
            col = int(coord - 1) % self.cols
            x = int(col * rect.width // self.cols) - bdr
            y = int(row * rect.height // self.rows) - bdr
            x_list.append(x)
            y_list.append(y)

        rect.x += sum(x_list) // len(x_list)
        rect.y += sum(y_list) // len(y_list)

        rect.width = (rect.width // self.cols) + bdr * 2
        rect.height = (rect.height // self.rows) + bdr * 2

        return rect

    def narrow(self, boxes, move=True):
        self.save_state()
        rect = self.calc_narrow(boxes, self.rect)
        # check count so we don't bother zooming in _too_ far
        if self.count < self.max_zoom:
            self.rect = rect.copy()
            self.count += 1
        if move:
            ctrl.mouse_move(*rect.center)
        if self.count >= 2:
            self.update_screenshot()
        else:
            self.mcanvas.freeze()

    def update_screenshot(self):
        def finish_capture():
            self.img = screen.capture_rect(self.rect)
            self.mcanvas.freeze()

        self.mcanvas.hide()
        cron.after("16ms", finish_capture)

    def draw_zoom(self, canvas, x, y, w, h):
        if self.img:
            src = Rect(0, 0, self.img.width, self.img.height)
            dst = Rect(x, y, w, h)
            canvas.draw_image_rect(self.img, src, dst)

    def narrow_to_pos(self, x, y):
        col_size = int(self.width // self.cols)
        row_size = int(self.height // self.rows)
        col = math.floor((x - self.rect.x) / col_size)
        row = math.floor((y - self.rect.x) / row_size)
        self.narrow(1 + col + 3 * row, move=False)

    def save_state(self):
        self.history.append((self.count, self.rect.copy()))

    def go_back(self):
        # FIXME: need window and screen tracking
        self.count, self.rect = self.history.pop()
        self.mcanvas.freeze()


mg = MouseSnapNine()


@mod.action_class
class GridActions:
    def grid_activate():
        """Show mouse grid"""
        if not mg.mcanvas:
            mg.setup()
        mg.show()
        ctx.tags = ["user.mouse_grid_showing"]

    def grid_place_window():
        """Places the grid on the currently active window"""
        mg.setup(rect=ui.active_window().rect)

    def grid_reset():
        """Resets the grid to fill the whole screen again"""
        if mg.active:
            mg.setup()

    def grid_select_screen(screen: int):
        """Brings up mouse grid"""
        mg.setup(screen_num=screen - 1)
        mg.show()

    def grid_narrow_list(digit_list: list[str]):
        """Choose fields multiple times in a row"""
        out = []
        for d in digit_list:
            out.append(mg.chars_map[d])
        mg.narrow(out)

    def grid_narrow(digit: Union[int, str]):
        """Choose a field of the grid and narrow the selection down"""
        mg.narrow([mg.chars_map[digit]])

    def grid_narrow_letter(letter: str):
        """Choose a field of the grid and narrow the selection down"""
        mg.narrow([mg.chars_map[letter]])

    def grid_go_back():
        """Sets the grid state back to what it was before the last command"""
        mg.go_back()

    def grid_close():
        """Close the active grid"""
        ctx.tags = []
        mg.close()

    def grid_is_active():
        """check if grid is already active"""
        return mg.active
