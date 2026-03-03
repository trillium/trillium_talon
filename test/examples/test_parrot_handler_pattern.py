"""Example: Testing parrot (noise detection) handlers.

This demonstrates how to test plugins that respond to mouth noises.
Pattern: Create a handler, wire it to a mock ParrotSystem, simulate noises.

Applicable to: pop-click, hiss-scroll, noise-triggered commands
"""

import talon

if hasattr(talon, "test_mode"):
    from unittest.mock import MagicMock

    from talon.experimental.parrot import ParrotDelegate, ParrotSystem

    # --- Simulated production code ---

    class PopClickHandler(ParrotDelegate):
        """Clicks on pop noise."""

        def __init__(self, click_fn):
            self.click_fn = click_fn
            self.pop_count = 0

        def on_noise(self, noise):
            if noise == "pop":
                self.pop_count += 1
                self.click_fn()

    class HissScrollHandler(ParrotDelegate):
        """Scrolls while hiss is active."""

        def __init__(self, scroll_fn):
            self.scroll_fn = scroll_fn
            self.hissing = False

        def on_noise(self, noise):
            if noise == "hiss_start":
                self.hissing = True
            elif noise == "hiss_stop":
                self.hissing = False

        def on_frame(self, frame):
            if self.hissing:
                self.scroll_fn(1)

    # --- Tests ---

    def test_pop_triggers_click():
        click = MagicMock()
        handler = PopClickHandler(click)

        system = ParrotSystem()
        system.set_delegate(handler)
        system.enable()

        system.simulate_noise("pop")

        click.assert_called_once()
        assert handler.pop_count == 1

    def test_pop_count_increments():
        click = MagicMock()
        handler = PopClickHandler(click)

        system = ParrotSystem()
        system.set_delegate(handler)
        system.enable()

        system.simulate_noise("pop")
        system.simulate_noise("pop")
        system.simulate_noise("pop")

        assert handler.pop_count == 3
        assert click.call_count == 3

    def test_non_pop_noise_ignored():
        click = MagicMock()
        handler = PopClickHandler(click)

        system = ParrotSystem()
        system.set_delegate(handler)
        system.enable()

        system.simulate_noise("hiss")
        system.simulate_noise("shush")

        click.assert_not_called()

    def test_disabled_system_ignores_noise():
        click = MagicMock()
        handler = PopClickHandler(click)

        system = ParrotSystem()
        system.set_delegate(handler)
        # Not enabled

        system.simulate_noise("pop")

        click.assert_not_called()

    def test_hiss_scroll_start_stop():
        scroll = MagicMock()
        handler = HissScrollHandler(scroll)

        system = ParrotSystem()
        system.set_delegate(handler)
        system.enable()

        # Before hiss — frame does nothing
        system.simulate_frame()
        scroll.assert_not_called()

        # Start hissing
        system.simulate_noise("hiss_start")
        system.simulate_frame()
        scroll.assert_called_once_with(1)

        # Stop hissing
        system.simulate_noise("hiss_stop")
        scroll.reset_mock()
        system.simulate_frame()
        scroll.assert_not_called()
