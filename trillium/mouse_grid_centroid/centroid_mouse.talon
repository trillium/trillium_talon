tag: user.use_centroid_mouse_grid
-
touch:
    # close zoom if open
    tracking.zoom_cancel()
    mouse_click(0)
    # close the mouse grid if open
    user.centroid_grid_close()

    # End any open drags
    # Touch automatically ends left drags so this is for right drags specifically
    user.mouse_drag_end()

righty:
    # close zoom if open
    tracking.zoom_cancel()
    mouse_click(1)
    # close the mouse grid if open
    user.centroid_grid_close()


mid click:
    # close zoom if open
    tracking.zoom_cancel()
    mouse_click(2)
    # close the mouse grid
    user.centroid_grid_close()


#see keys.py for modifiers.
#defaults
#command
#control
#option = alt
#shift
#super = windows key

<user.modifiers> touch:
    # close zoom if open
    tracking.zoom_cancel()
    key("{modifiers}:down")
    mouse_click(0)
    key("{modifiers}:up")
    # close the mouse grid
    user.centroid_grid_close()


<user.modifiers> righty:
    # close zoom if open
    tracking.zoom_cancel()
    key("{modifiers}:down")
    mouse_click(1)
    key("{modifiers}:up")
    # close the mouse grid
    user.centroid_grid_close()


(dub click | duke):
    # close zoom if open
    tracking.zoom_cancel()
    mouse_click()
    mouse_click()
    # close the mouse grid
    user.centroid_grid_close()


(trip click | trip lick):
    # close zoom if open
    tracking.zoom_cancel()
    mouse_click()
    mouse_click()
    mouse_click()
    # close the mouse grid
    user.centroid_grid_close()


left drag | drag | drag start:
    # close zoom if open
    tracking.zoom_cancel()
    user.mouse_drag(0)
    # close the mouse grid
    user.centroid_grid_close()


right drag | righty drag:
    # close zoom if open
    tracking.zoom_cancel()
    user.mouse_drag(1)
    # close the mouse grid
    user.centroid_grid_close()