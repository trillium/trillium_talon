"""The phone page served at `GET /`: one static HTML file, read once. No Talon.

The page is self-contained (no CDN, no build step), so a phone on the tailnet loads it
with no token and searches `/commands` client-side. Runs are still `POST /execute`,
which is bearer-token gated; the token never appears in the page or in a URL.
"""

import os

PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page.html")
CONTENT_TYPE = "text/html; charset=utf-8"

# Served only if page.html is missing from the install. A page that says what is wrong
# beats a 500 the phone cannot read; it is never the normal path.
_MISSING = b"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Palette</title>
</head><body style="font:17px/1.4 system-ui;padding:20px">
<h1 style="font-size:20px">palette page.html is missing</h1>
<p>The palette feed is running but its page file was not found next to
<code>trillium/palette_feed/page.py</code>.</p>
<p>On the Mac, reinstall or re-check that checkout, then reload the feed
(touch <code>trillium/palette_feed/palette_feed.py</code>) or restart Talon.</p>
</body></html>
"""

_cache: bytes | None = None


def _read(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return _MISSING


def html_page(path: str = PAGE_PATH) -> bytes:
    """The page bytes, read from disk once and then held."""
    global _cache
    if _cache is None:
        _cache = _read(path)
    return _cache
