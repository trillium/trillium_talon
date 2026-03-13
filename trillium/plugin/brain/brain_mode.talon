tag: user.brain_mode
mode: all
-
# Continue dictating - appends to current brain entry
^<user.text>$:
    user.brain_append(text)

# End brain capture mode
^brain end$:
    user.brain_end()
