"""
Speak Scratchpad — batch flag & rewrite via VS Code scratch file.

Opens a VS Code scratchpad with speak history (read-only context) above a
--- separator. Below is empty for user input. On tab close, parses entries
and dispatches to the speak CLI.

Line format below ---:
  bare word         → speak --flag "word"
  word: replacement → speak --rewrites fix "word=replacement"
  # comment         → ignored
"""

import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from talon import Module, actions

mod = Module()

SPEAK = "/Users/trilliumsmith/code/speak/bin/speak"
REWRITES_FILE = Path("/Users/trilliumsmith/code/speak/config/rewrites.json")

# Talon's subprocess environment is stripped — speak needs uv, python3, ffplay
_env = os.environ.copy()
_env["PATH"] = ":".join([
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/Users/trilliumsmith/.local/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
    _env.get("PATH", ""),
])

# Module state
_scratchpad_path: Path | None = None


def _fetch_history() -> list[str]:
    """Get recent speak history as a list of strings."""
    try:
        result = subprocess.run(
            [SPEAK, "--history", "10"],
            capture_output=True, text=True, env=_env, timeout=5,
        )
        if result.returncode != 0:
            return []
        entries = json.loads(result.stdout)
        texts = []
        for e in entries:
            if isinstance(e, dict):
                texts.append(e.get("text", str(e)))
            else:
                texts.append(str(e))
        return texts
    except Exception:
        return []


def _build_file() -> Path:
    """Build the scratchpad temp file. Below --- starts empty for user input."""
    global _scratchpad_path

    history = _fetch_history()

    lines = []
    for text in history:
        lines.append(f'"{text}"')
    lines.append("---")
    lines.append("# bare word = flag for review")
    lines.append("# word: replacement = pronunciation fix")
    lines.append("")

    fd, path = tempfile.mkstemp(suffix=".txt", prefix="speak-scratchpad-")
    os.close(fd)
    _scratchpad_path = Path(path)
    _scratchpad_path.write_text("\n".join(lines) + "\n")
    return _scratchpad_path


def _open_and_wait(path: Path):
    """Open VS Code --wait in a background thread, process on tab close."""
    def _worker():
        try:
            subprocess.run(["code", "--wait", str(path)], env=_env)
        except Exception:
            pass
        _process()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _load_existing_rewrites() -> dict[str, str]:
    """Load all rewrites from rewrites.json as a flat dict."""
    if not REWRITES_FILE.exists():
        return {}
    try:
        with open(REWRITES_FILE, "r") as f:
            data = json.load(f)
        result = {}
        for section in ("pronunciation", "phrase_rewrites"):
            result.update(data.get(section, {}))
        return result
    except Exception:
        return {}


def _open_collisions(collisions: list[tuple[str, str, str]]):
    """Open a VS Code file showing collisions: (key, new_value, existing_value)."""
    lines = [
        "# These words already have rewrites.",
        "# To overwrite, uncomment the new line (remove the #).",
        "# Close this file to apply.",
        "",
    ]
    # Calculate padding so "# current" labels align vertically
    entry_lines: list[tuple[str, str | None]] = []  # (line_text, tag_or_None)
    for key, new_val, existing_val in collisions:
        entry_lines.append((f"# {key}: {existing_val}", "current"))
        entry_lines.append((f"# {key}: {new_val}", None))
    max_len = max((len(t) for t, _ in entry_lines), default=0)

    for i, (text, tag) in enumerate(entry_lines):
        if tag:
            padding = max_len - len(text) + 4
            lines.append(f"{text}{' ' * padding}# {tag}")
        else:
            lines.append(text)
        # blank line between pairs
        if tag is None:
            lines.append("")

    fd, path = tempfile.mkstemp(suffix=".txt", prefix="speak-collisions-")
    os.close(fd)
    collision_path = Path(path)
    collision_path.write_text("\n".join(lines) + "\n")

    def _worker():
        try:
            subprocess.run(["code", "--wait", str(path)], env=_env)
        except Exception:
            pass
        _process_collisions(collision_path)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _strip_inline_comment(line: str) -> str:
    """Strip trailing # comments from a line, e.g. 'daemon: day-mon  # current' → 'daemon: day-mon'."""
    # Find # that's preceded by whitespace (not inside a value)
    idx = line.find("  #")
    if idx >= 0:
        return line[:idx].rstrip()
    return line


def _process_collisions(path: Path):
    """Parse the collision file — uncommented key: value lines get applied."""
    if not path.exists():
        return
    content = path.read_text()
    fixes: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = _strip_inline_comment(stripped)
        if ": " in stripped:
            key, value = stripped.split(": ", 1)
            fixes.append(f"{key.strip()}={value.strip()}")

    if fixes:
        batch = ", ".join(fixes)
        subprocess.run([SPEAK, "--rewrites", "fix", batch], env=_env)
        msg = f"Collisions resolved: {len(fixes)} rewrites updated."
    else:
        msg = "Collisions file closed, no overwrites."
    subprocess.Popen([SPEAK, "--enqueue", msg], start_new_session=True, env=_env)

    path.unlink(missing_ok=True)


def _process():
    """Read the scratchpad, parse entries below ---, dispatch CLI commands.

    Bare words get flagged. Key: value lines get applied as rewrite fixes,
    unless the key already has an existing rewrite — collisions open a
    separate VS Code file for review.
    """
    global _scratchpad_path

    if _scratchpad_path is None or not _scratchpad_path.exists():
        _cleanup()
        return

    content = _scratchpad_path.read_text()
    parts = content.split("---", 1)
    if len(parts) < 2:
        _cleanup()
        return

    existing = _load_existing_rewrites()

    flags: list[str] = []
    fixes: list[str] = []
    collisions: list[tuple[str, str, str]] = []  # (key, new_val, existing_val)

    for line in parts[1].strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = _strip_inline_comment(stripped)
        if ": " in stripped:
            key, value = stripped.split(": ", 1)
            key = key.strip()
            value = value.strip()
            if key in existing:
                collisions.append((key, value, existing[key]))
            else:
                fixes.append(f"{key}={value}")
        else:
            flags.append(stripped)

    if flags:
        batch = ", ".join(flags)
        subprocess.run([SPEAK, "--flag", batch], env=_env)

    if fixes:
        batch = ", ".join(fixes)
        subprocess.run([SPEAK, "--rewrites", "fix", batch], env=_env)

    # Announce what was applied
    parts_msg = []
    if flags:
        parts_msg.append(f"{len(flags)} flagged")
    if fixes:
        parts_msg.append(f"{len(fixes)} rewrites added")
    if parts_msg:
        msg = f"Scratchpad done: {', '.join(parts_msg)}."
        subprocess.Popen([SPEAK, "--enqueue", msg], start_new_session=True, env=_env)
    elif not collisions:
        subprocess.Popen(
            [SPEAK, "--enqueue", "Scratchpad closed, no changes."],
            start_new_session=True, env=_env,
        )

    # Open collision file if needed
    if collisions:
        subprocess.Popen(
            [SPEAK, "--enqueue",
             f"{len(collisions)} collisions found, opening review file."],
            start_new_session=True, env=_env,
        )
        _open_collisions(collisions)

    _cleanup()


def _cleanup():
    """Remove temp file and reset state."""
    global _scratchpad_path
    if _scratchpad_path and _scratchpad_path.exists():
        _scratchpad_path.unlink()
    _scratchpad_path = None


@mod.action_class
class Actions:
    def speak_scratchpad():
        """Open VS Code scratchpad to batch-edit flags and rewrites"""
        path = _build_file()
        _open_and_wait(path)

    def speak_scratchpad_submit():
        """Manually process the current scratchpad and apply changes"""
        _process()

    def speak_scratchpad_cancel():
        """Cancel the scratchpad without applying changes"""
        _cleanup()
        subprocess.Popen(
            [SPEAK, "--enqueue", "Scratchpad cancelled."],
            start_new_session=True, env=_env,
        )
