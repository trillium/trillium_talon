tag: user.sidecar_list_active
-
^pick <user.overlay_select>$: user.sidecar_pick(overlay_select)
^sidecar pane <number_small>$: user.sidecar_pick(number_small - 1)
^sidecar close$: user.sidecar_close()
key(escape): user.sidecar_close()
