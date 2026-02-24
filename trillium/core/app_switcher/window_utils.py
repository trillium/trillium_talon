from talon import Module, ui, actions
import time

mod = Module()

def rects_intersect(r1, r2):
    return not (
        r1.x + r1.width <= r2.x or
        r2.x + r2.width <= r1.x or
        r1.y + r1.height <= r2.y or
        r2.y + r2.height <= r1.y
    )

def windows_in_viewport(screen=None):
    """
    Returns a list of ui.Window objects that are at least partially visible on the given screen.
    If no screen is provided, uses the primary screen (ui.screens()[0]).
    """
    if screen is None:
        screen = ui.screens()[0]
    screen_rect = screen.rect
    visible_windows = []
    for app in ui.apps(background=False):
        for window in app.windows():
            try:
                rect = window.rect
            except Exception:
                continue  # skip windows that raise errors
            if rect and rects_intersect(rect, screen_rect):
                visible_windows.append(window)
    return visible_windows

def is_ui_apps_in_z_order():
    """
    Returns a list of dicts for the apps in ui.apps(),
    with the frontmost app (ui.active_app()) assigned z_order 0.
    The rest are assigned None, as global z-order is not available.
    Each dict contains the app, its main window's rect, active status, and z_order.
    """
    apps = ui.apps(background=False)
    active_app = ui.active_app()
    active_window = ui.active_window()
    if not apps:
        return []
    result = []
    for app in apps:
        rect = None
        try:
            windows = app.windows()
            if windows:
                rect = windows[0].rect
        except Exception:
            pass
        z_order = 0 if active_app and app == active_app else None
        result.append({
            'app': app,
            'rect': rect,
            'is_active': (active_window and app == active_window.app),
            'z_order': z_order
        })
    return result

def z_order_list():
    """
    Returns a list of apps ordered by inferred z-order (frontmost first),
    using the z_order field from is_ui_apps_in_z_order().
    If z-order cannot be inferred, returns empty list.
    """
    app_data = is_ui_apps_in_z_order()
    # Filter out entries where z_order is None
    ordered = [entry for entry in app_data if entry.get('z_order') is not None]
    # Sort by z_order (0 is frontmost)
    ordered.sort(key=lambda x: x['z_order'])
    return [entry['app'] for entry in ordered]

_recent_window_stack = []  # List of (window, timestamp)

def update_recent_window_stack():
    """
    Tracks the most recently focused windows by polling the active window.
    Maintains a list of unique windows in most-recently-focused order (frontmost first),
    using window.id to ensure uniqueness.
    """
    global _recent_window_stack
    active = ui.active_window()
    actions.user.boolean_print("update_recent_window_stack", str(active))
    if not active:
        return
    # Remove if already in stack (by window.id)
    _recent_window_stack = [entry for entry in _recent_window_stack if entry[0].id != active.id]
    # Insert at front with timestamp
    _recent_window_stack.insert(0, (active, time.time()))
    # Optionally, limit stack size
    _recent_window_stack = _recent_window_stack[:50]

    # Clean up windows that no longer exist (by window.id)
    existing_ids = {w.id for app in ui.apps(background=False) for w in app.windows()}
    _recent_window_stack = [entry for entry in _recent_window_stack if entry[0].id in existing_ids]

def get_recent_window_stack():
    """
    Returns a list of dicts for the most recently focused windows, frontmost first.
    Each dict contains: window, app, rect, is_active, z_order (0 is frontmost)
    """
    active = ui.active_window()
    stack = []
    for idx, (window, ts) in enumerate(_recent_window_stack):
        stack.append({
            'window': window,
            'app': window.app,
            'rect': window.rect,
            'is_active': (window == active),
            'z_order': idx
        })
    return stack

@mod.action_class
class Actions:
    def windows_in_viewport() -> list:
        """Return a list of ui.Window objects that are at least partially visible on the main screen."""
        return windows_in_viewport()
    
    def is_ui_apps_in_z_order() -> dict:
        """Return a dict of ui.Window objects that are at least partially visible on the main screen."""
        return is_ui_apps_in_z_order()
    
    def z_order_list() -> list:
        """Return a list of apps ordered by inferred z-order (frontmost first), with their main window rect and active status."""
        return z_order_list()

    def update_recent_window_stack():
        """Update the recent window stack with the current active window."""
        return update_recent_window_stack()

    def get_recent_window_stack() -> list:
        """Return a list of the most recently focused windows, frontmost first, with z_order."""
        return get_recent_window_stack()
