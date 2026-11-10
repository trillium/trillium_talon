"""Tests for Phase 2 (recall_session_state) and Phase 3 (recall_pill_colors)."""

import json

import pytest

from plugin.recall import recall_pill_colors as rpc
from plugin.recall import recall_session_state as rss

# ── Phase 3: pill colors ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "status,hex_",
    [
        (rpc.STATUS_IDLE, "22aa44"),
        (rpc.STATUS_ACTIVE, "4488ff"),
        (rpc.STATUS_CHURNING, "ff4444"),
        (rpc.STATUS_UNKNOWN, "666666"),
    ],
)
def test_status_to_color_known(status, hex_):
    assert rpc.status_to_color(status) == hex_


def test_status_to_color_unknown_defaults_to_unknown():
    assert rpc.status_to_color("not-a-status") == rpc.COLOR_MAP[rpc.STATUS_UNKNOWN]


@pytest.mark.parametrize(
    "a,m,expected",
    [
        (0, 0, ""),
        (2, 0, "2A"),
        (0, 1, "1M"),
        (2, 1, "2A 1M"),
    ],
)
def test_format_badge(a, m, expected):
    assert rpc.format_badge(a, m) == expected


def test_derive_status_churning_when_two_agents():
    assert rpc.derive_status(2, 0, "active") == rpc.STATUS_CHURNING


def test_derive_status_passes_through_valid_base():
    assert rpc.derive_status(1, 0, "idle") == rpc.STATUS_IDLE


def test_derive_status_unknown_for_invalid_base():
    assert rpc.derive_status(0, 0, "bogus") == rpc.STATUS_UNKNOWN


# ── Phase 2: session state ────────────────────────────────────────────


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """Redirect _STATE_FILE to tmp_path and reset cache between tests."""
    f = tmp_path / "session-pills.jsonl"
    monkeypatch.setattr(rss, "_STATE_FILE", f)
    monkeypatch.setattr(rss, "_cache", {})
    monkeypatch.setattr(rss, "_cache_time", 0.0)
    return f


def test_missing_file_returns_none_and_empty(state_file):
    assert rss.get_session_status("anything") is None
    assert rss.get_all_session_states() == {}


def test_empty_file_returns_none_and_empty(state_file):
    state_file.write_text("")
    assert rss.get_session_status("anything") is None
    assert rss.get_all_session_states() == {}


def test_single_valid_event(state_file):
    evt = {"session_id": "abc", "status": "active", "agent_count": 1}
    state_file.write_text(json.dumps(evt) + "\n")
    assert rss.get_session_status("abc") == evt
    assert rss.get_all_session_states() == {"abc": evt}


def test_latest_event_wins_for_same_session(state_file):
    e1 = {"session_id": "abc", "status": "idle"}
    e2 = {"session_id": "abc", "status": "active"}
    state_file.write_text(json.dumps(e1) + "\n" + json.dumps(e2) + "\n")
    assert rss.get_session_status("abc") == e2


def test_malformed_json_lines_skipped(state_file):
    good = {"session_id": "ok", "status": "idle"}
    state_file.write_text("not json\n" + json.dumps(good) + "\n{bad\n")
    assert rss.get_session_status("ok") == good
    assert rss.get_session_status("nope") is None


def test_unknown_session_id_returns_none(state_file):
    state_file.write_text(json.dumps({"session_id": "a", "status": "idle"}) + "\n")
    assert rss.get_session_status("missing") is None


def test_ttl_cache_serves_stale_within_window(state_file, monkeypatch):
    state_file.write_text(json.dumps({"session_id": "a", "status": "idle"}) + "\n")
    now = [1000.0]
    monkeypatch.setattr(rss.time, "monotonic", lambda: now[0])
    assert rss.get_session_status("a") == {"session_id": "a", "status": "idle"}
    # Mutate file but advance clock < TTL — cache should serve stale
    state_file.write_text(json.dumps({"session_id": "a", "status": "active"}) + "\n")
    now[0] += rss._TTL_SECONDS / 10  # well inside the TTL
    assert rss.get_session_status("a") == {"session_id": "a", "status": "idle"}
    # Advance past TTL — cache refreshes
    now[0] += rss._TTL_SECONDS
    assert rss.get_session_status("a") == {"session_id": "a", "status": "active"}
