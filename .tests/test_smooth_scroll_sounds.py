"""Hiss/shh scroll only right after "demo down"/"demo up": arming, expiry, debounce."""

import importlib.util
import types
from pathlib import Path

import pytest

_FILE = (
    Path(__file__).resolve().parent.parent
    / "plugin"
    / "smooth_scroll"
    / "smooth_scroll_sounds.py"
)


class Cmd:
    def __init__(self, trigger):
        self.trigger = trigger


@pytest.fixture
def sounds(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "smooth_scroll_sounds_under_test", _FILE
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    calls, fell_through, clock = [], [], [1000.0]
    last = [None]

    def last_command():
        if last[0] is None:
            raise IndexError
        return last[0], None

    fake = types.SimpleNamespace(
        user=types.SimpleNamespace(smooth_scroll_mimic=calls.append),
        core=types.SimpleNamespace(last_command=last_command),
        next=lambda: fell_through.append(True),
    )
    monkeypatch.setattr(mod, "actions", fake)
    monkeypatch.setattr(mod.time, "monotonic", lambda: clock[0])

    def say(trigger):
        last[0] = Cmd(trigger) if trigger else None
        mod._on_post_phrase(None)

    mod.say, mod.calls, mod.fell_through, mod.clock = say, calls, fell_through, clock
    return mod


def test_unarmed_falls_through(sounds):
    sounds.UserActions.noise_hiss()
    sounds.UserActions.noise_shh()
    assert sounds.calls == []
    assert len(sounds.fell_through) == 2


def test_demo_down_arms_hiss_down_and_shh_up(sounds):
    sounds.say("demo down")
    sounds.UserActions.noise_hiss()
    sounds.clock[0] += 1
    sounds.UserActions.noise_shh()
    assert sounds.calls == ["down", "up"]
    assert sounds.fell_through == []


def test_demo_up_also_arms(sounds):
    sounds.say("demo up")
    sounds.UserActions.noise_hiss()
    assert sounds.calls == ["down"]


@pytest.mark.parametrize("other", ["downer", "demo flat down", "wheel down", None])
def test_other_commands_do_not_arm(sounds, other):
    sounds.say(other)
    sounds.UserActions.noise_hiss()
    assert sounds.calls == []
    assert sounds.fell_through == [True]


def test_next_command_disarms(sounds):
    sounds.say("demo down")
    sounds.say("wheel down")
    sounds.UserActions.noise_hiss()
    assert sounds.calls == []
    assert sounds.fell_through == [True]


def test_expires_after_20_seconds(sounds):
    sounds.say("demo down")
    sounds.clock[0] += 19.9
    sounds.UserActions.noise_hiss()
    sounds.clock[0] += 0.2
    sounds.UserActions.noise_hiss()
    assert sounds.calls == ["down"]
    assert sounds.fell_through == [True]


def test_debounce_swallows_rapid_repeats_without_falling_through(sounds):
    sounds.say("demo down")
    sounds.UserActions.noise_hiss()
    sounds.clock[0] += 0.1
    sounds.UserActions.noise_hiss()
    sounds.clock[0] += 0.3
    sounds.UserActions.noise_hiss()
    assert sounds.calls == ["down", "down"]
    assert sounds.fell_through == []


def test_sounds_do_not_extend_the_window(sounds):
    sounds.say("demo down")
    for _ in range(5):
        sounds.clock[0] += 5
        sounds.UserActions.noise_hiss()
    assert len(sounds.calls) == 3  # t=5,10,15 scroll; t=20 and 25 are expired
    assert len(sounds.fell_through) == 2
