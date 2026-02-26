from talon import Module, Context, actions


mod = Module()
state = {}
cron_jobs = {}
callbacks = {}
shush_start: float = 0

# Define the parrot_on tag
mod.tag("parrot_on", desc="Enable parrot noise detection")

# Context for toggling parrot on/off (always active)
toggle_ctx = Context()

# Context for parrot noise handlers (only active when parrot is on)
ctx = Context()
ctx.matches = r"""
tag: user.parrot_on
"""


@ctx.action_class("user")
class UserActions:
    def noise_lip_pop():
        print("🎵 DETECTED: lip-pop")

    def noise_tongue_click():
        print("🎵 DETECTED: tongue-click -- repeat")

    def noise_cmere():
        print("🎵 DETECTED: kitty-cmere")

    def noise_suppress_clicks():
        print("🎵 DETECTED: speech (suppressing clicks)")

    def noise_hiss():
        print("🎵 DETECTED: hiss")

    def noise_piggy_oink():
        print("🎵 DETECTED: piggy-oink")

    def noise_shh():
        print("🎵 DETECTED: shh")

    def noise_clap():
        print("🎵 DETECTED: clap")


@mod.action_class
class Actions:
    def noise_lip_pop():
        """Lip pop noise"""
        pass

    def noise_tongue_click():
        """Tongue click noise"""
        pass

    def noise_cmere():
        """Kitty c'mere noise"""
        pass

    def noise_suppress_clicks():
        """Speech detected (suppresses clicks)"""
        pass

    def noise_hiss():
        """Hiss noise"""
        pass

    def noise_piggy_oink():
        """Piggy oink noise"""
        pass

    def noise_shh():
        """Shh noise"""
        pass

    def noise_clap():
        """Clap noise"""
        pass

    def parrot_enable():
        """Enable parrot noise detection"""
        toggle_ctx.tags = ["user.parrot_on"]

    def parrot_disable():
        """Disable parrot noise detection"""
        toggle_ctx.tags = []

    def parrot_toggle():
        """Toggle parrot noise detection"""
        if "user.parrot_on" in toggle_ctx.tags:
            actions.user.parrot_disable()
        else:
            actions.user.parrot_enable()
