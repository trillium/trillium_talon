"""`POST /noise`: one noise the phone detected, run as the `parrot(<name>)` trigger it stands for.

Pure Python (no `talon` import). The phone runs Parrot on-device and sends events only, so the
Mac's job is the last step a local detection takes: find the trigger scripts Talon registered for
`parrot(<name>)` and run the last one (Talon's own rule: the last impl wins). The glue
(`phone_receiver_live`) supplies the two Talon-facing callables, `lookup(key)` over
`registry.impls.parrot_noises` and `run(impl, event)` over `actions.core.run_talon_script`, so
the captain's `.talon` triggers, their tag and mode gating and every `user.noise_*` override
apply unchanged. No grammar is written here. See `docs/phone-receiver.md`, "POST /noise".

Wire body (JSON, at most `MAX_BODY_BYTES`): `{v, name, edge, power, prob, ts, session, seq}`.
`edge` is `start` (default), `repeat` or `stop` and picks the registry key `name`, `name:repeat`
or `name:stop`. The name is checked for shape only (`NAME_RE`), never used as a path or a
format string; whether it means anything is the registry's call, and a name with no trigger is
`ignored` / `no_trigger`, not an error (a gated trigger, such as an inactive `user.parrot_on`
tag, leaves no impl, which is correct).

Ordering: a `start` whose `seq` is not above the last `start` seen for that `(session, name)` is
`ignored` / `stale_seq` (an out-of-order retry or a late packet). The phone applies the real
throttles; the Mac keeps only a per-name floor (`NAME_FLOOR_S`) so a bug on the phone cannot
fire a trigger faster than the fastest pattern in `patterns.json`, and answers `ignored` /
`throttled`. Idempotency by `X-Talon-Utterance-Id` is the listener's ledger, not this module's.
"""

import json
import math
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, NamedTuple, Sequence

PATH = "/noise"
MAX_BODY_BYTES = 1024
RATE = (
    20,
    1.0,
)  # events per window seconds, counted per server; apart from `/emission`'s
NAME_FLOOR_S = 0.03  # the smallest throttle in the phone's patterns.json (hiss, shh)
WIRE_VERSION = 1
MAX_NAME_LEN = 32
MAX_SESSION_LEN = 64
MAX_SEQ = 2**53  # a JSON number the phone can count to without losing integers
MAX_TRACKED = 256  # (session, name) pairs and names remembered; the oldest drop first
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
SESSION_RE = re.compile(r"[A-Za-z0-9_.-]+")

EDGE_START = "start"
EDGE_REPEAT = "repeat"
EDGE_STOP = "stop"
EDGES = (EDGE_START, EDGE_REPEAT, EDGE_STOP)

STATUS_RAN = "ran"
STATUS_IGNORED = "ignored"
STATUS_ERROR = "error"
WHY_NO_TRIGGER = "no_trigger"
WHY_THROTTLED = "throttled"
WHY_STALE_SEQ = "stale_seq"
WHY_DISPATCH_FAILED = "dispatch_failed"


class NoiseError(ValueError):
    """The body is not a valid noise event; `code` is a stable machine-readable reason."""

    def __init__(self, code: str, status: int = 422):
        super().__init__(code)
        self.code = code
        self.status = status


class NoiseEvent(NamedTuple):
    name: str
    edge: str
    power: float
    prob: float
    ts: float
    session: str
    seq: int

    @property
    def key(self) -> str:
        """The `parrot_noises` registry key: `name`, `name:repeat` or `name:stop`."""
        return self.name if self.edge == EDGE_START else f"{self.name}:{self.edge}"


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NoiseError("bad_field")
    if not math.isfinite(value):
        raise NoiseError("non_finite")
    return float(value)


def parse_body(body: bytes) -> NoiseEvent:
    """A `NoiseEvent` from the request body; raises `NoiseError` (never anything else)."""
    if len(body) > MAX_BODY_BYTES:
        raise NoiseError("payload_too_large", 413)
    try:
        obj = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
    except NoiseError:
        raise
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise NoiseError("bad_json", 400) from None
    if not isinstance(obj, dict):
        raise NoiseError("bad_json", 400)
    if obj.get("v") != WIRE_VERSION or isinstance(obj.get("v"), bool):
        raise NoiseError("bad_version")
    name = obj.get("name")
    if (
        not isinstance(name, str)
        or len(name) > MAX_NAME_LEN
        or not NAME_RE.fullmatch(name)
    ):
        raise NoiseError("bad_name")
    edge = obj.get("edge", EDGE_START)
    if edge not in EDGES:
        raise NoiseError("bad_edge")
    session = obj.get("session")
    if (
        not isinstance(session, str)
        or len(session) > MAX_SESSION_LEN
        or not SESSION_RE.fullmatch(session)
    ):
        raise NoiseError("bad_session")
    seq = obj.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq <= MAX_SEQ:
        raise NoiseError("bad_seq")
    power, prob, ts = (_number(obj.get(k)) for k in ("power", "prob", "ts"))
    if not 0.0 <= prob <= 1.0:
        raise NoiseError("bad_field")
    return NoiseEvent(name, edge, power, prob, ts, session, seq)


def _reject_constant(_name: str):
    # json.loads accepts NaN / Infinity by default; they are not JSON
    raise NoiseError("non_finite")


class NoiseReply(NamedTuple):
    ok: bool
    error: str | None = None
    name: str | None = None
    edge: str | None = None
    status: str | None = None
    why: str | None = None
    commands: int = 0
    ms: float = 0.0
    detail: str | None = None


class NoiseService:
    """Gate, order and throttle a noise event, then run its trigger.

    `lookup(key)` returns the impls registered for that `parrot_noises` key (any sequence, empty
    for none); `run(impl, event)` runs one. Both are called on whatever thread calls `handle`, which
    the listener makes Talon's main thread. `enabled` and `record_all` are read per call.
    """

    def __init__(
        self,
        lookup: Callable[[str], Sequence[Any]],
        run: Callable[[Any, NoiseEvent], None],
        enabled: Callable[[], bool],
        record_all: Callable[[], bool],
        clock: Callable[[], float] = time.monotonic,
        timer: Callable[[], float] = time.perf_counter,
        floor_s: float = NAME_FLOOR_S,
    ):
        self._lookup = lookup
        self._run = run
        self._enabled = enabled
        self._record_all = record_all
        self._clock = clock
        self._timer = timer
        self._floor_s = floor_s
        self._lock = threading.Lock()
        self._last_seq: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._last_run: OrderedDict[str, float] = OrderedDict()

    def _remember(self, table: OrderedDict, key, value) -> None:
        table[key] = value
        table.move_to_end(key)
        while len(table) > MAX_TRACKED:
            table.popitem(last=False)

    def handle(self, event: NoiseEvent) -> NoiseReply:
        t0 = self._timer()

        def reply(status, why=None, commands=0) -> NoiseReply:
            ms = round((self._timer() - t0) * 1000, 2)
            return NoiseReply(
                True, None, event.name, event.edge, status, why, commands, ms
            )

        if not self._enabled():
            return NoiseReply(False, "disabled")
        # A missing or unreadable setting counts as on, as for /emission.
        if self._record_all():
            return NoiseReply(False, "record_all_on")
        now = self._clock()
        with self._lock:
            if event.edge == EDGE_START:
                pair = (event.session, event.name)
                if event.seq <= self._last_seq.get(pair, -1):
                    return reply(STATUS_IGNORED, WHY_STALE_SEQ)
                self._remember(self._last_seq, pair, event.seq)
                last = self._last_run.get(event.name)
                if last is not None and now - last < self._floor_s:
                    return reply(STATUS_IGNORED, WHY_THROTTLED)
        try:
            impls = self._lookup(event.key)
        except (
            Exception
        ) as exc:  # noqa: BLE001 - the registry is Talon's; say it failed
            return NoiseReply(
                False,
                "registry_error",
                event.name,
                event.edge,
                detail=type(exc).__name__,
            )
        if not impls:
            return reply(STATUS_IGNORED, WHY_NO_TRIGGER)
        try:
            self._run(impls[-1], event)  # last impl wins, as Talon's own dispatch
        except Exception as exc:  # noqa: BLE001
            out = reply(STATUS_ERROR, WHY_DISPATCH_FAILED)
            return out._replace(detail=type(exc).__name__)
        with self._lock:
            if event.edge == EDGE_START:
                self._remember(self._last_run, event.name, now)
        return reply(STATUS_RAN, None, 1)
