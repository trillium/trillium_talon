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
    """Hand `fn` to `schedule` (e.g. Talon's cron.after), block for its result, re-raise errors.

    On timeout the job is cancelled if it has not started, so a job that Talon's cron
    thread picks up late does nothing instead of running a command the caller was told
    never ran. A job already running cannot be stopped; the timeout then means only
    "not finished", and the command may still complete.
    """
    done = threading.Event()
    box: dict[str, Any] = {}
    lock = threading.Lock()
    state = {"started": False, "cancelled": False}

    def job():
        with lock:
            if state["cancelled"]:
                done.set()
                return
            state["started"] = True
        try:
            box["value"] = fn()
        except BaseException as exc:  # carried back to the waiting thread
            box["error"] = exc
        finally:
            done.set()

    schedule(job)
    if not done.wait(timeout):
        with lock:
            if not state["started"]:
                state["cancelled"] = True
        raise DispatchTimeout()
    if "error" in box:
        raise box["error"]
    return box.get("value")
