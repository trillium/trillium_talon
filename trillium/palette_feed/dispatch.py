"""Run a callable on another thread and wait for its result."""

import threading
from typing import Any, Callable


class DispatchTimeout(Exception):
    """The scheduled call did not finish in time."""


def run_scheduled(
    schedule: Callable[[Callable[[], None]], None],
    fn: Callable[[], Any],
    timeout: float,
) -> Any:
    """Hand `fn` to `schedule` (e.g. Talon's cron.after), block for its result, re-raise errors."""
    done = threading.Event()
    box: dict[str, Any] = {}

    def job():
        try:
            box["value"] = fn()
        except BaseException as exc:  # carried back to the waiting thread
            box["error"] = exc
        finally:
            done.set()

    schedule(job)
    if not done.wait(timeout):
        raise DispatchTimeout()
    if "error" in box:
        raise box["error"]
    return box.get("value")
