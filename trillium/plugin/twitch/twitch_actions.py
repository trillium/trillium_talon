"""Twitch Talon actions: stream status, chat connect/disconnect."""
from talon import Module, settings


mod = Module()


@mod.action_class
class TwitchActions:
    def twitch_stream_status() -> str:
        """Get a human-readable stream status string."""
        channel = settings.get("user.twitch_channel")
        if not channel:
            return "Twitch: no channel configured"
        from user.trillium_talon.trillium.plugin.twitch.twitch_helix import get_stream_status
        status = get_stream_status(channel)
        if status is None:
            return "Offline"
        return f"Live: {status.viewer_count} viewers - Playing {status.game_name} - {status.title}"

    def twitch_viewer_count() -> int:
        """Get current viewer count (0 if offline)."""
        channel = settings.get("user.twitch_channel")
        if not channel:
            return 0
        from user.trillium_talon.trillium.plugin.twitch.twitch_helix import get_stream_status
        status = get_stream_status(channel)
        if status is None:
            return 0
        return status.viewer_count

    def twitch_chat_connect():
        """Start the Twitch IRC chat client."""
        from user.trillium_talon.trillium.plugin.twitch.twitch_irc import client
        client.start()
        print("Twitch: chat client started")

    def twitch_chat_disconnect():
        """Stop the Twitch IRC chat client."""
        from user.trillium_talon.trillium.plugin.twitch.twitch_irc import client
        client.stop()
        print("Twitch: chat client stopped")
