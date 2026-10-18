# Changelog

Notable changes to this repo. Newest first.

## Unreleased

### Added — phone page: Recent, Favorites and a setup doc

- `trillium/palette_feed/page.html`: the last 10 successful runs show as a tappable
  **Recent** list (newest first, de-duplicated), and a star on each command row adds it
  to **Favorites** above the results. Both persist in `localStorage`
  (`palette_recents`, `palette_favorites`); every storage access is guarded and corrupt
  JSON is discarded, so the page works fully with storage unavailable.
- Docs: new `docs/palette-setup.md` (adding a device); `docs/palette-feed.md` links it.
- Tests: page checks under node and jsdom cover recents cap/order/dedup, favorite toggle
  and reload persistence, corrupt storage and throwing storage. Also fixed a jsdom check
  that read a stale success toast as a failure.

### Fixed — `POST /execute` no longer answers 200 when nothing can run

- `trillium/palette_feed`: when Talon has no speech engine attached
  (`scope.get("speech.engine")` is `None`, as on mini0) `actions.mimic` is a silent
  no-op, so a tap returned `200` and did nothing. `POST /execute` now answers
  `503 {"ok": false, "error": "engine_inactive", "hint": "..."}` before dispatching.
  Auth and validation (401/400/403/423/422/404/409) still win over it; `?dry_run=1` and
  all read endpoints are unchanged and work with no engine.
- The phone page shows the `hint` for `engine_inactive` instead of a success toast, and
  gains a small dismissible first-run block (what the page is, one search tip); the
  dismissal is the only thing it stores in `localStorage`.
- Docs: `docs/palette-feed.md` → "`POST /execute`" and "Phone page". Tests:
  `test/test_palette_feed_api.py` (`TestEngineInactive`), page checks under node and jsdom.

### Added — a phone page at `GET /`

- `trillium/palette_feed`: the feed now serves a phone-first fuzzy-search page at
  `GET /` — one static HTML file (`page.html`, served by `page.py`), no build step, no
  CDN. It needs no token to load, and follows `open_reads` like the other reads.
- The page searches `/commands` client-side (contiguous hits beat subsequences), shows
  app/mode/window from `/state` polled every 5s, and runs a tapped command with
  `POST /execute`. Literal rules fire immediately; rules with `(a | b)`, `{list}` or
  `<capture>` slots open a small form (list slots get `/lists/<name>` suggestions) plus
  an **Edit phrase** escape hatch.
- The page holds no credential at all: no token field, no `localStorage`, no
  `Authorization` header. Publishing the feed is the whole authorization story.
- Every failure (401 when the host has not opened `/execute`, 423 not-in-command-mode with
  a **Run anyway** `?force=1` retry, 429, 403 denylist, 404/409 stale rule, 422, 504, 5xx,
  unreachable host) renders a fix-guide with the exact next step instead of a bare status
  or raw JSON.
- Tests: `test/test_palette_feed_page.py` (routing and bytes over a real socket) and
  `test/palette_page_check.mjs` / `test/palette_page_dom_check.mjs` (the page's own script
  under node, and its DOM wiring under jsdom). Docs: `docs/palette-feed.md` → "Phone page".

### Added — `open_execute`, so a tailnet host can run commands without a token

- `TALON_PALETTE_OPEN_EXECUTE` / `user.palette_feed_open_execute`, default `false`. While it
  is on, `POST /execute` accepts requests with no `Authorization` header and still accepts a
  valid token; every other gate is unchanged (denylist, command mode, rate limit, body
  limits). Reads are unaffected — it is its own axis.
- **While it is on, any device that can reach the bind can run Talon commands.** The
  security model is then the bind address and the tailnet, which `docs/palette-feed.md`
  now states plainly, along with the new full bind × open_reads × open_execute matrix. The
  startup log adds a `WARNING /execute is open` line naming the exposed address.
- A missing token is no longer fatal when nothing is left gated, and `/execute` is no
  longer "disabled" merely because no token file exists.

### Fixed — the feed's Talon settings were inert (task-ncz8l)

- `palette_feed.py` now declares `palette_feed_bind`, `palette_feed_open_reads` and
  `palette_feed_open_execute` with `Module.setting`. Talon only accepts a `.talon`
  `settings():` assignment for a declared setting; without the declaration it logged
  "settings skipped because they have no matching declaration" and dropped the value, so
  `trillium/settings.talon`'s `user.palette_feed_bind` / `user.palette_feed_open_reads`
  changed nothing and the feed stayed on loopback. Regression test:
  `test/test_palette_feed_settings.py`, which imports the module with `Module.setting`
  recorded and fails if a declaration and the name `options.resolve` reads drift apart.

### Changed — the palette feed can serve the tailnet

- `trillium/palette_feed`: the bind address and the read-auth requirement are now
  configurable per host — `TALON_PALETTE_BIND` / `user.palette_feed_bind` and
  `TALON_PALETTE_OPEN_READS` / `user.palette_feed_open_reads`. The defaults are unchanged
  (`127.0.0.1`, reads authenticated), so nothing is published until a host asks.
- With reads open, `GET /state`, `GET /commands` and `GET /lists/<name>` answer without a
  bearer token. `POST /execute` always requires one.
- The feed now starts without a token file when reads are open; `/execute` then answers
  `401` instead of running. A token file inside the repo still refuses to start.
- `0.0.0.0` or the tailnet address removes the need for `tailscale serve` on port 7399.
  Docs and the bind/auth matrix: `docs/palette-feed.md`.
