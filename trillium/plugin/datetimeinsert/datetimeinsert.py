import datetime

from talon import Module

mod = Module()


@mod.action_class
class Actions:
    def time_format_utc(fmt: str = None) -> str:
        """Return the current UTC time, formatted.
        fmt: strftime()-style format string, defaults to ISO format."""
        now = datetime.datetime.now(datetime.UTC)
        if fmt is None:
            return now.replace(microsecond=0).isoformat()
        return now.strftime(fmt)

    def time_format_utc_future(minutes: int = 1, fmt: str = None) -> str:
        """Return the current UTC time + number minutes in the future, formatted.
        fmt: strftime()-style format string, defaults to ISO format."""
        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes)
        if fmt is None:
            return future.replace(microsecond=0).isoformat()
        return future.strftime(fmt)

