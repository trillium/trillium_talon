from talon import Module, actions, app, ui

mod = Module()

def announce_window_focus(window: ui.Window):
    """Announce when window focus changes"""
    try:
        app_name = window.app.name
        window_title = window.title

        # Create notification message
        message = f"{app_name}"
        if window_title and window_title != app_name:
            message += f"\n{window_title}"

        # Use your custom notify action
        # level 1 to avoid conflict with other notifications
        # 2 second duration for brief announcement
        actions.user.notify(message, level=1, duration=2)

    except Exception as e:
        actions.user.boolean_print("window_focus_announcer", f"Error: {e}")

def on_ready():
    """Register the window focus handler on Talon startup"""
    ui.register("win_focus", announce_window_focus)

app.register("ready", on_ready)
