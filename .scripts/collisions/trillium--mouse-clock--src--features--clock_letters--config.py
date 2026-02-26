"""
Clock letters overlay configuration.

Gets active letters and colors from mode config.
"""

from typing import List
from ...core.config import get_mode_config, get_setting
from ...core.constants import DEFAULT_TEXT_COLOR, DEFAULT_TEXT_BG_COLOR


def get_text_color() -> str:
    """Get the text color for clock letter labels."""
    return get_setting("clock_letters_text_color", DEFAULT_TEXT_COLOR)


def get_text_bg_color() -> str:
    """Get the background color for clock letter labels."""
    return get_setting("clock_letters_text_bg_color", DEFAULT_TEXT_BG_COLOR)


def get_clock_letters_colors() -> List[str]:
    """Get the list of active colors (columns)."""
    return get_mode_config("clock_letters", "colors")


def get_clock_letters_letters() -> List[str]:
    """Get the list of active letters (rows)."""
    return get_mode_config("clock_letters", "letters")
