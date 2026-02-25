mode: command
mode: dictation
-
# Disabled: TalonScript doesn't support arithmetic in repeat()
# clear left <user.number_small> hundred:
#     key(backspace)
#     repeat(number_small * 100 - 1)

# clear right <user.number_small> hundred:
#     key(delete)
#     repeat(number_small * 100 - 1)

^destroy$:
    user.clear_last_dictation()

^destroy {user.dictation_ender}$:
    user.clear_last_dictation()
    key(enter)

^destroy <user.text> {user.dictation_ender}$:
    user.clear_left_by_text(text)
    key(enter)

^destroy <user.text>$:
    user.clear_left_by_text(text)

^destroy right <user.text>$:
    user.clear_right_by_text(text)

^go left <user.text>$:
    user.go_left_by_text(text)

^go right <user.text>$:
    user.go_right_by_text(text)

