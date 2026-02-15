import os
import shlex
import subprocess
import time
from pathlib import Path

import talon
from talon import Context, Module, actions, app, fs, imgui, ui

mod = Module()


@mod.action_class
class Actions:
    def press_key_after_switch(name: str, key_name: str, sleep_seconds: str = 0.35 ):
        """Presses a key after focusing an app. Waits N seconds to press if app is NOT active AND full screen"""
        app = actions.user.get_running_app(name)

        # If app is active window, press key immediately, done
        if app == ui.active_app():
            actions.key(key_name)
        # If app is not the active window 
        else:
            # focus that window
            actions.user.switcher_focus_app(app)
        
            app = ui.active_window()

            # check if app is full screen

            if app.fullscreen:
                # if it is, delay slightly for transition animation
                time.sleep(sleep_seconds)
            
            # press key, done
            actions.key(key_name)

    def slide_next():
        """Utility for changing slides in presentations"""
        app_name = "beta"
        key_press = "down"
        actions.user.press_key_after_switch(app_name, key_press)

    def slide_previous():
        """Utility for changing slides in presentations"""
        app_name = "beta"
        key_press = "up"
        actions.user.press_key_after_switch(app_name, key_press)