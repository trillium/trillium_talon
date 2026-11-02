mode: command
mode: dictation
-
^pondering <user.text>$:
    user.pondering_enable()
    user.dictation_insert(user.text)
^pondering$:
    user.pondering_enable()

# After a click finishes pondering + writes text, the next tongue-click submits
# (default Enter) via repeater's repeat override. Set or reset that key here:
click action <user.keys>$: user.click_submit_key_set(user.keys)
click action default$:     user.click_submit_key_reset()
click fire$:               user.click_submit_now()
