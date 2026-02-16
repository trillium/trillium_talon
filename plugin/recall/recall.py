"""
Recall - Save and recall specific windows by name

Allows you to save specific windows and bring them back later by name,
solving the problem where "focus chrome" brings any Chrome window instead
of the specific one you care about.

Features:
- Save the focused window with a name: "recall assign edgar" or "recall save edgar"
- Switch to it by just saying the name: "edgar"
- Dictate into a named window: "edgar hello world"
- See all named windows: "recall list" (shows overlay labels for 5 seconds)
- Forget a named window: "recall forget edgar"
"""

import json
from pathlib import Path
from talon import Module, Context, actions, app, ui
from . import recall_overlay

mod = Module()
ctx = Context()

# Storage file path
STORAGE_FILE = Path(__file__).parent / "saved_windows.json"

# In-memory storage: {name: {id: int, app: str, title: str}}
saved_windows = {}

mod.list("saved_window_names", desc="Names of saved windows for recall")


@mod.capture(rule="{self.saved_window_names}")
def saved_window_names(m) -> str:
    """Returns a single saved window name"""
    return m.saved_window_names


def load_saved_windows():
    """Load saved windows from JSON file"""
    global saved_windows
    if STORAGE_FILE.exists():
        try:
            with open(STORAGE_FILE, "r") as f:
                saved_windows = json.load(f)
            update_window_list()
        except Exception as e:
            print(f"[recall] Error loading saved windows: {e}")
            saved_windows = {}


def save_to_disk():
    """Persist saved windows to JSON file"""
    try:
        with open(STORAGE_FILE, "w") as f:
            json.dump(saved_windows, f, indent=2)
    except Exception as e:
        print(f"[recall] Error saving to disk: {e}")


def update_window_list():
    """Update the dynamic list of saved window names for voice commands"""
    if saved_windows:
        window_names = list(saved_windows.keys())
        spoken_forms = actions.user.create_spoken_forms_from_list(
            window_names,
            generate_subsequences=True
        )
        ctx.lists["self.saved_window_names"] = spoken_forms
    else:
        ctx.lists["self.saved_window_names"] = {}


def find_window_by_id(window_id: int) -> ui.Window:
    """Find a window by its ID across all apps"""
    for a in ui.apps(background=False):
        for window in a.windows():
            if window.id == window_id:
                return window
    return None


def cleanup_closed_windows(closed_window: ui.Window):
    """Remove saved windows that have been closed"""
    global saved_windows

    removed = []
    for name, info in list(saved_windows.items()):
        if info["id"] == closed_window.id:
            del saved_windows[name]
            removed.append(name)

    if removed:
        save_to_disk()
        update_window_list()


@mod.action_class
class Actions:
    def save_window(name: str):
        """Save the currently focused window with the given name"""
        global saved_windows

        window = ui.active_window()
        saved_windows[name] = {
            "id": window.id,
            "app": window.app.name,
            "title": window.title
        }

        save_to_disk()
        update_window_list()

    def recall_window(name: str):
        """Focus the saved window with the given name"""
        if name not in saved_windows:
            return

        info = saved_windows[name]
        window = find_window_by_id(info["id"])

        if window is None:
            recall_overlay.show_overlay()
            return

        actions.user.switcher_focus_window(window)

    def forget_window(name: str):
        """Remove a saved window by name"""
        global saved_windows

        if name not in saved_windows:
            return

        del saved_windows[name]
        save_to_disk()
        update_window_list()

    def forget_all_windows():
        """Clear all saved windows"""
        global saved_windows

        saved_windows = {}
        save_to_disk()
        update_window_list()

    def dictate_to_window(name: str, text: str):
        """Focus a saved window and type dictated text into it"""
        actions.user.recall_window(name)
        actions.user.dictation_insert(text)

    def list_saved_windows():
        """Show window name labels on each saved window for 5 seconds"""
        recall_overlay.show_overlay()


def on_ready():
    """Initialize on Talon startup"""
    load_saved_windows()
    ui.register("win_close", cleanup_closed_windows)


app.register("ready", on_ready)
