mode: dictation
-
key(cmd-ctrl-alt-shift-`):
    #capslock -> #supercommand
    #
    sleep(100ms)
    speech.disable()
    print("disabled from mode: dictation")

key(cmd-ctrl-alt-shift-m):
    #capslock -> #super
    user.mic_onboard()
