"""Twitch Talon actions: stream status, chat connect/disconnect, title management."""
from talon import Module, actions, settings


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

    def twitch_show_title():
        """Show the current Twitch channel title in the HUD log."""
        channel = settings.get("user.twitch_channel")
        if not channel:
            actions.user.hud_add_log("warning", "Twitch: no channel configured")
            return
        from user.trillium_talon.trillium.plugin.twitch.twitch_helix import get_channel_title
        title = get_channel_title(channel)
        if title:
            actions.user.hud_add_log("event", f"Title: {title}")
        else:
            actions.user.hud_add_log("warning", "Twitch: could not fetch title")

    def twitch_set_title(title: str):
        """Set the Twitch channel title."""
        channel = settings.get("user.twitch_channel")
        if not channel:
            actions.user.hud_add_log("warning", "Twitch: no channel configured")
            return
        from user.trillium_talon.trillium.plugin.twitch.twitch_helix import set_channel_title
        success = set_channel_title(channel, title)
        if success:
            actions.user.hud_add_log("success", f"Title set: {title}")
        else:
            actions.user.hud_add_log("warning", "Twitch: failed to update title")
