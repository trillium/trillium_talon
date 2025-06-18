import time

from talon import Context, actions, settings

# ctx = Context()

# # @ctx.action("user.noise_trigger_pop")
# # def on_pop():
# #     print("~~~~REPEATER~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")


ctx = Context()

ctx.matches = r"""
mode: command
"""

time_last_pop = 0


@ctx.action_class("user")
class UserActions:
    def noise_trigger_pop():
        print("Pop to repeat!")
        global time_last_pop
        # if settings.get("user.mouse_enable_pop_wake") == 1:
        delta = time.time() - time_last_pop
        if delta >= 0.1 and delta <= 0.3:
            # actions.speech.enable()
            actions.core.repeat_phrase(1)
        time_last_pop = time.time()
