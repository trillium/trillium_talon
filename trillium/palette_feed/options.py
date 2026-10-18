"""Runtime options for the feed: where it binds, and whether reads need the token.

Resolved from the environment first, then the Talon setting, then the defaults here,
so a host can be repointed without editing this repo. Pure stdlib, no Talon imports.
"""

import ipaddress
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

DEFAULT_BIND = "127.0.0.1"
DEFAULT_OPEN_READS = False

ENV_BIND = "TALON_PALETTE_BIND"
ENV_OPEN_READS = "TALON_PALETTE_OPEN_READS"

SETTING_BIND = "user.palette_feed_bind"
SETTING_OPEN_READS = "user.palette_feed_open_reads"

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def is_loopback(host: str) -> bool:
    """True only for an address that provably cannot leave this machine.

    A hostname resolves elsewhere, so it counts as non-loopback: the caller has to
    say out loud that it meant to publish.
    """
    try:
        return ipaddress.ip_address(host.strip()).is_loopback
    except ValueError:
        return False


def parse_bool(value: Any) -> bool | None:
    """True/False for a recognizable switch value; None when it is not one."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    return None


@dataclass(frozen=True)
class Options:
    bind: str = DEFAULT_BIND
    open_reads: bool = DEFAULT_OPEN_READS
    warnings: tuple[str, ...] = field(default=())

    @property
    def allow_non_loopback(self) -> bool:
        """True when the operator configured a bind that can leave the machine.

        Passed to `server.start`, which refuses a non-loopback address without it, so
        a future hardcoded host fails loudly instead of publishing by accident.
        """
        return not is_loopback(self.bind)

    def describe(self) -> str:
        """One log line's worth of what this configuration exposes."""
        where = "tailnet/network" if self.allow_non_loopback else "loopback only"
        reads = "open" if self.open_reads else "token-gated"
        return f"{where}, reads {reads}"


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def resolve(
    env: Mapping[str, str] = os.environ,
    setting: Callable[[str, Any], Any] = lambda name, default=None: default,
) -> Options:
    """Env wins over the Talon setting, which wins over the defaults."""
    warnings: list[str] = []

    bind = (
        _text(env.get(ENV_BIND)) or _text(setting(SETTING_BIND, None)) or DEFAULT_BIND
    )

    open_reads = parse_bool(env.get(ENV_OPEN_READS))
    if open_reads is None:
        if env.get(ENV_OPEN_READS):
            warnings.append(
                f"{ENV_OPEN_READS}={env[ENV_OPEN_READS]!r} is not a yes/no value"
            )
        open_reads = parse_bool(setting(SETTING_OPEN_READS, None))
    if open_reads is None:
        open_reads = DEFAULT_OPEN_READS

    return Options(bind=bind, open_reads=open_reads, warnings=tuple(warnings))
