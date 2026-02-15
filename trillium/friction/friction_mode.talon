tag: user.friction_mode
mode: all
-
# Continue dictating - appends to current friction
^<user.text>$:
    user.friction_append(user.text)

# End friction capture mode
^friction end$:
    user.friction_end()
