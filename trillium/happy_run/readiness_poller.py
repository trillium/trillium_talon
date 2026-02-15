# readiness_poller.py - Poll window title until ready signal, then invoke callback
#
# Inputs: terminal_app (ui.App), window (ui.Window), callback (callable)
# Outputs: calls callback when ready
#
# Two modes:
#   1. marker mode: look for a specific string in the title (e.g. "✳")
#   2. stability mode: wait for title to stop changing (fallback)
#
# Uses cron.after() for polling — runs on Talon's event loop, non-blocking.
# Each poll schedules the next via cron.after(), forming a recursive chain.
# No threads, no blocking — compatible with other cron jobs in the system.

from talon import cron, ui

HAPPY_MARKER = "✳"
POLL_INTERVAL = "500ms"
STABILITY_THRESHOLD = 3  # consecutive checks = 1.5s
MAX_CHECKS = 40  # 20 seconds timeout

# Recording storage — list of (check_count, window_id, title) tuples
# Only records when title differs from previous (uses existing diff logic)
_recording = []
_recording_active = False


def poll_for_marker(app, window, marker, callback, check_count=0):
    """Poll until window title contains the marker string.

    Args:
        app: Target app (ui.App)
        window: Target window (ui.Window)
        marker: String to look for in title (e.g. "✳")
        callback: Called with (app, window) when marker appears
        check_count: Internal counter for timeout
    """
    if check_count >= MAX_CHECKS:
        print(f"Timeout: marker '{marker}' not found after {MAX_CHECKS} checks")
        return

    # Refresh window reference to get current title
    current_windows = {w.id: w for w in app.windows()}
    current_window = current_windows.get(window.id)

    if current_window is None:
        print("Window disappeared, aborting")
        return

    if marker in current_window.title:
        print(f"Marker '{marker}' found in title: '{current_window.title}'")
        callback(app, current_window)
        return

    cron.after(
        POLL_INTERVAL,
        lambda: poll_for_marker(app, window, marker, callback, check_count + 1),
    )


def poll_for_stability(app, window, callback, previous_title=None, stable_count=0, check_count=0):
    """Poll until window title stabilizes (stops changing).

    Fallback for when there's no known marker to look for
    (e.g. waiting for shell prompt after terminal launch).

    Args:
        app: Target app (ui.App)
        window: Target window (ui.Window)
        callback: Called with (app, window) when title is stable
        previous_title: Title from last check
        stable_count: Consecutive checks with same title
        check_count: Internal counter for timeout
    """
    if check_count >= MAX_CHECKS:
        print(f"Timeout: title never stabilized after {MAX_CHECKS} checks")
        return

    current_windows = {w.id: w for w in app.windows()}
    current_window = current_windows.get(window.id)

    if current_window is None:
        print("Window disappeared, aborting")
        return

    current_title = current_window.title

    if current_title == previous_title:
        new_stable = stable_count + 1
        if new_stable >= STABILITY_THRESHOLD:
            print(f"Title stable: '{current_title}'")
            callback(app, current_window)
            return
    else:
        new_stable = 0

    cron.after(
        POLL_INTERVAL,
        lambda: poll_for_stability(
            app, window, callback, current_title, new_stable, check_count + 1
        ),
    )


import json
import os

RECORDING_DIR = os.path.dirname(os.path.realpath(__file__))


def record_titles(app, window, check_count=0, previous_title=None):
    """Record window title changes over time for debugging.

    Only logs when title differs from previous check (reuses diff pattern).
    Writes results to recordings.json in the happy_run directory.

    Args:
        app: Target app (ui.App)
        window: Target window (ui.Window)
        check_count: Internal counter for timeout
        previous_title: Title from last check
    """
    global _recording, _recording_active

    if check_count == 0:
        _recording = []
        _recording_active = True

    if check_count >= MAX_CHECKS or not _recording_active:
        _recording_active = False
        _save_recording()
        return

    current_windows = {w.id: w for w in app.windows()}
    current_window = current_windows.get(window.id)

    if current_window is None:
        _recording_active = False
        _save_recording()
        return

    current_title = current_window.title

    # Only record on diff
    if current_title != previous_title:
        _recording.append({
            "elapsed_s": check_count * 0.5,
            "window_id": current_window.id,
            "title": current_title,
        })

    cron.after(
        POLL_INTERVAL,
        lambda: record_titles(app, window, check_count + 1, current_title),
    )


def stop_recording():
    """Stop an active recording."""
    global _recording_active
    _recording_active = False


def _save_recording():
    """Write recording to recordings.json in happy_run dir."""
    path = os.path.join(RECORDING_DIR, "recordings.json")

    # Append to existing recordings
    existing = []
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)

    existing.append({
        "changes": len(_recording),
        "entries": _recording,
    })

    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
