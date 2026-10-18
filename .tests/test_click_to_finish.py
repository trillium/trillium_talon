"""Tests for the pondering follow/steer submit-method logic."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import talon
from talon import ui

if not hasattr(talon, "speech_system"):
    talon.speech_system = MagicMock()

_PATH = Path(__file__).parent.parent / "trillium" / "core" / "click_to_finish.py"


@pytest.fixture
def cf(monkeypatch):
    spec = importlib.util.spec_from_file_location("click_to_finish_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    keys = []
    monkeypatch.setattr(module.actions, "key", keys.append, raising=False)
    module.keys = keys
    return module


def _focus(monkeypatch, title):
    monkeypatch.setattr(ui, "active_window", lambda: ui.Window(title=title))


@pytest.mark.parametrize("title", ["π - trillium_talon", "pi - ~/work", "Pi"])
def test_pi_titles_detected(cf, monkeypatch, title):
    _focus(monkeypatch, title)
    assert cf._is_pi_terminal()


@pytest.mark.parametrize("title", ["pip install foo", "zsh", "", "Google Chrome"])
def test_non_pi_titles_rejected(cf, monkeypatch, title):
    _focus(monkeypatch, title)
    assert not cf._is_pi_terminal()


def test_setting_word_only_when_alone(cf):
    assert cf._setting_word(["follow"]) == "follow"
    assert cf._setting_word(["Steer"]) == "steer"
    assert cf._setting_word(["follow", "up"]) is None
    assert cf._setting_word([]) is None
    assert cf._setting_word(["hello"]) is None


def test_pi_default_is_follow_on(cf, monkeypatch):
    _focus(monkeypatch, "π - repo")
    cf._submit()
    assert cf.keys == ["alt-enter"]


def test_pi_steer_uses_plain_enter(cf, monkeypatch):
    _focus(monkeypatch, "π - repo")
    cf._set_submit_method("steer")
    cf._submit()
    assert cf.keys == ["enter"]
    cf._set_submit_method("follow")
    cf._submit()
    assert cf.keys == ["enter", "alt-enter"]


def test_non_pi_always_plain_enter(cf, monkeypatch):
    _focus(monkeypatch, "zsh")
    cf._submit()
    assert cf.keys == ["enter"]
