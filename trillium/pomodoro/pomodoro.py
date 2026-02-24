from talon import Module, imgui, cron, actions
import math
import threading
import time
import datetime
from typing import Optional, Union

module = Module()


lock = threading.Lock()
start_time = None
current_duration = None
pomodoro_type = None
pause_time = None
finished = False
cancel_job = None


# TODO: Better placement
@imgui.open(y=20, x=5)
def gui(gui: imgui.GUI):
    global cancel_job
    if pomodoro_type is not None:
        with lock:
            current_time = pause_time if pause_time else time.monotonic()
            remaining_time = math.ceil(
                (current_duration + start_time - current_time) / 60
            )
            if remaining_time <= 0:
                # Flash effect
                flashes_per_second = 1.5
                suffix = (
                    "FINISHED" if int(time.monotonic() * flashes_per_second) % 2 else ""
                )
                gui.text(f"{pomodoro_type} -- {suffix}")
            else:
                # remaining_time = (current_duration + start_time - current_time) / 60
                gui.text(f"{pomodoro_type} {remaining_time:02d}")


def delete_cancel_cron():
    global cancel_job
    try:
        cron.cancel(cancel_job)
    except:
        pass
    cancel_job = None


def check_pomodoro():
    global sound_job
    with lock:
        if start_time and time.monotonic() > start_time + current_duration:
            # TODO: Play alarm
            delete_cancel_cron()
            finished = True
            # TODO: Cron this?
            actions.key("f20")
            # for i in range(4):
                # Implementation at time of writing can't play parallel sounds,
                # so this will repeat the ding.


@module.action_class
class Actions:
    def pomodoro_start(
        type_: Optional[str] = "W",
        minutes_: Optional[Union[int, float]] = 25 * 60,
        seconds_: Optional[int] = 0
        ):
        """Start a pomodoro of `type` of length `time`."""
        global start_time, pomodoro_type, pause_time, finished, cancel_job, current_duration

        # 2025-05-12T22:35:59+00:00
        # 2025-05-12T22:36:16+00:00*0,0*0-
        print("pomodoro", minutes_, seconds_)
        with lock:
            delete_cancel_cron()
            cancel_job = cron.interval("1s", check_pomodoro)

            start_time = time.monotonic()
            pomodoro_type = type_
            current_duration = int(round(minutes_)) + int(seconds_)
            pause_time = None
            finished = False
        gui.show()

    def pomodoro_pause():

        """Pause the active pomodoro."""
        global pause_time
        with lock:
            if not pause_time:
                pause_time = time.monotonic()

    def pomodoro_unpause():

        """Unpause the active pomodoro."""
        global pause_time, current_time
        with lock:
            if pause_time:
                current_time -= pause_time - time.monotonic()
                pause_time = None

    def pomodoro_cancel():
        """Cancel the active pomodoro."""
        global start_time, pomodoro_type, pause_time, current_duration
        with lock:
            delete_cancel_cron()
            if not pomodoro_type:
                raise RuntimeError("No pomodoro running.")
            pomodoro_type = None
            start_time = None
            pause_time = None
            current_duration = None
        gui.hide()

    def pomodoro_get_end_time(fmt: str = None) -> str:
        """Return the end time of the pomodoro"""
        global current_duration, start_time
        global start_time, pomodoro_type, pause_time, current_duration
        current_time = pause_time if pause_time else time.monotonic()
        remaining_time = math.ceil(
                (current_duration + start_time - current_time) / 60
            )

        timestamp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=remaining_time)
        local_timestamp = timestamp.astimezone().replace(microsecond=0)

        if fmt is None:
            return local_timestamp.isoformat()
        return local_timestamp.strftime(fmt)

    def get_time_local(fmt: str = None) -> str:
        """Return the current local time with timezone info."""
        local_timestamp = datetime.datetime.now().astimezone().replace(microsecond=0)
        if fmt is None:
            return local_timestamp.isoformat()
        return local_timestamp.strftime(fmt)

    def get_time_local_ago(minutes: int, fmt: str = None) -> str:
        """Return the local time minus the given number of minutes."""
        local_timestamp = datetime.datetime.now().astimezone().replace(microsecond=0)
        ago_timestamp = local_timestamp - datetime.timedelta(minutes=minutes)
        if fmt is None:
            return ago_timestamp.isoformat()
        return ago_timestamp.strftime(fmt)

    def get_time_local_future(minutes: int, fmt: str = None) -> str:
        """Return the local time plus the given number of minutes."""
        local_timestamp = datetime.datetime.now().astimezone().replace(microsecond=0)
        future_timestamp = local_timestamp + datetime.timedelta(minutes=minutes)
        if fmt is None:
            return future_timestamp.isoformat()
        return future_timestamp.strftime(fmt)

