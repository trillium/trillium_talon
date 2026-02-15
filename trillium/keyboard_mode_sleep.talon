mode: sleep
-

key(super-ctrl-alt-shift-`):
    #capslock -> #super

    mode.disable("sleep")
    mode.disable("dictation")
    mode.enable("command")
    user.mic_keyboard_toggle_action()
    speech.enable()

key(super-ctrl-alt-shift-m):
    user.mic_onboard()
    mode.disable("sleep")
    mode.disable("dictation")
    mode.enable("command")
    user.mic_keyboard_toggle_action()
    speech.enable()
