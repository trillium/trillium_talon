"""OBS scene voice command actions."""
from talon import Module

from . import obs_scene_overlay
from .obs_scene_state import (
    switch_scene, get_current_scene, get_scenes,
    start_stream, stop_stream, start_recording, stop_recording, set_mics_muted,
)

mod = Module()


def _switch_and_refresh(name: str):
    """Switch scene and refresh overlay if visible."""
    if name == get_current_scene():
        return
    switch_scene(name)
    if obs_scene_overlay.is_showing():
        obs_scene_overlay.hide()
        obs_scene_overlay.show()


@mod.action_class
class Actions:
    def obs_show_scenes():
        """Show OBS scene list overlay"""
        obs_scene_overlay.show()

    def obs_hide_scenes():
        """Hide OBS scene list overlay"""
        obs_scene_overlay.hide()

    def obs_switch_scene(name: str):
        """Switch to an OBS scene by name"""
        _switch_and_refresh(name)

    def obs_switch_scene_by_letter(letter: str):
        """Switch to an OBS scene by its letter shortcut (a=first, b=second, etc.)"""
        scenes = get_scenes()
        idx = ord(letter.lower()) - ord('a')
        if 0 <= idx < len(scenes):
            _switch_and_refresh(scenes[idx])

    def obs_start_stream():
        """Start OBS stream"""
        start_stream()

    def obs_stop_stream():
        """Stop OBS stream"""
        stop_stream()

    def obs_start_recording():
        """Start OBS recording"""
        start_recording()

    def obs_stop_recording():
        """Stop OBS recording"""
        stop_recording()

    def obs_mute_mics():
        """Mute all OBS microphone inputs (coreaudio_input_capture sources)"""
        set_mics_muted(True)

    def obs_unmute_mics():
        """Unmute all OBS microphone inputs"""
        set_mics_muted(False)
