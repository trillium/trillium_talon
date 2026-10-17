"""Tests for PaletteApi routing and the HTTP server, against a fake backend."""

import http.client
import io
import json
import socket
import threading

import pytest

from trillium.palette_feed import server
from trillium.palette_feed.api import Config, PaletteApi
from trillium.palette_feed.dispatch import DispatchTimeout
from trillium.palette_feed.limits import RateLimiter
from trillium.palette_feed.serialize import RawImpl, serialize_commands
from trillium.palette_feed.simparse import NoMatch

TOKEN = "t" * 43
AUTH = {"Authorization": f"Bearer {TOKEN}"}

SIM_PLAYBACK = '[1] "playback now"\n   path: user/pb.talon\n   rule: "playback now"'
SIM_BY_PHRASE = {
    "playback now": SIM_PLAYBACK,
    "sudo restart talon": (
        '[1] "sudo restart talon"\n   path: user/restart.talon\n'
        '   rule: "sudo (restart talon|talon restart)"'
    ),
    # a harmless-looking phrase whose matched rule is dangerous
    "innocent words": (
        '[1] "innocent words"\n   path: user/x.talon\n   rule: "sudo wifi off"'
    ),
    "other thing": '[1] "other thing"\n   path: user/o.talon\n   rule: "other thing"',
    "two things": SIM_PLAYBACK + '\n[2] "x"\n   path: user/o.talon\n   rule: "x"',
}


class FakeBackend:
    def __init__(self):
        self.executed = []
        self.mode_set = {"all", "command"}
        self.execute_error = None
        self._commands = serialize_commands(
            [
                [RawImpl("playback now", "user.pb.talon", 4, (0,))],
                [RawImpl("tab {user.tab_action}", "user.tabs.talon", 2, (0,))],
                [RawImpl("say <user.text>", "user.say.talon", 9, (0,))],
            ],
            lambda name: 6,
        )

    def state(self):
        return {"host": "h", "rev": "r1", "modes": sorted(self.mode_set)}

    def commands(self):
        return self._commands

    def list_entries(self, name):
        return ["open", "close"]

    def modes(self):
        return self.mode_set

    def sim(self, phrase):
        if phrase not in SIM_BY_PHRASE:
            raise NoMatch()
        return SIM_BY_PHRASE[phrase]

    def execute(self, phrase):
        if self.execute_error:
            raise self.execute_error
        self.executed.append(phrase)

    def id_of(self, rule):
        return next(c["id"] for c in self._commands["commands"] if c["rule"] == rule)


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def api(backend):
    return PaletteApi(
        TOKEN, backend, RateLimiter(100, 1.0), Config(max_body_bytes=1024)
    )


def post(api, payload, query="", headers=AUTH, raw=None, length=None):
    body = raw if raw is not None else json.dumps(payload).encode()
    hdrs = {**headers, "Content-Length": str(len(body) if length is None else length)}
    return api.handle("POST", "/execute" + query, hdrs, io.BytesIO(body))


class TestAuthGate:
    @pytest.mark.parametrize(
        "method, path",
        [
            ("GET", "/state"),
            ("GET", "/commands"),
            ("GET", "/lists/x"),
            ("POST", "/execute"),
            ("GET", "/nope"),
        ],
    )
    def test_everything_requires_a_token(self, api, backend, method, path):
        resp = api.handle(method, path, {}, io.BytesIO(b"{}"))
        assert resp.status == 401
        assert resp.headers["WWW-Authenticate"] == "Bearer"
        assert backend.executed == []

    def test_wrong_token_is_401(self, api):
        assert (
            api.handle("GET", "/state", {"Authorization": "Bearer nope"}).status == 401
        )

    def test_unauthenticated_execute_never_reaches_backend(self, api, backend):
        resp = post(api, {"phrase": "playback now"}, headers={})
        assert resp.status == 401 and backend.executed == []


class TestReads:
    def test_state(self, api):
        resp = api.handle("GET", "/state", AUTH)
        assert resp.status == 200 and resp.body["host"] == "h"

    def test_commands_with_etag(self, api):
        resp = api.handle("GET", "/commands", AUTH)
        assert resp.status == 200 and resp.body["count"] == 3
        assert resp.headers["ETag"] == f'"{resp.body["commands_rev"]}"'

    def test_commands_304_on_rev_query_and_if_none_match(self, api):
        rev = api.handle("GET", "/commands", AUTH).body["commands_rev"]
        assert api.handle("GET", f"/commands?rev={rev}", AUTH).status == 304
        assert (
            api.handle("GET", "/commands", {**AUTH, "If-None-Match": f'"{rev}"'}).status
            == 304
        )
        assert api.handle("GET", "/commands?rev=stale", AUTH).status == 200

    def test_commands_filter(self, api):
        resp = api.handle("GET", "/commands?q=TAB", AUTH)
        assert [c["rule"] for c in resp.body["commands"]] == ["tab {user.tab_action}"]
        assert resp.body["count"] == 1

    def test_lists_only_serves_referenced_lists(self, api):
        assert api.handle("GET", "/lists/user.tab_action", AUTH).body["entries"] == [
            "open",
            "close",
        ]
        assert api.handle("GET", "/lists/user.secret", AUTH).status == 404
        assert api.handle("GET", "/lists/../etc", AUTH).status == 404

    def test_unknown_route_and_method(self, api):
        assert api.handle("GET", "/nope", AUTH).status == 404
        assert api.handle("POST", "/state", AUTH).status == 404


class TestExecute:
    def test_runs_matching_phrase(self, api, backend):
        resp = post(
            api, {"phrase": "playback now", "id": backend.id_of("playback now")}
        )
        assert resp.status == 200
        assert resp.body == {
            "ok": True,
            "matched_rule": "playback now",
            "path": "user/pb.talon",
        }
        assert backend.executed == ["playback now"]

    def test_id_is_optional(self, api, backend):
        assert post(api, {"phrase": "playback now"}).status == 200

    def test_dry_run_does_not_execute(self, api, backend):
        resp = post(api, {"phrase": "playback now"}, "?dry_run=1")
        assert resp.status == 200 and resp.body["dry_run"] is True
        assert backend.executed == []

    def test_no_match_is_422(self, api, backend):
        assert post(api, {"phrase": "zzqx"}).status == 422
        assert backend.executed == []

    def test_rule_mismatch_is_409_with_would_run(self, api, backend):
        resp = post(api, {"phrase": "other thing", "id": backend.id_of("playback now")})
        assert resp.status == 409
        assert resp.body["would_run"] == {"rule": "other thing", "path": "user/o.talon"}
        assert backend.executed == []

    def test_unknown_id_is_404(self, api, backend):
        assert post(api, {"phrase": "playback now", "id": "deadbeef00"}).status == 404
        assert backend.executed == []

    def test_chained_commands_rejected(self, api, backend):
        resp = post(api, {"phrase": "two things"})
        assert resp.status == 422 and resp.body["count"] == 2
        assert backend.executed == []

    def test_denylisted_phrase_is_403_before_sim(self, api, backend):
        assert post(api, {"phrase": "sudo restart talon"}).status == 403
        assert backend.executed == []

    def test_denylisted_matched_rule_is_403(self, api, backend):
        assert post(api, {"phrase": "innocent words"}).status == 403
        assert backend.executed == []

    def test_requires_command_mode(self, api, backend):
        backend.mode_set = {"all", "sleep"}
        assert post(api, {"phrase": "playback now"}).status == 423
        assert backend.executed == []

    def test_force_overrides_command_mode(self, api, backend):
        backend.mode_set = {"all", "sleep"}
        assert post(api, {"phrase": "playback now"}, "?force=1").status == 200

    def test_command_mode_requirement_is_optional(self, backend):
        backend.mode_set = set()
        api = PaletteApi(
            TOKEN, backend, RateLimiter(10, 1.0), Config(require_command_mode=False)
        )
        assert post(api, {"phrase": "playback now"}).status == 200

    def test_force_does_not_bypass_denylist(self, api, backend):
        assert post(api, {"phrase": "sudo restart talon"}, "?force=1").status == 403

    def test_execute_timeout_is_504(self, api, backend):
        backend.execute_error = DispatchTimeout()
        assert post(api, {"phrase": "playback now"}).status == 504

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"phrase": ""},
            {"phrase": "   "},
            {"phrase": 5},
            {"phrase": "a\nb"},
            {"phrase": "x" * 201},
            {"phrase": "ok", "id": 5},
            {"phrase": "ok", "id": "x" * 65},
            [1],
            "str",
        ],
    )
    def test_invalid_payloads_are_400(self, api, backend, payload):
        assert post(api, payload).status == 400
        assert backend.executed == []

    def test_invalid_json_is_400(self, api):
        assert post(api, None, raw=b"{not json").status == 400
        assert post(api, None, raw=b"\xff\xfe").status == 400

    def test_oversized_body_is_413_and_unread(self, api):
        rfile = io.BytesIO(b"x" * 2000)
        resp = api.handle("POST", "/execute", {**AUTH, "Content-Length": "2000"}, rfile)
        assert resp.status == 413
        assert rfile.tell() == 0

    def test_missing_content_length_is_411(self, api):
        assert api.handle("POST", "/execute", AUTH, io.BytesIO(b"{}")).status == 411

    def test_chunked_is_rejected(self, api):
        hdrs = {**AUTH, "Transfer-Encoding": "chunked", "Content-Length": "2"}
        assert api.handle("POST", "/execute", hdrs, io.BytesIO(b"{}")).status == 411

    def test_truncated_body_is_400(self, api):
        assert post(api, None, raw=b'{"phrase"', length=50).status == 400


class TestRateLimit:
    def test_execute_is_rate_limited_with_retry_after(self, backend):
        now = [0.0]
        api = PaletteApi(TOKEN, backend, RateLimiter(2, 1.0, clock=lambda: now[0]))
        assert post(api, {"phrase": "playback now"}).status == 200
        assert post(api, {"phrase": "playback now"}).status == 200
        resp = post(api, {"phrase": "playback now"})
        assert resp.status == 429 and resp.headers["Retry-After"] == "1"
        assert len(backend.executed) == 2

    def test_unauthenticated_calls_do_not_spend_the_budget(self, backend):
        api = PaletteApi(TOKEN, backend, RateLimiter(1, 60.0))
        for _ in range(5):
            assert post(api, {"phrase": "playback now"}, headers={}).status == 401
        assert post(api, {"phrase": "playback now"}).status == 200

    def test_reads_are_not_limited(self, backend):
        api = PaletteApi(TOKEN, backend, RateLimiter(1, 60.0))
        for _ in range(5):
            assert api.handle("GET", "/state", AUTH).status == 200


@pytest.fixture
def live(backend):
    api = PaletteApi(TOKEN, backend, RateLimiter(100, 1.0), Config(max_body_bytes=1024))
    srv, _ = server.start(api, "127.0.0.1", 0)
    yield srv.server_address[1]
    server.stop(srv)


def call(port, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), data


class TestHttpServer:
    def test_round_trip_over_a_real_socket(self, live, backend):
        status, headers, data = call(live, "GET", "/state", AUTH)
        assert status == 200 and json.loads(data)["host"] == "h"
        assert headers["Content-Type"] == "application/json"
        assert headers["Cache-Control"] == "no-store"

    def test_401_over_the_wire(self, live):
        status, _, data = call(live, "GET", "/commands")
        assert status == 401 and json.loads(data)["error"] == "unauthorized"

    def test_execute_over_the_wire(self, live, backend):
        body = json.dumps({"phrase": "playback now"}).encode()
        status, _, data = call(live, "POST", "/execute", AUTH, body)
        assert status == 200 and backend.executed == ["playback now"]

    def test_304_has_no_body(self, live):
        rev = json.loads(call(live, "GET", "/commands", AUTH)[2])["commands_rev"]
        status, _, data = call(live, "GET", f"/commands?rev={rev}", AUTH)
        assert status == 304 and data == b""

    def test_backend_crash_is_500_not_a_dead_server(self, live, backend):
        backend.state = lambda: 1 / 0
        status, _, data = call(live, "GET", "/state", AUTH)
        assert status == 500 and json.loads(data)["error"] == "internal"
        assert call(live, "GET", "/commands", AUTH)[0] == 200

    def test_idle_connection_does_not_block_other_clients(self, live):
        idle = socket.create_connection(("127.0.0.1", live), timeout=5)
        try:
            assert call(live, "GET", "/state", AUTH)[0] == 200
        finally:
            idle.close()

    def test_server_start_launches_a_fixed_number_of_threads(self, live):
        before = threading.active_count()
        for _ in range(10):
            call(live, "GET", "/state", AUTH)
        assert threading.active_count() == before

    def test_refuses_non_loopback_bind(self, backend):
        api = PaletteApi(TOKEN, backend, RateLimiter(1, 1.0))
        for host in ("0.0.0.0", "192.168.1.5", "100.64.0.1", "example.com"):
            with pytest.raises(ValueError, match="loopback"):
                server.start(api, host, 0)

    def test_default_host_is_loopback(self):
        assert server.DEFAULT_HOST == "127.0.0.1"
        assert server.DEFAULT_PORT == 7399
