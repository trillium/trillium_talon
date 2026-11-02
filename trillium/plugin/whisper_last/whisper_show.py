"""Whisper show — voice-triggered overlay listing recent OpenSuperWhisper transcriptions.

Provides actions to show/hide the picker panel and to pick a transcription
(paste it and close). Mirrors the activity monitor's tag + thin-wrapper split.
"""

from talon import Context, Module

from . import whisper_show_overlay

mod = Module()
mod.tag("whisper_show_active", desc="Whisper transcription picker overlay is showing")

ctx = Context()


def _update_tag():
    """Sync the whisper_show_active tag with overlay visibility."""
    if whisper_show_overlay.is_showing():
        ctx.tags = ["user.whisper_show_active"]
    else:
        ctx.tags = []


whisper_show_overlay.set_on_hide(_update_tag)


@mod.action_class
class Actions:
    def whisper_show():
        """Show the whisper transcription picker overlay"""
        whisper_show_overlay.show()
        _update_tag()

    def whisper_show_hide():
        """Hide the whisper transcription picker overlay"""
        whisper_show_overlay.hide()
        _update_tag()

    def whisper_show_pick(n: int):
        """Paste the transcription at row n (0-based from overlay_select) and close"""
        success, message = whisper_show_overlay.pick_by_index(n)
        print(f"[whisper_show] {message}")
