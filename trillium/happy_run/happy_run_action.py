# happy_run_action.py - Talon action that orchestrates the full sequence
#
# Pipeline: launch → wait → inject → wait → inject
#
# Step 1: snapshot + launch new terminal window
# Step 2: poll for new window to appear (window_tracker)
# Step 3: record title changes (readiness_poller) to observe state transitions
# Step 4: (future) inject "happy" once shell ready
# Step 5: (future) poll for ✳ marker, then inject prompt

import os

from talon import Module, actions, clip, cron, ui

from .window_tracker import snapshot_windows, poll_for_new_window
from .readiness_poller import record_titles, poll_for_stability, poll_for_marker, HAPPY_MARKER

TERMINAL_BUNDLE = "com.apple.Terminal"

mod = Module()


def _inject_text(text, app, window):
    """Focus window and type text + enter"""
    actions.user.switcher_focus_window(window)
    actions.insert(text)
    actions.key("enter")


def _inject_prompt(text, app, window):
    """Focus window, paste prompt from clipboard, submit (enter twice for happy)"""
    actions.user.switcher_focus_window(window)
    old_clip = clip.text()
    clip.set_text(text)
    actions.key("cmd-v")
    actions.sleep("200ms")
    actions.key("enter")
    actions.sleep("200ms")
    actions.key("enter")
    clip.set_text(old_clip)


def _close_window(app, window):
    """Focus window, cmd-w, confirm modal with enter"""
    actions.user.switcher_focus_window(window)
    actions.key("cmd-w")
    actions.sleep("200ms")
    actions.key("enter")


@mod.action_class
class Actions:
    def happy_launch_and_record():
        """Launch a new terminal window and record its title changes"""
        windows_before = snapshot_windows(TERMINAL_BUNDLE)
        actions.user.terminal_new_window()
        poll_for_new_window(
            TERMINAL_BUNDLE,
            windows_before,
            lambda app, window: record_titles(app, window),
        )

    def happy_launch_and_inject():
        """Launch a new terminal, wait for shell ready, then type 'happy --yolo'"""
        windows_before = snapshot_windows(TERMINAL_BUNDLE)
        actions.user.terminal_new_window()
        poll_for_new_window(
            TERMINAL_BUNDLE,
            windows_before,
            lambda app, window: poll_for_stability(
                app, window, lambda a, w: _inject_text("happy --yolo", a, w)
            ),
        )

    def happy_launch_prompt_and_close():
        """Full lifecycle: launch → happy → prompt → 2s → close"""
        actions.user.happy_run_full("/tmp", "please just chill for a minute, gonna close you", close_after_s=2)

    def happy_run_full(directory: str, prompt: str, close_after_s: int = 0):
        """Launch happy in a directory, inject prompt, optionally close after N seconds"""
        windows_before = snapshot_windows(TERMINAL_BUNDLE)
        actions.user.terminal_new_window()

        # Use directory basename as the recall signature
        recall_name = f"happy-{os.path.basename(directory)}"

        def on_new_window(app, window):
            # Save to recall with directory-based name
            actions.user.switcher_focus_window(window)
            actions.user.save_window(recall_name)

            def on_shell_ready(app, window):
                _inject_text(f'cd "{directory}" && happy --yolo', app, window)

                def on_happy_ready(app, window):
                    # Re-focus before prompt injection
                    actions.user.recall_window(recall_name)
                    actions.sleep("200ms")
                    _inject_prompt(prompt, app, window)
                    if close_after_s > 0:
                        cron.after(f"{close_after_s}s", lambda: _close_window(app, window))

                poll_for_marker(app, window, HAPPY_MARKER, on_happy_ready)

            poll_for_stability(app, window, on_shell_ready)

        poll_for_new_window(
            TERMINAL_BUNDLE,
            windows_before,
            on_new_window,
        )

    def happy_close(directory: str):
        """Close a happy window by directory name. Any process can call this."""
        recall_name = f"happy-{os.path.basename(directory)}"
        actions.user.recall_window(recall_name)
        actions.sleep("200ms")
        actions.key("cmd-w")
        actions.sleep("200ms")
        actions.key("enter")
        actions.user.forget_window(recall_name)
