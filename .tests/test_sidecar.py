"""Sidecar voice plugin: argv building, verb table, background runner, row parsing.

No real `sidecar` is run: subprocess.run is faked."""

import importlib
import json
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent / "trillium" / "plugin" / "sidecar"
_PKG = "sidecar_under_test"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [str(_DIR)]
sys.modules[_PKG] = _pkg
cli = importlib.import_module(f"{_PKG}.sidecar_cli")


@pytest.fixture(autouse=True)
def no_token(monkeypatch):
    monkeypatch.setattr(cli, "TOKEN_FILE", Path("/nonexistent/token"))


def wait(pred):
    for _ in range(100):
        if pred():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


@pytest.mark.parametrize(
    "verb, tail",
    [
        ("next", ["invoke", "dev-1", "pdf-next"]),
        ("previous", ["invoke", "dev-1", "pdf-prev"]),
        ("down", ["invoke", "dev-1", "scroll", "--direction", "down"]),
        ("up", ["invoke", "dev-1", "scroll", "--direction", "up"]),
        ("top", ["invoke", "dev-1", "scroll", "--direction", "top"]),
        ("bottom", ["invoke", "dev-1", "scroll", "--direction", "bottom"]),
    ],
)
def test_verb_argv(verb, tail):
    assert cli.verb_argv(verb, "dev-1") == ["sidecar", *tail]


def test_unknown_verb_is_none():
    assert cli.verb_argv("explode", "dev-1") is None


def test_token_file_attached_when_present(tmp_path, monkeypatch):
    t = tmp_path / "token"
    t.write_text("x")
    monkeypatch.setattr(cli, "TOKEN_FILE", t)
    assert cli.show_argv("a.pdf", "dev-1") == [
        "sidecar", "show", "a.pdf", "--pane", "dev-1", "--token-file", str(t),
    ]


def test_back_and_list_argv():
    assert cli.back_argv("p") == ["sidecar", "show", "--back", "--pane", "p"]
    assert cli.list_argv("controls", "p") == [
        "sidecar", "affordances", "p", "--usable", "--json",
    ]
    assert cli.list_argv("nope", "p") is None


def test_run_reports_output(monkeypatch):
    got = []
    monkeypatch.setattr(
        cli.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="hi", stderr=""),
    )
    cli.run(["sidecar"], lambda c, o: got.append((c, o)))
    wait(lambda: got)
    assert got == [(0, "hi")]


@pytest.mark.parametrize(
    "exc", [subprocess.TimeoutExpired("sidecar", 1), FileNotFoundError("sidecar")]
)
def test_run_swallows_errors(monkeypatch, exc):
    got = []

    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(cli.subprocess, "run", boom)
    cli.run(["sidecar", "x"], lambda c, o: got.append(c))
    wait(lambda: got)
    assert got == [1]


def test_parse_rows_variants():
    raw = json.dumps({"panes": [{"id": "dev-1", "app": "pdf"}, "junk"]})
    assert cli.parse_rows("panes", raw) == [
        {"id": "dev-1", "name": "dev-1", "detail": "pdf"}
    ]
    assert cli.parse_rows("controls", json.dumps([{"id": "pdf-next", "label": "Next"}])) == [
        {"id": "pdf-next", "name": "Next", "detail": ""}
    ]


@pytest.mark.parametrize("raw", ["", "not json", "{}", "3", None])
def test_parse_rows_tolerates_junk(raw):
    assert cli.parse_rows("panes", raw) == []


def test_talon_files_do_not_shadow_smooth_scroll():
    spoken = (_DIR / "sidecar.talon").read_text()
    for word in ("downer", "upper", "hiss", "shh"):
        assert word not in spoken
    assert all(l.startswith("sidecar ") for l in spoken.splitlines()[1:])
