"""Tests for sleep-mode repeater override consumption.

`repeater_sleep_repeat` / `repeater_sleep_opposite` are bound from
`repeater_sleep.talon` while Talon is asleep. Unlike the command-mode
handlers, they MUST never fall back to the last command. Repeat only fires
when an override is armed (the ones click_to_finish.py lines up with
`set_next_repeat_action` / `set_next_opposite_action`). Opposite fires the
armed override when present; otherwise the reverse sound is reserved for
re-launching pondering (LINE_ENDER_REVERSE_ACTION) so the hands-free loop
stays live.
"""

import talon

if hasattr(talon, "test_mode"):
    from unittest.mock import MagicMock

    import pytest

    from trillium.plugin.repeater import repeater
    from trillium._boolean_print import boolean_print

    @pytest.fixture(autouse=True)
    def _clean_overrides(talon_actions):
        talon_actions.user.clear_repeat_overrides()
        yield

    def _arm_repeat(talon_actions, action="click_submit_now", debounce_s=0.0):
        talon_actions.user.set_next_repeat_action(
            "user", action, [], debounce_s=debounce_s
        )

    def _arm_opposite(talon_actions, action="pondering_enable", debounce_s=0.0):
        talon_actions.user.set_next_opposite_action(
            "user", action, [], debounce_s=debounce_s
        )

    def test_sleep_repeat_consumes_armed_override(talon_actions):
        submit = MagicMock()
        talon_actions.register_test_action("user", "click_submit_now", submit)
        _arm_repeat(talon_actions)

        talon_actions.user.repeater_sleep_repeat()

        submit.assert_called_once_with()

    def test_sleep_opposite_consumes_armed_override(talon_actions):
        enable = MagicMock()
        talon_actions.register_test_action("user", "pondering_enable", enable)
        _arm_opposite(talon_actions)

        talon_actions.user.repeater_sleep_opposite()

        enable.assert_called_once_with()

    def test_sleep_repeat_without_override_is_noop(talon_actions):
        submit = MagicMock()
        talon_actions.register_test_action("user", "click_submit_now", submit)

        talon_actions.user.repeater_sleep_repeat()

        submit.assert_not_called()

    def test_sleep_opposite_without_override_relaunches_pondering(talon_actions):
        """No override armed -> the reverse sound re-launches pondering."""
        enable = MagicMock()
        talon_actions.register_test_action("user", "pondering_enable", enable)

        talon_actions.user.repeater_sleep_opposite()

        enable.assert_called_once_with()

    def test_sleep_opposite_without_override_ignores_stored_command(talon_actions):
        """Relaunch pondering even if a repeatable command is stored — cmere
        never executes the last command's opposite from sleep."""
        enable = MagicMock()
        talon_actions.register_test_action("user", "pondering_enable", enable)
        repeater.last_repeatable_cmd = MagicMock()

        talon_actions.user.repeater_sleep_opposite()

        enable.assert_called_once_with()

    def test_sleep_repeat_does_not_fall_back_to_last_command(talon_actions):
        """Even with a prior repeatable stored, no override means no action."""
        submit = MagicMock()
        talon_actions.register_test_action("user", "click_submit_now", submit)
        repeater.last_repeatable_cmd = MagicMock()

        talon_actions.user.repeater_sleep_repeat()

        submit.assert_not_called()

    def test_sleep_override_persists_across_consumptions(talon_actions):
        """Overrides stay armed after consumption (cleared only on a new command)."""
        submit = MagicMock()
        talon_actions.register_test_action("user", "click_submit_now", submit)
        _arm_repeat(talon_actions)

        talon_actions.user.repeater_sleep_repeat()
        talon_actions.user.repeater_sleep_repeat()

        assert submit.call_count == 2

    def test_sleep_repeat_respects_debounce(talon_actions):
        submit = MagicMock()
        talon_actions.register_test_action("user", "click_submit_now", submit)
        _arm_repeat(talon_actions, debounce_s=60.0)

        talon_actions.user.repeater_sleep_repeat()
        talon_actions.user.repeater_sleep_repeat()

        submit.assert_called_once_with()

    def test_command_mode_repeat_uses_same_override(talon_actions):
        """Shared helper: repeat_last_repeatable consumes the same armed override."""
        submit = MagicMock()
        talon_actions.register_test_action("user", "click_submit_now", submit)
        _arm_repeat(talon_actions)

        repeater.repeat_last_repeatable()

        submit.assert_called_once_with()

    def test_command_mode_opposite_no_mapping_relaunches_pondering(talon_actions):
        """A command with no OPPOSITES entry -> cmere re-launches pondering."""
        enable = MagicMock()
        talon_actions.register_test_action("user", "pondering_enable", enable)
        repeater.last_repeatable_cmd = MagicMock()
        repeater.last_repeatable_cmd.trigger = "some_unmapped_command"

        repeater.opposite()

        enable.assert_called_once_with()

    def test_sleep_actions_dispatch_by_sound(talon_actions):
        """Repeat vs opposite are independent slots — cmere must not consume the
        repeat override; with no opposite armed it re-launches pondering."""
        submit = MagicMock()
        enable = MagicMock()
        talon_actions.register_test_action("user", "click_submit_now", submit)
        talon_actions.register_test_action("user", "pondering_enable", enable)
        _arm_repeat(talon_actions)

        talon_actions.user.repeater_sleep_opposite()
        talon_actions.user.repeater_sleep_repeat()

        submit.assert_called_once_with()
        enable.assert_called_once_with()
