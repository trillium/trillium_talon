os: mac
-
# key(f1):
#     user.hud_add_log("success", "f1")
#     key(f1)

# key(f1:repeat):
#     sleep(100ms)
#     key(brightness_down)

# key(f2:repeat):
#     sleep(100ms)
#     key(brightness_up)
    # key(volup)

brightness up | up brightness:
    key(brightness_up)

brightness down | down brightness:
    key(brightness_down)

increase [screen] brightness:
    key(brightness_up)

decreased [screen] brightness:
    key(brightness_down)

[increase] [screen] brightness (max|maximum):
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)
    key(brightness_up)

key(f1:down): skip()
key(f2:down): skip()
key(f1:repeat):
    sleep(100ms)
    key(brightness_down)
key(f2:repeat):
    sleep(100ms)
    key(brightness_up)

# key(f3): # mission control?
# key(f4): # spotlight?                                                   
# key(f5): # dictation?
# key(f6): # do not disturb?  

key(f7): key(rewind)
key(f8): key(play)
key(f9): key(fast_forward)
key(f10): key(mute)

key(f11:down): skip()
key(f12:down): skip()
key(f12:up):
    user.hud_add_log("success", "f12:up")
key(f11:repeat):
    sleep(100ms)
    key(voldown)
key(f12:repeat):
    sleep(100ms)
    key(volup)