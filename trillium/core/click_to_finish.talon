mode: command
mode: dictation
-
^pondering <user.text>$:
    user.pondering_enable()
    user.dictation_insert(user.text)
^pondering$:
    user.pondering_enable()
