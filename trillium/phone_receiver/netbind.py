"""Where the phone listener may bind: loopback, or this Mac's own tailnet address.

Pure stdlib, no `talon` import. Two addresses are acceptable and nothing else is: `127.0.0.1`,
and an IPv4 address inside the Tailscale CGNAT range `100.64.0.0/10` that `tailscale ip -4`
reports as assigned to this machine. `0.0.0.0`, `::`, a LAN address, a hostname, an address in
the tailnet range that belongs to some other node, and anything unparsable are refused, so a
typo in the setting can never publish the listener on a wider interface.
"""

import ipaddress
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable

LOOPBACK = ipaddress.IPv4Address("127.0.0.1")
TAILNET = ipaddress.IPv4Network("100.64.0.0/10")
# Talon's PATH is sparse, so `which` alone is not enough.
TAILSCALE_BINARIES = (
    "/usr/local/bin/tailscale",
    "/opt/homebrew/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
)
TAILSCALE_TIMEOUT_S = 3.0


class BindError(ValueError):
    """The requested bind address is not one the listener may serve on."""


@dataclass(frozen=True)
class BindPlan:
    host: str
    # True when reachable from the tailnet, so the shared-secret key is the auth
    tailnet: bool


def _tailscale_binary() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    return next((p for p in TAILSCALE_BINARIES if os.access(p, os.X_OK)), None)


def tailnet_addresses() -> frozenset[ipaddress.IPv4Address]:
    """The tailnet IPv4 addresses assigned to this Mac, from `tailscale ip -4`.

    Empty when tailscale is missing, stopped, slow or prints nothing usable: every failure
    means "no address is provably ours", which refuses the bind.
    """
    binary = _tailscale_binary()
    if binary is None:
        return frozenset()
    try:
        out = subprocess.run(
            [binary, "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=TAILSCALE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if out.returncode != 0:
        return frozenset()
    found = set()
    for line in out.stdout.split():
        try:
            addr = ipaddress.ip_address(line)
        except ValueError:
            continue
        if isinstance(addr, ipaddress.IPv4Address) and addr in TAILNET:
            found.add(addr)
    return frozenset(found)


def resolve_bind(
    host: object,
    assigned: Callable[[], Iterable[ipaddress.IPv4Address]] = tailnet_addresses,
) -> BindPlan:
    """Validate `host`; raises `BindError` unless it is loopback or an assigned tailnet address.

    `assigned` is only called for a tailnet-range address, so the default loopback bind never
    shells out.
    """
    if not isinstance(host, str):
        raise BindError("bind host must be a string")
    text = host.strip()
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        raise BindError(f"bind host {text!r} is not an IP address") from None
    if addr == LOOPBACK:
        return BindPlan(str(addr), tailnet=False)
    if not isinstance(addr, ipaddress.IPv4Address) or addr not in TAILNET:
        raise BindError(
            f"bind host {text!r} is neither 127.0.0.1 nor a tailnet (100.64.0.0/10) address"
        )
    if addr not in set(assigned()):
        raise BindError(
            f"bind host {text!r} is in the tailnet range but is not assigned to this Mac "
            "(see `tailscale ip -4`)"
        )
    return BindPlan(str(addr), tailnet=True)
