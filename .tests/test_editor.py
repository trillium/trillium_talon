from talon import Module, actions

mod = Module()

def bare_editor(props):
    screen, textarea = actions.user.ui_elements(["screen", "textarea"])
    return screen(justify_content="center", align_items="center")[
        textarea(id="bare", font_family="Menlo", font_size=14, width=600, height=400,
                 background_color="1e1e1e", color="d4d4d4", autofocus=True)
    ]

@mod.action_class
class Actions:
    def test_bare_editor():
        """Show bare textarea with no wrapping"""
        actions.user.ui_elements_show(bare_editor)
