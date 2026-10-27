from talon import Module, actions

from . import last_dictation

mod = Module()


@mod.action_class
class Actions:
    def whisper_last():
        """Paste the most recent dictation from OpenSuperWhisper or Handy, whichever is newer."""
        text = last_dictation.latest_dictation()
        if text:
            actions.user.paste_transient(text)
