(lasty | windy): user.switcher_focus_last_window()

tag: user.window_browsing
-
^next$: user.window_browse_next()
^(previous | prevy)$: user.window_browse_previous()
^(stop | done | cancel)$: user.window_browse_stop()
