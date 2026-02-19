"""Playback — play recent speech recordings non-blocking.

"playback ten" plays the 10 most recent .flac recordings.
"playback last five minutes" plays all recordings from the last 5 minutes.
"playback pause" pauses, "playback resume" continues from where you left off.
"playback stop" kills playback and clears the queue.
Requires speech.record_all = 1 in settings and ffplay on PATH.
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from talon import Module

mod = Module()

RECORDINGS_DIR = Path.home() / ".talon" / "recordings"
FFPLAY = shutil.which("ffplay") or "/home/linuxbrew/.linuxbrew/bin/ffplay"
SILENCE = Path(__file__).parent / "../../assets/sounds/silence.wav"

_playback_process: subprocess.Popen | None = None
_progress_file: Path | None = None
_current_playlist: list[Path] = []
_playback_start_time: float = 0


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


def _find_flacs_since(minutes: int) -> list[Path]:
    """Find all .flac files modified within the last N minutes."""
    cutoff = time.time() - (minutes * 60)
    flacs = []
    for dirpath, _, filenames in os.walk(RECORDINGS_DIR):
        for f in filenames:
            if f.endswith(".flac"):
                full = Path(dirpath) / f
                if full.stat().st_mtime >= cutoff:
                    flacs.append(full)
    flacs.sort(key=lambda p: p.stat().st_mtime)
    return flacs


def _play_files(files: list[Path], start_index: int = 0):
    """Launch a background bash process to play files sequentially.

    Writes the current file index to a temp file so pause/resume can
    pick up where we left off.
    """
    global _playback_process, _progress_file, _current_playlist, _playback_start_time

    _current_playlist = list(files)
    remaining = files[start_index:]

    if not remaining:
        print("[playback] Nothing to play")
        return

    # Log file count and time span
    oldest_time = remaining[0].stat().st_mtime
    newest_time = remaining[-1].stat().st_mtime
    span_secs = newest_time - oldest_time
    span_min = int(span_secs // 60)
    span_sec = int(span_secs % 60)
    print(f"[playback] Playing {len(remaining)} recordings spanning {span_min}m{span_sec:02d}s")
    _playback_start_time = time.time()

    # Create a temp file to track progress
    fd, progress_path = tempfile.mkstemp(prefix="playback_", suffix=".idx")
    os.close(fd)
    _progress_file = Path(progress_path)

    # Build bash script that writes the current index before playing each file
    lines = [f'echo {start_index} > {progress_path!r}']
    # Prime audio
    lines.append(f'{FFPLAY} -nodisp -autoexit {str(SILENCE.resolve())!r} 2>/dev/null')
    for i, f in enumerate(remaining, start=start_index):
        lines.append(f'echo {i} > {progress_path!r}')
        lines.append(f'{FFPLAY} -nodisp -autoexit {str(f)!r} 2>/dev/null')
    # Mark complete
    lines.append(f'echo done > {progress_path!r}')
    script = "\n".join(lines)

    _playback_process = subprocess.Popen(
        ["bash", "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _read_progress() -> int | None:
    """Read the current file index from the progress file. Returns None if done or missing."""
    if not _progress_file or not _progress_file.exists():
        return None
    try:
        content = _progress_file.read_text().strip()
        if content == "done":
            _print_elapsed()
            return None
        return int(content)
    except Exception:
        return None


def _print_elapsed():
    """Print how long playback took."""
    if _playback_start_time:
        elapsed = time.time() - _playback_start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        print(f"[playback] Finished — playback took {mins}m{secs:02d}s")


def _kill_process():
    """Kill the playback process group."""
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


def _cleanup_progress():
    """Remove the progress temp file."""
    global _progress_file
    if _progress_file and _progress_file.exists():
        try:
            _progress_file.unlink()
        except Exception:
            pass
    _progress_file = None


@mod.action_class
class Actions:
    def playback(count: int):
        """Play the N most recent speech recordings non-blocking."""
        _kill_process()
        _cleanup_progress()
        files = _find_recent_flacs(count)
        if not files:
            print("[playback] No .flac recordings found")
            return
        _play_files(files)

    def playback_minutes(minutes: int):
        """Play all speech recordings from the last N minutes."""
        _kill_process()
        _cleanup_progress()
        files = _find_flacs_since(minutes)
        if not files:
            print(f"[playback] No recordings in the last {minutes} minute(s)")
            return
        _play_files(files)

    def playback_pause():
        """Pause playback — can be resumed later."""
        _kill_process()
        idx = _read_progress()
        if idx is not None:
            elapsed = time.time() - _playback_start_time if _playback_start_time else 0
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            print(f"[playback] Paused at {idx + 1}/{len(_current_playlist)} ({mins}m{secs:02d}s in)")
        else:
            print("[playback] Nothing playing")

    def playback_resume():
        """Resume playback from where it was paused."""
        idx = _read_progress()
        if idx is None or not _current_playlist:
            print("[playback] Nothing to resume")
            return
        # Start from the next file (current one was interrupted)
        resume_from = idx + 1
        if resume_from >= len(_current_playlist):
            print("[playback] Playlist finished")
            _cleanup_progress()
            return
        print(f"[playback] Resuming from index {resume_from}")
        _play_files(_current_playlist, start_index=resume_from)

    def playback_stop():
        """Stop playback and clear the queue."""
        _kill_process()
        _cleanup_progress()
        global _current_playlist
        _current_playlist = []
