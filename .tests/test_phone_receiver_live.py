"""LiveInstall gating and the Talon glue declaration, against a fake engine (no Talon)."""

import importlib.util
import os
import threading

import numpy as np
import pytest
from talon import Module

from trillium.phone_receiver import wire
from trillium.phone_receiver.encoder import PhoneEncoder
from trillium.phone_receiver.live import LiveInstall, NoEngine, active_engine

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


class Proxy:
    """Talon's `EngineProxy`: `speech_system.engine`, with the real engine at `.engine`."""

    def __init__(self, engine):
        self.engine = engine

    def __repr__(self):
        return f"EngineProxy({self.engine!r})"


class Speech:
    def __init__(self, engine):
        self.engine = engine


def detail_for(engine_getter):
    lines = []
    r = LiveInstall(
        engine_getter, lambda: True, lambda: False, log=lines.append
    ).handle(good())
    assert (r.ok, r.error) == (False, "no_engine")
    return r.detail, lines


def test_active_engine_unwraps_the_proxy():
    eng = FakeEngine()
    assert active_engine(Speech(Proxy(eng))) is eng


def test_no_active_engine_says_so():
    detail, _ = detail_for(lambda: active_engine(Speech(None)))
    assert detail == "speech_system.engine is None: no speech engine is active"


def test_proxy_with_nothing_inside_is_named():
    detail, _ = detail_for(lambda: active_engine(Speech(Proxy(None))))
    assert detail == "EngineProxy(None) wraps no engine"


def test_active_engine_lookup_is_what_the_glue_calls():
    with pytest.raises(NoEngine):
        active_engine(Speech(None))
    with pytest.raises(NoEngine):
        active_engine(Speech(Proxy(None)))


class DragonLike:
    """An engine that is attached but is not a W2l engine: no lock, encoder or frame entry."""

    def __repr__(self):
        return "DragonEngine(dragon)"


def test_engine_without_the_w2l_surface_names_the_engine_and_what_it_lacks():
    detail, _ = detail_for(lambda: active_engine(Speech(Proxy(DragonLike()))))
    assert detail == (
        "DragonEngine(dragon) cannot take injected audio: "
        "it has no lock, encoder, _on_audio_frame"
    )


def test_w2l_engine_that_lost_its_encoder_says_only_that():
    eng = FakeEngine()
    del eng.encoder
    eng.__class__ = type(
        "W2lEngine", (FakeEngine,), {"__repr__": lambda s: "W2lEngine(x)"}
    )
    detail, _ = detail_for(lambda: eng)
    assert detail == "W2lEngine(x) cannot take injected audio: it has no encoder"


def test_lookup_that_raises_names_the_class_not_the_message_and_logs_where():
    def boom():
        raise RuntimeError("secret-looking message")

    detail, lines = detail_for(boom)
    assert detail == "engine lookup raised RuntimeError"
    text = "\n".join(lines)
    assert "phone_listener: engine lookup failed: RuntimeError" in text
    assert "secret-looking" not in text and "secret-looking" not in detail


def test_lookup_returning_none_is_named():
    detail, _ = detail_for(lambda: None)
    assert detail == "engine lookup returned None"


def test_detail_is_one_short_line_even_for_a_wild_repr():
    class Wild:
        def __repr__(self):
            return "W2lEngine(" + "very\nlong " * 100 + ")"

    detail, _ = detail_for(lambda: Wild())
    assert "\n" not in detail and len(detail) <= 200


def test_broken_repr_does_not_hide_the_refusal():
    class Broken:
        def __repr__(self):
            raise ValueError("no repr")

    detail, _ = detail_for(lambda: Broken())
    assert detail.startswith("Broken cannot take injected audio")


def test_other_refusals_carry_no_detail():
    eng = FakeEngine()
    assert install(eng, enabled=False).handle(good()).detail is None
    assert install(eng, record_all=True).handle(good()).detail is None
    assert install(eng).handle(good()).detail is None


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
    monkeypatch.setattr(
        Module, "setting", lambda self, name, **kw: calls.append((name, kw))
    )
    spec = importlib.util.spec_from_file_location(
        "trillium.phone_receiver._glue_probe", GLUE_PATH
    )
    glue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(glue)
    assert calls and calls[0][0] == "phone_receiver_enabled"
    assert calls[0][1]["type"] is bool and calls[0][1]["default"] is False
    assert glue.SETTING == "user.phone_receiver_enabled"
