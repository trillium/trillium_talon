# Mapping for reversing navigation modifiers
REVERSE_MODIFIERS = {
    "left": "right",
    "right": "left",
    "lineUp": "lineDown",
    "lineDown": "lineUp",
    "wordLeft": "wordRight",
    "wordRight": "wordLeft",
    "word": "wordLeft",  # "word" alone means wordRight, so opposite is wordLeft
}

# Mapping for reversing special keys
REVERSE_SPECIAL_KEYS = {
    "pageup": "pagedown",
    "pagedown": "pageup",
    "home": "end",
    "end": "home",
}

# Combined mapping with trigger, opposite, and action
OPPOSITES = {
    "upper": {
        "trigger": "downer",
        "action": ("user", "rango_command_without_target", ("scrollDownPage",))
    },
    "downer": {
        "trigger": "upper",
        "action": ("user", "rango_command_without_target", ("scrollUpPage",))
    },
    "north": {
        "trigger": "south",
        "action": ("edit", "down", ())
    },
    "south": {
        "trigger": "north",
        "action": ("edit", "up", ())
    },
    # east/west
    "east": {
        "trigger": "west",
        "action": ("edit", "left", ())
    },
    "west": {
        "trigger": "east",
        "action": ("edit", "right", ())
    },
    # scroll up/down (page up/down)
    "scroll up": {
        "trigger": "scroll down",
        "action": ("edit", "page_down", ())
    },
    "scroll down": {
        "trigger": "scroll up",
        "action": ("edit", "page_up", ())
    },
    # go page up/down
    "go page up": {
        "trigger": "go page down",
        "action": ("edit", "page_down", ())
    },
    "go page down": {
        "trigger": "go page up",
        "action": ("edit", "page_up", ())
    },
    # special key (page up/down, home/end, etc.)
    "<user.special_key>": {
        "trigger": "reverse",
        "action": ("user", "special_key_opposite", ())
    },
    # go top/bottom
    "go top": {
        "trigger": "go bottom",
        "action": ("edit", "file_end", ())
    },
    "go bottom": {
        "trigger": "go top",
        "action": ("edit", "file_start", ())
    },
    # go way directions
    "go way left": {
        "trigger": "go way right",
        "action": ("edit", "line_end", ())
    },
    "go way right": {
        "trigger": "go way left",
        "action": ("edit", "line_start", ())  # Actually runs line_start twice in the original
    },
    "go way up": {
        "trigger": "go way down",
        "action": ("edit", "file_end", ())
    },
    "go way down": {
        "trigger": "go way up",
        "action": ("edit", "file_start", ())
    },
    # go line start/end
    "go line start": {
        "trigger": "go line end",
        "action": ("edit", "line_end", ())
    },
    "go line end": {
        "trigger": "go line start",
        "action": ("edit", "line_start", ())
    },
    # head/tail
    "head": {
        "trigger": "tail",
        "action": ("edit", "line_end", ())
    },
    "tail": {
        "trigger": "head",
        "action": ("edit", "line_start", ())
    },
    # indent more/less
    "indent [more]": {
        "trigger": "(indent less | out dent)",
        "action": ("edit", "indent_less", ())
    },
    "(indent less | out dent)": {
        "trigger": "indent [more]",
        "action": ("edit", "indent_more", ())
    },
    # tab navigation
    "tab next": {
        "trigger": "tab (last | previous)",
        "action": ("app", "tab_previous", ())
    },
    "tab (last | previous)": {
        "trigger": "tab next",
        "action": ("app", "tab_next", ())
    },
    # window navigation
    "window next": {
        "trigger": "window (last | previous)",
        "action": ("app", "window_previous", ())
    },
    "window (last | previous)": {
        "trigger": "window next",
        "action": ("app", "window_next", ())
    },
    # terminal navigation
    "terminal next": {
        "trigger": "terminal (last | previous)",
        "action": ("user", "vscode", ("workbench.action.terminal.focusPrevious",))
    },
    "terminal (last | previous)": {
        "trigger": "terminal next",
        "action": ("user", "vscode", ("workbench.action.terminal.focusNext",))
    },
    # convo navigation (messages app)
    "[go] (convo | tab) next": {
        "trigger": "[go] (convo | tab) previous",
        "action": ("actions", "key", ("ctrl-shift-tab",))
    },
    "[go] (convo | tab) previous": {
        "trigger": "[go] (convo | tab) next",
        "action": ("actions", "key", ("ctrl-tab",))
    },
    # wheel scrolling
    "wheel up": {
        "trigger": "wheel down",
        "action": ("user", "mouse_scroll_down", ())
    },
    "wheel down": {
        "trigger": "wheel up",
        "action": ("user", "mouse_scroll_up", ())
    },
    # mouse clock navigation
    "<user.letters_colors>+": {
        "trigger": "reverse",
        "action": ("user", "mouse_clock_move_opposite", ())
    },
    "^<user.letters_colors>+$": {
        "trigger": "reverse",
        "action": ("user", "mouse_clock_move_opposite", ())
    },
    "^clock <user.letters_colors>+$": {
        "trigger": "reverse",
        "action": ("user", "mouse_clock_move_opposite", ())
    },
    "^<user.letters_colors>+ clock$": {
        "trigger": "reverse",
        "action": ("user", "mouse_clock_move_opposite", ())
    },
    "clock <user.letters_colors>+": {
        "trigger": "reverse",
        "action": ("user", "mouse_clock_move_opposite", ())
    },
    "<user.letters_colors>+ clock": {
        "trigger": "reverse",
        "action": ("user", "mouse_clock_move_opposite", ())
    },
    # circle answer (clock ring mode)
    "<user.circle_answer>": {
        "trigger": "reverse",
        "action": ("user", "mouse_clock_move_opposite", ())
    },
    # tab / shift-tab
    "tab": {
        "trigger": "shift-tab",
        "action": ("actions", "key", ("shift-tab",))
    },
    "shift-tab": {
        "trigger": "tab",
        "action": ("actions", "key", ("tab",))
    },
    # volume up/down
    "volume up": {
        "trigger": "volume down",
        "action": ("actions", "key", ("voldown",))
    },
    "volume down": {
        "trigger": "volume up",
        "action": ("actions", "key", ("volup",))
    },
    # reverse command - opposite is to move in original direction
    "reverse": {
        "trigger": "original",
        "action": ("user", "mouse_clock_move_original", ())
    },
}
