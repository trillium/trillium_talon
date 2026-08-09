"""Shared pytest fixtures for Talon plugin testing.

These fixtures provide common test setup patterns for:
- Action registration and cleanup
- Canvas/drawing testing
- Settings management
- Screen/window geometry
- Parrot noise simulation

Usage in tests:
    def test_my_feature(talon_actions, mock_canvas):
        talon_actions.register("user", "my_action", lambda: "result")
        # ... test code ...
"""

import pytest


@pytest.fixture
def talon_actions():
    """Provide a clean action registry for each test.

    Actions registered via this fixture are automatically cleaned up.
    Module-level actions (from imported talon code) persist.

    Usage:
        def test_foo(talon_actions):
            talon_actions.register("user", "do_thing", mock_fn)
            result = talon.actions.user.do_thing()
    """
    import talon

    talon.actions.reset_test_actions()
    yield talon.actions
    talon.actions.reset_test_actions()


@pytest.fixture
def talon_settings():
    """Provide clean settings for each test.

    Usage:
        def test_foo(talon_settings):
            talon_settings.set("user.my_setting", 42)
            assert talon.settings.get("user.my_setting") == 42
    """
    import talon

    talon.Settings.reset()
    yield talon.settings
    talon.Settings.reset()


@pytest.fixture
def mock_canvas():
    """Provide a mock Skia canvas that records draw operations.

    Usage:
        def test_drawing(mock_canvas):
            my_draw_function(mock_canvas)
            assert len(mock_canvas.circles()) == 3
            assert mock_canvas.texts()[0][3] == "Hello"
    """
    from talon.skia.canvas import Canvas

    return Canvas()


@pytest.fixture
def mock_paint():
    """Provide a fresh Skia Paint object.

    Usage:
        def test_paint(mock_paint):
            mock_paint.color = "ff0000ff"
            mock_paint.style = mock_paint.Style.STROKE
    """
    from talon.skia import Paint

    return Paint()


@pytest.fixture
def screen_rect():
    """Standard 1920x1080 screen rectangle."""
    return (0, 0, 1920, 1080)


@pytest.fixture
def mock_screen():
    """Provide a mock Screen object.

    Usage:
        def test_overlay(mock_screen):
            canvas = Canvas.from_screen(mock_screen)
    """
    from talon.screen import Screen

    return Screen(0, 0, 1920, 1080)


@pytest.fixture
def talon_cron():
    """Provide clean cron (timer) state for each test.

    Usage:
        def test_timer(talon_cron):
            job = talon_cron.interval("500ms", my_callback)
            talon_cron.trigger(job)  # fire it manually
    """
    import talon

    talon.Cron.reset()
    yield talon.cron
    talon.Cron.reset()


@pytest.fixture
def talon_clip():
    """Provide clean clipboard state for each test.

    Usage:
        def test_clipboard(talon_clip):
            talon_clip.set_text("hello")
            assert talon_clip.text() == "hello"
    """
    import talon

    talon.Clip.clear()
    yield talon.clip
    talon.Clip.clear()


@pytest.fixture
def talon_noise():
    """Provide clean noise detection state.

    Usage:
        def test_hiss(talon_noise):
            callback = Mock()
            talon_noise.register("hiss", callback)
            talon_noise.simulate("hiss")
            callback.assert_called_once()
    """
    import talon

    talon.Noise.reset()
    yield talon.noise
    talon.Noise.reset()


@pytest.fixture
def parrot_system():
    """Provide a ParrotSystem for testing noise handlers.

    Usage:
        def test_parrot(parrot_system):
            handler = MyParrotHandler()
            parrot_system.set_delegate(handler)
            parrot_system.enable()
            parrot_system.simulate_noise("pop")
    """
    from talon.experimental.parrot import ParrotSystem

    return ParrotSystem()
