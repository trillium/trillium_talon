"""OBS scene state: reads scene list directly from OBS config on disk."""
import json
from pathlib import Path
from talon import Module, Context, app

mod = Module()
ctx = Context()

mod.list("obs_scene_names", desc="Available OBS scene names")

OBS_SCENE_FILE = Path.home() / "Library" / "Application Support" / "obs-studio" / "basic" / "scenes" / "Untitled.json"

_scenes: list[str] = []
_current_scene: str = ""


def get_scenes() -> list[str]:
    return _scenes


def get_current_scene() -> str:
    return _current_scene


def _fetch_current_scene() -> str:
    """Query OBS websocket for the actual current program scene."""
    import subprocess
    _SYSTEM_PYTHON = "/Users/trilliumsmith/.pyenv/versions/3.13.1/bin/python3"
    _QUERY_SCRIPT = '''
import subprocess, json
pw = subprocess.run(
    ["security", "find-generic-password", "-s", "obs-websocket", "-w"],
    capture_output=True, text=True, timeout=3,
).stdout.strip()
import obsws_python as obs
cl = obs.ReqClient(host="localhost", port=4455, password=pw, timeout=2)
print(cl.get_current_program_scene().scene_name)
'''
    try:
        result = subprocess.run(
            [_SYSTEM_PYTHON, "-c", _QUERY_SCRIPT],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"OBS scenes: websocket query error: {e}")
    return ""


def load_scenes():
    """Read scene list from OBS config file, current scene from websocket."""
    global _scenes, _current_scene
    try:
        data = json.loads(OBS_SCENE_FILE.read_text())
        _scenes = [
            s["name"]
            for s in data.get("sources", [])
            if s.get("versioned_id") == "scene"
        ]
        ctx.lists["user.obs_scene_names"] = {name.lower(): name for name in _scenes}
    except Exception as e:
        print(f"OBS scenes: error reading {OBS_SCENE_FILE}: {e}")
    # Get live current scene from websocket (falls back to disk value)
    live = _fetch_current_scene()
    if live:
        _current_scene = live
    elif not _current_scene:
        try:
            data = json.loads(OBS_SCENE_FILE.read_text())
            _current_scene = data.get("current_scene", "")
        except Exception:
            pass


def switch_scene(name: str):
    """Switch OBS scene via websocket subprocess (file is read-only for current scene)."""
    import subprocess
    _SYSTEM_PYTHON = "/Users/trilliumsmith/.pyenv/versions/3.13.1/bin/python3"
    _SWITCH_SCRIPT = '''
import subprocess, sys
pw = subprocess.run(
    ["security", "find-generic-password", "-s", "obs-websocket", "-w"],
    capture_output=True, text=True, timeout=3,
).stdout.strip()
import obsws_python as obs
cl = obs.ReqClient(host="localhost", port=4455, password=pw, timeout=2)
cl.set_current_program_scene(name=sys.argv[1])
'''
    try:
        subprocess.run(
            [_SYSTEM_PYTHON, "-c", _SWITCH_SCRIPT, name],
            capture_output=True, timeout=5,
        )
        global _current_scene
        _current_scene = name
    except Exception as e:
        print(f"OBS scenes: switch error: {e}")


def on_ready():
    load_scenes()

app.register("ready", on_ready)
