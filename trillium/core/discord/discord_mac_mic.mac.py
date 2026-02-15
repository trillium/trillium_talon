from talon import Context, actions, ctrl, mac
from talon.mac import ui

ctx = Context()
ctx.matches = r"""
os: mac
"""


@ctx.action_class("user")
class UserActions:
    def discord_mute():
        ctrl.key_press("m", app=ui.apps(bundle="com.hnc.Discord")[0], super=True, shift=True)

# On Discord, the default keyboard shortcut for toggling mute is Command+Shift+M on macOS. This shortcut allows users to quickly mute or unmute their microphone while in a voice channel. Discord also offers other keyboard shortcuts for various actions like toggling deafen (Command+Shift+D), creating a call, and answering/declining incoming calls. 