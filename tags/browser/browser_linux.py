from talon import Context, actions

ctx = Context()
ctx.matches = r"""
os: linux
tag: browser
"""


@ctx.action_class("browser")
class BrowserActions:
    def focus_address():
        actions.key("ctrl-l")
