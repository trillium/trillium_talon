"""
Clock notation conversions for the mouse clock system.

Functions for converting between letters (A-L) and positions/angles.
"""


def letter_to_position(letter: str) -> int:
    """
    Return the position of a letter in the alphabet (1-indexed).

    Args:
        letter: A letter A-Z (case insensitive)

    Returns:
        Position number (A=1, B=2, ..., Z=26)
    """
    return ord(letter.upper()) - ord("A") + 1


def letter_to_clock_angle(letter_position: int) -> float:
    """
    Given a letter position (1-12 for A-L), return the corresponding clock angle in degrees.

    Args:
        letter_position: Position of letter (1=A at 12 o'clock, 2=B, ..., 12=L)

    Returns:
        Angle in degrees (0° = 3 o'clock, 90° = 6 o'clock, -90° = 12 o'clock)

    Examples:
        1 (A) at 12 o'clock -> 30° (after modulo)
        4 (D) at 3 o'clock  -> 120° (after modulo)
    """
    return (30 * letter_position) % 360
