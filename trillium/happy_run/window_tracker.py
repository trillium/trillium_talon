# window_tracker.py - Track windows before/after a launch to find the new one
#
# Inputs: bundle_id (str) - e.g. "com.apple.Terminal"
# Outputs: via callback — (app, new_window)
#
# 1. Snapshot existing window IDs for the given bundle
# 2. After launch, poll until a new window ID appears in the diff
# 3. Pass (app, new_window) to callback
#
# Uses cron.after() polling — non-blocking, same pattern as readiness_poller.
# The pipeline is blocked from advancing until the callback fires.

from talon import cron, ui

POLL_INTERVAL = "500ms"
MAX_CHECKS = 10  # 5 seconds timeout


def snapshot_windows(bundle_id):
    """Capture current window IDs for a bundle.

    Call this BEFORE launching the new process.

    Args:
        bundle_id: e.g. "com.apple.Terminal"

    Returns:
        Set of window IDs currently open for that bundle.
        Empty set if the app isn't running yet.
    """
    apps = ui.apps(bundle=bundle_id)
    if apps:
        return {w.id for w in apps[0].windows()}
    return set()


def poll_for_new_window(bundle_id, windows_before, callback, check_count=0):
    """Poll until a new window appears for the bundle.

    Args:
        bundle_id: e.g. "com.apple.Terminal"
        windows_before: Set of window IDs from snapshot_windows()
        callback: Called with (app, new_window) when new window is found
        check_count: Internal counter for timeout
    """
    if check_count >= MAX_CHECKS:
        print(f"Timeout: no new window for {bundle_id} after {MAX_CHECKS} checks")
        return

    apps = ui.apps(bundle=bundle_id)
    if not apps:
        # App not running yet, keep waiting
        cron.after(
            POLL_INTERVAL,
            lambda: poll_for_new_window(bundle_id, windows_before, callback, check_count + 1),
        )
        return

    app = apps[0]
    windows_after = {w.id for w in app.windows()}
    new_ids = windows_after - windows_before

    if new_ids:
        new_id = new_ids.pop()
        new_window = next(w for w in app.windows() if w.id == new_id)
        print(f"New window found: '{new_window.title}' (id: {new_id})")
        callback(app, new_window)
        return

    # No new window yet, keep polling
    cron.after(
        POLL_INTERVAL,
        lambda: poll_for_new_window(bundle_id, windows_before, callback, check_count + 1),
    )
