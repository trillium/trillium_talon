"""herdr_tabs resolver: label -> (workspace, tab), duplicates, ssh argv, herdr down.
subprocess is mocked; no real herdr/focus/open call is ever made."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "plugin" / "recall" / "herdr_tabs.py"
_spec = importlib.util.spec_from_file_location("herdr_tabs_under_test", _PATH)
ht = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ht)

TABS = [
    {"label": "mayor", "tab_id": "wY7:t5Q", "workspace_id": "wY7"},
    {"label": "Fixer", "tab_id": "wY5:t8F", "workspace_id": "wY5"},
    {"label": "1", "tab_id": "wA:t1", "workspace_id": "wA"},
    {"label": "1", "tab_id": "wB:t1", "workspace_id": "wB"},
    {"label": "", "tab_id": "wC:t1", "workspace_id": "wC"},
]


class Run:
    def __init__(self, tabs=TABS, exc=None):
        self.calls = []
        self.tabs, self.exc = tabs, exc

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        if self.exc:
            raise self.exc
        out = json.dumps({"result": {"tabs": self.tabs}})
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    ht._cache.clear()
    ht._misses.clear()
    run = Run()
    monkeypatch.setattr(ht.subprocess, "run", run)
    return run


def test_resolve_case_insensitive():
    assert ht.resolve("MAYOR") == ("wY7", "wY7:t5Q")
    assert ht.resolve("fixer") == ("wY5", "wY5:t8F")
    assert ht.resolve(" Fixer ") == ("wY5", "wY5:t8F")


def test_duplicate_label_refused():
    assert ht.resolve("1") is None


def test_missing_and_empty_label():
    assert ht.resolve("nope") is None
    assert ht.resolve("") is None


def test_unique_labels_skips_dupes_and_empty():
    assert ht.unique_labels(TABS) == {"mayor": "mayor", "fixer": "Fixer"}


def test_herdr_unavailable_returns_none(monkeypatch):
    monkeypatch.setattr(ht.subprocess, "run", Run(exc=FileNotFoundError("herdr")))
    assert ht.resolve("mayor") is None
    assert ht.fetch_tabs() is None
    assert ht.focus_tab("mayor") is False


def test_bad_json_returns_none(monkeypatch):
    monkeypatch.setattr(
        ht.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout="garbage"),
    )
    assert ht.fetch_tabs() is None


def test_failed_refresh_keeps_previous_cache(monkeypatch):
    assert ht.resolve("mayor")
    monkeypatch.setattr(ht.subprocess, "run", Run(exc=OSError("down")))
    ht.refresh()
    assert ht.get_tabs(allow_fetch=False)


def test_cache_ttl_avoids_second_subprocess(fresh):
    ht.resolve("mayor")
    ht.resolve("fixer")
    assert len(fresh.calls) == 1


def test_no_fetch_mode_never_runs_subprocess(fresh):
    assert ht.get_tabs(allow_fetch=False) == []
    assert ht.resolve("mayor", allow_fetch=False) is None
    assert fresh.calls == []


def test_ssh_command_construction():
    assert ht.herdr_cmd(["tab", "list"]) == ["herdr", "tab", "list"]
    assert ht.herdr_cmd(["tab", "list"], "box") == [
        "ssh",
        *ht.SSH_OPTS,
        "box",
        "herdr",
        "tab",
        "list",
    ]
    assert ht.focus_commands("w1", "w1:t2", "box") == [
        ["ssh", *ht.SSH_OPTS, "box", "herdr", "workspace", "focus", "w1"],
        ["ssh", *ht.SSH_OPTS, "box", "herdr", "tab", "focus", "w1:t2"],
        ["open", "-a", "WezTerm"],
    ]


def test_remote_fetch_uses_ssh_and_separate_cache(fresh):
    assert ht.resolve("mayor", host="box") == ("wY7", "wY7:t5Q")
    assert fresh.calls[0][:2] == ["ssh", "-o"]
    assert "box" in fresh.calls[0]
    ht.resolve("mayor")
    assert len(fresh.calls) == 2


def test_focus_tab_runs_three_commands_in_order(fresh):
    assert ht.focus_tab("mayor") is True
    assert fresh.calls[1:] == [
        ["herdr", "workspace", "focus", "wY7"],
        ["herdr", "tab", "focus", "wY7:t5Q"],
        ["open", "-a", "WezTerm"],
    ]


def test_focus_unknown_runs_nothing_but_list(fresh):
    assert ht.focus_tab("nope") is False
    assert fresh.calls == [["herdr", "tab", "list"]]


EMOJI_TABS = [
    {"label": "\U0001f48e\U0001f48e Fixer", "tab_id": "w1:t1", "workspace_id": "w1"},
    {"label": "\U0001f48e\U0001f451 mayor", "tab_id": "w2:t1", "workspace_id": "w2"},
    {
        "label": "\u2764\ufe0f\u200d\U0001f525 hot",
        "tab_id": "w3:t1",
        "workspace_id": "w3",
    },
    {"label": "\U0001f48e", "tab_id": "w4:t1", "workspace_id": "w4"},
    {"label": "\U0001f451 dup", "tab_id": "w5:t1", "workspace_id": "w5"},
    {"label": "\U0001f48e dup", "tab_id": "w6:t1", "workspace_id": "w6"},
]


def test_clean_label():
    assert ht.clean_label("\U0001f48e\U0001f48e Fixer") == "Fixer"
    assert ht.clean_label("  \u2764\ufe0f\u200d\U0001f525 hot  ") == "hot"
    assert ht.clean_label("\U0001f48e") == ""
    assert ht.clean_label("a-b") == "a-b"


def test_emoji_labels_match_stripped_text(monkeypatch):
    monkeypatch.setattr(ht.subprocess, "run", Run(tabs=EMOJI_TABS))
    assert ht.resolve("fixer") == ("w1", "w1:t1")
    assert ht.resolve("MAYOR") == ("w2", "w2:t1")
    assert ht.resolve("hot") == ("w3", "w3:t1")


def test_emoji_only_label_skipped_and_stripped_dupes_refused(monkeypatch):
    monkeypatch.setattr(ht.subprocess, "run", Run(tabs=EMOJI_TABS))
    assert ht.resolve("") is None
    assert ht.resolve("dup") is None
    assert ht.unique_labels(EMOJI_TABS) == {
        "fixer": "Fixer",
        "mayor": "mayor",
        "hot": "hot",
    }


# --- multi-host ---

ZEPHYR = [{"label": "💎0️⃣ Zephyr", "tab_id": "wK:t2", "workspace_id": "wK"}]


class MultiRun:
    """Per-host fake: host (or None) -> tabs list, or an exception to raise."""

    def __init__(self, by_host):
        self.by_host, self.calls = by_host, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        host = argv[argv.index("herdr") - 1] if argv[0] == "ssh" else None
        val = self.by_host.get(host)
        if isinstance(val, Exception):
            raise val
        out = json.dumps({"result": {"tabs": val or []}})
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")


def _multi(monkeypatch, by_host):
    run = MultiRun(by_host)
    monkeypatch.setattr(ht.subprocess, "run", run)
    return run


def test_remote_tab_resolves_and_focuses_with_ssh_argv(monkeypatch):
    run = _multi(monkeypatch, {None: TABS, "mini0": ZEPHYR})
    ht.refresh_all(["mini0"])
    assert ht.resolve_any("zephyr", ["mini0"]) == ("mini0", "wK", "wK:t2")
    run.calls.clear()
    assert ht.focus_any("Zephyr", ["mini0"]) is True
    assert run.calls == [
        ["ssh", *ht.SSH_OPTS, "mini0", "herdr", "workspace", "focus", "wK"],
        ["ssh", *ht.SSH_OPTS, "mini0", "herdr", "tab", "focus", "wK:t2"],
        ["open", "-a", "WezTerm"],
    ]


def test_resolve_any_runs_no_subprocess(monkeypatch):
    run = _multi(monkeypatch, {None: TABS, "mini0": ZEPHYR})
    assert ht.resolve_any("zephyr", ["mini0"]) is None  # cold cache
    assert run.calls == []


def test_unreachable_host_skipped_then_dropped(monkeypatch):
    run = _multi(monkeypatch, {None: TABS, "mini0": ZEPHYR})
    ht.refresh_all(["mini0"])
    run.by_host["mini0"] = subprocess.TimeoutExpired("ssh", 5)
    for _ in range(ht.MAX_MISSES - 1):
        ht.refresh_all(["mini0"])
        assert ht.resolve_any("zephyr", ["mini0"]) == ("mini0", "wK", "wK:t2")
        assert ht.resolve_any("mayor", ["mini0"])[0] is None  # local unaffected
    ht.refresh_all(["mini0"])
    assert ht.resolve_any("zephyr", ["mini0"]) is None
    assert ht.resolve_any("mayor", ["mini0"]) == (None, "wY7", "wY7:t5Q")


def test_cross_host_duplicate_refused(monkeypatch):
    dup = [{"label": "💎 Mayor", "tab_id": "wZ:t1", "workspace_id": "wZ"}]
    _multi(monkeypatch, {None: TABS, "mini0": dup + ZEPHYR})
    merged = ht.refresh_all(["mini0"])
    assert ht.resolve_any("mayor", ["mini0"]) is None
    assert "mayor" not in ht.unique_labels_all(merged)
    assert "zephyr" in ht.unique_labels_all(merged)


def test_local_only_unchanged(monkeypatch):
    _multi(monkeypatch, {None: TABS})
    merged = ht.refresh_all([])
    assert ht.resolve_any("fixer", []) == (None, "wY5", "wY5:t8F")
    assert set(ht.unique_labels_all(merged)) == {"mayor", "fixer"}


def test_voice_labels_exclude_fm_workers(monkeypatch):
    tabs = [
        {"label": "fm-advisor", "tab_id": "w1:t1", "workspace_id": "w1"},
        {"label": "💎 FM-Scout", "tab_id": "w1:t2", "workspace_id": "w1"},
    ]
    _multi(monkeypatch, {None: TABS, "mini0": ZEPHYR + tabs})
    merged = ht.refresh_all(["mini0"])
    assert set(ht.voice_labels(merged)) == {"mayor", "fixer", "zephyr"}


def test_extra_allowed_readmits_fm_label(monkeypatch):
    tabs = [{"label": "fm-advisor", "tab_id": "w1:t1", "workspace_id": "w1"}]
    _multi(monkeypatch, {None: tabs})
    monkeypatch.setattr(ht, "EXTRA_ALLOWED", ["FM-Advisor"])
    merged = ht.refresh_all([])
    assert set(ht.voice_labels(merged)) == {"fm-advisor"}
