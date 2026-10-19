"""LiveInstall gating and the Talon glue declaration, against a fake engine (no Talon)."""

import importlib.util
import os
import threading

import numpy as np
import pytest
from talon import Module

from trillium.phone_receiver import wire
from trillium.phone_receiver.encoder import PhoneEncoder
from trillium.phone_receiver.live import LiveInstall

N_PCM = 12981
GLUE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "trillium",
    "phone_receiver",
    "phone_receiver_live.py",
)


class FakeEngine:
    def __init__(self):
        self.lock = threading.RLock()
        self.encoder = "mic-encoder"
        self.calls = 0
        self.encoder_seen = None

    def _on_audio_frame(self, samples, ts=0.0, *, pad=True):
        self.calls += 1
        self.encoder_seen = self.encoder
        self.encoder.forward(samples)


def good():
    em = np.random.default_rng(1).normal(0, 5, (wire.frames_for(N_PCM), 29))
    return wire.pack(em.astype(np.float32), N_PCM, 1.0)


def install(engine, enabled=True, record_all=False):
    return LiveInstall(lambda: engine, lambda: enabled, lambda: record_all)


def test_off_never_touches_engine():
    eng = FakeEngine()
    r = install(eng, enabled=False).handle(good())
    assert (r.ok, r.error) == (False, "disabled")
    assert eng.calls == 0 and eng.encoder == "mic-encoder"


def test_on_runs_and_restores_encoder():
    eng = FakeEngine()
    r = install(eng).handle(good())
    assert r.ok and eng.calls == 1
    assert isinstance(eng.encoder_seen, PhoneEncoder)
    assert eng.encoder == "mic-encoder"


def test_record_all_on_refuses():
    eng = FakeEngine()
    r = install(eng, record_all=True).handle(good())
    assert (r.ok, r.error) == (False, "record_all_on")
    assert eng.calls == 0


@pytest.mark.parametrize("engine", [None, object()])
def test_no_usable_engine(engine):
    assert install(engine).handle(good()).error == "no_engine"


def test_engine_getter_raising_is_no_engine():
    def boom():
        raise RuntimeError("no engine attached")

    r = LiveInstall(boom, lambda: True, lambda: False).handle(good())
    assert r.error == "no_engine"


def test_gate_checks_that_raise_are_contained():
    def boom():
        raise RuntimeError("settings unavailable")

    eng = FakeEngine()
    r = LiveInstall(lambda: eng, boom, lambda: False).handle(good())
    assert not r.ok and eng.calls == 0


def test_malformed_never_reaches_engine():
    eng = FakeEngine()
    inst = install(eng)
    for bad in (b"", b"XXXX" + good()[4:], good()[:-3], None):
        assert not inst.handle(bad).ok
    assert eng.calls == 0 and eng.encoder == "mic-encoder"


def test_toggle_leaves_no_encoder_swapped():
    eng = FakeEngine()
    state = {"on": True}
    inst = LiveInstall(lambda: eng, lambda: state["on"], lambda: False)
    for on in (True, False, True, False):
        state["on"] = on
        inst.handle(good())
        assert eng.encoder == "mic-encoder"


def test_heal_restores_a_leaked_phone_encoder():
    eng = FakeEngine()
    state = {"on": True}
    inst = LiveInstall(lambda: eng, lambda: state["on"], lambda: False)
    assert inst.handle(good()).ok
    eng.encoder = PhoneEncoder()  # simulate a swap that was never undone
    state["on"] = False
    assert inst.handle(good()).error == "disabled"
    assert eng.encoder == "mic-encoder"


def test_engine_change_rebuilds_receiver():
    a, b = FakeEngine(), FakeEngine()
    cur = {"e": a}
    inst = LiveInstall(lambda: cur["e"], lambda: True, lambda: False)
    assert inst.handle(good()).ok
    cur["e"] = b
    assert inst.handle(good()).ok
    assert (a.calls, b.calls) == (1, 1)
    assert b.encoder == "mic-encoder"


def test_glue_declares_setting_default_off(monkeypatch):
    calls = []
    monkeypatch.setattr(Module, "setting", lambda self, name, **kw: calls.append((name, kw)))
    spec = importlib.util.spec_from_file_location(
        "trillium.phone_receiver._glue_probe", GLUE_PATH
    )
    glue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(glue)
    assert calls and calls[0][0] == "phone_receiver_enabled"
    assert calls[0][1]["type"] is bool and calls[0][1]["default"] is False
    assert glue.SETTING == "user.phone_receiver_enabled"
