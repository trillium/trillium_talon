"""PhoneService: one injected utterance in, a small reply out (phrase text, reject flag, ms).

Pure Python (no `talon` import). It wraps `LiveInstall` and a `PhraseTap`: the tap is a
`phrase` listener that the Talon glue registers on `speech_system` (the lab registers it on
a private engine), and a call captures the one phrase its own injection dispatches.
"""

import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, NamedTuple

from .live import LiveInstall
from .receiver import Result

PHRASE_WAIT_S = (
    0.5  # dispatch is synchronous on the live engine; this only covers a late one
)


def summarize_phrase(j: Any) -> tuple[str, bool] | None:
    """`(text, reject)` from a `phrase` event dict, or None if it is not shaped like one."""
    try:
        text = " ".join(str(w) for w in j["phrase"])
        reject = bool((j.get("_metadata") or {}).get("reject", False))
    except (
        Exception
    ):  # noqa: BLE001 - an odd event must not break the engine's dispatch
        return None
    return text, reject


class PhraseTap:
    """Hands the next `phrase` event to whichever call is capturing; ignores the rest."""

    def __init__(self) -> None:
        self._lock = threading.Lock()  # one capture at a time
        self._slot: dict | None = None
        self._seen = threading.Event()

    def on_phrase(self, j: Any) -> None:
        if self._slot is not None and not self._seen.is_set():
            self._slot["phrase"] = summarize_phrase(j)
            self._seen.set()

    @contextmanager
    def capture(self, wait_s: float = PHRASE_WAIT_S):
        """Yields a `get()` that returns `(text, reject)` or None when no phrase arrived."""
        with self._lock:
            slot: dict = {}
            self._seen.clear()
            self._slot = slot

            def get() -> tuple[str, bool] | None:
                self._seen.wait(wait_s)
                return slot.get("phrase")

            try:
                yield get
            finally:
                self._slot = None


class Reply(NamedTuple):
    ok: bool
    error: str | None = None
    text: str | None = (
        None  # None: nothing was dispatched (an error, or no phrase seen)
    )
    reject: bool | None = None
    ms: float = 0.0
    frames: int = 0
    n_pcm: int = 0


class PhoneService:
    def __init__(
        self,
        install: LiveInstall,
        tap: PhraseTap,
        wait_s: float = PHRASE_WAIT_S,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self._install = install
        self._tap = tap
        self._wait_s = wait_s
        self._clock = clock

    def emission(self, buf: bytes) -> Reply:
        return self._run(lambda: self._install.handle(buf))

    def pcm(self, buf: bytes, ts: float) -> Reply:
        return self._run(lambda: self._install.handle_pcm(buf, ts))

    def _run(self, call: Callable[[], Result]) -> Reply:
        t0 = self._clock()
        with self._tap.capture(self._wait_s) as get:
            r = call()
            seen = get() if r.ok else None
        ms = round((self._clock() - t0) * 1000, 2)
        if not r.ok:
            return Reply(False, r.error or "error", ms=ms)
        text, reject = seen if seen is not None else (None, None)
        return Reply(True, None, text, reject, ms, r.frames, r.n_pcm)
