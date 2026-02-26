from talon import Module, imgui, cron, actions, app, Context, Module
import math
import threading
import time
from typing import Optional


# [
#     'None',
#     'System Default',
#     'MacBook Pro Microphone',
#     'trillium’s iPhone Microphone',
#     'Wireless GO II RX',
#     'USB Audio CODEC '
# ]

mod = Module()
ctx = Context()

# lock = threading.Lock()
start_time = None
current_duration = None
notify_type = None
pause_time = None
finished = False
cancel_job = None
microphone_name = ""

# TODO: Better placement  
@imgui.open(y=68, x=5)
def gui(gui: imgui.GUI):
    global microphone_name
    gui.text(f"Microphone: {microphone_name}")

def announce_microphone(mic: str):
    global microphone_name
    # gui.show()
    microphone_name = mic 
    actions.sound.set_microphone(microphone_name) 
    # cron.after("3s", gui.hide)

@mod.action_class
class Actions:
    def mic_main():
        """Switch to the main microphone"""
        global microphone_name
        mics = actions.sound.microphones()
        print(mics)
        if "RØDE Connect Stream" in mics:
            announce_microphone("RØDE Connect Stream") 
        elif "Wireless GO II RX" in mics:
            announce_microphone("Wireless GO II RX") 
        elif "USB Audio CODEC " in mics:
            announce_microphone("USB Audio CODEC ") 
        else:
            app.notify("Error")
        actions.user.sound_microphone_enable_event()

    def mic_onboard():
        """Switch to MacBook Pro Microphone"""
        active_mic = actions.sound.active_microphone()
        if actions.speech.enabled() and active_mic == "MacBook Pro Microphone":
            actions.speech.disable()
        else:
            announce_microphone("MacBook Pro Microphone")
            actions.user.sound_microphone_enable_event()
            if actions.speech.enabled() is False:
                actions.speech.enable()
    
    def mic_rotate_core_microphones():
        """Switch between core microphones: Onboard, Rode System"""
        active_mic = actions.sound.active_microphone()
        print("Switch between core microphones: Onboard, Rode System")
        if active_mic == "RØDE Connect Stream":
            actions.user.mic_onboard()
        elif active_mic == "MacBook Pro Microphone":
            actions.user.mic_main()
        else:
            actions.user.mic_onboard()
        actions.user.sound_microphone_enable_event()

    def mic_none():
        """Switch to no microphone"""
        announce_microphone("None")
        actions.user.sound_microphone_enable_event()

    def hide_gui():
        """Switch to no microphone"""
        gui.hide()
    
    def mic_keyboard_toggle_action():
        """Switch to no microphone"""
        active_mic = actions.sound.active_microphone()
        announce_microphone("None")
        announce_microphone(active_mic)

    # skipped because they have no matching declaration
