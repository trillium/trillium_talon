# Palette feed

A small HTTP server inside Talon that lets a phone (the palette app) read the
active command set and run a command. Code: `trillium/palette_feed/`.
Design and evidence: the scope report for task-jyg9w (project-7u7w).

It listens on `127.0.0.1:7399` by default, with reads requiring a bearer token. Two
switches publish it on the tailnet — a wider bind address and open reads — with no
`tailscale serve` and no proxy. `/execute` always requires the token, so a wider bind
never means unauthenticated voice control.

## Set up the token

The token lives outside every git repo, mode `0600`. While reads are authenticated a
missing token stops the feed from starting (it prints why to the Talon log); with
`open_reads` on it still starts, and only `/execute` is disabled.

```sh
mkdir -p -m 700 ~/.config/talon-palette
(umask 077; python3 -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.config/talon-palette/token)
chmod 600 ~/.config/talon-palette/token
```

- Override the path with `TALON_PALETTE_TOKEN_FILE`.
- The feed refuses a token file that is group/world readable, shorter than
  32 characters, or inside the repo it was loaded from. The first two are fatal only
  while reads are authenticated; a repo-local token is fatal either way (see the matrix
  below).
- Rotate by writing a new token, then reloading the module (touch
  `trillium/palette_feed/palette_feed.py`) or restarting Talon.
- Put the same token in the phone's Keychain while reads are authenticated, and always
  if the phone is to run commands (`/execute`). One token per host.

## Bind and auth

Both axes are configured per host, as an environment variable or the matching Talon
setting. The environment wins.

| env var                    | Talon setting                  | default     |
| -------------------------- | ------------------------------ | ----------- |
| `TALON_PALETTE_BIND`       | `user.palette_feed_bind`       | `127.0.0.1` |
| `TALON_PALETTE_OPEN_READS` | `user.palette_feed_open_reads` | `false`     |

`TALON_PALETTE_OPEN_READS` takes `1/true/yes/on` or `0/false/no/off`, case-insensitive.
A value it cannot read is ignored, with one line in the Talon log rather than a silent
change of behavior. Both defaults are the old behavior: nothing is published until a
host says so.

### The matrix

`open_reads` decides read auth. The bind only decides who can reach the socket.

| `bind`                      | `open_reads`      | `GET /state`, `/commands`, `/lists/<name>` | `POST /execute` |
| --------------------------- | ----------------- | ------------------------------------------ | --------------- |
| `127.0.0.1` (default)       | `false` (default) | bearer token                               | bearer token    |
| `127.0.0.1`                 | `true`            | no token                                   | bearer token    |
| `0.0.0.0` or the tailnet IP | `false`           | bearer token                               | bearer token    |
| `0.0.0.0` or the tailnet IP | `true`            | no token                                   | bearer token    |

A missing token is fatal only while reads are authenticated, so the token file itself
is the third input:

| Token file at `TALON_PALETTE_TOKEN_FILE`  | `open_reads=false`                   | `open_reads=true`                                |
| ----------------------------------------- | ------------------------------------ | ------------------------------------------------ |
| `0600`, 32+ chars, outside every git repo | reads and `/execute` work            | reads open, `/execute` works                     |
| missing, unreadable, too short, or `0644` | the feed does not start (prints why) | the feed starts, reads open, `/execute` is `401` |
| inside the repo it was loaded from        | the feed does not start              | the feed does not start                          |

`/execute` failing closed when no token is configured is deliberate: there is no
credential to check a caller against, so the endpoint is disabled rather than open.

### Publish it for the phone

On each host, for the phone:

```sh
export TALON_PALETTE_BIND=0.0.0.0
export TALON_PALETTE_OPEN_READS=1
```

or in a settings block in any `.talon` file:

```
settings():
    user.palette_feed_bind = "0.0.0.0"
    user.palette_feed_open_reads = true
```

Reload `trillium/palette_feed/palette_feed.py` (touch it) or restart Talon; the log
prints the resulting shape:

```
palette_feed: listening on 0.0.0.0:7399 (tailnet/network, reads open, /execute token-gated)
```

The phone then uses `http://<host>:7399` — the MacBook or mini0 tailnet address, over
plain HTTP on the tailnet. No `tailscale serve`, no Funnel, and nothing on the public
internet.

`0.0.0.0` listens on every interface, including non-tailnet ones the machine has. Use
the machine's own tailnet address (`tailscale ip -4`) to keep the socket on the tailnet
only. A hostname that is not an IP address counts as non-loopback too, so it needs the
same explicit configuration; `server.start` refuses any other non-loopback bind.

## Endpoints

`GET /state`, `GET /commands` and `GET /lists/<name>` need `Authorization: Bearer <token>`
only while `open_reads` is off. `POST /execute` always needs it, and answers
`401 {"ok":false,"error":"unauthorized"}` when it is missing, wrong, or unconfigured.
That same 401 comes back for every non-read path _before_ routing, so an unauthenticated
caller still cannot tell which routes exist; the only routes it can see are the reads the
operator published.

```sh
TOKEN=$(cat ~/.config/talon-palette/token)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:7399/state
curl -s http://$(tailscale ip -4):7399/state     # with open_reads: reading needs no token
```

| Method and path     | What it returns                                                                                                                                                  |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /state`        | `host`, `ts`, `rev`, `app{name,bundle}`, `window{title,filename,file_ext}`, `modes`, `tags`, `language`, `commands_rev`                                          |
| `GET /commands`     | `commands_rev`, `count`, `commands[]`. `ETag` is the `commands_rev`. `?rev=<commands_rev>` or `If-None-Match` gives `304`. `?q=text` filters rules by substring. |
| `GET /lists/<name>` | `{name, entries[]}` for a list used by an active rule (404 for any other name)                                                                                   |
| `POST /execute`     | Runs `{"phrase": "...", "id": "<command id>"}`. `id` is optional.                                                                                                |

Each entry in `commands`:

```json
{
  "id": "cb2eab42dd",
  "rule": "(abbreviate | brief) {user.abbreviation}",
  "kind": "list",
  "slots": [{ "name": "user.abbreviation", "type": "list", "n": 826 }],
  "context": "user.trillium_talon.core.text.text.talon",
  "lineno": 30,
  "shadowed": 0
}
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

1. `401` no token is configured, or the request's token is missing or wrong.
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

Constants at the top of `trillium/palette_feed/palette_feed.py`: `TOKEN_PATH`,
`EXECUTE_RATE` (calls, seconds), `EXECUTE_TIMEOUT_S`. `Config(open_reads=...,
require_command_mode=..., max_body_bytes=...)` is passed to `PaletteApi` there.

`options.resolve` picks the bind and `open_reads` (env, then Talon setting, then the
defaults above); `auth.plan_token` is the single place that decides whether the feed
starts and whether `/execute` is armed. `server.start` refuses a non-loopback bind
unless its caller passes `allow_non_loopback=True`, which only `options` does, and only
for an address the operator configured.

## Behavior to know

- **Two `CommandImpl` shapes.** Talon 0.4.0 (115.0) ships
  `CommandImpl(ctx, rule, script, experiments)`: no `trigger` and no `lineno`, so the trigger text
  is `impl.rule.rule` and the line is `impl.script.start_line`. Builds from the
  `CommandImpl(ScriptImpl)` refactor (0.4.0-1561-9c3d and later) answer both directly.
  `serialize.impl_to_raw` reads the newer values where present and falls back otherwise, so one
  feed serves either build without a 500. The fallbacks are id-equivalent to the newer build's
  values, which is why the phone's cached ids survive talking to either host. Full evidence: the
  scope report for task-ykd7c.
- **Start and reload.** The server starts on Talon's `ready` event and stops the
  previous instance on hot reload. Deleting the module does _not_ stop it
  (Talon has no unload hook); restart Talon, or from the REPL call
  `sys.modules["_trillium_palette_feed"].server.shutdown()`.
- **Threads.** A pool of 4 worker threads plus the accept thread, all started once.
  Talon logs a "User script started a thread" warning for each at startup; a
  thread-per-request server would log one for every request.
- **Logs.** The server never logs request lines or window titles.
- **One server per host.** MacBook and mini0 have different command sets; each
  runs its own server from this repo.
- **Windows titles** in `/state` can contain private text. While reads are
  authenticated the token and the tailnet protect them; with `open_reads` on the tailnet
  is the only protection, which is why the bind is worth pinning to the tailnet address.
- **Heads-up at start.** The log line names the bind, whether reads are open, and
  whether `/execute` is armed, so a misconfigured host is visible without a probe.

## Tests

```sh
python -m pytest test/test_palette_feed_helpers.py test/test_palette_feed_api.py test/test_palette_feed_impl_shapes.py -v
```

The pure modules (`auth`, `limits`, `denylist`, `dispatch`, `simparse`, `serialize`,
`api`, `server`, `options`) import no Talon code. Only `palette_feed.py` does, so it is
the one file with no direct unit tests: `test_palette_feed_impl_shapes.py` covers its
`TalonBackend` over a stub registry, and the pure helpers cover everything `start_server`
feeds it.
