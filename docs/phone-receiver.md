# Phone receiver (work items 1, 2, 4 Mac side and 5)

Accepts a phone-computed acoustic emission (`TPE1`) and runs it through a `W2lEngine`'s own
padding, decode, rejection and `phrase` dispatch, replacing only the encoder call. Code:
`trillium/phone_receiver/`. The decoder path opens no socket and registers nothing with `speech_system`. Work item 2 wires it to the
live engine behind `user.phone_receiver_enabled` (default off); see "Live install" below. Work items 4 (Mac side) and 5
add an HTTP listener (loopback, or this Mac's tailnet address with a shared-secret key) and a PCM fallback on the same switch; see "Listener" and "Tailnet bind" below.
An optional utterance id makes a retry safe after a lost reply (replay, `GET /result/<id>`); see "Durable delivery".
`POST /snippet` saves a short phone recording into Talon's recordings folder, and `GET /metrics` reports per-request latency and bytes; see "Snippets" and "Metrics" below.
`POST /noise` runs the `parrot(<name>)` trigger for a sound the phone detected; see "Noises" below.

| File                     | Role                                                                                                                                                                                                                                                                                                                   |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `wire.py`                | `parse_validate` / `validate_array` / `pack` / `frames_for`; every check runs before native code, failures are `WireError(code)`                                                                                                                                                                                       |
| `encoder.py`             | `PhoneEncoder`: bounded queue, `forward()` returns `(1, 1, T, 29)`                                                                                                                                                                                                                                                     |
| `live.py`                | `LiveInstall(get_engine, is_enabled, record_all).handle(bytes)`: the gate, in plain Python; `active_engine(speech_system)` is the glue's lookup. Refuses `disabled`, `record_all_on`, `no_engine` (with a `detail`, below); otherwise `PhoneReceiver.handle`. `heal()` restores the mic encoder if it was left swapped |
| `phone_receiver_live.py` | Talon glue: declares `user.phone_receiver_enabled` (bool, default false) and the action `user.phone_receiver_handle(payload: bytes) -> str` (`"ok"` or an error code). No voice commands, no socket                                                                                                                    |
| `service.py`             | `PhoneService`: one call per utterance, returns `Reply(ok, error, text, reject, ms, ..., kind, status, why, commands)`. `PhraseTap` is the `phrase` listener it captures the call's own phrase with                                                                                                                    |
| `listener.py`            | `ListenerApi` (the whole HTTP policy, pure) and a worker-pool server for `POST /emission` and `GET /result/<id>` that binds loopback or an assigned tailnet address only                                                                                                                                               |
| `ledger.py`              | Pure: the idempotency table. `parse_id`, `Ledger.begin` / `finish` / `lookup`: which utterance ids this process has seen and what each came to (memory only, TTL and cap). See "Durable delivery"                                                                                                                      |
| `netbind.py`             | `resolve_bind(host)`: accepts only `127.0.0.1` or a `100.64.0.0/10` address that `tailscale ip -4` lists as assigned to this Mac; `BindError` otherwise                                                                                                                                                                |
| `keyfile.py`             | The shared secret: `ensure_key` / `load_key` (0600 file outside any repo), `matches` (constant-time). `python -m trillium.phone_receiver.keyfile` creates it and prints only the path                                                                                                                                  |
| `faillog.py`             | What a failure writes to Talon's log (below): exception class and `file:line in function` frames, never the message, key, phrase text or audio                                                                                                                                                                         |
| `hop.py`                 | Pure: hands a job to the main thread inside a given Talon resource context; `SchedulerUnavailable` when it cannot                                                                                                                                                                                                      |
| `parity.py`              | Parity harness: both paths on the same audio through `ListenerApi`, phrase output diffed                                                                                                                                                                                                                               |
| `receiver.py`            | `PhoneReceiver(engine).handle(bytes) -> Result`: validate, then under `engine.lock` swap encoder, queue, `_on_audio_frame([0.0]*n_pcm, ts, pad=True)`, restore encoder. Never raises                                                                                                                                   |
| `snippet.py`             | `SnippetService.handle`: header checks, checksum, idempotent save, ack for `POST /snippet`; pure, no `talon` import                                                                                                                                                                                                    |
| `noise.py`               | `parse_body` and `NoiseService.handle`: validate a phone-detected noise event, gate, drop a stale `seq`, floor per name, run the last `parrot_noises` impl for `POST /noise`; pure, no `talon` import |
| `audio.py`               | Header-level FLAC / WAV validation (16 kHz mono 16-bit, 0.1 to 30 s) against the body's own length; `AudioError(code)`; no decoding                                                                                                                                                                                    |
| `recordings.py`          | `RecordingsWriter`: the only code that writes into Talon's recordings folder; new files only, temp then fsync then no-overwrite link                                                                                                                                                                                   |
| `snippet_ledger.py`      | Durable `utterance id -> ack` table (JSON lines, fsynced), the file-ack layer behind `ledger.py`'s memory table: a retry of a saved snippet, however late, writes nothing; a pending entry covers a crash after the file landed                                                                                        |
| `metrics.py`             | `Trace` (per-request stopwatch), `Sample`, `Metrics` (rolling p50/p95, hourly buckets, log line); no phrase or audio can enter it                                                                                                                                                                                      |

## Wire format

24-byte little-endian header `<4sBBHIId` (`TPE1`, dtype 0=f32 / 1=f16, flags, reserved, `T`,
`n_pcm`, `ts`) then `T*29` row-major values. Raw logits, not log-softmax. Rejected: wrong magic
or dtype, short or wrong-length body, payload over 64 KiB, `T` outside 1..1200, non-finite or
`|x| >= 1e4`, bad `ts`, `T != frames_for(n_pcm)`, and any array that is not `(T, 29)`.

A transposed body of the same byte length cannot be told from a valid one on the wire; the
header `T` check catches it unless `T` happens to equal 29, and the decoder only aborts on a
wrongly shaped array, which `validate_array` never lets through.

## Frame count

`frames_for(n_pcm)` is `ceil(((n_pcm + 8000 - 400) // 160 + 1) / 3)`, not the scout report's
`(n_pcm + 8000) // 480`, which is off by one for some lengths (e.g. 11187 samples gives 40
frames). The lab script checks the formula against the real encoder over a length sweep.

## Tests

- `python -m pytest .tests/test_phone_receiver.py`: fake engine, no Talon.
- `.tests/lab/phone_receiver_lab.py`: run in the Talon REPL against a private `W2lEngine`
  (reads `_model_info` and `grammar` from the live engine to build it; registers nothing).
  Needs a directory of 16 kHz mono int16 TTS wavs (`say -o x.wav --data-format=LEI16@16000 "page down"`):

  ```
  printf '%s\n' "exec(\"import os\nos.environ['PHONE_LAB_REPO']='$PWD'\nPHONE_LAB_DIR='/path/to/wavs'\nexec(open('$PWD/.tests/lab/phone_receiver_lab.py').read())\")" | ~/.talon/bin/repl
  ```

  The REPL accepts one statement per stdin line, hence the single `exec`. It prints `LAB PASS`
  or `LAB FAIL` plus a summary. Last run: 20 utterances (13 with words, 7 rejected by the
  engine) equal to the Mac-model reference for fp32 and fp16, 13 malformed payloads rejected
  with zero decoder calls, median 6.9 ms per utterance.

## Live install (work item 2)

`actions.user.phone_receiver_handle(payload)` is the only entry point; a transport (work item 4)
will call it. The engine is looked up per call (`speech_system.engine.engine`), so an engine
switch needs no reload.

- **Off (default):** returns `disabled`, never touches the engine.
- **On:** validates in Python, then swaps the phone encoder in under `engine.lock` for the one
  injected utterance and restores the mic encoder in a `finally`. Microphone frames use the
  engine's own encoder before and after; there is no persistent swap to undo when the setting
  flips.
- **`speech.record_all` on:** returns `record_all_on` and does nothing. The injected audio is
  all zeros, and the engine would write a silent recording per utterance.

The repo's `settings.talon` sets `speech.record_all = 1`, and Talon has no public runtime
setter for it, so a live injection needs it set to 0 first (edit the live `settings.talon`
or an override `.talon` file, then restore).

Live evidence (Talon REPL, real engine, no injection): off gives `disabled`; on with the live
`record_all = 1` gives `record_all_on`; a valid payload through a proxy that exposes the live
engine's `lock` and `encoder` but a spy `_on_audio_frame` swaps in `PhoneEncoder`, calls once,
and restores the original `W2lOrtEncoder`; 8 malformed payloads are all refused with zero
engine calls; Talon's PID unchanged.

### End-to-end live injection (verified 2026-10-19)

With `user.phone_receiver_enabled = 1` and `speech.record_all = 0` (temporary override file,
removed after), one synthetic TTS emission through `user.phone_receiver_handle` returned `ok`,
and `page down` reached `speech_system`'s `pre:phrase`/`phrase`/`post:phrase` listeners and
`user.history_get(0)`. The mic encoder was restored, and the malformed payloads were still refused
before any native call.

**Gate that hid it for a while: a locked macOS session.** While `CGSSessionScreenIsLocked` is true,
`SpeechSystem.engine_event` drops every phrase silently: the inner engine decodes and dispatches,
`EngineProxy._redispatch` calls `engine_event('phrase', proxy, j)`, and it returns `None` with no
listener called. The same happens for mic frames and for `actions.mimic`. Run any live injection
with the screen unlocked, and check `Quartz.CGSessionCopyCurrentDictionary()` first.

Injected phrases are logged like spoken ones by `command_logger`; set
`user.command_logger_enabled = 0` for a test run so nothing is appended to `~/.talon/recordings`.

### Injected emission executes a command (verified 2026-10-19)

The earlier test showed `page down` reaching `speech_system` listeners and history, but no
observable effect. This one uses existing commands that change Talon's mode, read back with
`scope.get("mode")`: `dictation mode` / `command mode` (`core/modes/command_and_dictation_mode.talon`,
which call `user.dictation_mode()` / `user.command_mode()`). No voice command or grammar was added.

Procedure: screen unlocked, temp override `.talon` (`user.phone_receiver_enabled = 1`,
`speech.record_all = 0`) removed afterwards, `command_logger._write_jsonl` swapped for an in-memory
no-op (the live checkout predates `user.command_logger_enabled`; 2 calls swallowed, original restored),
a private `W2lEngine` decoded two `say` wavs to emissions, `wire.parse_validate` passed in Python
before any live call, then `user.phone_receiver_handle(payload)` on the live engine:

| Step | Start state                                                                  | Injected         | Result                                                                                         |
| ---- | ---------------------------------------------------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------- |
| A    | sleep (`speech.enabled()` False)                                             | `command mode`   | `ok`, modes unchanged, `user.history_get(0)` unchanged                                         |
| B    | woken from the REPL (`speech.enable()`, `user.command_mode()`), not injected |                  | `command` in modes                                                                             |
| C    | command mode                                                                 | `dictation mode` | `ok` in about 127 ms; `dictation` in modes, `command` out; `history_get(0)` = `dictation mode` |
| D    | dictation mode                                                               | `command mode`   | `ok` in about 101 ms; `command` in modes, `dictation` out; `history_get(0)` = `command mode`   |

Only the injection changed the mode in C and D, so Talon's own grammar matched the phrase and ran the
command. The mode had already flipped when `phone_receiver_handle` returned: dispatch is synchronous.
Seam: `phone_receiver_handle` -> `PhoneReceiver.handle` -> `engine._on_audio_frame` (phone encoder) ->
inner `W2lEngine` decode -> `EngineProxy._redispatch` -> `SpeechSystem.engine_event` -> `Executor.run_phrase`
(native, so a Python class spy cannot see it; the mode change and history entry are the evidence).

Limits: the command mode and dictation mode paths are shown. In sleep mode (A) the phrase had no
effect and no history entry, but `command mode` is not in the sleep grammar, so this does not tell
a speech-disabled drop from a grammar miss; a phrase from the sleep grammar (`welcome back` calls
`user.mouse_wake()`) was not injected. `phone_receiver_handle` returns `ok` in sleep mode, so `ok`
means "decoded and dispatched", not "a command ran". Restored and diffed afterwards: Talon PID,
`~/.talon/recordings` mtime, both `settings.talon` hashes, live checkout HEAD and `git status`
all identical; the live host went back to sleep mode as found.

## Listener (work items 4 Mac side and 5)

`POST /emission`, one utterance per request, on port **7403** (checked free with `lsof`; the palette
feed holds 7399/7401). The bind address is `user.phone_receiver_bind`: `127.0.0.1` (default) or this
Mac's tailnet address; `listener.start` refuses everything else (see "Tailnet bind"). There is no
`tailscale serve` mapping and none is needed: the phone talks straight to the Mac's tailnet address.

The server starts only when `user.phone_receiver_enabled` is on at Talon's `ready` (or at a module
reload: touch `phone_receiver_live.py`); with it off no socket is opened. The gate is also checked
per request, so turning it off later answers `503 disabled` until the next reload stops the socket.

| Setting                              | Default     | Meaning                                                                                                                                                                           |
| ------------------------------------ | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `user.phone_receiver_enabled`        | `false`     | Existing gate; also decides whether the listener starts                                                                                                                           |
| `user.phone_receiver_bind`           | `127.0.0.1` | `127.0.0.1` or an address from `tailscale ip -4`. Anything else (`0.0.0.0`, LAN, hostname, an unassigned tailnet address) is refused and no socket opens. Read at start or reload |
| `user.phone_receiver_allowed_logins` | `""`        | Loopback bind only: comma or space separated `Tailscale-User-Login` values. Empty denies everyone; `*` is a literal, not a wildcard                                               |
| `user.phone_receiver_mode`           | `emission`  | `emission` (TPE1 body) or `pcm` (PCM16 body). Read per request, so flipping it needs no reload                                                                                    |

Declare them in a `.talon` `settings():` block, e.g. `user.phone_receiver_allowed_logins = "trillium@example.com"`
(the repo's `settings.talon` does not set any; the default is closed).

Request: `Content-Type` per mode, `Content-Length` required, body at most 65536 bytes. Checks run
in this order and stop at the first failure, before the body is read until step 5:

| Step | Check                                                                                                                  | Failure                                                                                 |
| ---- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| 1    | path is `/emission`, method is `POST`                                                                                  | `404 not_found`, `405 method_not_allowed`                                               |
| 2    | auth: tailnet bind `X-Talon-Phone-Key` matches the key file; loopback bind `Tailscale-User-Login` is in the allow-list | `403 forbidden` (missing, wrong and empty-list are indistinguishable)                   |
| 3    | mode is `emission` or `pcm`; content type                                                                              | `503 bad_mode`; `415 unsupported_media_type` (names the type wanted)                    |
| 4    | rate: 10 per second per server                                                                                         | `429 rate_limited` + `Retry-After`                                                      |
| 4a   | `X-Talon-Utterance-Id`, if present, is a usable id                                                                     | `400 bad_utterance_id` (a present but unusable id never falls back to "no id")          |
| 5    | `Content-Length` present, not chunked, <= 64 KiB                                                                       | `411 length_required`, `400 bad_content_length`, `413 body_too_large` (nothing read)    |
| 6    | body read in full                                                                                                      | `400 truncated_body`                                                                    |
| 7    | `wire.parse_validate` / `wire.parse_pcm`                                                                               | `422 <wire code>` (`bad_magic`, `frame_mismatch`, `non_finite`, `pcm_odd_length`, ...)  |
| 7a   | id claimed: a finished or running id is answered from the table (replay, `409 in_progress`), not executed              | see "Durable delivery"                                                                  |
| 8    | live gate                                                                                                              | `503 disabled`, `503 record_all_on`, `503 no_engine`; `500 engine_error`; `504 timeout` |
| 8a   | main-thread hop (before the gate runs)                                                                                 | `503 scheduler_unavailable` (never queued, so the command did not run)                  |

`GET /result/<id>` is a separate path with its own short list of checks (method, auth, rate, id), below.
Steps 1 to 7 never claim an id: a request refused there ran nothing and is not remembered.

Success: `200 {"ok":true,"mode":"emission","text":"page down","reject":false,"ms":6.9,"frames":43,"status":"ran","why":null,"kind":"command","commands":1,"total_ms":8.1}`
(see "Reply fields" below). Every error is `{"ok":false,"error":<code>,"ms"?}` and carries none of the
outcome fields; `no_engine` adds one `"detail"` line (below). The handler never raises into Talon: a bug is `500 internal`.

The phone runs on Talon's main thread (`cron.after("0ms")`, the palette feed's `run_scheduled`),
because a command can drive UI and keys; a call that does not finish in 5 s answers `504`.

`cron.after` registers the job with the resource context of the _calling thread_, and a thread inherits
the context of whoever started it. A listener started by calling `start_listener()` from a REPL
statement therefore serves on workers whose context is freed when that statement ends, and every
request would raise `ResourceClosed` (this was the live `500 internal` on every utterance). `hop.py`
schedules inside the context the module is loaded under (`rctx.active()` at import), so the hop does not
depend on how the listener was started; if that context is freed (the module was reloaded and this is an
orphaned listener) the reply is `503 scheduler_unavailable`. Start the listener by touching
`phone_receiver_live.py` or restarting Talon, not from the REPL.

### Reply fields

A `200` tells the phone what Talon did with the utterance. The first six fields are the original
reply and are unchanged (`text` is now capped, see below); the rest were added and are always present on a `200`,
so a client that ignores them keeps working. Non-200 bodies are `{"ok":false,"error":<code>,"ms"?}`
only (plus `detail` on `no_engine`), so the phone treats `ok:false` as the error case.

#### `no_engine` detail

`503 no_engine` means the receiver found no engine it can drive. `detail` says which link is missing, and the
same text ends the `service refused: no_engine` log line. It names engines and attributes, never an exception
message or a payload.

| `detail`                                                                        | Meaning                                                                                                                                            |
| ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `speech_system.engine is None: no speech engine is active`                      | Talon has no active engine (still starting, or the engine was unloaded)                                                                            |
| `EngineProxy(...) wraps no engine`                                              | the proxy is there but holds nothing                                                                                                               |
| `<engine> cannot take injected audio: it has no lock, encoder, _on_audio_frame` | the active engine is not a W2l engine (a Dragon engine), or a W2l engine that lost its encoder (a private lab engine once its REPL statement ends) |
| `engine lookup raised <Class>`                                                  | looking the engine up threw; the log has `engine lookup failed: <Class>` and the frames                                                            |
| `engine lookup returned None`                                                   | a getter returned nothing                                                                                                                          |

| Field            | Type             | Meaning                                                                                                                                              |
| ---------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ok`             | `true`           | Always `true` on a `200`                                                                                                                             |
| `mode`           | string           | `emission` or `pcm`                                                                                                                                  |
| `text`           | string or null   | The words Talon decoded and dispatched, space-joined. `null` if no `phrase` event arrived within 0.5 s, or it could not be read. Capped, below       |
| `reject`         | bool or null     | The engine's own reject flag for that decode; `null` when `text` is `null`                                                                           |
| `ms`             | number           | Time inside the engine call (includes the up-to-0.5 s wait when no phrase arrives)                                                                   |
| `frames`         | int              | Encoder frames fed                                                                                                                                   |
| `status`         | string           | `ran`, `ignored` or `error` (below)                                                                                                                  |
| `why`            | string or null   | `null` when `status` is `ran`; otherwise the reason (below)                                                                                          |
| `kind`           | string           | `command`, `dictation` or `unknown` (below)                                                                                                          |
| `commands`       | int              | How many rules the phrase parsed into (`0` for `unknown`); a chained phrase like `page down page up` is `2`                                          |
| `total_ms`       | number           | Wall time from handing the utterance to Talon's main thread until the reply was built: includes the thread hop and any phrase wait, not network time |
| `text_truncated` | `true`, optional | Present only when `text` was cut to 512 characters                                                                                                   |

`status` and `why`:

| `status`  | `why`               | When                                                                                                       |
| --------- | ------------------- | ---------------------------------------------------------------------------------------------------------- |
| `ran`     | `null`              | Talon matched the phrase and dispatched it. A script that then raises is not visible on the `phrase` event |
| `ignored` | `no_phrase`         | The call ran but no `phrase` event arrived in 0.5 s (a locked macOS session drops them silently)           |
| `ignored` | `rejected`          | The engine rejected the decode (`reject` is `true`)                                                        |
| `ignored` | `empty`             | A `phrase` event with no words                                                                             |
| `ignored` | `asleep`            | Speech is off and only the free-text catch-all rule matched, so nothing ran                                |
| `ignored` | `no_match`          | The event had no `parsed` rules                                                                            |
| `error`   | `unreadable_phrase` | A `phrase` event arrived but was not shaped like one                                                       |

`kind` is read from the event's `parsed` list: `dictation` is the free-text catch-all rule (`<phrase>`,
the rule `skip_phrase_in_sleep` also keys on) matched alone; `command` is any other matched rule, which
includes prose rules in dictation mode, so `dictation` means "no command matched", not "text was typed";
`unknown` is no `parsed` list or no event.

How it is learned: only the `phrase` event the receiver's `PhraseTap` already registers on
`speech_system` (`phrase`, `parsed`, `_metadata.reject`), plus `actions.speech.enabled()` read inside that
same event for `asleep`. No new hook, grammar or voice command, nothing is written to
`~/.talon/recordings`, and neither audio nor the shared key reaches the reply or the log.

Size: every added field is a short enum, a count or a number, so a reply is about 150 bytes plus `text`.
`text` is cut to 512 characters (`text_truncated: true`); a normal utterance is far under that.

Example, `dictation mode` heard while awake: `{"ok":true,"mode":"emission","text":"dictation mode","reject":false,"ms":127.1,"frames":43,"status":"ran","why":null,"kind":"command","commands":1,"total_ms":128.4}`.
Example, free text while asleep: `{"ok":true,...,"text":"hello there","status":"ignored","why":"asleep","kind":"dictation","commands":1,...}`.

Not run live: the `parsed` list and `actions.speech.enabled()` were checked against the stubs and the
repo's own use of them (`plugin/subtitles/on_phrase.py`), not against the live engine; the live Talon was not touched.

**Could the palette feed carry this instead?** Only as a poll. `palette_feed/` (port 7399) has `GET /state`
and `POST /execute`, but no per-utterance result, and `/execute` runs a typed phrase through `_sim`,
not an injected emission. A "last utterance" endpoint would need a second connection, the feed's token
(a second credential) and a way to match each result to the request that caused it. The reply to the
same `POST /emission` is already correlated and costs no extra request, so it is the better carrier.

**On loopback, identity is a convention, not a credential.** `Tailscale-User-Login` is only set by
`tailscale serve`, which is not used here, so on the loopback bind any process on this Mac can POST
its own value; that is the same boundary the palette feed has. The `record_all` and body-validation
gates still apply. On the tailnet bind the identity header is ignored entirely.

### Failure log

Every failure the receiver contains becomes a status code, so the cause is written to Talon's log
(`print`, prefix `phone_listener:`) before the code goes back. A report is the exception class and one
`file:line in function` per frame (innermost 12, following `__cause__` up to 4 deep); the exception
message, source lines, locals, the key, phrase text and audio are never written, and a request is
described only by mode, byte count and elapsed ms. Ordinary traffic and caller mistakes (`4xx`) log nothing.

```
phone_listener: runner failed: RuntimeError (mode emission, 5360 bytes, 12.4 ms)
phone_listener: raised RuntimeError
phone_listener:   dispatch.py:48 in run_scheduled
```

| Line                                                     | Means                                                                                                                                    | Reply                       |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| `scheduler failed: SchedulerUnavailable`                 | the main-thread hop could not queue the job (the `from` lines name why, e.g. `ResourceClosed`)                                           | `503 scheduler_unavailable` |
| `runner failed: <Class>`                                 | the service raised on the main thread                                                                                                    | `500 internal`              |
| `handling at <stage> failed: <Class>`                    | policy code raised; stage is `auth`, `mode`, `read_body`, `validate` or `reply`                                                          | `500 internal`              |
| `engine feed failed: <Class>`                            | `_on_audio_frame` (or the encoder swap) raised, swallowed by `PhoneReceiver`                                                             | `500 engine_error`          |
| `live gate failed: <Class>`                              | the gate (`settings`, `speech_system.engine`, `heal`) raised                                                                             | `500 engine_error`          |
| `runner timed out`                                       | the main thread did not finish in 5 s; the command may still complete                                                                    | `504 timeout`               |
| `service refused: <code>`                                | `disabled`, `record_all_on`, `no_engine` or `engine_error` came back from the service (no exception); `no_engine` ends with `: <detail>` | `503` / `500`               |
| `request failed: <Class>` / `connection failed: <Class>` | the HTTP handler raised, or the reply could not be built or written                                                                      | `500 internal` / none       |

## Durable delivery (utterance ids)

If the reply to `POST /emission` is lost after the Mac ran the command, the phone sees only a timeout and
cannot tell "never arrived" from "ran". The phone names each utterance with an id, and the Mac remembers
what became of it, so a retry cannot run the command twice and the phone can ask what happened. It is
additive: a request without the header behaves exactly as before and carries none of the fields below.
Code: `trillium/phone_receiver/ledger.py` (the table), `ListenerApi._once` and `_result` in `listener.py`.

### Request: `X-Talon-Utterance-Id`

A UUID, or 16 to 64 hex digits with optional hyphens, either case. The Mac keys on the lower-case hex
with hyphens dropped, so `3F2A…` and `3f2a…` are one id. One id names one utterance: generate it once
(UUIDv4), keep it with the queued utterance, and send the same id on every retry of that utterance and
on no other. The id names the utterance, not its bytes: a replay is answered from the table even if the
body differs, and the same id covers an emission sent first and its PCM fallback sent after
(`emission` and `pcm` modes use one table). `POST /snippet` takes the same header and the same table
(`ListenerApi._once(id, run)`; see "Snippets"); do not reuse one id across endpoints.

A present but malformed header is `400 bad_utterance_id` and nothing runs, because the phone believes it
is protected against a double run. Only a missing header means "no id".

### Reply stamp

A reply to a request that carried an id and reached step 7a is stamped with four extra fields (also on
`409`, and on `500`/`503` replies from step 8). Errors from steps 1 to 7 (`403`, `415`, `429`, `413`,
`422`, ...) are not stamped, because the id was never claimed.

| Field       | Meaning                                                                                                                                      |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`        | The canonical key (lower-case hex, no hyphens)                                                                                               |
| `seq`       | Server sequence number of the execution attempt this reply describes: starts at 1, monotonic within one `instance`, shared by all ids        |
| `instance`  | 16 random hex digits, new every time the listener starts (Talon restart, module reload). The table lives and dies with it                    |
| `boot_time` | Epoch seconds when that instance started, for display. To compare times use `uptime_s` from `/result`, which is on the Mac's monotonic clock |

A phone that sees `instance` change knows every earlier id it holds was asked of a table that no longer
exists.

### Repeat of an id

| The id is...                                | Reply                                                                                                                                                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| new, or expired, or evicted                 | Runs as usual; the reply is stored and stamped                                                                                                                                              |
| finished (a final reply)                    | The stored status and body, with the response header `X-Talon-Replayed: 1`. **The executor is not called.** The stored body is exactly what the first answer said, so `seq` is the original |
| running right now (first request in flight) | `409 {"ok":false,"error":"in_progress","id":…,"seq":…,"instance":…,"boot_time":…}` + `Retry-After: 1`. The executor is not called. Query `/result/<id>` instead of re-posting               |
| finished with a retriable refusal (below)   | Runs again as a new attempt: new `seq`, `attempts` goes up, the reply replaces the stored one                                                                                               |

A replay still passes steps 1 to 7 first (auth, mode, content type, rate, length, a valid body), so it
costs the same rate-limit slot as the original and a retry must send a well-formed body. It needs no
engine and ignores the live gate: a finished id is answered even if the gate was switched off since.

### What is stored

Every reply the id reached step 7a with is stored, successes and failures alike, so a refused command
retried does not look like a new execution. The entry is the reply the phone was sent (the phrase `text`
is already capped at 512 characters) plus counters; no audio, request body or key is held.

| Outcome                                                                                   | Stored as     | The same id again                                                                               |
| ----------------------------------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------- |
| `200` (any `status`: `ran`, `ignored`, `error`)                                           | final         | replay                                                                                          |
| `504 timeout`                                                                             | final         | replay. The command may still complete on the main thread, so it is never run a second time     |
| `500 engine_error`, `500 internal`                                                        | final         | replay. The engine may have run partway; a runner that raises settles the id as `500 internal`  |
| `503 scheduler_unavailable`                                                               | **retriable** | runs again: the job was never queued, so the command did not run                                |
| `503 disabled`, `503 record_all_on`, `503 no_engine`                                      | **retriable** | runs again: the gate refused before anything ran (the switch may have been turned on since)     |
| a service-level `413` / `422` (the service refused the payload)                           | **retriable** | runs again: a phone that fixes its payload is not answered with the old refusal for ten minutes |
| refused at steps 1 to 7 (`403`, `415`, `429`, `400`, `411`, `413`, `422`, `503 bad_mode`) | not stored    | nothing ran and the id was never claimed; `/result` says `unknown`, which is true               |

The rule is "retriable only if the command provably did not run". When in doubt a reply is final. The
list lives in `listener._RETRIABLE_ERRORS` and `listener.retriable`; `GET /result/<id>` shows it as
`retriable`, so a phone does not need to know the list.

### TTL, cap and what "unknown" can mean

- An entry expires **10 minutes after it finishes** (`ledger.DEFAULT_TTL_S`; an abandoned in-flight entry
  expires 10 minutes after it started). At most **512** entries are held (`DEFAULT_MAX_ENTRIES`); past
  that the oldest finished entry goes first, and an entry in flight is never evicted.
- **Memory only.** A Talon restart or module reload empties the table and changes `instance`.
- `unknown` does not say why the id is missing. It covers four cases: the request never arrived; it
  arrived and was refused at steps 1 to 7; the entry expired or was evicted (the command may have run);
  or the Mac restarted (the command may have run). `uptime_s`, `ttl_s` and `horizon_s` in the `404` body
  let the phone separate the first from the rest (see the policy below). `horizon_s` is `ttl_s` unless
  the cap has evicted an entry younger than that, in which case it is how far back an unknown id still
  means "never received".

### `GET /result/<id>`

Asks the table what became of an id. It never touches the engine, the gate or the body.

| Step | Check                                                                                        | Failure                                 |
| ---- | -------------------------------------------------------------------------------------------- | --------------------------------------- |
| 1    | method is `GET`                                                                              | `405 method_not_allowed` + `Allow: GET` |
| 2    | auth, exactly as for `POST /emission`                                                        | `403 forbidden`                         |
| 3    | rate: 20 per second per server, apart from the POST limit so polling cannot 429 an utterance | `429 rate_limited` + `Retry-After`      |
| 4    | `<id>` is a usable id (query string ignored)                                                 | `400 bad_utterance_id`                  |

Auth and bind rules are the POST's: the tailnet bind needs `X-Talon-Phone-Key`, the loopback bind needs
an allowed `Tailscale-User-Login`; a refused request spends none of the rate limit. Any spelling of the
id finds its entry. Replies:

| Status | When             | Body                                                                                                                                              |
| ------ | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `200`  | finished         | `{"ok":true,"state":"done","id","seq","instance","boot_time","attempts","uptime_s","age_s","expires_in_s","http_status","retriable","reply":{…}}` |
| `202`  | running now      | the same without `http_status`, `retriable` and `reply`, and `state` is `"in_progress"`; `Retry-After: 1`                                         |
| `404`  | not in the table | `{"ok":false,"error":"unknown","instance","boot_time","uptime_s","ttl_s","horizon_s"}`                                                            |

| Field                | Meaning                                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `reply`              | The body the POST answered (or would have: it is the stored copy), stamp included; `http_status` is its status code |
| `retriable`          | `true` if the stored reply is a refusal under which nothing ran, so the same id may be POSTed again                 |
| `attempts`           | Executions begun under this id: `1`, or more after retriable refusals                                               |
| `uptime_s`           | Seconds since this `instance` started (monotonic)                                                                   |
| `age_s`              | Seconds since the id was first received                                                                             |
| `expires_in_s`       | Seconds until the entry is dropped                                                                                  |
| `ttl_s`, `horizon_s` | `404` only: the table's TTL, and how far back an unknown id still means "never received"                            |

Example, after a lost reply: `GET /result/3f2a…` → `200 {"ok":true,"state":"done","id":"3f2a…","seq":7,"instance":"9c1e…","boot_time":1792500000.123,"attempts":1,"uptime_s":412.8,"age_s":3.2,"expires_in_s":596.8,"http_status":200,"retriable":false,"reply":{"ok":true,"mode":"emission","text":"page down",…,"id":"3f2a…","seq":7,"instance":"9c1e…","boot_time":1792500000.123}}`.

### Phone client contract

Use one id per utterance and follow this policy; the Mac side does not retry anything itself.

1. Generate the id and store it with the queued utterance **before** the first send. Note the phone's
   monotonic time of the first send.
2. `POST /emission` with the id. On a `200` stop: show `text`, `status` and `why`. On a final error
   (`500`, `504`) stop and show it: the command may have run.
3. After a timeout or a dropped connection, **do not POST again. Query `GET /result/<id>` first**, then
   act on the answer (table below).
4. Back off exponentially between attempts of either request: 0.5 s, 1 s, 2 s, 4 s, ... capped at 30 s,
   with jitter, and never less than a `Retry-After` the Mac sent. A `409 in_progress` on a POST means
   the first request is still running: poll `/result/<id>` (`202` until it finishes), do not re-post.
5. Stop automatic attempts once more than 10 minutes (`ttl_s`; the smaller `horizon_s` once a `404` has
   reported one) have passed since the first send: after that a replay can no longer be served. Show the
   state, offer a manual resend.

| `GET /result/<id>` says                                                                                                            | What happened                                                                                  | The phone does                                                                                                                       |
| ---------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `200`, `retriable: false`                                                                                                          | It finished (ran, or failed finally); the reply is stored                                      | Show `reply`. Do not POST again                                                                                                      |
| `200`, `retriable: true`                                                                                                           | The Mac refused it and nothing ran                                                             | Show the refusal (`reply.error`); POST again with **the same id** after backoff, once the cause is fixed or if it may be transient   |
| `202`                                                                                                                              | Still running on the Mac                                                                       | Poll again after `Retry-After`; do not POST                                                                                          |
| `404` and the first send was within `horizon_s` and `uptime_s` is at least the time since the first send (allow a second of slack) | The Mac was up the whole time and holds nothing, so **the request never reached the executor** | Safe to POST again, **same id**, after backoff. The Mac will run it once                                                             |
| `404` and `uptime_s` is less than the time since the first send, or `instance` differs from the one the phone last saw             | The Mac restarted since the first send; the table that would have known is gone                | **Unknown, and say so.** The command may or may not have run. Do not resend automatically; offer the user a manual resend (a new id) |
| `404` and the first send was more than `horizon_s` ago                                                                             | The entry may have expired or been evicted; the command may have run                           | **Unknown, and say so.** Do not resend automatically; offer a manual resend (a new id)                                               |
| `403`, `429`, no answer                                                                                                            | A key problem, rate limit, or the Mac is unreachable                                           | Keep the id. `403`: fix the key. Otherwise retry `/result/<id>` with backoff                                                         |

Only the first `404` row resends automatically, and only because `uptime_s` and `horizon_s` prove the
Mac would have remembered the id. The other two rows do not guess: an unknown that could hide a run is
shown as unknown. (A `404` is therefore not "never ran": that is a stricter reading than "never seen or
expired" would give, on purpose, so a restart or an expiry never turns into a silent second run.)

## Tailnet bind

Set `user.phone_receiver_bind` to the Mac's tailnet address (`tailscale ip -4`) and
`user.phone_receiver_enabled = 1`, then touch `phone_receiver_live.py` (or restart Talon). The phone
posts to `http://<that address>:7403/emission`.

- **Bind check.** The value must be exactly `127.0.0.1`, or an IPv4 address in `100.64.0.0/10` that
  `tailscale ip -4` reports for this Mac. `0.0.0.0`, `::`, LAN addresses, hostnames, other nodes'
  tailnet addresses and anything unparsable are refused, the listener does not start, and Talon logs
  `phone_listener: not started: ...`. The socket is bound to that one address, never a wildcard. If
  Tailscale is down at Talon start the check fails closed; reload the file after it is up.
- **Shared secret.** Requests need `X-Talon-Phone-Key: <key>`, compared in constant time; missing or
  wrong is `403 forbidden` before any body is read. The key is read from
  `~/.config/talon-phone/key` (mode 0600, owned by you, a regular file, not a symlink, outside any git
  repo, at least 32 characters; otherwise the listener does not start). If the file is missing it is
  generated (`secrets.token_urlsafe(32)`, directory 0700) when the listener starts, or earlier with
  `python -m trillium.phone_receiver.keyfile`, which prints only the path. The key is never printed,
  logged, returned in a response or committed. To pair the phone, copy it yourself, e.g.
  `pbcopy < ~/.config/talon-phone/key`. To rotate: delete the file, reload, re-pair. It is read once
  at listener start.
- **Unchanged.** The 64 KiB body cap, the Python validation in `wire`, the rate limit, `record_all`
  refusal and the default-off switch all apply on both binds. The tailnet bind is still default off:
  `user.phone_receiver_enabled` defaults to `false` and `user.phone_receiver_bind` to `127.0.0.1`.

Checked 2026-10-19 on the real tailnet address (fake engine, no Talon, key file in a temp dir):
`0.0.0.0`, a LAN address and an unassigned tailnet address were refused; the socket bound only to the
assigned address (loopback refused connections); right key `200`, no key and wrong key `403`, a 70000-byte
body `413 body_too_large`, a malformed body `422 short_header`; key file mode `0600`.

**Plain HTTP, and what that costs.** There is no TLS. The tailnet is WireGuard-encrypted between
nodes, so the key and the utterance are not readable in transit between your devices, and nothing is
published beyond the tailnet (no Funnel, no `tailscale serve`). That is weaker than the earlier
`tailscale serve` plan in three ways, which you accept by using this bind:

1. The shared key is the only credential. `tailscale serve` added a per-user identity header that the
   tailnet vouched for; here any device on your tailnet that learns the key can drive Talon, and a
   tailnet ACL is what limits which devices can reach port 7403 at all.
2. The key is a bearer secret in a request header. Anything that can read the phone's stored key or
   the Mac's key file has it; there is no per-request signature and no replay protection beyond the
   rate limit.
3. A valid request injects a spoken command that Talon will run, so a leaked key is remote command
   execution as the logged-in user, limited only by what Talon's grammar can do. Treat the key like
   an SSH key: 0600 file, never in a repo or chat, rotate if in doubt.

iOS may refuse cleartext HTTP to an IP address unless the app declares an ATS exception for it; that
is a phone-side setting and this repo does not touch it.

## PCM fallback (seam c)

With `user.phone_receiver_mode = "pcm"` the same endpoint wants
`Content-Type: audio/L16; rate=16000; channels=1` (raw little-endian int16, 16 kHz mono) and optional
`X-Utterance-Ts: <seconds>` (default: now). The Mac hands the samples to `engine._on_audio_frame(pcm,
ts, pad=True)` with the engine's own encoder, so frontend and acoustic model run locally and nothing
is swapped. Anything the engine does after that (decode, reject, `phrase`) is the same code as the
emission path. `emission` mode refuses PCM and `pcm` mode refuses TPE1 with `415`.

`X-Talon-Utterance-Id` works in `pcm` mode exactly as in `emission` mode ("Durable delivery"), and the id
names the utterance, not the mode: if an emission landed and the phone then falls back to PCM with the
same id, the answer is the replay of the emission's reply and nothing runs twice.

Limits: 1600 samples minimum (100 ms), and the 64 KiB cap means **at most 32768 samples, about 2.05
s of audio**, so a longer utterance answers `413`. The cap is the brief's hard limit; raise
`wire.MAX_PAYLOAD_BYTES` for PCM only if longer fallback utterances are needed. `record_all` refuses
PCM too, since it would write the phone's real audio to `~/.talon/recordings`.

## Snippets (`POST /snippet`)

The phone uploads a short recording (a FLAC or WAV, 16 kHz mono 16-bit, 0.1 to 30 s) and the Mac
saves it as a new file in Talon's own recordings folder. It is off until
`user.phone_receiver_snippets_enabled` is on (default `false`; the listener switch
`user.phone_receiver_enabled` must be on too). Off answers `503 snippets_disabled`. The receiver
never enables `speech.record_all` or changes any other Talon setting.

**The one write.** The folder is `actions.path.talon_home() / "recordings"`, the place Talon's own
`speech.record_all` writes, taken from Talon at call time and never hard-coded. `RecordingsWriter`
only creates new files there. It never lists the folder, opens, reads, copies, moves, renames or
deletes an existing entry (the sole thing it removes is its own `.phone-snippet-*.tmp`), never
overwrites, and never creates the folder: if it is missing or unwritable the reply is `503
no_recordings_dir`. A write is: temp file (`O_EXCL`), write, `fsync`, hard link to the final name (which
fails if the name exists, so a collision draws a new random name and the other file is untouched),
unlink the temp, `fsync` the folder, `stat` the size. The ack is built only after that.

**Name.** Talon's recordings are `<phrase>-<8 letters or digits>.flac`. A snippet is
`phone-snippet-<8 letters or digits>.flac`. A spoken phrase is words separated by spaces and never
holds a hyphen, so the fixed `phone-snippet` cannot be a real command and the files are told apart by
name alone (anything that derives a command name from the filename gets `phone-snippet`). No subfolder
fallback was needed. Mode `0644`.

Request, after the same auth, rate, content-length and cap rules as `/emission`:

| Item                     | Rule                                                                                                                                                                          |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Path, method             | `POST /snippet`; `405` otherwise; `404` if the listener has no snippet service                                                                                                |
| Auth                     | Identical to `/emission`: `X-Talon-Phone-Key` on the tailnet bind, `Tailscale-User-Login` allow-list on loopback; `403 forbidden` before any body is read                     |
| `Content-Type`           | `audio/flac` (or `audio/x-flac`) stored byte for byte; `audio/wav` (or `x-wav`, `wave`, `vnd.wave`) is converted to FLAC. Else `415` with `want`                              |
| `Content-Length`         | Required, no chunked. **Cap 1 MiB (1,048,576 bytes)**, against 64 KiB for `/emission`; 30 s of WAV is 960,044 bytes. Over it is `413` and nothing is read                     |
| Rate                     | 4 per second per server, counted apart from `/emission` and `/metrics`; `429` + `Retry-After`. A retry of a saved upload still spends one                                     |
| `X-Talon-Utterance-Id`   | **Required**, and the same header, alphabet and table as `/emission` (see "Durable delivery"): a UUID or 16 to 64 hex digits. `400 missing_utterance_id` / `bad_utterance_id` |
| `X-Talon-Sample-Rate`    | Optional, an integer. Must equal the audio's own rate (16000), else `422 sample_rate_mismatch`. The rate is also read from the audio header                                   |
| `X-Talon-Content-Sha256` | Optional, 64 hex digits of the request body. A mismatch is `422 checksum_mismatch` and nothing is written                                                                     |
| `X-Talon-Client-Rtt-Ms`  | Optional, see "Client round trip" below                                                                                                                                       |

Validation is of headers against the body's own length, not a decode (`audio.py`): FLAC needs
`fLaC`, a STREAMINFO of 16 kHz, 1 channel, 16 bits and a non-zero total sample count, a frame sync after
the metadata, and a frame-data size between 8 bytes a block and the verbatim bound for that many samples. WAV
needs `RIFF/WAVE`, a PCM `fmt ` before `data`, a finalized `data` size that fits the body and is whole
samples. Anything else is `422` with one of `not_flac`, `not_wav`, `bad_streaminfo`, `bad_wav`,
`bad_sample_rate`, `bad_channels`, `bad_bit_depth`, `unsupported_wav_format`, `unfinalized_audio`,
`truncated_audio`, `length_mismatch`, `no_audio_frames`, `too_short`, `too_long`, `bad_audio`.
A failed validation writes nothing and does not spend the id.

**Ack.** `200` with:

| Field                                | Meaning                                                                            |
| ------------------------------------ | ---------------------------------------------------------------------------------- |
| `ok`                                 | `true`                                                                             |
| `id`                                 | The canonical key of the `X-Talon-Utterance-Id` sent (lower-case hex, no hyphens)  |
| `name`                               | Basename of the saved file (never a directory), e.g. `phone-snippet-aB3dE9fG.flac` |
| `received_bytes`, `received_sha256`  | Length and SHA-256 of the body the phone sent                                      |
| `stored_bytes`, `stored_sha256`      | Length and SHA-256 of the file on disk (equal to the received ones for a FLAC)     |
| `container`, `converted`             | What was sent (`flac` / `wav`) and whether it was converted to FLAC to store       |
| `sample_rate`, `channels`, `seconds` | From the audio header                                                              |
| `duplicate`                          | `false` the first time, `true` for a replay                                        |

A reply that went through the id table also carries the stamp fields (`seq`, `instance`,
`boot_time`; see "Reply stamp").

**The phone deletes its copy only on a verified ack:** status `200`, `ok` true, `id` equal to its
own id (compare canonical keys), and `received_sha256` / `received_bytes` equal to the SHA-256 and length of what it sent. An
error, a timeout or a mismatch means keep the audio and retry with the same id.

**Idempotency, in two layers.** The id is the one `/emission` uses and goes through the same memory
table, so the rules of "Repeat of an id" apply: an id in flight is `409 in_progress` + `Retry-After: 1`;
a finished one is answered from the table with `X-Talon-Replayed: 1` and `duplicate: true`; `GET
/result/<id>` works. Two differences: the replay checks the bytes (the same id with different bytes is
`409 id_conflict`, not the old ack), and a snippet has more retriable refusals (nothing was saved): a
`422` validation error, `snippets_disabled`, `no_recordings_dir`, `wav_unavailable`, `id_conflict`,
`ledger_write_failed`, `save_failed`, `encode_failed` and the two bad-header codes
(`snippet.RETRIABLE_ERRORS`).

Behind it is the **file-ack table**, `~/.config/talon-phone/snippets.jsonl` (next to the key; directory
0700, file 0600; ids, basenames, sizes, checksums only; code in `snippet_ledger.py`), appended and
`fsync`ed before the ack leaves. The memory table forgets after ten minutes or a restart; this one does
not, so a retry any time later still gets the stored ack (`duplicate: true`, nothing written) instead of a
second file. It keeps the last 10,000 ids; an older id would be saved again. `GET /result/<id>` falls back
to it when the memory table does not hold the id: `200` with `"stored": true` and the original ack in
`reply` (no `seq`, `attempts` or `age_s`). A `404` for a snippet id therefore means neither table holds a
finished ack for it. Check, save and entry are one step under a lock, so two requests with one id at once
write one file.

**A crash between the file landing and the ack saves it once.** Before the write, a _pending_ entry
naming the reserved file goes into the table (if that cannot be written, nothing is saved:
`500 ledger_write_failed`). If the process dies, or the folder fsync fails, after the file landed, the
retry finds the pending entry, `confirm`s the file (one `stat` of that exact name plus a folder fsync; the
file is not opened or read) and acks it as a duplicate. If the file is not there, it is saved afresh.
Remaining hole: a name collision (one in 62^8) followed by a crash.

**WAV to FLAC** uses `talon.lib.flac.encode(samples, sample_rate=16000, channels=1)`, the same call Talon
records with; without the library a WAV is `503 wav_unavailable` and a FLAC upload still works. Not yet
verified live: the exact float scale and a decoded round trip of the converted file. A FLAC upload involves
no conversion.

Other errors: `500 save_failed`, `500 encode_failed`, `500 ledger_write_failed`, `503 no_recordings_dir`. Log lines name the
class and `file:line` only (see "Failure log"); never the id, name, bytes or audio.

## Noises (`POST /noise`)

The phone runs Parrot on-device and sends one JSON event per detected sound. The Mac runs the
trigger scripts Talon registered for `parrot(<name>)`: the last impl in
`talon.registry.impls.parrot_noises[<key>]`, through `actions.core.run_talon_script`, on the main
thread in the module's context. The captain's own `.talon` triggers, their tag and mode gating and
every `user.noise_*` override therefore apply unchanged; this adds no grammar. (Design: the
2026-10-19 parrot spike, level L2.) It is gated by `user.phone_receiver_enabled` and refused with
`503 record_all_on` while `speech.record_all` is on, like `/emission`.

| Item        | Rule                                                                                                                               |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Request     | `POST /noise`, `Content-Type: application/json`, `Content-Length` required, body at most 1 KiB (`413` above)                      |
| Auth        | As `/emission`: `X-Talon-Phone-Key` on the tailnet bind, `Tailscale-User-Login` allow-list on loopback                              |
| Id          | `X-Talon-Utterance-Id` **required** (`400 missing_utterance_id`); same table as `/emission`: a repeat replays the stored reply and never runs the trigger again |
| Rate        | its own bucket, 20 per second per server (`429 rate_limited`), apart from `/emission`'s                                            |
| Body        | `{v:1, name, edge, power, prob, ts, session, seq}`; `name` is `[A-Za-z0-9][A-Za-z0-9_-]*`, at most 32 chars; `edge` is `start` (default), `repeat` or `stop` and picks the registry key `name`, `name:repeat`, `name:stop`; `prob` is 0 to 1; numbers must be finite |
| Errors      | `400 bad_json`; `422 bad_version, bad_name, bad_edge, bad_session, bad_seq, bad_field, non_finite`; `503 disabled, record_all_on, registry_error, scheduler_unavailable`; `504 timeout` |

Reply: `200 {"ok":true,"name","edge","status":"ran|ignored|error","why","commands","ms","total_ms"}` plus
the ledger stamp. `ran` means the last impl was handed to `run_talon_script` (`commands: 1`; a script
that then raises is logged by Talon, not visible here). `ignored` carries `why`: `no_trigger` (no
impl for that key: an unknown name, or a gated trigger such as an inactive `user.parrot_on` tag),
`stale_seq` (a `start` whose `seq` is not above the last `start` for that `(session, name)`; the
state is bounded to 256 entries) or `throttled` (a `start` for the same name within 30 ms of the last
one that ran). The phone applies the real `patterns.json` throttles. `error` / `dispatch_failed`
means looking up or running the impl raised (the log line and `detail` hold the exception class only).
A refusal where nothing ran (`disabled`, `record_all_on`, `registry_error`, `scheduler_unavailable`)
leaves the id usable. `GET /result/<id>` answers a lost reply. The body is never logged; the key
never is.

## Metrics (`GET /metrics`)

Key-authenticated like the rest (`403` without it), `GET` only, 5 per second per server. Returns counts and
timings and nothing else: no phrase, id, filename, audio or key can reach it (`Sample` has a kind, a
status, five numbers and two byte counts).

Every `/emission`, `/snippet` and `/noise` request that passes routing becomes one sample, whatever its status, and its
response carries `X-Talon-Server-Ms` (the handler total). Reading `/metrics` is not a sample.

| Timing (ms, on the Mac)   | Covers                                                                                                                        |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `receive_ms`              | handler start (headers parsed) to the body read in full                                                                       |
| `decode_ms`               | validation (emission: `wire.parse_validate`; snippet: audio checks plus WAV to FLAC). Absent if refused earlier               |
| `dispatch_ms`             | emission: main-thread hop and engine call; snippet: write, fsync, link, folder fsync and the table append                     |
| `total_ms`                | handler start to the response built. The socket write and the network are not in it                                           |
| `req_bytes`, `resp_bytes` | Body bytes read (0 if refused before the body, or if the body came up short) and the JSON bytes sent. Headers are not counted |

Response shape (`emission`, `snippet` and `noise` each hold the same two blocks):

```
{"ok": true, "generated_at": "...Z", "window": 500, "client_rtt_rejected": 0,
 "emission": {"last_n": STATS, "hours": [{"hour": "2026-10-20T14:00:00Z", ...STATS}], "client_rtt_ms": {...}},
 "snippet":  {...}, "noise": {...}}
STATS = {"n", "ok", "by_status": {"200": 41, "403": 2}, "bytes_in", "bytes_out",
         "receive_ms": {"p50","p95"}, "decode_ms": {...}, "dispatch_ms": {...}, "total_ms": {...},
         "req_bytes": {...}, "resp_bytes": {...}}
```

`last_n` is the newest 500 requests of that kind; `hours` is one block per UTC hour (up to 24, oldest first)
over the last 20,000 samples kept. Percentiles are **nearest-rank** (the value at rank `ceil(p/100 * n)`, always an
observed value) and use the `200` responses only, because a `403` or `429` is answered in microseconds and
would drag p50 down; `by_status`, `n`, `bytes_in` and `bytes_out` count every response. A number with no
data is `null`. The window is in memory and starts empty when Talon reloads the module.

**Log line.** Every 5 minutes, if there were any requests since the last line, Talon's log gets one line (the
`phone_listener:` prefix, no ids or text):

```
phone_listener: metrics: emission 4 req (200:3 429:1) total p50 20.0 p95 30.0 ms, in 300 B out 180 B | snippet 1 req (200:1) total p50 80.0 p95 80.0 ms, in 5000 B out 300 B
```

**Client round trip.** The server cannot see network time, so the phone measures its own (request sent to
response received, for a request that already completed) and sends it on its **next** authenticated
request to `/emission`, `/snippet` or `/noise`:

| Header                    | Value                                                                                                                   |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `X-Talon-Client-Rtt-Ms`   | Milliseconds, a decimal from 0 to 600,000                                                                               |
| `X-Talon-Client-Rtt-Kind` | Optional: `emission`, `snippet` or `noise`, which request kind was measured; default the kind of the request carrying the header |

Kept and summarised under `client_rtt_ms` (`last_n` and `hours`, each `{n, p50, p95}`). Subtract the matching
`X-Talon-Server-Ms` to get the network share. A value that is not a number in range, or an unknown kind, is
counted in `client_rtt_rejected` and never fails the request. The header is read only after auth.

## Parity harness

`parity.run_parity(post, set_mode, utterances, emit)` posts each utterance twice through the same
`ListenerApi`, flipping only the mode, and compares `(ok, text, reject)`. `emit(samples)` is the
phone's acoustic model; the PCM path receives the same int16-quantized samples. `Report.identical`
is false for an empty set or any difference, and `Report.format()` prints one line per utterance.

- `python -m pytest .tests/test_phone_snippet.py .tests/test_phone_metrics.py`: audio parsing (synthetic and, where installed, real `flac` / `afconvert` / `sox` output), the recordings writer (atomic, no overwrite, collisions, never lists or reads the folder), the id table, the service, the HTTP rules (auth, caps, rate, content types), the metrics maths and the `/metrics` endpoint. Every folder is a pytest temp dir; no Talon, no key.
- `python -m pytest .tests/test_phone_listener.py`: policy, malformed bodies, oversize, identity, shared-key
  auth (wrong, missing, wrong header), bind refusals, key file, content type, real loopback socket, and the harness against a fake engine (including that it flags a phone
  model that disagrees).
- `python -m pytest .tests/test_phone_ledger.py`: the id protocol with fake engines and a fake clock: id
  parsing, dedupe and replay, a duplicate never reaching the executor (also under 10 concurrent POSTs),
  in-flight `409`, retriable vs final refusals, TTL expiry and the cap, restart (`instance` change),
  `GET /result/<id>` shapes, auth and rate limit, body cap, the no-id path unchanged, and the lost-reply
  story and PCM fallback over a real loopback socket.
- `.tests/lab/phone_listener_lab.py`: same harness on a private `W2lEngine` in the Talon REPL, using the
  engine's own emission as the phone's. It loads this checkout's modules under a private `phlab` name,
  because a bare `trillium.*` import in Talon's REPL resolves to the live checkout. Run it as the receiver lab, with `PHONE_LAB_REPO` set as a REPL variable
  (it wins over any `PHONE_LAB_REPO` env var already in Talon's environment):

  ```
  printf '%s\n' "exec(\"PHONE_LAB_REPO='$PWD'\nPHONE_LAB_DIR='/path/to/wavs'\nexec(open('$PWD/.tests/lab/phone_listener_lab.py').read())\")" | ~/.talon/bin/repl
  ```

  Last run (2026-10-19): 22 `say` utterances, `22/22 identical` for fp32 and for fp16 emissions;
  one request of each kind over a real loopback socket returned `page down` (emission 6.9 ms, PCM 39 ms);
  9 malformed bodies (6 emission, 3 PCM) accepted 0 times with 0 decoder calls; the engine kept serving and
  its encoder was restored.

Not run live: the listener was not installed in the live Talon (`~/.talon/user/trillium_talon`), so the
live `phrase` event's shape through `speech_system.register` and the main-thread hop are covered by
the lab (private engine) and the stub tests only. See the live test notes above for how to do it with
`speech.record_all = 0` and `user.command_logger_enabled = 0`.
