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
    "next": ["invoke", "{pane}", "app.pdf-next"],
    "previous": ["invoke", "{pane}", "app.pdf-prev"],
    "up": ["invoke", "{pane}", "scroll", "--direction", "up"],
    "down": ["invoke", "{pane}", "scroll", "--direction", "down"],
    "top": ["invoke", "{pane}", "scroll", "--direction", "top"],
    "bottom": ["invoke", "{pane}", "scroll", "--direction", "bottom"],
}

# Every spoken command: (spoken form, one-line description, scope). "global" rules
# live in sidecar.talon, "modal" rules in sidecar_list_active.talon (only while a
# list modal is open). The footer, the help modal and the .talon-drift test all
# read this table. Spoken forms use <...> for slots, e.g. "pick <N>".
COMMANDS: list[tuple[str, str, str]] = [
    ("sidecar next", "Next page on the current pane", "global"),
    ("sidecar previous", "Previous page on the current pane", "global"),
    ("sidecar up", "Scroll up", "global"),
    ("sidecar down", "Scroll down", "global"),
    ("sidecar top", "Jump to the top", "global"),
    ("sidecar bottom", "Jump to the bottom", "global"),
    ("sidecar show <view>", "Show a named view on the current pane", "global"),
    ("sidecar back", "Restore what the pane showed before", "global"),
    ("sidecar pane <name>", "Choose the current pane by name (main, chrome)", "global"),
    ("sidecar list", "List panes; say a number to choose one", "global"),
    ("sidecar views", "List the named views you can show", "global"),
    ("sidecar controls", "List the current pane's controls", "global"),
    ("sidecar requests", "List open requests", "global"),
    ("sidecar help", "List every sidecar voice command", "global"),
    ("<N>", "Choose a row by its letter word (air = A) or number", "modal"),
    ("pick <N>", "Same, with the word pick first", "modal"),
    ("sidecar pane <N>", "Choose a pane by letter word or number", "modal"),
    ("sidecar close", "Close the open list", "modal"),
]

# Modal commands that make sense per list kind, in footer order.
_FOOTER = {
    "panes": ["<N>", "sidecar pane <N>", "sidecar help", "sidecar close"],
    "views": ["<N>", "sidecar help", "sidecar close"],
    "controls": ["<N>", "sidecar help", "sidecar close"],
    "requests": ["<N>", "sidecar help", "sidecar close"],
    "help": ["sidecar close"],
}

# Spoken alphabet words, as bound by <user.letter>.
LETTER_WORDS = (
    "air bat cap drum each fine gust harp sit jury crunch look made near odd "
    "pit quench red sun trap urge vest whale plex yank zip"
).split()


def footer_text(kind: str, count: int) -> str:
    """Spoken commands valid right now, e.g. 'Say: air to pick A ...'."""
    known = {spoken for spoken, _, _ in COMMANDS}
    parts = []
    for spoken in _FOOTER.get(kind, ["sidecar close"]):
        assert spoken in known, spoken
        if "<N>" in spoken:
            if not count:
                continue
            w = LETTER_WORDS[0]
            spoken = spoken.replace("<N>", w)
            if spoken == w:
                spoken = f"{w} to pick A (or 1)"
            else:
                spoken += " (or 1)"
        parts.append(spoken)
    return "Say: " + "  ·  ".join(parts)


def help_rows() -> list[dict]:
    return [{"id": "", "name": s, "detail": d} for s, d, _ in COMMANDS]


def friendly_pane_name(pane: dict, aliases: dict[str, str]) -> str:
    """Human name for a pane: spoken alias, else what it is showing."""
    for alias, pid in aliases.items():
        if pid == pane.get("id"):
            return f"{alias.capitalize()} pane"
    app = str(pane.get("app") or "")
    if not app:
        return "Idle pane" if pane.get("mode") in ("", "default", None) else "Pane"
    if app.startswith("show-"):
        return "Showing a page"
    return f"{app.replace('-', ' ').capitalize()} pane"


def decorate_panes(rows: list[dict], aliases: dict[str, str], current: str) -> list[dict]:
    """Panes rows: friendly name first, raw id as the small detail, current marked."""
    out = []
    for r in rows:
        pane = {"id": r["id"], "app": r.get("app", ""), "mode": r.get("mode", "")}
        out.append(
            {
                "id": r["id"],
                "name": friendly_pane_name(pane, aliases),
                "detail": r["id"],
                "current": r["id"] == current,
            }
        )
    return out


_env = os.environ.copy()
_env["PATH"] = ":".join(
    [
        "/opt/homebrew/bin",
        str(Path.home() / ".local" / "bin"),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        _env.get("PATH", ""),
    ]
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
                log.warning(
                    "sidecar %s exit %s: %s", argv[1:3], code, p.stderr.strip()[:300]
                )
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
            item.get("label")
            or item.get("title")
            or item.get("question")
            or item.get("name")
            or ident
        )
        detail = str(item.get("app") or item.get("kind") or item.get("status") or "")
        if ident or name:
            row = {"id": ident, "name": name, "detail": detail}
            if kind == "panes":
                row["app"] = str(item.get("app") or "")
                row["mode"] = str(item.get("mode") or "")
            rows.append(row)
    return rows
