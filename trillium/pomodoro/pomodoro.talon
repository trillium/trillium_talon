# Pass time in seconds
^[start] (timer | pomodoro)$: user.pomodoro_start("W", 25 * 60)
^[start] (timer | pomodoro) <number> [minute | minutes]$: user.pomodoro_start("W", number * 60)
^start (rest | break)$: user.pomodoro_start("B", 5 * 60)
^start (rest | break) <number>$: user.pomodoro_start("B", number * 60)

^(unpause | resume) (timer | pomodoro)$: user.pomodoro_unpause()
^(cancel | stop) (timer | pomodoro)$: user.pomodoro_cancel()

^pomodoro start$:
    user.pomodoro_start("W", 25 * 60)
^pomodoro start <number>$:
    user.pomodoro_start("W", number * 60)
^pomodoro [start] <number> (minute | minutes) [and] <number> [(second | seconds)]$:
    user.pomodoro_start("W", number_1 * 60, number_2)
^pause (timer | pomodoro)$:
    user.pomodoro_pause()
^pomodoro pause$:
    user.pomodoro_pause()
^pomodoro (unpause | resume)$:
    user.pomodoro_pause()
^pomodoro (cancel | stop)$:
    user.pomodoro_cancel()

^pomodoro (rest | break)$: user.pomodoro_start("B", 5 * 60)
^pomodoro (rest | break) <number>$: user.pomodoro_start("B", number * 60)
