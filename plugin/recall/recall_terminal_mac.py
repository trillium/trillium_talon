"""
Recall Terminal (macOS) - AppleScript-based terminal launching

Registers macOS terminal launchers into the shared TERMINAL_LAUNCHERS registry.
"""

from talon import app

if app.platform == "mac":
    import subprocess

    from .recall_terminal import TERMINAL_LAUNCHERS

    def _launch_mac_terminal(path: str):
        # Each -e is one line of AppleScript; do script without "in window" creates a new window
        subprocess.Popen([
            "osascript",
            "-e", 'tell application "Terminal"',
            "-e", f'do script "cd {path} && clear"',
            "-e", "activate",
            "-e", "end tell",
        ])

    def _launch_mac_iterm2(path: str):
        subprocess.Popen([
            "osascript",
            "-e", 'tell application "iTerm2"',
            "-e", "create window with default profile",
            "-e", "tell current session of current window",
            "-e", f'write text "cd \'{path}\' && clear"',
            "-e", "end tell",
            "-e", "end tell",
        ])

    TERMINAL_LAUNCHERS["Terminal"] = _launch_mac_terminal
    TERMINAL_LAUNCHERS["iTerm2"] = _launch_mac_iterm2
