from talon import actions, clip, Context, Module
import time

mod = Module()
ctx = Context()

state = {}
state["last_press_time"] = 0
state["count"] = 1

# @ctx.action_class("hooks")
# class HooksActions:
#     def short_repeat():
#         """Utility function to change actions based on repeated pressing of a key/noise"""
#         actions.user.hud_add_log("event", "short_repeat")

@mod.action_class
class Actions:
    def short_repeat():
        """Utility function to change actions based on repeated pressing of a key/noise"""
        name = "last_press_time"
        now = time.perf_counter()
        prev = state["last_press_time"]
        state["last_press_time"] = now
        # actions.user.hud_add_log("event", f"short_repeat" + " " + str(t0))

        timeout = .5

        # actions.user.hud_add_log("event", f"short_repeat" + " " + str(state["count"]) + f" {str((now - prev) > timeout)}")

        if (now - prev) < timeout:
            state["count"] = state["count"] + 1
            actions.user.hud_add_log("success", str(state["count"]))
        else:
            state["count"] = 1
            # phrase = "2: toggle, 3: mic_main, 4: mic_none"
            # # actions.user.hud_add_log("warning", phrase)

        #Actions
        if state["count"] == 2:
            # actions.speech.toggle()
            # actions.user.hud_add_log("event", f"toggle sleep" + " " + str(state["count"]))
            None

        if state["count"] == 3:
            actions.speech.enable()
            actions.user.mic_main()

        if state["count"] == 4:
            actions.speech.enable()
            actions.user.mic_onboard()

        if state["count"] == 5:
            actions.user.mic_none()
            actions.speech.disable()
            