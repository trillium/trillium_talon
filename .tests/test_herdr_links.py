"""Herdr links overlay: history merge, non-blocking scan runner, grammar, draw.

No real herdr or herdr-links call is made: the runner tests use a fake Popen
or a throwaway python child process."""

import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from trillium.herdr_links import links_data as ld
from trillium.herdr_links import links_scan as ls

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "trillium" / "herdr_links"


def scan(*panes):
    return {"machine": None, "panes": list(panes), "all_urls": []}


def pane(tab_id, *urls, pane_id="w1:p1", error=None):
    p = {
        "pane_id": pane_id,
        "tab_id": tab_id,
        "urls": [{"url": u, "context": f"ctx {u}", "count": 1} for u in urls],
    }
    if error:
        p["read_error"] = error
    return p


# ── links_data ──


def test_records_from_scan_flattens_dedupes_and_skips_local_and_errors():
    data = scan(
        pane("w1:t1", "https://a.example", "http://localhost:3000/x", pane_id="w1:p1"),
        pane("w1:t1", "https://a.example", "https://b.example", pane_id="w1:p2"),
        pane("w1:t2", "https://c.example", error="boom"),
        pane(None, "https://d.example"),
    )
    recs = ld.records_from_scan(data, "mini0", "Zephyr", 100.0)
    assert sorted(r["url"] for r in recs) == ["https://a.example", "https://b.example"]
    assert all(r["host"] == "mini0" and r["tab_id"] == "w1:t1" for r in recs)
    assert all(r["tab_label"] == "Zephyr" and r["first_seen"] == 100.0 for r in recs)


@pytest.mark.parametrize("junk", [None, [], "x", {"panes": None}, {"panes": ["x", 3]}])
def test_records_from_scan_tolerates_junk(junk):
    assert ld.records_from_scan(junk, "", "", 1.0) == []


def test_merge_updates_existing_and_keeps_first_seen():
    first = ld.records_from_scan(scan(pane("t1", "https://a")), "", "local", 10.0)
    again = ld.records_from_scan(
        scan(pane("t1", "https://a", "https://b")), "", "local", 20.0
    )
    hist = ld.merge(ld.merge([], first), again)
    a = next(r for r in hist if r["url"] == "https://a")
    assert (a["first_seen"], a["last_seen"], a["seen_count"]) == (10.0, 20.0, 2)
    assert len(hist) == 2


def test_merge_same_url_on_two_hosts_is_two_records():
    local = ld.records_from_scan(scan(pane("w1:t1", "https://a")), "", "local", 1.0)
    remote = ld.records_from_scan(
        scan(pane("w1:t1", "https://a")), "mini0", "zephyr", 1.0
    )
    assert len(ld.merge(local, remote)) == 2


def test_merge_caps_by_oldest_last_seen():
    hist = []
    for i in range(10):
        hist = ld.merge(
            hist,
            ld.records_from_scan(scan(pane("t", f"https://{i}")), "", "", float(i)),
            max_records=4,
        )
    assert [r["url"] for r in hist] == [
        "https://9",
        "https://8",
        "https://7",
        "https://6",
    ]


def test_tab_rows_filters_host_and_tab_newest_first():
    hist = ld.merge(
        ld.records_from_scan(scan(pane("t1", "https://old")), "", "", 1.0),
        ld.records_from_scan(
            scan(pane("t1", "https://new"), pane("t2", "https://other")), "", "", 2.0
        )
        + ld.records_from_scan(scan(pane("t1", "https://remote")), "mini0", "", 3.0),
    )
    assert [r["url"] for r in ld.tab_rows(hist, "", "t1")] == [
        "https://new",
        "https://old",
    ]
    assert [r["url"] for r in ld.tab_rows(hist, "mini0", "t1")] == ["https://remote"]


def test_extend_frozen_never_moves_shown_numbers():
    rows = [{"url": u} for u in ["https://new", "https://a", "https://b"]]
    assert ld.extend_frozen(["https://a", "https://b"], rows) == [
        "https://a",
        "https://b",
        "https://new",
    ]


def test_pages():
    assert ld.page_count(0) == 1 and ld.page_count(9) == 1 and ld.page_count(10) == 2
    assert ld.page_bounds(1, 12) == (9, 12)
    assert ld.page_bounds(5, 12) == (9, 12)
    assert ld.page_bounds(-1, 3) == (0, 3)


@pytest.mark.parametrize(
    "s,out", [(5, "5s"), (61, "1m"), (7200, "2h"), (90000, "1d"), (-3, "0s")]
)
def test_short_age(s, out):
    assert ld.short_age(s) == out


def test_save_load_roundtrip_is_private_and_atomic(tmp_path):
    path = tmp_path / "sub" / "history.json"
    hist = ld.records_from_scan(scan(pane("t", "https://a")), "", "", 1.0)
    ld.save(hist, path)
    assert ld.load(path) == hist
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert [p.name for p in path.parent.iterdir()] == ["history.json"]


def test_load_missing_or_corrupt_is_empty(tmp_path):
    assert ld.load(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert ld.load(bad) == []


# ── links_scan ──


def test_scan_argv_local_and_remote():
    assert ls.scan_argv("hl", "", "w1:t1") == ["hl", "--json", "--tab", "w1:t1"]
    assert ls.scan_argv("hl", "mini0", "wK:t2") == [
        "hl",
        "--json",
        "--tab",
        "wK:t2",
        "--machine",
        "mini0",
    ]


class FakeProc:
    def __init__(self, argv, stdout=None, **kw):
        self.argv, self.returncode, self.killed = argv, None, False
        self.out = stdout.name

    def finish(self, payload, rc=0):
        with open(self.out, "w") as f:
            f.write(payload)
        self.returncode = rc

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class FakePopen:
    def __init__(self):
        self.procs = []

    def __call__(self, argv, **kw):
        p = FakeProc(argv, **kw)
        self.procs.append(p)
        return p


@pytest.fixture
def runner(tmp_path):
    clock = {"t": 0.0}
    popen = FakePopen()
    r = ls.ScanRunner(
        tool="hl", popen=popen, clock=lambda: clock["t"], tmp_dir=str(tmp_path)
    )
    r.popen, r.clock = popen, clock
    return r


def test_runner_one_at_a_time_and_parses_result(runner, tmp_path):
    runner.enqueue(ls.Job("", "t1", "local"))
    runner.enqueue(ls.Job("mini0", "t2", "zephyr"))
    assert runner.tick() == [] and len(runner.popen.procs) == 1
    assert runner.tick() == [] and len(runner.popen.procs) == 1  # still running
    runner.popen.procs[0].finish(json.dumps(scan(pane("t1", "https://a"))))
    (res,) = runner.tick()
    assert res.job.key == ("", "t1") and res.error is None
    assert res.data["panes"][0]["urls"][0]["url"] == "https://a"
    assert runner.popen.procs[1].argv[-2:] == ["--machine", "mini0"]
    assert (
        list(tmp_path.iterdir()) and len(list(tmp_path.iterdir())) == 1
    )  # only the running one


def test_runner_reports_herdr_links_error_json(runner):
    runner.enqueue(ls.Job("nosuch", "t1"))
    runner.tick()
    runner.popen.procs[0].finish(
        json.dumps({"error": "herdr pane list failed", "detail": "unknown machine"}), 1
    )
    (res,) = runner.tick()
    assert res.data is None and "unknown machine" in res.error


def test_runner_reports_non_json(runner):
    runner.enqueue(ls.Job("", "t1"))
    runner.tick()
    runner.popen.procs[0].finish("", 1)
    (res,) = runner.tick()
    assert "no JSON" in res.error


def test_runner_kills_after_timeout_and_moves_on(runner, tmp_path):
    runner.enqueue(ls.Job("mini0", "t1"))
    runner.enqueue(ls.Job("", "t2"))
    runner.tick()
    runner.clock["t"] = ls.SCAN_TIMEOUT + 0.1
    (res,) = runner.tick()
    assert runner.popen.procs[0].killed and "timed out" in res.error
    assert len(runner.popen.procs) == 2  # next job started in the same tick
    assert len(list(tmp_path.iterdir())) == 1


def test_runner_dedupes_and_front_promotes(runner):
    a, b = ls.Job("", "a"), ls.Job("", "b")
    runner.enqueue(a)
    runner.enqueue(b)
    runner.enqueue(ls.Job("", "a"))
    assert [j.tab_id for j in runner.queue] == ["a", "b"]
    runner.enqueue(ls.Job("", "b"), front=True)
    assert [j.tab_id for j in runner.queue] == ["b", "a"]
    runner.tick()
    assert runner.pending(("", "b")) and runner.pending(("", "a"))
    runner.enqueue(ls.Job("", "b"), front=True)  # running: not re-queued
    assert [j.tab_id for j in runner.queue] == ["a"]


def test_runner_start_failure_is_a_result_not_an_exception(tmp_path):
    def boom(*a, **k):
        raise FileNotFoundError("herdr-links")

    r = ls.ScanRunner(popen=boom, tmp_dir=str(tmp_path))
    r.enqueue(ls.Job("", "t1"))
    (res,) = r.tick()
    assert "could not start" in res.error and not r.busy
    assert list(tmp_path.iterdir()) == []


def _script(tmp_path, body):
    p = tmp_path / "fake-herdr-links"
    p.write_text(f"#!{sys.executable}\n{body}\n")
    p.chmod(0o755)
    return str(p)


def test_runner_real_child_never_blocks_tick(tmp_path):
    tool = _script(tmp_path, "import time, json; time.sleep(30)")
    r = ls.ScanRunner(tool=tool, timeout=0.5, tmp_dir=str(tmp_path / "out"))
    (tmp_path / "out").mkdir()
    r.enqueue(ls.Job("", "t1"))
    t0 = time.monotonic()
    assert r.tick() == []
    assert time.monotonic() - t0 < 0.5
    time.sleep(0.7)
    (res,) = r.tick()
    assert "timed out" in res.error
    assert list((tmp_path / "out").iterdir()) == []


def test_runner_real_child_passes_tab_and_machine(tmp_path):
    tool = _script(
        tmp_path,
        "import sys, json; print(json.dumps({'panes': [], 'argv': sys.argv[1:]}))",
    )
    r = ls.ScanRunner(tool=tool, tmp_dir=str(tmp_path))
    r.enqueue(ls.Job("mini0", "wK:t2"))
    r.tick()
    deadline = time.monotonic() + 5
    results = []
    while not results and time.monotonic() < deadline:
        time.sleep(0.05)
        results = r.tick()
    assert results[0].data["argv"] == ["--json", "--tab", "wK:t2", "--machine", "mini0"]


def test_scan_env_adds_local_bin():
    assert str(Path.home() / ".local" / "bin") in ls.scan_env()["PATH"].split(
        os.pathsep
    )


# ── grammar ──


def test_links_opens_only_by_tab_name():
    rules = [
        line.split(":")[0]
        for line in (PKG / "links.talon").read_text().splitlines()
        if line.startswith("^")
    ]
    assert rules == ["^{user.herdr_tab_names} links$"]


def test_active_grammar_is_tag_scoped():
    text = (PKG / "links_active.talon").read_text()
    assert text.startswith("tag: user.links_active\n-\n")
    for rule in (
        "link open <user.overlay_select>",
        "link copy <user.overlay_select>",
        "links close",
    ):
        assert rule in text


def test_show_tab_reuses_recall_switch():
    src = (PKG / "links.py").read_text()
    assert "actions.user.herdr_tab_focus(label)" in src


# ── overlay draw (stub canvas) ──


class _Bounds:
    def __init__(self, w):
        self.width = w


def test_overlay_draws_numbered_rows_across_pages(mock_canvas, monkeypatch):
    from talon import screen, ui

    from trillium.herdr_links import links_overlay as lo

    monkeypatch.setattr(ui, "main_screen", screen.main_screen, raising=False)
    # The skia Path stub has no rounded rects; the frame helpers are tested elsewhere.
    for helper in (
        "draw_dim_backdrop",
        "draw_panel_frame",
        "draw_separator",
        "draw_close_hint",
    ):
        monkeypatch.setattr(lo, helper, lambda *a, **k: None)
    monkeypatch.setattr(
        mock_canvas.paint,
        "measure_text",
        lambda text: (None, _Bounds(len(text) * mock_canvas.paint.textsize * 0.6)),
        raising=False,
    )
    rows = [
        {"url": f"https://example.com/{i}", "last_seen": time.time(), "live": i == 9}
        for i in range(12)
    ]
    lo._rows, lo._page, lo._title, lo._subtitle_host, lo._status = (
        rows,
        1,
        "Fixer",
        "",
        "",
    )
    lo._on_draw(mock_canvas, lo._overlay)
    texts = [t[3] for t in mock_canvas.texts()]
    flat = " | ".join(str(t) for t in texts)
    assert "Links › Fixer" in flat
    assert "page 2/2" in flat
    assert "10" in texts and "12" in texts and "1" not in texts
    assert "https://example.com/9" in flat
    assert len(mock_canvas.circles()) == 1  # live dot on row 10 only
