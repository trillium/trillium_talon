"""TPE1 wire format: parse and validate a phone emission before anything native sees it.

A malformed array handed to the native w2l decoder aborts the whole Talon process, so every
check here runs in Python first and any failure raises `WireError`.

Layout (little-endian): 24-byte header `<4sBBHIId` (magic `TPE1`, dtype 0=f32 / 1=f16,
flags, reserved, u32 T, u32 n_pcm, f64 ts) then `T * 29` values, row-major `[T, 29]`.
"""

import math
import struct
from typing import NamedTuple

import numpy as np

MAGIC = b"TPE1"
HEADER = struct.Struct("<4sBBHIId")
TOKENS = 29
MAX_FRAMES = 1200
MAX_PAYLOAD_BYTES = 65536
MAX_ABS = 1e4
PAD_SAMPLES = 4000
WINDOW_SAMPLES = 400  # 25 ms analysis window
HOP_SAMPLES = 160  # 10 ms hop
SUBSAMPLE = 3  # encoder emits one frame per 3 feature frames (30 ms)
DTYPE_F32 = 0
DTYPE_F16 = 1
_DTYPES = {DTYPE_F32: np.dtype("<f4"), DTYPE_F16: np.dtype("<f2")}


class WireError(ValueError):
    """The payload is not a valid TPE1 frame; `code` is a stable machine-readable reason."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class Emission(NamedTuple):
    array: np.ndarray  # (T, 29) float32, C-contiguous, finite
    n_pcm: int
    ts: float


def frames_for(n_pcm: int) -> int:
    """Frame count the engine produces for `n_pcm` samples with pad=True.

    Fitted to observed encoder output (25 ms window, 10 ms hop, 3x subsample, ceil); the
    scout's `(n_pcm + 8000) // 480` is off by one for some lengths. The lab script checks
    this against the real encoder over a length sweep.
    """
    n = n_pcm + 2 * PAD_SAMPLES
    if n < WINDOW_SAMPLES:
        return 0
    feats = (n - WINDOW_SAMPLES) // HOP_SAMPLES + 1
    return -(-feats // SUBSAMPLE)


def pack(em: np.ndarray, n_pcm: int, ts: float, fp16: bool = False) -> bytes:
    """Encode an emission the way the phone does (used by tests and tooling)."""
    a = np.ascontiguousarray(em, dtype=_DTYPES[DTYPE_F16 if fp16 else DTYPE_F32])
    return (
        HEADER.pack(
            MAGIC, DTYPE_F16 if fp16 else DTYPE_F32, 0, 0, a.shape[0], n_pcm, ts
        )
        + a.tobytes()
    )


def parse_validate(buf: bytes) -> Emission:
    """Return the validated emission or raise `WireError`. Never touches native code."""
    if not isinstance(buf, (bytes, bytearray, memoryview)):
        raise WireError("not_bytes", type(buf).__name__)
    n = len(buf)
    if n > MAX_PAYLOAD_BYTES:
        raise WireError("payload_too_large", f"{n} > {MAX_PAYLOAD_BYTES}")
    if n < HEADER.size:
        raise WireError("short_header", f"{n} < {HEADER.size}")
    magic, dt, _flags, _rsvd, T, n_pcm, ts = HEADER.unpack_from(buf)
    if magic != MAGIC:
        raise WireError("bad_magic", repr(bytes(magic)))
    if dt not in _DTYPES:
        raise WireError("bad_dtype", str(dt))
    if not 1 <= T <= MAX_FRAMES:
        raise WireError("bad_frame_count", str(T))
    if not math.isfinite(ts) or ts < 0:
        raise WireError("bad_ts", repr(ts))
    if T != frames_for(n_pcm):
        raise WireError("frame_mismatch", f"T={T} n_pcm={n_pcm} want {frames_for(n_pcm)}")
    dtype = _DTYPES[dt]
    want = HEADER.size + T * TOKENS * dtype.itemsize
    if n != want:
        raise WireError("body_length", f"{n} != {want}")
    a = np.frombuffer(buf, dtype, T * TOKENS, HEADER.size).astype(np.float32)
    return Emission(validate_array(a.reshape(T, TOKENS)), n_pcm, ts)


def validate_array(a, n_pcm: int | None = None) -> np.ndarray:
    """Check an already-decoded emission and return it as C-contiguous float32 `(T, 29)`.

    This is the last Python gate before the array reaches the native decoder, so the
    encoder queue runs it again on everything it accepts. A `(29, T)` array is refused
    here by shape; a wire payload cannot be told apart by bytes alone, only by header.
    """
    if not isinstance(a, np.ndarray) or a.dtype.kind != "f":
        raise WireError("bad_array", type(a).__name__)
    if a.ndim != 2 or a.shape[1] != TOKENS:
        raise WireError("bad_shape", str(a.shape))
    T = a.shape[0]
    if not 1 <= T <= MAX_FRAMES:
        raise WireError("bad_frame_count", str(T))
    if n_pcm is not None and T != frames_for(n_pcm):
        raise WireError("frame_mismatch", f"T={T} n_pcm={n_pcm} want {frames_for(n_pcm)}")
    if not np.isfinite(a).all():
        raise WireError("non_finite")
    if np.abs(a).max() >= MAX_ABS:
        raise WireError("out_of_range", f"abs max >= {MAX_ABS}")
    return np.ascontiguousarray(a, dtype=np.float32)
