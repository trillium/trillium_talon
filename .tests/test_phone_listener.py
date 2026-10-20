"""The phone listener: policy (`ListenerApi`), a real loopback socket, the PCM path and the
parity harness, all against a fake engine (no Talon, no model).

Every refusal here must happen before the engine is called, and Talon must stay up: each
malformed case asserts `engine.calls == 0` and ends with a request that still succeeds.
"""

import http.client
import importlib.util
import io
import json
import os
import threading

import numpy as np
import pytest
from talon import Module

from trillium.palette_feed.dispatch import DispatchTimeout
from trillium.palette_feed.limits import RateLimiter
from trillium.phone_receiver import faillog, keyfile, listener, netbind, parity, wire
from trillium.phone_receiver.encoder import PhoneEncoder
from trillium.phone_receiver.live import LiveInstall
from trillium.phone_receiver.service import (
    UNREADABLE,
    PhoneService,
    PhraseTap,
    Reply,
)

LOGIN = "trillium@example.com"
TPE1 = listener.CONTENT_TYPES[listener.MODE_EMISSION]
PCM = "audio/L16; rate=16000; channels=1"
N_PCM = 12981
RNG = np.random.default_rng(7)
GLUE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "trillium",
    "phone_receiver",
    "phone_receiver_live.py",
)


def fake_acoustic(samples) -> np.ndarray:
    """Stand-in for frontend + acoustic model: samples -> (T, 29) logits, one-hot per frame."""
    s = np.asarray(samples, dtype=np.float32)
    t = wire.frames_for(len(s))
    em = np.zeros((t, wire.TOKENS), np.float32)
    chunk = max(1, len(s) // t)
    for i in range(t):
        tok = int(abs(float(s[i * chunk : (i + 1) * chunk].sum())) * 100) % 28
        em[i, tok] = 10.0
    return em


def fake_decode(em: np.ndarray) -> tuple[str, bool]:
    toks = em.argmax(axis=1)
    runs = [t for i, t in enumerate(toks) if t != 28 and (i == 0 or t != toks[i - 1])]
    text = "".join(chr(97 + int(t)) for t in runs[:12])
    return text, not text


class FakeMicEncoder:
    def forward(self, samples):
        e = fake_acoustic(samples)
        return e.reshape(1, 1, *e.shape)


class FakeCapture:
    """The bit of a Talon `Capture` the outcome reads: its rule name."""

    def __init__(self, name):
        self._name = name


class FakeEngine:
    """The W2lEngine seam: `_on_audio_frame` -> `encoder.forward` -> decode -> `phrase`."""

    def __init__(self):
        self.lock = threading.RLock()
        self.encoder = FakeMicEncoder()
        self.mic_encoder = self.encoder
        self.calls = 0
        self.listeners = []
        self.boom = False
        self.forced = None  # (text, reject) to decode instead of the fake model's
        self.parsed = (
            None  # list of FakeCapture, or None to omit `parsed` from the event
        )
        self.raw_event = None  # an event dict to dispatch verbatim

    def register(self, event, cb):
        self.listeners.append(cb)

    def _on_audio_frame(self, samples, ts=0.0, *, pad=True):
        self.calls += 1
        if self.boom:
            raise RuntimeError("decoder fell over")
        em = self.encoder.forward(samples)[0, 0]
        text, reject = self.forced or fake_decode(em)
        j = {"phrase": text.split(), "_metadata": {"reject": reject}}
        if self.parsed is not None:
            j["parsed"] = self.parsed
        if self.raw_event is not None:
            j = self.raw_event
        for cb in self.listeners:
            cb(j)


class Rig:
    """FakeEngine + LiveInstall + PhoneService + ListenerApi, with a mutable mode and allow-list."""

    def __init__(
        self,
        enabled=True,
        record_all=False,
        mode="emission",
        allowed=LOGIN,
        key=None,
        log=None,
    ):
        self.engine = FakeEngine()
        self.state = {"enabled": enabled, "record_all": record_all}
        self.mode = mode
        self.allowed = allowed
        self.awake = True
        self.tap = PhraseTap(awake=lambda: self.awake)
        self.engine.register("phrase", self.tap.on_phrase)
        install = LiveInstall(
            lambda: self.engine,
            lambda: self.state["enabled"],
            lambda: self.state["record_all"],
            log=log,
        )
        self.service = PhoneService(install, self.tap, wait_s=0.05)
        self.api = listener.ListenerApi(
            self.service,
            lambda: self.mode,
            lambda: self.allowed,
            limiter=RateLimiter(1000, 1.0),
            key=(lambda: key) if key is not None else None,
            log=log,
        )

    def post(self, body, ctype=None, login=LOGIN, extra=None, length=None):
        h = {"Content-Length": str(len(body) if length is None else length)}
        if ctype is None:
            ctype = TPE1 if self.mode == "emission" else PCM
        if ctype:
            h["Content-Type"] = ctype
        if login is not None:
            h["Tailscale-User-Login"] = login
        h.update(extra or {})
        return self.api.handle("POST", "/emission", h, io.BytesIO(body))


def emission_body(n_pcm=N_PCM, fp16=False, ts=1.25):
    return wire.pack(fake_acoustic(RNG.normal(0, 0.1, n_pcm)), n_pcm, ts, fp16)


def pcm_body(n=N_PCM):
    return parity.pcm16(RNG.normal(0, 0.1, n).astype(np.float32))


@pytest.fixture
def rig():
    return Rig()


@pytest.fixture
def pcm_rig():
    return Rig(mode="pcm")


class ExplodingBody:
    def read(self, n=-1):
        raise AssertionError("the body must not be read")


class TestHappyPath:
    @pytest.mark.parametrize("fp16", [False, True])
    def test_emission_returns_phrase_and_ms(self, rig, fp16):
        r = rig.post(emission_body(fp16=fp16))
        assert r.status == 200
        assert r.body["ok"] is True and r.body["mode"] == "emission"
        assert isinstance(r.body["text"], str) and r.body["ms"] >= 0
        assert r.body["frames"] == wire.frames_for(N_PCM)
        assert rig.engine.calls == 1
        assert rig.engine.encoder is rig.engine.mic_encoder

    def test_pcm_returns_phrase_and_ms(self, pcm_rig):
        r = pcm_rig.post(pcm_body())
        assert r.status == 200 and r.body["mode"] == "pcm"
        assert isinstance(r.body["text"], str) and r.body["ms"] >= 0
        assert pcm_rig.engine.calls == 1
        assert pcm_rig.engine.encoder is pcm_rig.engine.mic_encoder

    def test_pcm_uses_the_engines_own_encoder_not_the_phone_one(self, pcm_rig):
        seen = []
        orig = pcm_rig.engine._on_audio_frame

        def spy(samples, ts=0.0, *, pad=True):
            seen.append((type(pcm_rig.engine.encoder), ts, pad, len(samples)))
            return orig(samples, ts, pad=pad)

        pcm_rig.engine._on_audio_frame = spy
        pcm_rig.post(pcm_body(4000), extra={"X-Utterance-Ts": "2.5"})
        assert seen == [(FakeMicEncoder, 2.5, True, 4000)]

    def test_identity_match_is_case_insensitive_and_allows_several(self):
        rig = Rig(allowed="Other@x.org, TRILLIUM@Example.com")
        assert rig.post(emission_body(), login="trillium@example.com").status == 200
        assert rig.post(emission_body(), login=" Other@X.org ").status == 200

    def test_query_string_is_ignored(self, rig):
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1}
        body = emission_body()
        h["Content-Length"] = str(len(body))
        assert (
            rig.api.handle("POST", "/emission?x=1", h, io.BytesIO(body)).status == 200
        )


class TestIdentity:
    @pytest.mark.parametrize("login", [None, "", "   ", "stranger@example.com", "*"])
    def test_missing_or_wrong_identity_is_403(self, rig, login):
        r = rig.post(emission_body(), login=login)
        assert (r.status, r.body["error"]) == (403, "forbidden")
        assert rig.engine.calls == 0

    @pytest.mark.parametrize("allowed", ["", "   ", ",", None, 5])
    def test_default_deny_when_allowlist_is_empty(self, allowed):
        rig = Rig(allowed=allowed)
        assert rig.post(emission_body()).status == 403
        assert rig.engine.calls == 0

    def test_wildcard_in_allowlist_is_literal(self):
        rig = Rig(allowed="*")
        assert rig.post(emission_body(), login="trillium@example.com").status == 403
        assert rig.post(emission_body(), login="*").status == 200  # a literal login

    def test_overlong_identity_is_refused(self):
        long = "a" * 300 + "@example.com"
        rig = Rig(allowed=long)
        assert rig.post(emission_body(), login=long).status == 403

    def test_identity_is_checked_before_the_body_is_read(self, rig):
        h = {"Content-Type": TPE1, "Content-Length": "10"}
        assert rig.api.handle("POST", "/emission", h, ExplodingBody()).status == 403

    def test_header_name_is_case_insensitive(self, rig):
        h = {
            "tAiLsCaLe-UsEr-LoGiN": LOGIN,
            "content-type": TPE1,
            "content-length": "1",
        }
        assert rig.api.handle("POST", "/emission", h, io.BytesIO(b"x")).status == 422


class TestRouting:
    def test_unknown_path_is_404(self, rig):
        r = rig.api.handle("POST", "/other", {"Tailscale-User-Login": LOGIN}, None)
        assert r.status == 404

    @pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH", "HEAD"])
    def test_other_methods_are_405(self, rig, method):
        r = rig.api.handle(method, "/emission", {"Tailscale-User-Login": LOGIN}, None)
        assert r.status == 405 and r.headers["Allow"] == "POST"


class TestContentType:
    @pytest.mark.parametrize(
        "ctype",
        [
            "",
            "text/plain",
            "application/json",
            "application/octet-stream",
            PCM,  # the other mode's type
            "application/x-talon-tpe1x",
        ],
    )
    def test_emission_mode_wants_tpe1(self, rig, ctype):
        r = rig.post(emission_body(), ctype=ctype)
        assert (r.status, r.body["error"]) == (415, "unsupported_media_type")
        assert r.body["want"] == TPE1
        assert rig.engine.calls == 0

    @pytest.mark.parametrize(
        "ctype",
        [
            "",
            "text/plain",
            TPE1,  # the other mode's type
            "audio/L16",  # no rate
            "audio/L16; rate=44100",
            "audio/L16; rate=16000; channels=2",
            "audio/wav",
        ],
    )
    def test_pcm_mode_wants_16k_mono_l16(self, pcm_rig, ctype):
        r = pcm_rig.post(pcm_body(), ctype=ctype)
        assert (r.status, r.body["error"]) == (415, "unsupported_media_type")
        assert pcm_rig.engine.calls == 0

    def test_content_type_matching_ignores_case_and_spacing(self, pcm_rig):
        r = pcm_rig.post(pcm_body(), ctype="AUDIO/l16 ;Rate=16000;CHANNELS=1")
        assert r.status == 200

    def test_flipping_the_setting_flips_the_accepted_body_with_no_code_change(self):
        rig = Rig(mode="emission")
        assert rig.post(emission_body()).status == 200
        assert rig.post(pcm_body(), ctype=PCM).status == 415
        rig.mode = "pcm"
        assert rig.post(pcm_body()).status == 200
        assert rig.post(emission_body(), ctype=TPE1).status == 415

    @pytest.mark.parametrize("mode", ["", "emissions", "both", None, 3])
    def test_unknown_mode_fails_closed(self, mode):
        rig = Rig(mode=mode)
        r = rig.post(emission_body(), ctype=TPE1)
        assert (r.status, r.body["error"]) == (503, "bad_mode")
        assert rig.engine.calls == 0


class TestBodyBounds:
    def test_oversize_content_length_is_413_and_unread(self, rig):
        n = wire.MAX_PAYLOAD_BYTES + 1
        h = {
            "Tailscale-User-Login": LOGIN,
            "Content-Type": TPE1,
            "Content-Length": str(n),
        }
        r = rig.api.handle("POST", "/emission", h, ExplodingBody())
        assert (r.status, r.body["error"]) == (413, "body_too_large")
        assert rig.engine.calls == 0

    def test_exactly_the_cap_is_read_then_rejected_by_the_validator(self, rig):
        r = rig.post(b"\0" * wire.MAX_PAYLOAD_BYTES)
        assert r.status == 422 and rig.engine.calls == 0

    def test_pcm_cap_is_the_same_64k(self, pcm_rig):
        assert pcm_rig.post(b"\0" * (wire.MAX_PAYLOAD_BYTES + 2)).status == 413
        full = pcm_rig.post(pcm_body(wire.MAX_PAYLOAD_BYTES // 2))
        assert full.status == 200  # 32768 samples, about 2.05 s

    @pytest.mark.parametrize("value", ["", "abc", "-1", "1.5"])
    def test_bad_content_length_is_400(self, rig, value):
        r = rig.post(b"x", length=0, extra={"Content-Length": value})
        assert r.status in (400, 411) and rig.engine.calls == 0

    def test_missing_content_length_is_411(self, rig):
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1}
        r = rig.api.handle("POST", "/emission", h, io.BytesIO(b"x"))
        assert r.status == 411

    def test_chunked_is_411(self, rig):
        r = rig.post(b"x", extra={"Transfer-Encoding": "chunked"})
        assert r.status == 411

    def test_truncated_body_is_400(self, rig):
        r = rig.post(b"abc", length=50)
        assert (r.status, r.body["error"]) == (400, "truncated_body")
        assert rig.engine.calls == 0


MALFORMED = {
    "empty": lambda: b"",
    "short_header": lambda: b"TPE1\0\0",
    "wrong_magic": lambda: b"XXXX" + emission_body()[4:],
    "bad_dtype": lambda: emission_body()[:4] + b"\x09" + emission_body()[5:],
    "truncated": lambda: emission_body()[:-3],
    "trailing_byte": lambda: emission_body() + b"\0",
    "t_zero": lambda: wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 0, 0, 0.0),
    "t_huge": lambda: (
        wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 2**32 - 1, 0, 0.0) + b"\0" * 8
    ),
    "t_mismatch": lambda: wire.pack(fake_acoustic(np.zeros(N_PCM + 5000)), N_PCM, 1.0),
    "transposed": lambda: (
        wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 29, N_PCM, 0.0)
        + fake_acoustic(np.zeros(N_PCM)).T.copy().tobytes()
    ),
    "nan": lambda: _with(lambda a: a.__setitem__((0, 0), np.nan)),
    "inf": lambda: _with(lambda a: a.__setitem__((1, 1), np.inf)),
    "huge_value": lambda: _with(lambda a: a.__setitem__((2, 2), 1e6)),
    "negative_ts": lambda: wire.pack(fake_acoustic(np.zeros(N_PCM)), N_PCM, -1.0),
    "nan_ts": lambda: wire.pack(fake_acoustic(np.zeros(N_PCM)), N_PCM, float("nan")),
}


def _with(mutate):
    a = fake_acoustic(np.zeros(N_PCM))
    mutate(a)
    return wire.pack(a, N_PCM, 1.0)


class TestMalformedEmission:
    @pytest.mark.parametrize("name", sorted(MALFORMED))
    def test_rejected_before_the_engine_and_the_listener_survives(self, rig, name):
        r = rig.post(MALFORMED[name]())
        assert r.status == 422 and r.body["ok"] is False, name
        assert isinstance(r.body["error"], str)
        assert rig.engine.calls == 0
        assert rig.engine.encoder is rig.engine.mic_encoder
        assert rig.post(emission_body()).status == 200  # still serving

    def test_random_bytes_never_escape(self, rig):
        rng = np.random.default_rng(3)
        for n in (1, 7, 24, 25, 500, 5000):
            r = rig.post(rng.bytes(n))
            assert r.status == 422 and rig.engine.calls == 0

    def test_valid_header_random_payload_is_either_ok_or_a_clean_error(self, rig):
        head = wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 43, N_PCM, 1.0)
        for seed in range(5):
            body = head + np.random.default_rng(seed).bytes(43 * 29 * 4)
            r = rig.post(body)
            assert r.status in (200, 422)  # random bit patterns are often NaN/inf


class TestMalformedPcm:
    @pytest.mark.parametrize(
        "body,code",
        [
            (b"", "pcm_too_short"),
            (b"\0", "pcm_odd_length"),
            (b"\0" * 3, "pcm_odd_length"),
            (b"\0" * 2 * (wire.MIN_PCM_SAMPLES - 1), "pcm_too_short"),
        ],
    )
    def test_bad_lengths(self, pcm_rig, body, code):
        r = pcm_rig.post(body)
        assert (r.status, r.body["error"]) == (422, code)
        assert pcm_rig.engine.calls == 0
        assert pcm_rig.post(pcm_body()).status == 200

    @pytest.mark.parametrize("ts", ["abc", "nan", "inf", "-1", ""])
    def test_bad_timestamp_header(self, pcm_rig, ts):
        r = pcm_rig.post(pcm_body(), extra={"X-Utterance-Ts": ts})
        assert (r.status, r.body["error"]) == (400, "bad_ts")
        assert pcm_rig.engine.calls == 0

    def test_full_scale_and_silence_are_ordinary_audio(self, pcm_rig):
        loud = np.full(4000, 32767, "<i2").tobytes()
        assert pcm_rig.post(loud).status == 200
        assert pcm_rig.post(np.zeros(4000, "<i2").tobytes()).status == 200


class TestGate:
    @pytest.mark.parametrize("mode", ["emission", "pcm"])
    def test_disabled_never_touches_the_engine(self, mode):
        rig = Rig(enabled=False, mode=mode)
        body = emission_body() if mode == "emission" else pcm_body()
        r = rig.post(body)
        assert (r.status, r.body["error"]) == (503, "disabled")
        assert rig.engine.calls == 0

    @pytest.mark.parametrize("mode", ["emission", "pcm"])
    def test_record_all_refuses_both_paths(self, mode):
        rig = Rig(record_all=True, mode=mode)
        body = emission_body() if mode == "emission" else pcm_body()
        r = rig.post(body)
        assert (r.status, r.body["error"]) == (503, "record_all_on")
        assert rig.engine.calls == 0

    def test_engine_failure_is_a_500_and_the_next_request_works(self, rig):
        rig.engine.boom = True
        r = rig.post(emission_body())
        assert (r.status, r.body["error"]) == (500, "engine_error")
        assert rig.engine.encoder is rig.engine.mic_encoder
        rig.engine.boom = False
        assert rig.post(emission_body()).status == 200


class TestRobustness:
    def test_backend_exception_is_contained(self):
        class Boom:
            def emission(self, buf):
                raise RuntimeError("x")

        api = listener.ListenerApi(Boom(), lambda: "emission", lambda: LOGIN)
        body = emission_body()
        h = {
            "Tailscale-User-Login": LOGIN,
            "Content-Type": TPE1,
            "Content-Length": str(len(body)),
        }
        r = api.handle("POST", "/emission", h, io.BytesIO(body))
        assert (r.status, r.body["error"]) == (500, "internal")

    def test_settings_getter_exception_is_contained(self):
        def boom():
            raise RuntimeError("settings unavailable")

        api = listener.ListenerApi(object(), boom, lambda: LOGIN)
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1}
        assert api.handle("POST", "/emission", h, None).status == 500

    def test_runner_timeout_is_504(self, rig):
        def runner(fn):
            raise DispatchTimeout()

        api = listener.ListenerApi(
            rig.service, lambda: "emission", lambda: LOGIN, runner=runner
        )
        body = emission_body()
        h = {
            "Tailscale-User-Login": LOGIN,
            "Content-Type": TPE1,
            "Content-Length": str(len(body)),
        }
        r = api.handle("POST", "/emission", h, io.BytesIO(body))
        assert (r.status, r.body["error"]) == (504, "timeout")

    def test_rate_limit_is_429_with_retry_after(self, rig):
        api = listener.ListenerApi(
            rig.service,
            lambda: "emission",
            lambda: LOGIN,
            limiter=RateLimiter(2, 60.0),
        )
        statuses = []
        for _ in range(3):
            body = emission_body()
            h = {
                "Tailscale-User-Login": LOGIN,
                "Content-Type": TPE1,
                "Content-Length": str(len(body)),
            }
            r = api.handle("POST", "/emission", h, io.BytesIO(body))
            statuses.append(r.status)
        assert statuses == [200, 200, 429] and int(r.headers["Retry-After"]) >= 1

    def test_phrase_that_never_arrives_is_ok_with_null_text(self):
        rig = Rig()
        rig.engine.listeners.clear()  # nothing reaches the tap
        r = rig.post(emission_body())
        assert r.status == 200 and r.body["text"] is None

    def test_odd_phrase_event_does_not_break_dispatch(self):
        tap = PhraseTap()
        with tap.capture(0.01) as get:
            tap.on_phrase({"unexpected": 1})
            assert get() is UNREADABLE
        tap.on_phrase(None)  # no capture active: ignored, never raises


OLD_200_KEYS = {"ok", "mode", "text", "reject", "ms", "frames"}
NEW_200_KEYS = {"status", "why", "kind", "commands", "total_ms"}


def ran(rig, text="page down", parsed=("user.cmd",), reject=False):
    rig.engine.forced = (text, reject)
    rig.engine.parsed = [FakeCapture(n) for n in parsed]
    return rig.post(emission_body())


class TestOutcome:
    """The reply says what Talon did with the utterance, from the `phrase` event alone."""

    def test_command_ran(self, rig):
        r = ran(rig)
        assert r.status == 200
        b = r.body
        assert (b["status"], b["why"], b["kind"], b["commands"]) == (
            "ran",
            None,
            "command",
            1,
        )
        assert b["text"] == "page down" and b["reject"] is False

    def test_chained_commands_count_every_rule(self, rig):
        b = ran(rig, "page down page up", ("user.a", "user.b")).body
        assert (b["status"], b["kind"], b["commands"]) == ("ran", "command", 2)

    def test_dictation_catch_all_runs_when_awake(self, rig):
        b = ran(rig, "hello there", ("___ltphrase_gt__",)).body
        assert (b["status"], b["kind"], b["commands"]) == ("ran", "dictation", 1)

    def test_dictation_catch_all_is_ignored_asleep(self, rig):
        rig.awake = False
        b = ran(rig, "hello there", ("___ltphrase_gt__",)).body
        assert (b["status"], b["why"], b["kind"]) == ("ignored", "asleep", "dictation")
        assert b["text"] == "hello there"

    def test_a_real_command_asleep_still_ran(self, rig):
        rig.awake = False  # the sleep grammar's own commands (e.g. wake) match here
        b = ran(rig, "welcome back", ("user.wake",)).body
        assert (b["status"], b["kind"]) == ("ran", "command")

    def test_awake_probe_failure_is_not_a_failure(self, rig):
        def boom():
            raise RuntimeError("no talon")

        rig.tap._awake = boom
        b = ran(rig, "hello", ("___ltphrase_gt__",)).body
        assert (b["status"], b["kind"]) == ("ran", "dictation")

    def test_engine_reject_is_ignored(self, rig):
        r = ran(rig, "", reject=True)
        assert r.status == 200
        assert (r.body["status"], r.body["why"]) == ("ignored", "rejected")
        assert r.body["reject"] is True and r.body["text"] == ""

    def test_phrase_with_no_parse_is_ignored(self, rig):
        rig.engine.forced = ("mumble", False)  # event has no `parsed`
        b = rig.post(emission_body()).body
        assert (b["status"], b["why"], b["kind"], b["commands"]) == (
            "ignored",
            "no_match",
            "unknown",
            0,
        )

    def test_empty_phrase_is_ignored(self, rig):
        b = ran(rig, "").body
        assert (b["status"], b["why"]) == ("ignored", "empty")

    def test_no_phrase_event_is_ignored(self, rig):
        rig.engine.listeners.clear()
        b = rig.post(emission_body()).body
        assert (b["status"], b["why"], b["kind"], b["commands"]) == (
            "ignored",
            "no_phrase",
            "unknown",
            0,
        )
        assert b["text"] is None and b["reject"] is None

    def test_unreadable_phrase_event_is_error(self, rig):
        rig.engine.raw_event = {"unexpected": 1}
        r = rig.post(emission_body())
        assert r.status == 200
        assert (r.body["status"], r.body["why"]) == ("error", "unreadable_phrase")
        assert r.body["text"] is None

    def test_pcm_mode_carries_the_same_fields(self, pcm_rig):
        pcm_rig.engine.forced = ("page down", False)
        pcm_rig.engine.parsed = [FakeCapture("user.cmd")]
        b = pcm_rig.post(pcm_body()).body
        assert (b["mode"], b["status"], b["kind"]) == ("pcm", "ran", "command")

    def test_total_ms_is_the_handoff_to_reply_time(self, rig):
        ticks = iter([10.0, 10.25])
        rig.api._timer = lambda: next(ticks)
        assert ran(rig).body["total_ms"] == 250.0

    def test_added_fields_only_and_old_ones_keep_their_types(self, rig):
        b = ran(rig).body
        assert set(b) == OLD_200_KEYS | NEW_200_KEYS
        assert b["ok"] is True and b["mode"] == "emission"
        assert isinstance(b["ms"], float) and isinstance(b["frames"], int)
        assert isinstance(b["total_ms"], float) and b["total_ms"] >= 0

    def test_reply_is_small(self, rig):
        r = ran(rig)
        assert len(json.dumps(r.body, separators=(",", ":"))) < 256

    def test_long_text_is_capped_and_marked(self, rig):
        long = " ".join(["word"] * 400)
        b = ran(rig, long).body
        assert len(b["text"]) == listener.MAX_TEXT_CHARS
        assert b["text_truncated"] is True and b["status"] == "ran"
        assert "text_truncated" not in ran(rig).body

    def test_old_clients_reading_old_fields_only_still_work(self, rig):
        b = json.loads(json.dumps(ran(rig).body))
        assert (b["ok"], b["text"], b["reject"]) == (True, "page down", False)

    @pytest.mark.parametrize(
        "make,status,error",
        [
            (
                lambda r: r.post(emission_body(), login="nobody@example.com"),
                403,
                "forbidden",
            ),
            (
                lambda r: r.post(emission_body(), ctype="text/plain"),
                415,
                "unsupported_media_type",
            ),
            (lambda r: r.post(b"\x00" * 40), 422, "bad_magic"),
        ],
    )
    def test_4xx_bodies_are_unchanged(self, rig, make, status, error):
        r = make(rig)
        assert r.status == status and r.body["error"] == error
        assert r.body["ok"] is False
        assert not (set(r.body) & (NEW_200_KEYS | {"text", "reject", "frames"}))

    def test_refusals_after_the_gate_are_unchanged(self):
        rig = Rig(enabled=False)
        r = rig.post(emission_body())
        assert (r.status, r.body["error"]) == (503, "disabled")
        assert set(r.body) == {"ok", "error", "ms"}
        rig = Rig()
        rig.engine.boom = True
        r = rig.post(emission_body())
        assert (r.status, r.body["error"]) == (500, "engine_error")
        assert set(r.body) == {"ok", "error", "ms"}


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
        conn.close()
        return resp.status, json.loads(data)

    def test_binds_loopback_only(self, server):
        srv, _ = server
        assert srv.server_address[0] == "127.0.0.1"

    @pytest.mark.parametrize("host", ["0.0.0.0", "100.74.138.74", "::", "macbook"])
    def test_refuses_non_loopback_bind(self, rig, host):
        with pytest.raises(ValueError):
            listener.start(rig.api, 0, host, assigned=lambda: [])

    def test_post_emission_round_trip(self, server):
        srv, rig = server
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1}
        status, body = self.call(srv, "POST", "/emission", emission_body(), h)
        assert status == 200 and body["ok"] and "text" in body and "ms" in body

    def test_post_pcm_round_trip(self, server):
        srv, rig = server
        rig.mode = "pcm"
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": PCM}
        status, body = self.call(srv, "POST", "/emission", pcm_body(), h)
        assert status == 200 and body["mode"] == "pcm"

    def test_no_identity_is_403_over_the_wire(self, server):
        srv, rig = server
        status, body = self.call(
            srv, "POST", "/emission", emission_body(), {"Content-Type": TPE1}
        )
        assert (status, body["error"]) == (403, "forbidden")
        assert rig.engine.calls == 0

    def test_oversize_body_is_413_over_the_wire(self, server):
        srv, rig = server
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1}
        status, body = self.call(srv, "POST", "/emission", b"\0" * 70000, h)
        assert (status, body["error"]) == (413, "body_too_large")
        assert rig.engine.calls == 0

    def test_get_is_405_and_server_keeps_serving(self, server):
        srv, rig = server
        assert self.call(srv, "GET", "/emission")[0] == 405
        assert self.call(srv, "GET", "/")[0] == 404
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1}
        assert self.call(srv, "POST", "/emission", emission_body(), h)[0] == 200

    def test_garbage_http_does_not_kill_the_server(self, server):
        import socket

        srv, _ = server
        for junk in (
            b"\x00\xff\xfe garbage\r\n\r\n",
            b"POST /emission HTTP/1.0\r\n\r\n",
        ):
            s = socket.create_connection(("127.0.0.1", srv.server_address[1]), 2)
            s.sendall(junk)
            s.settimeout(2)
            try:
                s.recv(4096)
            except OSError:
                pass
            s.close()
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1}
        assert self.call(srv, "POST", "/emission", emission_body(), h)[0] == 200

    def test_concurrent_posts(self, server):
        srv, rig = server
        h = {"Tailscale-User-Login": LOGIN, "Content-Type": TPE1}
        out = []

        def one():
            out.append(self.call(srv, "POST", "/emission", emission_body(), h)[0])

        threads = [threading.Thread(target=one) for _ in range(6)]
        [t.start() for t in threads]
        [t.join(10) for t in threads]
        assert sorted(out) == [200] * 6 and rig.engine.encoder is rig.engine.mic_encoder


KEY = "k" * 43
OTHER_KEY = "z" * 43
KEYHDR = {keyfile.HEADER: KEY}


class TestKeyAuth:
    """Tailnet form of auth: the shared secret replaces the Tailscale identity header."""

    @pytest.fixture
    def krig(self):
        return Rig(key=KEY)

    def test_right_key_is_served_and_identity_header_is_not_needed(self, krig):
        r = krig.post(emission_body(), login=None, extra=KEYHDR)
        assert r.status == 200 and krig.engine.calls == 1

    def test_header_name_is_case_insensitive(self, krig):
        r = krig.post(emission_body(), login=None, extra={"X-TALON-PHONE-KEY": KEY})
        assert r.status == 200

    @pytest.mark.parametrize(
        "presented",
        [None, "", " ", OTHER_KEY, KEY[:-1], KEY + "x", KEY.upper(), "a" * 5000],
    )
    def test_wrong_or_missing_key_is_403_and_the_body_is_unread(self, krig, presented):
        h = {"Content-Type": TPE1, "Content-Length": "10"}
        if presented is not None:
            h[keyfile.HEADER] = presented
        r = krig.api.handle("POST", "/emission", h, ExplodingBody())
        assert (r.status, r.body["error"]) == (403, "forbidden")
        assert krig.engine.calls == 0

    def test_identity_header_does_not_substitute_for_the_key(self, krig):
        r = krig.post(emission_body(), login=LOGIN)  # allowed login, no key
        assert r.status == 403 and krig.engine.calls == 0

    def test_identity_is_ignored_even_when_the_key_is_right(self):
        rig = Rig(key=KEY, allowed="")  # empty allow-list would deny in identity mode
        assert rig.post(emission_body(), login=None, extra=KEYHDR).status == 200

    def test_key_header_is_ignored_in_identity_mode(self, rig):
        r = rig.post(emission_body(), login=None, extra=KEYHDR)
        assert r.status == 403

    @pytest.mark.parametrize("key", ["", "short", None])
    def test_an_unusable_server_key_denies_everyone(self, key):
        api = listener.ListenerApi(
            object(), lambda: "emission", lambda: LOGIN, key=lambda: key
        )
        h = {"Content-Type": TPE1, keyfile.HEADER: key or ""}
        assert api.handle("POST", "/emission", h, None).status == 403

    def test_non_ascii_header_value_is_a_403_not_a_crash(self, krig):
        r = krig.post(
            emission_body(), login=None, extra={keyfile.HEADER: "k\u00e9\ud800"}
        )
        assert r.status == 403

    def test_oversize_and_malformed_still_apply_after_a_good_key(self, krig):
        h = {
            "Content-Type": TPE1,
            "Content-Length": str(wire.MAX_PAYLOAD_BYTES + 1),
            **KEYHDR,
        }
        assert krig.api.handle("POST", "/emission", h, ExplodingBody()).status == 413
        assert krig.post(b"junk", login=None, extra=KEYHDR).status == 422
        assert krig.engine.calls == 0

    def test_the_key_never_appears_in_any_response(self, krig):
        for presented in (KEY, OTHER_KEY):
            r = krig.post(b"junk", login=None, extra={keyfile.HEADER: presented})
            assert KEY not in json.dumps(r.body) and KEY not in str(r.headers)


def _ip(text):
    import ipaddress

    return ipaddress.IPv4Address(text)


class TestTailnetBind:
    ASSIGNED = staticmethod(lambda: [_ip("100.74.138.74")])

    @pytest.mark.parametrize(
        "host",
        [
            "0.0.0.0",
            "::",
            "::1",
            "192.168.1.20",
            "10.0.0.5",
            "172.16.0.1",
            "100.63.255.255",  # just below 100.64.0.0/10
            "100.128.0.0",  # just above it
            "100.74.138.75",  # tailnet range, but not assigned to this Mac
            "127.0.0.2",
            "127.1",
            "localhost",
            "macbook.hippo-tilapia.ts.net",
            "",
            "   ",
            "100.74.138.74/32",
            "100.74.138.74:7403",
            None,
            7,
        ],
    )
    def test_refused(self, host):
        with pytest.raises(netbind.BindError):
            netbind.resolve_bind(host, self.ASSIGNED)

    def test_loopback_is_accepted_without_asking_tailscale(self):
        def boom():
            raise AssertionError("loopback must not shell out")

        assert netbind.resolve_bind("127.0.0.1", boom) == netbind.BindPlan(
            "127.0.0.1", False
        )
        assert netbind.resolve_bind(" 127.0.0.1 ", boom).host == "127.0.0.1"

    def test_assigned_tailnet_address_is_accepted_and_flags_key_auth(self):
        plan = netbind.resolve_bind("100.74.138.74", self.ASSIGNED)
        assert plan == netbind.BindPlan("100.74.138.74", True)

    @pytest.mark.parametrize("edge", ["100.64.0.0", "100.127.255.255"])
    def test_range_edges_are_inside_when_assigned(self, edge):
        assert netbind.resolve_bind(edge, lambda: [_ip(edge)]).tailnet

    def test_start_refuses_before_any_socket_exists(self, rig):
        for host in ("0.0.0.0", "192.168.1.20", "100.74.138.75"):
            with pytest.raises(netbind.BindError):
                listener.start(Rig(key=KEY).api, 0, host, assigned=self.ASSIGNED)

    def test_start_refuses_a_tailnet_bind_with_identity_auth(self, rig):
        with pytest.raises(netbind.BindError):
            listener.start(rig.api, 0, "100.74.138.74", assigned=self.ASSIGNED)

    def test_binding_an_address_that_vanished_is_an_oserror_not_a_crash(self):
        # Claimed assigned, but the OS has no such interface: the bind itself fails cleanly.
        with pytest.raises(OSError):
            listener.start(
                Rig(key=KEY).api,
                0,
                "100.100.100.100",
                assigned=lambda: [_ip("100.100.100.100")],
            )

    def test_tailscale_failures_mean_no_assigned_address(self, monkeypatch):
        import subprocess

        monkeypatch.setattr(
            netbind, "_tailscale_binary", lambda: "/nonexistent/tailscale"
        )

        def boom(*a, **k):
            raise subprocess.TimeoutExpired("tailscale", 3)

        monkeypatch.setattr(netbind.subprocess, "run", boom)
        assert netbind.tailnet_addresses() == frozenset()
        monkeypatch.setattr(netbind, "_tailscale_binary", lambda: None)
        assert netbind.tailnet_addresses() == frozenset()

    def test_tailscale_output_is_filtered_to_the_tailnet_range(self, monkeypatch):
        class Out:
            returncode = 0
            stdout = "100.74.138.74\n192.168.1.5\nnot-an-ip\n8.8.8.8\n"

        monkeypatch.setattr(netbind, "_tailscale_binary", lambda: "/x/tailscale")
        monkeypatch.setattr(netbind.subprocess, "run", lambda *a, **k: Out())
        assert netbind.tailnet_addresses() == frozenset({_ip("100.74.138.74")})


class TestKeyFile:
    def test_ensure_creates_a_private_file_and_load_reads_it_back(self, tmp_path):
        path = tmp_path / "talon-phone" / "key"
        key = keyfile.ensure_key(str(path))
        assert len(key) >= keyfile.MIN_KEY_LEN
        assert (path.stat().st_mode & 0o777) == 0o600
        assert (path.parent.stat().st_mode & 0o777) == 0o700
        assert keyfile.load_key(str(path)) == key

    def test_ensure_never_overwrites_an_existing_key(self, tmp_path):
        path = tmp_path / "key"
        first = keyfile.ensure_key(str(path))
        assert keyfile.ensure_key(str(path)) == first

    def test_group_readable_key_is_refused(self, tmp_path):
        path = tmp_path / "key"
        path.write_text(KEY)
        os.chmod(path, 0o640)
        with pytest.raises(keyfile.KeyFileError, match="chmod 600"):
            keyfile.load_key(str(path))

    def test_symlinked_and_short_and_missing_keys_are_refused(self, tmp_path):
        real = tmp_path / "real"
        real.write_text(KEY)
        os.chmod(real, 0o600)
        link = tmp_path / "link"
        link.symlink_to(real)
        with pytest.raises(keyfile.KeyFileError):
            keyfile.load_key(str(link))
        short = tmp_path / "short"
        short.write_text("abc")
        os.chmod(short, 0o600)
        with pytest.raises(keyfile.KeyFileError):
            keyfile.load_key(str(short))
        with pytest.raises(keyfile.KeyFileError):
            keyfile.load_key(str(tmp_path / "missing"))

    def test_a_key_inside_a_git_repo_is_refused(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with pytest.raises(keyfile.KeyFileError, match="git repository"):
            keyfile.ensure_key(str(tmp_path / "key"))
        assert not (tmp_path / "key").exists()

    def test_default_path_is_outside_any_repo(self):
        path = os.path.expanduser(keyfile.KEY_PATH)
        assert path.endswith(os.path.join(".config", "talon-phone", "key"))
        assert keyfile.find_repo_root(path) is None or not keyfile.is_within(
            path, keyfile.find_repo_root(path)
        )

    def test_errors_and_cli_never_contain_the_key(self, tmp_path, capsys):
        path = tmp_path / "key"
        key = keyfile.ensure_key(str(path))
        os.chmod(path, 0o644)
        with pytest.raises(keyfile.KeyFileError) as err:
            keyfile.load_key(str(path))
        assert key not in str(err.value)
        os.chmod(path, 0o600)
        assert keyfile.main([str(path)]) == 0
        out = capsys.readouterr()
        assert key not in out.out + out.err and str(path) in out.out

    def test_matches_is_exact_and_bounded(self):
        assert keyfile.matches(KEY, KEY)
        assert not keyfile.matches(KEY + " ", KEY)
        assert not keyfile.matches("", KEY) and not keyfile.matches(None, KEY)
        assert not keyfile.matches(
            KEY, "short"
        )  # an unusable server key matches nothing


class TestRealSocketKeyAuth:
    @pytest.fixture
    def server(self):
        rig = Rig(key=KEY)
        srv, _ = listener.start(rig.api, 0)  # loopback socket, key-authenticated api
        try:
            yield srv, rig
        finally:
            listener.stop(srv)

    def call(self, srv, headers, body=b""):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        conn.request("POST", "/emission", body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data)

    def test_key_round_trip_wrong_key_oversize_and_malformed(self, server):
        srv, rig = server
        base = {"Content-Type": TPE1}
        good = self.call(srv, {**base, **KEYHDR}, emission_body())
        assert good[0] == 200 and good[1]["ok"]
        for headers in (
            base,
            {**base, keyfile.HEADER: OTHER_KEY},
            {**base, "Tailscale-User-Login": LOGIN},
        ):
            assert self.call(srv, headers, emission_body())[0] == 403
        assert (
            self.call(srv, {**base, **KEYHDR}, b"\0" * 70000)[1]["error"]
            == "body_too_large"
        )
        assert self.call(srv, {**base, **KEYHDR}, b"junk")[1]["error"] == "short_header"
        assert rig.engine.calls == 1
        assert (
            self.call(srv, {**base, **KEYHDR}, emission_body())[0] == 200
        )  # still serving


def exploding_runner(fn):
    """Stands in for a main-thread hop that fails (Talon busy, engine gone): any call is a 500."""
    raise RuntimeError("the runner must not be reached for a malformed body")


class TestMalformedBodiesAreNever500:
    """robots-foyk6: a malformed body is a 4xx decided in the listener, before the runner,
    the main thread or the engine, so a failure there cannot turn it into a 500 `internal`.
    """

    @staticmethod
    def api(mode="emission", key=KEY):
        rig = Rig(mode=mode, key=key)
        rig.api = listener.ListenerApi(
            rig.service,
            lambda: rig.mode,
            lambda: rig.allowed,
            runner=exploding_runner,
            limiter=RateLimiter(1000, 1.0),
            key=(lambda: key) if key else None,
        )
        return rig

    EMISSION = {
        "one_byte": lambda: b"x",
        "one_nul": lambda: b"\0",
        "empty": lambda: b"",
        "tiny_magic_only": lambda: b"TPE1",
        "just_under_header": lambda: b"TPE1" + b"\0" * 19,
        "garbage": lambda: np.random.default_rng(5).bytes(300),
        "garbage_header_sized": lambda: np.random.default_rng(6).bytes(
            wire.HEADER.size
        ),
        "truncated_mid_array": lambda: emission_body()[: wire.HEADER.size + 40],
        "truncated_last_byte": lambda: emission_body()[:-1],
        "wrong_dtype_byte": lambda: emission_body()[:4] + b"\x07" + emission_body()[5:],
        "f16_header_f32_payload": lambda: (
            emission_body()[:4] + bytes([wire.DTYPE_F16]) + emission_body()[5:]
        ),
        "f32_header_f16_payload": lambda: (
            emission_body()[:4] + bytes([wire.DTYPE_F32]) + emission_body(fp16=True)[5:]
        ),
        "at_the_cap_zeros": lambda: b"\0" * wire.MAX_PAYLOAD_BYTES,
    }

    @pytest.mark.parametrize("name", sorted(EMISSION))
    @pytest.mark.parametrize("key", [KEY, None])
    def test_emission_body_is_422_without_reaching_the_runner(self, name, key):
        rig = self.api(key=key)
        extra = KEYHDR if key else None
        r = rig.post(self.EMISSION[name](), login=None if key else LOGIN, extra=extra)
        assert r.status == 422 and r.body["ok"] is False, name
        assert isinstance(r.body["error"], str) and r.body["error"] != "internal"
        assert rig.engine.calls == 0

    @pytest.mark.parametrize(
        "body",
        [b"x", b"", b"\0", b"\0" * 3, b"\0" * 2 * (wire.MIN_PCM_SAMPLES - 1)],
        ids=["one_byte", "empty", "one_nul", "odd_three", "just_too_short"],
    )
    def test_pcm_body_is_422_without_reaching_the_runner(self, body):
        rig = self.api(mode="pcm")
        r = rig.post(body, login=None, extra=KEYHDR)
        assert r.status == 422 and r.body["error"] != "internal"
        assert rig.engine.calls == 0

    def test_oversize_is_413_without_reaching_the_runner(self):
        rig = self.api()
        for length in (wire.MAX_PAYLOAD_BYTES + 1, 10**9):
            h = {"Content-Type": TPE1, "Content-Length": str(length), **KEYHDR}
            r = rig.api.handle("POST", "/emission", h, ExplodingBody())
            assert (r.status, r.body["error"]) == (413, "body_too_large")
        assert rig.engine.calls == 0

    def test_a_valid_body_still_reaches_the_runner(self):
        r = self.api().post(emission_body(), login=None, extra=KEYHDR)
        assert (
            r.status == 500
        )  # the runner is the failure; only malformed bodies dodge it

    @pytest.mark.parametrize("name", sorted(EMISSION))
    def test_over_a_real_socket_never_500_and_the_listener_survives(self, name):
        rig = Rig(key=KEY)
        srv, _ = listener.start(rig.api, 0)
        try:
            h = {"Content-Type": TPE1, **KEYHDR}
            conn = http.client.HTTPConnection(
                "127.0.0.1", srv.server_address[1], timeout=5
            )
            conn.request("POST", "/emission", body=self.EMISSION[name](), headers=h)
            resp = conn.getresponse()
            body = json.loads(resp.read())
            conn.close()
            assert resp.status == 422 and body["error"] != "internal", name
            assert rig.engine.calls == 0
            conn = http.client.HTTPConnection(
                "127.0.0.1", srv.server_address[1], timeout=5
            )
            conn.request("POST", "/emission", body=emission_body(), headers=h)
            assert conn.getresponse().status == 200  # Talon-side state untouched
            conn.close()
        finally:
            listener.stop(srv)


def make_utterances(n=20):
    rng = np.random.default_rng(11)
    return [
        parity.Utterance(
            f"utt{i:02d}",
            rng.normal(0, 0.2, int(rng.integers(3000, 30000))).astype("f4"),
        )
        for i in range(n)
    ]


class TestParity:
    def run(self, emit=fake_acoustic, fp16=False, rig=None):
        rig = rig or Rig()
        return (
            parity.run_parity(
                parity.api_poster(rig.api, LOGIN),
                lambda m: setattr(rig, "mode", m),
                make_utterances(),
                emit,
                fp16=fp16,
            ),
            rig,
        )

    @pytest.mark.parametrize("fp16", [False, True])
    def test_identical_phrases_for_the_test_set(self, fp16):
        report, rig = self.run(fp16=fp16)
        assert report.identical, report.format()
        assert report.summary()["utterances"] == 20
        assert rig.engine.calls == 40  # both paths ran for every utterance
        assert all(r.emission.text is not None for r in report.rows)

    def test_harness_flags_a_phone_model_that_disagrees(self):
        def drifting(samples):
            e = fake_acoustic(samples)
            return np.roll(e, 1, axis=1)  # every frame lands on a different token

        report, _ = self.run(emit=drifting)
        assert not report.identical
        assert report.mismatches() and "DIFF" in report.format()

    def test_harness_reports_a_path_that_errors(self):
        rig = Rig(record_all=True)
        report, _ = self.run(rig=rig)
        assert not report.identical
        assert all(not r.emission.ok and not r.pcm.ok for r in report.rows)

    def test_empty_set_is_not_a_pass(self):
        assert not parity.Report([]).identical


class TestGlue:
    def load(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            Module, "setting", lambda self, name, **kw: calls.append((name, kw))
        )
        spec = importlib.util.spec_from_file_location(
            "trillium.phone_receiver._glue_probe_listener", GLUE_PATH
        )
        glue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(glue)
        return glue, {n: kw for n, kw in calls}

    def test_declares_mode_and_allowlist_settings_with_closed_defaults(
        self, monkeypatch
    ):
        _, decl = self.load(monkeypatch)
        assert decl["phone_receiver_enabled"]["default"] is False
        assert decl["phone_receiver_mode"]["default"] == "emission"
        assert decl["phone_receiver_allowed_logins"]["default"] == ""
        assert decl["phone_receiver_mode"]["type"] is str

    def test_port_is_the_documented_one(self, monkeypatch):
        glue, _ = self.load(monkeypatch)
        assert glue.listener.DEFAULT_PORT == 7403

    def test_setting_off_opens_no_socket(self, monkeypatch):
        glue, _ = self.load(monkeypatch)
        monkeypatch.setattr(glue.listener, "DEFAULT_PORT", 0)
        glue._holder.server = None
        glue.start_listener()
        assert glue._holder.server is None and glue._holder.tap is None

    def test_setting_on_binds_loopback_and_denies_by_default(self, monkeypatch):
        import talon

        glue, _ = self.load(monkeypatch)
        monkeypatch.setattr(glue.listener, "DEFAULT_PORT", 0)
        talon.Settings.set("user.phone_receiver_enabled", True)
        try:
            glue.start_listener()
            srv = glue._holder.server
            assert srv is not None and srv.server_address[0] == "127.0.0.1"
            conn = http.client.HTTPConnection(
                "127.0.0.1", srv.server_address[1], timeout=5
            )
            conn.request("POST", "/emission", body=b"x", headers={"Content-Type": TPE1})
            assert conn.getresponse().status == 403  # allow-list empty: deny all
            conn.close()
            glue.start_listener()  # a reload replaces the server instead of stacking one
            assert glue._holder.server is not srv
        finally:
            talon.Settings.reset()
            if glue._holder.server is not None:
                glue.listener.stop(glue._holder.server)
            glue._holder.server = None
            talon.speech_system.reset()


class TestFailureLog:
    """A failure while running an utterance leaves its exception class and frames in Talon's
    log, and nothing a request carried: no message, key, phrase text or audio."""

    SECRET = "s3cret-phrase-and-key-material"
    LOGKEY = "k" * 43

    @staticmethod
    def body_headers(body, key=None):
        h = {"Content-Type": TPE1, "Content-Length": str(len(body))}
        h.update({keyfile.HEADER: key} if key else {"Tailscale-User-Login": LOGIN})
        return h

    def api(self, runner, lines, key=None):
        rig = Rig(key=key, log=lines.append)
        api = listener.ListenerApi(
            rig.service,
            lambda: "emission",
            lambda: LOGIN,
            runner=runner,
            limiter=RateLimiter(1000, 1.0),
            key=(lambda: key) if key else None,
            log=lines.append,
        )
        return rig, api

    def post(self, api, key=None, body=None):
        body = body if body is not None else emission_body()
        return api.handle(
            "POST", "/emission", self.body_headers(body, key), io.BytesIO(body)
        )

    def test_runner_exception_logs_class_stage_size_and_frames_but_not_the_message(
        self,
    ):
        def runner(fn):
            raise KeyError(self.SECRET)

        lines = []
        _, api = self.api(runner, lines, key=self.LOGKEY)
        body = emission_body()
        r = self.post(api, key=self.LOGKEY, body=body)
        assert (r.status, r.body["error"]) == (500, "internal")
        text = "\n".join(lines)
        assert lines[0].startswith(
            "phone_listener: runner failed: KeyError (mode emission, "
        )
        assert f"{len(body)} bytes" in lines[0]
        assert "phone_listener: raised KeyError" in text
        assert "test_phone_listener.py:" in text and " in runner" in text
        assert all(line.startswith("phone_listener:") for line in lines)
        assert self.SECRET not in text and self.LOGKEY not in text

    def test_report_names_the_module_of_a_non_builtin_class(self):
        def runner(fn):
            raise wire.WireError("bad_magic", self.SECRET)

        lines = []
        _, api = self.api(runner, lines)
        assert self.post(api).status == 500
        assert "runner failed: trillium.phone_receiver.wire.WireError" in lines[0]
        assert self.SECRET not in "\n".join(lines)

    def test_chained_exception_is_followed_without_its_message(self):
        def runner(fn):
            try:
                raise ValueError(self.SECRET)
            except ValueError as e:
                raise RuntimeError("outer " + self.SECRET) from e

        lines = []
        _, api = self.api(runner, lines)
        self.post(api)
        text = "\n".join(lines)
        assert "raised RuntimeError" in text and "from ValueError" in text
        assert self.SECRET not in text

    def test_report_keeps_only_the_innermost_frames(self):
        def deep(n):
            if n:
                return deep(n - 1)
            raise RuntimeError

        try:
            deep(40)
        except RuntimeError as e:
            lines = faillog.trace_lines(e)
        assert len(lines) == 1 + faillog.MAX_FRAMES
        assert lines[-1].endswith(" in deep")

    def test_failure_before_the_runner_names_its_stage(self):
        class Dies:
            def read(self, n=-1):
                raise TimeoutError("timed out")

        lines = []
        _, api = self.api(None, lines)
        body = emission_body()
        r = api.handle("POST", "/emission", self.body_headers(body), Dies())
        assert (r.status, r.body["error"]) == (500, "internal")
        assert lines[0].startswith(
            "phone_listener: handling at read_body failed: TimeoutError"
        )
        assert f"{len(body)} bytes" in lines[0]

    def test_failure_building_the_reply_names_its_stage(self):
        class Odd:
            ok = True
            error = None

            def __getattr__(self, name):
                raise AttributeError(name)

        lines = []
        _, api = self.api(lambda fn: Odd(), lines)
        assert self.post(api).status == 500
        assert lines[0].startswith(
            "phone_listener: handling at reply failed: AttributeError"
        )

    def test_runner_timeout_is_one_line(self):
        def runner(fn):
            raise DispatchTimeout()

        lines = []
        _, api = self.api(runner, lines)
        assert self.post(api).status == 504
        assert len(lines) == 1
        assert lines[0].startswith("phone_listener: runner timed out (mode emission, ")

    def test_engine_failure_logs_where_the_engine_raised_not_what_it_said(self):
        lines = []
        rig = Rig(log=lines.append)
        rig.engine.boom = True
        r = rig.post(emission_body())
        assert (r.status, r.body["error"]) == (500, "engine_error")
        text = "\n".join(lines)
        assert "phone_listener: engine feed failed: RuntimeError (mode emission" in text
        assert "in _on_audio_frame" in text and "in _feed" in text
        assert "phone_listener: service refused: engine_error (mode emission" in text
        assert "decoder fell over" not in text

    def test_pcm_engine_failure_is_logged_too(self):
        lines = []
        rig = Rig(mode="pcm", log=lines.append)
        rig.engine.boom = True
        assert rig.post(pcm_body()).status == 500
        assert "engine feed failed: RuntimeError (mode pcm" in "\n".join(lines)

    def test_gate_exception_is_logged(self):
        lines = []
        rig = Rig(log=lines.append)

        def boom():
            raise RuntimeError(self.SECRET)

        rig.service._install._is_enabled = boom
        assert rig.post(emission_body()).status == 500
        text = "\n".join(lines)
        assert "live gate failed: RuntimeError" in text and self.SECRET not in text

    @pytest.mark.parametrize(
        "setup,code",
        [
            (lambda rig: rig.state.update(enabled=False), "disabled"),
            (lambda rig: rig.state.update(record_all=True), "record_all_on"),
        ],
    )
    def test_refusals_with_no_exception_are_one_line_each(self, setup, code):
        lines = []
        rig = Rig(log=lines.append)
        setup(rig)
        assert rig.post(emission_body()).status == 503
        assert len(lines) == 1 and f"service refused: {code} (mode emission" in lines[0]

    def test_ordinary_traffic_logs_nothing(self):
        lines = []
        rig = Rig(log=lines.append)
        assert rig.post(emission_body()).status == 200
        assert rig.post(b"junk").status == 422
        assert rig.post(emission_body(), login="nobody@example.com").status == 403
        assert lines == []

    def test_default_log_is_print(self, capsys):
        rig = Rig()
        rig.engine.boom = True
        assert rig.post(emission_body()).status == 500
        out = capsys.readouterr().out
        assert "phone_listener: engine feed failed: RuntimeError" in out

    def test_a_log_that_raises_does_not_change_the_reply(self):
        def log(line):
            raise OSError("log closed")

        rig = Rig(log=log)
        rig.engine.boom = True
        assert rig.post(emission_body()).body["error"] == "engine_error"

    def test_over_a_real_socket_the_runner_failure_reaches_the_log(self):
        lines = []

        def runner(fn):
            raise RuntimeError(self.SECRET)

        _, api = self.api(runner, lines, key=self.LOGKEY)
        srv, _ = listener.start(api, 0)
        try:
            body = emission_body()
            conn = http.client.HTTPConnection(
                "127.0.0.1", srv.server_address[1], timeout=5
            )
            conn.request(
                "POST",
                "/emission",
                body=body,
                headers=self.body_headers(body, self.LOGKEY),
            )
            resp = conn.getresponse()
            payload = json.loads(resp.read())
            conn.close()
        finally:
            listener.stop(srv)
        assert (resp.status, payload["error"]) == (500, "internal")
        text = "\n".join(lines)
        assert "runner failed: RuntimeError" in text
        assert self.SECRET not in text and self.LOGKEY not in text

    def serve_once(self, api, key):
        """One real request against a listener whose `api.handle` is already patched."""
        srv, _ = listener.start(api, 0)
        try:
            conn = http.client.HTTPConnection(
                "127.0.0.1", srv.server_address[1], timeout=5
            )
            conn.request(
                "POST", "/emission", body=b"x", headers=self.body_headers(b"x", key)
            )
            try:
                conn.getresponse().read()
            except (http.client.HTTPException, OSError):
                pass  # the worker may drop the connection; the log is what is under test
            conn.close()
        finally:
            listener.stop(srv)

    def test_an_exception_escaping_handle_is_logged_by_the_request_handler(self):
        lines = []
        _, api = self.api(None, lines, key=self.LOGKEY)
        api.handle = lambda *a, **k: (_ for _ in ()).throw(BrokenPipeError(self.SECRET))
        self.serve_once(api, self.LOGKEY)
        text = "\n".join(lines)
        assert "request failed: BrokenPipeError" in text and self.SECRET not in text

    def test_a_failure_writing_the_reply_is_logged_by_the_worker(self):
        lines = []
        _, api = self.api(None, lines, key=self.LOGKEY)
        api.handle = lambda *a, **k: listener.Response(200, {"bad": object()})
        self.serve_once(api, self.LOGKEY)
        assert any("connection failed: TypeError" in line for line in lines)
