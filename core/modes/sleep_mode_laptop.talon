mode: sleep
not speech.engine: dragon
hostname: MacBookPro.localdomain
-

^wake up laptop$: speech.enable()
^only laptop [<phrase>]$: speech.enable()
