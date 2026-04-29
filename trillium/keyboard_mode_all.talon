mode: all
-

# key(cmd-ctrl-alt-shift-v):
#     text = clip.text()
#     insert(text)

key(cmd-ctrl-alt-shift-`):
    user.speech_mode_rotate()

key(cmd-ctrl-alt-shift-m):
    user.hotkey_onboard_mic_speech_rotate()

key(cmd-ctrl-alt-shift-d):
    menu.open_debug_window()

key(cmd-ctrl-alt-shift-h):
    user.toggle_phrase_history()

key(cmd-ctrl-alt-shift-p):
    mimic('talon open rebel')

key(cmd-ctrl-alt-shift-l):
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    print("")
    menu.open_log()

# key(cmd-ctrl-alt-shift-tab):
#     sleep(50ms)
#     print("tab")
#     user.switcher_focus_last()
