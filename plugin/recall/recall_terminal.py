"""
Recall Terminal - Terminal detection and launching

Self-contained module for terminal-related utilities:
- Detecting known terminal emulators
- Parsing working directories from terminal titles
- Launching new terminal windows at a given path
"""

import os
import re
from talon import ui

# Known terminal app names for path detection
TERMINAL_APPS = {
    "Gnome-terminal", "Mate-terminal", "kitty", "Alacritty",
    "foot", "xfce4-terminal", "Terminator", "Tilix",
    "Terminal", "iTerm2",
}


def is_terminal(app_name: str) -> bool:
    """Check if an app name is a known terminal emulator"""
    return app_name in TERMINAL_APPS


def _parse_title_path(title: str) -> str | None:
    """Extract a working directory from a terminal title.
    Tries multiple strategies as a fallback chain:
    1. Classic 'user@host: /path' pattern
    2. Split on common delimiters (— | - :) and check each segment
    3. Scan for any token starting with / or ~
    Returns the path if valid, else None."""
    try:
        # Strategy 1: user@host: /path
        match = re.search(r"@[^:]*:\s*(.+)$", title)
        if match:
            path = os.path.expanduser(match.group(1).strip())
            if os.path.isdir(path):
                return path

        # Strategy 2: split on common title delimiters and check segments
        segments = re.split(r"\s*[—|]\s*", title)
        for seg in segments:
            seg = seg.strip()
            if seg and (seg.startswith("/") or seg.startswith("~")):
                path = os.path.expanduser(seg)
                if os.path.isdir(path):
                    return path

        # Strategy 3: scan individual tokens for paths
        for token in title.split():
            token = token.strip()
            if token.startswith("/") or token.startswith("~"):
                path = os.path.expanduser(token)
                if os.path.isdir(path):
                    return path
    except Exception:
        pass
    return None


def detect_terminal_path(window: ui.Window) -> str:
    """Detect the working directory of a terminal window via title parsing.
    Only trusts the 'user@host: /path' pattern in the terminal title.
    The /proc fallback is intentionally omitted because gnome-terminal shares
    a single server PID across all windows, making it impossible to map a
    specific window to a specific child shell."""
    return _parse_title_path(window.title)


# Launcher registry: maps app name -> callable(path)
# OS-specific files (recall_terminal_mac.py, recall_terminal_linux.py)
# register their entries at load time
TERMINAL_LAUNCHERS = {}


def _launch_terminal(app_name: str, path: str):
    """Launch a terminal at the given path using OS-registered launchers."""
    launcher = TERMINAL_LAUNCHERS.get(app_name)
    if launcher:
        launcher(path)
    else:
        # Generic fallback
        ui.launch(path=app_name.lower(), args=[f"--working-directory={path}"])
