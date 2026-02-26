knife:
    insert(" -")

blade:
    insert(" --")

blade {user.blade_phrases}:
    insert(" --{blade_phrases}")

push <user.text>:
    insert(" ")
    sleep(50ms)
    insert(text)
