"""HTTP front for the phone receiver: `POST /emission` (one utterance per request),
`POST /snippet` (one saved audio snippet per request, see `snippet`), `POST /noise` (one
phone-detected noise per request, see `noise`), `GET /result/<id>` to ask
what became of one, and `GET /metrics` (see `metrics`).

Pure stdlib, no `talon` import. `ListenerApi.handle` is the whole policy and takes plain
values, so tests drive it without a socket; `start` binds it to loopback or to this Mac's own
tailnet address (see `netbind`) and nothing else.

Order of checks, cheapest and least informative first, so a caller learns nothing it is not
cleared for and no body is read before it is: path (404), method (405), auth (403),
content type for the configured mode (415), rate (429), length headers (411/400/413), then
the body itself (400), the body's wire format (422, validated here so a malformed body is
refused before the runner, the main thread or the engine is involved), and only then the
service, which validates again in Python before any native call. `/snippet` runs the same
checks with its own content types, rate and body cap, then hands the body to `SnippetService`;
`/metrics` is auth then rate, and returns counts and timings only.

Auth has two forms, chosen by how the listener is served. With no `key` provider (the
loopback case, fronted by `tailscale serve` if at all) it is the `Tailscale-User-Login`
header matched against an allow-list; an empty list denies everyone, and any local process
can forge the header, which is the same boundary the palette feed has. With a `key` provider
(the tailnet bind, where nothing adds that header) it is the shared secret in
`X-Talon-Phone-Key`, compared in constant time, and the identity header is ignored.

A request may carry `X-Talon-Utterance-Id` (see `ledger`): the id makes the POST idempotent, so a
retry after a lost reply gets the stored reply instead of running the command a second time, and
`GET /result/<id>` (same auth, its own rate limit) says what the first attempt came to. Without
the header an `/emission` request behaves exactly as it always did. `/snippet` requires it
(`400 missing_utterance_id`): it is the same header and the same table, and the snippet service
keeps a durable ack per id behind that table, so a retry after the table forgot it (ten minutes,
or a restart) still returns the stored ack, and `GET /result/<id>` still finds it.
"""

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, BinaryIO, Callable, Iterable, Mapping, Protocol

from ..palette_feed.dispatch import DispatchTimeout
from ..palette_feed.limits import (
    BodyError,
    RateLimiter,
    parse_content_length,
    read_body,
)
from . import faillog, keyfile, ledger, netbind, noise, snippet, wire
from .hop import SchedulerUnavailable
from .metrics import EMISSION, NOISE, SNIPPET, Metrics, Sample, Trace
from .service import Reply

DEFAULT_PORT = 7403
PATH = "/emission"
RESULT_PREFIX = "/result/"
METRICS_PATH = "/metrics"
IDENTITY_HEADER = "tailscale-user-login"
TS_HEADER = "x-utterance-ts"
MODE_EMISSION = "emission"
MODE_PCM = "pcm"
MODES = (MODE_EMISSION, MODE_PCM)
CONTENT_TYPES = {MODE_EMISSION: "application/x-talon-tpe1", MODE_PCM: "audio/l16"}
MAX_IDENTITY_LEN = 256
REQUEST_TIMEOUT_S = 10
RATE = (10, 1.0)  # utterances per window seconds, counted per server
# result queries per window seconds; apart from RATE so polling cannot 429 an utterance
RESULT_RATE = (20, 1.0)
METRICS_RATE = (5, 1.0)  # summaries per window seconds, counted per server
RTT_HEADER = (
    "x-talon-client-rtt-ms"  # the phone's own round trip for an earlier request
)
RTT_KIND_HEADER = (
    "x-talon-client-rtt-kind"  # which request it measured; default: this one's kind
)
SERVER_MS_HEADER = (
    "X-Talon-Server-Ms"  # on every response to a known path: handler total_ms
)
MAX_TEXT_CHARS = 512  # cap on the echoed phrase; the other reply fields are short enums

# Wire-level mistakes are the caller's; the rest say why the host could not serve.
_STATUS = {
    "disabled": 503,
    "record_all_on": 503,
    "no_engine": 503,
    "engine_error": 500,
    "payload_too_large": 413,
}

# A refusal where the command provably did not run keeps its id usable: the stored reply says so
# (`retriable`) and the next request under that id executes. Everything else is final, because
# the command may have run (a 504 or a 500 from inside the engine) or did (any 200).
_RETRIABLE_ERRORS = (
    frozenset(
        {
            "scheduler_unavailable",
            "disabled",
            "record_all_on",
            "no_engine",
            "registry_error",
        }
    )
    | snippet.RETRIABLE_ERRORS
)


class Backend(Protocol):
    def emission(self, buf: bytes) -> Reply: ...
    def pcm(self, buf: bytes, ts: float) -> Reply: ...


@dataclass
class Response:
    status: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    def payload(self) -> bytes:
        """The JSON bytes sent for `body`; also what the byte metrics count."""
        return json.dumps(self.body, separators=(",", ":")).encode("utf-8")


def _error(status: int, code: str, **extra: Any) -> Response:
    return Response(status, {"ok": False, "error": code, **extra})


def retriable(resp: Response) -> bool:
    """True if `resp` is a refusal under which the command did not run, so its id may be reused.

    The wire-level 4xx (413, 422) count: the body was refused before any engine call, and a phone
    that fixes it should not be answered with the old refusal for ten minutes.
    """
    if resp.body.get("ok") is not False:
        return False
    return resp.body.get("error") in _RETRIABLE_ERRORS or resp.status in (413, 422)


def parse_allowlist(value: Any) -> frozenset[str]:
    """Logins from a comma/space/newline separated setting value, lower-cased. No wildcard."""
    if not isinstance(value, str):
        return frozenset()
    return frozenset(p.lower() for p in value.replace(",", " ").split() if p)


def media_type(header: str | None) -> tuple[str, dict[str, str]]:
    """`(lower-cased type/subtype, params)` of a Content-Type value; unparsable gives ("", {})."""
    if not header:
        return "", {}
    head, *rest = header.split(";")
    params = {}
    for part in rest:
        k, sep, v = part.partition("=")
        if sep:
            params[k.strip().lower()] = v.strip().strip('"').lower()
    return head.strip().lower(), params


def content_type_ok(mode: str, header: str | None) -> bool:
    media, params = media_type(header)
    if media != CONTENT_TYPES.get(mode):
        return False
    if mode == MODE_PCM:  # raw PCM is meaningless without its format, so it is pinned
        return params.get("rate") == "16000" and params.get("channels", "1") == "1"
    return True


def parse_ts(value: str | None, default: float) -> float | None:
    """The optional PCM timestamp header: `default` when absent, None when not a finite float >= 0."""
    if value is None:
        return default
    try:
        ts = float(value.strip())
    except ValueError:
        return None
    return ts if ts == ts and 0 <= ts < float("inf") else None


class ListenerApi:
    def __init__(
        self,
        backend: Backend,
        get_mode: Callable[[], str],
        get_allowed: Callable[[], Any],
        runner: Callable[[Callable[[], Reply]], Reply] | None = None,
        limiter: RateLimiter | None = None,
        clock: Callable[[], float] | None = None,
        key: Callable[[], str | None] | None = None,
        timer: Callable[[], float] | None = None,
        log: faillog.Log | None = None,
        table: ledger.Ledger | None = None,
        result_limiter: RateLimiter | None = None,
        snippets: snippet.SnippetService | None = None,
        metrics: Metrics | None = None,
        snippet_limiter: RateLimiter | None = None,
        metrics_limiter: RateLimiter | None = None,
        trace_timer: Callable[[], float] | None = None,
        noises: noise.NoiseService | None = None,
        noise_limiter: RateLimiter | None = None,
    ):
        self._backend = backend
        self._get_mode = get_mode
        self._get_allowed = get_allowed
        self._get_key = key
        # Talon runs commands from its main thread; the glue passes a runner that hops there.
        self._run = runner or (lambda fn: fn())
        self._limiter = limiter or RateLimiter(*RATE)
        self._result_limiter = result_limiter or RateLimiter(*RESULT_RATE)
        # Fresh per listener, so a reload (which loses the table) also changes `instance`.
        self._ledger = table or ledger.Ledger()
        self._clock = clock or time.time
        self._timer = timer or time.perf_counter
        # Talon's log; see faillog for what is (and is not) written
        self._log = log or print
        # Both optional: without them `/snippet` and `/metrics` are 404, as before they existed.
        # Snippets and summaries are limited apart from `/emission` so an upload backlog cannot
        # starve live speech.
        self._snippets = snippets
        self._metrics = metrics
        self._snippet_limiter = snippet_limiter or RateLimiter(*snippet.RATE)
        self._metrics_limiter = metrics_limiter or RateLimiter(*METRICS_RATE)
        # Optional too: without it `/noise` is 404. Its own bucket, so a flurry of noise events
        # cannot starve utterances and the other way round.
        self._noises = noises
        self._noise_limiter = noise_limiter or RateLimiter(*noise.RATE)
        self._trace_timer = (
            trace_timer or time.perf_counter
        )  # apart from `timer`, which times total_ms

    @property
    def log(self) -> faillog.Log:
        return self._log

    @property
    def table(self) -> ledger.Ledger:
        return self._ledger

    @property
    def uses_key(self) -> bool:
        """True when auth is the shared-secret header rather than the Tailscale identity."""
        return self._get_key is not None

    def _mode(self) -> str:
        mode = self._get_mode()
        return mode.strip().lower() if isinstance(mode, str) else ""

    def _authorized(self, h: Mapping[str, str]) -> bool:
        if self._get_key is not None:
            key = self._get_key()  # no key loaded denies everyone
            return isinstance(key, str) and keyfile.matches(h.get(keyfile.HEADER), key)
        login = h.get(IDENTITY_HEADER)
        return (
            isinstance(login, str)
            and bool(login.strip())
            and len(login) <= MAX_IDENTITY_LEN
            and login.strip().lower() in parse_allowlist(self._get_allowed())
        )

    def handle(
        self,
        method: str,
        target: str,
        headers: Mapping[str, str],
        rfile: BinaryIO | None = None,
    ) -> Response:
        """Never raises; every outcome is a `Response`."""
        ctx: dict[str, Any] = {"stage": "request"}
        trace = Trace(self._trace_timer)
        try:
            resp = self._handle(method, target, headers, rfile, ctx, trace)
        except Exception as exc:  # noqa: BLE001 - nothing may escape into Talon
            faillog.report(self._log, f"handling at {ctx['stage']}", exc, **ctx)
            resp = _error(500, "internal")
        return self._measure(resp, ctx, trace)

    def _measure(self, resp: Response, ctx: dict[str, Any], trace: Trace) -> Response:
        """Record the request in the metrics and stamp the server time on the response."""
        kind = ctx.get("kind")
        if kind is None:
            return resp
        try:
            timings = trace.timings()
            resp.headers[SERVER_MS_HEADER] = str(timings["total_ms"])
            if self._metrics is not None:
                self._metrics.record(
                    Sample(
                        kind,
                        self._metrics.now(),
                        resp.status,
                        ctx.get("read_bytes", 0),
                        len(resp.payload()),
                        **timings,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - metrics must never fail a request
            faillog.report(self._log, "metrics", exc)
        return resp

    def _rate_limited(self, limiter: RateLimiter) -> Response | None:
        allowed, retry_after = limiter.check()
        if allowed:
            return None
        return Response(
            429,
            {"ok": False, "error": "rate_limited"},
            {"Retry-After": str(max(1, int(retry_after + 0.999)))},
        )

    def _absorb_rtt(self, h: Mapping[str, str], kind: str) -> None:
        """Keep the phone's round trip for an earlier request; a bad value is counted, not an error."""
        raw = h.get(RTT_HEADER)
        if raw is None or self._metrics is None:
            return
        try:
            ms = float(raw.strip())
        except ValueError:
            ms = float("nan")
        self._metrics.record_client_rtt(
            (h.get(RTT_KIND_HEADER) or kind).strip().lower(), ms
        )

    def _handle(self, method, target, headers, rfile, ctx, trace) -> Response:
        h = {str(k).lower(): v for k, v in headers.items()}
        path = target.split("?", 1)[0]
        if path.startswith(RESULT_PREFIX):
            return self._result(method, path[len(RESULT_PREFIX) :], h, ctx)
        routes = {PATH: EMISSION, snippet.PATH: SNIPPET}
        if self._metrics is not None:
            routes[METRICS_PATH] = None
        if self._snippets is None:
            routes.pop(snippet.PATH)
        if self._noises is not None:
            routes[noise.PATH] = NOISE
        if path not in routes:
            return _error(404, "not_found")
        want = "GET" if path == METRICS_PATH else "POST"
        if method != want:
            return Response(
                405, {"ok": False, "error": "method_not_allowed"}, {"Allow": want}
            )
        kind = routes[path]
        if kind is not None:
            ctx["kind"] = kind
        ctx["stage"] = "auth"
        if not self._authorized(h):
            return _error(403, "forbidden")
        if kind is None:
            ctx["stage"] = "metrics"
            return self._rate_limited(self._metrics_limiter) or Response(
                200, self._metrics.summary()
            )
        self._absorb_rtt(h, kind)
        if kind == SNIPPET:
            return self._snippet(h, rfile, ctx, trace)
        if kind == NOISE:
            return self._noise(h, rfile, ctx, trace)
        ctx["stage"] = "mode"
        mode = self._mode()
        ctx["mode"] = mode
        if (
            mode not in MODES
        ):  # a typo in the setting must not fall through to either path
            return _error(503, "bad_mode")
        if not content_type_ok(mode, h.get("content-type")):
            return _error(
                415, "unsupported_media_type", want=CONTENT_TYPES[mode], mode=mode
            )
        limited = self._rate_limited(self._limiter)
        if limited is not None:
            return limited
        try:
            uid = ledger.parse_id(h.get(ledger.ID_HEADER))
        except ledger.BadId:
            return _error(400, "bad_utterance_id")
        if "transfer-encoding" in h:
            return _error(411, "length_required")
        ctx["stage"] = "read_body"
        try:
            length = parse_content_length(
                h.get("content-length"), wire.MAX_PAYLOAD_BYTES
            )
            ctx["bytes"] = length
            body = read_body(rfile, length) if rfile is not None else b""
        except BodyError as exc:
            return _error(exc.status, exc.code)
        ctx["bytes"] = ctx["read_bytes"] = len(body)
        trace.mark("received")
        ctx["stage"] = "validate"
        ts = 0.0
        if mode == MODE_PCM:
            ts = parse_ts(h.get(TS_HEADER), self._clock())
            if ts is None:
                return _error(400, "bad_ts")
        invalid = _wire_error(mode, body)
        if invalid is not None:
            return _error(422, invalid)
        trace.mark("decoded")
        if mode == MODE_PCM:
            call = lambda: self._backend.pcm(body, ts)  # noqa: E731
        else:
            call = lambda: self._backend.emission(body)  # noqa: E731
        if uid is None:
            return self._execute(call, mode, ctx, trace)
        return self._once(uid, lambda: self._execute(call, mode, ctx, trace))

    def _once(
        self,
        uid: str,
        run: Callable[[], Response],
        replay: Callable[[ledger.Entry], Response | None] | None = None,
    ) -> Response:
        """`run()` at most once per `uid` (until its refusal is retriable or the entry expires).

        Not for wire-level refusals: those return before an id is claimed, since nothing ran and
        nothing needs remembering. `run` is the executor; this is the only caller of it for an
        utterance that carries an id, and it is never called for a replay or an id in flight.
        `replay`, if given, may answer a replay itself (a snippet checks that the bytes are the
        ones the stored ack is for); None from it means the stored reply as it was.
        """
        claim = self._ledger.begin(uid)
        entry = claim.entry
        if claim.kind == ledger.IN_PROGRESS:
            body = {"ok": False, "error": "in_progress", **self._ledger.stamp(entry)}
            return Response(409, body, {"Retry-After": "1"})
        if claim.kind == ledger.REPLAY:
            answer = replay(entry) if replay is not None else None
            if answer is not None:
                return answer
            return Response(
                entry.status or 500,
                dict(entry.body or {}),
                {ledger.REPLAYED_HEADER: "1"},
            )
        try:
            resp = run()
        except BaseException:
            # It may have run, so the id is spent: settle it before `handle` answers 500.
            self._ledger.finish(
                entry,
                500,
                {"ok": False, "error": "internal", **self._ledger.stamp(entry)},
            )
            raise
        body = {**resp.body, **self._ledger.stamp(entry)}
        self._ledger.finish(entry, resp.status, body, retriable(resp))
        return Response(resp.status, body, resp.headers)

    def _execute(
        self, call: Callable[[], Reply], mode: str, ctx: dict[str, Any], trace: Trace
    ) -> Response:
        ctx["stage"] = "runner"
        t0 = self._timer()
        try:
            try:
                reply = self._run(call)
            finally:
                trace.mark("dispatched")
        except (TimeoutError, DispatchTimeout):
            faillog.note(
                self._log, "runner timed out", **ctx, ms=_ms(self._timer() - t0)
            )
            return _error(504, "timeout")
        except SchedulerUnavailable as exc:
            # never queued, so the command did not run: unlike the generic 500 below
            faillog.report(
                self._log, "scheduler", exc, **{**ctx, "ms": _ms(self._timer() - t0)}
            )
            return _error(503, "scheduler_unavailable")
        except Exception as exc:  # noqa: BLE001
            faillog.report(
                self._log, "runner", exc, **{**ctx, "ms": _ms(self._timer() - t0)}
            )
            return _error(500, "internal")
        total_ms = _ms(self._timer() - t0)
        ctx["stage"] = "reply"
        if not reply.ok and _STATUS.get(reply.error or "error", 422) >= 500:
            faillog.note(
                self._log,
                f"service refused: {reply.error}",
                **ctx,
                ms=total_ms,
                detail=reply.detail,
            )
        return _reply(reply, mode, total_ms)

    def _result(
        self, method: str, raw_id: str, h: Mapping[str, str], ctx: dict[str, Any]
    ) -> Response:
        """`GET /result/<id>`: what became of an utterance, from the table and nothing else."""
        if method != "GET":
            return Response(
                405, {"ok": False, "error": "method_not_allowed"}, {"Allow": "GET"}
            )
        ctx["stage"] = "auth"
        if not self._authorized(h):
            return _error(403, "forbidden")
        allowed, retry_after = self._result_limiter.check()
        if not allowed:
            return Response(
                429,
                {"ok": False, "error": "rate_limited"},
                {"Retry-After": str(max(1, int(retry_after + 0.999)))},
            )
        ctx["stage"] = "result"
        try:
            key = ledger.parse_id(raw_id)
        except ledger.BadId:
            return _error(400, "bad_utterance_id")
        entry = self._ledger.lookup(key) if key is not None else None
        if entry is None:
            stored = self._snippets.stored(key) if self._snippets and key else None
            if stored is not None:
                return Response(200, self._stored_view(key, stored))
            return Response(404, self._ledger.unknown())
        view = self._ledger.view(entry)
        if entry.done:
            return Response(200, view)
        return Response(202, view, {"Retry-After": "1"})

    def _stored_view(self, key: str, ack: dict[str, Any]) -> dict[str, Any]:
        """`GET /result/<id>` for a snippet the memory table no longer holds but the durable one does.

        The ack is the reply as first sent; there is no attempt count or age here, and `stored`
        says it came from the file-ack table, which outlives the memory table's TTL and restarts.
        """
        return {
            "ok": True,
            "state": "done",
            "id": key,
            "instance": self._ledger.instance,
            "boot_time": self._ledger.boot_time,
            "uptime_s": self._ledger.uptime_s(),
            "http_status": 200,
            "retriable": False,
            "stored": True,
            "reply": {**ack, "id": key, "duplicate": False},
        }

    def _snippet(self, h, rfile, ctx, trace) -> Response:
        """`POST /snippet`: the checks `/emission` makes, then `SnippetService.handle`.

        The id is required (the phone deletes its copy on the ack, so a retry must be safe) and is
        the same `X-Talon-Utterance-Id` as `/emission`'s, held in the same table: an id in flight
        is `409 in_progress`, a finished one is replayed (`X-Talon-Replayed`). The service adds the
        durable layer behind that table, which is what makes a retry after the TTL or a restart
        return the stored ack instead of saving a second file.
        """
        svc = self._snippets
        ctx["stage"] = "snippet"
        if not svc.enabled():
            return _error(503, "snippets_disabled")
        container = snippet.MEDIA_TYPES.get(media_type(h.get("content-type"))[0])
        if container is None:
            return _error(
                415, "unsupported_media_type", want=sorted(snippet.MEDIA_TYPES)
            )
        limited = self._rate_limited(self._snippet_limiter)
        if limited is not None:
            return limited
        try:
            uid = ledger.parse_id(h.get(ledger.ID_HEADER))
        except ledger.BadId:
            return _error(400, "bad_utterance_id")
        if uid is None:
            return _error(400, "missing_utterance_id")
        if "transfer-encoding" in h:
            return _error(411, "length_required")
        ctx["stage"] = "read_body"
        try:
            length = parse_content_length(h.get("content-length"), snippet.MAX_BYTES)
            ctx["bytes"] = length
            body = read_body(rfile, length) if rfile is not None else b""
        except BodyError as exc:
            return _error(exc.status, exc.code)
        ctx["bytes"] = ctx["read_bytes"] = len(body)
        trace.mark("received")
        ctx["stage"] = "save"

        def save() -> Response:
            out = svc.handle(container, uid, body, h, trace)
            return Response(out.status, out.body)

        def replay(entry: ledger.Entry) -> Response | None:
            out = svc.replay(entry.body or {}, body)
            if out is None:
                return None
            headers = {ledger.REPLAYED_HEADER: "1"} if out.status == 200 else {}
            return Response(out.status, out.body, headers)

        return self._once(uid, save, replay)

    def _noise(self, h, rfile, ctx, trace) -> Response:
        """`POST /noise`: the checks `/emission` makes, then `NoiseService.handle` on the main thread.

        The id is required and goes through the same table: a repeat of a finished id replays the
        stored reply and never runs the trigger again; an id in flight is `409 in_progress`.
        """
        ctx["stage"] = "noise"
        if media_type(h.get("content-type"))[0] != "application/json":
            return _error(415, "unsupported_media_type", want="application/json")
        limited = self._rate_limited(self._noise_limiter)
        if limited is not None:
            return limited
        try:
            uid = ledger.parse_id(h.get(ledger.ID_HEADER))
        except ledger.BadId:
            return _error(400, "bad_utterance_id")
        if uid is None:
            return _error(400, "missing_utterance_id")
        if "transfer-encoding" in h:
            return _error(411, "length_required")
        ctx["stage"] = "read_body"
        try:
            length = parse_content_length(h.get("content-length"), noise.MAX_BODY_BYTES)
            ctx["bytes"] = length
            body = read_body(rfile, length) if rfile is not None else b""
        except BodyError as exc:
            return _error(exc.status, exc.code)
        ctx["bytes"] = ctx["read_bytes"] = len(body)
        trace.mark("received")
        ctx["stage"] = "validate"
        try:
            event = noise.parse_body(body)
        except noise.NoiseError as exc:
            return _error(exc.status, exc.code)
        trace.mark("decoded")
        return self._once(uid, lambda: self._execute_noise(event, ctx, trace))

    def _execute_noise(self, event, ctx, trace) -> Response:
        ctx["stage"] = "runner"
        t0 = self._timer()
        try:
            try:
                reply = self._run(lambda: self._noises.handle(event))
            finally:
                trace.mark("dispatched")
        except (TimeoutError, DispatchTimeout):
            faillog.note(
                self._log, "runner timed out", **ctx, ms=_ms(self._timer() - t0)
            )
            return _error(504, "timeout")
        except SchedulerUnavailable as exc:
            faillog.report(
                self._log, "scheduler", exc, **{**ctx, "ms": _ms(self._timer() - t0)}
            )
            return _error(503, "scheduler_unavailable")
        except Exception as exc:  # noqa: BLE001
            faillog.report(
                self._log, "runner", exc, **{**ctx, "ms": _ms(self._timer() - t0)}
            )
            return _error(500, "internal")
        total_ms = _ms(self._timer() - t0)
        ctx["stage"] = "reply"
        if not reply.ok:
            extra = {"detail": reply.detail} if reply.detail else {}
            return _error(
                _STATUS.get(reply.error or "error", 500), reply.error, **extra
            )
        if reply.status == noise.STATUS_ERROR:
            faillog.note(
                self._log,
                f"noise {reply.name} {reply.edge}: {reply.why}",
                detail=reply.detail,
            )
        return Response(
            200,
            {
                "ok": True,
                "name": reply.name,
                "edge": reply.edge,
                "status": reply.status,
                "why": reply.why,
                "commands": reply.commands,
                "ms": reply.ms,
                "total_ms": total_ms,
            },
        )


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 2)


def _wire_error(mode: str, body: bytes) -> str | None:
    """The stable error code if `body` is not a valid payload for `mode`, else None. Never raises."""
    try:
        if mode == MODE_PCM:
            wire.parse_pcm(body)
        else:
            wire.parse_validate(body)
    except wire.WireError as exc:
        return exc.code
    except (
        Exception
    ):  # noqa: BLE001 - anything unparsable is the caller's fault, not a 500
        return "invalid"
    return None


def _reply(r: Reply, mode: str, total_ms: float) -> Response:
    if not r.ok:
        err = r.error or "error"
        extra = {"detail": r.detail} if r.detail else {}
        return _error(_STATUS.get(err, 422), err, ms=r.ms, **extra)
    body: dict[str, Any] = {
        "ok": True,
        "mode": mode,
        "text": r.text,
        "reject": r.reject,
        "ms": r.ms,
        "frames": r.frames,
        # Outcome of the utterance (see docs/phone-receiver.md, "Reply fields").
        "status": r.status,
        "why": r.why,
        "kind": r.kind,
        "commands": r.commands,
        "total_ms": total_ms,
    }
    if isinstance(r.text, str) and len(r.text) > MAX_TEXT_CHARS:
        body["text"] = r.text[:MAX_TEXT_CHARS]
        body["text_truncated"] = True
    return Response(200, body)


def make_handler(api: ListenerApi) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        timeout = REQUEST_TIMEOUT_S  # a stalled client must not pin a worker
        # HTTP/1.0 (the default): one request per connection, so a body we refuse to
        # read can never be parsed as the next request.

        def _serve(self):
            try:
                resp = api.handle(
                    self.command, self.path, dict(self.headers), self.rfile
                )
            except Exception as exc:  # noqa: BLE001
                faillog.report(api.log, "request", exc)
                resp = _error(500, "internal")
            payload = resp.payload()
            self.send_response(resp.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            for name, value in resp.headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _serve

        def log_message(self, format, *args):
            pass  # request lines and identities stay out of the Talon log

    return Handler


class ListenerServer(HTTPServer):
    """HTTPServer with a fixed worker pool: Talon logs a stack-trace warning per thread
    a user script starts, so threads start once rather than per request."""

    allow_reuse_address = True
    WORKERS = 2
    BACKLOG = 8

    def __init__(self, address, handler, log: faillog.Log | None = None):
        self._log = log or print
        # A failed bind calls server_close from inside super().__init__, before any worker exists.
        self._workers: list[threading.Thread] = []
        super().__init__(address, handler)
        self._pending: queue.Queue = queue.Queue(maxsize=self.BACKLOG)
        self._workers = [
            threading.Thread(target=self._work, name=f"phone-listener-{n}", daemon=True)
            for n in range(self.WORKERS)
        ]
        for worker in self._workers:
            worker.start()

    def process_request(self, request, client_address):
        try:
            self._pending.put_nowait((request, client_address))
        except queue.Full:  # shed load rather than grow without bound
            self.shutdown_request(request)

    def _work(self):
        while True:
            item = self._pending.get()
            if item is None:
                return
            request, client_address = item
            try:
                self.finish_request(request, client_address)
            except Exception as exc:  # noqa: BLE001
                faillog.report(self._log, "connection", exc)
            finally:
                self.shutdown_request(request)

    def server_close(self):
        super().server_close()
        for _ in self._workers:
            self._pending.put(None)


def start(
    api: ListenerApi,
    port: int = DEFAULT_PORT,
    host: str = "127.0.0.1",
    assigned: Callable[[], Iterable[Any]] = netbind.tailnet_addresses,
):
    """Serve on `host`, which must be 127.0.0.1 or a tailnet address assigned to this Mac.

    Anything else raises `netbind.BindError` (a `ValueError`) before a socket exists. A tailnet
    bind also demands a key-authenticated `api`: the identity header is not set on that path,
    so an allow-list `api` there would be forgeable by every device on the tailnet.
    """
    plan = netbind.resolve_bind(host, assigned)
    if plan.tailnet and not api.uses_key:
        raise netbind.BindError("a tailnet bind requires shared-secret auth")
    server = ListenerServer((plan.host, port), make_handler(api), api.log)
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.05),
        name="phone-listener",
        daemon=True,
    )
    thread.start()
    return server, thread


def stop(server: ListenerServer) -> None:
    server.shutdown()
    server.server_close()
