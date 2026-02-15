tag: user.use_centroid_mouse_grid
-
mouse grid:
    user.centroid_grid_select_screen(1)
    user.centroid_grid_activate()

grid win:
    user.centroid_grid_place_window()
    user.centroid_grid_activate()

reset <user.letter>+:
    user.centroid_grid_reset()
    user.centroid_grid_narrow_list(letter_list)

grid <user.letter>+:
    user.centroid_grid_activate()
    user.centroid_grid_narrow_list(letter_list)
    
grid screen [<number>]:
    user.centroid_grid_select_screen(number or 1)
    user.centroid_grid_activate()

# mouse update screenshot:
#     user.centroid_update_screenshot()
