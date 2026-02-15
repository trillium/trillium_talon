mode: sleep
-

key(cmd-ctrl-alt-shift-`):
    #capslock -> #super

    mode.disable("sleep")
    mode.disable("dictation")
    mode.enable("command")
    user.mic_keyboard_toggle_action()
    speech.enable()

key(cmd-ctrl-alt-shift-m):
    user.mic_onboard()
    mode.disable("sleep")
    mode.disable("dictation")
    mode.enable("command")
    user.mic_keyboard_toggle_action()
    speech.enable()
