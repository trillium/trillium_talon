mode: command
mode: dictation
not speech.engine: dragon
hostname: laptop
-

^sleep laptop [<phrase>]$: speech.disable()

^only laptop [<phrase>]$:
    speech.disable()
    sleep(200ms)
    speech.enable()

^only mini [<phrase>]$: speech.disable()
