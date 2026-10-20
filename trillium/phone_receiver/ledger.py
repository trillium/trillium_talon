"""Idempotency table for the phone listener: which utterance ids this process has seen and what
each one came to, so a phone whose reply was lost can ask instead of guessing.

Pure Python (no `talon` import). A request names itself with `X-Talon-Utterance-Id`; the
listener calls `begin(id)` before it runs anything and `finish(...)` after. A second request with
an id that has finished gets the stored reply and never reaches the executor; one that arrives
while the first is still running is told so. `GET /result/<id>` reads the same table.

Memory only. An entry holds the reply the phone was sent (the phrase text is capped at 512
characters there) and nothing else: no audio, no request body, no key. The table is lost when the
process ends or the listener is restarted (a module reload makes a new `Ledger`), which is what
`instance` is for: it is fresh per `Ledger`, so a phone that sees it change knows the table it
asked about is gone and an unknown id is unknown rather than "never ran".

Entries expire `ttl_s` after they finish and the table holds at most `max_entries`; past that the
oldest finished entry goes first. An early (cap) eviction would make "unknown" ambiguous, so the
newest id ever evicted early is remembered and `horizon_s` says how far back an unknown id still
means "never received".
"""

import dataclasses
import re
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

ID_HEADER = "x-talon-utterance-id"
REPLAYED_HEADER = "X-Talon-Replayed"
MIN_ID_HEX = 16  # 64 bits; a UUID is 32 hex digits and 4 hyphens
MAX_ID_LEN = 64
DEFAULT_TTL_S = 600.0
DEFAULT_MAX_ENTRIES = 512

FRESH = "fresh"  # nothing stored (or only a retriable refusal): run it
REPLAY = "replay"  # finished: answer with the stored reply, run nothing
IN_PROGRESS = "in_progress"  # another request holds this id right now

_ID = re.compile(r"[0-9A-Fa-f-]{%d,%d}" % (MIN_ID_HEX, MAX_ID_LEN))


class BadId(ValueError):
    """An id header or path segment was present but is not a usable id."""


def parse_id(value: str | None) -> str | None:
    """The canonical key (lower-case hex, hyphens dropped) of an id, or None if `value` is None.

    Raises `BadId` for anything else that is not 16+ hex digits (optionally hyphenated, 64
    characters at most). A header that is present but unusable must not fall back to "no id":
    the phone believes it is protected against a double run.
    """
    if value is None:
        return None
    text = value.strip()
    if not _ID.fullmatch(text):
        raise BadId("bad utterance id")
    key = text.replace("-", "").lower()
    if len(key) < MIN_ID_HEX:
        raise BadId("bad utterance id")
    return key


@dataclass(frozen=True)
class Entry:
    key: str
    seq: int  # server sequence of the attempt this entry describes
    attempts: int  # executions begun under this id (more than 1 only after a retriable refusal)
    first: float  # clock when the id was first claimed
    started: float  # clock when this attempt was claimed
    finished: float | None = None
    status: int | None = None  # HTTP status of the stored reply
    body: dict[str, Any] | None = (
        None  # the reply body exactly as the phone was sent it
    )
    retriable: bool = (
        False  # nothing ran, so the next request under this id executes afresh
    )

    @property
    def done(self) -> bool:
        return self.status is not None


@dataclass(frozen=True)
class Claim:
    kind: str  # FRESH, REPLAY or IN_PROGRESS
    entry: Entry


class Ledger:
    def __init__(
        self,
        ttl_s: float = DEFAULT_TTL_S,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        instance: str | None = None,
    ):
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._clock = clock
        self.instance = instance or secrets.token_hex(8)
        self.boot_time = round(
            wall(), 3
        )  # epoch seconds, for display; compare uptime_s
        self._boot = clock()
        self._seq = 0
        self._entries: OrderedDict[str, Entry] = OrderedDict()
        self._lost_before: float | None = None
        self._lock = threading.Lock()

    def uptime_s(self) -> float:
        return round(self._clock() - self._boot, 3)

    def stamp(self, entry: Entry) -> dict[str, Any]:
        """The fields that mark a reply as belonging to `entry` and to this instance."""
        return {
            "id": entry.key,
            "seq": entry.seq,
            "instance": self.instance,
            "boot_time": self.boot_time,
        }

    def horizon_s(self) -> float:
        """An id first received within this many seconds is still held, so unknown means never
        received. It is `ttl_s` unless the cap has evicted a younger entry than that."""
        with self._lock:
            return self._horizon(self._clock())

    def _horizon(self, now: float) -> float:
        if self._lost_before is None:
            return self.ttl_s
        return round(max(0.0, min(self.ttl_s, now - self._lost_before)), 3)

    def _purge(self, now: float) -> None:
        stale = [
            k
            for k, e in self._entries.items()
            if now - (e.finished if e.finished is not None else e.started) >= self.ttl_s
        ]
        for k in stale:
            del self._entries[k]

    def _evict(self) -> None:
        # Never an in-flight entry: its worker is about to finish it.
        while len(self._entries) > self.max_entries:
            victim = next((k for k, e in self._entries.items() if e.done), None)
            if victim is None:
                return
            gone = self._entries.pop(victim)
            if self._lost_before is None or gone.first > self._lost_before:
                self._lost_before = gone.first

    def begin(self, key: str) -> Claim:
        """Claim `key` for execution, or say why not. Atomic: of two racing requests under one id
        exactly one gets FRESH."""
        with self._lock:
            now = self._clock()
            self._purge(now)
            cur = self._entries.get(key)
            if cur is not None and not cur.done:
                return Claim(IN_PROGRESS, cur)
            if cur is not None and not cur.retriable:
                return Claim(REPLAY, cur)
            self._seq += 1
            entry = Entry(
                key,
                self._seq,
                cur.attempts + 1 if cur is not None else 1,
                cur.first if cur is not None else now,
                now,
            )
            self._entries[key] = entry
            self._entries.move_to_end(key)
            self._evict()
            return Claim(FRESH, entry)

    def finish(
        self, entry: Entry, status: int, body: dict[str, Any], retriable: bool = False
    ) -> Entry:
        """Store the reply for the attempt `entry` was claimed for. If the table has dropped or
        replaced the entry meanwhile (it outlived the TTL), the reply is still returned, unstored."""
        with self._lock:
            done = dataclasses.replace(
                entry,
                finished=self._clock(),
                status=status,
                body=body,
                retriable=retriable,
            )
            cur = self._entries.get(entry.key)
            if cur is not None and cur.seq == entry.seq:
                self._entries[entry.key] = done
            return done

    def lookup(self, key: str) -> Entry | None:
        with self._lock:
            self._purge(self._clock())
            return self._entries.get(key)

    def view(self, entry: Entry) -> dict[str, Any]:
        """The `GET /result/<id>` body for a known entry."""
        now = self._clock()
        last = entry.finished if entry.finished is not None else entry.started
        view: dict[str, Any] = {
            "ok": True,
            "state": "done" if entry.done else "in_progress",
            **self.stamp(entry),
            "attempts": entry.attempts,
            "uptime_s": self.uptime_s(),
            "age_s": round(now - entry.first, 3),
            "expires_in_s": round(max(0.0, self.ttl_s - (now - last)), 3),
        }
        if entry.done:
            view["http_status"] = entry.status
            view["retriable"] = entry.retriable
            view["reply"] = dict(entry.body or {})
        return view

    def unknown(self) -> dict[str, Any]:
        """The `GET /result/<id>` body for an id the table does not hold."""
        return {
            "ok": False,
            "error": "unknown",
            "instance": self.instance,
            "boot_time": self.boot_time,
            "uptime_s": self.uptime_s(),
            "ttl_s": self.ttl_s,
            "horizon_s": self.horizon_s(),
        }
