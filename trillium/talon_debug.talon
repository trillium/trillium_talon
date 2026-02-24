mode: command
-

key(super-ctrl-alt-shift-l):
    mimic('talon open log')

^(custom debug view | talon debug view | frosty socks)$:
    mimic('talon open log')
    sleep(450ms)
    mimic('snap top left third')
    sleep(250ms)
    sleep(250ms)
    mimic('talon open rebel')
    sleep(50ms)
    mimic('dotted events tail')
    sleep(50ms)
    mimic('snap bottom left third')
    sleep(50ms)
    mimic('paren reparen')
    sleep(50ms)
    mimic('lap')

^lumberjack$:
    mimic('talon open rebel')
    sleep(50ms)
    mimic('dotted events tail')
    sleep(50ms)
    mimic('snap bottom left third')
    sleep(50ms)
    mimic('paren reparen')
    sleep(50ms)
    mimic('lap')

^sensation$:
    mimic('talon open log')
    sleep(450ms)
    mimic('snap top left third')
    sleep(250ms)
