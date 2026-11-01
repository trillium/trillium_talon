"""Parrot clips: RAM ring, event clips, 'parrot missed', caps, and the no-IO audio path."""

import builtins
import importlib.util
import json
import os
import time
import types
import wave
from pathlib import Path

import numpy as np
import pytest

_FILE = Path(__file__).resolve().parent.parent / "trillium/plugin/parrot/parrot_clips.py"
SR = 16000


@pytest.fixture
def clips():
    spec = importlib.util.spec_from_file_location("parrot_clips_under_test", _FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_service(clips, tmp_path, **kw):
    t = [100.0]
    svc = clips.ClipService(clock=lambda: t[0], wall=lambda: 1_700_000_000.0 + t[0])
    svc.t = t
    svc.configure(enabled=True, root=str(tmp_path / "pc"), sample_rate=SR, **kw)
    return svc


def click_audio(seconds=0.1, at=0.04, amp=0.5, seed=0):
    """Quiet noise with a short loud burst, float32 like the mic callback."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 0.002, int(SR * seconds)).astype(np.float32)
    a = int(SR * at)
    x[a : a + 160] += (amp * np.hanning(160)).astype(np.float32)
    return x


def play(svc, audio, step=0.01, power=0.0):
    """Feed audio in 10ms chunks, ticking the clock like real frames."""
    n = int(SR * step)
    for i in range(0, len(audio), n):
        svc.feed(audio[i : i + n])
        svc.t[0] += step
        svc.tick(power)


class Frame:
    def __init__(self, power, classes):
        self.power, self.classes = power, classes


def read_wav(p):
    with wave.open(str(p)) as w:
        return w.getframerate(), w.getnframes()


def metas(tmp_path):
    return [json.loads(p.read_text()) for p in (tmp_path / "pc" / "_meta").glob("*.json")]


def test_ring_wraps_and_snapshot_is_the_latest(clips):
    ring = clips.AudioRing(SR, 1.0)
    ring.write(np.arange(SR * 3 // 2, dtype=np.int16))  # wraps once
    pcm, start = ring.snapshot(ring.total, 100)
    assert start == SR * 3 // 2 - 100
    assert list(pcm) == list(range(SR * 3 // 2 - 100, SR * 3 // 2))


def test_ring_scales_float_and_clips(clips):
    ring = clips.AudioRing(SR, 1.0)
    ring.write(np.array([0.5, -2.0, 2.0], dtype=np.float32))
    pcm, _ = ring.snapshot(ring.total, 3)
    assert list(pcm) == [16383, -32768, 32767]


def test_segments_find_the_click_not_the_noise_floor(clips):
    segs = clips.find_segments((click_audio(1.0, 0.4) * 32767).astype(np.int16), SR)
    assert segs and 330 <= segs[0]["start_ms"] <= 420
    assert segs[0]["end_ms"] - segs[0]["start_ms"] < 150


def test_segments_none_in_silence(clips):
    assert clips.find_segments(np.zeros(SR, dtype=np.int16), SR) == []


def test_event_saves_clip_and_sidecar_with_rejected_near_miss(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    play(svc, np.zeros(SR, dtype=np.float32))
    classes = {"lip_pop": 0.6, "alviolar_tongue_click": 0.3, "silence": 0.1, "x": 0.0}
    svc.tick(50.0)  # event opens
    svc.frame(Frame(50.0, classes), set(), lambda f, a: {"tongue-click": "throttled"})
    play(svc, click_audio(1.0, 0.05), power=50.0)
    play(svc, np.zeros(SR, dtype=np.float32), power=0.0)
    svc.drain()
    root = tmp_path / "pc"
    (m,) = metas(tmp_path)
    assert m["kind"] == "auto" and m["fired"] == [] and m["confirmed"] is False
    assert m["suppressed"] == {"tongue-click": "throttled"}
    assert [p["label"] for p in m["probabilities"]] == [
        "lip_pop",
        "alviolar_tongue_click",
        "silence",
    ]
    assert m["detected_label"] == "lip_pop" and m["power"] == 50.0
    assert read_wav(root / m["source_wav"])[0] == SR
    assert m["start_ms"] is not None and m["end_ms"] > m["start_ms"]
    assert (root / m["segment_wav"]).exists()
    for k in (
        "source_wav",
        "start_ms",
        "end_ms",
        "label",
        "intended",
        "detected_label",
        "probabilities",
        "confirmed",
    ):
        assert k in m


def test_missed_works_with_no_event_ever_detected(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    play(svc, click_audio(6.0, 3.0), power=0.0)  # sound never crossed the floor
    assert svc.mark_missed("alviolar_tongue_click")
    svc.drain()
    root = tmp_path / "pc"
    (m,) = metas(tmp_path)
    assert m["kind"] == "missed" and m["intended"] == "alviolar_tongue_click"
    assert m["intended_but_missed"] is True and m["detected_label"] is None
    assert m["source_wav"].startswith("_source/alviolar_tongue_click/")
    assert m["segment_wav"].startswith("alviolar_tongue_click/")
    assert read_wav(root / m["source_wav"])[1] == SR * 5  # the whole buffer window
    # training layout: the sound folder holds only the trimmed wav
    assert [p.suffix for p in (root / "alviolar_tongue_click").iterdir()] == [".wav"]


def test_missed_without_sound_goes_to_unlabeled(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    play(svc, click_audio(2.0, 1.0))
    svc.mark_missed(None)
    svc.drain()
    (m,) = metas(tmp_path)
    assert m["intended"] is None and m["segment_wav"].startswith("unlabeled/")


def test_missed_links_the_recent_auto_clip(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    svc.tick(50.0)
    svc.frame(Frame(50.0, {"hiss_sound": 0.9}), {"hiss"}, lambda f, a: {})
    play(svc, click_audio(1.0, 0.05), power=50.0)
    play(svc, np.zeros(SR, dtype=np.float32))
    svc.drain()
    svc.mark_missed("lip_pop")
    svc.drain()
    ms = metas(tmp_path)
    auto = next(m for m in ms if m["kind"] == "auto")
    missed = next(m for m in ms if m["kind"] == "missed")
    assert auto["intended"] == "lip_pop" and auto["intended_but_missed"]
    assert missed["linked_clip"] == auto["id"] and missed["fired"] == ["hiss"]
    assert missed["detected_label"] == "hiss_sound"


def test_kill_switch_drops_ram_and_stops_everything(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    play(svc, click_audio(1.0))
    svc.configure(enabled=False, root=str(tmp_path / "pc"))
    assert svc.ring is None and not svc.enabled
    svc.feed(click_audio(1.0))
    svc.tick(99.0)
    assert svc.mark_missed("x") is False
    assert not (tmp_path / "pc").exists()


def test_prune_count_cap_keeps_labeled_over_auto(clips, tmp_path):
    svc = make_service(clips, tmp_path, max_clips=3)
    for i in range(5):
        play(svc, click_audio(1.0, 0.1, seed=i))
        if i == 0:
            svc.mark_missed("lip_pop")
        svc.tick(50.0)
        svc.frame(Frame(50.0, {"silence": 1.0}), set(), None)
        play(svc, np.zeros(SR, dtype=np.float32))
        svc.drain()
    ms = metas(tmp_path)
    assert len(ms) <= 3
    assert any(m["kind"] == "missed" for m in ms)


def test_prune_size_cap_removes_everything_at_zero(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    play(svc, click_audio(2.0, 1.0))
    svc.mark_missed("lip_pop")
    svc.drain()
    store = clips.ClipStore(tmp_path / "pc", max_mb=0.0, max_age_days=30, max_clips=99)
    assert store.prune() == 1
    assert not list((tmp_path / "pc").rglob("*.wav"))


def test_full_queue_drops_instead_of_blocking(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    svc.queue.put = lambda *a, **k: pytest.fail("must not use blocking put")
    svc.queue = type(
        "Q", (), {"put_nowait": lambda self, j: (_ for _ in ()).throw(__import__("queue").Full())}
    )()
    t0 = time.perf_counter()
    assert [svc._submit({"kind": "x"}) for _ in range(50)] == [False] * 50
    assert time.perf_counter() - t0 < 0.5 and svc.dropped == 50


def test_callback_path_does_no_io(clips, tmp_path, monkeypatch):
    svc = make_service(clips, tmp_path)
    submitted = []
    svc.queue = type("Q", (), {"put_nowait": lambda self, j: submitted.append(j)})()

    def boom(*a, **k):
        raise AssertionError("IO on the audio path")

    for owner, name in [
        (builtins, "open"),
        (os, "replace"),
        (os, "makedirs"),
        (os, "stat"),
        (wave, "open"),
        (Path, "mkdir"),
        (Path, "write_text"),
    ]:
        monkeypatch.setattr(owner, name, boom)
    chunk = np.zeros(160, dtype=np.float32)
    for i in range(400):
        svc.feed(chunk)
        svc.t[0] += 0.01
        svc.tick(50.0 if 100 < i < 150 else 0.0)
        svc.frame(Frame(50.0, {"a": 1.0}), set(), lambda f, a: {})
    assert submitted  # the event closed and was only handed to the queue


def test_callback_errors_never_escape(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    svc.feed("not audio")
    svc.tick("nan")
    svc.frame(None, None)


def test_install_audio_tap_feeds_ring_and_calls_original(clips, tmp_path):
    svc = make_service(clips, tmp_path)
    seen = []
    system = types.SimpleNamespace(on_audio=lambda sid, ts, a: seen.append(len(a)) or "orig")
    assert clips.install_audio_tap(system, svc)
    assert system.on_audio(1, 2, np.zeros(160, dtype=np.float32)) == "orig"
    assert seen == [160] and svc.ring.total == 160


def test_callback_overhead_microbenchmark(clips, tmp_path, capsys):
    svc = make_service(clips, tmp_path)
    svc.queue = type("Q", (), {"put_nowait": lambda self, j: None})()
    chunk = np.random.default_rng(1).normal(0, 0.1, 1600).astype(np.float32)
    n = 5000
    t0 = time.perf_counter()
    for _ in range(n):
        svc.feed(chunk)
    feed_us = (time.perf_counter() - t0) / n * 1e6
    fr = Frame(50.0, {"a": 1.0})
    t0 = time.perf_counter()
    for i in range(n):
        svc.tick(50.0 if i % 40 < 20 else 0.0)
        svc.frame(fr, set(), None)
    tick_us = (time.perf_counter() - t0) / n * 1e6
    with capsys.disabled():
        print(f"\nparrot_clips per-callback: feed(100ms chunk)={feed_us:.1f}us tick+frame={tick_us:.1f}us")
    assert feed_us < 500 and tick_us < 200
