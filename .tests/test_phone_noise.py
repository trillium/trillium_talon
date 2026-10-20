"""`POST /noise`: body validation, the service (gating, stale seq, floor, dispatch), and the HTTP
policy in front of them. No Talon: the registry and the script runner are fakes, the key is a
throwaway string.
"""

import hashlib
import http.client
import importlib.util
import io
import json
import os
import types

import pytest
from talon import Module

from trillium.palette_feed.limits import RateLimiter
from trillium.phone_receiver import keyfile, ledger, listener, metrics, noise
from trillium.phone_receiver.hop import SchedulerUnavailable

KEY = "k" * 43
OTHER_KEY = "z" * 43
KEYHDR = {keyfile.HEADER: KEY}
LOGIN = "trillium@example.com"
GLUE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "trillium",
    "phone_receiver",
    "phone_receiver_live.py",
)


def uid(name="n-1"):
    return hashlib.sha256(name.encode()).hexdigest()[:32]


def event(**over):
    base = dict(
        v=1, name="lip-pop", edge="start", power=42.5, prob=0.93, ts=12.345,
        session="s1", seq=1,
    )  # fmt: skip
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def body_of(**over):
    return json.dumps(event(**over)).encode()


class Registry:
    """Fake `registry.impls.parrot_noises` plus a recorder for what ran."""

    def __init__(self, **keys):
        self.keys = {k: list(v) for k, v in keys.items()}
        self.ran = []

    def lookup(self, key):
        return self.keys.get(key, [])

    def run(self, impl, ev):
        self.ran.append((impl, ev))


class Flag:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make_service(reg=None, enabled=True, record_all=False, clock=None, **kw):
    reg = reg or Registry(**{"lip-pop": ["impl-a"]})
    svc = noise.NoiseService(
        reg.lookup,
        reg.run,
        Flag(enabled),
        Flag(record_all),
        clock=clock or Clock(),
        **kw,
    )
    return svc, reg


def make_api(svc=None, *, key=KEY, runner=None, **kw):
    kw.setdefault("noise_limiter", RateLimiter(1000, 1.0))
    api = listener.ListenerApi(
        types.SimpleNamespace(),  # the emission backend: never reached
        lambda: "emission",
        lambda: LOGIN,
        runner=runner,
        key=(lambda: key) if key is not None else None,
        metrics=metrics.Metrics(),
        limiter=RateLimiter(1000, 1.0),
        noises=svc,
        log=lambda *_: None,
        **kw,
    )
    return api


def post(api, body, ctype="application/json", key=uid(), auth=None, extra=None,
         length=None, path="/noise", method="POST"):  # fmt: skip
    h = {"Content-Length": str(len(body) if length is None else length)}
    if ctype:
        h["Content-Type"] = ctype
    if key is not None:
        h[ledger.ID_HEADER] = key
    h.update(KEYHDR if auth is None else auth)
    h.update(extra or {})
    return api.handle(method, path, h, io.BytesIO(body))


class TestParse:
    def test_a_good_body(self):
        ev = noise.parse_body(body_of())
        assert ev == noise.NoiseEvent("lip-pop", "start", 42.5, 0.93, 12.345, "s1", 1)
        assert ev.key == "lip-pop"

    def test_edge_defaults_to_start_and_picks_the_registry_key(self):
        assert noise.parse_body(body_of(edge=None)).edge == "start"
        assert noise.parse_body(body_of(edge="repeat")).key == "lip-pop:repeat"
        assert noise.parse_body(body_of(edge="stop")).key == "lip-pop:stop"

    @pytest.mark.parametrize(
        "over,code",
        [
            (dict(v=2), "bad_version"),
            (dict(v=None), "bad_version"),
            (dict(v=True), "bad_version"),
            (dict(name=None), "bad_name"),
            (dict(name=""), "bad_name"),
            (dict(name="x" * 33), "bad_name"),
            (dict(name="lip pop"), "bad_name"),
            (dict(name="../etc"), "bad_name"),
            (dict(name="a:repeat"), "bad_name"),
            (dict(name=7), "bad_name"),
            (dict(edge="hold"), "bad_edge"),
            (dict(session=None), "bad_session"),
            (dict(session="a b"), "bad_session"),
            (dict(session="s" * 65), "bad_session"),
            (dict(seq=None), "bad_seq"),
            (dict(seq=-1), "bad_seq"),
            (dict(seq=1.5), "bad_seq"),
            (dict(seq=True), "bad_seq"),
            (dict(power="9"), "bad_field"),
            (dict(power=True), "bad_field"),
            (dict(prob=1.5), "bad_field"),
            (dict(prob=-0.1), "bad_field"),
            (dict(ts=None), "bad_field"),
        ],
    )
    def test_field_errors_are_422(self, over, code):
        with pytest.raises(noise.NoiseError) as exc:
            noise.parse_body(body_of(**over))
        assert exc.value.code == code and exc.value.status == 422

    @pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
    def test_non_finite_numbers(self, token):
        raw = json.dumps(event()).replace("42.5", token).encode()
        with pytest.raises(noise.NoiseError) as exc:
            noise.parse_body(raw)
        assert exc.value.code == "non_finite"

    def test_huge_number_is_non_finite(self):
        raw = json.dumps(event()).replace("42.5", "1e999").encode()
        with pytest.raises(noise.NoiseError) as exc:
            noise.parse_body(raw)
        assert exc.value.code == "non_finite"

    @pytest.mark.parametrize("raw", [b"", b"{", b"[]", b"null", b"\xff\xfe", b'"x"'])
    def test_not_a_json_object_is_400(self, raw):
        with pytest.raises(noise.NoiseError) as exc:
            noise.parse_body(raw)
        assert exc.value.code == "bad_json" and exc.value.status == 400

    def test_deep_nesting_is_bad_json_not_a_crash(self):
        with pytest.raises(noise.NoiseError) as exc:
            noise.parse_body(b"[" * 500 + b"]" * 500)
        assert exc.value.code == "bad_json"

    def test_over_the_cap(self):
        with pytest.raises(noise.NoiseError) as exc:
            noise.parse_body(b" " * 1025)
        assert exc.value.status == 413


class TestService:
    def test_runs_the_last_impl_for_the_key(self):
        svc, reg = make_service(Registry(**{"lip-pop": ["first", "last"]}))
        ev = noise.parse_body(body_of())
        r = svc.handle(ev)
        assert (r.ok, r.status, r.why, r.commands) == (True, "ran", None, 1)
        assert reg.ran == [("last", ev)]

    def test_repeat_and_stop_use_their_own_keys(self):
        reg = Registry(**{"hiss": ["on"], "hiss:stop": ["off"]})
        svc, _ = make_service(reg)
        svc.handle(noise.parse_body(body_of(name="hiss", seq=1)))
        r = svc.handle(noise.parse_body(body_of(name="hiss", edge="stop", seq=2)))
        assert r.status == "ran" and [i for i, _ in reg.ran] == ["on", "off"]
        r = svc.handle(noise.parse_body(body_of(name="hiss", edge="repeat", seq=3)))
        assert (r.status, r.why, r.commands) == ("ignored", "no_trigger", 0)

    def test_no_trigger_is_ignored_not_an_error(self):
        svc, reg = make_service()
        r = svc.handle(noise.parse_body(body_of(name="cluck")))
        assert (r.ok, r.status, r.why, r.commands) == (True, "ignored", "no_trigger", 0)
        assert reg.ran == []

    def test_disabled_and_record_all_refuse_and_run_nothing(self):
        for kw, code in [
            (dict(enabled=False), "disabled"),
            (dict(record_all=True), "record_all_on"),
        ]:
            svc, reg = make_service(**kw)
            r = svc.handle(noise.parse_body(body_of()))
            assert (r.ok, r.error) == (False, code) and reg.ran == []

    def test_stale_seq_is_dropped_per_session_and_name(self):
        reg = Registry(**{"lip-pop": ["a"], "clap": ["c"]})
        clock = Clock()
        svc, _ = make_service(reg, clock=clock)

        def go(**over):
            clock.now += 1
            return svc.handle(noise.parse_body(body_of(**over)))

        assert go(seq=5).status == "ran"
        for seq in (5, 4, 0):
            r = go(seq=seq)
            assert (r.status, r.why) == ("ignored", "stale_seq")
        assert go(seq=6).status == "ran"
        assert (
            go(name="clap", seq=1).status == "ran"
        )  # another name has its own counter
        assert go(session="s2", seq=1).status == "ran"  # a restarted app starts clean
        assert len(reg.ran) == 4

    def test_stop_is_not_subject_to_the_start_seq_rule(self):
        reg = Registry(**{"hiss": ["on"], "hiss:stop": ["off"]})
        svc, _ = make_service(reg)
        svc.handle(noise.parse_body(body_of(name="hiss", seq=9)))
        r = svc.handle(noise.parse_body(body_of(name="hiss", edge="stop", seq=9)))
        assert r.status == "ran"

    def test_per_name_floor(self):
        clock = Clock()
        svc, reg = make_service(clock=clock)
        assert svc.handle(noise.parse_body(body_of(seq=1))).status == "ran"
        clock.now += 0.01
        r = svc.handle(noise.parse_body(body_of(seq=2)))
        assert (r.status, r.why) == ("ignored", "throttled")
        clock.now += 0.05
        assert svc.handle(noise.parse_body(body_of(seq=3))).status == "ran"
        assert len(reg.ran) == 2

    def test_a_dispatch_failure_is_status_error_with_the_class_only(self):
        reg = Registry(**{"lip-pop": ["a"]})
        reg.run = lambda impl, ev: (_ for _ in ()).throw(KeyError("secret-detail"))
        svc, _ = make_service(reg)
        r = svc.handle(noise.parse_body(body_of()))
        assert (r.ok, r.status, r.why, r.detail) == (
            True,
            "error",
            "dispatch_failed",
            "KeyError",
        )

    def test_a_registry_failure_is_a_refusal(self):
        reg = Registry()
        reg.lookup = lambda key: 1 / 0
        svc, _ = make_service(reg)
        r = svc.handle(noise.parse_body(body_of()))
        assert (r.ok, r.error, r.detail) == (
            False,
            "registry_error",
            "ZeroDivisionError",
        )

    def test_remembered_state_is_bounded(self):
        svc, _ = make_service(Registry())
        for n in range(noise.MAX_TRACKED * 2):
            svc.handle(noise.parse_body(body_of(session=f"s{n}", name=f"n{n}")))
        assert len(svc._last_seq) <= noise.MAX_TRACKED


class TestHttp:
    def test_a_good_noise_is_200_ran(self):
        svc, reg = make_service()
        r = post(make_api(svc), body_of())
        assert r.status == 200
        assert r.body["ok"] is True and r.body["status"] == "ran"
        assert r.body["why"] is None and r.body["commands"] == 1
        assert r.body["name"] == "lip-pop" and r.body["edge"] == "start"
        assert "id" in r.body and "instance" in r.body  # the ledger's stamp
        assert len(reg.ran) == 1

    def test_unknown_name_is_200_ignored(self):
        svc, reg = make_service()
        r = post(make_api(svc), body_of(name="cluck"))
        assert (r.status, r.body["status"], r.body["why"]) == (
            200,
            "ignored",
            "no_trigger",
        )
        assert reg.ran == []

    def test_without_a_service_the_path_is_404(self):
        assert post(make_api(None), body_of()).status == 404

    def test_other_paths_and_methods(self):
        svc, _ = make_service()
        api = make_api(svc)
        assert post(api, b"", method="GET").status == 405
        assert post(api, body_of(), path="/noises").status == 404

    @pytest.mark.parametrize(
        "auth", [{}, {keyfile.HEADER: OTHER_KEY}, {keyfile.HEADER: ""}]
    )
    def test_auth_failures_are_403_and_run_nothing(self, auth):
        svc, reg = make_service()
        r = post(make_api(svc), body_of(), auth=auth)
        assert r.status == 403 and reg.ran == []

    def test_no_key_loaded_denies_everyone(self):
        svc, reg = make_service()
        api = make_api(svc)
        api._get_key = lambda: None
        assert post(api, body_of()).status == 403 and reg.ran == []

    def test_loopback_identity_auth(self):
        svc, reg = make_service()
        api = make_api(svc, key=None)
        ok = post(api, body_of(), auth={listener.IDENTITY_HEADER: LOGIN})
        assert ok.status == 200 and len(reg.ran) == 1
        assert post(api, body_of(), auth={}).status == 403

    def test_auth_comes_before_everything_else(self):
        svc, _ = make_service()
        r = post(make_api(svc), b"junk", ctype="text/plain", key="bad", auth={})
        assert r.status == 403

    def test_content_type(self):
        svc, reg = make_service()
        api = make_api(svc)
        assert post(api, body_of(), ctype="text/plain").status == 415
        assert post(api, body_of(), ctype=None).status == 415
        assert (
            post(api, body_of(), ctype="Application/JSON; charset=utf-8").status == 200
        )
        assert len(reg.ran) == 1

    def test_utterance_id_is_required_and_checked(self):
        svc, reg = make_service()
        api = make_api(svc)
        missing = post(api, body_of(), key=None)
        assert (missing.status, missing.body["error"]) == (400, "missing_utterance_id")
        bad = post(api, body_of(), key="not-an-id")
        assert (bad.status, bad.body["error"]) == (400, "bad_utterance_id")
        assert reg.ran == []

    def test_size_cap_by_header_is_413_before_the_body_is_read(self):
        svc, reg = make_service()

        class Boom(io.BytesIO):
            def read(self, *a):
                raise AssertionError("body read")

        h = {"Content-Length": "1025", "Content-Type": "application/json",
             ledger.ID_HEADER: uid(), **KEYHDR}  # fmt: skip
        r = make_api(svc).handle("POST", "/noise", h, Boom())
        assert r.status == 413 and reg.ran == []

    def test_a_body_at_the_cap_is_read(self):
        svc, reg = make_service()
        pad = "p" * (noise.MAX_BODY_BYTES - len(body_of(session="")) - 20)
        raw = json.dumps({**event(), "pad": pad}).encode()
        assert len(raw) <= noise.MAX_BODY_BYTES
        assert post(make_api(svc), raw).status == 200

    @pytest.mark.parametrize("length", [None, "x", "-1"])
    def test_length_header_problems(self, length):
        svc, _ = make_service()
        h = {"Content-Type": "application/json", ledger.ID_HEADER: uid(), **KEYHDR}
        if length is not None:
            h["Content-Length"] = length
        r = make_api(svc).handle("POST", "/noise", h, io.BytesIO(body_of()))
        assert r.status in (400, 411)

    def test_chunked_is_refused(self):
        svc, _ = make_service()
        r = post(make_api(svc), body_of(), extra={"Transfer-Encoding": "chunked"})
        assert r.status == 411

    def test_truncated_body(self):
        svc, reg = make_service()
        r = post(make_api(svc), body_of(), length=len(body_of()) + 10)
        assert r.status == 400 and reg.ran == []

    @pytest.mark.parametrize(
        "raw,status,code",
        [
            (b"not json", 400, "bad_json"),
            (b"[]", 400, "bad_json"),
            (body_of(name="a b"), 422, "bad_name"),
            (body_of(v=9), 422, "bad_version"),
            (json.dumps(event()).replace("42.5", "NaN").encode(), 422, "non_finite"),
        ],
    )
    def test_bad_bodies_run_nothing(self, raw, status, code):
        svc, reg = make_service()
        r = post(make_api(svc), raw)
        assert (r.status, r.body["error"]) == (status, code) and reg.ran == []

    def test_rate_limit_has_its_own_bucket(self):
        svc, reg = make_service()
        api = make_api(svc, noise_limiter=RateLimiter(2, 60.0))
        clockless = [
            post(api, body_of(seq=n), key=uid(f"r{n}")).status for n in range(1, 4)
        ]
        assert clockless == [200, 200, 429]
        # the emission bucket was not touched
        assert api._limiter.check()[0]

    def test_refusals_map_to_503_and_the_id_stays_usable(self):
        flag = Flag(False)
        reg = Registry(**{"lip-pop": ["a"]})
        svc = noise.NoiseService(reg.lookup, reg.run, flag, Flag(False), clock=Clock())
        api = make_api(svc)
        first = post(api, body_of())
        assert (first.status, first.body["error"]) == (503, "disabled")
        flag.value = True
        again = post(api, body_of())  # same id: a retriable refusal is not replayed
        assert again.status == 200 and again.body["status"] == "ran"

    def test_record_all_is_503(self):
        svc, reg = make_service(record_all=True)
        r = post(make_api(svc), body_of())
        assert (r.status, r.body["error"]) == (503, "record_all_on") and reg.ran == []

    def test_replay_returns_the_stored_reply_and_does_not_dispatch_again(self):
        svc, reg = make_service()
        api = make_api(svc)
        first = post(api, body_of())
        again = post(api, body_of())
        assert first.status == again.status == 200
        assert again.headers.get(ledger.REPLAYED_HEADER) == "1"
        assert again.body["status"] == "ran" and again.body["id"] == first.body["id"]
        assert len(reg.ran) == 1

    def test_a_replayed_ignore_is_replayed_as_it_was(self):
        svc, reg = make_service()
        api = make_api(svc)
        post(api, body_of(seq=3), key=uid("a"))
        stale = post(api, body_of(seq=3), key=uid("b"))
        assert stale.body["why"] == "stale_seq"
        again = post(api, body_of(seq=3), key=uid("b"))
        assert (
            again.body["why"] == "stale_seq"
            and again.headers[ledger.REPLAYED_HEADER] == "1"
        )

    def test_a_new_id_with_an_old_seq_is_dropped_as_stale(self):
        svc, reg = make_service(clock=Clock())
        api = make_api(svc)
        assert post(api, body_of(seq=7), key=uid("a")).body["status"] == "ran"
        r = post(api, body_of(seq=7), key=uid("b"))
        assert (r.status, r.body["status"], r.body["why"]) == (
            200,
            "ignored",
            "stale_seq",
        )
        assert len(reg.ran) == 1

    def test_result_endpoint_finds_a_noise(self):
        svc, _ = make_service()
        api = make_api(svc)
        post(api, body_of())
        h = dict(KEYHDR)
        r = api.handle("GET", f"/result/{uid()}", h)
        assert r.status == 200 and r.body["reply"]["status"] == "ran"

    def test_dispatch_goes_through_the_runner(self):
        svc, reg = make_service()
        seen = []

        def runner(fn):
            seen.append("hop")
            return fn()

        assert post(make_api(svc, runner=runner), body_of()).status == 200
        assert seen == ["hop"]

    def test_scheduler_unavailable_is_503_and_nothing_ran(self):
        svc, reg = make_service()

        def runner(fn):
            raise SchedulerUnavailable("ResourceClosed")

        r = post(make_api(svc, runner=runner), body_of())
        assert (r.status, r.body["error"]) == (503, "scheduler_unavailable")
        assert reg.ran == []

    def test_timeout_is_504(self):
        svc, _ = make_service()

        def runner(fn):
            raise TimeoutError

        assert post(make_api(svc, runner=runner), body_of()).status == 504

    def test_an_unexpected_exception_is_500_internal(self):
        svc, _ = make_service()

        def runner(fn):
            raise RuntimeError("boom")

        r = post(make_api(svc, runner=runner), body_of())
        assert (r.status, r.body["error"]) == (500, "internal")

    def test_dispatch_error_status_is_a_200_the_phone_can_read(self):
        reg = Registry(**{"lip-pop": ["a"]})
        reg.run = lambda impl, ev: 1 / 0
        svc, _ = make_service(reg)
        r = post(make_api(svc), body_of())
        assert (r.status, r.body["status"], r.body["why"]) == (
            200,
            "error",
            "dispatch_failed",
        )

    def test_the_key_and_body_never_reach_the_log(self):
        lines = []
        reg = Registry(**{"lip-pop": ["a"]})
        reg.run = lambda impl, ev: 1 / 0
        svc, _ = make_service(reg)
        api = make_api(svc)
        api._log = lines.append
        post(api, body_of(session="sess-secret"))
        assert lines and not any(KEY in x or "sess-secret" in x for x in lines)

    def test_noise_requests_are_counted_apart_from_emissions(self):
        svc, _ = make_service()
        api = make_api(svc)
        post(api, body_of())
        s = api._metrics.summary()
        assert s["noise"]["last_n"]["n"] == 1 and s["emission"]["last_n"]["n"] == 0


class TestRealSocket:
    @pytest.fixture
    def server(self):
        reg = Registry(**{"lip-pop": ["a"]})
        svc, _ = make_service(reg)
        srv, _ = listener.start(make_api(svc), 0)
        try:
            yield srv, reg
        finally:
            listener.stop(srv)

    def call(self, srv, body, headers, path="/noise"):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        out = (resp.status, json.loads(resp.read()), dict(resp.getheaders()))
        conn.close()
        return out

    def test_post_replay_and_refusals_over_http(self, server):
        srv, reg = server
        h = {
            "Content-Type": "application/json",
            ledger.ID_HEADER: uid("sock"),
            **KEYHDR,
        }
        status, out, _ = self.call(srv, body_of(), h)
        assert status == 200 and out["status"] == "ran" and out["commands"] == 1
        status, again, hdrs = self.call(srv, body_of(), h)
        assert status == 200 and again["status"] == "ran"
        assert {k.lower() for k in hdrs} >= {"x-talon-replayed"}
        assert len(reg.ran) == 1
        wrong = {**h, keyfile.HEADER: OTHER_KEY}
        assert self.call(srv, body_of(), wrong)[0] == 403
        big = {**h, ledger.ID_HEADER: uid("sock2")}
        assert self.call(srv, b"x" * 2000, big)[0] == 413
        assert len(reg.ran) == 1


class TestGlue:
    def load(self, monkeypatch):
        monkeypatch.setattr(Module, "setting", lambda self, name, **kw: None)
        spec = importlib.util.spec_from_file_location(
            "trillium.phone_receiver._glue_probe_noise", GLUE_PATH
        )
        glue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(glue)
        return glue

    def test_lookup_reads_the_registry_parrot_noises_table(self, monkeypatch):
        glue = self.load(monkeypatch)
        table = {"lip-pop": ["x", "y"]}
        monkeypatch.setattr(
            glue,
            "registry",
            types.SimpleNamespace(impls=types.SimpleNamespace(parrot_noises=table)),
        )
        assert glue._noise_impls("lip-pop") == ["x", "y"]
        assert glue._noise_impls("clap") == []

    def test_dispatch_calls_run_talon_script_with_the_impl_script_and_a_frame(
        self, monkeypatch
    ):
        glue = self.load(monkeypatch)
        calls = []

        class Frame:
            def __init__(self, **kw):
                self.kw = kw

        owner = object()
        monkeypatch.setattr(glue, "ParrotFrame", Frame)
        monkeypatch.setattr(glue, "_owner", lambda: owner)
        monkeypatch.setattr(
            glue,
            "actions",
            types.SimpleNamespace(
                core=types.SimpleNamespace(run_talon_script=lambda *a: calls.append(a))
            ),
        )
        impl = types.SimpleNamespace(script="SCRIPT")
        ev = noise.parse_body(body_of(power=7, ts=3.5))
        glue._run_noise(impl, ev)
        ((ctx, script, frame),) = calls
        assert ctx is owner and script == "SCRIPT"
        assert frame.kw["power"] == 7 and frame.kw["ts"] == 3.5

    def test_the_service_is_wired_to_the_gate_and_record_all(self, monkeypatch):
        glue = self.load(monkeypatch)
        monkeypatch.setattr(glue, "_enabled", lambda: False)
        r = glue._noises.handle(noise.parse_body(body_of()))
        assert r.error == "disabled"
