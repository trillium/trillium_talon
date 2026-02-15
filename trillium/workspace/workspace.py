_V = "0.0.3"; print(f"[v{_V}] {__name__}")

"""
Workspace Registry - Register, alias, and open VSCode workspaces by voice.

Registry stored in workspaces.json alongside this file.
Voice commands open workspaces via `code <path>`.
"""

import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
from talon import Module, Context, actions, app, fs, ui

mod = Module()
ctx = Context()

REGISTRY_FILE = Path(__file__).parent / "workspaces.json"

# In-memory registry
_registry = {"workspaces": {}, "removed": {}}

mod.list("workspace_alias", desc="Aliases for registered workspaces")


@mod.capture(rule="{self.workspace_alias}")
def workspace_alias(m) -> str:
    """Returns a workspace alias"""
    return m.workspace_alias


def _load_registry():
    """Load registry from JSON file"""
    global _registry
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, "r") as f:
                _registry = json.load(f)
            # Ensure both keys exist
            _registry.setdefault("workspaces", {})
            _registry.setdefault("removed", {})
            _update_list()
            print(f"[workspace] Loaded {len(_registry['workspaces'])} workspaces")
        except Exception as e:
            print(f"[workspace] Error loading registry: {e}")
            _registry = {"workspaces": {}, "removed": {}}
    else:
        _save_registry()


def _save_registry():
    """Persist registry to JSON file"""
    try:
        REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(REGISTRY_FILE, "w") as f:
            json.dump(_registry, f, indent=2)
    except Exception as e:
        print(f"[workspace] Error saving registry: {e}")


def _update_list():
    """Update the dynamic Talon list from registry aliases"""
    alias_map = {}
    for key, entry in _registry["workspaces"].items():
        for alias in entry.get("aliases", [key]):
            alias_map[alias] = key
    ctx.lists["self.workspace_alias"] = alias_map
    print(f"[workspace] Updated list: {list(alias_map.keys())}")


def _editor():
    """Return the editor command from the registry, defaulting to 'code'."""
    return _registry.get("editor", "code")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _name_from_path(path_str: str) -> str:
    """Generate a workspace name from a path.

    For .code-workspace files, use the filename without extension.
    For folders, use the folder name.
    Underscores become spaces for voice-friendliness.
    """
    p = Path(path_str)
    if p.suffix == ".code-workspace":
        name = p.stem
    else:
        name = p.name
    return name.replace("_", " ").replace("-", " ").strip()


def _find_key_by_alias(alias: str) -> str:
    """Find the workspace key that owns a given alias"""
    for key, entry in _registry["workspaces"].items():
        if alias in entry.get("aliases", []) or alias == key:
            return key
    return None


def _find_vscode_window(workspace_name: str):
    """Find an existing VSCode window for a workspace by matching title.

    Title format: '... — <workspace_name> — Visual Studio Code — ...'
    """
    name_lower = workspace_name.lower().replace(" ", "").replace("-", "").replace("_", "")
    for w in ui.windows():
        if w.app.name != "Code":
            continue
        parts = w.title.split(" \u2014 ")
        for i, part in enumerate(parts):
            if "Visual Studio Code" in part and i > 0:
                candidate = parts[i - 1].strip()
                candidate_norm = candidate.lower().replace(" ", "").replace("-", "").replace("_", "")
                if candidate_norm == name_lower:
                    return w
    return None


def _workspace_name_from_title() -> str:
    """Extract workspace/folder name from VSCode window title.

    Title format: '<file> — <workspace_name> — Visual Studio Code — ...'
    or:           '<workspace_name> — Visual Studio Code — ...'
    """
    try:
        title = ui.active_window().title
        if not title:
            return None
        # Split on ' — ' (em dash with spaces)
        parts = title.split(" \u2014 ")
        # Find the part right before 'Visual Studio Code'
        for i, part in enumerate(parts):
            if "Visual Studio Code" in part and i > 0:
                return parts[i - 1].strip()
    except Exception as e:
        print(f"[workspace] Error parsing title: {e}")
    return None


# VSCode state DB location on macOS
_VSCODE_STATE_DB = Path.home() / "Library/Application Support/Code/User/globalStorage/state.vscdb"


def _get_recent_paths_from_vscode() -> list:
    """Read recently opened folder/workspace paths from VSCode's state DB."""
    if not _VSCODE_STATE_DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(_VSCODE_STATE_DB))
        cursor = conn.execute(
            "SELECT value FROM ItemTable WHERE key = 'history.recentlyOpenedPathsList'"
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return []
        data = json.loads(row[0])
        paths = []
        for entry in data.get("entries", []):
            uri = entry.get("folderUri") or entry.get("workspace", {}).get("configPath")
            if uri:
                parsed = urlparse(uri)
                paths.append(unquote(parsed.path))
        return paths
    except Exception as e:
        print(f"[workspace] Error reading VSCode state DB: {e}")
        return []


def _get_current_workspace_path() -> str:
    """Get the workspace path by matching VSCode window title against recent paths."""
    name = _workspace_name_from_title()
    if not name:
        print("[workspace] Could not extract workspace name from window title")
        return None

    print(f"[workspace] Window title workspace name: '{name}'")

    # Search VSCode's recently opened paths for a match
    recent = _get_recent_paths_from_vscode()
    name_lower = name.lower().replace(" ", "").replace("-", "").replace("_", "")
    for path in recent:
        folder_name = Path(path).name.lower().replace(" ", "").replace("-", "").replace("_", "")
        if folder_name == name_lower:
            print(f"[workspace] Matched: {path}")
            return path

    # If no exact match, try substring
    for path in recent:
        if name.lower() in path.lower():
            print(f"[workspace] Substring match: {path}")
            return path

    print(f"[workspace] No match found for '{name}' in {len(recent)} recent paths")
    return None


@mod.action_class
class Actions:
    def workspace_open(alias: str):
        """Open a registered workspace by alias"""
        key = alias  # The capture already resolves alias -> key
        entry = _registry["workspaces"].get(key)
        if not entry:
            actions.user.notify(f"Workspace '{alias}' not found", level=2, duration=3)
            return

        path = entry["path"]
        name = _name_from_path(path)

        # Hot path: workspace already open — just focus it
        win = _find_vscode_window(name)
        if win:
            print(f"[workspace] Focusing existing window: {name}")
            win.focus()
            entry["last_invoked"] = _now_iso()
            _save_registry()
            return

        # Cold path: not open yet, code <path> opens a new window
        print(f"[workspace] Opening: {path}")
        try:
            subprocess.Popen([_editor(), path])
            entry["last_invoked"] = _now_iso()
            _save_registry()
        except Exception as e:
            actions.user.notify(f"Failed to open workspace: {e}", level=2, duration=3)
            print(f"[workspace] Error opening: {e}")

    def workspace_add_current():
        """Register the currently open VSCode workspace"""
        path = _get_current_workspace_path()
        if not path:
            actions.user.notify("Could not detect workspace path", level=2, duration=3)
            return

        name = _name_from_path(path)
        key = name.lower()

        if key in _registry["workspaces"]:
            actions.user.notify(f"Already registered: {name}", level=2, duration=3)
            return

        _registry["workspaces"][key] = {
            "path": path,
            "aliases": [name],
            "last_invoked": _now_iso(),
        }
        _save_registry()
        _update_list()

        actions.user.notify(f"Registered: {name}", level=2, duration=3)
        print(f"[workspace] Added '{name}' -> {path}")

        # Open the registry file so user can edit aliases
        subprocess.Popen([_editor(), str(REGISTRY_FILE)])

    def workspace_remove_by_alias(alias: str):
        """Remove a workspace by alias, moving it to the removed section"""
        key = alias  # Capture resolves alias -> key
        entry = _registry["workspaces"].get(key)
        if not entry:
            actions.user.notify(f"Workspace '{alias}' not found", level=2, duration=3)
            return

        entry["removed_at"] = _now_iso()
        _registry["removed"][key] = entry
        del _registry["workspaces"][key]
        _save_registry()
        _update_list()

        actions.user.notify(f"Removed: {key}", level=2, duration=2)
        print(f"[workspace] Removed '{key}'")

    def workspace_remove_current():
        """Remove the currently open workspace from registry"""
        path = _get_current_workspace_path()
        if not path:
            actions.user.notify("Could not detect workspace path", level=2, duration=3)
            return

        # Find entry by path
        found_key = None
        for key, entry in _registry["workspaces"].items():
            if entry["path"] == path:
                found_key = key
                break

        if not found_key:
            actions.user.notify("Current workspace not in registry", level=2, duration=3)
            return

        actions.user.workspace_remove_by_alias(found_key)

    def workspace_list():
        """Open the workspace registry file for viewing/editing"""
        subprocess.Popen([_editor(), str(REGISTRY_FILE)])
        actions.user.notify("Opened workspace registry", level=2, duration=2)

    def workspace_edit_aliases():
        """Open the workspace registry file for alias editing"""
        subprocess.Popen([_editor(), str(REGISTRY_FILE)])


def _on_registry_changed(path, flags):
    """Reload registry when the JSON file changes externally"""
    if path == str(REGISTRY_FILE):
        _load_registry()


def on_ready():
    """Initialize on Talon startup"""
    _load_registry()
    fs.watch(str(REGISTRY_FILE.parent), _on_registry_changed)
    print(f"[workspace] Ready - {len(_registry['workspaces'])} workspaces registered")


app.register("ready", on_ready)
