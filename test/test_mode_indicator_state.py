"""mode_indicator_state: pollers run off the cron thread, state lives outside ~/.talon.

The module is loaded by file path with STATE_FILE pointed at tmp_path; no Talon process
and no OBS. The worker is driven with a synchronous `post` so results land deterministically.
"""

import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest
import talon

SRC = (
    Path(__file__).parent.parent
    / "trillium"
    / "plugin"
    / "mode_indicator"
    / "mode_indicator_state.py"
)


@pytest.fixture
def mis(tmp_path, monkeypatch):
    monkeypatch.setenv("TALON_MODE_INDICATOR_STATE", str(tmp_path / "state" / "s.json"))
    spec = importlib.util.spec_from_file_location("_mis_under_test", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SYSMON_STATS = tmp_path / "stats.json"
    yield mod
    mod._stop.set()


def test_state_file_is_outside_watched_tree(mis):
    assert SRC.parent not in mis.STATE_FILE.parents


def test_default_state_file_not_under_talon_dir(monkeypatch):
    monkeypatch.delenv("TALON_MODE_INDICATOR_STATE", raising=False)
    spec = importlib.util.spec_from_file_location("_mis_default", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert Path.home() / ".talon" not in mod.STATE_FILE.parents
    assert (
        mod.STATE_FILE == Path.home() / ".cache" / "talon" / "mode_indicator_state.json"
    )


def test_update_notifies_listener_and_writes_file(mis):
    seen = []
    mis.add_listener(seen.append)
    mis.update(mode="command")
    assert seen[-1]["mode"] == "command"
    assert json.loads(mis.STATE_FILE.read_text())["mode"] == "command"
    n = len(seen)
    mis.update(mode="command")  # unchanged: no flush, no notify
    assert len(seen) == n


def test_flush_preserves_external_keys(mis):
    mis.STATE_FILE.parent.mkdir(parents=True)
    mis.STATE_FILE.write_text(json.dumps({"static_percent": "42%"}))
    mis.update(mode="dictation")
    assert json.loads(mis.STATE_FILE.read_text())["static_percent"] == "42%"


def test_external_keys_reach_listeners(mis):
    seen = []
    mis.add_listener(seen.append)
    mis.STATE_FILE.parent.mkdir(parents=True)
    mis.STATE_FILE.write_text(json.dumps({"static_percent": "7%", "mode": "bogus"}))
    ext = mis._fetch_external()
    assert ext == {"static_percent": "7%"}  # own keys never taken from disk
    mis._apply_external(ext)
    assert seen[-1]["static_percent"] == "7%"
    assert mis._fetch_external() is None  # unchanged mtime


def test_obs_python_uses_setting_then_path_then_sys(mis, monkeypatch):
    talon.settings._values["user.mode_indicator_obs_python"] = "/opt/py"
    assert mis._obs_python() == "/opt/py"
    talon.settings._values["user.mode_indicator_obs_python"] = ""
    monkeypatch.setattr(mis.shutil, "which", lambda n: "/usr/bin/python3")
    assert mis._obs_python() == "/usr/bin/python3"
    monkeypatch.setattr(mis.shutil, "which", lambda n: None)
    assert mis._obs_python() == sys.executable
    talon.settings._values.pop("user.mode_indicator_obs_python", None)


def test_no_hardcoded_pyenv_path():
    assert "pyenv" not in SRC.read_text()


def test_fetch_obs_runs_given_python_and_parses(mis, monkeypatch):
    calls = []

    class R:
        returncode = 0
        stdout = json.dumps({"streaming": True, "recording": False, "scene": "Main"})

    monkeypatch.setattr(
        mis.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or R()
    )
    out = mis._fetch_obs_status("/x/python")
    assert calls[0][0] == "/x/python"
    assert out == {"obs_streaming": True, "obs_recording": False, "obs_scene": "Main"}


def test_fetch_obs_failure_reports_off(mis, monkeypatch):
    def boom(*a, **k):
        raise OSError("no python")

    monkeypatch.setattr(mis.subprocess, "run", boom)
    assert mis._fetch_obs_status("/nope") == {
        "obs_streaming": False,
        "obs_recording": False,
        "obs_scene": "",
    }


def test_fetch_sysmon(mis):
    mis.SYSMON_STATS.write_text(
        json.dumps(
            {"cpu": {"per_core": [1, 2]}, "memory": {"percent": 50, "pressure": 1}}
        )
    )
    assert mis._fetch_sysmon() == {
        "cpu_per_core": [1, 2],
        "mem_percent": 50,
        "mem_pressure": 1,
    }
    mis.SYSMON_STATS.unlink()
    assert mis._fetch_sysmon() == {}


def test_worker_blocking_work_stays_off_calling_thread(mis, monkeypatch):
    main = threading.get_ident()
    fetch_threads = []
    posted = []
    done = threading.Event()

    def slow_obs(python):
        fetch_threads.append(threading.get_ident())
        return {"obs_scene": "S"}

    monkeypatch.setattr(mis, "_fetch_obs_status", slow_obs)
    monkeypatch.setattr(mis, "_obs_python", lambda: "py")

    def post(fn):
        posted.append(fn)
        done.set()
        mis._stop.set()

    t = threading.Thread(target=mis._worker_loop, args=(post,), daemon=True)
    t.start()
    assert done.wait(5)
    t.join(5)
    assert fetch_threads and fetch_threads[0] != main
    # nothing applied until the posted callback runs on the "main" thread
    assert mis._state["obs_scene"] == ""
    posted[0]()
    assert mis._state["obs_scene"] == "S"


def test_start_worker_is_idempotent_daemon(mis):
    mis.start_worker()
    first = mis._worker
    mis.start_worker()
    assert mis._worker is first and first.daemon
    mis._stop.set()
    first.join(5)


def test_on_ready_registers_no_slow_cron_pollers(mis, monkeypatch):
    jobs = []
    monkeypatch.setattr(mis.cron, "interval", lambda p, cb: jobs.append(cb))
    monkeypatch.setattr(mis, "start_worker", lambda: None)
    talon.settings._values.update(
        {"user.week_reset_day": 3, "user.week_reset_hour": 12}
    )
    mis.on_ready()
    names = {getattr(cb, "__name__", "") for cb in jobs}
    assert "_poll_obs_status" not in names and "_poll_sysmon" not in names
