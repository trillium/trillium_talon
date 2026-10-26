"""Goto-picker keystrokes for a spoken Herdr tab name (local / fixer / zephyr).

Why the picker query is the tab's RAW label: Herdr's Goto picker (verified in a
Herdr 0.9.5 lab) matches the typed text against machine names, workspace names
and terminal rows, and a machine/workspace hit pulls in every terminal under it.
"/zephyr" therefore matches the machine "mini0-zephyr" and Enter lands on that
machine's first terminal (fm-advisor), not the Zephyr tab. The raw label keeps
its emoji ("💎0️⃣ Zephyr"), so only the tab's own rows match.

No real herdr, ssh, WezTerm or keystroke is used."""

import importlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent / "plugin" / "recall"
_PKG = "recall_picker_under_test"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [str(_DIR)]
sys.modules[_PKG] = _pkg
ht = importlib.import_module(f"{_PKG}.herdr_tabs")
voice = importlib.import_module(f"{_PKG}.herdr_tab_voice")

LOCAL = [
    {"label": "💎👑 local", "tab_id": "wY7:t5Q", "workspace_id": "wY7"},
    {"label": "fm-worker", "tab_id": "wY7:t26", "workspace_id": "wY7"},
    {"label": "💎💎 Fixer", "tab_id": "wY5:t8F", "workspace_id": "wY5"},
]
MINI0 = [
    {"label": "fm-advisor", "tab_id": "wJ:t2", "workspace_id": "wJ"},
    {"label": "💎0️⃣ Zephyr", "tab_id": "wK:t2", "workspace_id": "wK"},
]
HOSTS = ["mini0"]

PREFIX = [("key", "ctrl-b"), ("key", "g"), ("key", "/")]


class Run:
    def __init__(self, by_host):
        self.by_host, self.calls = by_host, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        host = argv[argv.index("herdr") - 1] if argv[0] == "ssh" else None
        out = json.dumps({"result": {"tabs": self.by_host.get(host, [])}})
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")


@pytest.fixture(autouse=True)
def cache(monkeypatch):
    ht._cache.clear()
    ht._misses.clear()
    run = Run({None: LOCAL, "mini0": MINI0})
    monkeypatch.setattr(ht.subprocess, "run", run)
    monkeypatch.setattr(ht, "HOSTS", HOSTS)
    ht.refresh_all(HOSTS)
    run.calls.clear()
    return run


@pytest.mark.parametrize(
    "spoken, typed",
    [("local", "💎👑 local"), ("fixer", "💎💎 Fixer"), ("zephyr", "💎0️⃣ Zephyr")],
)
def test_goto_steps_type_the_raw_label(spoken, typed):
    assert ht.goto_steps(spoken) == [*PREFIX, ("insert", typed), ("key", "enter")]


@pytest.mark.parametrize("spoken", ["local", "fixer", "zephyr"])
def test_query_never_a_bare_machine_or_workspace_substring(spoken):
    typed = ht.picker_query(spoken)
    for machine in ("Local", "mini0-zephyr", "mini1-yonder", "firstmate"):
        assert typed.lower() not in machine.lower()


def test_unknown_label_falls_back_to_cleaned_label():
    assert ht.picker_query("Nope") == "Nope"
    assert ht.picker_query("  💎 Spaced  Out ") == "Spaced Out"


def test_duplicate_labels_fall_back_to_cleaned_label(cache):
    dup = [{"label": "💎 Twin", "tab_id": "a:t1"}, {"label": "Twin", "tab_id": "b:t1"}]
    cache.by_host[None] = dup
    ht.refresh_all(HOSTS)
    assert ht.picker_query("twin") == "twin"


class FakeActions:
    def __init__(self):
        self.steps = []

    def key(self, k):
        self.steps.append(("key", k))

    def insert(self, t):
        self.steps.append(("insert", t))

    def sleep(self, _):
        pass


@pytest.fixture
def fake(monkeypatch):
    fa = FakeActions()
    monkeypatch.setattr(voice, "actions", fa)
    return fa


@pytest.mark.parametrize(
    "spoken, typed",
    [("local", "💎👑 local"), ("fixer", "💎💎 Fixer"), ("zephyr", "💎0️⃣ Zephyr")],
)
def test_voice_action_keystrokes_when_viewing_a_remote(
    fake, monkeypatch, spoken, typed
):
    monkeypatch.setattr(voice, "_viewing_remote", lambda: True)
    voice.Actions.herdr_tab_focus(spoken)
    assert fake.steps == [*PREFIX, ("insert", typed), ("key", "enter")]


def test_voice_action_remote_target_uses_picker_even_when_viewing_local(
    fake, monkeypatch
):
    monkeypatch.setattr(voice, "_viewing_remote", lambda: False)
    voice.Actions.herdr_tab_focus("zephyr")
    assert fake.steps == [*PREFIX, ("insert", "💎0️⃣ Zephyr"), ("key", "enter")]


def test_voice_action_local_target_viewing_local_uses_cli_not_keys(
    fake, monkeypatch, cache
):
    monkeypatch.setattr(voice, "_viewing_remote", lambda: False)
    voice.Actions.herdr_tab_focus("local")
    assert fake.steps == []
    assert ["herdr", "tab", "focus", "wY7:t5Q"] in cache.calls
