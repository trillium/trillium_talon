"""Per-request latency and byte metrics for the phone listener, and their rolling summary.

Pure stdlib, no `talon` import. Each `POST /emission` and `POST /snippet` request becomes one
`Sample`; `Metrics.summary()` is what `GET /metrics` returns and `Metrics.tick_line()` is the one
line Talon's log gets every few minutes. Nothing in a sample can carry a phrase or audio: the
fields are a kind, a status, five numbers and two byte counts.

Server timings, from `Trace` (all milliseconds on the Mac, none include network time):

- `receive_ms`: from the handler starting (request line and headers already parsed by the
  socket layer) to the whole body being read. Absent when the request was refused before that.
- `decode_ms`: validating the body, plus, for a WAV snippet, encoding it to FLAC. Emission:
  `wire.parse_validate`. Absent when the request was refused before it.
- `dispatch_ms`: the work the request exists for. Emission: the hop to Talon's main thread and
  the engine call. Snippet: the durable save (write, fsync, link, folder fsync) and the ledger
  append. Absent when the request was refused before it.
- `total_ms`: the whole handler, request start to the response built (the socket write of the
  response is not in it).

Latency percentiles use the 200 responses only: a `403` or `429` is answered in microseconds and
would drag `p50` down. Counts by status use every response. Percentiles are nearest-rank: the
value at rank `ceil(p/100 * n)` of the sorted values, so they are always an observed value.

Client round trips are what the phone measured for a request it already sent and report back in
`X-Talon-Client-Rtt-Ms` on a later authenticated request; they are kept and summarised alongside.
"""

import math
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

EMISSION = "emission"
SNIPPET = "snippet"
KINDS = (EMISSION, SNIPPET)
WINDOW = 500  # "last N" in the summary
RETAIN = 20000  # samples kept per kind; the oldest drop first
HOURS = 24  # hourly buckets in the summary
MAX_RTT_MS = (
    600_000.0  # a phone round trip over ten minutes is a bug, not a measurement
)
TIMINGS = ("receive_ms", "decode_ms", "dispatch_ms", "total_ms")


@dataclass(frozen=True)
class Sample:
    kind: str
    at: float  # epoch seconds, when the request finished
    status: int
    req_bytes: int  # body bytes read (headers excluded); 0 if refused before the body
    resp_bytes: int  # the JSON body sent back (headers excluded)
    total_ms: float
    receive_ms: float | None = None
    decode_ms: float | None = None
    dispatch_ms: float | None = None


class Trace:
    """Stopwatch for one request: `mark` the phases that happened, `timings` turns them to ms."""

    def __init__(self, timer: Callable[[], float] = time.perf_counter):
        self._timer = timer
        self._t0 = timer()
        self._marks: dict[str, float] = {}

    def mark(self, name: str) -> None:
        self._marks[name] = self._timer()

    def elapsed_ms(self) -> float:
        return _ms(self._timer() - self._t0)

    def timings(self) -> dict[str, float | None]:
        m = self._marks
        got, dec, dis = m.get("received"), m.get("decoded"), m.get("dispatched")
        return {
            "receive_ms": _ms(got - self._t0) if got is not None else None,
            "decode_ms": (
                _ms(dec - got) if dec is not None and got is not None else None
            ),
            "dispatch_ms": (
                _ms(dis - (dec if dec is not None else got))
                if dis is not None and (dec is not None or got is not None)
                else None
            ),
            "total_ms": self.elapsed_ms(),
        }


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 3)


def percentile(values: Iterable[float], p: float) -> float | None:
    """Nearest-rank `p`th percentile (0 < p <= 100) of `values`; None when there are none."""
    data = sorted(values)
    if not data:
        return None
    rank = min(len(data), max(1, math.ceil(p / 100 * len(data))))
    return data[rank - 1]


def _pair(values: list[float]) -> dict[str, float | None]:
    p50, p95 = percentile(values, 50), percentile(values, 95)
    return {
        "p50": round(p50, 2) if p50 is not None else None,
        "p95": round(p95, 2) if p95 is not None else None,
    }


def _present(values: Iterable[float | None]) -> list[float]:
    return [v for v in values if v is not None]


def _stats(samples: list[Sample]) -> dict[str, Any]:
    ok = [s for s in samples if s.status == 200]
    out: dict[str, Any] = {
        "n": len(samples),
        "ok": len(ok),
        "by_status": {
            str(k): v for k, v in sorted(Counter(s.status for s in samples).items())
        },
        "bytes_in": sum(s.req_bytes for s in samples),
        "bytes_out": sum(s.resp_bytes for s in samples),
    }
    for name in TIMINGS:
        out[name] = _pair(_present(getattr(s, name) for s in ok))
    out["req_bytes"] = _pair([s.req_bytes for s in ok])
    out["resp_bytes"] = _pair([s.resp_bytes for s in ok])
    return out


def _hour_label(hour: int) -> str:
    return datetime.fromtimestamp(hour * 3600, timezone.utc).strftime(
        "%Y-%m-%dT%H:00:00Z"
    )


def _hours(
    items: Iterable[Any], at: Callable[[Any], float], make: Callable[[list], dict]
):
    buckets: dict[int, list] = {}
    for item in items:
        buckets.setdefault(int(at(item) // 3600), []).append(item)
    return [
        {"hour": _hour_label(h), **make(buckets[h])} for h in sorted(buckets)[-HOURS:]
    ]


class Metrics:
    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        window: int = WINDOW,
        retain: int = RETAIN,
    ):
        self._clock = clock
        self._window = window
        self._lock = threading.Lock()
        self._samples = {k: deque(maxlen=retain) for k in KINDS}
        self._rtt = {k: deque(maxlen=retain) for k in KINDS}  # (at, ms)
        self._since_tick: deque[Sample] = deque(maxlen=retain)  # drained by tick_line
        self._rtt_rejected = 0

    def now(self) -> float:
        return self._clock()

    def record(self, sample: Sample) -> None:
        with self._lock:
            self._samples[sample.kind].append(sample)
            self._since_tick.append(sample)

    def record_client_rtt(self, kind: str, ms: float) -> bool:
        """Keep a phone-measured round trip. False (and counted) when it is not a usable number."""
        usable = (
            kind in KINDS
            and isinstance(ms, (int, float))
            and not isinstance(ms, bool)
            and math.isfinite(ms)
            and 0 <= ms <= MAX_RTT_MS
        )
        with self._lock:
            if not usable:
                self._rtt_rejected += 1
                return False
            self._rtt[kind].append((self._clock(), float(ms)))
            return True

    def summary(self) -> dict[str, Any]:
        with self._lock:
            samples = {k: list(v) for k, v in self._samples.items()}
            rtt = {k: list(v) for k, v in self._rtt.items()}
            rejected = self._rtt_rejected
        out: dict[str, Any] = {
            "ok": True,
            "generated_at": datetime.fromtimestamp(
                self._clock(), timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": self._window,
            "client_rtt_rejected": rejected,
        }
        for kind in KINDS:
            mine, theirs = samples[kind], rtt[kind]
            out[kind] = {
                "last_n": _stats(mine[-self._window :]),
                "hours": _hours(mine, lambda s: s.at, _stats),
                "client_rtt_ms": {
                    "last_n": {
                        "n": len(theirs[-self._window :]),
                        **_pair([ms for _, ms in theirs[-self._window :]]),
                    },
                    "hours": _hours(
                        theirs,
                        lambda r: r[0],
                        lambda rs: {"n": len(rs), **_pair([ms for _, ms in rs])},
                    ),
                },
            }
        return out

    def tick_line(self) -> str | None:
        """One log line over the requests since the last call, or None when there were none."""
        with self._lock:
            fresh = list(self._since_tick)
            self._since_tick.clear()
        parts = []
        for kind in KINDS:
            mine = [s for s in fresh if s.kind == kind]
            if not mine:
                continue
            st = _stats(mine)
            statuses = " ".join(f"{k}:{v}" for k, v in st["by_status"].items())
            total = st["total_ms"]
            lat = (
                f"total p50 {total['p50']} p95 {total['p95']} ms"
                if total["p50"] is not None
                else "no 200s"
            )
            parts.append(
                f"{kind} {st['n']} req ({statuses}) {lat}, "
                f"in {st['bytes_in']} B out {st['bytes_out']} B"
            )
        return "metrics: " + " | ".join(parts) if parts else None
