"""Example: Testing voice command actions.

This demonstrates how to test action classes that define voice command behavior.
Pattern: Register dependencies as test actions, then call the action under test.

Applicable to: any plugin that defines voice commands via Module.action_class
"""

import talon

if hasattr(talon, "test_mode"):
    from unittest.mock import MagicMock

    from talon import Module, actions

    # --- Simulated production code ---
    # (In real tests, you'd import this from your plugin module)

    mod = Module()

    @mod.action_class
    class ExampleActions:
        def greet(name: str) -> str:
            """Say hello to someone."""
            return f"Hello, {name}!"

        def greet_twice(name: str) -> str:
            """Say hello twice."""
            first = actions.user.greet(name)
            return f"{first} {first}"

    # --- Tests ---

    def setup_function():
        actions.reset_test_actions()

    def test_simple_action():
        """Test a standalone action with no dependencies."""
        result = actions.user.greet("World")
        assert result == "Hello, World!"

    def test_action_calling_other_action():
        """Test an action that calls other actions."""
        result = actions.user.greet_twice("Talon")
        assert result == "Hello, Talon! Hello, Talon!"

    def test_mock_dependency():
        """Test by replacing a dependency action with a mock."""
        mock_greet = MagicMock(return_value="Hi!")
        actions.register_test_action("user", "greet", mock_greet)

        result = actions.user.greet_twice("Test")

        mock_greet.assert_called_with("Test")
        assert result == "Hi! Hi!"

    def test_action_not_found_raises():
        """Verify that calling a non-existent action raises."""
        import pytest

        with pytest.raises(AttributeError, match="Couldn't find action"):
            actions.user.nonexistent_action()
