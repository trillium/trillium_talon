"""`start_server` with the stub Talon registry, over a real socket and no Talon process.

The bind/auth switches meet the token file here, and this is the only place the feed's
start/disable decision is exercised end to end: `/state` answers with no token while reads
are open, `/execute` never does, and a missing token is fatal only when reads are
authenticated. Port 0 keeps every listener ephemeral.
"""

import http.client
import json
import sys

import pytest

from trillium.palette_feed import palette_feed

HOLDER = sys.modules["_trillium_palette_feed"]


def call(port, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), data


@pytest.fixture
def feed(tmp_path, monkeypatch):
    """Point the feed at a throwaway token path and port, and stop it afterwards.

    Each test calls `start_server` itself, so what it prints is that test's alone.
    """
    monkeypatch.setattr(palette_feed, "TOKEN_PATH", str(tmp_path / "absent-token"))
    monkeypatch.setattr(palette_feed, "PORT", 0)
    monkeypatch.delenv("TALON_PALETTE_BIND", raising=False)
    monkeypatch.delenv("TALON_PALETTE_OPEN_READS", raising=False)
    try:
        yield
    finally:
        if HOLDER.server is not None:
            palette_feed.server.stop(HOLDER.server)
            HOLDER.server = None


def port_of(server):
    return server.server_address[1]


def test_reads_are_open_and_execute_is_not_when_there_is_no_token(feed, monkeypatch):
    monkeypatch.setenv("TALON_PALETTE_OPEN_READS", "1")
    monkeypatch.setenv("TALON_PALETTE_BIND", "127.0.0.1")
    palette_feed.start_server()
    assert HOLDER.server is not None

    status, _, data = call(port_of(HOLDER.server), "GET", "/state")
    assert status == 200 and json.loads(data)["host"]

    status, _, data = call(port_of(HOLDER.server), "GET", "/commands")
    assert status == 200 and "commands_rev" in json.loads(data)

    body = json.dumps({"phrase": "playback now"}).encode()
    status, headers, data = call(port_of(HOLDER.server), "POST", "/execute", {}, body)
    assert status == 401 and headers["WWW-Authenticate"] == "Bearer"
    assert json.loads(data)["error"] == "unauthorized"


def test_a_missing_token_stops_a_private_read_feed(feed, capsys):
    palette_feed.start_server()
    assert HOLDER.server is None
    assert "not starting" in capsys.readouterr().out


def test_the_log_reports_the_bind_reads_and_execute_shape(feed, monkeypatch, capsys):
    monkeypatch.setenv("TALON_PALETTE_OPEN_READS", "1")
    monkeypatch.setenv("TALON_PALETTE_BIND", "0.0.0.0")
    palette_feed.start_server()
    out = capsys.readouterr().out
    assert HOLDER.server is not None
    assert HOLDER.server.server_address[0] == "0.0.0.0"
    assert "listening on 0.0.0.0:0 (tailnet/network, reads open" in out
    assert "/execute disabled" in out
    assert call(port_of(HOLDER.server), "GET", "/state")[0] == 200  # over loopback


def test_defaults_still_bind_loopback_and_require_the_token(feed, monkeypatch, capsys):
    monkeypatch.setenv("TALON_PALETTE_OPEN_READS", "0")
    palette_feed.start_server()
    assert HOLDER.server is None
    assert "not starting" in capsys.readouterr().out


def test_a_token_inside_the_repo_refuses_to_start_even_with_open_reads(
    feed, monkeypatch, capsys
):
    monkeypatch.setenv("TALON_PALETTE_OPEN_READS", "1")
    monkeypatch.setattr(palette_feed, "TOKEN_PATH", __file__)
    palette_feed.start_server()
    assert HOLDER.server is None
    assert "inside the repo" in capsys.readouterr().out


def test_an_unreadable_switch_value_is_reported_not_guessed(feed, monkeypatch, capsys):
    monkeypatch.setenv("TALON_PALETTE_OPEN_READS", "maybe")
    palette_feed.start_server()
    out = capsys.readouterr().out
    assert "TALON_PALETTE_OPEN_READS" in out and "not a yes/no value" in out
    assert HOLDER.server is None  # fell back to the private-reads default
