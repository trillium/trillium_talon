"""Playback — play recent speech recordings non-blocking.

"playback ten" plays the 10 most recent .flac recordings.
"playback stop" kills the playback process.
Requires speech.record_all = 1 in settings and ffplay on PATH.
"""

import os
import shutil
import subprocess
from pathlib import Path

from talon import Module

mod = Module()

RECORDINGS_DIR = Path.home() / ".talon" / "recordings"
FFPLAY = shutil.which("ffplay") or "/home/linuxbrew/.linuxbrew/bin/ffplay"
SILENCE = Path(__file__).parent / "../../assets/sounds/silence.wav"

_playback_process: subprocess.Popen | None = None


def _find_recent_flacs(count: int) -> list[Path]:
    """Find the N most recent .flac files across all subdirectories."""
    flacs = []
    for dirpath, _, filenames in os.walk(RECORDINGS_DIR):
        for f in filenames:
            if f.endswith(".flac"):
                full = Path(dirpath) / f
                flacs.append(full)
    flacs.sort(key=lambda p: p.stat().st_mtime)
    return flacs[-count:]


@mod.action_class
class Actions:
    def playback(count: int):
        """Play the N most recent speech recordings non-blocking."""
        global _playback_process

        # Stop any existing playback first
        if _playback_process:
            try:
                _playback_process.kill()
            except Exception:
                pass
            _playback_process = None

        files = _find_recent_flacs(count)
        if not files:
            print("[playback] No .flac recordings found")
            return

        print(f"[playback] Playing {len(files)} recordings")

        # Build a shell command: prime audio with silence, then play each file
        parts = [f'{FFPLAY} -nodisp -autoexit {str(SILENCE.resolve())!r}']
        parts.extend(
            f'{FFPLAY} -nodisp -autoexit {str(f)!r}'
            for f in files
        )
        script = " && ".join(parts)

        print(f"[playback] script: {script[:200]}")
        _playback_process = subprocess.Popen(
            ["bash", "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def playback_stop():
        """Stop the current playback."""
        global _playback_process
        if _playback_process:
            try:
                os.killpg(os.getpgid(_playback_process.pid), 9)
            except Exception:
                try:
                    _playback_process.kill()
                except Exception:
                    pass
            _playback_process = None
