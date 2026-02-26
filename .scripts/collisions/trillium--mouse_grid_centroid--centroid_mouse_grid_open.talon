tag: user.use_centroid_mouse_grid
and tag: user.mouse_grid_showing
-
^<user.letter>+$: user.centroid_grid_narrow_list(letter_list)
# ^<user.letter> <user.letter>$: user.centroid_grid_narrow_list(letter_list)
# ^<user.letter>+$: user.centroid_grid_narrow_list(letter_list)
^<user.letter>+ touch$:
    user.centroid_grid_narrow_list(letter_list)
    # touch:
    # close zoom if open
    tracking.zoom_cancel()
    mouse_click(0)
    # close the mouse grid if open
    user.centroid_grid_close()
    # End any open drags
    # Touch automatically ends left drags so this is for right drags specifically
    user.mouse_drag_end()
grid off:
    user.centroid_grid_close()
^<user.letter>+ grid off$:
    centroid_grid_narrow_list(letter_list)
    # sleep(200ms)
    # user.centroid_grid_close()

grid close:
    print('spiteless')
    user.centroid_grid_close()

[grid] reset: user.centroid_grid_reset()

grid back: user.centroid_grid_go_back()
