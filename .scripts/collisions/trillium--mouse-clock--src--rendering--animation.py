"""
Animation utilities for canvas overlays.

Provides fade in/out and other animation effects.
"""

import time
from talon import cron
from typing import Callable, Optional


class FadeAnimator:
    """Handles fade in/out animations for a canvas."""

    def __init__(self, on_update: Callable[[int], None], on_complete: Optional[Callable[[], None]] = None, frame_interval_ms: int = 16):
        """
        Initialize fade animator.

        Args:
            on_update: Callback called with current alpha (0-255) each frame
            on_complete: Optional callback when animation completes
            frame_interval_ms: Milliseconds between frames (default 16 ≈ 60fps)
        """
        self.on_update = on_update
        self.on_complete_callback = on_complete
        self.frame_interval_ms = frame_interval_ms
        self.alpha = 0
        self._job = None
        self._delay_job = None
        self._start_time = None
        self._start_alpha = 0
        self._target_alpha = 255
        self._duration_ms = 300
        self._pulsing = False
        self._pulse_min = 80
        self._pulse_max = 255
        self._pulse_duration = 500

    def fade_in(self, duration_ms: int = 200, on_complete: Optional[Callable[[], None]] = None):
        """Fade in from current alpha to fully opaque."""
        self._animate(target=255, duration=duration_ms, on_complete=on_complete)

    def fade_out(self, duration_ms: int = 200, on_complete: Optional[Callable[[], None]] = None):
        """Fade out from current alpha to fully transparent."""
        self._animate(target=0, duration=duration_ms, on_complete=on_complete)

    def pulse(self, min_alpha: int = 80, max_alpha: int = 255, fade_out_ms: int = 500, fade_in_ms: int = 500, delay_at_min_ms: int = 0):
        """
        Start continuous pulsing between min and max alpha.

        Args:
            min_alpha: Minimum alpha (0-255)
            max_alpha: Maximum alpha (0-255)
            fade_out_ms: Time to fade from max to min
            fade_in_ms: Time to fade from min to max
            delay_at_min_ms: Pause duration at minimum alpha before fading back up
        """
        self._pulse_min = min_alpha
        self._pulse_max = max_alpha
        self._fade_out_duration = fade_out_ms
        self._fade_in_duration = fade_in_ms
        self._pulse_delay = delay_at_min_ms
        self._pulsing = True

        def _fade_up():
            """Fade from min to max (quick)."""
            self._delay_job = None
            if self._pulsing:
                self._animate(target=self._pulse_max, duration=self._fade_in_duration, on_complete=_at_max)

        def _at_max():
            """At max alpha, start fading down (slow)."""
            if self._pulsing:
                self._animate(target=self._pulse_min, duration=self._fade_out_duration, on_complete=_at_min)

        def _at_min():
            """At min alpha, delay then fade back up. Keep ticking on_update so canvas tracks mouse."""
            if self._pulsing:
                if self._pulse_delay > 0:
                    self._job = cron.interval(f"{self.frame_interval_ms}ms", lambda: self.on_update(self.alpha))
                    self._delay_job = cron.after(f"{self._pulse_delay}ms", _fade_up)
                else:
                    _fade_up()

        # Start with fade to min (slow)
        self._animate(target=min_alpha, duration=self._fade_out_duration, on_complete=_at_min)

    def stop(self):
        """Stop all animation immediately. Does not change alpha."""
        self._pulsing = False
        self._cancel()

    def stop_pulse(self):
        """Stop pulsing and fade to full opacity."""
        self.stop()
        self.fade_in(duration_ms=200)

    def set_alpha(self, alpha: int):
        """Set alpha immediately without animation."""
        self._cancel()
        self.alpha = max(0, min(255, alpha))
        self.on_update(self.alpha)

    def _animate(self, target: int, duration: int, on_complete: Optional[Callable[[], None]] = None):
        """Start animation to target alpha."""
        self._cancel()

        self._start_time = time.time()
        self._start_alpha = self.alpha
        self._target_alpha = target
        self._duration_ms = max(1, duration)
        self._on_complete = on_complete

        # Start animation loop
        self._job = cron.interval(f"{self.frame_interval_ms}ms", self._tick)

    def _tick(self):
        """Animation frame update."""
        elapsed_ms = (time.time() - self._start_time) * 1000
        progress = min(elapsed_ms / self._duration_ms, 1.0)

        # Linear interpolation (could add easing here)
        self.alpha = int(self._start_alpha + (self._target_alpha - self._start_alpha) * progress)

        # Notify listener
        self.on_update(self.alpha)

        # Check if complete
        if progress >= 1.0:
            self._cancel()
            if self._on_complete:
                self._on_complete()
            if self.on_complete_callback:
                self.on_complete_callback()

    def _cancel(self):
        """Cancel any running animation."""
        if self._delay_job:
            cron.cancel(self._delay_job)
            self._delay_job = None
        if self._job:
            cron.cancel(self._job)
            self._job = None

    def is_animating(self) -> bool:
        """Check if an animation is currently running."""
        return self._job is not None

    def is_visible(self) -> bool:
        """Check if alpha is above zero."""
        return self.alpha > 0
