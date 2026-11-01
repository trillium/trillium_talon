"""parrot_clips_talon must not read settings at import and must survive them raising."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent / "trillium/plugin/parrot"


@pytest.fixture
def pct(monkeypatch):
    import talon

    pkg = types.ModuleType("pc_pkg")
    pkg.__path__ = [str(_DIR)]
    monkeypatch.setitem(sys.modules, "pc_pkg", pkg)
    for name in ("pc_pkg.parrot_clips", "pc_pkg.parrot_clips_talon"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    mod = importlib.import_module("pc_pkg.parrot_clips_talon")
    mod._configured[0] = False
    mod._hooked[0] = False
    mod._retries[0] = 0
    mod.service.configure(enabled=False, root="/nonexistent")
    registered = []
    monkeypatch.setattr(talon.app, "register", staticmethod(lambda e, cb: registered.append((e, cb))))
    mod.registered = registered
    yield mod
    mod.service.configure(enabled=False, root="/nonexistent")


class Settings:
    def __init__(self):
        self.ready = False
        self.reads = 0
        self.watchers = []

    def get(self, name):
        self.reads += 1
        if not self.ready:
            raise KeyError(name)
        return {"user.parrot_clips_dir": "/tmp/pc-test", "user.parrot_clips_power_floor": 33.0}.get(name)

    def register(self, name, cb):
        if not self.ready:
            raise KeyError(name)
        self.watchers.append((name, cb))


def test_start_reads_no_settings_at_import_time(pct, monkeypatch):
    st = Settings()
    monkeypatch.setattr(pct, "settings", st)
    pct.start(16000)
    assert st.reads == 0
    assert [e for e, _ in pct.registered] == ["ready"]
    assert not pct.service.enabled


def test_settings_raising_then_succeeding(pct, monkeypatch):
    st = Settings()
    monkeypatch.setattr(pct, "settings", st)
    pct.start(16000)
    pct.apply_settings()  # KeyError on every read: falls back to defaults, no raise
    assert pct.service.enabled and pct.service.power_floor == 20.0
    assert pct._configured[0] is False  # remembers it has not seen real settings
    st.ready = True
    pct.registered[0][1]()  # app 'ready'
    assert pct._configured[0] is True and pct._hooked[0] is True
    assert pct.service.power_floor == 33.0
    assert st.watchers[0][0] == "user.parrot_clips_enabled"


def test_action_configures_lazily(pct, monkeypatch):
    st = Settings()
    st.ready = True
    monkeypatch.setattr(pct, "settings", st)
    pct._sample_rate[0] = 16000
    pct.ensure_configured()
    assert pct.service.enabled and pct.service.power_floor == 33.0
    reads = st.reads
    pct.ensure_configured()  # already configured: no further reads
    assert st.reads == reads


def test_register_failure_never_raises(pct, monkeypatch):
    import talon

    monkeypatch.setattr(talon.app, "register", staticmethod(lambda e, cb: 1 / 0))
    pct.start(16000)  # logged, not raised
