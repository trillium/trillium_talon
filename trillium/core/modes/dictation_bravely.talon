# Dictation ender: dictate text and press Enter
# e.g. "hello world bravely" → types "hello world" then presses Enter
# e.g. "bravely" alone → just presses Enter
# Edit dictation_ender.talon-list to change/add ender words
#
# Command mode too. command_mode(), wake, and pondering exit all turn
# dictation mode off. This Enter is what submits the line to the focused
# pane, so the ender has to keep matching after that.
mode: command
mode: dictation
-
<user.raw_prose> {user.dictation_ender}$:
    user.dictation_insert(raw_prose)
    sleep(50ms)
    key(enter)
{user.dictation_ender}$:
    key(enter)
