# Palette feed

A small HTTP server inside Talon that lets a phone (the palette app) read the
active command set and run a command. Code: `trillium/palette_feed/`.
Design and evidence: the scope report for task-jyg9w (project-7u7w).

The server also serves a phone-first search page at `GET /`: one self-contained HTML
file, no build step and no CDN, so a phone can open `http://<host>:7399/`, search every
active command, and tap one to run it. The page holds no credential. See "Phone page"
below.

It listens on `127.0.0.1:7399` by default, with reads requiring a bearer token. Three
switches are configured per host and default to the closed behavior: a wider bind address,
open reads, and open execute. `/execute` needs the token unless a host explicitly turns
`open_execute` on — and while it is on, **any device that can reach the bind can run
Talon commands**. There is no `tailscale serve` and no proxy anywhere in this.

## Set up the token

Only a gated route needs the token. With both `open_reads` and `open_execute` on, the feed
runs fine with no token file at all; skip this section.

The token lives outside every git repo, mode `0600`. While reads are authenticated a
missing token stops the feed from starting (it prints why to the Talon log); with
`open_reads` on it still starts, and `/execute` answers 401 until either a token exists or
`open_execute` is on.

```sh
mkdir -p -m 700 ~/.config/talon-palette
(umask 077; python3 -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.config/talon-palette/token)
chmod 600 ~/.config/talon-palette/token
```

- Override the path with `TALON_PALETTE_TOKEN_FILE`.
- The feed refuses a token file that is group/world readable, shorter than
  32 characters, or inside the repo it was loaded from. The first two are fatal only
  while some route is still gated; a repo-local token is fatal either way (see the matrix
  below).
- Rotate by writing a new token, then reloading the module (touch
  `trillium/palette_feed/palette_feed.py`) or restarting Talon.
- Any client that talks to a gated route carries one token per host: the palette app uses
  the phone's Keychain, `curl` uses `-H "Authorization: Bearer $TOKEN"`.

## Bind and auth

All three axes are configured per host, as an environment variable or the matching Talon
setting. The environment wins. All three settings are declared with `Module.setting` in
`palette_feed.py`; without that declaration Talon drops a `.talon` assignment with a
"settings skipped because they have no matching declaration" warning and the feed keeps the
closed defaults (that was task-ncz8l).

| env var                      | Talon setting                    | default     |
| ---------------------------- | -------------------------------- | ----------- |
| `TALON_PALETTE_BIND`         | `user.palette_feed_bind`         | `127.0.0.1` |
| `TALON_PALETTE_OPEN_READS`   | `user.palette_feed_open_reads`   | `false`     |
| `TALON_PALETTE_OPEN_EXECUTE` | `user.palette_feed_open_execute` | `false`     |

The switches take `1/true/yes/on` or `0/false/no/off`, case-insensitive. A value it cannot
read is ignored, with one line in the Talon log rather than a silent change of behavior.
Every default is the closed one: nothing is published, and nothing runs, until a host says
so.

### The matrix

`open_reads` decides read auth and `open_execute` decides execute auth; the bind only
decides who can reach the socket. They are independent.

| `bind`                      | `open_reads`      | `open_execute`    | `GET /`, `/state`, `/commands`, `/lists/<name>` | `POST /execute` |
| --------------------------- | ----------------- | ----------------- | ----------------------------------------------- | --------------- |
| `127.0.0.1` (default)       | `false` (default) | `false` (default) | bearer token                                    | bearer token    |
| `127.0.0.1`                 | `true`            | `false`           | no token                                        | bearer token    |
| `127.0.0.1`                 | `false`           | `true`            | bearer token                                    | no token        |
| `127.0.0.1`                 | `true`            | `true`            | no token                                        | no token        |
| `0.0.0.0` or the tailnet IP | `false`           | `false`           | bearer token                                    | bearer token    |
| `0.0.0.0` or the tailnet IP | `true`            | `false`           | no token                                        | bearer token    |
| `0.0.0.0` or the tailnet IP | `false`           | `true`            | bearer token                                    | **no token**    |
| `0.0.0.0` or the tailnet IP | `true`            | `true`            | no token                                        | **no token**    |

A token is still accepted on an open route; it is simply not required. Whether a gated
route is fatal when there is no usable token follows from the matrix, so the token file is
the last input:

| Token file at `TALON_PALETTE_TOKEN_FILE`  | nothing open                         | `open_reads=true`                                | `open_execute=true`                           |
| ----------------------------------------- | ------------------------------------ | ------------------------------------------------ | --------------------------------------------- |
| `0600`, 32+ chars, outside every git repo | reads and `/execute` work            | reads open, `/execute` works                     | reads work, `/execute` open                   |
| missing, unreadable, too short, or `0644` | the feed does not start (prints why) | the feed starts, reads open, `/execute` is `401` | the feed starts, reads `401`, `/execute` runs |
| inside the repo it was loaded from        | the feed does not start              | the feed does not start                          | the feed does not start                       |

A gated route failing closed with no configured token is deliberate: there is no
credential to check a caller against, so the endpoint is disabled rather than open — except
where a host explicitly opened it.

### Publish it for the phone

On each host, for the phone. Copy the machine's tailnet address rather than using
`0.0.0.0`, which also listens on every other interface:

```sh
export TALON_PALETTE_BIND=$(tailscale ip -4)   # or 0.0.0.0, which is wider
export TALON_PALETTE_OPEN_READS=1
export TALON_PALETTE_OPEN_EXECUTE=1
```

or in a settings block in any `.talon` file:

```
settings():
    user.palette_feed_bind = "100.64.0.1"   # this host's tailnet address
    user.palette_feed_open_reads = true
    user.palette_feed_open_execute = true
```

Reload `trillium/palette_feed/palette_feed.py` (touch it) or restart Talon; the log prints
the resulting shape, and names the open execute loudly:

```
palette_feed: WARNING /execute is open: any device that can reach 100.64.0.1:7399 can run Talon commands
palette_feed: listening on 100.64.0.1:7399 (tailnet/network, reads open, /execute open (no token needed))
```

**While `open_execute` is on, the tailnet is the only thing between a network peer and
voice control of this machine.** Every device on the tailnet — and everything on any other
interface the bind covers — can run any non-denylisted command. Keep the denylist tight,
keep the bind on the tailnet address, and turn `open_execute` off again when the phone does
not need it. With the default loopback bind, only this machine can reach it.

The phone then uses `http://<host>:7399` — the MacBook or mini0 tailnet address, over
plain HTTP on the tailnet. No `tailscale serve`, no Funnel, and nothing on the public
internet. Opening that URL in the phone's browser is the search page described under
[Phone page](#phone-page-get-).

`0.0.0.0` listens on every interface, including non-tailnet ones the machine has. Use
the machine's own tailnet address (`tailscale ip -4`) to keep the socket on the tailnet
only. A hostname that is not an IP address counts as non-loopback too, so it needs the
same explicit configuration; `server.start` refuses any other non-loopback bind.

## Endpoints

`GET /`, `GET /state`, `GET /commands` and `GET /lists/<name>` need
`Authorization: Bearer <token>` only while `open_reads` is off. `POST /execute` needs it
only while `open_execute` is off, and answers `401 {"ok":false,"error":"unauthorized"}`
when the token it does need is missing, wrong, or unconfigured. That same 401 comes back for
every gated path _before_ routing, so an unauthenticated caller still cannot tell which
routes exist; the only routes it can see are the ones the operator opened.

```sh
TOKEN=$(cat ~/.config/talon-palette/token)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:7399/state
curl -s http://$(tailscale ip -4):7399/state     # with open_reads: reading needs no token
curl -s -X POST -d '{"phrase":"playback now"}' http://$(tailscale ip -4):7399/execute   # with open_execute
```

| Method and path     | What it returns                                                                                                                                                  |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /`             | The phone page: one HTML file, `text/html; charset=utf-8`, `Cache-Control: no-store`. No secrets in it, so it follows `open_reads` like the other reads.         |
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

1. `401` the route is gated and no token is configured, or the request's token is missing or wrong. Skipped entirely while `open_execute` is on.
2. `429` more than 5 calls per second (`Retry-After` header). Counted per server, not per caller.
3. `411` no `Content-Length` (chunked is refused), `400` bad length, `413` body over 4096 bytes.
4. `400` body is not a JSON object with a printable `phrase` of 1-200 characters.
5. `403 denied` the phrase matches the denylist.
6. `423 not_in_command_mode` Talon is not in `command` mode. `?force=1` skips this check only.
7. `422 no_match` Talon cannot parse the phrase; `422 not_single_command` it would run more than one command.
8. `403 denied` the rule Talon matched is on the denylist (catches innocent-looking phrases).
9. With `id`: `404 unknown_command`, or `409 rule_mismatch` (response has `would_run`) if a different rule would win now.
10. `?dry_run=1` stops here with `200` and `dry_run: true`. It only parses (`speech_system._sim`), which needs no speech engine, so it keeps working on a catalogue-only device.
11. `503 engine_inactive` Talon has no speech engine attached (`scope.get("speech.engine")` is `None`). Nothing is dispatched. Without this check `actions.mimic` is a silent no-op and the call would answer `200` while running nothing.
12. `actions.mimic(phrase)` runs on Talon's main thread. `200` on success, `504` if it never started within 5 s.

The 503 body is `{"ok": false, "error": "engine_inactive", "hint": "<plain English>"}`; the
hint says the speech engine is not running on that machine and to start or attach it in Talon.
`GET /`, `/state`, `/commands` and `/lists/<name>` are unaffected, so a device with no engine
still serves its command catalogue. When verifying a real run, a `200` whose command did not
happen is no longer expected: treat it as a bug, and a `503 engine_inactive` as the host
being unable to execute.

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
A leaked token is voice-level control of the machine, and so is an open `/execute`; keep
this list tight either way.

## Phone page (`GET /`)

Open `http://<host>:7399/` on the phone. One static HTML file
(`trillium/palette_feed/page.html`, served by `page.py`), no build step, no CDN, no
credential of any kind: no token field, no `Authorization` header (its `localStorage`
holds only UI state, below). It needs `open_reads` to load and `open_execute` to run
anything. Adding a device: [`palette-setup.md`](palette-setup.md).

- **Search.** The active command set is fetched once from `/commands` and ranked
  client-side: a contiguous hit beats a subsequence hit, and a shorter rule wins a tie.
  A `?rev=` round trip means a second load can answer `304`.
- **Header.** `app`, window title, modes and language, polled from `/state` every 5s while
  the page is visible (`command` is highlighted when Talon is in command mode).
- **Run.** Tapping a fully literal rule POSTs `/execute` immediately. A rule with
  `(a | b)` alternation, `{list}` slots or `<capture>` slots opens a small form first —
  with `/lists/<name>` suggestions for list slots — plus **Edit phrase** to hand-fix any
  template the builder reads wrongly. Every request carries `{phrase, id}`.
- **First run.** A small block says what the page is and gives one search tip. **Got it**
  hides it and remembers that in `localStorage` (it also hides after the first
  successful run).
- **Recent and favorites.** The last 10 successful runs (newest first, de-duplicated) show
  as **Recent**; the ☆ on a row stars a command into **Favorites** above the results.
  Keys `palette_intro_dismissed`, `palette_recents`, `palette_favorites`: per device and
  browser, not synced. Every storage access is wrapped in try/catch and stored JSON is
  shape-checked, so corrupt or blocked storage just means nothing persists.
- **Engine off.** A `503 engine_inactive` shows the feed's `hint` text instead of success.
- **Failures are guidance.** A 401 (the Mac has not opened `/execute`, and the guide
  names `user.palette_feed_open_execute`), 423 (not in command mode, with **Run anyway** =
  `?force=1`), 429, 403 denylist, 404/409 stale rule, 422 no_match, 504 timeout, any 5xx,
  or an unreachable host each render a title plus the exact next step — check the tailnet,
  check Talon is running, where the Mac's log is — never a bare status or raw JSON, and
  never advice about credentials, because the page has none.
- **Nothing to leak.** The page carries no credential and no external asset, so serving it
  is not the interesting part of the exposure: `open_execute` is.

Editing `page.html` needs `page.py` re-imported to serve the new bytes: touch
`trillium/palette_feed/page.py` (or restart Talon). The feed logs nothing about page
requests.

## Settings

Constants at the top of `trillium/palette_feed/palette_feed.py`: `TOKEN_PATH`,
`EXECUTE_RATE` (calls, seconds), `EXECUTE_TIMEOUT_S`, and the three `Module.setting`
declarations. `Config(open_reads=..., open_execute=..., require_command_mode=...,
max_body_bytes=...)` is passed to `PaletteApi` there.

`options.resolve` picks the bind and the two switches (env, then Talon setting, then the
defaults above); `auth.plan_token` is the single place that decides whether the feed starts
and which routes end up disabled. `api._permitted` is the single place that decides what a
request is allowed to do: open reads, then an open `/execute`, then the token.
`server.start` refuses a non-loopback bind unless its caller passes
`allow_non_loopback=True`, which only `options` does, and only for an address the operator
configured.

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
- **Settings must be declared.** A `.talon` `settings():` block only assigns a setting that
  `palette_feed.py` declared with `Module.setting`; otherwise Talon logs "settings skipped
  because they have no matching declaration" and `settings.get` keeps returning the default,
  so the host looks configured and is not. That is task-ncz8l;
  `test/test_palette_feed_settings.py` fails if a declared name and the name `options`
  reads ever drift apart.
- **Heads-up at start.** The log line names the bind, whether reads are open, and
  whether `/execute` is armed; with `open_execute` on it adds a `WARNING /execute is open`
  line naming the address, so a misconfigured host is visible without a probe.

## Tests

```sh
python -m pytest test/test_palette_feed_helpers.py test/test_palette_feed_api.py test/test_palette_feed_impl_shapes.py test/test_palette_feed_settings.py test/test_palette_feed_startup.py test/test_palette_feed_page.py -v
node test/palette_page_check.mjs        # the page's script: search, templates, fix-guides
# the page's DOM wiring (needs jsdom, skipped without it):
npm install --prefix /tmp/palette-jsdom jsdom
NODE_PATH=/tmp/palette-jsdom/node_modules node test/palette_page_dom_check.mjs
```

The pure modules (`auth`, `limits`, `denylist`, `dispatch`, `simparse`, `serialize`,
`api`, `server`, `options`, `page`) import no Talon code. Only `palette_feed.py` does, so it is
the one file with no direct unit tests: `test_palette_feed_impl_shapes.py` covers its
`TalonBackend` over a stub registry, `test_palette_feed_settings.py` covers its setting
declarations, and the pure helpers cover everything `start_server` feeds it.

`test/test_palette_feed_page.py` checks `GET /` as bytes over a real socket, including the
invariant that the page has no credential handling at all. The page's script is pure logic
until it finds a `document`, so two node checks exercise the shipped script itself:
`test/palette_page_check.mjs` (no dependencies; search ranking, template filling,
fix-guide text, request shape) and `test/palette_page_dom_check.mjs` (jsdom; how the page
renders and what it sends — header from `/state`, filtering, the slot form, the one POST,
and the fix-guide per failure). Both skip when their dependencies are missing. Neither
covers a real phone: layout, touch and iOS behaviour are unverified by this suite.
