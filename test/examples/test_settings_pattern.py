"""Example: Testing settings-dependent plugins.

This demonstrates how to test code that reads Talon settings.
Pattern: Use the talon_settings fixture to set values before testing.

Applicable to: any plugin that reads user.* settings
"""

import talon

if hasattr(talon, "test_mode"):
    from talon import settings

    # --- Simulated production code ---

    def get_scroll_speed():
        """Get scroll speed from settings with a default."""
        return settings.get("user.scroll_speed", 5)

    def get_theme_colors():
        """Get theme colors, with fallback defaults."""
        bg = settings.get("user.theme_background", "000000ff")
        fg = settings.get("user.theme_foreground", "ffffffff")
        return {"background": bg, "foreground": fg}

    def is_feature_enabled(feature_name):
        """Check if a feature flag is enabled."""
        return settings.get(f"user.enable_{feature_name}", False)

    # --- Tests ---

    def setup_function():
        talon.Settings.reset()

    def teardown_function():
        talon.Settings.reset()

    def test_default_scroll_speed():
        assert get_scroll_speed() == 5

    def test_custom_scroll_speed():
        talon.Settings.set("user.scroll_speed", 10)
        assert get_scroll_speed() == 10

    def test_default_theme():
        colors = get_theme_colors()
        assert colors["background"] == "000000ff"
        assert colors["foreground"] == "ffffffff"

    def test_custom_theme():
        talon.Settings.set("user.theme_background", "1a1a1aff")
        talon.Settings.set("user.theme_foreground", "e0e0e0ff")
        colors = get_theme_colors()
        assert colors["background"] == "1a1a1aff"
        assert colors["foreground"] == "e0e0e0ff"

    def test_feature_flag_default_off():
        assert is_feature_enabled("experimental_grid") is False

    def test_feature_flag_enabled():
        talon.Settings.set("user.enable_experimental_grid", True)
        assert is_feature_enabled("experimental_grid") is True
