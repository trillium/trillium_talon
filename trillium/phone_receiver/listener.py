"""HTTP front for the phone receiver: `POST /emission`, one utterance per request.

Pure stdlib, no `talon` import. `ListenerApi.handle` is the whole policy and takes plain
values, so tests drive it without a socket; `start` binds it to loopback or to this Mac's own
tailnet address (see `netbind`) and nothing else.

Order of checks, cheapest and least informative first, so a caller learns nothing it is not
cleared for and no body is read before it is: path (404), method (405), auth (403),
content type for the configured mode (415), rate (429), length headers (411/400/413), then
the body itself (400), and only then the service, which validates in Python before any
native call.

Auth has two forms, chosen by how the listener is served. With no `key` provider (the
loopback case, fronted by `tailscale serve` if at all) it is the `Tailscale-User-Login`
header matched against an allow-list; an empty list denies everyone, and any local process
can forge the header, which is the same boundary the palette feed has. With a `key` provider
(the tailnet bind, where nothing adds that header) it is the shared secret in
`X-Talon-Phone-Key`, compared in constant time, and the identity header is ignored.
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
from . import keyfile, netbind, wire
from .service import Reply

DEFAULT_PORT = 7403
PATH = "/emission"
IDENTITY_HEADER = "tailscale-user-login"
TS_HEADER = "x-utterance-ts"
MODE_EMISSION = "emission"
MODE_PCM = "pcm"
MODES = (MODE_EMISSION, MODE_PCM)
CONTENT_TYPES = {MODE_EMISSION: "application/x-talon-tpe1", MODE_PCM: "audio/l16"}
MAX_IDENTITY_LEN = 256
REQUEST_TIMEOUT_S = 10
RATE = (10, 1.0)  # utterances per window seconds, counted per server

# Wire-level mistakes are the caller's; the rest say why the host could not serve.
_STATUS = {
    "disabled": 503,
    "record_all_on": 503,
    "no_engine": 503,
    "engine_error": 500,
    "payload_too_large": 413,
}


class Backend(Protocol):
    def emission(self, buf: bytes) -> Reply: ...
    def pcm(self, buf: bytes, ts: float) -> Reply: ...


@dataclass
class Response:
    status: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


def _error(status: int, code: str, **extra: Any) -> Response:
    return Response(status, {"ok": False, "error": code, **extra})


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
    ):
        self._backend = backend
        self._get_mode = get_mode
        self._get_allowed = get_allowed
        self._get_key = key
        # Talon runs commands from its main thread; the glue passes a runner that hops there.
        self._run = runner or (lambda fn: fn())
        self._limiter = limiter or RateLimiter(*RATE)
        self._clock = clock or time.time

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
        try:
            return self._handle(method, target, headers, rfile)
        except Exception:  # noqa: BLE001 - nothing may escape into Talon
            return _error(500, "internal")

    def _handle(self, method, target, headers, rfile) -> Response:
        h = {str(k).lower(): v for k, v in headers.items()}
        path = target.split("?", 1)[0]
        if path != PATH:
            return _error(404, "not_found")
        if method != "POST":
            return Response(
                405, {"ok": False, "error": "method_not_allowed"}, {"Allow": "POST"}
            )
        if not self._authorized(h):
            return _error(403, "forbidden")
        mode = self._mode()
        if (
            mode not in MODES
        ):  # a typo in the setting must not fall through to either path
            return _error(503, "bad_mode")
        if not content_type_ok(mode, h.get("content-type")):
            return _error(
                415, "unsupported_media_type", want=CONTENT_TYPES[mode], mode=mode
            )
        allowed, retry_after = self._limiter.check()
        if not allowed:
            return Response(
                429,
                {"ok": False, "error": "rate_limited"},
                {"Retry-After": str(max(1, int(retry_after + 0.999)))},
            )
        if "transfer-encoding" in h:
            return _error(411, "length_required")
        try:
            length = parse_content_length(
                h.get("content-length"), wire.MAX_PAYLOAD_BYTES
            )
            body = read_body(rfile, length) if rfile is not None else b""
        except BodyError as exc:
            return _error(exc.status, exc.code)
        ts = 0.0
        if mode == MODE_PCM:
            ts = parse_ts(h.get(TS_HEADER), self._clock())
            if ts is None:
                return _error(400, "bad_ts")
            call = lambda: self._backend.pcm(body, ts)  # noqa: E731
        else:
            call = lambda: self._backend.emission(body)  # noqa: E731
        try:
            reply = self._run(call)
        except (TimeoutError, DispatchTimeout):
            return _error(504, "timeout")
        except Exception:  # noqa: BLE001
            return _error(500, "internal")
        return _reply(reply, mode)


def _reply(r: Reply, mode: str) -> Response:
    if not r.ok:
        err = r.error or "error"
        return _error(_STATUS.get(err, 422), err, ms=r.ms)
    return Response(
        200,
        {
            "ok": True,
            "mode": mode,
            "text": r.text,
            "reject": r.reject,
            "ms": r.ms,
            "frames": r.frames,
        },
    )


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
            except Exception:  # noqa: BLE001
                resp = _error(500, "internal")
            payload = json.dumps(resp.body, separators=(",", ":")).encode("utf-8")
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

    def __init__(self, address, handler):
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
                print(f"phone_listener: connection error: {type(exc).__name__}")
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
    server = ListenerServer((plan.host, port), make_handler(api))
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
