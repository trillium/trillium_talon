"""Twitch integration settings for Talon."""
from talon import Module

mod = Module()
mod.setting("twitch_channel", type=str, default="", desc="Twitch channel name to join for chat")
mod.setting("twitch_bot_username", type=str, default="", desc="Twitch bot/account username")
mod.setting(
    "twitch_helix_poll_interval",
    type=str,
    default="30s",
    desc="How often to poll Helix API for stream status (e.g. '30s', '1m')",
)

KEYCHAIN_ACCOUNT = "talon_chat_assistant"
