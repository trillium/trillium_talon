"""PhoneEncoder: stands in for the W2l acoustic encoder and returns a queued phone emission."""

import collections
import threading

import numpy as np

from . import wire

try:  # only importable inside Talon; plain object elsewhere (tests, CI)
    from talon.engines.w2l import W2lBaseEncoder as _Base
except Exception:  # noqa: BLE001
    _Base = object

MAX_QUEUED = 8


class PhoneEncoder(_Base):
    """`forward(samples)` ignores the audio and returns the next queued `(T, 29)` emission
    as `(1, 1, T, 29)`, the shape the engine's own encoder returns."""

    def __init__(self, max_queued: int = MAX_QUEUED):
        self._q: collections.deque = collections.deque()
        self._max = max_queued
        self._lock = threading.Lock()

    def push(self, emission: np.ndarray) -> None:
        """Queue an emission; re-validates it, since the decoder aborts on a bad array."""
        a = wire.validate_array(emission)
        with self._lock:
            if len(self._q) >= self._max:
                raise wire.WireError("queue_full", str(self._max))
            self._q.append(a)

    def clear(self) -> int:
        with self._lock:
            n = len(self._q)
            self._q.clear()
            return n

    def __len__(self) -> int:
        return len(self._q)

    def forward(self, samples):
        with self._lock:
            if not self._q:
                raise RuntimeError("no phone emission queued")
            e = self._q.popleft()
        return e.reshape(1, 1, *e.shape)
