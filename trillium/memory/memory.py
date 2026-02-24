"""
Memory - Personal command reference with overlay display

Stores command/description pairs in a JSON file and displays them
via a full-screen overlay panel. Agents can edit memory.json directly;
_load() is called on every show() to pick up external edits.
"""

import json
from pathlib import Path

from talon import Module, Context, fs

from . import memory_overlay as overlay

mod = Module()

mod.tag("memory_active", desc="Memory overlay is visible")
_ctx = Context()

DATA_FILE = Path(__file__).parent / "memory.json"


def _load() -> list[dict]:
    """Load entries from disk."""
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save(entries: list[dict]):
    """Write entries to disk."""
    with open(DATA_FILE, "w") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")


def _refresh_if_visible(entries: list[dict]):
    """Update the overlay if it's currently showing."""
    if overlay._canvas:
        overlay.update(entries)


def _on_file_change(path: str, flags):
    """Called by fs.watch when memory.json changes on disk."""
    if overlay._canvas:
        entries = _load()
        overlay.update(entries)


fs.watch(str(DATA_FILE.parent), _on_file_change)


@mod.action_class
class Actions:
    def memory_show():
        """Show the memory overlay"""
        entries = _load()
        overlay.update(entries)
        overlay.show()
        _ctx.tags = ["user.memory_active"]

    def memory_hide():
        """Hide the memory overlay"""
        overlay.hide()
        _ctx.tags = []

    def memory_add(command: str, description: str):
        """Add an entry to memory"""
        entries = _load()
        # Don't add duplicates — update if command already exists
        for entry in entries:
            if entry.get("command") == command:
                entry["description"] = description
                _save(entries)
                _refresh_if_visible(entries)
                return
        entries.append({"command": command, "description": description})
        _save(entries)
        _refresh_if_visible(entries)

    def memory_remove(command: str):
        """Remove an entry from memory by command text"""
        entries = _load()
        entries = [e for e in entries if e.get("command") != command]
        _save(entries)
        _refresh_if_visible(entries)

    def memory_update(command: str, description: str):
        """Update the description for an existing memory entry"""
        entries = _load()
        for entry in entries:
            if entry.get("command") == command:
                entry["description"] = description
                _save(entries)
                _refresh_if_visible(entries)
                return

    def memory_clear():
        """Remove all entries from memory"""
        _save([])
        _refresh_if_visible([])
