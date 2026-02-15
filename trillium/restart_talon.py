"""
restart_talon - Voice command to quit and restart Talon

Preserves user state (mode, parrot, etc.) across restarts.
"""

import json
import subprocess
from pathlib import Path
from talon import Module, app, scope, actions

mod = Module()

TIMESTAMP_FILE = Path.home() / ".talon" / "launch_timestamp"
RESTART_MARKER_FILE = Path.home() / ".talon" / "restart_marker"
RESTART_STATE_FILE = Path.home() / ".talon" / "restart_state.json"

# Shell script that runs independently of Talon:
# 1. Create restart marker file (so Talon knows it was restarted, not fresh launched)
# 2. Read current launch timestamp
# 3. Quit Talon via AppleScript
# 4. Poll with pgrep until Talon is gone
# 5. Brief pause for clean state
# 6. Relaunch with 'open' command
# 7. Poll until timestamp file changes (confirms Talon is ready)
RESTART_SCRIPT = '''
TIMESTAMP_FILE="$HOME/.talon/launch_timestamp"
RESTART_MARKER="$HOME/.talon/restart_marker"

# Create restart marker so Talon knows this was a restart
touch "$RESTART_MARKER"

# Read current timestamp before restart
OLD_TIMESTAMP=""
if [ -f "$TIMESTAMP_FILE" ]; then
    OLD_TIMESTAMP=$(cat "$TIMESTAMP_FILE")
fi

# Quit Talon
osascript -e 'quit app "Talon"'

# Wait for Talon to fully exit (poll with pgrep, up to 10 seconds)
for i in $(seq 1 50); do
    if ! pgrep -x Talon > /dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

# Brief pause after exit for clean state
sleep 1

# Relaunch
open /Applications/Talon.app

# Wait for timestamp to change (confirms Talon is ready, up to 30 seconds)
for i in $(seq 1 60); do
    if [ -f "$TIMESTAMP_FILE" ]; then
        NEW_TIMESTAMP=$(cat "$TIMESTAMP_FILE")
        if [ "$NEW_TIMESTAMP" != "$OLD_TIMESTAMP" ]; then
            break
        fi
    fi
    sleep 0.5
done
'''


def get_current_state() -> dict:
    """Capture current Talon state for restoration after restart."""
    state = {
        "version": "1.0",
    }

    # Get current modes
    try:
        current_modes = scope.get("mode")
        if current_modes:
            state["modes"] = list(current_modes) if isinstance(current_modes, set) else current_modes
    except Exception:
        state["modes"] = []

    # Get current tags (for parrot_on, etc.)
    try:
        current_tags = scope.get("tag")
        if current_tags:
            # Only save user-controlled tags we care about restoring
            tags_to_save = [t for t in current_tags if t in [
                "user.parrot_on",
            ]]
            state["tags"] = tags_to_save
    except Exception:
        state["tags"] = []

    # Get repeater state (last repeatable command)
    try:
        repeater_state = actions.user.repeater_get_state()
        if repeater_state:
            state["repeater"] = repeater_state
    except Exception:
        pass

    return state


def save_state():
    """Save current state to file before restart."""
    try:
        state = get_current_state()
        RESTART_STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        print(f"Failed to save restart state: {e}")


def load_state() -> dict | None:
    """Load saved state from file."""
    try:
        if RESTART_STATE_FILE.exists():
            state = json.loads(RESTART_STATE_FILE.read_text())
            # Clean up after reading
            RESTART_STATE_FILE.unlink()
            return state
    except Exception as e:
        print(f"Failed to load restart state: {e}")
    return None


def restore_state(state: dict):
    """Restore Talon state from saved state."""
    try:
        modes = state.get("modes", [])
        tags = state.get("tags", [])

        # Restore mode
        # Check for mixed mode (both command and dictation enabled)
        if "command" in modes and "dictation" in modes:
            actions.user.mixed_mode()
        elif "dictation" in modes and "command" not in modes:
            actions.user.dictation_mode()
        # else: default to command mode (Talon's default)

        # Restore parrot
        if "user.parrot_on" in tags:
            actions.user.parrot_enable()

        # Restore repeater state (last repeatable command)
        repeater_state = state.get("repeater")
        if repeater_state:
            actions.user.repeater_restore_state(repeater_state)

        print(f"Restored state: modes={modes}, tags={tags}, repeater={repeater_state}")

    except Exception as e:
        print(f"Failed to restore state: {e}")


def on_ready():
    """Called when Talon is ready - restore state if this was a restart."""
    if RESTART_MARKER_FILE.exists():
        RESTART_MARKER_FILE.unlink()
        state = load_state()
        if state:
            restore_state(state)
            actions.user.notify("Talon restarted - state restored")


app.register("ready", on_ready)


@mod.action_class
class Actions:
    def restart_talon():
        """Quit and restart Talon, preserving current state"""
        # Save state before restart
        save_state()

        # Spawn shell script as a detached process that survives Talon quitting
        subprocess.Popen(
            ['/bin/bash', '-c', RESTART_SCRIPT],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def save_state_for_restart():
        """Save current state and create restart marker (for MCP or external callers)."""
        save_state()
        RESTART_MARKER_FILE.touch()

    def talon_was_restarted() -> bool:
        """Check if Talon was restarted (vs fresh launch). Consumes the marker."""
        if RESTART_MARKER_FILE.exists():
            RESTART_MARKER_FILE.unlink()
            return True
        return False
