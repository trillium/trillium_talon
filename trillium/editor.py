from talon import Module, actions, cron

mod = Module()

FONT = "Menlo"
FONT_SIZE = 14
PAD = 12
LINE_HEIGHT = FONT_SIZE + 4  # matches textarea's gap=4 default

_poll_job = None


def editor_ui(props):
    screen, div, text, textarea = actions.user.ui_elements(["screen", "div", "text", "textarea"])
    state = actions.user.ui_elements("state")

    line_count, set_line_count = state.use("line_count", 1)
    scroll_line, set_scroll_line = state.use("scroll_line", 0)

    def on_change(e):
        value = actions.user.ui_elements_get_input_value("editor")
        set_line_count(value.count("\n") + 1)

    visible_lines = (400 - PAD * 2) // LINE_HEIGHT + 2
    first = scroll_line + 1
    last = scroll_line + visible_lines + 1

    return screen(justify_content="center", align_items="center")[
        div(flex_direction="row")[
            div(
                background_color="252525",
                padding=PAD,
                padding_right=8,
                align_items="flex_end",
                gap=4,
                height=400,
                overflow_y="hidden",
                border_top_left_radius=12,
                border_bottom_left_radius=12,
            )[
                *[text(str(i), font_family=FONT, font_size=FONT_SIZE, color="555555")
                  for i in range(first, min(last, line_count + 1))]
            ],
            textarea(
                id="editor",
                font_family=FONT,
                font_size=FONT_SIZE,
                width=570,
                height=400,
                background_color="1e1e1e",
                color="d4d4d4",
                padding=PAD,
                padding_left=8,
                on_change=on_change,
                autofocus=True,
                border_top_right_radius=12,
                border_bottom_right_radius=12,
            ),
        ]
    ]


def _sync_scroll():
    try:
        offset = actions.user.ui_elements_get_input_scroll_offset("editor")
        scroll_line = int(offset // LINE_HEIGHT)
        actions.user.ui_elements_set_state("scroll_line", scroll_line)
    except Exception:
        pass


@mod.action_class
class Actions:
    def toggle_editor():
        """Toggle the basic text editor overlay"""
        global _poll_job
        is_active = actions.user.ui_elements_is_active(editor_ui)
        actions.user.ui_elements_toggle(editor_ui, show_hints=False)
        if is_active:
            if _poll_job:
                cron.cancel(_poll_job)
                _poll_job = None
        else:
            _poll_job = cron.interval("100ms", _sync_scroll)
