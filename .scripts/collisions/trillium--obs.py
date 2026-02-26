_V = "0.0.3"; print(f"[v{_V}] {__name__}")

import subprocess
from pathlib import Path
from talon import Module, actions

mod = Module()

OBS_RECORDINGS_DIR = Path.home() / "Movies"


@mod.action_class
class Actions:
    def obs_open_last_recording():
        """Open the most recent OBS recording"""
        recordings = sorted(
            OBS_RECORDINGS_DIR.glob("*.mov"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not recordings:
            actions.user.notify("No recordings found in ~/Movies", level=2, duration=3)
            return
        path = recordings[0]
        print(f"[obs] Opening: {path.name}")
        subprocess.Popen(["open", str(path)])

    def obs_open_recordings_folder():
        """Open the OBS recordings folder in Finder"""
        print(f"[obs] Opening folder: {OBS_RECORDINGS_DIR}")
        subprocess.Popen(["open", str(OBS_RECORDINGS_DIR)])

    def obs_open_recordings_in_code():
        """Open the OBS recordings folder in VSCode"""
        print(f"[obs] Opening in code: {OBS_RECORDINGS_DIR}")
        subprocess.Popen(["code", str(OBS_RECORDINGS_DIR)])
