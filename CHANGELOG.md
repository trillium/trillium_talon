# Changelog

Notable changes to this repo. Newest first.

## Unreleased

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
