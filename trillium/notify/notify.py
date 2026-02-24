from talon import Module, imgui, cron
import time

module = Module()

# Track notifications by level: {level: {"message": str, "timestamp": float}}
notifications = {}
auto_hide_jobs = {}

BASE_Y = 70  # Base y position
LEVEL_HEIGHT = 28  # Pixels per level


# Create GUI instances for levels 0-9
def make_gui(level):
    y_pos = BASE_Y + (level * LEVEL_HEIGHT)

    @imgui.open(y=y_pos, x=5)
    def gui(gui: imgui.GUI):
        if level in notifications:
            gui.text(notifications[level]["message"])

    return gui


# Create GUIs for levels 0-9
guis = {level: make_gui(level) for level in range(10)}


def auto_hide_level(level):
    """Automatically hide notification at specific level after timeout"""
    global notifications, auto_hide_jobs

    if level in notifications:
        timestamp = notifications[level]["timestamp"]
        duration = notifications[level]["duration"]

        if time.time() - timestamp >= duration:
            del notifications[level]
            guis[level].hide()

            if level in auto_hide_jobs:
                try:
                    cron.cancel(auto_hide_jobs[level])
                except:
                    pass
                del auto_hide_jobs[level]


@module.action_class
class Actions:
    def notify(message: str, level: int = 0, duration: int = 5):
        """Display a notification message at the specified level

        Args:
            message: The text to display (supports multiline with \\n)
            level: Which level to display at (0-9, each 70px apart)
            duration: How long to show in seconds (0 = no auto-hide)
        """
        global notifications, auto_hide_jobs

        if level < 0 or level > 9:
            raise ValueError(f"Level must be 0-9, got {level}")

        # Store notification
        notifications[level] = {
            "message": message,
            "timestamp": time.time(),
            "duration": duration
        }

        # Cancel any existing auto-hide job for this level
        if level in auto_hide_jobs:
            try:
                cron.cancel(auto_hide_jobs[level])
            except:
                pass

        # Set up auto-hide if duration > 0
        if duration > 0:
            auto_hide_jobs[level] = cron.interval("1s", lambda lvl=level: auto_hide_level(lvl))

        guis[level].show()

    def notify_hide(level: int = None):
        """Manually hide notification(s)

        Args:
            level: Specific level to hide (None = hide all)
        """
        global notifications, auto_hide_jobs

        if level is None:
            # Hide all notifications
            levels_to_hide = list(notifications.keys())
        else:
            levels_to_hide = [level] if level in notifications else []

        for lvl in levels_to_hide:
            if lvl in notifications:
                del notifications[lvl]

            if lvl in auto_hide_jobs:
                try:
                    cron.cancel(auto_hide_jobs[lvl])
                except:
                    pass
                del auto_hide_jobs[lvl]

            guis[lvl].hide()
