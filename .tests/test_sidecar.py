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
        ("next", ["invoke", "dev-1", "app.pdf-next"]),
        ("previous", ["invoke", "dev-1", "app.pdf-prev"]),
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
        "sidecar",
        "show",
        "a.pdf",
        "--pane",
        "dev-1",
        "--token-file",
        str(t),
    ]


def test_back_and_list_argv():
    assert cli.back_argv("p") == ["sidecar", "show", "--back", "--pane", "p"]
    assert cli.list_argv("controls", "p") == [
        "sidecar",
        "affordances",
        "p",
        "--usable",
        "--json",
    ]
    assert cli.list_argv("nope", "p") is None


def test_run_reports_output(monkeypatch):
    got = []
    monkeypatch.setattr(
        cli.subprocess,
        "run",
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
        {"id": "dev-1", "name": "dev-1", "detail": "pdf", "app": "pdf", "mode": ""}
    ]
    assert cli.parse_rows(
        "controls", json.dumps([{"id": "pdf-next", "label": "Next"}])
    ) == [{"id": "pdf-next", "name": "Next", "detail": ""}]


@pytest.mark.parametrize("raw", ["", "not json", "{}", "3", None])
def test_parse_rows_tolerates_junk(raw):
    assert cli.parse_rows("panes", raw) == []


def test_talon_files_do_not_shadow_smooth_scroll():
    spoken = (_DIR / "sidecar.talon").read_text()
    for word in ("downer", "upper", "hiss", "shh"):
        assert word not in spoken
    assert all(l.startswith("sidecar ") for l in spoken.splitlines()[1:])


ALIASES = {"main": "dev-f5cf8b", "chrome": "dev-c49599"}


def _panes():
    raw = json.dumps(
        {
            "panes": [
                {"id": "dev-adc9d8", "mode": "default", "app": ""},
                {"id": "dev-c49599", "mode": "app", "app": "show-dev-c49599-16"},
                {"id": "dev-f5cf8b", "mode": "app", "app": "show-dev-f5cf8b-36"},
                {"id": "t1", "mode": "app", "app": "clock"},
            ]
        }
    )
    return cli.parse_rows("panes", raw)


def test_decorate_panes_names_and_current():
    rows = cli.decorate_panes(_panes(), ALIASES, "dev-f5cf8b")
    assert [r["name"] for r in rows] == [
        "Idle pane",
        "Chrome pane",
        "Main pane",
        "Clock pane",
    ]
    assert [r["id"] for r in rows][0] == "dev-adc9d8"
    assert rows[1]["detail"] == "dev-c49599"
    assert [r["current"] for r in rows] == [False, False, True, False]


def test_footer_lists_bound_commands():
    f = cli.footer_text("panes", 4)
    assert "pick 1-4" in f and "sidecar pane 1-4" in f
    assert "sidecar help" in f and "sidecar close" in f
    assert "pick" not in cli.footer_text("help", 5)
    assert "pick" not in cli.footer_text("panes", 0)


def _rules(name):
    out = []
    for line in (_DIR / name).read_text().splitlines():
        if ":" in line and not line.startswith(("tag", "-", "#")):
            out.append(line.split(":", 1)[0].strip().lstrip("^").rstrip("$"))
    return out


def test_command_table_matches_talon_files():
    import re

    def norm(rule):
        rule = re.sub(r"\{user\.sidecar_view\}", "<view>", rule)
        rule = re.sub(r"\{user\.sidecar_pane\}", "<name>", rule)
        return re.sub(r"<user\.overlay_select>|<number_small>", "<N>", rule)

    for scope, fname in (("global", "sidecar.talon"), ("modal", "sidecar_list_active.talon")):
        table = sorted(s for s, _, sc in cli.COMMANDS if sc == scope)
        bound = sorted(norm(r) for r in _rules(fname) if not r.startswith("key("))
        assert table == bound


def test_help_rows_cover_every_command():
    rows = cli.help_rows()
    assert [r["name"] for r in rows] == [s for s, _, _ in cli.COMMANDS]
    assert all(r["detail"] for r in rows)
