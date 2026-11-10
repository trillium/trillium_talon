"""'demo down' and 'demo up' are exact opposites: same gesture, mirrored, never cut short.

The helper's own checks live in plugin/smooth_scroll/helper-rs (cargo test); the
last test here runs them. The rest cover the Python side: one code path for both
directions, and chained commands queued instead of cutting each other off.
"""

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_FOLDER = Path(__file__).resolve().parent.parent / "plugin" / "smooth_scroll"


class FakeProc:
    def __init__(self, args):
        self.args = args
        self.running = True
        self.killed = False

    def poll(self):
        return None if self.running else 0

    def kill(self):
        self.killed = True
        self.running = False

    def wait(self):
        pass


@pytest.fixture
def ss(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "smooth_scroll_under_test", _FOLDER / "smooth_scroll.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    helper = tmp_path / "helper"
    helper.touch()
    profile = tmp_path / "profile.jsonl"
    profile.touch()
    monkeypatch.setattr(mod, "HELPER", helper)
    monkeypatch.setattr(mod, "PROFILE_FILE", profile)
    overrides = {}
    monkeypatch.setattr(mod, "_overrides", overrides)
    defaults = {
        "pixels": 11,
        "frames": 30,
        "frame_ms": 16,
        "decay": 0.92,
        "min_pixels": 0.5,
    }
    monkeypatch.setattr(
        mod, "_get", lambda name: overrides.get(name, defaults.get(name))
    )
    spawned, jobs, notes = [], {}, []
    monkeypatch.setattr(
        mod, "_spawn", lambda args: spawned.append(FakeProc(args)) or spawned[-1]
    )
    ids = iter(range(1, 1000))

    def interval(_period, fn):
        job = next(ids)
        jobs[job] = fn
        return job

    monkeypatch.setattr(mod.cron, "interval", interval)
    monkeypatch.setattr(mod.cron, "cancel", lambda job: jobs.pop(job, None))
    monkeypatch.setattr(mod.app, "notify", notes.append)
    monkeypatch.setattr(mod, "_proc", None)
    monkeypatch.setattr(mod, "_hold_proc", None)
    monkeypatch.setattr(mod, "_poll_job", None)
    monkeypatch.setattr(mod, "_queue_job", None)
    monkeypatch.setattr(mod, "_queue", [])
    mod.spawned, mod.jobs, mod.notes = spawned, jobs, notes

    def tick():
        """Run the queue's cron job once, as Talon would."""
        if mod._queue_job is not None:
            jobs[mod._queue_job]()

    mod.tick = tick
    return mod


def directions(mod):
    return [p.args[4] for p in mod.spawned]


def test_down_and_up_differ_only_in_direction(ss):
    ss.Actions.smooth_scroll_mimic("down")
    ss.spawned[-1].running = False
    ss.Actions.smooth_scroll_mimic("up")
    down, up = (p.args for p in ss.spawned)
    assert (down[4], up[4]) == ("down", "up")
    assert down[:4] == up[:4]
    assert down[5:] == up[5:]  # same distance scale, same stretch, no extras


def test_down_and_up_follow_the_pixels_setting_together(ss):
    ss._overrides["pixels"] = 22  # same dict _get reads
    ss.Actions.smooth_scroll_mimic("down")
    ss.spawned[-1].running = False
    ss.Actions.smooth_scroll_mimic("up")
    assert [p.args[5] for p in ss.spawned] == ["2.000", "2.000"]


def test_unknown_direction_plays_nothing(ss):
    ss.Actions.smooth_scroll_mimic("sideways")
    assert ss.spawned == []
    assert ss.notes


def test_chained_commands_are_not_cut_short(ss):
    """'demo down demo up' said in one breath: both play in full, in order."""
    ss.Actions.smooth_scroll_mimic("down")
    first = ss.spawned[0]
    ss.Actions.smooth_scroll_mimic("up")
    assert len(ss.spawned) == 1 and not first.killed  # waiting, not interrupting
    ss.tick()
    assert len(ss.spawned) == 1  # first still playing
    first.running = False
    ss.tick()
    assert directions(ss) == ["down", "up"]
    assert not first.killed
    assert "cancel" not in ss.spawned[1].args  # nothing was cut off
    ss.spawned[1].running = False
    ss.tick()
    assert ss._queue_job is None and ss._queue == []  # drain job retires itself


def test_a_long_chain_plays_every_gesture_in_order(ss):
    for d in ["down", "down", "up", "down", "up"]:
        ss.Actions.smooth_scroll_mimic(d)
    for _ in range(5):
        ss.spawned[-1].running = False
        ss.tick()
    assert directions(ss) == ["down", "down", "up", "down", "up"]
    assert not any(p.killed for p in ss.spawned)


def test_a_call_after_the_last_one_finished_still_queues_behind_waiting_ones(ss):
    ss.Actions.smooth_scroll_mimic("down")
    ss.Actions.smooth_scroll_mimic("up")  # waiting
    ss.spawned[0].running = False  # finished, but the queue has not ticked yet
    ss.Actions.smooth_scroll_mimic("down")
    ss.tick()
    ss.spawned[-1].running = False
    ss.tick()
    assert directions(ss) == ["down", "up", "down"]


def test_hold_replaces_a_waiting_chain(ss, monkeypatch):
    ss.Actions.smooth_scroll_mimic("down")
    ss.Actions.smooth_scroll_mimic("up")
    monkeypatch.setattr(ss, "HOLD_CONTROL", ss.HELPER.parent / "hold.touch")
    ss.Actions.smooth_scroll_hold("down")
    assert ss._queue == []


def test_parked_variant_still_replaces_the_playing_gesture(ss):
    ss.Actions.smooth_scroll_mimic("down")
    first = ss.spawned[0]
    ss._park_prepare = lambda *_: []
    ss.Actions.smooth_scroll_mimic_parked("up")
    assert first.killed
    assert "cancel" in ss.spawned[1].args


def test_talon_file_sends_each_direction_to_the_same_action():
    text = (_FOLDER / "smooth_scroll.talon").read_text()
    down = re.search(r"^demo down: (.*)$", text, re.M).group(1)
    up = re.search(r"^demo up: (.*)$", text, re.M).group(1)
    assert down == 'user.smooth_scroll_mimic("down")'
    assert up == 'user.smooth_scroll_mimic("up")'


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("cargo") is None,
    reason="the helper links CoreGraphics; needs macOS and cargo",
)
def test_helper_mirrors_up_exactly_in_rust():
    out = subprocess.run(
        ["cargo", "test", "--manifest-path", str(_FOLDER / "helper-rs" / "Cargo.toml")],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "down_is_the_exact_negation_of_up ... ok" in out.stdout
