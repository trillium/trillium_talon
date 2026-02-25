mode: command
mode: dictation
not speech.engine: dragon
hostname: laptop
-

^sleep laptop [<phrase>]$: speech.disable()
^only mini [<phrase>]$: speech.disable()
^wake up mini$: speech.disable()
