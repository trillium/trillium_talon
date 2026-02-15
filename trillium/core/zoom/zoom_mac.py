from talon import Context, actions, ctrl, ui

ctx = Context()
ctx.matches = r"""
os: mac
"""

########
@ctx.action_class("user")
class zoom_actions:
    def zoom_mute():
        """This function mutes the zoom"""
        ctrl.key_press("a", app=ui.apps(bundle="us.zoom.xos")[0], super=True, shift=True)

    def zoom_toggle_video():
        """This function mutes the zoom"""
        ctrl.key_press("v", app=ui.apps(bundle="us.zoom.xos")[0], super=True, shift=True)

