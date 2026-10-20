"""Hand a job to Talon's main thread from a listener worker thread.

Pure Python (no `talon` import): the caller passes `after` (queue a job to run soon on the main
thread) and, optionally, the Talon resource context that should own the queued job.

Why an owner: `cron.after` registers the job with the resource context of the *calling thread*,
and a thread inherits the context of whoever started it. A listener started from a Talon REPL
statement therefore keeps serving on workers whose context was freed when that statement ended,
and every `cron.after` raises `ResourceClosed` (seen live: every request was `500 internal`).
Scheduling inside a context the module owns does not depend on how the worker was started.
"""

from contextlib import AbstractContextManager
from typing import Callable, Protocol

Job = Callable[[], None]


class SchedulerUnavailable(Exception):
    """The job could not be handed to the main thread. It was never queued, so nothing ran."""


class Owner(Protocol):
    def enter(self) -> AbstractContextManager[None]: ...


def main_thread(
    after: Callable[[Job], None], owner: Owner | None = None
) -> Callable[[Job], None]:
    """`schedule(job)` that runs `after(job)` inside `owner`, and raises `SchedulerUnavailable`
    (chained to the cause) if that fails for any reason."""

    def schedule(job: Job) -> None:
        try:
            if owner is None:
                after(job)
            else:
                with owner.enter():
                    after(job)
        except (
            Exception
        ) as exc:  # noqa: BLE001 - whatever the scheduler raised, the job did not run
            raise SchedulerUnavailable(type(exc).__name__) from exc

    return schedule
