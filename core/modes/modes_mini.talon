mode: command
mode: dictation
not speech.engine: dragon
hostname: trillium-mini
-

^sleep mini [<phrase>]$: speech.disable()
^only laptop [<phrase>]$: speech.disable()
^wake up laptop$: speech.disable()
