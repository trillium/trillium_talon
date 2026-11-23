"""Linux-only overrides must leave macOS behaviour alone.

The stub talon runtime reports platform "mac"; tests flip it per case.
"""

import importlib.util
from pathlib import Path

import pytest
from talon import app

ROOT = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def platform(monkeypatch):
    def set_platform(value):
        monkeypatch.setattr(app, "platform", value, raising=False)

    return set_platform


@pytest.fixture
def state():
    return _load(
        "mi_state_linux_test", "trillium/plugin/mode_indicator/mode_indicator_state.py"
    )


def test_sysmon_path_unchanged_on_mac_even_with_env(state, platform, monkeypatch):
    platform("mac")
    monkeypatch.setenv("MONITOR_DATA_DIR", "/elsewhere")
    assert state._sysmon_stats_path() == state.SYSMON_STATS


def test_sysmon_path_linux_env_override_wins(state, platform, monkeypatch):
    platform("linux")
    monkeypatch.setenv("MONITOR_DATA_DIR", "/elsewhere")
    assert state._sysmon_stats_path() == Path("/elsewhere/stats.json")


def test_sysmon_path_linux_uses_xdg_data_home(state, platform, monkeypatch):
    platform("linux")
    monkeypatch.delenv("MONITOR_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/xdg")
    assert state._sysmon_stats_path() == Path("/xdg/system-monitor/stats.json")


def test_sysmon_path_linux_default_is_local_share(state, platform, monkeypatch):
    platform("linux")
    monkeypatch.delenv("MONITOR_DATA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert (
        state._sysmon_stats_path()
        == Path.home() / ".local/share/system-monitor/stats.json"
    )


@pytest.fixture
def prefix():
    return _load(
        "herdr_prefix_linux_test", "trillium/plugin/herder/herdr_prefix_linux.py"
    )


def test_prefix_read_from_config(prefix, tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[keys]\nprefix = "ctrl+space"\n')
    monkeypatch.setattr(prefix, "CONFIG", cfg)
    assert prefix.herdr_prefix_key() == "ctrl-space"


@pytest.mark.parametrize("body", [None, "not = [valid", "[keys]\nother = 1\n"])
def test_prefix_falls_back_to_ctrl_b_loudly(
    prefix, tmp_path, monkeypatch, capsys, body
):
    cfg = tmp_path / "config.toml"
    if body is not None:
        cfg.write_text(body)
    monkeypatch.setattr(prefix, "CONFIG", cfg)
    assert prefix.herdr_prefix_key() == "ctrl-b"
    assert "FALLBACK" in capsys.readouterr().out


def test_hyprland_bridge_does_not_poll_off_linux(monkeypatch):
    import talon

    calls = []
    monkeypatch.setattr(
        talon.cron, "interval", lambda *a, **k: calls.append(a), raising=False
    )
    _load("hypr_bridge_test", "linux/hyprland_bridge/hyprland_bridge.py")
    assert calls == []  # stub platform is "mac"


def test_hyprland_spoken_forms():
    bridge = _load("hypr_bridge_forms_test", "linux/hyprland_bridge/hyprland_bridge.py")
    assert {"chrome", "google chrome"} <= bridge._spoken_forms("google-chrome")
    assert "wezterm" in bridge._spoken_forms("org.wezfurlong.wezterm")
