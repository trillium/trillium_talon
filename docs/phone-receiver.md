# Phone receiver (work items 1, 2, 4 Mac side and 5)

Accepts a phone-computed acoustic emission (`TPE1`) and runs it through a `W2lEngine`'s own
padding, decode, rejection and `phrase` dispatch, replacing only the encoder call. Code:
`trillium/phone_receiver/`. The decoder path opens no socket and registers nothing with `speech_system`. Work item 2 wires it to the
live engine behind `user.phone_receiver_enabled` (default off); see "Live install" below. Work items 4 (Mac side) and 5
add a loopback HTTP listener and a PCM fallback on the same switch; see "Listener" below.

| File                     | Role                                                                                                                                                                                                                                     |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `wire.py`                | `parse_validate` / `validate_array` / `pack` / `frames_for`; every check runs before native code, failures are `WireError(code)`                                                                                                         |
| `encoder.py`             | `PhoneEncoder`: bounded queue, `forward()` returns `(1, 1, T, 29)`                                                                                                                                                                       |
| `live.py`                | `LiveInstall(get_engine, is_enabled, record_all).handle(bytes)`: the gate, in plain Python. Refuses `disabled`, `record_all_on`, `no_engine`; otherwise `PhoneReceiver.handle`. `heal()` restores the mic encoder if it was left swapped |
| `phone_receiver_live.py` | Talon glue: declares `user.phone_receiver_enabled` (bool, default false) and the action `user.phone_receiver_handle(payload: bytes) -> str` (`"ok"` or an error code). No voice commands, no socket                                      |
| `service.py`             | `PhoneService`: one call per utterance, returns `Reply(ok, error, text, reject, ms)`. `PhraseTap` is the `phrase` listener it captures the call's own phrase with                                                                        |
| `listener.py`            | `ListenerApi` (the whole HTTP policy, pure) and a loopback-only worker-pool server for `POST /emission`                                                                                                                                  |
| `parity.py`              | Parity harness: both paths on the same audio through `ListenerApi`, phrase output diffed                                                                                                                                                 |
| `receiver.py`            | `PhoneReceiver(engine).handle(bytes) -> Result`: validate, then under `engine.lock` swap encoder, queue, `_on_audio_frame([0.0]*n_pcm, ts, pad=True)`, restore encoder. Never raises                                                     |

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

`POST /emission`, one utterance per request, on **`127.0.0.1:7403`** (checked free with `lsof`;
the palette feed holds 7399/7401). `listener.start` refuses any non-loopback host. The only way in
from the network is a `tailscale serve` mapping, which does not exist yet (see below).

The server starts only when `user.phone_receiver_enabled` is on at Talon's `ready` (or at a module
reload: touch `phone_receiver_live.py`); with it off no socket is opened. The gate is also checked
per request, so turning it off later answers `503 disabled` until the next reload stops the socket.

| Setting                              | Default    | Meaning                                                                                                         |
| ------------------------------------ | ---------- | --------------------------------------------------------------------------------------------------------------- |
| `user.phone_receiver_enabled`        | `false`    | Existing gate; also decides whether the listener starts                                                         |
| `user.phone_receiver_allowed_logins` | `""`       | Comma or space separated `Tailscale-User-Login` values. Empty denies everyone; `*` is a literal, not a wildcard |
| `user.phone_receiver_mode`           | `emission` | `emission` (TPE1 body) or `pcm` (PCM16 body). Read per request, so flipping it needs no reload                  |

Declare them in a `.talon` `settings():` block, e.g. `user.phone_receiver_allowed_logins = "trillium@example.com"`
(the repo's `settings.talon` does not set any; the default is closed).

Request: `Content-Type` per mode, `Content-Length` required, body at most 65536 bytes. Checks run
in this order and stop at the first failure, before the body is read until step 5:

| Step | Check                                            | Failure                                                                                 |
| ---- | ------------------------------------------------ | --------------------------------------------------------------------------------------- |
| 1    | path is `/emission`, method is `POST`            | `404 not_found`, `405 method_not_allowed`                                               |
| 2    | `Tailscale-User-Login` is in the allow-list      | `403 forbidden` (missing, wrong and empty-list are indistinguishable)                   |
| 3    | mode is `emission` or `pcm`; content type        | `503 bad_mode`; `415 unsupported_media_type` (names the type wanted)                    |
| 4    | rate: 10 per second per server                   | `429 rate_limited` + `Retry-After`                                                      |
| 5    | `Content-Length` present, not chunked, <= 64 KiB | `411 length_required`, `400 bad_content_length`, `413 body_too_large` (nothing read)    |
| 6    | body read in full                                | `400 truncated_body`                                                                    |
| 7    | `wire.parse_validate` / `wire.parse_pcm`         | `422 <wire code>` (`bad_magic`, `frame_mismatch`, `non_finite`, `pcm_odd_length`, ...)  |
| 8    | live gate                                        | `503 disabled`, `503 record_all_on`, `503 no_engine`; `500 engine_error`; `504 timeout` |

Success: `200 {"ok":true,"mode":"emission","text":"page down","reject":false,"ms":6.9,"frames":43}`.
`text` is the dispatched phrase's words; it is `null` if no phrase event arrived within 0.5 s of the
call (the call still ran). `ms` is the time inside the engine call, not network time. Every error is
`{"ok":false,"error":<code>,"ms"?}`. The handler never raises into Talon: a bug is `500 internal`.

The phone runs on Talon's main thread (`cron.after("0ms")`, the palette feed's `run_scheduled`),
because a command can drive UI and keys; a call that does not finish in 5 s answers `504`.

**Identity is a convention, not a credential.** The socket is loopback only, and `tailscale serve`
sets `Tailscale-User-Login` itself on requests that arrive over the tailnet. Any process on this
Mac can POST its own value, which is the same boundary the palette feed has. The `record_all` and
body-validation gates still apply.

## PCM fallback (seam c)

With `user.phone_receiver_mode = "pcm"` the same endpoint wants
`Content-Type: audio/L16; rate=16000; channels=1` (raw little-endian int16, 16 kHz mono) and optional
`X-Utterance-Ts: <seconds>` (default: now). The Mac hands the samples to `engine._on_audio_frame(pcm,
ts, pad=True)` with the engine's own encoder, so frontend and acoustic model run locally and nothing
is swapped. Anything the engine does after that (decode, reject, `phrase`) is the same code as the
emission path. `emission` mode refuses PCM and `pcm` mode refuses TPE1 with `415`.

Limits: 1600 samples minimum (100 ms), and the 64 KiB cap means **at most 32768 samples, about 2.05
s of audio**, so a longer utterance answers `413`. The cap is the brief's hard limit; raise
`wire.MAX_PAYLOAD_BYTES` for PCM only if longer fallback utterances are needed. `record_all` refuses
PCM too, since it would write the phone's real audio to `~/.talon/recordings`.

## Parity harness

`parity.run_parity(post, set_mode, utterances, emit)` posts each utterance twice through the same
`ListenerApi`, flipping only the mode, and compares `(ok, text, reject)`. `emit(samples)` is the
phone's acoustic model; the PCM path receives the same int16-quantized samples. `Report.identical`
is false for an empty set or any difference, and `Report.format()` prints one line per utterance.

- `python -m pytest .tests/test_phone_listener.py`: policy, malformed bodies, oversize, identity, content
  type, real loopback socket, and the harness against a fake engine (including that it flags a phone
  model that disagrees).
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

## Tailscale serve (captain approval pending: NOT created)

No `tailscale serve` mapping was created or changed. When approved, the captain runs:

```
tailscale serve --bg --https=7403 http://127.0.0.1:7403
```

That publishes `https://macbook.hippo-tilapia.ts.net:7403/emission` to the tailnet only (not Funnel),
terminates TLS (so iOS needs no ATS exception), and adds `Tailscale-User-Login` for the calling
user. To remove it: `tailscale serve --https=7403 off`. Check `tailscale serve status` first: other
mappings already use ports 4173, 4175, 4242 and 11434, and `7403` is unused.
