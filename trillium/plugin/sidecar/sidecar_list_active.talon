tag: user.sidecar_list_active
-
^<user.overlay_select>$: user.sidecar_pick(overlay_select)
^pane <user.overlay_select>$: user.sidecar_pick(overlay_select)
^pick <user.overlay_select>$: user.sidecar_pick(overlay_select)
^close$: user.sidecar_close()
^help$: user.sidecar_help()
^sidecar close$: user.sidecar_close()
^sidecar help$: user.sidecar_help()
key(escape): user.sidecar_close()
