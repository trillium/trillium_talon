tag: user.links_active
-
^link open <user.overlay_select>$: user.links_open(overlay_select)
^link copy <user.overlay_select>$: user.links_copy(overlay_select)
^next$: user.links_next()
^previous$: user.links_previous()
^refresh$: user.links_refresh()
^links close$: user.links_hide()
