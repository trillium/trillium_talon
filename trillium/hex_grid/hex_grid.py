from typing import Any

from talon import Module, Context, app, cron, registry, scope, skia, ui, actions, ctrl
from talon.canvas import Canvas, MouseEvent
from talon.screen import Screen
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.skia.imagefilter import ImageFilter
from talon.ui import Rect
from talon.types.point import Point2d
import time

canvas: Canvas = None
current_mode = ""
mod = Module()
mod.list(
    "hex_grid_coord_name",
    "Coordinate name in the _new_vals dict",
)

ctx = Context()

hex_points = {
    "beep": "boop"
}

cron_jobs = {}

cron_num = 0
CRON_ACTIVE = True

last_mouse_pos = None

BACKGROUND_COLOR = "00000000"  # Snow
BLACK = "000000"  # Black
GREEN = "ff1493"  # Green
PINK = "ff1493"  # Pink
BLUE = "0072b1"  # Blue
RED = "ff1493"  # Red
BORDER_COLOR =   "000000"  # Black
WIDTH = 500
HEIGHT = 500

CIRCLE_RADIUS = 3
OFFSET = 24

BUTTON_OFFSET = CIRCLE_RADIUS / 2
BUTTON_RADIUS = BUTTON_OFFSET / 2
ROW_OFFSET = CIRCLE_RADIUS * 1.25
BUTTON_FLAT_WIDTH = BUTTON_RADIUS * 3
BUTTON_FLAT_HEIGHT = BUTTON_RADIUS
TRIGGER_HEIGHT = CIRCLE_RADIUS
BUTTON_OFFSETS = [(0, -1), (1, 0), (0, 1), (-1, 0)]

def cron_bump():
    global cron_num
    cron_num += 1
    if CRON_ACTIVE:
        # actions.user.hud_add_log("warning", f"cron_num: {cron_num}")
        cron.after("1500ms", cron_bump)

def cron_on():
    global CRON_ACTIVE
    CRON_ACTIVE = True

def cron_off():
    global CRON_ACTIVE
    CRON_ACTIVE = False

@ctx.action_class("user")
class UserActions:
    def hex_active():
        """hex hexhexhex"""
        actions.user.hud_add_log("warning", "hex-grid-active")

def generate_coordinate_key(letter: str, color: str = "") -> str:
    """Generate a coordinate key"""
    # return f"{letter}{color}"
    return f"{letter}"

def on_draw(c: SkiaCanvas):
    global cron_num
    global hex_points
    # Render background
    c.paint.style = c.paint.Style.FILL
    c.paint.color = BACKGROUND_COLOR
    c.draw_rect(c.rect)

    c.paint.color = BLACK
    y_center = c.rect.center.y


    # Draw a a small circle at the mouse position
    c.paint.style = c.paint.Style.FILL
    c.paint.color = GREEN
    mouse_x, mouse_y = get_mouse_position()
    # c.draw_circle(mouse_x, mouse_y, CIRCLE_RADIUS / 2)
    # draw_dot(c, mouse_x, mouse_y, GREEN)
    # draw_text(c, mouse_x, mouse_y, f"{mouse_x}, {mouse_y}")
    # text = f"{round(mouse_x * 100)}, {round(mouse_y * 100)}"
    # text_rect = c.paint.measure_text(text)[1]
    # c.draw_text(
    #     text,
    #     x - text_rect.x - text_rect.width / 2,
    #     y - CIRCLE_RADIUS - text_rect.height,
    # )

    # Get current mouse position
    # vals = []
    # for row in ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    #     for col in ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    #         vals.append(f"{row}{col}")

    # vals needs to be changed to a dictionary
        # dictionary to have keys as the point names
        # values as the point values
    # 

    ROW_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".lower()
    COL_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".lower()
    # ROW_LETTERS = "0123456789"
    # COL_LETTERS = "0123456789"
    row_chooser = 0
    col_chooser = 0

    # for row in range(0):

    for runs_row, row in enumerate(range(-10,11)):
        # Pick the first letter in the list first
        # Picks "A"
        row_letter = ROW_LETTERS[runs_row]
        row_chooser = row_chooser + 1
        # "A"
        # "B"
        # "C"

        for runs_col, col in enumerate(range(15)):
            color = GREEN
            if row_letter == "i":
                color = PINK
            if row_letter == "I":
                color = PINK
                
            # col_letter = COL_LETTERS[row_chooser + runs_col]
            col_letter = COL_LETTERS[runs_col]

                
            key = f"{row_letter}{col_letter}"
            if row_letter == "I":
                key= col_letter
            if row_letter == "i":
                key= col_letter
            hex_points[key] = {
                "coords": (mouse_x - ((col+1) * OFFSET), mouse_y + (row * OFFSET)),
                "group": 0 if color == GREEN else 1
            }

            text = None if (cron_num + hex_points[key]["group"]) % 2 == 0 else key
            # if cron_num % 2 == 0:
            #     if row_letter != "I":
            #         text = None  if row_letter == col_letter else key

            # render(c, _new_vals[key]["coords"], None, GREEN)
            render(c, hex_points[key]["coords"], text, color)
            

            col_letter = COL_LETTERS[runs_col ]
            if row_letter == "I":
                color = BLUE
            if row_letter == "i":
                color = BLUE

            key = f"{col_letter}{row_letter}"
            if row_letter == "I":
                key= col_letter
            if row_letter == "i":
                key= col_letter

            hex_points[key] = {
                "coords": (mouse_x + ((col+1) * OFFSET), mouse_y + (row * OFFSET)),
                "group": 0 if color == GREEN else 1
            }

            # text = None
            # text = key
            text = None if (cron_num +hex_points[key]["group"]) % 2 == 0 else key

            # render(c, _new_vals[key]["coords"], None, GREEN)
            render(c, hex_points[key]["coords"], text, color)
        

            


            # "AB"   &   "BA"
            # "AC"   &   "CA"
            # "AD"   &   "DA"



            # Render dots from left to right
            # x, y = mouse_x + (i * OFFSET), mouse_y + (j * OFFSET)
            # render(c, (x,y), vals.pop(0), GREEN)
            
            # x, y = mouse_x - (i * OFFSET), mouse_y + (j * OFFSET)
            # render(c, (x,y), vals.pop(0), GREEN)
            

            # Render dots to the right of cursor
            # draw_dot(c, mouse_x + (i * OFFSET), mouse_y + (j * OFFSET), GREEN)

            # draw_dot(c, mouse_x - (i * OFFSET), mouse_y - (j * OFFSET), GREEN)
            # # Render dots to the right of cursor
            # draw_dot(c, mouse_x + (i * OFFSET), mouse_y - (j * OFFSET), GREEN)

            # # render dots above cursor
            # draw_dot(c, mouse_x, mouse_y + (i * OFFSET), GREEN)
            # # render dots below cursor
            # draw_dot(c, mouse_x, mouse_y - (i * OFFSET), GREEN)
        # col_letter = COL_LETTERS[runs_col ]

        key = f"{row_letter}"
        hex_points[key] = {
            "coords": (mouse_x + (0 * OFFSET), mouse_y + (row * OFFSET)),
            "group": 1
        }

        # text = None
        text = None if (cron_num +hex_points[key]["group"]) % 2 == 0 else key

        # render(c, _new_vals[key]["coords"], None, GREEN)
        render(c, hex_points[key]["coords"], text, PINK)
        
        

# def get_mouse_position():
#     mouse_x, mouse_y = ctrl.mouse_pos()
#     return mouse_x, mouse_y


def get_mouse_position():
    '''returns (x, y) mouse position'''
    mouse_x, mouse_y = ctrl.mouse_pos()
    return mouse_x, mouse_y

def draw_dot(
    c: SkiaCanvas,
    x: float,
    y: float,
    color: str = GREEN,
    stroke: bool = True,
):  
    c.paint.style = c.paint.Style.FILL
    c.paint.color = color
    c.draw_circle(x, y, CIRCLE_RADIUS / 2)
    if stroke:
        c.paint.style = c.paint.Style.STROKE
        c.paint.color = BLACK
        c.draw_circle(x, y, CIRCLE_RADIUS / 2)

def draw_text(
    c: SkiaCanvas,
    x: float,
    y: float,
    text: str,
    color: str = GREEN,
    stroke: bool = True,
):
    c.paint.style = c.paint.Style.FILL
    c.paint.color = color
    text_rect = c.paint.measure_text(text)[1]
    c.draw_text(
        text,
        x - text_rect.x - text_rect.width / 2,
        y + CIRCLE_RADIUS,
    )

def render(
        c: SkiaCanvas,
        coords: (float, float),
        text: str=None,
        color: str=GREEN,
        stroke: bool=True,
):
    x, y = coords
    c.paint.style = c.paint.Style.FILL
    c.paint.color = color
    # if stroke:
    #     c.paint.style = c.paint.Style.STROKE
    #     c.paint.color = BLACK
    #     c.draw_circle(x, y, CIRCLE_RADIUS / 2)
    # if text:
    if text:
        c.paint.style = c.paint.Style.FILL
        c.paint.color = color
        text_rect = c.paint.measure_text(text)[1]
        c.draw_text(
            text,
            x - text_rect.x - text_rect.width / 2,
            y + CIRCLE_RADIUS,
        )
    else:
        c.draw_circle(x, y, CIRCLE_RADIUS / 2)


# @mod.capture(rule="<user.letter> | <user.letter> <user.letter>")
# def rango_hint(m) -> str:
#     return "".join(m.letter_list)


# @mod.capture(rule="<user.letter>")
# def rango_hint_double(m) -> str:
#     return m.letter + m.letter

@mod.capture(rule="<user.letter> | <user.letter> <user.letter>")
def hex_target(m) -> str:
    "Multiple letter keys"
    # val = "".join(m.letter_list)
    # actions.user.hud_add_log("event", "capture: " + str(val))
    return "".join(m.letter_list)

def on_mouse(e: MouseEvent):
    global last_mouse_pos
    if e.event == "mousedown" and e.button == 0:
        last_mouse_pos = e.gpos
    elif e.event == "mousemove" and last_mouse_pos:
        dx = e.gpos.x - last_mouse_pos.x
        dy = e.gpos.y - last_mouse_pos.y
        last_mouse_pos = e.gpos
        canvas.move(canvas.rect.x + dx, canvas.rect.y + dy)
    elif e.event == "mouseup" and e.button == 0:
        last_mouse_pos = None

def hex_grid_show():
    """Toggle visibility of hex grid"""
    global canvas
    global cron_num
    global cron_num_job
    # actions.user.hud_add_log("success", "hex_grid_show" + " " + str(len(_new_vals)))
    screen: Screen = ui.main_screen()
    x = screen.rect.center.x
    y = screen.rect.center.y
    top_left, top_right, bottom_right, bottom_left = screen.rect
    canvas = Canvas.from_rect(Rect(top_left, top_right, bottom_right, bottom_left))
    # canvas = Canvas.from_rect(Rect(x - WIDTH / 2, y - HEIGHT / 2, WIDTH, HEIGHT))
    canvas.draggable = False
    # canvas.blocks_mouse = True
    canvas.register("draw", on_draw)
    canvas.register("mouse", on_mouse)
    ctx.tags = ["user.hex_grid"]
    cron_bump()
    # cron_num_job = cron.after("1s", lambda: cron_num = True)

def hex_grid_hide():
    """Toggle visibility of gamepad tester gui"""
    global canvas
    global cron_num
    actions.user.hud_add_log("success", "hex_grid_hide" + " " + str(len(hex_points)))
    canvas.unregister("draw", on_draw)
    canvas.unregister("mouse", on_mouse)
    canvas.close()
    canvas = None
    ctx.tags = []      
    cron_off()


@mod.action_class
class Actions:
    def hex_toggle(foo: str = ""):
        """Toggle visibility of the hex grid ui"""
        if foo == "on":
            hex_grid_show()
            return
        elif foo == "off":
            hex_grid_hide()
            return
        elif not canvas:
            hex_grid_show()
        else:
            hex_grid_hide()
        
    def hex_grid():
        """hex_grid"""

    def hex_active():
        """hex_curve_active"""

    # def test_test(m) -> list[str]:
    def test_test(m: str) -> str:
        """Returns a list of letters"""
        global hex_points    
        out = "".join(m)
        try:
            point = hex_points[out]
            # x,y = hex_points['coords'](m)
            # stringy = str(point.keys())
            x,y = point['coords']
            actions.mouse_move(x, y)
            # actions.user.hud_add_log("success", stringy)

            x,y = str(x), str(y)
        except:
            x,y = None, None
            # actions.user.hud_add_log("warning", "except")
        if x and y:
            # actions.user.hud_add_log("success", "test_test: " + out + " " + x + " " + y)
            None
        else:
            # actions.user.hud_add_log("success", "test_test: " + out)
            None

        # return m.rango_hint_list

    def hex_grid_show():
        """Hex grid on"""
        
    def hex_grid_hide():
        """Hex grid off"""
        
        

    def cron_experiment():
        '''Cron experiment'''
        
