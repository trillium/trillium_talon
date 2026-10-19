"""Parity harness: run each utterance down both listener paths and diff the phrase output.

Path A posts the phone's emission (TPE1, mode `emission`); path B posts the same audio as PCM16
(mode `pcm`, the engine runs its own frontend and acoustic model). Both go through the same
`ListenerApi`, and the only thing flipped between them is the mode setting, so a pass also shows
that falling back to PCM needs no code change. Pure Python: the engine behind the API decides
what is being tested (a fake in pytest, a private `W2lEngine` in `.tests/lab/phone_listener_lab.py`).
"""

import io
from dataclasses import dataclass
from typing import Any, Callable, NamedTuple

import numpy as np

from . import listener, wire


@dataclass
class Utterance:
    name: str
    pcm: np.ndarray  # mono 16 kHz float32 in [-1, 1]
    ts: float = 1.25


class Outcome(NamedTuple):
    status: int
    ok: bool
    text: str | None
    reject: bool | None
    error: str | None


class Row(NamedTuple):
    name: str
    emission: Outcome
    pcm: Outcome

    @property
    def equal(self) -> bool:
        return self.emission.ok and self.pcm.ok and self.emission[1:4] == self.pcm[1:4]


class Report(NamedTuple):
    rows: list[Row]

    @property
    def identical(self) -> bool:
        return bool(self.rows) and all(r.equal for r in self.rows)

    def mismatches(self) -> list[Row]:
        return [r for r in self.rows if not r.equal]

    def summary(self) -> dict[str, Any]:
        bad = self.mismatches()
        return {
            "utterances": len(self.rows),
            "identical": len(self.rows) - len(bad),
            "mismatched": [r.name for r in bad],
        }

    def format(self) -> str:
        out = []
        for r in self.rows:
            tag = "same" if r.equal else "DIFF"
            out.append(f"{tag} {r.name}: emission={_fmt(r.emission)} pcm={_fmt(r.pcm)}")
        s = self.summary()
        out.append(f"{s['identical']}/{s['utterances']} identical")
        return "\n".join(out)


def _fmt(o: Outcome) -> str:
    if not o.ok:
        return f"error({o.status} {o.error})"
    return f"{o.text!r}{' reject' if o.reject else ''}"


def pcm16(pcm: np.ndarray) -> bytes:
    """Quantize float samples to the little-endian int16 the phone sends."""
    return np.clip(np.rint(pcm * 32768.0), -32768, 32767).astype("<i2").tobytes()


def api_poster(api: listener.ListenerApi, login: str) -> Callable:
    """`post(content_type, body, ts)` -> `(status, json_body)` against `api`, as `login`."""

    def post(content_type: str, body: bytes, ts: float):
        headers = {
            "Tailscale-User-Login": login,
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            listener.TS_HEADER: repr(ts),
        }
        resp = api.handle("POST", listener.PATH, headers, io.BytesIO(body))
        return resp.status, resp.body

    return post


def _outcome(status: int, body: dict) -> Outcome:
    return Outcome(
        status,
        bool(body.get("ok")),
        body.get("text"),
        body.get("reject"),
        body.get("error"),
    )


def run_parity(
    post: Callable,
    set_mode: Callable[[str], None],
    utterances: list[Utterance],
    emit: Callable[[np.ndarray], np.ndarray],
    fp16: bool = False,
) -> Report:
    """`emit(samples)` is the phone's acoustic model: samples in, `(T, 29)` raw logits out.

    It is called on the int16-quantized samples, the exact audio the PCM path receives.
    """
    rows = []
    for u in utterances:
        raw = pcm16(u.pcm)
        samples = wire.parse_pcm(raw)
        em = np.asarray(emit(samples), dtype=np.float32)
        set_mode(listener.MODE_EMISSION)
        a = _outcome(
            *post(
                listener.CONTENT_TYPES[listener.MODE_EMISSION],
                wire.pack(em, len(samples), u.ts, fp16),
                u.ts,
            )
        )
        set_mode(listener.MODE_PCM)
        b = _outcome(
            *post("audio/L16; rate=16000; channels=1", raw, u.ts),
        )
        rows.append(Row(u.name, a, b))
    return Report(rows)
