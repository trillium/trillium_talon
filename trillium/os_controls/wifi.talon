os: mac
-
^sudo wifi off$: user.system_command('networksetup -setairportpower "Wi-Fi" off')
^sudo wifi on$: user.system_command('networksetup -setairportpower "Wi-Fi" on')
^sudo wifi refresh$:
    user.system_command('networksetup -setairportpower "Wi-Fi" off')
    sleep(700ms)
    user.system_command('networksetup -setairportpower "Wi-Fi" on')
