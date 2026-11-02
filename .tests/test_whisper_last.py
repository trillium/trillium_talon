"""whisper last: newest of Whisper/Handy wins; missing Handy db falls back.

Sources are injected fakes; the Handy db test uses a throwaway sqlite file.
No dictated text from real databases is read."""

import importlib.util
import sqlite3
import sys
import types
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "trillium" / "plugin" / "whisper_last"


def _load(name):
    full = f"wl_pkg.{name}"
    if "wl_pkg" not in sys.modules:
        pkg = types.ModuleType("wl_pkg")
        pkg.__path__ = [str(PKG)]
        sys.modules["wl_pkg"] = pkg
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


handy_data = _load("handy_data")
whisper_data = _load("whisper_data")
ld = _load("last_dictation")


def test_handy_newer_wins():
    assert ld.latest_dictation(lambda: (100.0, "w"), lambda: (200.0, "h")) == "h"


def test_whisper_newer_wins():
    assert ld.latest_dictation(lambda: (300.0, "w"), lambda: (200.0, "h")) == "w"


def test_tie_prefers_whisper():
    assert ld.latest_dictation(lambda: (5.0, "w"), lambda: (5.0, "h")) == "w"


def test_handy_nothing_falls_back_to_whisper():
    assert ld.latest_dictation(lambda: (1.0, "w"), lambda: None) == "w"


def test_whisper_nothing_uses_handy():
    assert ld.latest_dictation(lambda: None, lambda: (1.0, "h")) == "h"


def test_both_empty():
    assert ld.latest_dictation(lambda: None, lambda: None) is None


def test_missing_handy_db(tmp_path):
    assert handy_data.get_latest(tmp_path / "nope.db") is None


def test_handy_db_newest_nonempty(tmp_path):
    db = tmp_path / "history.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE transcription_history (id INTEGER PRIMARY KEY, file_name TEXT, "
        "timestamp INTEGER, saved BOOLEAN, title TEXT, transcription_text TEXT)"
    )
    conn.executemany(
        "INSERT INTO transcription_history (file_name,timestamp,saved,title,transcription_text)"
        " VALUES ('f',?,0,'t',?)",
        [(10, "old"), (20, "new"), (30, "")],
    )
    conn.commit()
    conn.close()
    assert handy_data.get_latest(db) == (20.0, "new")


def test_corrupt_handy_db_is_none(tmp_path):
    db = tmp_path / "history.db"
    db.write_text("not sqlite")
    assert handy_data.get_latest(db) is None


def test_whisper_timestamp_parse():
    assert ld._whisper_timestamp_to_unix("1970-01-01 00:01:00.500") == 60.5
    assert ld._whisper_timestamp_to_unix("garbage") is None
