"""
Animation and timing utilities for smooth radius transitions.

Provides exponential acceleration for radius control (voice widen/narrow).
"""

import time
from typing import Optional


def exponential_lerp_factor(
    elapsed_seconds: float,
    base: float = 0.08,
    max_factor: float = 0.98,
    ramp_time: float = 1.5,
    exponent: float = 4.0
) -> float:
    """
    Calculate an accelerating lerp factor based on elapsed time.

    Starts slow for fine control, accelerates for rapid large movements.

    Args:
        elapsed_seconds: How long the sound has been active
        base: Starting lerp factor (slow, precise)
        max_factor: Maximum lerp factor (fast)
        ramp_time: Seconds to reach max acceleration
        exponent: Curve steepness (2.0 = quadratic, 3.0 = cubic, 4.0 = quartic)

    Returns:
        Lerp factor between base and max_factor
    """
    # Normalize time to 0-1 range over ramp_time
    t = min(elapsed_seconds / ramp_time, 1.0)

    # Apply exponential curve
    curve = t ** exponent

    # Interpolate between base and max
    return base + (max_factor - base) * curve


class RadiusAnimator:
    """
    Manages smooth radius animation with exponential acceleration.

    Tracks timing for radius changes and provides accelerating
    increment and lerp values.
    """

    # Configuration - can be tuned
    BASE_INCREMENT = 5          # Starting pixels per event (was 3)
    MAX_MULTIPLIER = 50         # Maximum multiplier (2 * 25 = 50px max, was 150)
    RAMP_TIME = 1.5             # Seconds to reach max acceleration
    GAP_THRESHOLD = 0.08          # Seconds of silence before resetting (80ms ~2 missed events)

    # Caps - set to None for no limit
    MAX_RADIUS = None               # Maximum radius allowed (e.g., 1000)
    MIN_RADIUS = 20                 # Minimum radius allowed
    MAX_INCREMENT_PER_EVENT = 40    # Cap per-event increment
    MAX_LERP_FACTOR = .1          # Cap lerp speed (e.g., 0.5)

    def __init__(self):
        self._animation_start_time: Optional[float] = None
        self._last_input_time: Optional[float] = None

    def update_timing(self) -> bool:
        """
        Update animation timing on each input event.

        Resets acceleration if there's been a gap in input.

        Returns:
            True if a gap was detected and timer was reset, False otherwise
        """
        now = time.time()
        # If gap since last input exceeds threshold, reset acceleration
        gap_detected = self._last_input_time is None or (now - self._last_input_time) > self.GAP_THRESHOLD
        if gap_detected:
            self._animation_start_time = now
        self._last_input_time = now
        return gap_detected

    def get_elapsed(self) -> float:
        """Get elapsed time since animation started."""
        if self._animation_start_time is None:
            return 0.0
        return time.time() - self._animation_start_time

    def get_dynamic_increment(self) -> float:
        """
        Get radius increment that accelerates over time.

        Returns small increment at start for precision,
        large increment after sustained input for speed.
        """
        if self._animation_start_time is None:
            return self.BASE_INCREMENT

        elapsed = self.get_elapsed()
        # Normalize to 0-1 over ramp time
        t = min(elapsed / self.RAMP_TIME, 1.0)
        # Quartic curve (t^4) - stays flat then explodes
        curve = t ** 4
        multiplier = 1 + (self.MAX_MULTIPLIER - 1) * curve
        increment = self.BASE_INCREMENT * multiplier

        # Apply cap if set
        if self.MAX_INCREMENT_PER_EVENT is not None:
            increment = min(increment, self.MAX_INCREMENT_PER_EVENT)

        return int(increment)

    def get_lerp_factor(self) -> float:
        """
        Get lerp factor for interpolating radius toward target.

        Accelerates over time for snappier response during sustained input.
        """
        if self._animation_start_time is None:
            lerp = 0.15  # Fallback base
        else:
            lerp = exponential_lerp_factor(self.get_elapsed())

        # Apply cap if set
        if self.MAX_LERP_FACTOR is not None:
            lerp = min(lerp, self.MAX_LERP_FACTOR)

        return lerp

    def clamp_radius(self, radius: float) -> float:
        """Clamp radius within allowed bounds."""
        if self.MAX_RADIUS is not None:
            radius = min(radius, self.MAX_RADIUS)
        radius = max(radius, self.MIN_RADIUS)
        return radius

    def reset(self):
        """Reset animation state."""
        self._animation_start_time = None
        self._last_input_time = None
