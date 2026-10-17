# Palette feed

A small HTTP server inside Talon that lets a phone (the palette app) read the
active command set and run a command. Code: `trillium/palette_feed/`.
Design and evidence: the scope report for task-jyg9w (project-7u7w).

It listens on `127.0.0.1:7399` only. Reach it from the phone through
`tailscale serve` (tailnet-only HTTPS) plus a bearer token.

## Set up the token

The token lives outside every git repo, mode `0600`. Without it the server
does not start (it prints why to the Talon log).

```sh
mkdir -p -m 700 ~/.config/talon-palette
(umask 077; python3 -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.config/talon-palette/token)
chmod 600 ~/.config/talon-palette/token
```

- Override the path with `TALON_PALETTE_TOKEN_FILE`.
- The server refuses a token file that is group/world readable, shorter than
  32 characters, or inside the repo it was loaded from.
- Rotate by writing a new token, then reloading the module (touch
  `trillium/palette_feed/palette_feed.py`) or restarting Talon.
- Put the same token in the phone's Keychain. One token per host.

## Publish over the tailnet

Run on each host, once. Do not use `funnel`: this machine has Funnel enabled
for other ports, and this port must never be public.

```sh
tailscale serve --bg --https=7399 http://127.0.0.1:7399
tailscale serve status        # confirm 7399 is listed under the tailnet URL
tailscale funnel status       # confirm 7399 is NOT listed
```

The phone then uses `https://<host>.<tailnet>.ts.net:7399`.
Remove it with `tailscale serve --https=7399 off`.

## Endpoints

All requests need `Authorization: Bearer <token>`. Anything else gets
`401 {"ok":false,"error":"unauthorized"}` before routing, so unauthenticated
callers cannot tell which routes exist.

```sh
TOKEN=$(cat ~/.config/talon-palette/token)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:7399/state
```

| Method and path | What it returns |
|---|---|
| `GET /state` | `host`, `ts`, `rev`, `app{name,bundle}`, `window{title,filename,file_ext}`, `modes`, `tags`, `language`, `commands_rev` |
| `GET /commands` | `commands_rev`, `count`, `commands[]`. `ETag` is the `commands_rev`. `?rev=<commands_rev>` or `If-None-Match` gives `304`. `?q=text` filters rules by substring. |
| `GET /lists/<name>` | `{name, entries[]}` for a list used by an active rule (404 for any other name) |
| `POST /execute` | Runs `{"phrase": "...", "id": "<command id>"}`. `id` is optional. |

Each entry in `commands`:

```json
{"id": "cb2eab42dd", "rule": "(abbreviate | brief) {user.abbreviation}", "kind": "list",
 "slots": [{"name": "user.abbreviation", "type": "list", "n": 826}],
 "context": "user.trillium_talon.core.text.text.talon", "lineno": 30, "shadowed": 0}
```

- `kind` is `literal`, `list` (has `{list}` slots), or `capture` (has `<capture>` slots).
- A capture slot has `open: true` when it takes free text or a number (`<phrase>`,
  `<user.text>`, `<user.prose>`, `<user.raw_prose>`, `<number>`, `<number_small>`).
  The app composes the concrete phrase from the rule template.
- Only the winning definition of a rule is listed. Winner = highest
  `ctx._active_scores`, first registered on a tie. `shadowed` counts the losers.
- `context` is the Talon context path, dotted as Talon reports it.

### `POST /execute`

Order of checks (the first failure wins, and nothing runs unless all pass):

1. `401` bad or missing token.
2. `429` more than 5 calls per second (`Retry-After` header). Counted per server, not per caller.
3. `411` no `Content-Length` (chunked is refused), `400` bad length, `413` body over 4096 bytes.
4. `400` body is not a JSON object with a printable `phrase` of 1-200 characters.
5. `403 denied` the phrase matches the denylist.
6. `423 not_in_command_mode` Talon is not in `command` mode. `?force=1` skips this check only.
7. `422 no_match` Talon cannot parse the phrase; `422 not_single_command` it would run more than one command.
8. `403 denied` the rule Talon matched is on the denylist (catches innocent-looking phrases).
9. With `id`: `404 unknown_command`, or `409 rule_mismatch` (response has `would_run`) if a different rule would win now.
10. `?dry_run=1` stops here with `200` and `dry_run: true`.
11. `actions.mimic(phrase)` runs on Talon's main thread. `200` on success, `504` if it never started within 5 s.

Success body: `{"ok": true, "matched_rule": "...", "path": "..."}`.

Execution goes only through `actions.mimic`, so it behaves like speech: current
context, mode and ranking all apply, and a stale choice fails safe with 409/422.
The `200` means the command was matched and handed to Talon, not that its
action succeeded.

### Denylist

Edit `trillium/palette_feed/denylist.py`. It matches the phrase and the matched
rule, ignoring case and punctuation: anything containing `sudo` (this repo's
prefix for system commands), `restart/quit/kill talon`, `talon restart/quit`,
`shutdown`, `reboot`, `log out`, `system command`, `kill all`.
A leaked token is voice-level control of the machine, so keep this list tight.

## Settings

Constants at the top of `trillium/palette_feed/palette_feed.py`:
`TOKEN_PATH`, `EXECUTE_RATE` (calls, seconds), `EXECUTE_TIMEOUT_S`.
`Config(require_command_mode=..., max_body_bytes=...)` is passed to `PaletteApi` there.
The server refuses any non-loopback bind in `server.start`.

## Behavior to know

- **Start and reload.** The server starts on Talon's `ready` event and stops the
  previous instance on hot reload. Deleting the module does *not* stop it
  (Talon has no unload hook); restart Talon, or from the REPL call
  `sys.modules["_trillium_palette_feed"].server.shutdown()`.
- **Threads.** A pool of 4 worker threads plus the accept thread, all started once.
  Talon logs a "User script started a thread" warning for each at startup; a
  thread-per-request server would log one for every request.
- **Logs.** The server never logs request lines or window titles.
- **One server per host.** MacBook and mini0 have different command sets; each
  runs its own server from this repo.
- **Windows titles** in `/state` can contain private text. The only protection
  is the token and the tailnet.

## Tests

```sh
python -m pytest test/test_palette_feed_helpers.py test/test_palette_feed_api.py -v
```

The pure modules (`auth`, `limits`, `denylist`, `dispatch`, `simparse`,
`serialize`, `api`, `server`) import no Talon code. Only `palette_feed.py` does,
so it is the one file not covered by unit tests.
