mode: all
not app: Google Chrome Beta
-
ridiculously long focus <user.running_applications>:
    user.switcher_focus(running_applications)

slide next [<phrase>]$:
    user.slide_next()

slide previous [<phrase>]$:
    user.slide_previous()

^[<phrase>] slide next$:
    user.slide_next()

[<phrase>] slide previous$:
    user.slide_previous()
