_V = "0.0.1"; print(f"[v{_V}] {__name__}")

import json
import subprocess
from pathlib import Path
from talon import Module, actions, imgui

mod = Module()


@imgui.open(y=0)
def gui_profiles(gui: imgui.GUI):
    gui.text("Display Profiles")
    gui.line()
    for name in _list_profiles():
        gui.text(f"  display load {name}")
    gui.spacer()
    gui.text("Say 'display load <name>' to apply")
    gui.text("Say 'display close' to dismiss")
    if gui.button("Close"):
        gui_profiles.hide()

TAG = "displayplacer"
PROFILES_DIR = Path.home() / ".config" / "displayplacer"


def _ensure_profiles_dir():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _get_current_command() -> str:
    """Run displayplacer list and extract the command at the bottom."""
    result = subprocess.run(
        ["displayplacer", "list"], capture_output=True, text=True
    )
    lines = result.stdout.strip().splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("displayplacer "):
            return line
    return ""


def _list_profiles() -> list[str]:
    _ensure_profiles_dir()
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


@mod.action_class
class Actions:
    def display_save_profile(name: str):
        """Save the current display arrangement as a named profile"""
        _ensure_profiles_dir()
        cmd = _get_current_command()
        if not cmd:
            actions.user.notify("Could not read current display config", level=2, duration=3)
            return
        profile_path = PROFILES_DIR / f"{name}.json"
        profile_path.write_text(json.dumps({"name": name, "command": cmd}, indent=2))
        print(f"[{TAG}] Saved profile '{name}': {cmd}")
        actions.user.notify(f"Display profile '{name}' saved", duration=2)

    def display_load_profile(name: str):
        """Load and apply a named display profile"""
        profile_path = PROFILES_DIR / f"{name}.json"
        if not profile_path.exists():
            actions.user.notify(f"Display profile '{name}' not found", level=2, duration=3)
            print(f"[{TAG}] Profile not found: {name}")
            return
        data = json.loads(profile_path.read_text())
        cmd = data["command"]
        print(f"[{TAG}] Loading profile '{name}': {cmd}")
        subprocess.Popen(cmd, shell=True)
        actions.user.notify(f"Display profile '{name}' applied", duration=2)

    def display_list_profiles():
        """Show the display profiles help menu"""
        profiles = _list_profiles()
        if not profiles:
            actions.user.notify("No display profiles saved", level=2, duration=3)
            return
        gui_profiles.show()

    def display_hide_profiles():
        """Hide the display profiles help menu"""
        gui_profiles.hide()

    def display_delete_profile(name: str):
        """Delete a saved display profile"""
        profile_path = PROFILES_DIR / f"{name}.json"
        if not profile_path.exists():
            actions.user.notify(f"Display profile '{name}' not found", level=2, duration=3)
            return
        profile_path.unlink()
        print(f"[{TAG}] Deleted profile '{name}'")
        actions.user.notify(f"Display profile '{name}' deleted", duration=2)

    def display_show_current():
        """Show the current display configuration command"""
        cmd = _get_current_command()
        if cmd:
            print(f"[{TAG}] Current: {cmd}")
            actions.user.notify(f"Current config logged to Talon console", duration=2)
        else:
            actions.user.notify("Could not read display config", level=2, duration=3)
