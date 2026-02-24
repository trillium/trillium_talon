"""
Speak Review - Voice-driven review session for speak rewrite entries

Load pending rewrites from the speak CLI config, present them one at a time
via overlay + audio, and accept/reject/skip each entry.
"""

import json
import os
import subprocess
from pathlib import Path

from talon import Module, Context, actions

from . import speak_review_overlay as overlay

mod = Module()

mod.tag("speak_review_active", desc="Speak rewrite review session is active")
review_ctx = Context()

SPEAK = "/Users/trilliumsmith/code/speak/bin/speak"
REWRITES_FILE = Path("/Users/trilliumsmith/code/speak/config/rewrites.json")
REVIEW_FILE = Path("/Users/trilliumsmith/code/speak/config/rewrites-review.json")

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

# Transient state — speak CLI handles persistence
_entries: list[dict] = []
_current_idx: int = -1


def _load_entries(status_filter: str = "pending") -> list[dict]:
    """Load entries filtered by review status.

    status_filter: "pending" (unreviewed), "accepted", "rejected",
                   "unnecessary", or "all" (every entry regardless).
    """
    rewrites = {}
    if REWRITES_FILE.exists():
        with open(REWRITES_FILE, "r") as f:
            rewrites = json.load(f)

    reviewed = {}
    if REVIEW_FILE.exists():
        with open(REVIEW_FILE, "r") as f:
            reviewed = json.load(f)

    if status_filter == "pending":
        # Pending: in rewrites.json but not yet reviewed
        entries = []
        for section in ("pronunciation", "phrase_rewrites"):
            for key, value in rewrites.get(section, {}).items():
                if f"{section}:{key}" not in reviewed:
                    entries.append({"section": section, "key": key, "value": value})
        return entries

    # For all other filters, pull from the review file (entries may have
    # been removed from rewrites.json, e.g. "unnecessary")
    entries = []
    for review_key, info in reviewed.items():
        if status_filter != "all" and info.get("status") != status_filter:
            continue
        entries.append({
            "section": info.get("section", ""),
            "key": info.get("word", ""),
            "value": info.get("value", ""),
        })

    # For "all", also include pending entries not yet in reviewed
    if status_filter == "all":
        for section in ("pronunciation", "phrase_rewrites"):
            for key, value in rewrites.get(section, {}).items():
                if f"{section}:{key}" not in reviewed:
                    entries.append({"section": section, "key": key, "value": value})

    return entries


def _play_current():
    """Play the current entry's key and value via speak --enqueue (non-blocking)."""
    if _current_idx < 0 or _current_idx >= len(_entries):
        return
    entry = _entries[_current_idx]
    key = entry["key"]
    value = entry["value"]
    if value:
        text = f"{key} ... {value}"
    else:
        text = f"{key} ... remove"
    subprocess.Popen([SPEAK, "--enqueue", text], start_new_session=True, env=_env)


def _update_overlay():
    """Sync the overlay with current state."""
    if _current_idx < 0 or _current_idx >= len(_entries):
        return
    entry = _entries[_current_idx]
    overlay.update(
        section=entry["section"],
        key=entry["key"],
        value=entry["value"],
        current=_current_idx + 1,
        total=len(_entries),
    )


def _advance_after_action():
    """After accept/reject removes an entry, show next (or stop if done)."""
    global _current_idx
    if not _entries:
        actions.user.speak_review_stop()
        return
    if _current_idx >= len(_entries):
        _current_idx = len(_entries) - 1
    _update_overlay()
    _play_current()


def _start_session(status_filter: str = "pending"):
    """Load entries with the given filter, open overlay, play first."""
    global _entries, _current_idx
    _entries = _load_entries(status_filter)
    if not _entries:
        actions.user.notify(f"No {status_filter} rewrites to review")
        return
    _current_idx = 0
    review_ctx.tags = ["user.speak_review_active"]
    overlay.show()
    _update_overlay()
    _play_current()


@mod.action_class
class Actions:
    def speak_review_start():
        """Start a speak rewrite review session with pending entries"""
        _start_session("pending")

    def speak_review_stop():
        """Stop the review session, kill audio, and clean up"""
        global _entries, _current_idx
        subprocess.Popen([SPEAK, "--stop"], start_new_session=True, env=_env)
        _entries = []
        _current_idx = -1
        review_ctx.tags = []
        overlay.hide()

    def speak_review_play():
        """Replay the current entry"""
        _play_current()

    def speak_review_accept():
        """Accept the current entry and advance"""
        global _current_idx
        if _current_idx < 0 or _current_idx >= len(_entries):
            return
        entry = _entries[_current_idx]
        review_key = f"{entry['section']}:{entry['key']}"
        subprocess.run([SPEAK, "--rewrites", "accept", review_key], env=_env)
        _entries.pop(_current_idx)
        _advance_after_action()

    def speak_review_reject():
        """Reject the current entry and advance"""
        global _current_idx
        if _current_idx < 0 or _current_idx >= len(_entries):
            return
        entry = _entries[_current_idx]
        review_key = f"{entry['section']}:{entry['key']}"
        subprocess.run([SPEAK, "--rewrites", "reject", review_key], env=_env)
        _entries.pop(_current_idx)
        _advance_after_action()

    def speak_review_unnecessary():
        """Mark the current entry as unnecessary (Kokoro says it right) and advance"""
        global _current_idx
        if _current_idx < 0 or _current_idx >= len(_entries):
            return
        entry = _entries[_current_idx]
        subprocess.run([SPEAK, "--rewrites", "unnecessary", entry["key"]], env=_env)
        _entries.pop(_current_idx)
        _advance_after_action()

    def speak_review_regenerate():
        """Bulk regenerate LLM alternatives for all rejected entries, then reload"""
        subprocess.Popen(
            [SPEAK, "--rewrites", "regenerate"],
            start_new_session=True, env=_env,
        )

    def speak_review_recent(filter: str = ""):
        """Open review panel filtered by status"""
        _start_session(filter if filter else "all")

    def speak_review_fix(new_value: str):
        """Change the current entry's pronunciation and advance"""
        global _current_idx
        if _current_idx < 0 or _current_idx >= len(_entries):
            return
        entry = _entries[_current_idx]
        subprocess.run([SPEAK, "--rewrites", "fix", entry["key"], new_value], env=_env)
        _entries.pop(_current_idx)
        _advance_after_action()

    def speak_review_next():
        """Skip to next entry without marking"""
        global _current_idx
        if not _entries:
            return
        _current_idx = min(_current_idx + 1, len(_entries) - 1)
        _update_overlay()
        _play_current()

    def speak_review_previous():
        """Go back to previous entry"""
        global _current_idx
        if not _entries:
            return
        _current_idx = max(_current_idx - 1, 0)
        _update_overlay()
        _play_current()
