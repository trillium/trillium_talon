os: linux
-
# Linux brightness controls using brightnessctl to avoid Samsung stuck-key bug.
# On Samsung 940X5M, F1/F2 never send key-up events, causing Talon's
# key(f1:repeat) to loop forever injecting brightness keys via XTEST.
# Using brightnessctl bypasses the X11 input stack entirely.

brightness up | up brightness:
    user.system_command("brightnessctl set +5%")

brightness down | down brightness:
    user.system_command("brightnessctl set 5%-")

increase [screen] brightness:
    user.system_command("brightnessctl set +5%")

decreased [screen] brightness:
    user.system_command("brightnessctl set 5%-")

[increase] [screen] brightness (max|maximum):
    user.system_command("brightnessctl set 100%")

[decrease] [screen] brightness (min|minimum):
    user.system_command("brightnessctl set 1%")

# F1/F2: single brightness step on key-up only. No repeat handler.
# This prevents the infinite loop when Samsung hardware never sends key-up.
key(f1:down): skip()
key(f2:down): skip()
key(f1:up):
    user.system_command("brightnessctl set 5%-")
key(f2:up):
    user.system_command("brightnessctl set +5%")

# Media keys - single fire, no repeat
key(f7): key(rewind)
key(f8): key(play)
key(f9): key(fast_forward)
key(f10): key(mute)

# Volume: same pattern - key-up only, no repeat
key(f11:down): skip()
key(f12:down): skip()
key(f11:up):
    key(voldown)
key(f12:up):
    key(volup)
