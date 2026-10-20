"""`POST /snippet`: validate an uploaded audio snippet and save it, once, into Talon's recordings.

Pure stdlib, no `talon` import. `SnippetService.handle` takes the already-read body and the
request's headers as plain values and returns `(status, body)`; `listener.ListenerApi` owns the
HTTP checks before it (path, method, auth, content type, rate, length) and calls this.

The ack is the point. The phone deletes its copy only when it sees `ok`, its own id, and a
`received_sha256` / `received_bytes` that match what it sent, so the ack is built only after the
file is durable (`recordings.RecordingsWriter.save` fsyncs the file and the folder) and the
ledger entry is on disk.

Ids are the listener's: `X-Talon-Utterance-Id`, parsed by `ledger.parse_id` and held, while in
flight and for ten minutes after, in the same memory table `/emission` uses. This module adds the
durable layer behind that table (`snippet_ledger`): it outlives the table's TTL and a restart, so
a retry any time later still gets the stored ack with `duplicate: true` and writes nothing, and
the same id with different bytes is `409 id_conflict`. Before saving, a pending entry naming the
reserved file goes into that ledger; a retry that finds one `confirm`s the file (one stat of that
name, no read) and acks it, so a crash between the file landing and the ack cannot save it twice.

A FLAC is stored byte for byte. A WAV is stored as FLAC (Talon's recordings are `.flac`), encoded
by `encode`, which the glue wires to `talon.lib.flac.encode`; without one a WAV is `503
wav_unavailable`. Either way the ack carries both checksums: `received_*` for the bytes the phone
sent, `stored_*` for the file.
"""

import hashlib
import re
import threading
from typing import Any, Callable, NamedTuple

from . import audio, faillog
from .metrics import Trace
from .recordings import RecordingsWriter, SaveError
from .snippet_ledger import LedgerError, SnippetLedger

PATH = "/snippet"
MAX_BYTES = (
    1 << 20
)  # 1 MiB: 30 s of 16 kHz mono 16-bit WAV is 960,044 bytes, FLAC is smaller
RATE = (
    4,
    1.0,
)  # uploads per window seconds, counted per server and apart from /emission
SHA_HEADER = "x-talon-content-sha256"
RATE_HEADER = "x-talon-sample-rate"
MEDIA_TYPES = {
    "audio/flac": audio.FLAC,
    "audio/x-flac": audio.FLAC,
    "audio/wav": audio.WAV,
    "audio/x-wav": audio.WAV,
    "audio/wave": audio.WAV,
    "audio/vnd.wave": audio.WAV,
}
_SHA = re.compile(r"[0-9a-fA-F]{64}")

_SAVE_STATUS = {"no_recordings_dir": 503, "save_failed": 500}

# Refusals under which nothing is left to replay: the id stays usable (see `listener.retriable`).
# A save that failed after the link left a pending entry, which the next attempt settles.
RETRIABLE_ERRORS = frozenset(
    {
        "snippets_disabled",
        "no_recordings_dir",
        "wav_unavailable",
        "bad_checksum_header",
        "bad_sample_rate_header",
        "id_conflict",
        "ledger_write_failed",
        "save_failed",
        "encode_failed",
    }
)

Encode = Callable[[bytes], bytes]


class Outcome(NamedTuple):
    status: int
    body: dict[str, Any]


def _error(status: int, code: str, **extra: Any) -> Outcome:
    return Outcome(status, {"ok": False, "error": code, **extra})


class SnippetService:
    def __init__(
        self,
        writer: RecordingsWriter,
        ledger: SnippetLedger,
        enabled: Callable[[], bool],
        encode: Encode | None = None,
        log: faillog.Log | None = None,
    ):
        self._writer = writer
        self._ledger = ledger
        self._enabled = enabled
        self._encode = encode
        self._log = log or print
        # One writer at a time: the check for a repeated id, the save and the ledger entry are a
        # single step, so a retry that arrives while the first copy is still saving cannot
        # slip between them and save a second file.
        self._lock = threading.Lock()

    def enabled(self) -> bool:
        try:
            return bool(self._enabled())
        except Exception:  # noqa: BLE001 - an unreadable setting counts as off
            return False

    def stored(self, uid: str) -> dict[str, Any] | None:
        """The finished ack for `uid`, or None (unknown, or only pending: not acked, so not done)."""
        try:
            entry = self._ledger.get(uid)
        except Exception:  # noqa: BLE001 - an unreadable ledger is "unknown"
            return None
        if entry is None or entry.get("pending"):
            return None
        return dict(entry)

    def replay(self, ack: dict[str, Any], body: bytes) -> Outcome | None:
        """Answer a request whose id the memory table has finished: the ack again if the bytes are
        the ones it is for, `409 id_conflict` if not. None if `ack` is not an ack (a stored
        refusal), which the caller replays as it was."""
        if ack.get("ok") is not True or "received_sha256" not in ack:
            return None
        if ack["received_sha256"] != hashlib.sha256(body).hexdigest():
            return _error(409, "id_conflict")
        return Outcome(200, {**ack, "duplicate": True})

    def handle(
        self,
        container: str,
        uid: str,
        body: bytes,
        headers: dict[str, str],
        trace: Trace,
    ) -> Outcome:
        """`uid` is the canonical id (`ledger.parse_id`); `body` is read in full; `headers` has
        lower-cased names. Marks `decoded` and `dispatched` on `trace`."""
        declared_sha = headers.get(SHA_HEADER)
        if declared_sha is not None and not _SHA.fullmatch(declared_sha.strip()):
            return _error(400, "bad_checksum_header")
        declared_rate = None
        if headers.get(RATE_HEADER) is not None:
            try:
                declared_rate = int(headers[RATE_HEADER].strip())
            except ValueError:
                return _error(400, "bad_sample_rate_header")

        sha = hashlib.sha256(body).hexdigest()
        if declared_sha is not None and declared_sha.strip().lower() != sha:
            return _error(422, "checksum_mismatch")

        with self._lock:
            prior = self._ledger.get(uid)
            if prior is not None:
                if prior.get("received_sha256") != sha:
                    return _error(409, "id_conflict")
                if not prior.get("pending"):
                    return Outcome(200, {**prior, "duplicate": True})
                settled = self._settle(uid, prior)
                if settled is not None:
                    return settled

            try:
                info = audio.inspect(container, body)
            except audio.AudioError as exc:
                return _error(422, exc.code)
            if declared_rate is not None and declared_rate != info.sample_rate:
                return _error(422, "sample_rate_mismatch", want=audio.SAMPLE_RATE)
            stored = body
            if info.container == audio.WAV:
                if self._encode is None:
                    return _error(503, "wav_unavailable")
                try:
                    stored = self._encode(info.pcm or b"")
                except Exception as exc:  # noqa: BLE001
                    faillog.report(self._log, "snippet encode", exc, bytes=len(body))
                    return _error(500, "encode_failed")
            trace.mark("decoded")

            ack = {
                "ok": True,
                "id": uid,
                "name": self._writer.reserve(),
                "received_bytes": len(body),
                "received_sha256": sha,
                "stored_bytes": len(stored),
                "stored_sha256": (
                    sha if stored is body else hashlib.sha256(stored).hexdigest()
                ),
                "container": info.container,
                "converted": stored is not body,
                "sample_rate": info.sample_rate,
                "channels": info.channels,
                "seconds": round(info.seconds, 3),
            }
            # Pending first: if the file lands and the process dies (or the folder fsync fails)
            # before the ack, the retry finds this entry and settles it instead of saving again.
            # Without a durable record there is nothing to settle against, so nothing is saved.
            try:
                self._ledger.put(uid, {**ack, "pending": True})
            except LedgerError:
                faillog.note(self._log, "snippet ledger not written", bytes=len(body))
                return _error(500, "ledger_write_failed")
            try:
                saved = self._writer.save(stored, ack["name"])
            except SaveError as exc:
                faillog.note(
                    self._log, f"snippet not saved: {exc.code}", bytes=len(body)
                )
                return _error(_SAVE_STATUS.get(exc.code, 500), exc.code)
            except Exception as exc:  # noqa: BLE001
                faillog.report(self._log, "snippet save", exc, bytes=len(body))
                return _error(500, "save_failed")
            ack["name"], ack["stored_bytes"] = saved.name, saved.size
            self._finish(uid, ack, len(body))
            trace.mark("dispatched")
        return Outcome(200, {**ack, "duplicate": False})

    def _finish(self, uid: str, ack: dict[str, Any], received: int) -> None:
        """Replace the pending entry with the ack. The file is durable, so the ack stands even if
        this fails: the pending entry is still there and a retry settles it."""
        try:
            self._ledger.put(uid, ack)
        except LedgerError:
            faillog.note(self._log, "snippet ledger not written", bytes=received)

    def _settle(self, uid: str, pending: dict[str, Any]) -> Outcome | None:
        """A pending entry from an earlier attempt: if its file is there, ack it (the ack the
        first attempt would have sent), else None and the caller saves afresh."""
        ack = {k: v for k, v in pending.items() if k != "pending"}
        try:
            size = self._writer.confirm(str(ack.get("name", "")))
        except SaveError as exc:
            faillog.note(self._log, f"snippet not confirmed: {exc.code}")
            return _error(_SAVE_STATUS.get(exc.code, 500), exc.code)
        if size is None or size != ack.get("stored_bytes"):
            return None
        self._finish(uid, ack, int(ack.get("received_bytes", 0)))
        return Outcome(200, {**ack, "duplicate": True})
