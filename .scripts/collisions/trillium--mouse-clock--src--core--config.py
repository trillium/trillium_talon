"""
Settings management for the mouse clock system.

JSON I/O, get/set/reset, active accessors, and per-mode configuration.
Pure constants live in constants.py and are re-exported here.
"""

from .constants import *  # noqa: F401,F403 — re-export all constants

# =============================================================================
# Settings Management
# =============================================================================

import json
from typing import Any, Dict, Optional
from pathlib import Path

# Default settings file path (in the mouse-clock directory)
_SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

# All available line styles
# Disabled: morse, barb, spike, saw (asymmetric), zig, wave
ALL_LINE_STYLES = [
    "solid", "dash", "dot", "tick", "blip", "long",
]

# All available color names (excluding "center" which is a special position)
ALL_COLORS = list(DISPLAY_COLORS)

# All available letters (full alphabet for clock_letters mode)
ALL_LETTERS = list("abcdefghijklmnopqrstuvwxyz")

# Default settings registry
_DEFAULTS: Dict[str, Any] = {
    "default_radius": DEFAULT_RADIUS,
    "min_radius": MIN_RADIUS,
    "debounce_interval_ms": 150,
    "line_thickness": DEFAULT_STROKE_WIDTH,
    "dot_radius": DEFAULT_DOT_RADIUS,
    "active_colors": list(ALL_COLORS),
    "active_styles": list(ALL_LINE_STYLES),
    "active_letters": list(ALL_LETTERS),
}

# Runtime settings (can be modified)
_settings: Dict[str, Any] = _DEFAULTS.copy()

# Setting change listeners: {name: [callback, ...]}
_listeners: Dict[str, list] = {}


def on_setting_change(name: str, callback):
    """Register a callback for when a specific setting changes. callback(new_value)."""
    _listeners.setdefault(name, []).append(callback)


def _notify_listeners(name: str, value: Any):
    """Notify listeners for a setting change."""
    for cb in _listeners.get(name, []):
        cb(value)


def get_setting(name: str, default: Any = None) -> Any:
    """
    Retrieve a setting value.

    Args:
        name: Setting name
        default: Fallback if setting not found

    Returns:
        Setting value or default
    """
    if name in _settings:
        return _settings[name]
    if name in _DEFAULTS:
        return _DEFAULTS[name]
    return default


def set_setting(name: str, value: Any, persist: bool = False):
    """
    Update a setting at runtime.

    Args:
        name: Setting name
        value: New value
        persist: If True, save settings to disk after updating
    """
    old = _settings.get(name)
    _settings[name] = value
    if persist:
        _auto_save()
    if value != old:
        _notify_listeners(name, value)


def reset_setting(name: str):
    """
    Restore a setting to its default value.

    Args:
        name: Setting name
    """
    if name in _DEFAULTS:
        _settings[name] = _DEFAULTS[name]
    elif name in _settings:
        del _settings[name]


def reset_all_settings():
    """Restore all settings to defaults."""
    _settings.clear()
    _settings.update(_DEFAULTS)


def get_all_settings() -> Dict[str, Any]:
    """Get copy of all current settings."""
    return _settings.copy()


def load_settings(file_path: str) -> bool:
    """
    Load settings from JSON file.

    Args:
        file_path: Path to settings file

    Returns:
        True if loaded successfully, False otherwise
    """
    try:
        path = Path(file_path)
        if path.exists():
            with open(path, 'r') as f:
                loaded = json.load(f)
                _settings.update(loaded)
            return True
    except Exception as e:
        print(f"mouse-clock: failed to load settings from {file_path}: {e}")
    return False


def save_settings(file_path: str) -> bool:
    """
    Persist current settings to JSON file.

    Args:
        file_path: Path to settings file

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(_settings, f, indent=2)
        return True
    except Exception as e:
        print(f"mouse-clock: failed to save settings to {file_path}: {e}")
    return False


def _auto_save():
    """Save settings to the default file (called after mode config changes)."""
    save_settings(str(_SETTINGS_FILE))


def load_default_settings() -> bool:
    """Load settings from the default file on startup."""
    return load_settings(str(_SETTINGS_FILE))


# Auto-load settings when this module is first imported by Talon
if load_default_settings():
    print("mouse-clock: loaded settings from settings.json")


# =============================================================================
# Active Configuration Accessors
# =============================================================================

def get_active_colors() -> list:
    """Get the list of currently active color names."""
    return get_setting("active_colors", ALL_COLORS)


def get_active_styles() -> list:
    """Get the list of currently active line style names."""
    return get_setting("active_styles", ALL_LINE_STYLES)


def get_active_letters() -> list:
    """Get the list of currently active letters."""
    return get_setting("active_letters", ALL_LETTERS)


# =============================================================================
# Per-Display-Mode Configuration
# =============================================================================

CONFIGURABLE_MODES = ["circles", "clock_letters"]

# Map dimension names to their global getter and validation set
_DIMENSION_INFO = {
    "colors": {"global_key": "active_colors", "all_items": ALL_COLORS},
    "styles": {"global_key": "active_styles", "all_items": ALL_LINE_STYLES},
    "horizontal_styles": {"global_key": "active_styles", "all_items": ALL_LINE_STYLES},
    "vertical_styles": {"global_key": "active_styles", "all_items": ALL_LINE_STYLES},
    "letters": {"global_key": "active_letters", "all_items": ALL_LETTERS},
}


def _mode_key(mode: str, dimension: str) -> str:
    """Build the settings key for a per-mode dimension."""
    return f"{mode}_active_{dimension}"


def get_mode_config(mode: str, dimension: str) -> list:
    """Get the active items for a mode+dimension, falling back to global.

    Args:
        mode: One of CONFIGURABLE_MODES
        dimension: "colors", "styles", or "letters"

    Returns:
        List of active items for this mode, or the global list if no override.
    """
    key = _mode_key(mode, dimension)
    per_mode = get_setting(key)
    if per_mode is not None:
        return list(per_mode)
    info = _DIMENSION_INFO.get(dimension)
    if info:
        return list(get_setting(info["global_key"], info["all_items"]))
    return []


def set_mode_config(mode: str, dimension: str, items: list):
    """Set the full list of active items for a mode+dimension.

    Args:
        mode: One of CONFIGURABLE_MODES
        dimension: "colors", "styles", or "letters"
        items: The new list of items
    """
    set_setting(_mode_key(mode, dimension), list(items))
    _auto_save()


def add_mode_item(mode: str, dimension: str, item: str) -> bool:
    """Add an item to a mode's dimension list (copy-on-write from global).

    Validates against the full set of allowed items for this dimension.

    Args:
        mode: One of CONFIGURABLE_MODES
        dimension: "colors", "styles", or "letters"
        item: Item to add

    Returns:
        True if added, False if invalid or already present.
    """
    info = _DIMENSION_INFO.get(dimension)
    if not info or item not in info["all_items"]:
        return False
    current = get_mode_config(mode, dimension)
    if item in current:
        return False
    current.append(item)
    set_mode_config(mode, dimension, current)
    return True


def remove_mode_item(mode: str, dimension: str, item: str) -> bool:
    """Remove an item from a mode's dimension list (copy-on-write from global).

    Args:
        mode: One of CONFIGURABLE_MODES
        dimension: "colors", "styles", or "letters"
        item: Item to remove

    Returns:
        True if removed, False if not present.
    """
    current = get_mode_config(mode, dimension)
    if item not in current:
        return False
    current.remove(item)
    set_mode_config(mode, dimension, current)
    return True


def reset_mode_config(mode: str, dimension: str):
    """Delete the per-mode override, restoring fallback to global.

    Args:
        mode: One of CONFIGURABLE_MODES
        dimension: "colors", "styles", or "letters"
    """
    key = _mode_key(mode, dimension)
    if key in _settings:
        del _settings[key]
        _auto_save()


