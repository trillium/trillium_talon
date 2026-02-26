mode: command
-
key(cmd-ctrl-alt-shift-`):
    #capslock -> #supercommand
    #
    sleep(100ms)
    speech.disable()

key(cmd-ctrl-alt-shift-m):
    #capslock -> #super
    user.mic_onboard()
