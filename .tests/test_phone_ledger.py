"""The durable phone link: utterance ids make `POST /emission` idempotent and `GET /result/<id>`
answers "did it land?" after a lost reply.

Everything runs against the fake engine of `test_phone_listener` (no Talon, no model, no live
emission). The invariant under test is that a duplicate id never reaches the executor a second
time: each case counts calls on the fake engine and on the service the listener drives.
"""

import http.client
import io
import json
import threading
import uuid

import pytest
from test_phone_listener import (
    KEY,
    KEYHDR,
    LOGIN,
    PCM,
    TPE1,
    ExplodingBody,
    Rig,
    emission_body,
    pcm_body,
)

from trillium.palette_feed.limits import RateLimiter
from trillium.phone_receiver import keyfile, ledger, listener, wire
from trillium.phone_receiver.hop import SchedulerUnavailable
from trillium.phone_receiver.service import Reply

ID = "X-Talon-Utterance-Id"
REPLAYED = ledger.REPLAYED_HEADER
IDENTITY_FIELDS = {"id", "seq", "instance", "boot_time"}


@pytest.fixture
def rig():
    return Rig()


@pytest.fixture
def pcm_rig():
    return Rig(mode="pcm")


def new_id() -> str:
    return uuid.uuid4().hex


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def make_ledger(clock=None, **kw):
    return ledger.Ledger(clock=clock or Clock(), wall=lambda: 1_700_000_000.0, **kw)


def post(rig, uid, body=None, **kw):
    if body is None:
        body = emission_body() if rig.mode == "emission" else pcm_body()
    extra = {**(kw.pop("extra", None) or {})}
    if uid is not None:
        extra[ID] = uid
    return rig.post(body, extra=extra, **kw)


def result(rig, uid, login=LOGIN, extra=None, rfile=None):
    h = {}
    if login is not None:
        h["Tailscale-User-Login"] = login
    h.update(extra or {})
    return rig.api.handle("GET", f"/result/{uid}", h, rfile)


def spy_service(rig):
    """Count calls that reach the service (the executor behind the listener)."""
    calls = {"emission": 0, "pcm": 0}
    real_em, real_pcm = rig.service.emission, rig.service.pcm

    def emission(buf):
        calls["emission"] += 1
        return real_em(buf)

    def pcm(buf, ts):
        calls["pcm"] += 1
        return real_pcm(buf, ts)

    rig.service.emission, rig.service.pcm = emission, pcm
    return calls


class Gate:
    """A runner that parks inside the executor until released, to hold an id in flight."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.count = 0

    def __call__(self, fn):
        self.count += 1
        self.entered.set()
        assert self.release.wait(5), "gate never released"
        return fn()


class TestParseId:
    def test_absent_is_none(self):
        assert ledger.parse_id(None) is None

    @pytest.mark.parametrize(
        "value,key",
        [
            ("0123456789abcdef", "0123456789abcdef"),
            ("0123456789ABCDEF", "0123456789abcdef"),
            ("  0123456789abcdef  ", "0123456789abcdef"),
            (
                "123E4567-E89B-12D3-A456-426614174000",
                "123e4567e89b12d3a456426614174000",
            ),
            ("123e4567e89b12d3a456426614174000", "123e4567e89b12d3a456426614174000"),
            ("a" * 64, "a" * 64),
        ],
    )
    def test_accepts_hex_and_uuid_forms_and_canonicalises(self, value, key):
        assert ledger.parse_id(value) == key

    def test_uuid_forms_of_one_id_are_the_same_key(self):
        u = uuid.uuid4()
        assert ledger.parse_id(str(u).upper()) == ledger.parse_id(u.hex)

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "0123456789abcde",  # 15 hex digits
            "0123456789abcdeg",
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",  # 65
            "-" * 20,
            "0123-4567-89ab-cde",  # 15 hex digits once the hyphens are gone
            "0123456789abc def",
            "0123456789abcdéf",
            "../../0123456789abcdef",
            "0123456789abcdef/x",
        ],
    )
    def test_rejects_everything_else(self, value):
        with pytest.raises(ledger.BadId):
            ledger.parse_id(value)

    def test_surrounding_whitespace_including_a_newline_is_stripped(self):
        assert ledger.parse_id("0123456789abcdef\n") == "0123456789abcdef"


class TestLedger:
    def test_fresh_then_in_progress_then_replay(self):
        led = make_ledger()
        a = led.begin("k" * 16)
        assert a.kind == ledger.FRESH and a.entry.seq == 1 and a.entry.attempts == 1
        assert led.begin("k" * 16).kind == ledger.IN_PROGRESS
        led.finish(a.entry, 200, {"ok": True})
        b = led.begin("k" * 16)
        assert b.kind == ledger.REPLAY and b.entry.body == {"ok": True}
        assert b.entry.seq == 1  # a replay is not a new sequence number

    def test_seq_is_monotonic_across_ids(self):
        led = make_ledger()
        seqs = []
        for i in range(5):
            c = led.begin(f"{i:016x}")
            led.finish(c.entry, 200, {})
            seqs.append(c.entry.seq)
        assert seqs == [1, 2, 3, 4, 5]

    def test_ttl_expires_a_finished_entry(self):
        clock = Clock()
        led = make_ledger(clock, ttl_s=600)
        c = led.begin("a" * 16)
        led.finish(c.entry, 200, {"ok": True})
        clock.advance(599.9)
        assert led.begin("a" * 16).kind == ledger.REPLAY
        clock.advance(0.2)  # 600.1 s after it finished
        assert led.lookup("a" * 16) is None
        again = led.begin("a" * 16)
        assert again.kind == ledger.FRESH and again.entry.seq == 2

    def test_ttl_counts_from_the_finish_not_the_claim(self):
        clock = Clock()
        led = make_ledger(clock, ttl_s=600)
        c = led.begin("a" * 16)
        clock.advance(500)  # a slow execution
        led.finish(c.entry, 200, {})
        clock.advance(500)
        assert led.lookup("a" * 16) is not None

    def test_an_abandoned_in_flight_entry_expires_too(self):
        clock = Clock()
        led = make_ledger(clock, ttl_s=600)
        led.begin("a" * 16)
        clock.advance(601)
        assert led.begin("a" * 16).kind == ledger.FRESH

    def test_finishing_an_entry_that_expired_does_not_resurrect_a_newer_one(self):
        clock = Clock()
        led = make_ledger(clock, ttl_s=600)
        old = led.begin("a" * 16)
        clock.advance(601)
        new = led.begin("a" * 16)  # the stuck first attempt expired; this is a second
        led.finish(old.entry, 500, {"late": True})  # the first worker finally returns
        assert led.lookup("a" * 16).seq == new.entry.seq
        assert not led.lookup("a" * 16).done

    def test_retriable_entry_is_reclaimable_and_keeps_its_first_time(self):
        clock = Clock()
        led = make_ledger(clock)
        a = led.begin("a" * 16)
        led.finish(a.entry, 503, {"ok": False}, retriable=True)
        clock.advance(30)
        b = led.begin("a" * 16)
        assert b.kind == ledger.FRESH
        assert (b.entry.attempts, b.entry.seq) == (2, 2)
        assert b.entry.first == a.entry.first and b.entry.started == a.entry.first + 30

    def test_cap_evicts_the_oldest_finished_entry_and_never_one_in_flight(self):
        clock = Clock()
        led = make_ledger(clock, max_entries=3)
        keys = [f"{i:016x}" for i in range(1, 5)]
        busy = led.begin(keys[0])  # stays in flight, oldest
        for k in keys[1:3]:
            clock.advance(10)
            led.finish(led.begin(k).entry, 200, {})
        clock.advance(10)
        led.finish(led.begin(keys[3]).entry, 200, {})
        assert led.lookup(keys[0]) is not None and not led.lookup(keys[0]).done
        assert led.lookup(keys[1]) is None  # oldest finished went
        assert all(led.lookup(k) for k in (keys[2], keys[3]))
        led.finish(busy.entry, 200, {})

    def test_horizon_is_the_ttl_until_the_cap_evicts_early(self):
        clock = Clock()
        led = make_ledger(clock, ttl_s=600, max_entries=2)
        assert led.horizon_s() == 600
        for i in range(3):
            led.finish(led.begin(f"{i:016x}").entry, 200, {})
            clock.advance(10)
        # the first id (claimed 30 s ago) was evicted early: it, and anything older, may be lost
        assert led.lookup(f"{0:016x}") is None
        assert led.horizon_s() == pytest.approx(30)
        clock.advance(1000)
        assert led.horizon_s() == 600  # never more than the TTL

    def test_instances_differ_and_uptime_runs(self):
        clock = Clock()
        a, b = make_ledger(clock), make_ledger(clock)
        assert a.instance != b.instance and len(a.instance) == 16
        assert a.boot_time == 1_700_000_000.0
        clock.advance(12.5)
        assert a.uptime_s() == 12.5

    def test_of_many_racing_claims_exactly_one_is_fresh(self):
        led = make_ledger()
        kinds, gate = [], threading.Barrier(16)

        def go():
            gate.wait()
            kinds.append(led.begin("a" * 16).kind)

        threads = [threading.Thread(target=go) for _ in range(16)]
        [t.start() for t in threads]
        [t.join(5) for t in threads]
        assert kinds.count(ledger.FRESH) == 1
        assert kinds.count(ledger.IN_PROGRESS) == 15

    def test_unknown_and_view_shapes(self):
        clock = Clock()
        led = make_ledger(clock)
        assert led.unknown() == {
            "ok": False,
            "error": "unknown",
            "instance": led.instance,
            "boot_time": 1_700_000_000.0,
            "uptime_s": 0.0,
            "ttl_s": 600.0,
            "horizon_s": 600.0,
        }
        c = led.begin("a" * 16)
        v = led.view(c.entry)
        assert v["state"] == "in_progress" and "reply" not in v
        clock.advance(5)
        done = led.finish(c.entry, 200, {"ok": True})
        v = led.view(done)
        assert v["state"] == "done" and v["reply"] == {"ok": True}
        assert (v["http_status"], v["retriable"], v["attempts"]) == (200, False, 1)
        assert v["age_s"] == 5.0 and v["expires_in_s"] == 600.0


class TestNoIdIsUnchanged:
    def test_a_request_without_the_header_runs_every_time_and_carries_no_id_fields(
        self, rig
    ):
        r1, r2 = rig.post(emission_body()), rig.post(emission_body())
        assert r1.status == r2.status == 200 and rig.engine.calls == 2
        for r in (r1, r2):
            assert not IDENTITY_FIELDS & r.body.keys()
            assert REPLAYED not in r.headers
        assert result(rig, new_id()).status == 404  # and nothing was recorded

    def test_the_reply_fields_are_exactly_the_documented_ones(self, rig):
        assert set(rig.post(emission_body()).body) == {
            "ok",
            "mode",
            "text",
            "reject",
            "ms",
            "frames",
            "status",
            "why",
            "kind",
            "commands",
            "total_ms",
        }


class TestIdempotentPost:
    def test_first_request_runs_and_is_marked(self, rig):
        uid = new_id()
        r = post(rig, uid)
        assert r.status == 200 and rig.engine.calls == 1
        assert REPLAYED not in r.headers
        assert r.body["id"] == uid and r.body["seq"] == 1
        assert r.body["instance"] == rig.api.table.instance
        assert r.body["boot_time"] == rig.api.table.boot_time
        assert {"text", "status", "why", "kind", "commands"} <= r.body.keys()

    def test_a_repeat_is_replayed_and_the_executor_is_not_called_again(self, rig):
        calls = spy_service(rig)
        uid = new_id()
        first = post(rig, uid)
        again = post(rig, uid)
        third = post(rig, uid)
        assert again.status == 200 and again.headers[REPLAYED] == "1"
        assert again.body == first.body == third.body
        assert rig.engine.calls == 1 and calls == {"emission": 1, "pcm": 0}

    def test_the_replay_carries_the_original_seq_and_new_ids_get_new_ones(self, rig):
        a, b = new_id(), new_id()
        assert post(rig, a).body["seq"] == 1
        assert post(rig, b).body["seq"] == 2
        assert post(rig, a).body["seq"] == 1
        assert post(rig, new_id()).body["seq"] == 3
        assert rig.engine.calls == 3

    def test_the_id_names_the_utterance_not_its_bytes(self, rig):
        uid = new_id()
        first = post(rig, uid, emission_body())
        again = post(rig, uid, emission_body(n_pcm=8000))  # different audio, same id
        assert again.headers[REPLAYED] == "1" and again.body == first.body
        assert rig.engine.calls == 1

    @pytest.mark.parametrize(
        "second",
        [lambda u: u.upper(), lambda u: "-".join([u[:8], u[8:12], u[12:16], u[16:]])],
    )
    def test_spellings_of_one_id_are_one_id(self, rig, second):
        uid = new_id()
        post(rig, uid)
        assert post(rig, second(uid)).headers[REPLAYED] == "1"
        assert rig.engine.calls == 1

    def test_distinct_ids_each_run(self, rig):
        for _ in range(4):
            assert post(rig, new_id()).status == 200
        assert rig.engine.calls == 4

    def test_pcm_mode_is_covered_the_same_way(self, pcm_rig):
        calls = spy_service(pcm_rig)
        uid = new_id()
        first = post(pcm_rig, uid, extra={"X-Utterance-Ts": "2.5"})
        again = post(pcm_rig, uid, extra={"X-Utterance-Ts": "2.5"})
        assert first.body["mode"] == "pcm" and first.body["id"] == uid
        assert again.headers[REPLAYED] == "1" and again.body == first.body
        assert pcm_rig.engine.calls == 1 and calls == {"emission": 0, "pcm": 1}

    def test_a_pcm_fallback_retry_of_an_emission_that_landed_is_a_replay(self, rig):
        uid = new_id()
        first = post(rig, uid)
        rig.mode = "pcm"  # the phone fell back to PCM16 for the retry
        again = post(rig, uid, pcm_body())
        assert again.status == 200 and again.headers[REPLAYED] == "1"
        assert again.body == first.body and again.body["mode"] == "emission"
        assert rig.engine.calls == 1

    def test_an_emission_fallback_after_a_pcm_that_landed_is_a_replay(self, pcm_rig):
        uid = new_id()
        first = post(pcm_rig, uid)
        pcm_rig.mode = "emission"
        again = post(pcm_rig, uid, emission_body())
        assert again.headers[REPLAYED] == "1" and again.body == first.body
        assert pcm_rig.engine.calls == 1

    def test_a_replay_needs_no_engine_and_ignores_the_gate(self, rig):
        uid = new_id()
        first = post(rig, uid)
        rig.state["enabled"] = False  # the Mac was switched off after it landed
        again = post(rig, uid)
        assert again.status == 200 and again.body == first.body

    def test_ignored_outcomes_are_final_too(self, rig):
        rig.engine.forced = ("", True)  # the engine rejects the decode
        uid = new_id()
        first = post(rig, uid)
        assert first.body["status"] == "ignored" and first.body["why"] == "rejected"
        rig.engine.forced = None
        again = post(rig, uid)
        assert again.body == first.body and rig.engine.calls == 1


class TestMalformedIds:
    @pytest.mark.parametrize(
        "value", ["", "   ", "short", "x" * 32, "a" * 65, "0123456789abcde", "a b" * 8]
    )
    def test_a_present_but_unusable_id_is_400_and_never_runs(self, rig, value):
        r = post(rig, value)
        assert (r.status, r.body["error"]) == (400, "bad_utterance_id")
        assert rig.engine.calls == 0
        assert post(rig, None).status == 200  # and the listener still serves

    def test_the_id_is_checked_after_auth(self, rig):
        r = post(rig, "short", login="stranger@example.com")
        assert (r.status, r.body["error"]) == (403, "forbidden")

    def test_the_id_is_checked_before_the_body_is_read(self, rig):
        h = {
            "Tailscale-User-Login": LOGIN,
            "Content-Type": TPE1,
            "Content-Length": "10",
            ID: "short",
        }
        assert rig.api.handle("POST", "/emission", h, ExplodingBody()).status == 400


class TestWhatIsStored:
    """Only a request that reached the executor owns an id."""

    def test_a_wire_error_does_not_claim_the_id(self, rig):
        uid = new_id()
        bad = post(rig, uid, b"junk")
        assert bad.status == 422 and rig.engine.calls == 0
        assert result(rig, uid).status == 404
        ok = post(rig, uid)  # the corrected body, same id
        assert ok.status == 200 and REPLAYED not in ok.headers
        assert rig.engine.calls == 1

    def test_oversize_body_is_413_unread_and_claims_nothing(self, rig):
        uid = new_id()
        h = {
            "Tailscale-User-Login": LOGIN,
            "Content-Type": TPE1,
            "Content-Length": str(wire.MAX_PAYLOAD_BYTES + 1),
            ID: uid,
        }
        r = rig.api.handle("POST", "/emission", h, ExplodingBody())
        assert (r.status, r.body["error"]) == (413, "body_too_large")
        assert result(rig, uid).status == 404 and rig.engine.calls == 0

    def test_a_truncated_body_claims_nothing(self, rig):
        uid = new_id()
        r = post(rig, uid, b"abc", length=50)
        assert (r.status, r.body["error"]) == (400, "truncated_body")
        assert result(rig, uid).status == 404

    def test_a_forbidden_request_claims_nothing(self, rig):
        uid = new_id()
        assert post(rig, uid, login=None).status == 403
        assert result(rig, uid).status == 404

    def test_a_rate_limited_request_claims_nothing_and_may_be_retried(self):
        rig = Rig(limiter=RateLimiter(1, 60.0))
        post(rig, new_id())
        uid = new_id()
        r = post(rig, uid)
        assert r.status == 429 and "Retry-After" in r.headers
        assert result(rig, uid).status == 404

    def test_a_replay_still_costs_a_rate_limit_slot(self):
        rig = Rig(limiter=RateLimiter(2, 60.0))
        uid = new_id()
        post(rig, uid)
        post(rig, uid)
        assert post(rig, uid).status == 429 and rig.engine.calls == 1


class TestInFlight:
    def test_a_duplicate_while_the_first_runs_is_409_and_does_not_run(self):
        gate = Gate()
        rig = Rig(runner=gate)
        calls = spy_service(rig)
        uid = new_id()
        first = {}
        t = threading.Thread(target=lambda: first.update(r=post(rig, uid)))
        t.start()
        assert gate.entered.wait(5)

        dup = post(rig, uid)
        assert (dup.status, dup.body["error"]) == (409, "in_progress")
        assert dup.headers["Retry-After"] == "1" and dup.body["id"] == uid
        assert dup.body["instance"] == rig.api.table.instance
        assert gate.count == 1 and calls["emission"] == 0  # not started twice

        q = result(rig, uid)  # the status query sees it too
        assert (q.status, q.body["state"]) == (202, "in_progress")
        assert q.headers["Retry-After"] == "1" and "reply" not in q.body

        gate.release.set()
        t.join(5)
        assert first["r"].status == 200 and first["r"].body["id"] == uid
        replay = post(rig, uid)
        assert replay.headers[REPLAYED] == "1" and replay.body == first["r"].body
        assert gate.count == 1 and rig.engine.calls == 1

    def test_concurrent_posts_of_one_id_run_once(self):
        rig = Rig()
        calls = spy_service(rig)
        uid = new_id()
        body = emission_body()
        out, start = [], threading.Barrier(10)

        def go():
            start.wait()
            out.append(post(rig, uid, body))

        threads = [threading.Thread(target=go) for _ in range(10)]
        [t.start() for t in threads]
        [t.join(10) for t in threads]
        assert len(out) == 10
        assert calls["emission"] == 1 and rig.engine.calls == 1
        assert {r.status for r in out} <= {200, 409}
        fresh = [r for r in out if r.status == 200 and REPLAYED not in r.headers]
        assert len(fresh) == 1
        assert all(r.body["id"] == uid for r in out)

    def test_a_runner_that_dies_settles_the_id_as_a_final_internal_error(self):
        class Died(BaseException):
            pass

        def runner(fn):
            raise Died

        rig = Rig(runner=runner)
        uid = new_id()
        with pytest.raises(Died):
            post(rig, uid)
        q = result(rig, uid)
        assert q.status == 200 and q.body["state"] == "done"
        assert q.body["http_status"] == 500 and q.body["reply"]["error"] == "internal"
        assert q.body["retriable"] is False
        again = post(rig, uid)  # the command may have run: never run it again
        assert (again.status, again.headers[REPLAYED]) == (500, "1")


class TestRefusals:
    """Retriable: nothing ran, so the same id may be sent again and executes. Final: it may have
    run (or did), so the stored reply is replayed and the executor is not called again."""

    @pytest.mark.parametrize(
        "code,break_it,fix_it",
        [
            (
                "disabled",
                lambda r: r.state.update(enabled=False),
                lambda r: r.state.update(enabled=True),
            ),
            (
                "record_all_on",
                lambda r: r.state.update(record_all=True),
                lambda r: r.state.update(record_all=False),
            ),
        ],
    )
    def test_gate_refusals_are_retriable(self, code, break_it, fix_it):
        rig = Rig()
        break_it(rig)
        uid = new_id()
        refused = post(rig, uid)
        assert (refused.status, refused.body["error"]) == (503, code)
        assert refused.body["id"] == uid and rig.engine.calls == 0

        q = result(
            rig, uid
        )  # the phone can see that nothing ran, and that it may retry
        assert q.body["state"] == "done" and q.body["retriable"] is True
        assert q.body["http_status"] == 503 and q.body["reply"] == refused.body

        fix_it(rig)
        ran = post(rig, uid)
        assert ran.status == 200 and REPLAYED not in ran.headers
        assert ran.body["seq"] > refused.body["seq"] and rig.engine.calls == 1
        assert result(rig, uid).body["attempts"] == 2
        assert post(rig, uid).headers[REPLAYED] == "1"  # now it is final
        assert rig.engine.calls == 1

    def test_no_engine_is_retriable(self):
        rig = Rig()
        engine, rig.engine = rig.engine, None
        uid = new_id()
        refused = post(rig, uid)
        assert (refused.status, refused.body["error"]) == (503, "no_engine")
        assert result(rig, uid).body["retriable"] is True
        rig.engine = engine
        assert post(rig, uid).status == 200 and engine.calls == 1

    def test_scheduler_unavailable_is_retriable(self):
        broken = {"on": True}

        def runner(fn):
            if broken["on"]:
                raise SchedulerUnavailable("ResourceClosed")
            return fn()

        rig = Rig(runner=runner)
        uid = new_id()
        refused = post(rig, uid)
        assert (refused.status, refused.body["error"]) == (503, "scheduler_unavailable")
        assert result(rig, uid).body["retriable"] is True and rig.engine.calls == 0
        broken["on"] = False
        ran = post(rig, uid)
        assert ran.status == 200 and REPLAYED not in ran.headers
        assert rig.engine.calls == 1

    def test_a_service_level_4xx_is_retriable(self):
        class Backend:
            def __init__(self):
                self.replies = [Reply(False, "invalid"), Reply(True, None, "go")]

            def emission(self, buf):
                return self.replies.pop(0)

        api = listener.ListenerApi(
            Backend(), lambda: "emission", lambda: LOGIN, limiter=RateLimiter(100, 1)
        )
        body, uid = emission_body(), new_id()

        def send():
            h = {
                "Tailscale-User-Login": LOGIN,
                "Content-Type": TPE1,
                "Content-Length": str(len(body)),
                ID: uid,
            }
            return api.handle("POST", "/emission", h, io.BytesIO(body))

        assert send().status == 422
        assert (
            send().status == 200
        )  # executed afresh: the first never reached the engine
        assert REPLAYED in send().headers

    @pytest.mark.parametrize("exc", [TimeoutError, RuntimeError])
    def test_timeout_and_internal_error_are_final(self, exc):
        n = {"calls": 0}

        def runner(fn):
            n["calls"] += 1
            raise exc("boom")

        rig = Rig(runner=runner)
        uid = new_id()
        first = post(rig, uid)
        assert first.status in (504, 500)
        again = post(rig, uid)
        assert again.status == first.status and again.headers[REPLAYED] == "1"
        assert again.body == first.body and n["calls"] == 1  # the command may have run
        q = result(rig, uid)
        assert q.body["state"] == "done" and q.body["retriable"] is False

    def test_an_engine_error_is_final(self, rig):
        rig.engine.boom = True
        uid = new_id()
        first = post(rig, uid)
        assert (first.status, first.body["error"]) == (500, "engine_error")
        rig.engine.boom = False
        again = post(rig, uid)
        assert again.headers[REPLAYED] == "1" and again.body == first.body
        assert rig.engine.calls == 1


class TestRestart:
    def test_a_new_listener_has_a_new_instance_and_has_forgotten_the_id(self):
        old, new = Rig(), Rig()  # a reload builds a new ListenerApi, so a new Ledger
        uid = new_id()
        landed = post(old, uid)
        q = result(new, uid)
        assert q.status == 404 and q.body["error"] == "unknown"
        assert q.body["instance"] != landed.body["instance"]
        assert q.body["boot_time"] >= landed.body["boot_time"]
        # the phone is told the table is gone; re-sending runs the command on the new one
        assert post(new, uid).status == 200 and new.engine.calls == 1
        assert old.engine.calls == 1

    def test_the_instance_is_stable_within_a_process(self, rig):
        a, b = post(rig, new_id()), post(rig, new_id())
        assert a.body["instance"] == b.body["instance"]
        assert a.body["boot_time"] == b.body["boot_time"]
        assert result(rig, new_id()).body["instance"] == a.body["instance"]


class TestTtl:
    def test_an_expired_id_is_unknown_and_runs_again(self):
        clock = Clock()
        led = make_ledger(clock, ttl_s=600)
        rig = Rig(table=led)
        uid = new_id()
        first = post(rig, uid)
        clock.advance(300)
        assert post(rig, uid).headers[REPLAYED] == "1"
        q = result(rig, uid)
        assert q.status == 200 and q.body["expires_in_s"] == pytest.approx(300)
        assert q.body["age_s"] == pytest.approx(300)
        clock.advance(301)
        gone = result(rig, uid)
        assert (gone.status, gone.body["error"]) == (404, "unknown")
        assert gone.body["ttl_s"] == 600 and gone.body["uptime_s"] == pytest.approx(601)
        again = post(rig, uid)
        assert REPLAYED not in again.headers and again.body["seq"] > first.body["seq"]
        assert rig.engine.calls == 2

    def test_the_table_is_capped(self):
        led = make_ledger(max_entries=4)
        rig = Rig(table=led)
        ids = [new_id() for _ in range(10)]
        for uid in ids:
            post(rig, uid)
        held = [uid for uid in ids if result(rig, uid).status == 200]
        assert held == ids[-4:]  # the newest four
        unknown = result(rig, ids[0]).body
        # six ids went early, so "unknown" is only trustworthy for very recent ids
        assert unknown["horizon_s"] < led.ttl_s


class TestResult:
    def test_done_returns_the_stored_reply_in_a_wrapper(self, rig):
        uid = new_id()
        sent = post(rig, uid)
        q = result(rig, uid)
        assert q.status == 200
        b = q.body
        assert (b["ok"], b["state"], b["http_status"]) == (True, "done", 200)
        assert b["reply"] == sent.body and b["retriable"] is False
        assert (b["id"], b["seq"], b["attempts"]) == (uid, sent.body["seq"], 1)
        assert b["instance"] == sent.body["instance"]
        assert {"uptime_s", "age_s", "expires_in_s", "boot_time"} <= b.keys()
        assert rig.engine.calls == 1  # asking never runs anything

    def test_unknown_is_404_with_what_the_phone_needs_to_judge_it(self, rig):
        q = result(rig, new_id())
        assert (q.status, q.body["ok"], q.body["error"]) == (404, False, "unknown")
        assert q.body["instance"] == rig.api.table.instance
        assert {"boot_time", "uptime_s", "ttl_s", "horizon_s"} <= q.body.keys()
        assert q.body["ttl_s"] == ledger.DEFAULT_TTL_S

    def test_any_spelling_of_the_id_finds_it(self, rig):
        u = uuid.uuid4()
        post(rig, str(u))
        assert result(rig, u.hex.upper()).status == 200

    @pytest.mark.parametrize(
        "raw", ["", "short", "g" * 32, "a" * 65, "x/y", "%41" * 16]
    )
    def test_a_bad_id_in_the_path_is_400(self, rig, raw):
        r = result(rig, raw)
        assert (r.status, r.body["error"]) == (400, "bad_utterance_id")

    def test_only_get_and_only_under_result(self, rig):
        uid = new_id()
        r = rig.api.handle("POST", f"/result/{uid}", {"Tailscale-User-Login": LOGIN})
        assert (r.status, r.headers["Allow"]) == (405, "GET")
        assert rig.api.handle("GET", "/result", {}).status == 404
        assert rig.api.handle("GET", "/emission", {}).status == 405

    def test_the_query_string_is_ignored_and_the_body_is_never_read(self, rig):
        uid = new_id()
        post(rig, uid)
        h = {"Tailscale-User-Login": LOGIN, "Content-Length": "999999"}
        r = rig.api.handle("GET", f"/result/{uid}?x=1", h, ExplodingBody())
        assert r.status == 200

    def test_it_answers_whatever_the_mode_setting_says(self, rig):
        uid = new_id()
        post(rig, uid)
        rig.mode = "garbage"  # POST would be 503 bad_mode; asking needs no mode
        assert result(rig, uid).status == 200


class TestResultAuth:
    @pytest.mark.parametrize("login", [None, "", "stranger@example.com", "*"])
    def test_identity_mode_denies_a_missing_or_wrong_login(self, rig, login):
        uid = new_id()
        post(rig, uid)
        r = result(rig, uid, login=login)
        assert (r.status, r.body["error"]) == (403, "forbidden")
        assert "reply" not in r.body and "instance" not in r.body

    def test_an_empty_allow_list_denies_everyone(self):
        rig = Rig(allowed="")
        assert result(rig, new_id()).status == 403

    def test_auth_comes_before_the_id_is_looked_at(self, rig):
        assert result(rig, "short", login=None).status == 403

    @pytest.fixture
    def krig(self):
        return Rig(key=KEY)

    def test_key_mode_serves_the_right_key(self, krig):
        uid = new_id()
        post(krig, uid, login=None, extra=KEYHDR)
        assert result(krig, uid, login=None, extra=KEYHDR).status == 200

    @pytest.mark.parametrize(
        "presented", [None, "", " ", "z" * 43, KEY[:-1], KEY + "x"]
    )
    def test_key_mode_denies_a_wrong_or_missing_key(self, krig, presented):
        uid = new_id()
        post(krig, uid, login=None, extra=KEYHDR)
        extra = {} if presented is None else {keyfile.HEADER: presented}
        r = result(krig, uid, login=None, extra=extra)
        assert (r.status, r.body["error"]) == (403, "forbidden")
        assert KEY not in json.dumps(r.body) and KEY not in str(r.headers)

    def test_the_identity_header_does_not_stand_in_for_the_key(self, krig):
        assert result(krig, new_id(), login=LOGIN).status == 403

    def test_the_key_is_never_in_a_result_body(self, krig):
        uid = new_id()
        post(krig, uid, login=None, extra=KEYHDR)
        for r in (
            result(krig, uid, None, KEYHDR),
            result(krig, new_id(), None, KEYHDR),
        ):
            assert KEY not in json.dumps(r.body)


class TestResultRateLimit:
    def test_over_the_limit_is_429_with_retry_after(self):
        rig = Rig(result_limiter=RateLimiter(2, 60.0))
        uid = new_id()
        assert result(rig, uid).status == 404
        assert result(rig, uid).status == 404
        r = result(rig, uid)
        assert (r.status, r.body["error"]) == (429, "rate_limited")
        assert int(r.headers["Retry-After"]) >= 1

    def test_forbidden_requests_do_not_spend_the_limit(self):
        rig = Rig(result_limiter=RateLimiter(2, 60.0))
        for _ in range(10):
            assert result(rig, new_id(), login=None).status == 403
        assert result(rig, new_id()).status == 404

    def test_polling_cannot_starve_utterances_and_vice_versa(self):
        rig = Rig(result_limiter=RateLimiter(1, 60.0), limiter=RateLimiter(1, 60.0))
        assert result(rig, new_id()).status == 404
        assert result(rig, new_id()).status == 429
        assert post(rig, new_id()).status == 200  # the POST budget is untouched
        assert post(rig, new_id()).status == 429
        assert result(rig, new_id()).status == 429

    def test_the_default_result_limiter_is_its_own_object(self):
        api = listener.ListenerApi(object(), lambda: "emission", lambda: LOGIN)
        assert api._result_limiter is not api._limiter


class TestRealSocket:
    @pytest.fixture
    def server(self, rig):
        srv, _ = listener.start(rig.api, 0)
        try:
            yield srv, rig
        finally:
            listener.stop(srv)

    @staticmethod
    def call(srv, method, path, body=b"", headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        out = resp.status, json.loads(data), dict(resp.getheaders())
        conn.close()
        return out

    def test_lost_reply_story_over_a_real_socket(self, server):
        srv, rig = server
        uid = new_id()
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1, ID: uid}
        body = emission_body()

        s1, b1, h1 = self.call(srv, "POST", "/emission", body, h)  # the reply is "lost"
        assert (
            s1 == 200
            and b1["id"] == uid
            and REPLAYED.lower() not in {k.lower() for k in h1}
        )

        auth = {"Tailscale-User-Login": LOGIN}
        sq, bq, _ = self.call(
            srv, "GET", f"/result/{uid}", headers=auth
        )  # did it land?
        assert sq == 200 and bq["state"] == "done" and bq["reply"] == b1

        s2, b2, h2 = self.call(srv, "POST", "/emission", body, h)  # a naive retry
        lowered = {k.lower(): v for k, v in h2.items()}
        assert s2 == 200 and b2 == b1 and lowered[REPLAYED.lower()] == "1"
        assert rig.engine.calls == 1

        su, bu, _ = self.call(srv, "GET", f"/result/{new_id()}", headers=auth)
        assert (su, bu["error"]) == (404, "unknown")

    def test_a_forbidden_result_query_over_the_wire(self, server):
        srv, _ = server
        s, b, _ = self.call(srv, "GET", f"/result/{new_id()}")
        assert (s, b["error"]) == (403, "forbidden")

    def test_pcm_fallback_with_an_id_over_the_wire(self, server):
        srv, rig = server
        rig.mode = "pcm"
        uid = new_id()
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": PCM, ID: uid}
        s, b, _ = self.call(srv, "POST", "/emission", pcm_body(), h)
        assert s == 200 and b["mode"] == "pcm" and b["id"] == uid
        s2, b2, _ = self.call(srv, "POST", "/emission", pcm_body(), h)
        assert s2 == 200 and b2 == b and rig.engine.calls == 1
