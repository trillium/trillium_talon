from talon import Context, Module, actions, app, fs, imgui, ui

import time

from ..config import SAFE_APPS

mod = Module()

def run_app_switch(app):
    actions.user.obs_get_blurry()
    if app == ui.active_app(): 
        actions.app.window_next()
    # Focus new app
    else:
        actions.user.switcher_focus_app(app)

def get_app_rect(app):
    windows = app.windows()

    rect = None

    # If active app get next window
    if app == ui.active_app(): 
        rect = windows[1].rect
    # Otherwise return rect of first window in app
    else:
        rect = windows[0].rect
    
    print("[get_app_rect]", rect)
    return rect

@mod.action_class
class Actions:
    def switcher_focus(name: str):
        """Focus a new application by name"""
        print("[switcher_focus]", name)
        # SWITCHING TO APP
        # NO SCENE CHANGE, ONLY MASK CHANGES
        # This means that all unsafe apps will have a mask build step before switching

        # find out if app is safe
        safe = name in SAFE_APPS
        

        # color is "white" or "black"
        color = actions.user.get_mask_color(name)

        app = actions.user.get_running_app(name)

        # blur screen
        actions.user.obs_get_blurry()
        # if it is safe

        rect = get_app_rect(app)
        print("[switcher_focus]", rect)

        t0 = time.monotonic()

        if safe:
            run_app_switch(app)
            # switch to app
            # build blur mask
            # need app.rect

            # draws black box of rect boundaries
            # need to pass
                # color
                # rect
            # DISABLED: Blocking ffmpeg call causing SIGABRT
            # actions.user.draw_rect_over_image_in_place(color, rect)
        else:
            # build blur mask first
            # DISABLED: Blocking ffmpeg call causing SIGABRT
            # actions.user.draw_rect_over_image_in_place(color, rect)
            # then bring app to forefront
            time.sleep(0.25)
            run_app_switch(app)


        
        t1 = time.monotonic()
        t1_t0 = t1 - t0
        print("[switcher_focus]", "t1 - t0", t1_t0)

        actions.user.obs_partial_blurry_mask()
        t2 = time.monotonic()
        t2_t1 = t2 - t1
        print("[switcher_focus]", "t2 - 10", t2_t1)

print("Reloaded [trillium_obs/window_management/app_switcher.py]")