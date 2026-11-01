# Parrot clips: keep the sounds the model missed

Code: `trillium/plugin/parrot/parrot_clips.py` (logic, no Talon imports), `parrot_clips_talon.py` (settings + actions),
`parrot_clips.talon` (voice), hooks in `parrot_integration.py`. Tests: `.tests/test_parrot_clips.py`.

## What it does

- **RAM only.** A fixed ~5 s int16 ring (`user.parrot_clips_buffer_seconds`) is filled from `ParrotSystem.on_audio`.
  Nothing is written continuously. Speech never reaches disk unless a sound event or `parrot missed` fires.
- **Sound events** (frame power >= `user.parrot_clips_power_floor`, 20) save a ~1 s source window plus sidecar, whether or
  not a pattern fired, so rejected near-misses (throttled, or waiting on `detect_after`) are kept.
- **`parrot missed`** / **`parrot missed <sound>`** (e.g. `parrot missed click`) pulls the last
  `user.parrot_clips_missed_seconds` (5) out of RAM and saves it as the sound you _intended_, even if the model never
  registered anything. Sounds: click, tongue click, kitty, pop, lip pop, hiss, shh, oink, clap (folder = model label).
- `parrot clips off` / `parrot clips on`, or `user.parrot_clips_enabled`, is the kill switch. Off frees the ring.

## Store: `~/.talon/parrot_clips/` (`user.parrot_clips_dir`)

```
<sound>/<id>.wav          tight trimmed segment, one folder per model label  -> copy into parrot.py data/recordings/<sound>/
unlabeled/<id>.wav        'parrot missed' with no sound, to name later
_auto/<id>.wav            trimmed segment of automatic event clips (not yet labeled)
_source/<folder>/<id>.wav untouched source window (re-trim from this)
_meta/<id>.json           sidecar
```

Sidecar fields: `source_wav, segment_wav, start_ms, end_ms` (auto-detected by energy onset/offset, relative to the source),
`candidates` (all segments, loudest first), `confirmed` (false until a review step adjusts start/end), `label`, `intended`,
`intended_but_missed`, `detected_label`, `probabilities` (top 3), `power`, `fired` (patterns), `suppressed`
(`{pattern: throttled | waiting_detect_after}`), `linked_clip`, `timestamp`, `sample_rate`, `kind` (`auto` | `missed`).
`parrot missed` also marks the auto clip it overlaps (`intended`, `intended_but_missed`) and copies its model view.
Scoring those flags and a trim/review tool are out of scope.

## Not degrading Talon

The audio callback only copies into the preallocated ring and runs a tiny state machine (`feed`, `tick`, `frame`):
no IO, no segmentation, no growth. One daemon thread owns all wav/JSON writes, segmentation and pruning, fed by a bounded
queue (8); a full queue drops the save. Every callback entry catches and logs. Caps: `parrot_clips_max_mb` (200),
`parrot_clips_max_age_days` (30), `parrot_clips_max_clips` (2000); pruning runs on the worker, auto clips first.
Microbenchmark (`pytest .tests/test_parrot_clips.py -s`): about 16 us per 100 ms chunk to copy, under 1 us for
`tick`+`frame`.

## Unverified live

Hooking `ParrotSystem.on_audio` is by instance attribute; Talon's source is encrypted, so whether the cubeb stream
calls the patched method (rather than a bound method captured at construction) can only be checked live. If `parrot missed`
reports "no audio yet", the tap is not receiving frames.
