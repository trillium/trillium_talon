tag: user.activity_active
-
^kill <user.overlay_select>$: user.activity_kill(overlay_select)
^activity close$: user.activity_hide()
^refresh$: user.activity_refresh()
^sort cpu$: user.activity_sort_cpu()
^sort memory$: user.activity_sort_memory()
^sort (combined | hogs)$: user.activity_sort_combined()
