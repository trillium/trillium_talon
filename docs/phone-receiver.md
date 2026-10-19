# Phone receiver (work items 1 and 2)

Accepts a phone-computed acoustic emission (`TPE1`) and runs it through a `W2lEngine`'s own
padding, decode, rejection and `phrase` dispatch, replacing only the encoder call. Code:
`trillium/phone_receiver/`. Nothing here opens a socket or registers with `speech_system`. Work item 2 wires it to the
live engine behind `user.phone_receiver_enabled` (default off); see "Live install" below.

| File                     | Role                                                                                                                                                                                                                                     |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `wire.py`                | `parse_validate` / `validate_array` / `pack` / `frames_for`; every check runs before native code, failures are `WireError(code)`                                                                                                         |
| `encoder.py`             | `PhoneEncoder`: bounded queue, `forward()` returns `(1, 1, T, 29)`                                                                                                                                                                       |
| `live.py`                | `LiveInstall(get_engine, is_enabled, record_all).handle(bytes)`: the gate, in plain Python. Refuses `disabled`, `record_all_on`, `no_engine`; otherwise `PhoneReceiver.handle`. `heal()` restores the mic encoder if it was left swapped |
| `phone_receiver_live.py` | Talon glue: declares `user.phone_receiver_enabled` (bool, default false) and the action `user.phone_receiver_handle(payload: bytes) -> str` (`"ok"` or an error code). No voice commands, no socket                                      |
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
