"""
Recall - Save and recall specific windows by name

Allows you to save specific windows and bring them back later by name,
solving the problem where "focus chrome" brings any Chrome window instead
of the specific one you care about.
"""

import json
import os
from pathlib import Path
from talon import Module, Context, actions, app, ui, imgui

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
            actions.user.boolean_print("recall", f"Loaded {len(saved_windows)} saved windows")
            update_window_list()
        except Exception as e:
            actions.user.boolean_print("recall", f"Error loading saved windows: {e}")
            saved_windows = {}


def save_to_disk():
    """Persist saved windows to JSON file"""
    try:
        with open(STORAGE_FILE, "w") as f:
            json.dump(saved_windows, f, indent=2)
    except Exception as e:
        actions.user.boolean_print("recall", f"Error saving to disk: {e}")


def update_window_list():
    """Update the dynamic list of saved window names for voice commands"""
    # Create spoken forms from saved window names
    if saved_windows:
        window_names = list(saved_windows.keys())
        actions.user.boolean_print("recall", f"Updating list with window names: {window_names}")
        spoken_forms = actions.user.create_spoken_forms_from_list(
            window_names,
            generate_subsequences=True
        )
        actions.user.boolean_print("recall", f"Generated spoken forms: {spoken_forms}")
        ctx.lists["self.saved_window_names"] = spoken_forms
    else:
        ctx.lists["self.saved_window_names"] = {}
        actions.user.boolean_print("recall", "No saved windows, list is empty")


def find_window_by_id(window_id: int) -> ui.Window:
    """Find a window by its ID across all apps"""
    for app in ui.apps(background=False):
        for window in app.windows():
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
        actions.user.boolean_print("recall", f"Removed closed windows: {', '.join(removed)}")
        save_to_disk()
        update_window_list()


@mod.action_class
class Actions:
    def save_window(name: str):
        """Save the currently focused window with the given name"""
        global saved_windows

        try:
            window = ui.active_window()
            app_name = window.app.name
            window_title = window.title
            window_id = window.id

            # Store window info
            saved_windows[name] = {
                "id": window_id,
                "app": app_name,
                "title": window_title
            }

            # Persist and update list
            save_to_disk()
            update_window_list()

            # Notify user
            message = f"Saved: {name}\n{app_name}: {window_title}"
            actions.user.notify(message, level=2, duration=3)
            actions.user.boolean_print("recall", f"{message.replace(chr(10), ' → ')}")

        except Exception as e:
            error_msg = f"Failed to save window: {e}"
            actions.user.notify(error_msg, level=2, duration=3)
            actions.user.boolean_print("recall", f"{error_msg}")

    def recall_window(name: str):
        """Focus the saved window with the given name"""
        actions.user.boolean_print("recall", f"recall_window called with name='{name}'")
        actions.user.boolean_print("recall", f"saved_windows keys: {list(saved_windows.keys())}")

        if name not in saved_windows:
            msg = f"No saved window named '{name}'"
            actions.user.notify(msg, level=2, duration=3)
            actions.user.boolean_print("recall", f"{msg}")
            return

        info = saved_windows[name]
        actions.user.boolean_print("recall", f"Looking for window ID {info['id']} (app: {info['app']}, title: {info['title']})")

        window = find_window_by_id(info["id"])

        if window is None:
            msg = f"Window '{name}' not found\n(may be closed)"
            actions.user.notify(msg, level=2, duration=3)
            actions.user.boolean_print("recall", f"{msg.replace(chr(10), ' ')}")
            return

        actions.user.boolean_print("recall", f"Found window: {window.title} (ID: {window.id})")
        actions.user.boolean_print("recall", f"Current active window: {ui.active_window().title}")

        try:
            # Use the existing switcher_focus_window action
            actions.user.boolean_print("recall", f"Calling switcher_focus_window...")
            actions.user.switcher_focus_window(window)

            # Notify user
            msg = f"Recalled: {name}"
            actions.user.notify(msg, level=2, duration=2)
            actions.user.boolean_print("recall", f"SUCCESS - {msg} ({info['app']}: {info['title']})")

        except Exception as e:
            error_msg = f"Failed to focus '{name}': {e}"
            actions.user.notify(error_msg, level=2, duration=3)
            actions.user.boolean_print("recall", f"ERROR - {error_msg}")

    def forget_window(name: str):
        """Remove a saved window by name"""
        global saved_windows

        if name not in saved_windows:
            msg = f"No saved window named '{name}'"
            actions.user.notify(msg, level=2, duration=3)
            actions.user.boolean_print("recall", f"{msg}")
            return

        info = saved_windows[name]
        del saved_windows[name]

        save_to_disk()
        update_window_list()

        msg = f"Forgot: {name}"
        actions.user.notify(msg, level=2, duration=2)
        actions.user.boolean_print("recall", f"{msg} (was {info['app']}: {info['title']})")

    def forget_all_windows():
        """Clear all saved windows"""
        global saved_windows

        count = len(saved_windows)
        saved_windows = {}

        save_to_disk()
        update_window_list()

        msg = f"Forgot all {count} saved windows"
        actions.user.notify(msg, level=2, duration=2)
        print(f"[recall] {msg}")

    def list_saved_windows():
        """Show GUI list of all saved windows"""
        if gui_saved_windows.showing:
            gui_saved_windows.hide()
        else:
            gui_saved_windows.show()


@imgui.open()
def gui_saved_windows(gui: imgui.GUI):
    """GUI showing all saved windows"""
    gui.text("Saved Windows (Recalls)")
    gui.line()

    if not saved_windows:
        gui.text("No saved windows")
    else:
        for name, info in sorted(saved_windows.items()):
            # Check if window still exists
            window = find_window_by_id(info["id"])
            status = "✓" if window else "✗"
            gui.text(f"{status} {name}: {info['app']} - {info['title']}")

    gui.spacer()
    if gui.button("Close"):
        actions.user.list_saved_windows()


def on_win_close(window: ui.Window):
    """Handle window close events to cleanup saved windows"""
    cleanup_closed_windows(window)


def on_ready():
    """Initialize on Talon startup"""
    load_saved_windows()
    ui.register("win_close", on_win_close)
    actions.user.boolean_print("recall", "Ready - use 'save recall <name>' to save windows")


app.register("ready", on_ready)
