mode: command
mode: dictation
not speech.engine: dragon
hostname: trillium-mini
-

^sleep mini [<phrase>]$: speech.disable()

^only mini [<phrase>]$:
    speech.disable()
    sleep(200ms)
    speech.enable()

^only laptop [<phrase>]$: speech.disable()
