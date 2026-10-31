"""Thin layer over the `sidecar` CLI: argv builders, verb table, background runner.

No Talon import, so it is unit-testable. When Sidecar lands its own scroll verbs
(`sidecar scroll <pane> next|prev|top|bottom`, task-e6jdw), repoint VERBS only.
Errors are logged, never raised; nothing here blocks Talon (work runs in a thread).
"""

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("sidecar")

SIDECAR = "sidecar"
DEFAULT_PANE = "dev-f5cf8b"
TIMEOUT_S = 15
TOKEN_FILE = Path.home() / ".config" / "sidecar" / "token"

# Spoken verb -> argv tail after the CLI name; "{pane}" is filled in.
# Today: pdf-next/pdf-prev via invoke, scrolling via invoke --direction.
VERBS: dict[str, list[str]] = {
    "next": ["invoke", "{pane}", "pdf-next"],
    "previous": ["invoke", "{pane}", "pdf-prev"],
    "up": ["invoke", "{pane}", "scroll", "--direction", "up"],
    "down": ["invoke", "{pane}", "scroll", "--direction", "down"],
    "top": ["invoke", "{pane}", "scroll", "--direction", "top"],
    "bottom": ["invoke", "{pane}", "scroll", "--direction", "bottom"],
}

_env = os.environ.copy()
_env["PATH"] = ":".join(
    ["/opt/homebrew/bin", str(Path.home() / ".local" / "bin"), "/usr/local/bin",
     "/usr/bin", "/bin", _env.get("PATH", "")]
)


def build_argv(tail: list[str], pane: str) -> list[str]:
    """Full argv for `sidecar <tail>`, with the pane filled in and auth attached."""
    argv = [SIDECAR, *[a.replace("{pane}", pane) for a in tail]]
    if TOKEN_FILE.exists():
        argv += ["--token-file", str(TOKEN_FILE)]
    return argv


def verb_argv(verb: str, pane: str) -> Optional[list[str]]:
    tail = VERBS.get(verb)
    return build_argv(tail, pane) if tail else None


def show_argv(target: str, pane: str) -> list[str]:
    return build_argv(["show", target, "--pane", pane], pane)


def back_argv(pane: str) -> list[str]:
    return build_argv(["show", "--back", "--pane", pane], pane)


def list_argv(kind: str, pane: str) -> Optional[list[str]]:
    """argv whose --json output feeds the list modal."""
    tails = {
        "panes": ["panes", "--json"],
        "controls": ["affordances", pane, "--usable", "--json"],
        "requests": ["requests", "--json"],
    }
    tail = tails.get(kind)
    return build_argv(tail, pane) if tail else None


def run(argv: list[str], on_done: Optional[Callable[[int, str], None]] = None):
    """Run argv in a daemon thread with a timeout; log failures; never raise."""

    def work():
        code, out = 1, ""
        try:
            p = subprocess.run(
                argv, capture_output=True, text=True, timeout=TIMEOUT_S, env=_env
            )
            code, out = p.returncode, p.stdout
            if code:
                log.warning("sidecar %s exit %s: %s", argv[1:3], code, p.stderr.strip()[:300])
        except subprocess.TimeoutExpired:
            log.warning("sidecar %s timed out after %ss", argv[1:3], TIMEOUT_S)
        except Exception as e:  # missing binary, permissions: log, don't raise
            log.warning("sidecar %s failed: %s", argv[1:3], e)
        if on_done:
            try:
                on_done(code, out)
            except Exception:
                log.exception("sidecar on_done failed")

    threading.Thread(target=work, daemon=True).start()


def parse_rows(kind: str, raw: str) -> list[dict]:
    """Normalise CLI JSON into [{"name": str, "detail": str, "id": str}] rows."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        for key in ("panes", "affordances", "requests", "items", "result"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            return []
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or item.get("device") or item.get("name") or "")
        name = str(
            item.get("label") or item.get("title") or item.get("question")
            or item.get("name") or ident
        )
        detail = str(item.get("app") or item.get("kind") or item.get("status") or "")
        if ident or name:
            rows.append({"id": ident, "name": name, "detail": detail})
    return rows
