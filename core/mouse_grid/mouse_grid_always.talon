mouse grid:
    user.grid_select_screen(1)
    user.grid_activate()

grid win:
    user.grid_place_window()
    user.grid_activate()

reset <user.letter>+:
    user.grid_reset()
    user.grid_narrow_list(letter_list)

grid <user.letter>+:
    user.grid_activate()
    user.grid_narrow_list(letter_list)
    
grid screen [<number>]:
    user.grid_select_screen(number or 1)
    user.grid_activate()
