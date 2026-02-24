from talon import Module, actions

mod = Module()


@mod.action_class
class Actions:
    def rapid_backspace(count: int = 300):
        """Execute backspace rapidly multiple times"""
        for _ in range(count):
            actions.key("backspace")

    def rapid_delete(count: int = 300):
        """Execute delete key rapidly multiple times"""
        for _ in range(count):
            actions.key("delete")
