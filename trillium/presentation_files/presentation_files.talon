mode: all
app: chrome
-
slide next [<phrase>]$:
    key("down")

slide previous [<phrase>]$:
    key("up")

^[<phrase>] slide next$:
    key("down")

[<phrase>] slide previous$:
    key("up")
