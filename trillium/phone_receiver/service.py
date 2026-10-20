"""PhoneService: one injected utterance in, a small reply out (phrase text, what Talon did
with it, ms).

Pure Python (no `talon` import). It wraps `LiveInstall` and a `PhraseTap`: the tap is a
`phrase` listener that the Talon glue registers on `speech_system` (the lab registers it on
a private engine), and a call captures the one phrase its own injection dispatches. The
outcome (`kind`, `status`, `why`, `commands`) is read from that same `phrase` event dict
(`parsed`, `_metadata.reject`) and, optionally, `speech.enabled()`; no other hook is used.
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


# What Talon matched. "dictation" is the free-text catch-all rule alone (`<phrase>`, the rule
# the repo's own `skip_phrase_in_sleep` keys on); "command" is any other matched rule, which
# includes prose rules in dictation mode; "unknown" is a phrase event with no `parsed` list.
KIND_COMMAND = "command"
KIND_DICTATION = "dictation"
KIND_UNKNOWN = "unknown"
CATCH_ALL_RULE = "___ltphrase_gt__"

# What became of it. "ran": Talon matched the phrase and dispatched it (a script that then
# raises is not visible on the `phrase` event). "ignored": decoded but nothing was run, with
# `why` saying which. "error": the phrase event arrived but could not be read.
STATUS_RAN = "ran"
STATUS_IGNORED = "ignored"
STATUS_ERROR = "error"
WHY_NO_PHRASE = "no_phrase"  # no phrase event within the wait (e.g. locked session)
WHY_REJECTED = "rejected"  # the engine rejected the decode
WHY_EMPTY = "empty"  # a phrase event with no words
WHY_ASLEEP = "asleep"  # speech is off and only the catch-all rule matched
WHY_NO_MATCH = "no_match"  # no `parsed` captures on the event
WHY_UNREADABLE = "unreadable_phrase"


class Heard(NamedTuple):
    text: str
    reject: bool
    kind: str
    commands: int  # how many rules (captures) the phrase parsed into
    awake: bool | None  # speech.enabled() at dispatch; None if unknown


def _classify(j: Any) -> tuple[str, int]:
    parsed = j.get("parsed")
    if not parsed:
        return KIND_UNKNOWN, 0
    names = [getattr(c, "_name", None) for c in parsed]
    if len(names) == 1 and names[0] == CATCH_ALL_RULE:
        return KIND_DICTATION, 1
    return KIND_COMMAND, len(names)


def summarize_phrase(j: Any, awake: Callable[[], Any] | None = None) -> Heard | None:
    """A `Heard` from a `phrase` event dict, or None if it is not shaped like one."""
    try:
        text = " ".join(str(w) for w in j["phrase"])
        reject = bool((j.get("_metadata") or {}).get("reject", False))
        kind, commands = _classify(j)
    except (
        Exception
    ):  # noqa: BLE001 - an odd event must not break the engine's dispatch
        return None
    state = None
    if awake is not None:
        try:
            state = bool(awake())
        except Exception:  # noqa: BLE001
            state = None
    return Heard(text, reject, kind, commands, state)


# An event arrived but `summarize_phrase` could not read it (as opposed to no event at all).
UNREADABLE = Heard("", False, KIND_UNKNOWN, 0, None)


def outcome(seen: Heard | None) -> tuple[str, str | None]:
    """`(status, why)` for what the tap saw; `why` is None when status is "ran"."""
    if seen is None:
        return STATUS_IGNORED, WHY_NO_PHRASE
    if seen is UNREADABLE:
        return STATUS_ERROR, WHY_UNREADABLE
    if seen.reject:
        return STATUS_IGNORED, WHY_REJECTED
    if not seen.text:
        return STATUS_IGNORED, WHY_EMPTY
    if seen.kind == KIND_UNKNOWN:
        return STATUS_IGNORED, WHY_NO_MATCH
    if seen.kind == KIND_DICTATION and seen.awake is False:
        return STATUS_IGNORED, WHY_ASLEEP
    return STATUS_RAN, None


class PhraseTap:
    """Hands the next `phrase` event to whichever call is capturing; ignores the rest.

    `awake` is read inside the event (the glue passes `actions.speech.enabled`), so it
    reflects the state the phrase was dispatched under rather than the state afterwards.
    """

    def __init__(self, awake: Callable[[], Any] | None = None) -> None:
        self._lock = threading.Lock()  # one capture at a time
        self._slot: dict | None = None
        self._seen = threading.Event()
        self._awake = awake

    def on_phrase(self, j: Any) -> None:
        if self._slot is not None and not self._seen.is_set():
            self._slot["phrase"] = summarize_phrase(j, self._awake) or UNREADABLE
            self._seen.set()

    @contextmanager
    def capture(self, wait_s: float = PHRASE_WAIT_S):
        """Yields a `get()` that returns a `Heard`, `UNREADABLE`, or None when no phrase arrived."""
        with self._lock:
            slot: dict = {}
            self._seen.clear()
            self._slot = slot

            def get() -> Heard | None:
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
    kind: str | None = None  # the fields below are set on success only
    status: str | None = None
    why: str | None = None
    commands: int | None = None


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
        status, why = outcome(seen)
        if seen is None or seen is UNREADABLE:
            text = reject = None  # nothing readable was dispatched
        else:
            text, reject = seen.text, seen.reject
        kind = seen.kind if seen is not None else KIND_UNKNOWN
        commands = seen.commands if seen is not None else 0
        return Reply(
            True, None, text, reject, ms, r.frames, r.n_pcm, kind, status, why, commands
        )
