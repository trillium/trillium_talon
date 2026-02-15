mode: command
-
# # use Alvoilar Click to wake talon
# parrot(cluck):
#     user.mouse_wake()
#     # user.history_enable()
#     user.talon_mode()

^(sleep all | dross | drowse | shut her down | shutter down | shudder down) [<phrase>]$:
    user.switcher_hide_running()
    user.history_disable()
    user.homophones_hide()
    user.help_hide()
    user.mouse_sleep()
    speech.disable()
