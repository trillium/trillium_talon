"""Request bounds: body size and a sliding-window rate limiter."""

import threading
import time
from collections import deque
from typing import BinaryIO, Callable


class BodyError(Exception):
    """A request body violated the bounds. Carries the HTTP status to return."""

    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def parse_content_length(value: str | None, max_bytes: int) -> int:
    """Validate a Content-Length header against `max_bytes` before reading anything."""
    if value is None or not value.strip():
        raise BodyError(411, "length_required")
    try:
        length = int(value.strip())
    except ValueError:
        raise BodyError(400, "bad_content_length") from None
    if length < 0:
        raise BodyError(400, "bad_content_length")
    if length > max_bytes:
        raise BodyError(413, "body_too_large")
    return length


def read_body(rfile: BinaryIO, length: int) -> bytes:
    """Read exactly `length` bytes (already bounded by parse_content_length)."""
    body = rfile.read(length)
    if len(body) != length:
        raise BodyError(400, "truncated_body")
    return body


class RateLimiter:
    """Allow at most `max_calls` per `window_seconds`. Thread-safe."""

    def __init__(
        self,
        max_calls: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._max_calls = max_calls
        self._window = window_seconds
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def check(self) -> tuple[bool, float]:
        """Record an attempt. Returns (allowed, retry_after_seconds)."""
        with self._lock:
            now = self._clock()
            while self._calls and now - self._calls[0] >= self._window:
                self._calls.popleft()
            if len(self._calls) >= self._max_calls:
                return False, self._window - (now - self._calls[0])
            self._calls.append(now)
            return True, 0.0
