"""PhoneReceiver: validate a TPE1 payload, then run it through a W2lEngine's own decoder.

Seam (a) from the phone-MVP scout: only the encoder call is replaced; padding, decode,
rejection and `phrase` dispatch are the engine's own code. The engine is passed in by the
caller (a private lab engine for now); this module never reaches for `speech_system`.
"""

import math
import threading
from typing import Any, NamedTuple

from . import faillog, wire
from .encoder import PhoneEncoder


class Result(NamedTuple):
    ok: bool
    error: str | None = (
        None  # stable code on failure (WireError.code, or "engine_error")
    )
    frames: int = 0
    n_pcm: int = 0


class PhoneReceiver:
    def __init__(
        self,
        engine: Any,
        encoder: PhoneEncoder | None = None,
        log: faillog.Log | None = None,
    ):
        self.engine = engine
        self.encoder = encoder or PhoneEncoder()
        # an engine failure becomes a code; this keeps its cause
        self._log = log or print
        self._stats_lock = threading.Lock()
        self.accepted = 0
        self.rejected = 0

    def handle(self, buf: bytes) -> Result:
        """Never raises: every failure is a `Result(ok=False, error=code)`."""
        try:
            em = wire.parse_validate(buf)
        except wire.WireError as e:
            return self._count(Result(False, e.code))
        except (
            Exception
        ):  # noqa: BLE001 - nothing malformed may reach the engine or escape
            return self._count(Result(False, "invalid"))
        try:
            self._feed(em)
        except wire.WireError as e:
            return self._count(Result(False, e.code))
        except Exception as exc:  # noqa: BLE001
            faillog.report(
                self._log, "engine feed", exc, mode="emission", bytes=len(buf)
            )
            return self._count(Result(False, "engine_error"))
        return self._count(Result(True, None, em.array.shape[0], em.n_pcm))

    def handle_pcm(self, buf: bytes, ts: float = 0.0) -> Result:
        """Seam (c): feed 16 kHz mono PCM16 to the engine's own encoder. Never raises.

        The engine runs its frontend and acoustic model on the samples exactly as it does for
        a microphone frame; nothing is swapped. Only the length and type can be wrong, and
        `wire.parse_pcm` checks both before the engine is touched.
        """
        try:
            pcm = wire.parse_pcm(buf)
            if not (isinstance(ts, float) and math.isfinite(ts) and ts >= 0):
                raise wire.WireError("bad_ts", repr(ts))
        except wire.WireError as e:
            return self._count(Result(False, e.code))
        except Exception:  # noqa: BLE001
            return self._count(Result(False, "invalid"))
        try:
            with self.engine.lock:
                self.engine._on_audio_frame(pcm.tolist(), ts, pad=True)
        except Exception as exc:  # noqa: BLE001
            faillog.report(self._log, "engine feed", exc, mode="pcm", bytes=len(buf))
            return self._count(Result(False, "engine_error"))
        return self._count(Result(True, None, wire.frames_for(len(pcm)), len(pcm)))

    def _feed(self, em: wire.Emission) -> None:
        eng = self.engine
        # The engine's lock is an RLock that `_on_audio_frame` also takes; holding it across
        # swap, queue and call keeps a concurrent microphone frame off the phone encoder.
        with eng.lock:
            prev = eng.encoder
            eng.encoder = self.encoder
            try:
                self.encoder.push(em.array)
                eng._on_audio_frame([0.0] * em.n_pcm, em.ts, pad=True)
            finally:
                self.encoder.clear()
                eng.encoder = prev

    def _count(self, r: Result) -> Result:
        with self._stats_lock:
            if r.ok:
                self.accepted += 1
            else:
                self.rejected += 1
        return r
