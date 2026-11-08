"""A reloaded parrot_integration must silence the ParrotSystem it replaces."""

import builtins
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "trillium/plugin/parrot/parrot_reload.py"


class FakeStream:
    def __init__(self):
        self.stopped = 0

    def stop(self):
        self.stopped += 1


class FakeSystem:
    def __init__(self):
        self.delegate = object()
        self.stream = FakeStream()


@pytest.fixture
def pr(monkeypatch):
    spec = importlib.util.spec_from_file_location("parrot_reload_under_test", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delattr(builtins, mod._KEY, raising=False)
    yield mod
    monkeypatch.delattr(builtins, mod._KEY, raising=False)


def test_first_load_has_nothing_to_retire(pr):
    assert pr.retire_previous_system() is False


def test_reload_silences_previous_delegate_and_stops_stream(pr):
    old = FakeSystem()
    pr.remember_system(old)
    assert pr.retire_previous_system() is True
    assert isinstance(old.delegate, pr.SilentDelegate)
    assert old.stream.stopped == 1


def test_silent_delegate_never_matches(pr):
    d = pr.SilentDelegate()
    assert d.power_threshold(99.0) is False
    assert d.pattern_match(object()) == set()


def test_retire_survives_a_system_without_a_stream(pr):
    old = FakeSystem()
    old.stream = None
    pr.remember_system(old)
    assert pr.retire_previous_system() is True
