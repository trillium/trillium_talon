"""Keep the mouth sounds the parrot model heard, or missed.

No Talon imports, so it is unit-testable (see docs/parrot-clips.md).

Audio path rules (Talon must not degrade):
- The audio callback only copies frames into a preallocated RAM ring and runs a
  tiny event state machine. No file IO, no segmentation, no growing buffers.
- Everything else (wav/JSON writes, onset/offset segmentation, pruning) runs on
  ONE background thread fed by a small bounded queue. A full queue drops the
  save; the audio path never blocks.
- Failures are logged, never raised into Talon.
"""

import json
import logging
import os
import queue
import threading
import time
import wave
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("parrot_clips")

AUTO_DIR = "_auto"  # event clips the captain has not labeled
SOURCE_DIR = "_source"  # untouched source windows, mirrors the sound folders
META_DIR = "_meta"  # sidecar JSON, one per clip
UNLABELED = "unlabeled"


class AudioRing:
    """Fixed-size int16 ring. One writer (the audio callback), no locks."""

    def __init__(self, sample_rate: int = 16000, seconds: float = 5.0):
        self.sample_rate = int(sample_rate)
        self.capacity = int(self.sample_rate * seconds)
        self.buf = np.zeros(self.capacity, dtype=np.int16)
        self._scratch = np.zeros(self.capacity, dtype=np.float32)
        self.total = 0  # samples ever written; position = total % capacity

    def write(self, chunk: np.ndarray) -> None:
        """Copy a chunk in. Float chunks are taken as [-1, 1] and scaled."""
        if chunk.ndim > 1:
            chunk = chunk[:, 0]
        n = chunk.shape[0]
        if n == 0:
            return
        if n > self.capacity:
            self.total += n - self.capacity  # keep sample positions honest
            chunk = chunk[-self.capacity :]
            n = self.capacity
        pos = self.total % self.capacity
        first = min(n, self.capacity - pos)
        if chunk.dtype.kind == "f":
            s = self._scratch[:n]
            np.multiply(chunk, 32767.0, out=s, casting="unsafe")
            np.clip(s, -32768.0, 32767.0, out=s)
            self.buf[pos : pos + first] = s[:first]
            if first < n:
                self.buf[: n - first] = s[first:]
        else:
            self.buf[pos : pos + first] = chunk[:first]
            if first < n:
                self.buf[: n - first] = chunk[first:]
        self.total += n

    def snapshot(self, end_sample: int, length: int):
        """Copy up to `length` samples ending at `end_sample`.

        Returns (samples, start_sample). Samples the writer overwrote while we
        copied are trimmed away, so a returned clip is never torn.
        """
        w0 = self.total
        copy = self.buf.copy()
        w1 = self.total
        end = min(end_sample, w0)
        oldest = max(0, w1 - self.capacity)  # first sample still intact
        start = max(end - length, oldest, 0)
        if end <= start:
            return np.zeros(0, dtype=np.int16), start
        out = np.empty(end - start, dtype=np.int16)
        out[:] = copy[np.arange(start, end) % self.capacity]
        return out, start

    def clear(self) -> None:
        self.total = 0


def find_segments(
    pcm: np.ndarray,
    sample_rate: int,
    frame_ms: int = 10,
    merge_gap_ms: int = 80,
    pad_ms: int = 30,
    min_ms: int = 10,
) -> list[dict]:
    """Energy onset/offset candidates, loudest first.

    Returns dicts {start_ms, end_ms, peak}. The noise floor is a low percentile
    of frame RMS, so steady hum is not a segment; a segment must also reach a
    fraction of the loudest frame.
    """
    hop = max(1, sample_rate * frame_ms // 1000)
    n = pcm.shape[0] // hop
    if n < 2:
        return []
    x = pcm[: n * hop].astype(np.float32).reshape(n, hop)
    rms = np.sqrt((x * x).mean(axis=1))
    peak = float(rms.max())
    if peak < 200.0:  # near digital silence
        return []
    floor = float(np.percentile(rms, 20))
    thresh = max(floor * 4.0, peak * 0.15, 100.0)
    above = rms >= thresh
    runs: list[list[int]] = []
    for i, a in enumerate(above):
        if a:
            if runs and i - runs[-1][1] <= max(1, merge_gap_ms // frame_ms):
                runs[-1][1] = i
            else:
                runs.append([i, i])
    pad = pad_ms // frame_ms
    total_ms = pcm.shape[0] * 1000 // sample_rate
    out = []
    for a, b in runs:
        if (b - a + 1) * frame_ms < min_ms:
            continue
        out.append(
            {
                "start_ms": max(0, (a - pad) * frame_ms),
                "end_ms": min(total_ms, (b + 1 + pad) * frame_ms),
                "peak": round(float(rms[a : b + 1].max()), 1),
            }
        )
    out.sort(key=lambda s: -s["peak"])
    return out


def _write_wav(path: Path, pcm: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.astype("<i2").tobytes())
    os.replace(tmp, path)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)


def top3(classes: Optional[dict]) -> list[dict]:
    if not classes:
        return []
    ranked = sorted(classes.items(), key=lambda kv: -kv[1])[:3]
    return [{"label": k, "probability": round(float(v), 4)} for k, v in ranked]


class ClipStore:
    """Worker-side: writes clips and sidecars, prunes by age / count / MB."""

    def __init__(self, root: Path, max_mb: float, max_age_days: float, max_clips: int):
        self.root = Path(root)
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.max_age_s = max_age_days * 86400
        self.max_clips = max_clips

    def save(self, job: dict, pcm: np.ndarray, sr: int, ident: str) -> dict:
        kind = job["kind"]
        sound = job.get("intended") or UNLABELED
        folder = AUTO_DIR if kind == "auto" else sound
        source_rel = f"{SOURCE_DIR}/{folder}/{ident}.wav"
        _write_wav(self.root / source_rel, pcm, sr)

        cands = find_segments(pcm, sr)
        best = cands[0] if cands else None
        segment_rel = None
        if best:
            a = best["start_ms"] * sr // 1000
            b = best["end_ms"] * sr // 1000
            segment_rel = f"{folder}/{ident}.wav"
            _write_wav(self.root / segment_rel, pcm[a:b], sr)

        peak_frame = job.get("peak_frame")
        classes = getattr(peak_frame, "classes", None)
        probs = top3(classes)
        meta = {
            "id": ident,
            "kind": kind,
            "timestamp": job["wall_time"],
            "sample_rate": sr,
            "duration_ms": pcm.shape[0] * 1000 // sr,
            "source_wav": source_rel,
            "segment_wav": segment_rel,
            "start_ms": best["start_ms"] if best else None,
            "end_ms": best["end_ms"] if best else None,
            "candidates": cands,
            "confirmed": False,
            "label": None if kind == "auto" else sound,
            "intended": job.get("intended"),
            "intended_but_missed": bool(job.get("intended_but_missed")),
            "detected_label": probs[0]["label"] if probs else None,
            "probabilities": probs,
            "power": round(float(getattr(peak_frame, "power", 0.0)), 2),
            "fired": sorted(job.get("fired", ())),
            "suppressed": job.get("suppressed", {}),
            "linked_clip": job.get("linked_clip"),
        }
        _write_json(self.root / META_DIR / f"{ident}.json", meta)
        return meta

    def update_meta(self, ident: str, **fields) -> None:
        p = self.root / META_DIR / f"{ident}.json"
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            return
        data.update(fields)
        _write_json(p, data)

    def prune(self, now: Optional[float] = None) -> int:
        """Delete oldest clips (auto first) until under every cap. Returns count."""
        now = time.time() if now is None else now
        meta_dir = self.root / META_DIR
        if not meta_dir.is_dir():
            return 0
        rows = []
        for mp in meta_dir.glob("*.json"):
            try:
                meta = json.loads(mp.read_text())
            except (OSError, ValueError):
                continue
            files = [mp] + [
                self.root / meta[k] for k in ("source_wav", "segment_wav") if meta.get(k)
            ]
            size = 0
            for f in files:
                try:
                    size += f.stat().st_size
                except OSError:
                    pass
            # labeled clips outlive auto ones when over a cap
            rank = 0 if meta.get("kind") == "auto" and not meta.get("intended") else 1
            rows.append((rank, mp.stat().st_mtime, size, files))
        rows.sort(key=lambda r: (r[0], r[1]))
        total = sum(r[2] for r in rows)
        count = len(rows)
        removed = 0
        for rank, mtime, size, files in rows:
            too_old = now - mtime > self.max_age_s
            if not (too_old or total > self.max_bytes or count > self.max_clips):
                continue
            for f in files:
                try:
                    f.unlink()
                except OSError:
                    pass
            total -= size
            count -= 1
            removed += 1
        return removed


class ClipService:
    """Callback-side state machine plus the single background worker."""

    PRE_S = 0.3  # audio kept before an event starts
    EVENT_S = 1.0  # total auto clip length
    QUIET_S = 0.3  # silence that closes an event

    def __init__(self, clock=time.perf_counter, wall=time.time):
        self._clock = clock
        self._wall = wall
        self.enabled = False
        self.ring: Optional[AudioRing] = None
        self.store: Optional[ClipStore] = None
        self.power_floor = 20.0
        self.missed_seconds = 5.0
        self.queue: queue.Queue = queue.Queue(maxsize=8)
        self.dropped = 0
        self.saved = 0
        self._worker: Optional[threading.Thread] = None
        # event state (callback thread only)
        self._ev_open = False
        self._ev_start_sample = 0
        self._ev_start_t = 0.0
        self._ev_last_loud_t = 0.0
        self._ev_peak_power = -1.0
        self._ev_peak_frame = None
        self._ev_fired: set = set()
        self._ev_suppressed: dict = {}
        # worker-side memory of recent auto clips, for linking
        self._recent = deque(maxlen=16)
        self._last_ident_ms = 0

    # ---- configuration (main thread) ----
    def configure(
        self,
        *,
        enabled: bool,
        root: str,
        sample_rate: int = 16000,
        buffer_seconds: float = 5.0,
        power_floor: float = 20.0,
        max_mb: float = 200.0,
        max_age_days: float = 30.0,
        max_clips: int = 2000,
        missed_seconds: float = 5.0,
    ) -> None:
        self.power_floor = float(power_floor)
        self.missed_seconds = min(float(missed_seconds), float(buffer_seconds))
        if not enabled:
            self.enabled = False
            self.ring = None  # RAM released; the kill switch also forgets audio
            return
        if (
            self.ring is None
            or self.ring.sample_rate != sample_rate
            or self.ring.capacity != int(sample_rate * buffer_seconds)
        ):
            self.ring = AudioRing(sample_rate, buffer_seconds)
        self.store = ClipStore(Path(root).expanduser(), max_mb, max_age_days, max_clips)
        self._ensure_worker()
        self.enabled = True

    def _ensure_worker(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._run, name="parrot-clips", daemon=True
        )
        self._worker.start()

    # ---- audio callback path: cheap, no IO, never raises ----
    def feed(self, chunk: np.ndarray) -> None:
        ring = self.ring
        if not self.enabled or ring is None:
            return
        try:
            ring.write(chunk)
        except Exception:
            log.exception("parrot_clips: feed failed")

    def tick(self, power: float) -> None:
        """Call once per audio frame (ParrotDelegate.power_threshold)."""
        ring = self.ring
        if not self.enabled or ring is None:
            return
        try:
            now = self._clock()
            if power >= self.power_floor:
                if not self._ev_open:
                    self._ev_open = True
                    self._ev_start_t = now
                    self._ev_start_sample = ring.total
                    self._ev_peak_power = -1.0
                    self._ev_peak_frame = None
                    self._ev_fired = set()
                    self._ev_suppressed = {}
                self._ev_last_loud_t = now
            if self._ev_open:
                age = now - self._ev_start_t
                quiet = now - self._ev_last_loud_t
                if age >= self.EVENT_S - self.PRE_S and (
                    quiet >= self.QUIET_S or power < self.power_floor
                ):
                    self._close_event(ring)
                elif age >= 2 * self.EVENT_S:  # a long sound: cut it off
                    self._close_event(ring)
        except Exception:
            log.exception("parrot_clips: tick failed")

    def frame(self, frame, active: set, pattern_probe=None) -> None:
        """Call from pattern_match for frames at/above the model silence gate."""
        if not self.enabled or not self._ev_open:
            return
        try:
            if active:
                self._ev_fired.update(active)
            if frame.power > self._ev_peak_power:
                self._ev_peak_power = frame.power
                self._ev_peak_frame = frame
                if pattern_probe is not None:
                    self._ev_suppressed = pattern_probe(frame, active)
        except Exception:
            log.exception("parrot_clips: frame failed")

    def _close_event(self, ring: AudioRing) -> None:
        self._ev_open = False
        end = self._ev_start_sample + int((self.EVENT_S - self.PRE_S) * ring.sample_rate)
        job = {
            "kind": "auto",
            "end_sample": min(end, ring.total),
            "length": int(self.EVENT_S * ring.sample_rate),
            "wall_time": self._wall(),
            "peak_frame": self._ev_peak_frame,
            "fired": set(self._ev_fired),
            "suppressed": dict(self._ev_suppressed),
        }
        self._submit(job)

    def _submit(self, job: dict) -> bool:
        try:
            self.queue.put_nowait(job)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    # ---- voice command (main thread) ----
    def mark_missed(self, sound: Optional[str]) -> bool:
        """'parrot missed [sound]': keep the last few seconds from RAM."""
        ring = self.ring
        if not self.enabled or ring is None or ring.total == 0:
            return False
        return self._submit(
            {
                "kind": "missed",
                "intended": sound or None,
                "intended_but_missed": True,
                "end_sample": ring.total,
                "length": int(self.missed_seconds * ring.sample_rate),
                "wall_time": self._wall(),
            }
        )

    # ---- worker thread ----
    def _run(self) -> None:
        while True:
            job = self.queue.get()
            if job is None:
                return
            try:
                self._process(job)
            except Exception:
                log.exception("parrot_clips: save failed")
            finally:
                self.queue.task_done()

    def _ident(self, wall: float) -> str:
        ms = int(wall * 1000)
        if ms <= self._last_ident_ms:
            ms = self._last_ident_ms + 1
        self._last_ident_ms = ms
        return datetime.fromtimestamp(ms / 1000).strftime("%Y%m%d-%H%M%S-") + f"{ms % 1000:03d}"

    def _process(self, job: dict) -> None:
        ring, store = self.ring, self.store
        if ring is None or store is None:
            return
        pcm, start = ring.snapshot(job["end_sample"], job["length"])
        if pcm.shape[0] == 0:
            return
        ident = self._ident(job["wall_time"])
        job = dict(job)
        end = start + pcm.shape[0]
        if job["kind"] == "missed":
            for rec in reversed(self._recent):
                if start <= rec["end"] and rec["start"] <= end:
                    job["linked_clip"] = rec["id"]
                    job["peak_frame"] = rec["peak_frame"]
                    job["fired"] = rec["fired"]
                    job["suppressed"] = rec["suppressed"]
                    store.update_meta(
                        rec["id"],
                        intended=job["intended"],
                        intended_but_missed=True,
                        linked_clip=ident,
                    )
                    break
        meta = store.save(job, pcm, ring.sample_rate, ident)
        if job["kind"] == "auto":
            self._recent.append(
                {
                    "id": ident,
                    "start": start,
                    "end": end,
                    "peak_frame": job.get("peak_frame"),
                    "fired": job.get("fired", set()),
                    "suppressed": job.get("suppressed", {}),
                }
            )
        self.saved += 1
        store.prune()
        return meta

    def drain(self, timeout: float = 5.0) -> None:
        """Test helper: wait for the worker to empty its queue."""
        t0 = time.time()
        while time.time() - t0 < timeout and self.queue.unfinished_tasks:
            time.sleep(0.01)


def install_audio_tap(system, service: "ClipService") -> bool:
    """Wrap ParrotSystem.on_audio so raw frames also land in the RAM ring."""
    orig = getattr(system, "on_audio", None)
    if orig is None:
        return False

    def tapped(stream_id, ts, array):
        service.feed(array)
        return orig(stream_id, ts, array)

    system.on_audio = tapped
    return True


service = ClipService()
