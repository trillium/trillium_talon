"""OBS scene voice command actions."""
from talon import Module

from . import obs_scene_overlay
from .obs_scene_state import switch_scene, get_current_scene

mod = Module()


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
        if name == get_current_scene():
            return
        switch_scene(name)
        # Refresh overlay if showing
        if obs_scene_overlay.is_showing():
            obs_scene_overlay.hide()
            obs_scene_overlay.show()
