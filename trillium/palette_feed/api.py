"""Request routing for the palette feed. Talon is reached only through `Backend`."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Mapping, Protocol
from urllib.parse import parse_qs, urlsplit

from .auth import is_authorized
from .denylist import denied_by
from .dispatch import DispatchTimeout
from .limits import BodyError, RateLimiter, parse_content_length, read_body
from .page import CONTENT_TYPE as PAGE_CONTENT_TYPE
from .page import html_page
from .serialize import referenced_lists
from .simparse import NoMatch, normalize_rule, parse_sim

MAX_PHRASE_LEN = 200
MAX_ID_LEN = 64
_LIST_NAME = re.compile(r"^[A-Za-z0-9_.]{1,100}$")


class Backend(Protocol):
    def state(self) -> dict[str, Any]: ...
    def commands(self) -> dict[str, Any]: ...
    def list_entries(self, name: str) -> list[str]: ...
    def modes(self) -> set[str]: ...
    def sim(self, phrase: str) -> str:
        """Raw `_sim` text; raises NoMatch when the phrase does not parse."""
        ...

    def execute(self, phrase: str) -> None:
        """Run the phrase like speech; raises DispatchTimeout if it never ran."""
        ...


@dataclass(frozen=True)
class Config:
    max_body_bytes: int = 4096
    require_command_mode: bool = True
    # Read endpoints answer without a token. Gated routes need one; with no token
    # configured at all they answer 401 (fail closed) rather than running anything.
    open_reads: bool = False
    # `/execute` answers without a token too. Opt-in per host, for a bind whose network
    # is the boundary: while this is on, any device that can reach the bind can run
    # Talon commands. A valid token is still accepted; it is simply not required.
    open_execute: bool = False


# GETs that `open_reads` publishes to any tailnet caller. `/` is the static phone page:
# it carries no secrets, and without it there is nothing for the phone to load.
_READ_PATHS = ("/", "/state", "/commands")


def _is_read(method: str, path: str) -> bool:
    return method == "GET" and (path in _READ_PATHS or path.startswith("/lists/"))


def _is_execute(method: str, path: str) -> bool:
    return method == "POST" and path == "/execute"


@dataclass
class Response:
    status: int
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    # `raw` is the exact response body; when it is set, `body` is ignored. It is how
    # the HTML page is served without going through the JSON encoder.
    content_type: str = "application/json"
    raw: bytes | None = None


def _error(status: int, code: str, **extra: Any) -> Response:
    return Response(status, {"ok": False, "error": code, **extra})


class PaletteApi:
    def __init__(
        self,
        token: str | None,
        backend: Backend,
        limiter: RateLimiter,
        config: Config = Config(),
    ):
        self._token = token
        self._backend = backend
        self._limiter = limiter
        self._config = config

    def _permitted(self, method: str, path: str, headers: Mapping[str, str]) -> bool:
        """Open reads, then an open `/execute`, then the token.

        An absent token can never authorize a gated route: it only stays out of the way
        when that route was explicitly opened.
        """
        if self._config.open_reads and _is_read(method, path):
            return True
        if self._config.open_execute and _is_execute(method, path):
            return True
        if self._token is None:
            return False
        return is_authorized(headers.get("authorization"), self._token)

    def handle(
        self,
        method: str,
        target: str,
        headers: Mapping[str, str],
        rfile: BinaryIO | None = None,
    ) -> Response:
        headers = {k.lower(): v for k, v in headers.items()}
        url = urlsplit(target)
        if not self._permitted(method, url.path, headers):
            return Response(
                401,
                {"ok": False, "error": "unauthorized"},
                {"WWW-Authenticate": "Bearer"},
            )
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        path = url.path
        if method == "GET":
            if path == "/":
                return Response(200, content_type=PAGE_CONTENT_TYPE, raw=html_page())
            if path == "/state":
                return Response(200, self._backend.state())
            if path == "/commands":
                return self._commands(query, headers)
            if path.startswith("/lists/"):
                return self._list(path[len("/lists/") :])
        elif method == "POST" and path == "/execute":
            return self._execute(query, headers, rfile)
        return _error(404, "not_found")

    def _commands(self, query: dict[str, str], headers: dict[str, str]) -> Response:
        payload = self._backend.commands()
        rev = payload["commands_rev"]
        etag = f'"{rev}"'
        if query.get("rev") == rev or headers.get("if-none-match") == etag:
            return Response(304, None, {"ETag": etag})
        needle = query.get("q", "").lower()
        if needle:
            kept = [c for c in payload["commands"] if needle in c["rule"].lower()]
            return Response(200, {**payload, "count": len(kept), "commands": kept})
        return Response(200, payload, {"ETag": etag})

    def _list(self, name: str) -> Response:
        allowed = referenced_lists(self._backend.commands()["commands"])
        if not _LIST_NAME.match(name) or name not in allowed:
            return _error(404, "unknown_list")
        return Response(
            200, {"name": name, "entries": self._backend.list_entries(name)}
        )

    def _execute(
        self, query: dict[str, str], headers: dict[str, str], rfile: BinaryIO | None
    ) -> Response:
        allowed, retry_after = self._limiter.check()
        if not allowed:
            return Response(
                429,
                {"ok": False, "error": "rate_limited"},
                {"Retry-After": str(max(1, int(retry_after + 0.999)))},
            )
        if "transfer-encoding" in headers:
            return _error(411, "length_required")
        try:
            length = parse_content_length(
                headers.get("content-length"), self._config.max_body_bytes
            )
            raw = read_body(rfile, length) if rfile is not None else b""
        except BodyError as exc:
            return _error(exc.status, exc.code)
        request = _parse_execute_body(raw)
        if isinstance(request, Response):
            return request
        phrase, command_id = request

        blocked = denied_by(phrase)
        if blocked:
            return _error(403, "denied")
        if (
            self._config.require_command_mode
            and query.get("force") != "1"
            and "command" not in self._backend.modes()
        ):
            return _error(423, "not_in_command_mode")

        try:
            matches = parse_sim(self._backend.sim(phrase))
        except NoMatch:
            return _error(422, "no_match")
        if len(matches) != 1:
            return _error(422, "not_single_command", count=len(matches))
        match = matches[0]
        if denied_by(match.rule):
            return _error(403, "denied")
        if command_id is not None:
            command = next(
                (
                    c
                    for c in self._backend.commands()["commands"]
                    if c["id"] == command_id
                ),
                None,
            )
            if command is None:
                return _error(404, "unknown_command")
            if normalize_rule(command["rule"]) != normalize_rule(match.rule):
                return _error(
                    409,
                    "rule_mismatch",
                    would_run={"rule": match.rule, "path": match.path},
                )
        result = {"matched_rule": match.rule, "path": match.path}
        if query.get("dry_run") == "1":
            return Response(200, {"ok": True, "dry_run": True, **result})
        try:
            self._backend.execute(phrase)
        except DispatchTimeout:
            return _error(504, "execute_timeout")
        return Response(200, {"ok": True, **result})


def _parse_execute_body(raw: bytes) -> tuple[str, str | None] | Response:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _error(400, "invalid_json")
    if not isinstance(data, dict):
        return _error(400, "invalid_json")
    phrase = data.get("phrase")
    command_id = data.get("id")
    if (
        not isinstance(phrase, str)
        or not phrase.strip()
        or len(phrase) > MAX_PHRASE_LEN
        or not phrase.isprintable()
    ):
        return _error(400, "invalid_phrase")
    if command_id is not None and (
        not isinstance(command_id, str) or len(command_id) > MAX_ID_LEN
    ):
        return _error(400, "invalid_id")
    return phrase.strip(), command_id
