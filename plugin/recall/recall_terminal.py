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


# Map app names to the binary + args needed to launch with a working directory
_TERMINAL_LAUNCH = {
    "Gnome-terminal":   ("gnome-terminal", ["--working-directory={path}"]),
    "Mate-terminal":    ("mate-terminal", ["--working-directory={path}"]),
    "kitty":            ("kitty", ["--directory", "{path}"]),
    "Alacritty":        ("alacritty", ["--working-directory", "{path}"]),
    "foot":             ("foot", ["--working-directory={path}"]),
    "xfce4-terminal":   ("xfce4-terminal", ["--working-directory={path}"]),
    "Terminator":       ("terminator", ["--working-directory={path}"]),
    "Tilix":            ("tilix", ["--working-directory={path}"]),
    "Terminal":          ("open", ["-a", "Terminal", "{path}"]),
    "iTerm2":            ("open", ["-a", "iTerm", "{path}"]),
}


def _launch_terminal(app_name: str, path: str):
    """Launch a terminal at the given path using the correct binary for the app."""
    entry = _TERMINAL_LAUNCH.get(app_name)
    if entry:
        binary, arg_templates = entry
        args = [a.format(path=path) for a in arg_templates]
        ui.launch(path=binary, args=args)
    else:
        # Fallback: try launching the app name lowercased with common --working-directory
        ui.launch(path=app_name.lower(), args=[f"--working-directory={path}"])
