mode: command
mode: dictation
-
clear left <user.number_small> hundred:
    key(backspace)
    repeat(number_small * 100 - 1)

clear right <user.number_small> hundred:
    key(delete)
    repeat(number_small * 100 - 1)

^destroy$:
    user.clear_last_dictation()

^destroy <user.text>$:
    user.clear_left_by_text(text)

^destroy right <user.text>$:
    user.clear_right_by_text(text)

^go left <user.text>$:
    user.go_left_by_text(text)

^go right <user.text>$:
    user.go_right_by_text(text)

^clear left <user.text>$:
    user.clear_left_by_text(text)

^clear right <user.text>$:
    user.clear_right_by_text(text)
