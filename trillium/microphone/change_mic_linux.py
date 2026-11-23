"""Linux overrides for the microphone commands (operating-system-level override of change_mic.py)."""

from talon import Context, actions

ctx = Context()
ctx.matches = r"""
os: linux
"""


def _announce(mic: str):
    # Same effect as change_mic.announce_microphone, without the macOS-only OpenSuperWhisper sync.
    actions.sound.set_microphone(mic)


@ctx.action_class("user")
class UserActions:
    def mic_main():
        """Switch to the main microphone: the RØDE Wireless GO II receiver."""
        # Linux names it with its ALSA profile, e.g. "Wireless GO II RX Analog Stereo".
        for mic in actions.sound.microphones():
            if "wireless go" in mic.lower():
                _announce(mic)
                actions.user.sound_microphone_enable_event()
                return
        actions.app.notify("Wireless GO microphone not found")
