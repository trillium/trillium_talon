from talon import Module, Context, actions, clip, settings, app

mod = Module()
ctx = Context()

@mod.action_class
class Actions:
    def write_the_clipboard():
        """Writes the clipboard to the active window"""

@ctx.action_class("user")
class Actions:
    def write_the_clipboard():
        """Writes the clipboard to the active window"""
        text = clip.text()
        actions.insert(text)