tag: user.sidecar_list_active
-
^<user.overlay_select>$: user.sidecar_pick(overlay_select)
^pick <user.overlay_select>$: user.sidecar_pick(overlay_select)
^sidecar pane <user.overlay_select>$: user.sidecar_pick(overlay_select)
^sidecar close$: user.sidecar_close()
key(escape): user.sidecar_close()
