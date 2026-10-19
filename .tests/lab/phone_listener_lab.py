"""Lab acceptance for the phone listener parity harness. Run inside the Talon REPL, NOT pytest:

    PHONE_LAB_REPO = "<this checkout>"; PHONE_LAB_DIR = "/path/to/wavs"; exec(open("<this file>").read())

PHONE_LAB_DIR holds `*.wav` (16 kHz mono int16, synthetic TTS, never a recording). Like
phone_receiver_lab.py it builds a PRIVATE W2lEngine that is never registered with
`speech_system`, and reads the live engine only for `_model_info` and `grammar`. Each wav goes
down both listener paths on that engine through `ListenerApi` (mode `emission`, then `pcm`)
and the phrase text and reject flag are diffed. The emission is the engine's own for the same
samples, so a mismatch means the PCM route or the harness is wrong, not the phone model. It
then serves one request of each kind over a real loopback socket (port 0) and fires a
malformed battery that must never reach the engine's decoder.
"""

import glob
import http.client
import json
import os
import sys
import time
import traceback
import wave

import numpy as np

# The caller's variable wins: Talon's own environment may still carry a PHONE_LAB_REPO that
# an earlier run exported for another checkout.
REPO = PHONE_LAB_REPO  # noqa: F821 - set by the caller

import importlib  # noqa: E402

# Talon's PluginFinder resolves a bare `trillium.*` import to the LIVE checkout under
# ~/.talon/user, whatever sys.path says, and a synthetic parent package still found another
# worktree. To test THIS checkout, load each module from its file under a private `phlab`
# name, in dependency order, so relative imports find them already in sys.modules.
import importlib.util  # noqa: E402
import types  # noqa: E402

import talon.engines.w2l as W  # noqa: E402
from talon import speech_system  # noqa: E402

for _m in [m for m in sys.modules if m == "phlab" or m.startswith("phlab.")]:
    del sys.modules[_m]  # pick up edits on re-run


def _load(name, rel):
    path = os.path.join(REPO, "trillium", *rel.split("/"))
    pkg = os.path.basename(path) == "__init__.py"
    spec = importlib.util.spec_from_file_location(
        name,
        path,
        submodule_search_locations=[os.path.dirname(path)] if pkg else None,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


(
    _load("phlab", "__init__.py")
    if os.path.exists(os.path.join(REPO, "trillium", "__init__.py"))
    else sys.modules.setdefault("phlab", types.ModuleType("phlab"))
)
for _name, _rel in [
    ("phlab.palette_feed", "palette_feed/__init__.py"),
    ("phlab.palette_feed.limits", "palette_feed/limits.py"),
    ("phlab.palette_feed.options", "palette_feed/options.py"),
    ("phlab.palette_feed.dispatch", "palette_feed/dispatch.py"),
    ("phlab.phone_receiver", "phone_receiver/__init__.py"),
    ("phlab.phone_receiver.wire", "phone_receiver/wire.py"),
    ("phlab.phone_receiver.encoder", "phone_receiver/encoder.py"),
    ("phlab.phone_receiver.receiver", "phone_receiver/receiver.py"),
    ("phlab.phone_receiver.live", "phone_receiver/live.py"),
    ("phlab.phone_receiver.service", "phone_receiver/service.py"),
    ("phlab.phone_receiver.listener", "phone_receiver/listener.py"),
    ("phlab.phone_receiver.parity", "phone_receiver/parity.py"),
]:
    _load(_name, _rel)
listener = sys.modules["phlab.phone_receiver.listener"]
parity = sys.modules["phlab.phone_receiver.parity"]
wire = sys.modules["phlab.phone_receiver.wire"]
LiveInstall = sys.modules["phlab.phone_receiver.live"].LiveInstall
PhoneService = sys.modules["phlab.phone_receiver.service"].PhoneService
PhraseTap = sys.modules["phlab.phone_receiver.service"].PhraseTap
RateLimiter = sys.modules["phlab.palette_feed.limits"].RateLimiter
assert wire.__file__.startswith(REPO), wire.__file__

P = lambda *a: print("LAB", *a, flush=True)  # noqa: E731
WAV_DIR = PHONE_LAB_DIR  # noqa: F821 - set by the caller
LOGIN = "lab@example.com"


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
    real_encoder = lab.encoder

    tap = PhraseTap()
    emissions = []
    lab.register("phrase", tap.on_phrase)
    lab.register(
        "phrase", lambda j: emissions.append(np.ascontiguousarray(j["_emission"]))
    )
    decode_calls = [0]
    _orig_decode = lab._decode

    def counting_decode(*a, **k):
        decode_calls[0] += 1
        return _orig_decode(*a, **k)

    lab._decode = counting_decode

    install = LiveInstall(lambda: lab, lambda: True, lambda: False)
    service = PhoneService(install, tap, wait_s=5.0)
    mode = {"v": "emission"}
    api = listener.ListenerApi(
        service,
        lambda: mode["v"],
        lambda: LOGIN,
        limiter=RateLimiter(1000, 1.0),
    )

    def reference_emission(samples):
        """The emission the engine's own encoder makes for these samples (the 'phone')."""
        emissions.clear()
        lab._on_audio_frame(samples.tolist(), 1.25, pad=True)
        for _ in range(100):
            if emissions:
                return emissions[0]
            time.sleep(0.05)
        raise TimeoutError("no phrase dispatched")

    utts = [
        parity.Utterance(os.path.basename(p), load_pcm(p))
        for p in sorted(glob.glob(os.path.join(WAV_DIR, "*.wav")))
    ]
    reports = {}
    for fp16 in (False, True):
        reports[fp16] = parity.run_parity(
            parity.api_poster(api, LOGIN),
            lambda m: mode.__setitem__("v", m),
            utts,
            reference_emission,
            fp16=fp16,
        )
        for line in reports[fp16].format().splitlines():
            P("fp16" if fp16 else "fp32", line)
    assert lab.encoder is real_encoder, "encoder left swapped"

    # one request of each kind over a real loopback socket
    srv, _ = listener.start(api, 0)
    port = srv.server_address[1]
    http_rows = []
    try:
        pcm = utts[0].pcm
        raw = parity.pcm16(pcm)
        em = reference_emission(wire.parse_pcm(raw))
        for m, ctype, body in (
            (
                "emission",
                listener.CONTENT_TYPES["emission"],
                wire.pack(em, len(pcm), 1.25),
            ),
            ("pcm", "audio/L16; rate=16000; channels=1", raw),
        ):
            mode["v"] = m
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request(
                "POST",
                "/emission",
                body,
                {"Tailscale-User-Login": LOGIN, "Content-Type": ctype},
            )
            r = c.getresponse()
            http_rows.append((m, r.status, json.loads(r.read())))
            c.close()
    finally:
        listener.stop(srv)
    P("HTTP", json.dumps(http_rows))

    # malformed battery: refused, decoder never called, engine still serving
    mode["v"] = "emission"
    good = wire.pack(em, len(pcm), 1.25)
    battery = [
        b"",
        b"XXXX" + good[4:],
        good[:-3],
        good + b"\0",
        good + b"\0" * wire.MAX_PAYLOAD_BYTES,
        wire.HEADER.pack(wire.MAGIC, 0, 0, 0, 29, len(pcm), 0.0)
        + em.T.copy().tobytes(),
    ]
    before = decode_calls[0]
    post = parity.api_poster(api, LOGIN)
    accepted = [
        i
        for i, b in enumerate(battery)
        if post(listener.CONTENT_TYPES["emission"], b, 1.0)[0] == 200
    ]
    mode["v"] = "pcm"
    accepted += [
        100 + i
        for i, b in enumerate([b"", b"\0", b"\0" * 6])
        if post("audio/L16; rate=16000", b, 1.0)[0] == 200
    ]
    after_bad = decode_calls[0]
    mode["v"] = "emission"
    alive = post(listener.CONTENT_TYPES["emission"], good, 1.25)[0] == 200

    ok = all(r.identical for r in reports.values()) and len(utts) >= 20
    summary = {
        "utterances": len(utts),
        "fp32": reports[False].summary(),
        "fp16": reports[True].summary(),
        "http": [(m, s, b.get("ok"), b.get("text")) for m, s, b in http_rows],
        "malformed_accepted": accepted,
        "decoder_calls_during_malformed": after_bad - before,
        "alive_after": alive,
        "encoder_restored": lab.encoder is real_encoder,
    }
    P("SUMMARY", json.dumps(summary))
    P(
        "PASS"
        if ok
        and not accepted
        and after_bad == before
        and alive
        and all(s == 200 for _, s, _ in http_rows)
        else "FAIL"
    )
except Exception:
    P("EXC", traceback.format_exc().replace("\n", " | ")[-1500:])
