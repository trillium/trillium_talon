"""Brain — voice-driven idea capture via the idea beads store.

Two-step capture: say "brain <thought>" to start, keep talking to append,
auto-ends after timeout or say "brain end". Like friction but for ideas.
"""

import os
import subprocess

from talon import Module, Context, actions, cron

mod = Module()
ctx = Context()

mod.tag("brain_mode", desc="Active when capturing a brain entry")

SPEAK = "/Users/trilliumsmith/code/speak/bin/speak"
TIMEOUT_MS = 90_000  # 90 seconds

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

# State
_active = False
_timeout_job = None
_current_issue_id = None
_last_issue_id = None


def _speak(text: str):
    subprocess.Popen(
        [SPEAK, "--enqueue", text],
        start_new_session=True,
        env=_env,
    )


def _create_issue(title: str) -> str | None:
    """Create an idea issue and return the ID."""
    try:
        result = subprocess.run(
            ["idea", "q", title, "-l", "brain", "-t", "task"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_env,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"[brain] idea create exception: {e}")
    return None


def _append_to_issue(issue_id: str, text: str):
    """Append text to an idea issue's notes."""
    try:
        subprocess.run(
            ["idea", "update", issue_id, "--append-notes", text],
            capture_output=True,
            text=True,
            timeout=10,
            env=_env,
        )
    except Exception:
        pass


def _on_timeout():
    actions.user.brain_end()


def _start_timeout():
    global _timeout_job
    if _timeout_job:
        cron.cancel(_timeout_job)
    _timeout_job = cron.after(f"{TIMEOUT_MS}ms", _on_timeout)


def _enter_brain_mode():
    global _active
    _active = True
    ctx.tags = ["user.brain_mode"]
    actions.user.mode_indicator_set_color("ff69b4")
    _start_timeout()


def _exit_brain_mode():
    global _active, _current_issue_id, _timeout_job
    _active = False
    _current_issue_id = None
    ctx.tags = []
    actions.user.mode_indicator_clear_color()
    if _timeout_job:
        cron.cancel(_timeout_job)
        _timeout_job = None


@mod.action_class
class Actions:
    def brain_capture(text: str):
        """Start brain capture — creates the idea and enters brain mode"""
        global _current_issue_id, _last_issue_id
        issue_id = _create_issue(text)
        _current_issue_id = issue_id
        if issue_id:
            _last_issue_id = issue_id
        _enter_brain_mode()
        _speak("Captured.")

    def brain_append(text: str):
        """Append text to the current brain entry"""
        if _current_issue_id:
            _append_to_issue(_current_issue_id, text)
            _start_timeout()

    def brain_end():
        """End brain capture mode"""
        _exit_brain_mode()

    def brain_more(text: str):
        """Append text to the last brain entry and re-enter brain mode"""
        global _current_issue_id
        if not _last_issue_id:
            return
        _append_to_issue(_last_issue_id, text)
        _current_issue_id = _last_issue_id
        _enter_brain_mode()
