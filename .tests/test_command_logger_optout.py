"""command_logger_enabled: default-preserving opt-out, nothing written when off (no Talon)."""

import importlib.util
import os
import sys
import types
from types import SimpleNamespace

import pytest
from talon import Module, scope, settings

# Load command_logger.py alone: its sibling import (analyze_phrase) drags in native engine types.
_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "trillium", "core", "on_phrase", "command_logger",
)


def _load():
    def pkg(name, path=None):
        m = types.ModuleType(name)
        m.__path__ = [path] if path else []
        sys.modules[name] = m
        return m

    pkg("_clp")
    pkg("_clp.analyze_phrase")
    t = types.ModuleType("_clp.analyze_phrase.types")
    t.AnalyzedPhrase = object
    sys.modules["_clp.analyze_phrase.types"] = t
    pkg("_clp.command_logger", _DIR)
    spec = importlib.util.spec_from_file_location(
        "_clp.command_logger.command_logger", os.path.join(_DIR, "command_logger.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cl = _load()

SETTING = "user.command_logger_enabled"


@pytest.fixture
def sink(monkeypatch, tmp_path):
    writes = []
    monkeypatch.setattr(cl, "_write_jsonl", lambda payload: writes.append(payload))
    monkeypatch.setattr(cl, "COMMANDS_RECORDINGS_DIR", tmp_path / "commands")
    monkeypatch.setattr(scope, "get", lambda key, default=None: {"command"} if key == "mode" else default, raising=False)
    monkeypatch.setitem(type(settings)._values, SETTING, True)
    return writes, tmp_path


def phrase():
    word = SimpleNamespace(text="page", start=0.0, end=0.1)
    cmd = SimpleNamespace(phrase="page down", rule="page down", code="", path="", line=1, captures=[])
    return SimpleNamespace(phrase="page down", words=[word], commands=[cmd], audio=None)


def test_setting_module_present():
    assert isinstance(cl.mod, Module)


def test_default_on_logs(sink):
    writes, tmp = sink
    settings._values.pop(SETTING, None)  # undeclared in the stub -> still on
    cl.log_analyzed_phrase(phrase())
    assert len(writes) == 1


def test_off_writes_nothing_anywhere(sink):
    writes, tmp = sink
    settings._values[SETTING] = False
    cl.log_analyzed_phrase(phrase())
    cl.log_parrot_command("pop", sound="pop", action="repeat")
    assert writes == []
    assert not (tmp / "commands").exists()
