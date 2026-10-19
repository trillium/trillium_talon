"""Tests for the phone emission receiver against a fake engine (no Talon, no model)."""

import struct
import threading

import numpy as np
import pytest

from trillium.phone_receiver import wire
from trillium.phone_receiver.encoder import PhoneEncoder
from trillium.phone_receiver.receiver import PhoneReceiver

N_PCM = 12981  # -> T = 43 frames
T = 43
RNG = np.random.default_rng(0)


def emission(t=T):
    return RNG.normal(0, 5, (t, wire.TOKENS)).astype(np.float32)


def good(fp16=False, n_pcm=N_PCM, ts=1.25):
    return wire.pack(emission(wire.frames_for(n_pcm)), n_pcm, ts, fp16)


class FakeEngine:
    """Mimics the W2lEngine seam: `_on_audio_frame` -> `encoder.forward` -> native decode."""

    def __init__(self):
        self.lock = threading.RLock()
        self.encoder = "mic-encoder"
        self.native_calls = []
        self.frames = []

    def _on_audio_frame(self, samples, ts=0.0, *, pad=True):
        assert isinstance(samples, list) and pad
        out = self.encoder.forward(samples)
        assert out.shape[:2] == (1, 1) and out.shape[3] == wire.TOKENS
        assert out.dtype == np.float32 and out.flags.c_contiguous
        self.native_calls.append(out)
        self.frames.append((len(samples), ts))


class TestWire:
    @pytest.mark.parametrize("fp16", [False, True])
    def test_round_trip(self, fp16):
        em = emission()
        got = wire.parse_validate(wire.pack(em, N_PCM, 1.25, fp16))
        assert got.array.shape == (T, wire.TOKENS) and got.array.dtype == np.float32
        assert got.n_pcm == N_PCM and got.ts == 1.25
        tol = 5e-2 if fp16 else 0
        assert np.allclose(got.array, em, atol=tol, rtol=tol)

    def test_sizes_match_scout_report(self):
        assert len(wire.pack(emission(), N_PCM, 0.0, False)) == 5012
        assert len(wire.pack(emission(), N_PCM, 0.0, True)) == 2518

    def test_frames_formula(self):
        for n_pcm, t in [
            (33161 - 8000, 69),
            (41161 - 8000, 85),
            (20981 - 8000, 43),
            (12981 - 8000, 27),
        ]:
            assert wire.frames_for(n_pcm) == t

    def rejects(self, buf, code):
        with pytest.raises(wire.WireError) as e:
            wire.parse_validate(buf)
        assert e.value.code == code

    def test_wrong_magic(self):
        self.rejects(b"XXXX" + good()[4:], "bad_magic")

    def test_bad_dtype(self):
        b = bytearray(good())
        b[4] = 7
        self.rejects(bytes(b), "bad_dtype")

    def test_short_and_empty(self):
        self.rejects(b"", "short_header")
        self.rejects(good()[:23], "short_header")

    def test_truncated_and_trailing_body(self):
        self.rejects(good()[:-1], "body_length")
        self.rejects(good() + b"\0", "body_length")

    def test_transposed_header_is_a_t_mismatch(self):
        # A (29, T) array packed as if T were 29 but with the real n_pcm.
        body = emission().T.copy().tobytes()
        hdr = wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 29, N_PCM, 0.0)
        self.rejects(hdr + body, "frame_mismatch")

    def test_transposed_array_refused_by_shape(self):
        with pytest.raises(wire.WireError) as e:
            wire.validate_array(emission().T)
        assert e.value.code == "bad_shape"

    @pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
    @pytest.mark.parametrize("fp16", [False, True])
    def test_non_finite(self, bad, fp16):
        em = emission()
        em[3, 4] = bad
        self.rejects(wire.pack(em, N_PCM, 0.0, fp16), "non_finite")

    def test_out_of_range(self):
        em = emission()
        em[0, 0] = 1e4
        self.rejects(wire.pack(em, N_PCM, 0.0), "out_of_range")

    def test_t_mismatch_with_n_pcm(self):
        self.rejects(wire.pack(emission(44), N_PCM, 0.0), "frame_mismatch")

    def test_zero_and_huge_t(self):
        hdr0 = wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 0, 0, 0.0)
        self.rejects(hdr0, "bad_frame_count")
        hdr = wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 2**32 - 1, 0, 0.0)
        self.rejects(hdr + b"\0" * 8, "bad_frame_count")

    def test_size_cap(self):
        self.rejects(good() + b"\0" * wire.MAX_PAYLOAD_BYTES, "payload_too_large")

    @pytest.mark.parametrize("ts", [float("nan"), float("inf"), -1.0])
    def test_bad_ts(self, ts):
        self.rejects(wire.pack(emission(), N_PCM, ts), "bad_ts")

    def test_not_bytes(self):
        self.rejects("TPE1", "not_bytes")
        self.rejects(None, "not_bytes")

    def test_validate_array_rejects(self):
        for a in (
            emission().astype(np.int32),
            emission()[None],
            emission()[:, :28],
            [[0.0] * 29],
        ):
            with pytest.raises(wire.WireError):
                wire.validate_array(a)
        with pytest.raises(wire.WireError):
            wire.validate_array(emission(), n_pcm=999)


class TestEncoder:
    def test_forward_shape_and_fifo(self):
        enc = PhoneEncoder()
        a, b = emission(), emission(5)
        enc.push(a), enc.push(b)
        out = enc.forward([])
        assert out.shape == (1, 1, T, wire.TOKENS) and np.array_equal(out[0, 0], a)
        assert enc.forward([]).shape == (1, 1, 5, wire.TOKENS)

    def test_empty_raises(self):
        with pytest.raises(RuntimeError):
            PhoneEncoder().forward([])

    def test_push_revalidates(self):
        enc = PhoneEncoder()
        with pytest.raises(wire.WireError):
            enc.push(emission().T)
        bad = emission()
        bad[0, 0] = np.nan
        with pytest.raises(wire.WireError):
            enc.push(bad)
        assert len(enc) == 0

    def test_queue_cap(self):
        enc = PhoneEncoder(max_queued=2)
        enc.push(emission()), enc.push(emission())
        with pytest.raises(wire.WireError) as e:
            enc.push(emission())
        assert e.value.code == "queue_full"


class TestReceiver:
    def test_accepts_and_feeds_engine(self):
        eng = FakeEngine()
        r = PhoneReceiver(eng)
        res = r.handle(good())
        assert res == (True, None, T, N_PCM)
        assert len(eng.native_calls) == 1 and eng.frames == [(N_PCM, 1.25)]
        assert (r.accepted, r.rejected) == (1, 0)

    def test_encoder_restored_and_queue_drained(self):
        eng = FakeEngine()
        r = PhoneReceiver(eng)
        r.handle(good())
        assert eng.encoder == "mic-encoder" and len(r.encoder) == 0

    def test_encoder_restored_when_engine_raises(self):
        eng = FakeEngine()
        eng._on_audio_frame = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
        r = PhoneReceiver(eng)
        res = r.handle(good())
        assert res.ok is False and res.error == "engine_error"
        assert eng.encoder == "mic-encoder" and len(r.encoder) == 0

    def test_malformed_payloads_never_reach_engine(self):
        eng = FakeEngine()
        r = PhoneReceiver(eng)
        nan = emission()
        nan[1, 1] = np.nan
        body = emission().T.copy().tobytes()
        bads = [
            b"",
            b"XXXX" + good()[4:],
            good()[:-4],
            wire.pack(nan, N_PCM, 0.0),
            wire.pack(emission(44), N_PCM, 0.0),
            wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 29, N_PCM, 0.0) + body,
            good() + b"\0" * wire.MAX_PAYLOAD_BYTES,
            None,
            "text",
            12,
        ]
        for b in bads:
            assert r.handle(b).ok is False
        assert eng.native_calls == [] and eng.frames == []
        assert eng.encoder == "mic-encoder"
        assert r.rejected == len(bads)

    def test_serves_good_payload_after_bad(self):
        eng = FakeEngine()
        r = PhoneReceiver(eng)
        assert not r.handle(b"junk").ok
        assert r.handle(good(fp16=True)).ok
        assert len(eng.native_calls) == 1

    def test_concurrent_submits_serialize(self):
        eng = FakeEngine()
        r = PhoneReceiver(eng)
        results = []
        ts = [
            threading.Thread(target=lambda: results.append(r.handle(good())))
            for _ in range(16)
        ]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert all(x.ok for x in results) and len(eng.native_calls) == 16
        assert eng.encoder == "mic-encoder"
