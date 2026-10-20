"""Header-level validation of an uploaded snippet: a FLAC or a WAV, 16 kHz mono 16-bit.

Pure stdlib, no `talon` import, and no decoding: everything here reads the container headers
the phone wrote and checks them against the body's own length. Talon's own recordings are
`talon.lib.flac.encode` output, whose defaults are `sample_rate=16000, channels=1`, so that is
the one format a snippet may have; a different rate is refused rather than resampled. Failures
are `AudioError(code)` with a stable code the listener returns as `422`.

What this does not prove: that the compressed frames decode. It proves the header is a finalized
16 kHz mono 16-bit stream, that the length it claims is sane, and that the body is neither too
small nor too large to hold that much audio. Transport damage is the caller's `Content-Length`
and optional `X-Talon-Content-Sha256` check.
"""

import array
import struct
import sys
from dataclasses import dataclass

SAMPLE_RATE = 16000
CHANNELS = 1
BITS = 16
MIN_SECONDS = 0.1
MAX_SECONDS = 30.0

FLAC = "flac"
WAV = "wav"

# Smallest FLAC frame: 6 header bytes, a constant subframe of 3, and a 2-byte CRC is 11; 8 is
# the lax floor. Largest: a verbatim subframe (2 bytes a sample) plus a frame header and CRC.
_MIN_FRAME_BYTES = 8
_FRAME_OVERHEAD = 24
_MAX_RIFF_CHUNKS = 64
_WAVE_FORMAT_PCM = 1
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE
_UNFINALIZED_DATA_SIZES = (0, 0xFFFFFFFF)  # a writer that never came back to fill it in


class AudioError(Exception):
    """The upload is not an acceptable snippet. `code` is the stable `422` error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AudioInfo:
    container: str  # FLAC or WAV
    sample_rate: int
    channels: int
    bits: int
    samples: int
    seconds: float
    pcm: bytes | None = (
        None  # the little-endian int16 data, for a WAV (it is stored as FLAC)
    )


def _check_format(rate: int, channels: int, bits: int) -> None:
    if rate != SAMPLE_RATE:
        raise AudioError("bad_sample_rate")
    if channels != CHANNELS:
        raise AudioError("bad_channels")
    if bits != BITS:
        raise AudioError("bad_bit_depth")


def _check_length(samples: int) -> float:
    seconds = samples / SAMPLE_RATE
    if seconds < MIN_SECONDS:
        raise AudioError("too_short")
    if seconds > MAX_SECONDS:
        raise AudioError("too_long")
    return seconds


def parse_flac(body: bytes) -> AudioInfo:
    if body[:4] != b"fLaC":
        raise AudioError("not_flac")
    if len(body) < 8 + 34:
        raise AudioError("truncated_audio")
    first, length = body[4], int.from_bytes(body[5:8], "big")
    if first & 0x7F != 0 or length != 34:  # STREAMINFO is required first, 34 bytes
        raise AudioError("bad_streaminfo")
    si = body[8 : 8 + 34]
    min_block, max_block = struct.unpack(">HH", si[:4])
    packed = int.from_bytes(si[10:18], "big")
    rate = packed >> 44
    channels = ((packed >> 41) & 0x7) + 1
    bits = ((packed >> 36) & 0x1F) + 1
    total = packed & ((1 << 36) - 1)
    if min_block < 16 or max_block < 16 or min_block > max_block:
        raise AudioError("bad_streaminfo")
    _check_format(rate, channels, bits)
    if total == 0:  # a stream written without finalizing the header
        raise AudioError("unfinalized_audio")
    seconds = _check_length(total)

    pos, last = 8 + 34, bool(first & 0x80)
    while not last:  # skip the remaining metadata blocks, each bounded by the body
        if pos + 4 > len(body):
            raise AudioError("truncated_audio")
        last = bool(body[pos] & 0x80)
        pos += 4 + int.from_bytes(body[pos + 1 : pos + 4], "big")
    if pos + 2 > len(body):
        raise AudioError("truncated_audio")
    if body[pos] != 0xFF or body[pos + 1] & 0xFE != 0xF8:  # frame sync code
        raise AudioError("no_audio_frames")
    audio_bytes = len(body) - pos
    if audio_bytes < -(-total // max_block) * _MIN_FRAME_BYTES:
        raise AudioError("truncated_audio")
    if audio_bytes > total * 2 + -(-total // min_block) * _FRAME_OVERHEAD + 64:
        raise AudioError("length_mismatch")
    return AudioInfo(FLAC, rate, channels, bits, total, seconds)


def _wav_format(chunk: bytes) -> tuple[int, int, int, int, int]:
    """`(format tag, channels, rate, block align, bits)` of a `fmt ` chunk body."""
    if len(chunk) < 16:
        raise AudioError("bad_wav")
    tag, channels, rate, _, align, bits = struct.unpack("<HHIIHH", chunk[:16])
    if tag == _WAVE_FORMAT_EXTENSIBLE:
        if len(chunk) < 26:
            raise AudioError("bad_wav")
        tag = struct.unpack("<H", chunk[24:26])[
            0
        ]  # the sub-format GUID starts with the tag
    return tag, channels, rate, align, bits


def parse_wav(body: bytes) -> AudioInfo:
    if body[:4] != b"RIFF" or body[8:12] != b"WAVE":
        raise AudioError("not_wav")
    fmt = None
    pos = 12
    for _ in range(_MAX_RIFF_CHUNKS):
        if pos + 8 > len(body):
            raise AudioError("bad_wav")
        cid, size = body[pos : pos + 4], struct.unpack("<I", body[pos + 4 : pos + 8])[0]
        start = pos + 8
        if cid == b"data":
            if fmt is None:
                raise AudioError("bad_wav")
            if size in _UNFINALIZED_DATA_SIZES:
                raise AudioError("unfinalized_audio")
            if start + size > len(body):
                raise AudioError("truncated_audio")
            tag, channels, rate, align, bits = fmt
            if tag != _WAVE_FORMAT_PCM:
                raise AudioError("unsupported_wav_format")
            _check_format(rate, channels, bits)
            if align != channels * bits // 8 or size % align:
                raise AudioError("bad_wav")
            samples = size // align
            seconds = _check_length(samples)
            return AudioInfo(
                WAV,
                rate,
                channels,
                bits,
                samples,
                seconds,
                bytes(body[start : start + size]),
            )
        if cid == b"fmt ":
            if start + size > len(body):
                raise AudioError("bad_wav")
            fmt = _wav_format(body[start : start + size])
        pos = start + size + (size & 1)  # chunks are word aligned
    raise AudioError("bad_wav")


def inspect(container: str, body: bytes) -> AudioInfo:
    """Validate `body` as `container` (FLAC or WAV). Raises `AudioError`; never anything else."""
    try:
        return parse_flac(body) if container == FLAC else parse_wav(body)
    except AudioError:
        raise
    except (
        Exception
    ) as exc:  # noqa: BLE001 - a header that defeats the parser is the caller's
        raise AudioError("bad_audio") from exc


def pcm16_to_floats(pcm: bytes) -> list[float]:
    """Little-endian int16 bytes to floats in [-1, 1), the input `talon.lib.flac.encode` takes."""
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder == "big":
        samples.byteswap()
    return [s / 32768.0 for s in samples]
