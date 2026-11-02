tag: user.logs_ignore_active
-
^clear <user.overlay_select>$: user.logs_ignore_remove(overlay_select)
^(ignore | ignore list) close$: user.logs_ignore_close()
