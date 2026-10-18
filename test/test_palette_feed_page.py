"""The phone page served at `GET /`: routing, wire shape, and a JS-level logic check.

No Talon and no browser: the page is verified as bytes over a real socket plus its own
script run under node (`test/palette_page_check.mjs`). What a real phone renders is not
covered here.
"""

import http.client
import io
import json
import os
import shutil
import subprocess

import pytest

# `FakeBackend` comes from the api tests: one fake backend for both files, rather than
# two that can drift. `backend` is re-declared here as a local fixture.
from test_palette_feed_api import AUTH, TOKEN, FakeBackend, post

from trillium.palette_feed import page, server
from trillium.palette_feed.api import Config, PaletteApi
from trillium.palette_feed.limits import RateLimiter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_FILE = os.path.join(REPO_ROOT, "trillium", "palette_feed", "page.html")
CHECK_JS = os.path.join(REPO_ROOT, "test", "palette_page_check.mjs")
DOM_CHECK_JS = os.path.join(REPO_ROOT, "test", "palette_page_dom_check.mjs")

# The hooks the page cannot work without: the search box, the result list, the state
# header, the theme switch, the refresh control, and the endpoints it talks to.
PAGE_HOOKS = [
    b'id="q"',
    b'id="results"',
    b'id="state"',
    b'id="refresh"',
    b"prefers-color-scheme",
    b'"/lists/"',
    b"executeRequest",
    b"docs/palette-feed.md",
]


def read_page_file() -> bytes:
    with open(PAGE_FILE, "rb") as handle:
        return handle.read()


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def open_api(backend):
    """Reads open, the way a tailnet host publishes itself for the phone."""
    return PaletteApi(
        TOKEN,
        backend,
        RateLimiter(100, 1.0),
        Config(max_body_bytes=1024, open_reads=True),
    )


@pytest.fixture
def private_api(backend):
    return PaletteApi(
        TOKEN, backend, RateLimiter(100, 1.0), Config(max_body_bytes=1024)
    )


@pytest.fixture
def live_open(backend):
    """A real socket with no token configured at all: enough to load the page."""
    api = PaletteApi(
        None,
        backend,
        RateLimiter(100, 1.0),
        Config(max_body_bytes=1024, open_reads=True),
    )
    srv, _ = server.start(api, "127.0.0.1", 0)
    yield srv.server_address[1]
    server.stop(srv)


def call(port, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), data


class TestPageFile:
    def test_the_page_is_served_verbatim_from_page_html(self):
        assert page.html_page() == read_page_file()

    def test_the_page_is_one_self_contained_document(self):
        html = read_page_file().decode("utf-8")
        assert html.startswith("<!doctype html>")
        assert 'name="viewport"' in html
        assert "width=device-width" in html
        assert "<script src=" not in html
        assert 'href="http' not in html  # no CDN, no remote icon
        assert "@import" not in html
        assert html.count("<script>") == 1

    def test_the_page_is_phone_first(self):
        html = read_page_file().decode("utf-8")
        assert "prefers-color-scheme: dark" in html  # dark and light
        assert ".tap" in html and "min-height: 64px" in html  # big tap targets

    @pytest.mark.parametrize("hook", PAGE_HOOKS)
    def test_the_page_carries_every_hook(self, hook):
        assert hook in read_page_file()

    def test_the_page_carries_no_secret(self):
        assert TOKEN.encode() not in read_page_file()

    @pytest.mark.parametrize(
        "absent",
        [b"Authorization", b"Bearer", b"paste", b'id="token"'],
    )
    def test_the_page_has_no_credential_handling(self, absent):
        """The tailnet is the boundary: the phone holds nothing to paste or store."""
        assert absent not in read_page_file()

    def test_local_storage_goes_through_one_read_and_one_write(self):
        html = read_page_file().decode("utf-8")
        assert html.count("localStorage") == 2  # storeGet and storeSet, nothing else
        assert 'INTRO_KEY = "palette_intro_dismissed"' in html
        assert 'RECENTS_KEY = "palette_recents"' in html
        assert 'FAVORITES_KEY = "palette_favorites"' in html

    def test_a_gated_host_is_told_which_setting_opens_it(self):
        assert "palette_feed_open_execute" in read_page_file().decode("utf-8")

    def test_a_missing_page_file_still_answers(self, monkeypatch):
        """A broken install serves an explanation, not a 500 the phone cannot read."""
        monkeypatch.setattr(page, "_cache", None)
        body = page.html_page("/nonexistent/page.html")
        assert body.startswith(b"<!doctype html")
        assert b"page.html is missing" in body

    def test_the_page_is_only_read_from_disk_once(self, monkeypatch, tmp_path):
        target = tmp_path / "page.html"
        target.write_bytes(b"<!doctype html><p>first")
        monkeypatch.setattr(page, "_cache", None)
        assert page.html_page(str(target)) == b"<!doctype html><p>first"
        target.write_bytes(b"<!doctype html><p>second")
        assert page.html_page(str(target)) == b"<!doctype html><p>first"


class TestPageRoute:
    def test_reads_open_serves_the_page_with_no_token(self, open_api):
        resp = open_api.handle("GET", "/", {})
        assert resp.status == 200
        assert resp.raw == read_page_file()
        assert resp.content_type == "text/html; charset=utf-8"
        assert resp.body is None

    def test_the_token_is_accepted_too(self, open_api):
        assert open_api.handle("GET", "/", AUTH).status == 200

    def test_a_query_string_still_serves_the_page(self, open_api):
        assert open_api.handle("GET", "/?ref=home", {}).status == 200

    def test_html_is_never_json_encoded(self, open_api):
        """The page goes out byte-for-byte; the page is not JSON and is not wrapped."""
        resp = open_api.handle("GET", "/", {})
        assert resp.raw == read_page_file()
        with pytest.raises(ValueError):
            json.loads(resp.raw.decode("utf-8"))

    @pytest.mark.parametrize(
        "method, path", [("POST", "/"), ("DELETE", "/"), ("GET", "/favicon.ico")]
    )
    def test_open_reads_publishes_nothing_else(self, open_api, method, path):
        assert open_api.handle(method, path, {}, io.BytesIO(b"{}")).status == 401

    def test_reads_private_needs_the_token(self, private_api):
        resp = private_api.handle("GET", "/", {})
        assert resp.status == 401
        assert resp.headers["WWW-Authenticate"] == "Bearer"
        assert private_api.handle("GET", "/", AUTH).status == 200


class TestPageOverTheWire:
    def test_the_page_loads_with_no_token_configured_at_all(self, live_open):
        status, headers, data = call(live_open, "GET", "/")
        assert status == 200
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert headers["Cache-Control"] == "no-store"  # never a stale page on a phone
        assert headers["Content-Length"] == str(len(data))
        assert data == read_page_file()

    def test_the_page_then_reads_state_and_commands_with_no_token(self, live_open):
        assert call(live_open, "GET", "/state")[0] == 200
        assert call(live_open, "GET", "/commands")[0] == 200

    def test_the_page_does_not_arm_execute(self, live_open):
        """Loading the page must not open the one write path."""
        body = json.dumps({"phrase": "playback now"}).encode()
        assert call(live_open, "POST", "/execute", body=body)[0] == 401


class TestExecuteIsUnchanged:
    def test_execute_still_needs_the_token_while_the_page_is_open(
        self, open_api, backend
    ):
        resp = post(open_api, {"phrase": "playback now"}, headers={})
        assert resp.status == 401
        assert backend.executed == []

    def test_execute_with_the_token_still_runs(self, open_api, backend):
        assert post(open_api, {"phrase": "playback now"}).status == 200
        assert backend.executed == ["playback now"]

    def test_the_page_and_the_reads_do_not_spend_the_token(self, open_api, backend):
        """A page load plus a search must not leave a 401 or touch the backend."""
        assert open_api.handle("GET", "/", {}).status == 200
        assert open_api.handle("GET", "/commands", {}).status == 200
        assert backend.executed == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
class TestPageLogicUnderNode:
    def test_the_pages_own_script_passes_its_checks(self):
        result = subprocess.run(
            ["node", CHECK_JS, PAGE_FILE],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "page checks passed" in result.stdout

    def test_the_pages_wiring_passes_its_dom_checks(self):
        """jsdom is not a repo dependency, so this skips where it is not installed."""
        result = subprocess.run(
            ["node", DOM_CHECK_JS, PAGE_FILE],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout.startswith("skip:"):
            pytest.skip(result.stdout.strip())
        assert result.returncode == 0, result.stdout + result.stderr
        assert "DOM checks passed" in result.stdout
