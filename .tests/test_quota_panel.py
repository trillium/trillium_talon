"""Quota panel: quota-axi parsing, colors, non-blocking runner, glue, draw.

No real quota-axi call is made: the runner tests use a fake Popen or a
throwaway python child process. The fixture is a trimmed real `quota-axi --json`
output captured 2026-10-26 (codex token expired, OpenCode Go monthly at 0)."""

import json
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trillium.quota_panel import quota_data as qd
from trillium.quota_panel import quota_run as qr

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "trillium" / "quota_panel"
FIXTURE = Path(__file__).parent / "fixtures" / "quota_axi_2026-10-26.json"
NOW = datetime(2026, 10, 26, 19, 0, tzinfo=timezone.utc)


def fixture():
    return json.loads(FIXTURE.read_text())


def rows_by_provider():
    return {r.provider: r for r in qd.parse(fixture())}


# ── parse: the real output ──


def test_parse_real_output_one_row_per_subscription_in_order():
    rows = qd.parse(fixture())
    assert [r.label for r in rows] == ["CC", "OC", "GPT", "GRK", "AGY"]


def test_claude_headline_is_all_models_with_fable_dot():
    cc = rows_by_provider()["claude"]
    assert cc.percent == 22
    assert cc.color == qd.ORANGE  # 22% left; through_reset adds no bump
    assert cc.dot is True  # model:fable scope is at 0
    assert (cc.resets_at.month, cc.resets_at.day, cc.resets_at.hour) == (10, 27, 0)


def test_opencode_exhausted_is_red_zero():
    oc = rows_by_provider()["opencode-go"]
    assert (oc.percent, oc.color) == (0, qd.RED)
    assert oc.resets_at.month == 11 and oc.resets_at.day == 4


def test_codex_expired_token_is_a_normal_login_state():
    gpt = rows_by_provider()["codex"]
    assert gpt.percent is None
    assert gpt.note == "login"
    assert gpt.color == qd.GRAY


def test_grok_green_ignores_credits_field():
    grk = rows_by_provider()["grok"]
    assert (grk.percent, grk.color) == (89, qd.GREEN)


def test_agy_takes_lowest_scope_and_projected_exhaustion_bumps_to_orange():
    agy = rows_by_provider()["agy"]
    assert agy.percent == 68  # claude_gpt (68) beats gemini (79)
    assert agy.color == qd.ORANGE  # green by percent, bumped by runway
    assert agy.resets_at.day == 31  # claude_gpt_weekly, not the 5h window


def test_not_set_up_provider_is_setup_note():
    rows = qd.parse(fixture(), ["cursor"])
    assert (rows[0].percent, rows[0].note) == (None, "setup")


# ── parse: edge cases ──


@pytest.mark.parametrize("junk", [None, [], "x", 3, {}, {"providers": None}])
def test_parse_tolerates_junk_with_gray_na_rows(junk):
    rows = qd.parse(junk, ["claude", "grok"])
    assert [(r.percent, r.note) for r in rows] == [(None, "n/a")] * 2


def test_parse_unknown_provider_not_requested_is_ignored():
    raw = {"providers": [{"provider": "mystery", "windows": []}]}
    assert [r.provider for r in qd.parse(raw, ["grok"])] == ["grok"]


def test_fresh_provider_with_no_data_is_na():
    raw = {"providers": [{"provider": "grok", "state": {"status": "fresh"}}]}
    assert qd.parse(raw, ["grok"])[0].note == "n/a"


def test_windows_fallback_when_no_semantics_uses_lowest_window_and_dup_ids():
    raw = {
        "providers": [
            {
                "provider": "agy",
                "state": {"status": "fresh"},
                "windows": [
                    {
                        "id": "w",
                        "percentRemaining": 94,
                        "resetsAt": "2026-10-31T21:00:00Z",
                    },
                    {
                        "id": "w",
                        "percentRemaining": 31,
                        "resetsAt": "2026-11-01T07:00:00Z",
                    },
                ],
            }
        ]
    }
    row = qd.parse(raw, ["agy"])[0]
    assert (row.percent, row.color, row.resets_at.day) == (31, qd.YELLOW, 1)


def test_unavailable_other_error_is_na_and_auth_required_is_login():
    raw = {
        "providers": [
            {"provider": "grok", "state": {"status": "unavailable", "authStatus": "x"}},
            {"provider": "codex", "state": {"status": "auth_required"}},
        ]
    }
    rows = qd.parse(raw, ["grok", "codex"])
    assert [r.note for r in rows] == ["n/a", "login"]


def test_percent_is_clamped_and_rounded():
    raw = {
        "providers": [
            {
                "provider": "grok",
                "state": {"status": "fresh"},
                "quotaSemantics": {
                    "effectiveAvailability": [
                        {"scope": "all_products", "effectivePercentRemaining": 120.4}
                    ]
                },
            }
        ]
    }
    assert qd.parse(raw, ["grok"])[0].percent == 100


def test_parse_providers_validates_and_dedupes():
    assert qd.parse_providers("claude, grok,claude,bad name,$x") == ["claude", "grok"]
    assert qd.parse_providers("") == list(qd.LABELS)
    assert qd.parse_providers(None) == list(qd.LABELS)


# ── colors ──


@pytest.mark.parametrize(
    "pct,color",
    [
        (100, qd.GREEN),
        (50, qd.GREEN),
        (49, qd.YELLOW),
        (25, qd.YELLOW),
        (24, qd.ORANGE),
        (10, qd.ORANGE),
        (9, qd.RED),
        (0, qd.RED),
        (None, qd.GRAY),
    ],
)
def test_color_thresholds(pct, color):
    assert qd.color_for(pct) == color


@pytest.mark.parametrize(
    "pct,runway,color",
    [
        (90, "projected_exhaustion", qd.ORANGE),
        (15, "projected_exhaustion", qd.ORANGE),
        (5, "projected_exhaustion", qd.RED),
        (90, "exhausted_now", qd.RED),
        (90, "through_reset", qd.GREEN),
    ],
)
def test_runway_bumps_never_improve_a_color(pct, runway, color):
    assert qd.color_for(pct, runway) == color


# ── formatting ──


@pytest.mark.parametrize(
    "iso,out",
    [
        ("2026-10-26T22:12:00Z", "3h12m"),
        ("2026-10-31T01:00:00+00:00", "4d6h"),
        ("2026-10-26T18:00:00Z", "0h"),
        (None, ""),
    ],
)
def test_format_reset(iso, out):
    assert qd.format_reset(qd.parse_iso(iso), NOW) == out


def test_parse_iso_rejects_junk_and_assumes_utc():
    assert qd.parse_iso("nope") is None and qd.parse_iso(5) is None
    assert qd.parse_iso("2026-10-26T19:00:00").tzinfo is not None


def test_format_age():
    assert [qd.format_age(s) for s in (5, 600, 7300, 200000)] == [
        "1m",
        "10m",
        "2h",
        "2d",
    ]


# ── cells: poll health ──


def cells(rows, **kw):
    kw.setdefault("last_ok", NOW.timestamp())
    kw.setdefault("interval", 120)
    return qd.build_cells(rows, list(qd.LABELS), NOW.timestamp(), **kw)


def test_cells_healthy_show_value_reset_bar_and_flags():
    cc, oc, gpt, grk, agy = cells(qd.parse(fixture()))
    assert (cc.label, cc.value, cc.frac, cc.dim, cc.dot) == (
        "CC",
        "22%",
        0.22,
        False,
        True,
    )
    assert cc.sub == "5h0m"
    assert oc.exhausted and oc.value == "0%"
    assert (gpt.value, gpt.sub, gpt.frac, gpt.color) == ("—", "login", None, qd.GRAY)
    assert not grk.dim and not grk.exhausted


def test_cells_before_first_read_are_gray_waiting_then_err():
    waiting = cells(None, last_ok=0)
    assert all((c.value, c.sub, c.color) == ("—", "…", qd.GRAY) for c in waiting)
    errored = cells(None, last_ok=0, failed=True)
    assert all(c.sub == "err" for c in errored)


def test_failed_poll_keeps_last_rows_dim_with_bang():
    cc = cells(qd.parse(fixture()), failed=True)[0]
    assert cc.dim and cc.value == "22%" and cc.sub.startswith("! ")


def test_stale_after_three_intervals_says_stale_age():
    old = NOW.timestamp() - 7 * 60
    cc = cells(qd.parse(fixture()), last_ok=old)[0]
    assert cc.dim and cc.sub == "stale 7m"
    fresh = cells(qd.parse(fixture()), last_ok=NOW.timestamp() - 300)[0]
    assert not fresh.dim  # 300s is under the 3 x 120s = 360s limit


def test_provider_reported_stale_dims_that_cell_only():
    rows = qd.parse(fixture())
    rows[3].stale = True
    out = cells(rows)
    assert out[3].dim and out[3].sub.startswith("stale ")
    assert not out[0].dim


# ── runner ──


def test_argv_has_provider_list_max_age_and_no_full():
    argv = qr.quota_argv("quota-axi", ["claude", "grok"])
    assert argv == [
        "quota-axi",
        "--json",
        "--provider",
        "claude,grok",
        "--max-age",
        "60s",
    ]
    assert "--full" not in argv


class FakeProc:
    def __init__(self, text, code=0, done=True):
        self.text, self.returncode, self.done, self.killed = text, code, done, False
        self.out = None

    def poll(self):
        return self.returncode if self.done else None

    def kill(self):
        self.killed = True
        self.done = True


class FakePopen:
    def __init__(self, text="", code=0, done=True, boom=None):
        self.args = []
        self.proc = FakeProc(text, code, done)
        self.boom = boom

    def __call__(self, argv, stdout=None, **kw):
        if self.boom:
            raise self.boom
        self.args.append((argv, kw))
        stdout.write(self.proc.text)
        stdout.flush()
        return self.proc


def runner(popen, clock=None, tmp=None, timeout=25.0):
    return qr.QuotaRunner(
        tool="quota-axi",
        popen=popen,
        clock=clock or (lambda: 0.0),
        timeout=timeout,
        tmp_dir=tmp,
    )


def test_runner_success_returns_parsed_json_and_cleans_temp(tmp_path):
    popen = FakePopen(FIXTURE.read_text())
    r = runner(popen, tmp=str(tmp_path))
    assert r.start(["claude"]) is None and r.busy
    res = r.tick()
    assert res.error is None and len(res.data["providers"]) == 6
    assert not r.busy and list(tmp_path.iterdir()) == []


def test_runner_passes_extended_path_and_devnull_stdin(tmp_path):
    popen = FakePopen("{}")
    runner(popen, tmp=str(tmp_path)).start(["claude"])
    _, kw = popen.args[0]
    assert str(Path.home() / ".local" / "bin") in kw["env"]["PATH"]
    assert kw["stdin"] is not None


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"providers": 3}'])
def test_runner_bad_output_is_an_error_not_a_crash(text, tmp_path):
    r = runner(FakePopen(text, code=1), tmp=str(tmp_path))
    r.start(["claude"])
    res = r.tick()
    assert res.data is None and res.error


def test_runner_start_failure_returns_error_result(tmp_path):
    r = runner(FakePopen(boom=FileNotFoundError("quota-axi")), tmp=str(tmp_path))
    res = r.start(["claude"])
    assert "could not start" in res.error and not r.busy
    assert list(tmp_path.iterdir()) == []


def test_runner_kills_a_hung_run_after_timeout(tmp_path):
    t = {"now": 0.0}
    popen = FakePopen("", done=False)
    r = runner(popen, clock=lambda: t["now"], tmp=str(tmp_path), timeout=25.0)
    r.start(["claude"])
    assert r.tick() is None and r.busy
    t["now"] = 26.0
    res = r.tick()
    assert "timed out" in res.error and popen.proc.killed and not r.busy


def test_runner_never_starts_a_second_run_while_busy(tmp_path):
    popen = FakePopen("", done=False)
    r = runner(popen, tmp=str(tmp_path))
    r.start(["claude"])
    r.start(["claude"])
    assert len(popen.args) == 1


def test_runner_real_child_process_does_not_block_tick(tmp_path):
    script = tmp_path / "fake-quota"
    script.write_text(
        f"#!{sys.executable}\nimport time\ntime.sleep(0.3)\n"
        "print('{\"providers\": []}')\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    r = qr.QuotaRunner(tool=str(script), tmp_dir=str(tmp_path))
    r.start(["claude"])
    t0 = time.monotonic()
    assert r.tick() is None  # still sleeping; tick returned at once
    assert time.monotonic() - t0 < 0.2
    for _ in range(50):
        res = r.tick()
        if res:
            break
        time.sleep(0.1)
    assert res and res.error is None


# ── glue: no thread, settings, draw (stub canvas) ──


def test_panel_uses_cron_and_a_child_process_never_a_thread():
    for name in ("quota_panel.py", "quota_run.py", "quota_data.py"):
        src = (PKG / name).read_text()
        assert "threading" not in src and "Thread(" not in src
    assert "cron.interval" in (PKG / "quota_panel.py").read_text()


def test_mode_indicator_talon_flips_the_two_settings():
    talon = (ROOT / "trillium" / "mode_indicator" / "mode_indicator.talon").read_text()
    assert "user.mode_indicator_show_usage = false" in talon
    assert "user.quota_panel_show = true" in talon


def test_quota_refresh_phrase():
    talon = (PKG / "quota_panel.talon").read_text()
    assert "quota refresh: user.quota_panel_refresh()" in talon


@pytest.fixture
def panel(monkeypatch, talon_settings):
    from talon import ui

    from trillium.quota_panel import quota_panel as qp

    monkeypatch.setattr(qp, "_rows", None)
    monkeypatch.setattr(qp, "_last_ok", 0.0)
    monkeypatch.setattr(qp, "_failed", False)
    monkeypatch.setattr(qp, "_draw_frame", lambda *a, **k: None)
    monkeypatch.setattr(qp.ui, "main_screen", lambda: _Screen(), raising=False)
    return qp


class _Screen:
    class rect:
        left, top, width, height = 0, 0, 1728, 1117


def test_panel_sits_right_of_the_bar_with_the_bars_height(panel, talon_settings):
    talon_settings.set("user.mode_indicator_bar_right_x", 0.617)
    talon_settings.set("user.mode_indicator_bar_height", 35)
    rect = panel.panel_rect(_Screen.rect, 5)
    assert rect.x == pytest.approx(1728 * 0.617 + 2)
    assert rect.height == 35 and rect.width == 5 * 66 + 8


def test_panel_left_x_setting_overrides_and_panel_stays_on_screen(
    panel, talon_settings
):
    talon_settings.set("user.quota_panel_left_x", 0.5)
    assert panel.panel_rect(_Screen.rect, 5).x == pytest.approx(864)
    talon_settings.set("user.quota_panel_left_x", 0.95)
    r = panel.panel_rect(_Screen.rect, 5)
    assert r.x + r.width <= 1728


def test_draw_five_cells_with_labels_values_bars_and_dot(
    panel, mock_canvas, talon_settings
):
    talon_settings.set("user.mode_indicator_bar_height", 35)
    panel._rows = qd.parse(fixture(), qd.parse_providers(""))
    panel._last_ok = time.time()
    panel.on_draw(mock_canvas)
    texts = [t[3] for t in mock_canvas.texts()]
    assert [t for t in texts if t in ("CC", "OC", "GPT", "GRK", "AGY")] == [
        "CC",
        "OC",
        "GPT",
        "GRK",
        "AGY",
    ]
    assert "22%" in texts and "89%" in texts and "login" in texts
    assert len(mock_canvas.circles()) == 1  # CC's Fable-at-zero dot
    assert len(mock_canvas.rects()) == 9  # 4 gauged cells x 2 rects + OC's red tint


def test_draw_before_first_read_shows_five_gray_waiting_cells(panel, mock_canvas):
    panel.on_draw(mock_canvas)
    texts = [t[3] for t in mock_canvas.texts()]
    assert texts.count("—") == 5 and texts.count("…") == 5
    assert mock_canvas.circles() == []


def test_apply_result_updates_rows_and_failure_keeps_old_rows(panel):
    panel._apply(qr.Result(data=fixture()))
    assert panel._rows and panel._failed is False
    kept = panel._rows
    panel._apply(qr.Result(error="quota-axi timed out after 25s"))
    assert panel._failed is True and panel._rows is kept
