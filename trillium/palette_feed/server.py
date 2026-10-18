"""Threaded stdlib HTTP server around PaletteApi. No Talon imports."""

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from .api import PaletteApi
from .options import DEFAULT_BIND, is_loopback

REQUEST_TIMEOUT_S = 10
DEFAULT_HOST = DEFAULT_BIND
DEFAULT_PORT = 7399


def make_handler(api: PaletteApi) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        timeout = REQUEST_TIMEOUT_S  # a stalled client must not pin a thread
        # HTTP/1.0 (the default): one request per connection, so a body we refuse
        # to read can never be parsed as the next request.

        def _serve(self):
            try:
                response = api.handle(
                    self.command, self.path, dict(self.headers), self.rfile
                )
            except Exception as exc:  # never let a handler bug reach Talon
                print(f"palette_feed: handler error: {type(exc).__name__}")
                body = b'{"ok":false,"error":"internal"}'
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if response.raw is not None:
                payload = response.raw
            elif response.body is None:
                payload = b""
            else:
                payload = json.dumps(response.body, separators=(",", ":")).encode(
                    "utf-8"
                )
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            # no-store, so a reload always asks this host rather than a phone's cache.
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        do_GET = _serve
        do_POST = _serve

        def log_message(self, format, *args):
            pass  # request lines can carry window-derived data; stay quiet

    return Handler


class PaletteHTTPServer(HTTPServer):
    """HTTPServer with a fixed worker pool.

    ThreadingHTTPServer starts a thread per request, and Talon logs a stack-trace
    warning for every thread a user script starts. A pool starts its threads once.
    """

    allow_reuse_address = True
    WORKERS = 4
    BACKLOG = 16

    def __init__(self, address, handler):
        super().__init__(address, handler)
        self._pending: queue.Queue = queue.Queue(maxsize=self.BACKLOG)
        self._workers = [
            threading.Thread(target=self._work, name=f"palette-feed-{n}", daemon=True)
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
            except Exception as exc:
                print(f"palette_feed: connection error: {type(exc).__name__}")
            finally:
                self.shutdown_request(request)

    def server_close(self):
        super().server_close()
        for _ in self._workers:
            self._pending.put(None)


def start(
    api: PaletteApi, host: str, port: int, allow_non_loopback: bool = False
) -> tuple[PaletteHTTPServer, threading.Thread]:
    """Serve `host:port`. A non-loopback host needs `allow_non_loopback=True`.

    Only the option resolver passes that flag, and only for an address the operator
    configured, so an accidental hardcoded host still refuses to expose the API.
    """
    if not allow_non_loopback and not is_loopback(host):
        raise ValueError(
            f"palette feed binds loopback only, pass allow_non_loopback=True for "
            f"{host!r}"
        )
    server = PaletteHTTPServer((host, port), make_handler(api))
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.05),
        name="palette-feed",
        daemon=True,
    )
    thread.start()
    return server, thread


def stop(server: PaletteHTTPServer) -> None:
    server.shutdown()
    server.server_close()
