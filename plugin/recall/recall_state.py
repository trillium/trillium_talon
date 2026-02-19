"""
Recall State - Shared state, Talon registration, and storage

This module is the foundation of the recall system. It owns:
- Module/Context registration and tag/list declarations
- Captures for saved_window_names and recall_command_name
- Persistent storage (saved_windows, archived_windows, load/save)
- The dynamic spoken-form list (update_window_list)
- Forbidden-name checking
- Two-step pending-input state
"""

import json
from pathlib import Path
from talon import Module, Context, actions

mod = Module()
ctx = Context()

# Tags
mod.tag("recall_pending_input", desc="Waiting for second input in a two-step recall command")
mod.tag("recall_overlay_visible", desc="A recall overlay is currently showing")
pending_ctx = Context()
overlay_ctx = Context()

# State for two-step commands (combine, rename, alias)
# _pending_mode: "combine" | "rename" | "alias" | ""
_pending_mode: str = ""
_pending_name: str = ""

# Storage file path
STORAGE_FILE = Path(__file__).parent / "saved_windows.json"

# In-memory storage: {name: {id, app, title, path, aliases}}
saved_windows = {}

# Archive of forgotten windows: {name: {id, app, title, path, aliases, forgotten_at}}
archived_windows = {}

# Persistent highlight toggle (survives Talon restarts via _settings in JSON)
_persistent_highlight_enabled: bool = False

# Forbidden names are defined in forbidden_recall_names.talon-list
mod.list("forbidden_recall_names", desc="Words that cannot be used as recall window names")

# Named commands for recall config (defined in recall_commands.talon-list)
mod.list("recall_commands", desc="Named commands that can be assigned to recall windows")

mod.list("saved_window_names", desc="Names of saved windows for recall")


@mod.capture(rule="{self.saved_window_names}")
def saved_window_names(m) -> str:
    """Returns a single saved window name"""
    return m.saved_window_names


@mod.capture(rule="{self.recall_commands}")
def recall_command_name(m) -> str:
    """Returns the spoken name of a recall command (not the resolved shell command)"""
    # m[0] is the spoken form, m.recall_commands is the resolved value
    return str(m[0])


def find_name_for_window_id(window_id) -> str | None:
    """Return the recall name for a given window ID, or None if not saved."""
    if window_id is None:
        return None
    for name, info in saved_windows.items():
        if info.get("id") == window_id:
            return name
    return None


def is_forbidden(name: str) -> bool:
    """Check if a name is in the forbidden list"""
    return name.lower() in ctx.lists.get("user.forbidden_recall_names", {}).values()


def load_saved_windows():
    """Load saved windows from JSON file"""
    global saved_windows, archived_windows, _persistent_highlight_enabled
    if STORAGE_FILE.exists():
        try:
            with open(STORAGE_FILE, "r") as f:
                data = json.load(f)
            # Archive lives under "_archive" key, everything else is active
            archived_windows = data.pop("_archive", {})
            # Settings (persistent_highlight, etc.) live under "_settings"
            settings = data.pop("_settings", {})
            _persistent_highlight_enabled = settings.get("persistent_highlight", False)
            saved_windows = data
            update_window_list()
        except Exception as e:
            print(f"[recall] Error loading saved windows: {e}")
            saved_windows = {}
            archived_windows = {}


def save_to_disk():
    """Persist saved windows and archive to JSON file"""
    try:
        data = dict(saved_windows)
        if archived_windows:
            data["_archive"] = archived_windows
        # Save settings if any are non-default
        if _persistent_highlight_enabled:
            data["_settings"] = {"persistent_highlight": True}
        with open(STORAGE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[recall] Error saving to disk: {e}")


def update_window_list():
    """Update the dynamic list of saved window names for voice commands.
    Uses create_spoken_forms_from_map so aliases resolve to the canonical name."""
    if saved_windows:
        # Build map: {spoken_form: canonical_name}
        # Both the canonical name and all aliases point to the canonical name
        name_map = {}
        for name, info in saved_windows.items():
            name_map[name] = name
            for alias in info.get("aliases", []):
                name_map[alias] = name
        spoken_forms = actions.user.create_spoken_forms_from_map(
            name_map,
            generate_subsequences=True,
        )
        ctx.lists["self.saved_window_names"] = spoken_forms
    else:
        ctx.lists["self.saved_window_names"] = {}


def _cancel_pending():
    """Cancel any pending two-step command."""
    global _pending_mode, _pending_name
    _pending_mode = ""
    _pending_name = ""
    pending_ctx.tags = []
