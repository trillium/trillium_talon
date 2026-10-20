"""Latency and byte metrics: the maths in `metrics`, and how `ListenerApi` records and serves them
(`GET /metrics`, `X-Talon-Server-Ms`, `X-Talon-Client-Rtt-Ms`). No Talon, no live listener.
"""

import http.client
import importlib.util
import io
import json
import math
import os
import types

import pytest
import talon
from talon import Module

from trillium.palette_feed.limits import RateLimiter
from trillium.phone_receiver import (
    keyfile,
    ledger,
    listener,
    metrics,
    recordings,
    snippet,
    snippet_ledger,
)
from trillium.phone_receiver.metrics import (
    EMISSION,
    SNIPPET,
    Metrics,
    Sample,
    Trace,
    percentile,
)
from trillium.phone_receiver.service import Reply

KEY = "k" * 43
KEYHDR = {keyfile.HEADER: KEY}
PRIVATE_ID = "deadbeefcafe0123456789abcdef0123"
HOUR = 3600
GLUE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "trillium",
    "phone_receiver",
    "phone_receiver_live.py",
)
T0 = 1_800_000_000 - (1_800_000_000 % HOUR)  # an exact UTC hour boundary


def sample(
    kind=EMISSION,
    at=T0,
    status=200,
    total=10.0,
    req=100,
    resp=50,
    receive=1.0,
    decode=2.0,
    dispatch=7.0,
):
    return Sample(kind, at, status, req, resp, total, receive, decode, dispatch)


class TestPercentile:
    def test_nearest_rank_on_a_known_series(self):
        data = list(range(1, 101))
        assert percentile(data, 50) == 50
        assert percentile(data, 95) == 95
        assert percentile(data, 100) == 100
        assert percentile(data, 1) == 1

    def test_it_is_always_an_observed_value(self):
        data = [3.0, 9.0, 4.0, 1.0]
        for p in (1, 25, 50, 75, 95, 99, 100):
            assert percentile(data, p) in data

    def test_small_samples(self):
        assert percentile([7.0], 50) == 7.0 and percentile([7.0], 95) == 7.0
        assert percentile([5.0, 1.0], 50) == 1.0  # rank ceil(0.5 * 2) = 1
        assert percentile([5.0, 1.0], 95) == 5.0  # rank ceil(1.9) = 2
        assert percentile([1, 2, 3, 4, 5], 50) == 3

    def test_unsorted_input_and_no_mutation(self):
        data = [5.0, 1.0, 3.0]
        assert percentile(data, 50) == 3.0
        assert data == [5.0, 1.0, 3.0]

    def test_empty_is_none(self):
        assert percentile([], 50) is None

    def test_the_rank_never_leaves_the_data(self):
        assert percentile([1.0, 2.0], 0.0001) == 1.0
        assert percentile([1.0, 2.0], 100) == 2.0

    def test_matches_the_definition_across_sizes(self):
        for n in range(1, 40):
            data = list(range(n))
            for p in (50, 95):
                assert percentile(data, p) == data[math.ceil(p / 100 * n) - 1]


class TestTrace:
    def clock(self, *ticks):
        it = iter(ticks)
        return lambda: next(it)

    def test_phases_are_the_gaps_between_marks(self):
        t = Trace(self.clock(1.000, 1.010, 1.030, 1.080, 1.100))
        t.mark("received")
        t.mark("decoded")
        t.mark("dispatched")
        assert t.timings() == {
            "receive_ms": 10.0,
            "decode_ms": 20.0,
            "dispatch_ms": 50.0,
            "total_ms": 100.0,
        }

    def test_a_request_refused_early_has_only_a_total(self):
        t = Trace(self.clock(0.0, 0.004))
        assert t.timings() == {
            "receive_ms": None,
            "decode_ms": None,
            "dispatch_ms": None,
            "total_ms": 4.0,
        }

    def test_dispatch_without_a_decode_phase_counts_from_the_receive(self):
        t = Trace(self.clock(0.0, 0.010, 0.060, 0.070))
        t.mark("received")
        t.mark("dispatched")
        out = t.timings()
        assert out["decode_ms"] is None and out["dispatch_ms"] == 50.0

    def test_a_request_that_stopped_after_the_decode(self):
        t = Trace(self.clock(0.0, 0.010, 0.020, 0.030))
        t.mark("received")
        t.mark("decoded")
        out = t.timings()
        assert out["decode_ms"] == 10.0 and out["dispatch_ms"] is None

    def test_a_later_mark_replaces_an_earlier_one(self):
        t = Trace(self.clock(0.0, 0.010, 0.020, 0.030))
        t.mark("received")
        t.mark("received")
        assert t.timings()["receive_ms"] == 20.0


class TestSummary:
    def test_an_empty_summary_has_every_field_and_no_numbers(self):
        m = Metrics(clock=lambda: T0)
        s = m.summary()
        assert s["ok"] is True and s["window"] == metrics.WINDOW
        assert s["generated_at"].endswith("Z") and s["client_rtt_rejected"] == 0
        for kind in (EMISSION, SNIPPET):
            last = s[kind]["last_n"]
            assert last["n"] == 0 and last["by_status"] == {}
            assert last["total_ms"] == {"p50": None, "p95": None}
            assert s[kind]["hours"] == []
            assert s[kind]["client_rtt_ms"]["last_n"] == {
                "n": 0,
                "p50": None,
                "p95": None,
            }

    def test_percentiles_come_from_the_200s_only(self):
        m = Metrics(clock=lambda: T0)
        for ms in (10, 20, 30, 40, 50):
            m.record(sample(total=float(ms)))
        for _ in range(20):
            m.record(sample(status=403, total=0.05))  # answered in microseconds
        last = m.summary()[EMISSION]["last_n"]
        assert last["n"] == 25 and last["ok"] == 5
        assert last["total_ms"] == {"p50": 30.0, "p95": 50.0}
        assert last["by_status"] == {"200": 5, "403": 20}

    def test_each_timing_is_summarised_apart(self):
        m = Metrics(clock=lambda: T0)
        for i in range(1, 11):
            m.record(
                sample(receive=float(i), decode=float(i * 2), dispatch=float(i * 3))
            )
        last = m.summary()[EMISSION]["last_n"]
        assert last["receive_ms"] == {"p50": 5.0, "p95": 10.0}
        assert last["decode_ms"] == {"p50": 10.0, "p95": 20.0}
        assert last["dispatch_ms"] == {"p50": 15.0, "p95": 30.0}

    def test_a_missing_phase_is_left_out_of_that_phase_only(self):
        m = Metrics(clock=lambda: T0)
        m.record(sample(decode=None, dispatch=None, receive=None, total=9.0))
        last = m.summary()[EMISSION]["last_n"]
        assert last["total_ms"]["p50"] == 9.0
        assert last["decode_ms"] == {"p50": None, "p95": None}

    def test_bytes_are_totalled_over_every_response_and_percentiled_over_the_200s(self):
        m = Metrics(clock=lambda: T0)
        m.record(sample(req=100, resp=40))
        m.record(sample(req=300, resp=60))
        m.record(sample(status=413, req=0, resp=30))
        last = m.summary()[EMISSION]["last_n"]
        assert (last["bytes_in"], last["bytes_out"]) == (400, 130)
        assert last["req_bytes"] == {"p50": 100.0, "p95": 300.0}
        assert last["resp_bytes"] == {"p50": 40.0, "p95": 60.0}

    def test_kinds_are_kept_apart(self):
        m = Metrics(clock=lambda: T0)
        m.record(sample(kind=EMISSION, total=5.0))
        m.record(sample(kind=SNIPPET, total=500.0))
        s = m.summary()
        assert s[EMISSION]["last_n"]["total_ms"]["p50"] == 5.0
        assert s[SNIPPET]["last_n"]["total_ms"]["p50"] == 500.0

    def test_last_n_is_the_window_newest_requests(self):
        m = Metrics(clock=lambda: T0, window=3)
        for ms in (1, 2, 3, 100, 200, 300):
            m.record(sample(total=float(ms)))
        s = m.summary()
        assert s["window"] == 3
        last = s[EMISSION]["last_n"]
        assert last["n"] == 3 and last["total_ms"] == {"p50": 200.0, "p95": 300.0}

    def test_retention_drops_the_oldest(self):
        m = Metrics(clock=lambda: T0, window=100, retain=5)
        for ms in range(10):
            m.record(sample(total=float(ms)))
        assert m.summary()[EMISSION]["last_n"]["n"] == 5
        assert m.summary()[EMISSION]["last_n"]["total_ms"]["p50"] == 7.0

    def test_hours_are_utc_buckets_oldest_first(self):
        m = Metrics(clock=lambda: T0 + 3 * HOUR)
        m.record(sample(at=T0 + 10, total=10.0))
        m.record(sample(at=T0 + HOUR - 1, total=30.0))  # same hour
        m.record(sample(at=T0 + HOUR, total=100.0))  # next hour, on the boundary
        m.record(sample(at=T0 + 2 * HOUR + 5, status=429, total=0.1))
        hours = m.summary()[EMISSION]["hours"]
        assert [h["hour"] for h in hours] == [
            "2027-01-15T08:00:00Z",
            "2027-01-15T09:00:00Z",
            "2027-01-15T10:00:00Z",
        ]
        assert hours[0]["n"] == 2 and hours[0]["total_ms"] == {"p50": 10.0, "p95": 30.0}
        assert hours[1]["n"] == 1 and hours[1]["total_ms"]["p50"] == 100.0
        assert hours[2]["by_status"] == {"429": 1} and hours[2]["ok"] == 0

    def test_only_the_newest_day_of_hours_is_shown(self):
        m = Metrics(clock=lambda: T0 + 40 * HOUR)
        for h in range(40):
            m.record(sample(at=T0 + h * HOUR))
        hours = m.summary()[EMISSION]["hours"]
        assert len(hours) == metrics.HOURS
        assert hours[-1]["hour"] > hours[0]["hour"]

    def test_hours_cover_samples_older_than_the_last_n_window(self):
        m = Metrics(clock=lambda: T0 + HOUR, window=2)
        for i in range(6):
            m.record(sample(at=T0 + i, total=float(i)))
        s = m.summary()[EMISSION]
        assert s["last_n"]["n"] == 2 and s["hours"][0]["n"] == 6

    def test_the_summary_is_json_and_holds_nothing_but_numbers_and_labels(self):
        m = Metrics(clock=lambda: T0)
        m.record(sample())
        m.record_client_rtt(EMISSION, 12.0)
        text = json.dumps(m.summary())
        assert "phrase" not in text and "text" not in text and "audio" not in text

    def test_generated_at_is_the_clock(self):
        assert (
            Metrics(clock=lambda: T0).summary()["generated_at"]
            == "2027-01-15T08:00:00Z"
        )


class TestClientRtt:
    def test_kept_and_summarised(self):
        m = Metrics(clock=lambda: T0)
        for ms in (100, 200, 300, 400):
            assert m.record_client_rtt(SNIPPET, ms) is True
        rtt = m.summary()[SNIPPET]["client_rtt_ms"]
        assert rtt["last_n"] == {"n": 4, "p50": 200.0, "p95": 400.0}
        assert rtt["hours"][0]["n"] == 4
        assert m.summary()[EMISSION]["client_rtt_ms"]["last_n"]["n"] == 0

    @pytest.mark.parametrize(
        "kind,ms",
        [
            (EMISSION, -1),
            (EMISSION, float("nan")),
            (EMISSION, float("inf")),
            (EMISSION, metrics.MAX_RTT_MS + 1),
            (EMISSION, True),
            (EMISSION, "12"),
            (EMISSION, None),
            ("telemetry", 5.0),
        ],
    )
    def test_unusable_values_are_counted_not_kept(self, kind, ms):
        m = Metrics(clock=lambda: T0)
        assert m.record_client_rtt(kind, ms) is False
        s = m.summary()
        assert s["client_rtt_rejected"] == 1
        assert s[EMISSION]["client_rtt_ms"]["last_n"]["n"] == 0

    def test_zero_and_the_ceiling_are_usable(self):
        m = Metrics(clock=lambda: T0)
        assert m.record_client_rtt(EMISSION, 0) and m.record_client_rtt(
            EMISSION, metrics.MAX_RTT_MS
        )


class TestTickLine:
    def test_none_when_nothing_happened(self):
        assert Metrics(clock=lambda: T0).tick_line() is None

    def test_one_line_over_the_requests_since_the_last_call(self):
        m = Metrics(clock=lambda: T0)
        for ms in (10, 20, 30):
            m.record(sample(total=float(ms), req=100, resp=50))
        m.record(sample(status=429, total=0.1, req=0, resp=30))
        m.record(sample(kind=SNIPPET, total=80.0, req=5000, resp=300))
        line = m.tick_line()
        assert "\n" not in line and line.startswith("metrics: ")
        assert (
            "emission 4 req (200:3 429:1) total p50 20.0 p95 30.0 ms, in 300 B out 180 B"
            in line
        )
        assert (
            "snippet 1 req (200:1) total p50 80.0 p95 80.0 ms, in 5000 B out 300 B"
            in line
        )
        assert m.tick_line() is None  # drained

    def test_a_tick_with_only_refusals_says_no_200s(self):
        m = Metrics(clock=lambda: T0)
        m.record(sample(status=403, total=0.1))
        assert "no 200s" in m.tick_line()

    def test_the_line_does_not_disturb_the_summary(self):
        m = Metrics(clock=lambda: T0)
        m.record(sample())
        m.tick_line()
        assert m.summary()[EMISSION]["last_n"]["n"] == 1

    def test_the_line_carries_no_ids_or_text(self):
        m = Metrics(clock=lambda: T0)
        m.record(sample())
        assert set(m.tick_line()) <= set(
            "abcdefghijklmnopqrstuvwxyz0123456789 :()|,.%B"
        )


class FakeBackend:
    """An emission backend that answers like a decode; its text must never reach the metrics."""

    def __init__(self):
        self.calls = 0

    def emission(self, body):
        self.calls += 1
        return Reply(
            ok=True,
            text="secret phrase",
            reject=False,
            ms=1.0,
            frames=3,
            kind="command",
            status="ran",
            why=None,
            commands=1,
        )


def snippet_service(tmp_path):
    folder = tmp_path / "rec"
    folder.mkdir()
    return snippet.SnippetService(
        recordings.RecordingsWriter(lambda: str(folder)),
        snippet_ledger.SnippetLedger(str(tmp_path / "l.jsonl")),
        lambda: True,
        log=lambda *_: None,
    )


def make_api(tmp_path, *, trace_ticks=None, **kw):
    met = Metrics()
    api = listener.ListenerApi(
        FakeBackend(),
        lambda: "emission",
        lambda: "",
        key=lambda: KEY,
        snippets=snippet_service(tmp_path),
        metrics=met,
        limiter=RateLimiter(1000, 1.0),
        snippet_limiter=RateLimiter(1000, 1.0),
        metrics_limiter=kw.pop("metrics_limiter", RateLimiter(1000, 1.0)),
        log=lambda *_: None,
        trace_timer=iter(trace_ticks).__next__ if trace_ticks else None,
        **kw,
    )
    return api, met


def get_metrics(api, auth=None, method="GET", path="/metrics", extra=None):
    h = dict(KEYHDR if auth is None else auth)
    h.update(extra or {})
    return api.handle(method, path, h, io.BytesIO(b""))


class TestMetricsEndpoint:
    def test_authenticated_get_returns_the_summary(self, tmp_path):
        api, met = make_api(tmp_path)
        r = get_metrics(api)
        assert r.status == 200 and r.body["ok"] is True
        assert set(r.body) >= {"window", "generated_at", EMISSION, SNIPPET}

    @pytest.mark.parametrize(
        "auth",
        [{}, {keyfile.HEADER: "z" * 43}, {"Tailscale-User-Login": "a@example.com"}],
    )
    def test_without_the_key_it_is_403(self, tmp_path, auth):
        api, _ = make_api(tmp_path)
        r = get_metrics(api, auth=auth)
        assert (r.status, r.body) == (403, {"ok": False, "error": "forbidden"})

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_only_get_is_allowed(self, tmp_path, method):
        api, _ = make_api(tmp_path)
        r = get_metrics(api, method=method)
        assert r.status == 405 and r.headers["Allow"] == "GET"

    def test_a_listener_without_metrics_has_no_such_path(self, tmp_path):
        api, _ = make_api(tmp_path)
        api._metrics = None
        assert get_metrics(api).status == 404

    def test_it_is_rate_limited_with_retry_after(self, tmp_path):
        api, _ = make_api(tmp_path, metrics_limiter=RateLimiter(2, 60.0))
        assert [get_metrics(api).status for _ in range(3)] == [200, 200, 429]
        assert int(get_metrics(api).headers["Retry-After"]) >= 1

    def test_the_metrics_limiter_is_not_the_emission_one(self, tmp_path):
        api, _ = make_api(tmp_path, metrics_limiter=RateLimiter(1, 60.0))
        get_metrics(api)
        assert get_metrics(api).status == 429
        assert api._limiter.check()[0] is True

    def test_reading_the_metrics_is_not_itself_a_sample(self, tmp_path):
        api, met = make_api(tmp_path)
        for _ in range(3):
            get_metrics(api)
        s = met.summary()
        assert s[EMISSION]["last_n"]["n"] == 0 and s[SNIPPET]["last_n"]["n"] == 0
        assert "X-Talon-Server-Ms" not in get_metrics(api).headers

    def test_the_summary_has_no_phrases_ids_names_keys_or_audio(self, tmp_path):
        api, _ = make_api(tmp_path)
        from test_phone_snippet import flac_bytes  # noqa: PLC0415

        h = {
            "Content-Length": str(len(flac_bytes())),
            "Content-Type": "audio/flac",
            ledger.ID_HEADER: PRIVATE_ID,
            **KEYHDR,
        }
        ack = api.handle("POST", "/snippet", h, io.BytesIO(flac_bytes()))
        assert ack.status == 200
        text = json.dumps(get_metrics(api).body)
        assert PRIVATE_ID not in text
        assert ack.body["name"] not in text and KEY not in text
        assert "secret phrase" not in text


class TestInstrumentation:
    def emission(self, api, body=b"\0" * 10, auth=None, ctype=None, extra=None):
        h = {
            "Content-Length": str(len(body)),
            "Content-Type": ctype or listener.CONTENT_TYPES["emission"],
        }
        h.update(KEYHDR if auth is None else auth)
        h.update(extra or {})
        return api.handle("POST", "/emission", h, io.BytesIO(body))

    def last(self, met, kind=EMISSION):
        return met.summary()[kind]["last_n"]

    def test_a_refused_emission_is_a_sample_with_its_status(self, tmp_path):
        api, met = make_api(tmp_path)
        self.emission(api, auth={})
        self.emission(api, ctype="text/plain")
        self.emission(api, body=b"junk")
        last = self.last(met)
        assert last["n"] == 3 and last["by_status"] == {"403": 1, "415": 1, "422": 1}
        assert last["ok"] == 0

    def test_the_bytes_read_are_counted_for_a_body_that_was_read(self, tmp_path):
        api, met = make_api(tmp_path)
        self.emission(api, body=b"x" * 77)  # a 422, but the body was read
        assert self.last(met)["bytes_in"] == 77

    def test_a_refusal_before_the_body_counts_no_request_bytes(self, tmp_path):
        api, met = make_api(tmp_path)
        self.emission(api, auth={}, body=b"x" * 77)
        assert self.last(met)["bytes_in"] == 0

    def test_response_bytes_are_the_json_sent(self, tmp_path):
        api, met = make_api(tmp_path)
        r = self.emission(api, auth={})
        assert self.last(met)["bytes_out"] == len(r.payload())
        assert r.payload() == json.dumps(r.body, separators=(",", ":")).encode()

    def test_a_404_or_405_is_not_a_sample(self, tmp_path):
        api, met = make_api(tmp_path)
        api.handle("POST", "/nope", dict(KEYHDR), io.BytesIO(b""))
        api.handle("GET", "/emission", dict(KEYHDR), io.BytesIO(b""))
        assert self.last(met)["n"] == 0

    def test_the_server_time_header_is_on_known_paths_only(self, tmp_path):
        api, _ = make_api(tmp_path)
        assert "X-Talon-Server-Ms" in self.emission(api, auth={}).headers
        assert (
            "X-Talon-Server-Ms"
            not in api.handle("POST", "/nope", dict(KEYHDR), io.BytesIO(b"")).headers
        )

    def test_the_server_time_header_is_the_total_the_summary_counts(self, tmp_path):
        api, met = make_api(tmp_path, trace_ticks=[0.0, 0.0425, 0.0425, 0.0425])
        r = self.emission(api, auth={})
        assert r.headers["X-Talon-Server-Ms"] == "42.5"

    def test_snippet_phases_are_timed(self, tmp_path):
        from test_phone_snippet import flac_bytes  # noqa: PLC0415

        # t0, received, decoded, dispatched, total
        api, met = make_api(tmp_path, trace_ticks=[0.0, 0.010, 0.030, 0.080, 0.100])
        h = {
            "Content-Length": str(len(flac_bytes())),
            "Content-Type": "audio/flac",
            ledger.ID_HEADER: "1" * 32,
            **KEYHDR,
        }
        assert api.handle("POST", "/snippet", h, io.BytesIO(flac_bytes())).status == 200
        last = self.last(met, SNIPPET)
        assert last["receive_ms"]["p50"] == 10.0
        assert last["decode_ms"]["p50"] == 20.0
        assert last["dispatch_ms"]["p50"] == 50.0
        assert last["total_ms"]["p50"] == 100.0

    def test_an_emission_that_reaches_the_runner_has_all_four_timings(self, tmp_path):
        from test_phone_listener import emission_body  # noqa: PLC0415

        api, met = make_api(tmp_path)
        r = self.emission(api, body=emission_body())
        assert r.status == 200
        last = self.last(met)
        for name in metrics.TIMINGS:
            assert last[name]["p50"] is not None, name
        assert api._backend.calls == 1

    def test_a_runner_that_blows_up_is_still_a_timed_sample(self, tmp_path):
        from test_phone_listener import emission_body  # noqa: PLC0415

        api, met = make_api(tmp_path)
        api._run = lambda fn: (_ for _ in ()).throw(RuntimeError("main thread gone"))
        r = self.emission(api, body=emission_body())
        assert r.status == 500
        assert self.last(met)["by_status"] == {"500": 1}

    def test_a_failing_recorder_does_not_fail_the_request(self, tmp_path):
        api, met = make_api(tmp_path)
        met.record = lambda s: (_ for _ in ()).throw(RuntimeError("down"))
        assert self.emission(api, auth={}).status == 403

    def test_without_a_metrics_object_requests_work_and_carry_the_server_time(
        self, tmp_path
    ):
        api, _ = make_api(tmp_path)
        api._metrics = None
        r = self.emission(api, auth={})
        assert r.status == 403 and "X-Talon-Server-Ms" in r.headers


class TestClientRttHeader:
    def post(self, api, **headers):
        h = {
            "Content-Length": "4",
            "Content-Type": listener.CONTENT_TYPES["emission"],
            **KEYHDR,
            **headers,
        }
        return api.handle("POST", "/emission", h, io.BytesIO(b"junk"))

    def rtt(self, met, kind=EMISSION):
        return met.summary()[kind]["client_rtt_ms"]["last_n"]

    def test_the_header_names_are_the_documented_ones(self):
        assert listener.RTT_HEADER == "x-talon-client-rtt-ms"
        assert listener.RTT_KIND_HEADER == "x-talon-client-rtt-kind"

    def test_a_value_is_kept_under_the_requests_own_kind(self, tmp_path):
        api, met = make_api(tmp_path)
        self.post(api, **{"X-Talon-Client-Rtt-Ms": "250.5"})
        assert self.rtt(met) == {"n": 1, "p50": 250.5, "p95": 250.5}
        assert self.rtt(met, SNIPPET)["n"] == 0

    def test_the_kind_header_says_which_request_it_measured(self, tmp_path):
        api, met = make_api(tmp_path)
        self.post(
            api,
            **{"X-Talon-Client-Rtt-Ms": "900", "X-Talon-Client-Rtt-Kind": "Snippet"},
        )
        assert self.rtt(met, SNIPPET)["p50"] == 900.0 and self.rtt(met)["n"] == 0

    @pytest.mark.parametrize("value", ["abc", "", "-4", "nan", "inf", "1e12", "0x10"])
    def test_junk_is_counted_as_rejected_and_never_fails_the_request(
        self, tmp_path, value
    ):
        api, met = make_api(tmp_path)
        r = self.post(api, **{"X-Talon-Client-Rtt-Ms": value})
        assert r.status == 422  # judged on its body, not on the header
        assert met.summary()["client_rtt_rejected"] == 1
        assert self.rtt(met)["n"] == 0

    def test_an_unknown_kind_is_rejected(self, tmp_path):
        api, met = make_api(tmp_path)
        self.post(
            api, **{"X-Talon-Client-Rtt-Ms": "5", "X-Talon-Client-Rtt-Kind": "other"}
        )
        assert met.summary()["client_rtt_rejected"] == 1

    def test_without_the_key_the_header_is_ignored(self, tmp_path):
        api, met = make_api(tmp_path)
        h = {
            "Content-Length": "4",
            "Content-Type": listener.CONTENT_TYPES["emission"],
            "X-Talon-Client-Rtt-Ms": "10",
        }
        assert api.handle("POST", "/emission", h, io.BytesIO(b"junk")).status == 403
        assert met.summary()["client_rtt_rejected"] == 0 and self.rtt(met)["n"] == 0

    def test_without_the_header_nothing_is_recorded(self, tmp_path):
        api, met = make_api(tmp_path)
        self.post(api)
        assert self.rtt(met)["n"] == 0 and met.summary()["client_rtt_rejected"] == 0


class TestMetricsOverTheWire:
    def test_a_real_socket_serves_the_summary_and_the_server_time(self, tmp_path):
        api, _ = make_api(tmp_path)
        srv, _ = listener.start(api, 0)
        try:
            port = srv.server_address[1]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(
                "POST",
                "/emission",
                body=b"junk",
                headers={"Content-Type": listener.CONTENT_TYPES["emission"], **KEYHDR},
            )
            r = conn.getresponse()
            r.read()
            assert r.status == 422 and float(r.getheader("X-Talon-Server-Ms")) >= 0
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/metrics", headers=KEYHDR)
            r = conn.getresponse()
            body = json.loads(r.read())
            assert r.status == 200 and body[EMISSION]["last_n"]["by_status"] == {
                "422": 1
            }
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/metrics")
            r = conn.getresponse()
            r.read()
            assert r.status == 403
            conn.close()
        finally:
            listener.stop(srv)


class TestGlueMetrics:
    def load(self, monkeypatch):
        monkeypatch.setattr(Module, "setting", lambda self, name, **kw: None)
        spec = importlib.util.spec_from_file_location(
            "trillium.phone_receiver._glue_probe_metrics", GLUE_PATH
        )
        glue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(glue)
        return glue

    def test_the_log_line_is_printed_only_when_there_is_something_to_say(
        self, monkeypatch, capsys
    ):
        glue = self.load(monkeypatch)
        glue._log_metrics()
        assert capsys.readouterr().out == ""
        glue._metrics.record(sample())
        glue._log_metrics()
        out = capsys.readouterr().out
        assert out.startswith("phone_listener: metrics: emission 1 req")
        glue._log_metrics()
        assert capsys.readouterr().out == ""

    def test_a_reload_cancels_the_old_job_and_a_start_schedules_one(self, monkeypatch):
        glue = self.load(monkeypatch)
        jobs, cancelled = [], []
        glue._holder.metrics_job = None  # the holder is process-wide; start clean
        monkeypatch.setattr(glue.listener, "DEFAULT_PORT", 0)
        monkeypatch.setattr(
            glue.cron,
            "interval",
            lambda every, fn: (jobs.append((every, fn)), f"job{len(jobs)}")[1],
        )
        monkeypatch.setattr(glue.cron, "cancel", lambda job: cancelled.append(job))
        talon.Settings.set("user.phone_receiver_enabled", True)
        try:
            glue.start_listener()
            glue.start_listener()
            assert [j[0] for j in jobs] == [glue.METRICS_LOG_INTERVAL] * 2
            assert cancelled == ["job1"]
            assert jobs[0][1] == glue._log_metrics
        finally:
            talon.Settings.reset()
            if glue._holder.server is not None:
                glue.listener.stop(glue._holder.server)
            glue._holder.server = None
            glue._holder.metrics_job = None
            talon.speech_system.reset()

    def test_a_listener_that_is_off_schedules_no_log_job(self, monkeypatch):
        glue = self.load(monkeypatch)
        jobs = []
        monkeypatch.setattr(glue.cron, "interval", lambda *a: jobs.append(a))
        glue._holder.server = None
        glue.start_listener()
        assert jobs == []
