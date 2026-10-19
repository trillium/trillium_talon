"""Live-engine install for the phone receiver: gates `PhoneReceiver` behind a setting.

Pure Python (no `talon` import) so it runs under pytest with fakes; the Talon glue that
declares the setting and the action is `phone_receiver_live.py`. Everything here is decided
per call, so there is no state to toggle: while the gate is off nothing touches the engine,
and while it is on the encoder is swapped only inside `PhoneReceiver.handle` and restored in
its `finally`. `heal()` is a belt-and-braces restore for an encoder somehow left swapped.

Refusals (each is a `Result(ok=False, error=code)`, never an exception):
`disabled`, `record_all_on`, `no_engine`, plus every `wire` / `engine_error` code.
"""

import threading
from typing import Any, Callable

from .encoder import PhoneEncoder
from .receiver import PhoneReceiver, Result


def _usable(engine: Any) -> bool:
    return (
        engine is not None
        and hasattr(engine, "lock")
        and hasattr(engine, "encoder")
        and callable(getattr(engine, "_on_audio_frame", None))
    )


class LiveInstall:
    def __init__(
        self,
        get_engine: Callable[[], Any],
        is_enabled: Callable[[], bool],
        record_all: Callable[[], bool],
    ):
        self._get_engine = get_engine
        self._is_enabled = is_enabled
        self._record_all = record_all
        self._lock = threading.Lock()
        self._receiver: PhoneReceiver | None = None
        self._original = None  # the mic encoder, noted before the first swap

    def _engine(self):
        try:
            engine = self._get_engine()
        except Exception:  # noqa: BLE001 - no engine attached yet
            return None
        return engine if _usable(engine) else None

    def _receiver_for(self, engine) -> PhoneReceiver:
        with self._lock:
            rx = self._receiver
            if rx is None or rx.engine is not engine:
                rx = self._receiver = PhoneReceiver(engine)
                self._original = None
            if self._original is None and not isinstance(engine.encoder, PhoneEncoder):
                self._original = engine.encoder
            return rx

    def heal(self) -> bool:
        """Put the mic encoder back if the engine still holds a phone encoder."""
        engine = self._engine()
        if engine is None or self._original is None:
            return False
        with engine.lock:
            if isinstance(engine.encoder, PhoneEncoder):
                engine.encoder = self._original
                return True
        return False

    def handle(self, buf: bytes) -> Result:
        """Never raises. Refuses unless the setting is on and `speech.record_all` is off."""
        try:
            if not self._is_enabled():
                self.heal()
                return Result(False, "disabled")
            # Injected audio is all zeros; with record_all on the engine would write a
            # silent recording per utterance, so refuse rather than touch the recordings.
            if self._record_all():
                return Result(False, "record_all_on")
            engine = self._engine()
            if engine is None:
                return Result(False, "no_engine")
            self.heal()
            return self._receiver_for(engine).handle(buf)
        except Exception:  # noqa: BLE001
            return Result(False, "engine_error")
