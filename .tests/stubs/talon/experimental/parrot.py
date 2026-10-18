"""Talon Parrot (noise detection) API stubs.

The parrot system detects mouth noises (pop, hiss, shush, etc.)
and fires callbacks. Used for hands-free mouse control and triggers.
"""


class ParrotFrame:
    """A single frame of audio data from the parrot system."""

    def __init__(self, samples=None):
        self.samples = samples or []


class ParrotDelegate:
    """Base class for parrot event handlers.

    Subclass and override methods to handle noise events:
        class MyHandler(ParrotDelegate):
            def on_noise(self, noise):
                if noise == "pop":
                    do_click()
    """

    def on_noise(self, noise):
        """Called when a noise is detected. noise is a string like 'pop', 'hiss'."""
        pass

    def on_frame(self, frame):
        """Called for each audio frame."""
        pass


class ParrotSystem:
    """Mock parrot noise detection system."""

    def __init__(self):
        self._delegate = None
        self._enabled = False

    def set_delegate(self, delegate):
        self._delegate = delegate

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    # Test helpers

    def simulate_noise(self, noise_name):
        """Test helper: simulate a noise detection event."""
        if self._delegate and self._enabled:
            self._delegate.on_noise(noise_name)

    def simulate_frame(self, samples=None):
        """Test helper: simulate an audio frame."""
        if self._delegate and self._enabled:
            self._delegate.on_frame(ParrotFrame(samples))
