"""Activity data gathering — pure process/port introspection with no Talon imports.

Provides ProcessRow, port scanning, and process listing used by activity_overlay.
"""

import os
import subprocess

# ── Dev ports to prioritize ──

DEV_PORTS = (
    set(range(3000, 4000))
    | set(range(4000, 5000))
    | set(range(5000, 6000))
    | set(range(8000, 9000))
    | {5432, 3306, 3307, 6379, 27017}
)

MAX_ROWS = 12


# ── Data types ──


class ProcessRow:
    __slots__ = ("pid", "name", "cpu", "mem_rss", "ports")

    def __init__(self, pid: int, name: str, cpu: float, mem_rss: int, ports: list[int]):
        self.pid = pid
        self.name = name
        self.cpu = cpu
        self.mem_rss = mem_rss
        self.ports = ports


# ── Helpers ──


def _human_mem(rss_kb: int) -> str:
    """Convert RSS in KB to human-readable string."""
    if rss_kb >= 1048576:
        return f"{rss_kb / 1048576:.1f}G"
    elif rss_kb >= 1024:
        return f"{rss_kb / 1024:.0f}M"
    else:
        return f"{rss_kb}K"


def _get_listening_ports() -> dict[int, list[int]]:
    """Return {pid: [port, ...]} for TCP listening sockets."""
    pid_ports: dict[int, list[int]] = {}
    try:
        out = subprocess.check_output(
            ["lsof", "-iTCP", "-sTCP:LISTEN", "-nP", "-F", "pcn"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
        current_pid = None
        for line in out.strip().split("\n"):
            if not line:
                continue
            if line.startswith("p"):
                try:
                    current_pid = int(line[1:])
                except ValueError:
                    current_pid = None
            elif line.startswith("n") and current_pid is not None:
                # Format: n*:PORT or n127.0.0.1:PORT or n[::1]:PORT
                addr = line[1:]
                colon = addr.rfind(":")
                if colon >= 0:
                    try:
                        port = int(addr[colon + 1:])
                        pid_ports.setdefault(current_pid, []).append(port)
                    except ValueError:
                        pass
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return pid_ports


def _get_processes() -> list[ProcessRow]:
    """Get top processes by CPU, joined with listening port data."""
    pid_ports = _get_listening_ports()

    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,pcpu,rss,comm"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    rows: list[ProcessRow] = []
    for line in out.strip().split("\n")[1:]:  # skip header
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            cpu = float(parts[1])
            rss = int(parts[2])
            name = os.path.basename(parts[3].strip())
        except (ValueError, IndexError):
            continue

        # Skip kernel/idle
        if name in ("kernel_task", "idle", "launchd") and cpu < 1.0:
            continue

        ports = pid_ports.get(pid, [])
        rows.append(ProcessRow(pid, name, cpu, rss, ports))

    # Separate dev-port processes from the rest
    dev_port_rows = []
    other_rows = []
    for r in rows:
        has_dev_port = any(p in DEV_PORTS for p in r.ports)
        if has_dev_port:
            dev_port_rows.append(r)
        else:
            other_rows.append(r)

    # Sort each group by CPU descending
    dev_port_rows.sort(key=lambda r: r.cpu, reverse=True)
    other_rows.sort(key=lambda r: r.cpu, reverse=True)

    # Take dev-port rows first, fill remaining slots with top CPU
    result = dev_port_rows[:MAX_ROWS]
    remaining = MAX_ROWS - len(result)
    if remaining > 0:
        # Avoid duplicates
        dev_pids = {r.pid for r in result}
        for r in other_rows:
            if r.pid not in dev_pids:
                result.append(r)
                if len(result) >= MAX_ROWS:
                    break

    return result
