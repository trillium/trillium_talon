"""
Memory - Personal command reference with overlay display

Stores command/description pairs in a JSON file and displays them
via a full-screen overlay panel. Supports pages for grouping commands.
Agents can edit memory.json directly; _load() is called on every show()
to pick up external edits.
"""

import json
from pathlib import Path

from talon import Module, Context, fs

from . import memory_overlay as overlay

mod = Module()

mod.tag("memory_active", desc="Memory overlay is visible")
mod.list("memory_page", desc="Available memory pages")
_ctx = Context()
_current_page = ""

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


def _update_page_list(entries: list[dict]):
    """Rebuild the dynamic page list from entries."""
    pages = sorted(set(e.get("page", "") for e in entries if e.get("page", "")))
    _ctx.lists["user.memory_page"] = {p: p for p in pages}


def _show_filtered(entries: list[dict], page: str):
    """Filter entries by page and update the overlay."""
    if page:
        filtered = [e for e in entries if e.get("page", "") == page]
    else:
        filtered = [e for e in entries if not e.get("page")]
    pages = sorted(set(e.get("page", "") for e in entries if e.get("page", "")))
    overlay.update(filtered, page=page, available_pages=pages)


def _refresh_if_visible(entries: list[dict]):
    """Update the overlay if it's currently showing."""
    _update_page_list(entries)
    if overlay._canvas:
        _show_filtered(entries, _current_page)


def _on_file_change(path: str, flags):
    """Called by fs.watch when memory.json changes on disk."""
    entries = _load()
    _update_page_list(entries)
    if overlay._canvas:
        _show_filtered(entries, _current_page)


fs.watch(str(DATA_FILE.parent), _on_file_change)


@mod.action_class
class Actions:
    def memory_show(page: str = ""):
        """Show the memory overlay, optionally filtered to a page"""
        global _current_page
        _current_page = page
        entries = _load()
        _update_page_list(entries)
        _show_filtered(entries, page)
        overlay.show()
        _ctx.tags = ["user.memory_active"]

    def memory_hide():
        """Hide the memory overlay"""
        overlay.hide()
        _ctx.tags = []

    def memory_add(command: str, description: str):
        """Add an entry to memory"""
        entries = _load()
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


# Populate page list on startup
_update_page_list(_load())
