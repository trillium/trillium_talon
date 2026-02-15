mode: dictation
-
key(super-ctrl-alt-shift-`):
    #capslock -> #supercommand
    #
    sleep(100ms)
    speech.disable()
    print("disabled from mode: dictation")

key(super-ctrl-alt-shift-m):
    #capslock -> #super
    user.mic_onboard()
