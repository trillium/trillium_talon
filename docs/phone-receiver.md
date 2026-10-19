# Phone receiver (work item 1, private lab engine only)

Accepts a phone-computed acoustic emission (`TPE1`) and runs it through a `W2lEngine`'s own
padding, decode, rejection and `phrase` dispatch, replacing only the encoder call. Code:
`trillium/phone_receiver/`. Nothing here opens a socket, registers with `speech_system`,
or changes a setting; wiring it to the live engine is a later, separate step (default off).

| File          | Role                                                                                                                                                                                 |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `wire.py`     | `parse_validate` / `validate_array` / `pack` / `frames_for`; every check runs before native code, failures are `WireError(code)`                                                     |
| `encoder.py`  | `PhoneEncoder`: bounded queue, `forward()` returns `(1, 1, T, 29)`                                                                                                                   |
| `receiver.py` | `PhoneReceiver(engine).handle(bytes) -> Result`: validate, then under `engine.lock` swap encoder, queue, `_on_audio_frame([0.0]*n_pcm, ts, pad=True)`, restore encoder. Never raises |

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
