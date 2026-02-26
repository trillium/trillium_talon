# bingo:
#     user.hud_add_log("success", "B I N G O !")

bingo {user.list_name}:
    user.hud_add_log("success", list_name)

bingo mouse {user.list_name} | bingo mouse {user.letter}:
    user.named_mouse_position(list_name or letter)
    
# bingo mouse {user.letter}:
#     user.named_mouse_position(letter)

bingo capture {user.letter}:
    user.named_mouse_position(letter)

bingo capture <number>:
    # user.hud_add_losg("success", strnumber))
    user.numbered_thing(number)

bingo color {user.bingo_color}:
    user.hud_add_log("success", bingo_color)

    