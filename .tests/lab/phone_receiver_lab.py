"""Lab acceptance for the phone receiver. Run inside the Talon REPL, NOT under pytest:

    ~/.talon/bin/repl   then:   PHONE_LAB_DIR = "/path/to/wavs"; exec(open("<this file>").read())

PHONE_LAB_DIR holds `*.wav` (16 kHz mono int16, synthetic TTS, never a recording). The script
builds a PRIVATE W2lEngine that is never registered with `speech_system`, decodes each wav with
the engine's own model (reference), then feeds the same utterance's emission through
`PhoneReceiver` (fp32 and fp16) and compares words, timings and reject flag. It then fires a
malformed-payload battery and checks the engine's decoder was not called. It only reads the
live engine's `_model_info` and `grammar` to construct the private one.
"""

import glob
import json
import os
import sys
import time
import traceback
import wave

import numpy as np

REPO = os.environ.get("PHONE_LAB_REPO") or os.path.abspath(os.path.join(os.path.dirname(globals().get("__file__", ".")), "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import talon.engines.w2l as W  # noqa: E402
from talon import speech_system  # noqa: E402

for _m in [m for m in sys.modules if m.startswith("trillium.phone_receiver")]:
    del sys.modules[_m]  # pick up edits on re-run
from trillium.phone_receiver import wire  # noqa: E402
from trillium.phone_receiver.receiver import PhoneReceiver  # noqa: E402

P = lambda *a: print("LAB", *a, flush=True)  # noqa: E731
WAV_DIR = PHONE_LAB_DIR  # noqa: F821 - set by the caller
TOL_TS = 0.0  # timings must be identical, not close


def summarize(j):
    m = j["_metadata"]
    return {
        "words": [(str(w), round(w.start, 4), round(w.end, 4)) for w in j["phrase"]],
        "reject": m["reject"],
    }


def load_pcm(path):
    w = wave.open(path)
    raw = w.readframes(w.getnframes())
    assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
    w.close()
    return np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0


try:
    live = speech_system.engine.engine
    lab = W.W2lEngine(info=live._model_info)
    lab.load()
    lab.enable()
    lab.sync_grammar(live.grammar)
    assert lab is not live and getattr(speech_system.engine, "engine", None) is live
    got = []
    lab.register("phrase", lambda j: got.append(j))

    decode_calls = [0]
    _orig_decode = lab._decode

    def counting_decode(*a, **k):
        decode_calls[0] += 1
        return _orig_decode(*a, **k)

    lab._decode = counting_decode

    def wait():
        for _ in range(100):
            if got:
                return got[0]
            time.sleep(0.05)
        raise TimeoutError("no phrase dispatched")

    rx = PhoneReceiver(lab)
    real_encoder = lab.encoder
    rows, mismatches = [], 0
    for path in sorted(glob.glob(os.path.join(WAV_DIR, "*.wav"))):
        pcm = load_pcm(path)
        got.clear()
        lab._on_audio_frame(pcm.tolist(), 1.25, pad=True)
        ref = wait()
        want = summarize(ref)
        em = np.ascontiguousarray(ref["_emission"])
        assert em.shape[0] == wire.frames_for(len(pcm)), ("T formula", len(pcm), em.shape[0], wire.frames_for(len(pcm)))
        row = {"wav": os.path.basename(path), "words": [w[0] for w in want["words"]], "reject": want["reject"], "n_pcm": len(pcm), "T": em.shape[0]}
        for fp16 in (False, True):
            got.clear()
            t0 = time.perf_counter()
            res = rx.handle(wire.pack(em, len(pcm), 1.25, fp16))
            assert res.ok, res
            have = summarize(wait())
            row["fp16" if fp16 else "fp32"] = {"equal": have == want, "ms": round((time.perf_counter() - t0) * 1000, 2)}
            if have != want:
                mismatches += 1
                row["diff"] = {"want": want, "have": have}
        assert lab.encoder is real_encoder, "encoder left swapped"
        rows.append(row)
        P("utt", json.dumps(row))

    # T geometry: the validator's frame count must equal the real encoder's for every length
    geom_bad = []
    for n in list(range(600, 40000, 1021)) + [1, 2, 479, 480, 481, 1000]:
        got.clear()
        try:
            lab._on_audio_frame(((np.random.default_rng(n).normal(0, 0.05, n)).astype(np.float32)).tolist(), 1.0, pad=True)
            t = wait()["_emission"].shape[0]
        except Exception as e:  # noqa: BLE001
            geom_bad.append((n, type(e).__name__, wire.frames_for(n)))
            continue
        if t != wire.frames_for(n):
            geom_bad.append((n, t, wire.frames_for(n)))
    P("T geometry mismatches (n_pcm, real, formula):", geom_bad)

    # malformed battery: every one rejected, decoder never called, engine encoder untouched
    em = np.ascontiguousarray(ref["_emission"])
    n_pcm, T = len(pcm), em.shape[0]
    nan = em.copy(); nan[0, 0] = np.nan
    inf = em.copy(); inf[1, 1] = np.inf
    big = em.copy(); big[2, 2] = 1e6
    good = wire.pack(em, n_pcm, 1.25)
    battery = {
        "wrong_magic": b"XXXX" + good[4:],
        "transposed_29xT_header": wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 29, n_pcm, 0.0) + em.T.copy().tobytes(),
        "transposed_trimmed": wire.pack(em.T[:, :5].copy(), n_pcm, 0.0),
        "nan": wire.pack(nan, n_pcm, 0.0),
        "inf": wire.pack(inf, n_pcm, 0.0),
        "huge": wire.pack(big, n_pcm, 0.0),
        "t_mismatch": wire.pack(np.vstack([em, em[:1]]), n_pcm, 0.0),
        "truncated": good[:-3],
        "trailing": good + b"\0",
        "empty": b"",
        "oversize": good + b"\0" * wire.MAX_PAYLOAD_BYTES,
        "zero_t": wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 0, 0, 0.0),
        "huge_t": wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 2**32 - 1, 0, 0.0) + b"\0" * 8,
    }
    before = decode_calls[0]
    leaks = [name for name, b in battery.items() if rx.handle(b).ok]
    after_bad = decode_calls[0]
    got.clear()
    alive = rx.handle(good).ok and wait() is not None
    summary = {
        "utterances": len(rows),
        "phrase_mismatches": mismatches,
        "t_geometry_mismatches": geom_bad,
        "malformed_total": len(battery),
        "malformed_accepted": leaks,
        "decoder_calls_during_malformed": after_bad - before,
        "engine_serves_after_battery": alive,
        "encoder_restored": lab.encoder is real_encoder,
        "median_fp32_ms": float(np.median([r["fp32"]["ms"] for r in rows])),
    }
    P("SUMMARY", json.dumps(summary))
    P("PASS" if (len(rows) >= 20 and not mismatches and not geom_bad and not leaks and after_bad == before and alive) else "FAIL")
except Exception:
    P("EXC", traceback.format_exc().replace("\n", " | ")[-1500:])
