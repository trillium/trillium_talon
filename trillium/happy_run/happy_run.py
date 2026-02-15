"""
happy_run - Create new iTerm2 window, run 'happy', then execute a command
"""

import subprocess
import os
from talon import Module, actions, ctrl, ui, cron

mod = Module()


def get_current_directory():
    """Get current working directory, fallback to home directory"""
    try:
        return os.getcwd()
    except:
        return os.path.expanduser("~")


def create_terminal_window(current_dir):
    """Create new iTerm2 window in specified directory

    Returns:
        tuple: (terminal_app, new_window) - The iTerm2 app and the new window object
    """
    # Get iTerm2 app and track windows before
    terminal_apps = ui.apps(bundle="com.googlecode.iterm2")
    windows_before = set()
    if terminal_apps:
        terminal_app = terminal_apps[0]
        windows_before = {w.id for w in terminal_app.windows()}

    # Create new iTerm2 window in current directory
    applescript = f'tell application "iTerm" to create window with default profile command "cd {current_dir}"'
    subprocess.run(["osascript", "-e", applescript])

    # Wait for iTerm2 and new window to appear
    actions.sleep(0.5)

    # Get iTerm2 app (should exist now)
    terminal_app = ui.apps(bundle="com.googlecode.iterm2")[0]

    # Find the NEW window by comparing window IDs
    windows_after = {w.id for w in terminal_app.windows()}
    new_window_ids = windows_after - windows_before

    new_window = None
    if new_window_ids:
        new_window_id = new_window_ids.pop()
        new_window = next(w for w in terminal_app.windows() if w.id == new_window_id)
        print(f"Found new window: {new_window.title} (id: {new_window_id})")
    else:
        print("Warning: Could not detect new window")

    return terminal_app, new_window


def restore_window_focus_order(terminal_app, new_window):
    """Ensure our new window is the focused iTerm2 window

    If the user switched windows, focus our window to ensure keys go to it.
    Only does this if iTerm2 is active but our window is not first.
    """
    if new_window is None:
        return

    # Check if iTerm2 is the active app
    if ui.active_app() == terminal_app:
        # Get current window order
        windows = terminal_app.windows()
        if windows and windows[0].id != new_window.id:
            # Our window is not first - focus it to make it receive keys
            print(f"Restoring focus to new window (was: {windows[0].title})")
            new_window.focus()
            actions.sleep(0.2)


def type_happy(terminal_app, new_window):
    """Type 'happy' and press enter"""
    restore_window_focus_order(terminal_app, new_window)
    for char in "happy":
        ctrl.key_press(char, app=terminal_app)
        actions.sleep(0.05)
    ctrl.key_press("return", app=terminal_app)


def type_command(terminal_app, new_window, command):
    """Type the command and press enter"""
    restore_window_focus_order(terminal_app, new_window)
    for char in command:
        if char == " ":
            ctrl.key_press("space", app=terminal_app)
        else:
            ctrl.key_press(char, app=terminal_app)
        actions.sleep(0.01)
    ctrl.key_press("return", app=terminal_app)


def poll_terminal_titles(terminal_app, check_count=0, previous_titles=None):
    """Poll all iTerm2 window titles and record changes

    Runs every 500ms and tracks title changes for all iTerm2 windows.
    Stops after 20 consecutive checks with no changes.

    Args:
        terminal_app: iTerm2 app object
        check_count: Number of checks without changes (stops at 20)
        previous_titles: Dict of {window_id: title} from last check
    """
    if previous_titles is None:
        previous_titles = {}
        print("Starting terminal title polling...")

    # Get current window titles
    current_titles = {}
    for window in terminal_app.windows():
        current_titles[window.id] = window.title

    # Check for changes
    changes_detected = False
    for window_id, current_title in current_titles.items():
        previous_title = previous_titles.get(window_id)
        if previous_title != current_title:
            changes_detected = True
            if previous_title is not None:
                print(f"Window {window_id} title changed:")
                print(f"  Was: '{previous_title}'")
                print(f"  Now: '{current_title}'")
            else:
                print(f"Window {window_id} new title: '{current_title}'")

    # Check for removed windows
    for window_id in previous_titles:
        if window_id not in current_titles:
            changes_detected = True
            print(f"Window {window_id} closed")

    # Update check count
    if changes_detected:
        new_check_count = 0  # Reset counter when change detected
    else:
        new_check_count = check_count + 1

    # Stop after 20 checks with no changes
    if new_check_count >= 20:
        print("No title changes for 20 checks (10 seconds), stopping poll")
        print("\n=== Final iTerm2 Windows ===")
        for window_id, title in current_titles.items():
            print(f"Window {window_id}: '{title}'")
        print("==============================\n")
        return

    # Schedule next check
    cron.after("500ms", lambda: poll_terminal_titles(terminal_app, new_check_count, current_titles))


def poll_for_ready(terminal_app, new_window, command, previous_title, stable_count=0):
    """Poll the window title until it stabilizes (indicates 'happy' is ready)

    Args:
        terminal_app: iTerm2 app object
        new_window: The new window we're monitoring
        command: The command to type when ready
        previous_title: The window title from last check
        stable_count: Number of consecutive checks with same title
    """
    if new_window is None:
        print("Warning: No window to poll, falling back to 10s wait")
        cron.after("10s", lambda: type_command(terminal_app, new_window, command))
        return

    # Refresh window list to get current title
    current_windows = {w.id: w for w in terminal_app.windows()}
    current_window = current_windows.get(new_window.id)

    if current_window is None:
        print("Warning: Window disappeared, aborting")
        return

    current_title = current_window.title

    # Check if title is stable (hasn't changed for 3 checks = 1.5 seconds)
    if current_title == previous_title:
        new_stable_count = stable_count + 1
        if new_stable_count >= 3:
            print(f"Title stable for {new_stable_count} checks: '{current_title}'")
            print("happy is ready, typing command...")
            type_command(terminal_app, new_window, command)
            print("happy_run complete!")
            return
    else:
        # Title changed, reset stability counter
        print(f"Title changed! Was: '{previous_title}' Now: '{current_title}'")
        new_stable_count = 0

    # Check again in 500ms
    cron.after("500ms", lambda: poll_for_ready(terminal_app, new_window, command, current_title, new_stable_count))


def run_async(terminal_app, new_window, command):
    """Async function to type happy, wait for it to load, then type command"""
    # Get initial title before typing 'happy'
    initial_title = new_window.title if new_window else ""
    print(f"Initial title: '{initial_title}'")

    # Type 'happy' and press enter
    type_happy(terminal_app, new_window)

    # Start polling for title stability (indicates happy is ready)
    # Wait 500ms before first check to let happy start
    cron.after("500ms", lambda: poll_for_ready(terminal_app, new_window, command, initial_title, 0))


@mod.action_class
class Actions:
    def happy_run(command: str):
        """Open new iTerm2 window, type 'happy', wait 10s, then run command"""
        current_dir = get_current_directory()
        print(f"Opening new iTerm2 window in: {current_dir}")
        print(f"Will run 'happy', wait 10s, then: {command}")

        terminal_app, new_window = create_terminal_window(current_dir)

        # Wait a bit for window to be ready, then run async
        actions.sleep(1)
        run_async(terminal_app, new_window, command)

        print("happy_run initiated (will complete in 10s)")

    def happy_poll():
        """runs poll"""
        terminal_app = ui.apps(bundle="com.googlecode.iterm2")[0]

        poll_terminal_titles(terminal_app)

