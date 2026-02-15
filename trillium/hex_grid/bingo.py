from typing import Any

from talon import Module, Context, app, cron, registry, scope, skia, ui, actions, ctrl
from talon.canvas import Canvas, MouseEvent
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.skia.imagefilter import ImageFilter
from talon.ui import Rect
from talon.types.point import Point2d
import time

mod = Module()
ctx = Context()

mod.list("list_name", "description of the list")
mod.list("bingo_color", "accepted colors")

points = {
    "name": (500, 500),
    "word": "B I N G O !",
    "a": (0,0),
    "pink air": (900, 900),
    "air bat": (900, 0),
}

colors = {
    "pink": "pink",
    "red": "red",
    "blue": "blue",
}

ctx.lists["user.bingo_color"] = colors.keys()

ctx.lists["user.list_name"] = points.keys()

@mod.action_class
class Actions:
    def named_mouse_position(name: str, color: str = ""):
        '''moves the mouse to preset positions'''
        actions.user.hud_add_log("success", "enter func()" + " color: " + color)
        x, y = points[name]
        actions.mouse_move(x, y)
    
    def numbered_thing(val: int):
        '''prints int as str'''
        actions.user.hud_add_log("success", str(val))

