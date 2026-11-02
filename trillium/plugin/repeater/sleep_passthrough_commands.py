"""Sleep-mode passthrough commands that arm the tongue-click to repeat them.

The sleep-mode tongue-click (`repeater_sleep_repeat`) only ever fires an ARMED
repeat override — it deliberately never falls back to the last spoken command
while Talon is asleep (see repeater.py). Sleep-mode commands are also not tracked
by `on_post_phrase` (it skips non command/dictation modes), so they can't arm
themselves implicitly.

So each of the sleep passthrough commands (escape / destroy / nuke left) wraps
its action here and arms itself as the repeat override. After saying one of them,
a tongue-click replays it (and re-arms, so repeated clucks keep repeating it),
without waking Talon. Arming from Python mirrors how gaze_ocr_choice.py and
click_to_finish.py arm their overrides — talonscript can't pass the `list` arg
that `set_next_repeat_action` needs, and `escape` is a raw key press with no
`user.` action to arm directly.
"""

from talon import Module, actions

mod = Module()


@mod.action_class
class Actions:
    def sleep_cmd_escape():
        """Sleep-mode escape: press escape, arm the tongue-click to repeat it."""
        actions.key("escape")
        actions.user.set_next_repeat_action("user", "sleep_cmd_escape", [])

    def sleep_cmd_destroy():
        """Sleep-mode destroy: clear last dictation, arm the tongue-click to repeat it."""
        actions.user.clear_last_dictation()
        actions.user.set_next_repeat_action("user", "sleep_cmd_destroy", [])

    def sleep_cmd_nuke_left():
        """Sleep-mode nuke-left: nuke left of cursor, arm the tongue-click to repeat it."""
        actions.user.nuke_left()
        actions.user.set_next_repeat_action("user", "sleep_cmd_nuke_left", [])

    def sleep_cmd_slide_next():
        """Sleep-mode slide next: advance the slide, arm tongue-click to repeat it and kitty-cmere to go back."""
        actions.user.slide_next()
        actions.user.set_next_repeat_action("user", "slide_next", [])
        actions.user.set_next_opposite_action("user", "slide_previous", [])

    def sleep_cmd_slide_previous():
        """Sleep-mode slide previous: go back a slide, arm tongue-click to repeat it and kitty-cmere to advance."""
        actions.user.slide_previous()
        actions.user.set_next_repeat_action("user", "slide_previous", [])
        actions.user.set_next_opposite_action("user", "slide_next", [])
