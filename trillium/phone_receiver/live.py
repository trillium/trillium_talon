"""Live-engine install for the phone receiver: gates `PhoneReceiver` behind a setting.

Pure Python (no `talon` import) so it runs under pytest with fakes; the Talon glue that
declares the setting and the action is `phone_receiver_live.py`. Everything here is decided
per call, so there is no state to toggle: while the gate is off nothing touches the engine,
and while it is on the encoder is swapped only inside `PhoneReceiver.handle` and restored in
its `finally`. `heal()` is a belt-and-braces restore for an encoder somehow left swapped.

Refusals (each is a `Result(ok=False, error=code)`, never an exception):
`disabled`, `record_all_on`, `no_engine`, plus every `wire` / `engine_error` code. `no_engine`
also carries `detail`: one short line saying precisely what is missing (no active engine, an
engine proxy with nothing inside, a lookup that raised, or an engine that lacks `lock` /
`encoder` / `_on_audio_frame`, such as a Dragon engine or a W2l engine whose model is gone).
The detail names engines and attributes, never an exception message or a payload.
"""

import threading
from typing import Any, Callable

from . import faillog
from .encoder import PhoneEncoder
from .receiver import PhoneReceiver, Result

MAX_DETAIL = 200
MAX_NAME = 80


class NoEngine(Exception):
    """No engine could be found; the message says which part is missing (see `Result.detail`)."""


def _line(text: str, limit: int = MAX_DETAIL) -> str:
    """`text` as one short line, safe to log and to return to the phone."""
    return " ".join(text.split())[:limit]


def _name(obj: Any) -> str:
    try:
        return _line(repr(obj), MAX_NAME)
    except Exception:  # noqa: BLE001 - a broken repr must not hide the refusal
        return type(obj).__name__


def _missing(engine: Any) -> list[str]:
    """What `engine` lacks of the W2l surface the receiver drives."""
    gone = [a for a in ("lock", "encoder") if not hasattr(engine, a)]
    if not callable(getattr(engine, "_on_audio_frame", None)):
        gone.append("_on_audio_frame")
    return gone


def _usable(engine: Any) -> bool:
    return engine is not None and not _missing(engine)


def active_engine(speech_system: Any) -> Any:
    """The engine behind `speech_system.engine` (Talon wraps it in an `EngineProxy`).

    Raises `NoEngine` saying which link is missing; any other exception is Talon's own.
    """
    proxy = speech_system.engine
    if proxy is None:
        raise NoEngine("speech_system.engine is None: no speech engine is active")
    engine = getattr(proxy, "engine", None)
    if engine is None:
        raise NoEngine(f"{_name(proxy)} wraps no engine")
    return engine


class LiveInstall:
    def __init__(
        self,
        get_engine: Callable[[], Any],
        is_enabled: Callable[[], bool],
        record_all: Callable[[], bool],
        log: faillog.Log | None = None,
    ):
        self._log = log or print
        self._get_engine = get_engine
        self._is_enabled = is_enabled
        self._record_all = record_all
        self._lock = threading.Lock()
        self._receiver: PhoneReceiver | None = None
        self._original = None  # the mic encoder, noted before the first swap

    def _lookup(self) -> tuple[Any, str | None]:
        """`(engine, None)` if there is a usable one, else `(None, what is missing)`."""
        try:
            engine = self._get_engine()
        except NoEngine as exc:
            return None, _line(str(exc))
        except Exception as exc:  # noqa: BLE001 - say what failed, never the message
            faillog.report(self._log, "engine lookup", exc)
            return None, f"engine lookup raised {faillog.qualname(exc)}"
        if engine is None:
            return None, "engine lookup returned None"
        gone = _missing(engine)
        if gone:
            return None, _line(
                f"{_name(engine)} cannot take injected audio: it has no {', '.join(gone)}"
            )
        return engine, None

    def _engine(self):
        return self._lookup()[0]

    def _receiver_for(self, engine) -> PhoneReceiver:
        with self._lock:
            rx = self._receiver
            if rx is None or rx.engine is not engine:
                rx = self._receiver = PhoneReceiver(engine, log=self._log)
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

    def _gated(self, run: Callable[[PhoneReceiver], Result]) -> Result:
        """Run `run(receiver)` only if the setting is on and `speech.record_all` is off."""
        try:
            if not self._is_enabled():
                self.heal()
                return Result(False, "disabled")
            # Injected audio is all zeros (and PCM is the phone's real audio); with record_all
            # on the engine would write a recording per utterance, so refuse rather than
            # touch the recordings.
            if self._record_all():
                return Result(False, "record_all_on")
            engine, why = self._lookup()
            if engine is None:
                return Result(False, "no_engine", detail=why)
            self.heal()
            return run(self._receiver_for(engine))
        except Exception as exc:  # noqa: BLE001
            faillog.report(self._log, "live gate", exc)
            return Result(False, "engine_error")

    def handle(self, buf: bytes) -> Result:
        """Never raises. Refuses unless the setting is on and `speech.record_all` is off."""
        return self._gated(lambda rx: rx.handle(buf))

    def handle_pcm(self, buf: bytes, ts: float = 0.0) -> Result:
        """Seam (c) twin of `handle`: same gate, PCM16 body, the engine's own encoder."""
        return self._gated(lambda rx: rx.handle_pcm(buf, ts))
