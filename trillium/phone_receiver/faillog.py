"""What the phone receiver writes to Talon's log when something it runs fails.

Pure Python (no `talon` import). Every failure inside the receiver is contained and turned into
a status code, so without this the cause is gone by the time the phone sees `500`. A report is
the exception class and the `file:line in function` of each frame, nothing else: no exception
message (it can echo a body, a header or a phrase), no source lines, no locals, no key, no
audio, and the phrase only ever as a length. Lines are prefixed `phone_listener:` and go to
`print`, which is Talon's normal log path.
"""

import os
import traceback
from typing import Any, Callable

PREFIX = "phone_listener:"
MAX_FRAMES = 12  # innermost frames kept per exception
MAX_CHAIN = 4  # exceptions followed through __cause__ / __context__

Log = Callable[[str], None]


def qualname(exc: BaseException) -> str:
    t = type(exc)
    return (
        t.__qualname__
        if t.__module__ == "builtins"
        else f"{t.__module__}.{t.__qualname__}"
    )


def _frames(exc: BaseException) -> list[str]:
    # `extract_tb`, not `walk_tb`: under Talon's interpreter a frame has no `f_code`.
    try:
        summary = traceback.extract_tb(exc.__traceback__)
        return [
            f"  {os.path.basename(f.filename)}:{f.lineno} in {f.name}" for f in summary
        ]
    except Exception:  # noqa: BLE001 - the class alone is still worth logging
        return ["  (frames unavailable)"]


def trace_lines(exc: BaseException) -> list[str]:
    """Class and frames of `exc`, then the same for the exception it was raised from."""
    lines: list[str] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen and len(seen) < MAX_CHAIN:
        seen.add(id(cur))
        lines.append(f"{'raised' if len(seen) == 1 else 'from'} {qualname(cur)}")
        lines.extend(_frames(cur)[-MAX_FRAMES:])
        nxt = cur.__cause__
        cur = nxt if nxt is not None else cur.__context__
    return lines


def _context(ctx: dict[str, Any]) -> str:
    parts = []
    if ctx.get("mode"):
        parts.append(f"mode {ctx['mode']}")
    if ctx.get("bytes") is not None:
        parts.append(f"{ctx['bytes']} bytes")
    if ctx.get("ms") is not None:
        parts.append(f"{ctx['ms']} ms")
    return f" ({', '.join(parts)})" if parts else ""


def _emit(log: Log, line: str) -> None:
    # Talon's `print` raises SystemExit in a thread whose resource context was freed (a listener
    # started from a REPL statement). Left alone it would end the worker, so the phone would see a
    # dropped connection instead of the status code, and the lines after it would be lost.
    try:
        log(f"{PREFIX} {line}")
    except (Exception, SystemExit):  # noqa: BLE001
        pass


def report(log: Log, where: str, exc: BaseException, **ctx: Any) -> None:
    """Log `where` failed with `exc`'s class and frames. Never raises."""
    try:
        lines = [f"{where} failed: {qualname(exc)}{_context(ctx)}", *trace_lines(exc)]
    except Exception:  # noqa: BLE001 - reporting must not become the failure
        return
    for line in lines:
        _emit(log, line)


def note(log: Log, what: str, **ctx: Any) -> None:
    """One line for a refusal that has no exception to show (a timeout, a service code)."""
    try:
        _emit(log, f"{what}{_context(ctx)}")
    except Exception:  # noqa: BLE001
        pass  # building the line failed; `_emit` already contains the log call
