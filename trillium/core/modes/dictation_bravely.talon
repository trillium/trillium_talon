# Dictation ender: dictate text and press Enter
# e.g. "hello world bravely" → types "hello world" then presses Enter
# e.g. "bravely" alone → just presses Enter
# Edit dictation_ender.talon-list to change/add ender words
mode: dictation
-
<user.raw_prose> {user.dictation_ender}$:
    user.dictation_insert(raw_prose)
    sleep(50ms)
    key(enter)
{user.dictation_ender}$:
    key(enter)
