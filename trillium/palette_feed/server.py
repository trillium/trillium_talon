"""Threaded stdlib HTTP server around PaletteApi. No Talon imports."""

import ipaddress
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from .api import PaletteApi

REQUEST_TIMEOUT_S = 10
DEFAULT_HOST = "127.0.0.1"
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
            payload = (
                b""
                if response.body is None
                else json.dumps(response.body, separators=(",", ":")).encode("utf-8")
            )
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
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
    api: PaletteApi, host: str, port: int
) -> tuple[PaletteHTTPServer, threading.Thread]:
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise ValueError(f"palette feed binds loopback only, got {host!r}")
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
