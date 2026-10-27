"""Tests for click_to_finish pondering mode restoration.

Pondering is entered from either command mode (voice "pondering") or from
Talon sleep (via repeater's sleep sounds). On exit the mode must return to
whatever it was BEFORE entry — sleep stays sleep, command mode stays command
mode — not unconditionally bounce back to command mode.
"""

import talon

if hasattr(talon, "test_mode"):
    from unittest.mock import MagicMock

    import pytest

    from trillium.core import click_to_finish

    def _install_harness(talon_actions):
        """Register the stub actions click_to_finish calls, return the mocks."""
        speech_disable = MagicMock()
        speech_enable = MagicMock()
        command_mode = MagicMock()
        noop = MagicMock()

        talon_actions.register_test_action("speech", "disable", speech_disable)
        talon_actions.register_test_action("speech", "enable", speech_enable)
        talon_actions.register_test_action("user", "command_mode", command_mode)
        for name in (
            "mode_indicator_set_color",
            "mode_indicator_set_pondering",
            "mode_indicator_clear_pondering",
            "mode_indicator_clear_color",
        ):
            talon_actions.register_test_action("user", name, noop)

        return {
            "speech_disable": speech_disable,
            "speech_enable": speech_enable,
            "command_mode": command_mode,
        }

    @pytest.fixture
    def pondering_harness(talon_actions):
        mocks = _install_harness(talon_actions)
        talon.scope.reset()
        yield mocks
        talon.scope.reset()
        click_to_finish.enabled = False
        click_to_finish._entered_from_sleep = False
        click_to_finish.toggle_ctx.tags = []

    def test_exit_from_command_mode_returns_to_command(talon_actions, pondering_harness):
        talon.scope.update({"mode": {"command"}})

        click_to_finish.enable()
        pondering_harness["speech_disable"].reset_mock()
        click_to_finish.disable()

        pondering_harness["speech_enable"].assert_called_once()
        pondering_harness["command_mode"].assert_called_once()
        pondering_harness["speech_disable"].assert_not_called()

    def test_exit_from_sleep_returns_to_sleep(talon_actions, pondering_harness):
        talon.scope.update({"mode": {"sleep"}})

        click_to_finish.enable()
        pondering_harness["speech_disable"].reset_mock()
        click_to_finish.disable()

        pondering_harness["speech_enable"].assert_called_once()
        pondering_harness["speech_disable"].assert_called_once()
        pondering_harness["command_mode"].assert_not_called()

    def test_disable_resets_return_to_sleep_state(pondering_harness):
        """After an exit, the next entry re-captures the mode (no stale state)."""
        talon.scope.update({"mode": {"sleep"}})
        click_to_finish.enable()
        click_to_finish.disable()
        assert click_to_finish._entered_from_sleep is False

    # --- pop-submit grace: a stray command must not wipe the armed Enter ---

    def _stray_command(talon_actions, monkeypatch, trigger="nuke left"):
        from trillium.plugin.repeater import repeater

        cmd = MagicMock()
        cmd.trigger = trigger
        talon_actions.register_test_action(
            "core", "last_command", lambda: (cmd, None)
        )
        monkeypatch.setattr(repeater, "should_track_command", lambda t: True)
        monkeypatch.setattr(
            repeater, "update_mode_indicator_with_last_command", lambda *a: None
        )
        talon.scope.update({"mode": {"command"}})
        repeater.on_post_phrase(None)
        return repeater

    @pytest.fixture
    def armed_after_finish(talon_actions, pondering_harness):
        talon_actions.user.clear_repeat_overrides()
        talon_actions.register_test_action("user", "boolean_print", MagicMock())
        talon_actions.register_test_action("user", "set_next_opposite_action", MagicMock())
        talon_actions.register_test_action("speech", "enable", MagicMock())
        talon_actions.register_test_action("key", "", MagicMock())
        click_to_finish._submit_and_exit()
        yield
        click_to_finish._finish_at = None
        talon_actions.user.clear_repeat_overrides()

    def test_stray_command_inside_grace_keeps_submit_armed(
        talon_actions, armed_after_finish, monkeypatch
    ):
        repeater = _stray_command(talon_actions, monkeypatch)
        assert repeater.override_repeat_action == ("user", "click_submit_now", ())

    def test_stray_command_after_grace_clears_submit(
        talon_actions, armed_after_finish, monkeypatch
    ):
        click_to_finish._finish_at -= click_to_finish.FINISH_GRACE_S + 0.1
        repeater = _stray_command(talon_actions, monkeypatch)
        assert repeater.override_repeat_action is None
