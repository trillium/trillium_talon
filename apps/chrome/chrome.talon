app: chrome
-
tag(): browser
tag(): user.tabs

profile switch: user.chrome_mod("shift-m")

tab search: user.chrome_mod("shift-a")

tab search <user.text>$:
    # Fails to clear search box if tab search is already open
    browser.focus_address()
    sleep(200ms)
    user.chrome_mod("shift-a")

    sleep(200ms)
    insert("{text}")

toggle dark [mode]: key(alt-shift-d)
