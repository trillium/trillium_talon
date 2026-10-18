"""Turn Talon registry data into the JSON the palette serves. No Talon imports."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

# Captures that take free text or numbers: the app must supply a value.
OPEN_CAPTURES = frozenset(
    {"phrase", "user.text", "user.prose", "user.raw_prose", "number", "number_small"}
)
_LIST_REF = re.compile(r"\{([\w.]+)\}")
_CAPTURE_REF = re.compile(r"<([\w.]+)>")


@dataclass(frozen=True)
class RawImpl:
    """One CommandImpl reduced to plain data. `score` is ctx._active_scores, `match` is repr(ctx._match)."""

    trigger: str
    context: str
    lineno: int
    score: tuple
    match: str = ""


# Matcher reprs look like `M(M(tag=='browser') AND M(NOT M(app=='zoom')))`: M(...) nodes holding a leaf
# `key=='value'` / `key==/regex/`, a `NOT M(...)`, or `M(...) AND|OR M(...)`.
_MATCH_TOKEN = re.compile(
    r"""\s*(?:
        (?P<open>M\()
      | (?P<close>\))
      | (?P<op>AND|OR|NOT)\b
      | (?P<key>[\w.]+)==(?P<value>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|/(?:[^/\\]|\\.)*/[a-z]*)
    )""",
    re.VERBOSE,
)
_APP_KEYS = frozenset({"app", "app.name", "app.bundle", "app.exe"})


class _Unparsed(Exception):
    pass


def _tokenize(text: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    pos = 0
    text = text.strip()
    while pos < len(text):
        found = _MATCH_TOKEN.match(text, pos)
        if not found:
            raise _Unparsed(text[pos : pos + 20])
        pos = found.end()
        if found.group("open"):
            tokens.append(("open", None))
        elif found.group("close"):
            tokens.append(("close", None))
        elif found.group("op"):
            tokens.append((found.group("op"), None))
        else:
            value = found.group("value")
            tokens.append(("leaf", (found.group("key"), value[1:-1] if value[0] in "'\"" else None)))
    return tokens


def _parse_node(tokens: list[tuple[str, Any]], pos: int) -> tuple[tuple, int]:
    """Parse one `M( ... )` starting at tokens[pos]; returns (node, next position)."""
    if pos >= len(tokens) or tokens[pos][0] != "open":
        raise _Unparsed("expected M(")
    pos += 1
    kind = tokens[pos][0] if pos < len(tokens) else ""
    if kind == "leaf":
        node: tuple = ("leaf", *tokens[pos][1])
        pos += 1
    elif kind == "NOT":
        child, pos = _parse_node(tokens, pos + 1)
        node = ("not", child)
    else:
        left, pos = _parse_node(tokens, pos)
        if pos >= len(tokens) or tokens[pos][0] not in ("AND", "OR"):
            raise _Unparsed("expected AND/OR")
        op = tokens[pos][0]
        right, pos = _parse_node(tokens, pos + 1)
        node = (op, left, right)
    if pos >= len(tokens) or tokens[pos][0] != "close":
        raise _Unparsed("expected )")
    return node, pos + 1


def _required(node: tuple, keys: frozenset[str]) -> set[str] | None:
    """Values of which at least one must hold for `node` to match, or None if the node does not need one.

    Negated leaves and OR branches that skip the key do not require it, so "everything but Chrome"
    and "tag a, or not tag b" stay global.
    """
    kind = node[0]
    if kind == "leaf":
        return {node[2]} if node[1] in keys and node[2] is not None else None
    if kind == "not":
        return None
    parts = [_required(child, keys) for child in node[1:]]
    if kind == "AND":
        found = [p for p in parts if p is not None]
        return set().union(*found) if found else None
    if any(p is None for p in parts):
        return None
    return set().union(*parts)


def context_scope(match: str) -> dict[str, Any]:
    """What a context needs from the current Talon scope: {"scope": app|tag|global, "apps": [...], "tags": [...]}.

    Only the commands Talon has active are served, so an "app" command is one whose context names the
    frontmost app. Anything unparseable (`None`, MatchAny, a future repr) is global: never hide a command.
    """
    try:
        tokens = _tokenize(match)
        tree, end = _parse_node(tokens, 0)
        if end != len(tokens):
            raise _Unparsed("trailing tokens")
    except (_Unparsed, IndexError):
        return {"scope": "global", "apps": [], "tags": []}
    apps = sorted(_required(tree, _APP_KEYS) or ())
    tags = sorted(_required(tree, frozenset({"tag"})) or ())
    scope = "app" if apps else "tag" if tags else "global"
    return {"scope": scope, "apps": apps, "tags": tags}


def command_id(context: str, lineno: int, trigger: str) -> str:
    """Stable id for a command definition."""
    digest = hashlib.sha1(f"{context}:{lineno}:{trigger}".encode("utf-8")).hexdigest()
    return digest[:10]


def pick_winner(impls: list[RawImpl]) -> RawImpl:
    """Highest `_active_scores` wins; on a tie the last registered impl wins.

    Talon runs the last-registered impl on equal scores (verified with speech_system._sim),
    so the feed's context, lineno and id must name that copy. `max` keeps the first of equal
    maxima, hence the reversal.
    """
    return max(reversed(impls), key=lambda impl: impl.score)


def describe_slots(rule: str, list_size: Callable[[str], int]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for name in _LIST_REF.findall(rule):
        slots.append({"name": name, "type": "list", "n": list_size(name)})
    for name in _CAPTURE_REF.findall(rule):
        slots.append({"name": name, "type": "capture", "open": name in OPEN_CAPTURES})
    return slots


def classify(rule: str) -> str:
    if _CAPTURE_REF.search(rule):
        return "capture"
    if _LIST_REF.search(rule):
        return "list"
    return "literal"


def serialize_commands(
    grouped: Iterable[list[RawImpl]], list_size: Callable[[str], int]
) -> dict[str, Any]:
    """Winning impl per rule, sorted by rule, with a content hash for caching."""
    commands = []
    for impls in grouped:
        winner = pick_winner(impls)
        commands.append(
            {
                "id": command_id(winner.context, winner.lineno, winner.trigger),
                "rule": winner.trigger,
                "kind": classify(winner.trigger),
                "slots": describe_slots(winner.trigger, list_size),
                "context": winner.context,
                "lineno": winner.lineno,
                "shadowed": len(impls) - 1,
                **context_scope(winner.match),
            }
        )
    commands.sort(key=lambda c: (c["rule"], c["id"]))
    return {
        # scope is in the digest so a client holding an older, scope-less list refetches once.
        "commands_rev": _digest([[c["id"], c["rule"], c["scope"], c["apps"], c["tags"]] for c in commands]),
        "count": len(commands),
        "commands": commands,
    }


def referenced_lists(commands: Iterable[Mapping[str, Any]]) -> set[str]:
    """List names that active rules use: the only ones /lists/NAME may serve."""
    return {
        slot["name"]
        for command in commands
        for slot in command["slots"]
        if slot["type"] == "list"
    }


def serialize_state(
    *,
    host: str,
    ts: str,
    app: Mapping[str, Any],
    window: Mapping[str, Any],
    modes: Iterable[str],
    tags: Iterable[str],
    language: str,
    commands_rev: str,
) -> dict[str, Any]:
    body = {
        "app": {"name": app.get("name", ""), "bundle": app.get("bundle", "")},
        "window": {
            "title": window.get("title", ""),
            "filename": window.get("filename", ""),
            "file_ext": window.get("file_ext", ""),
        },
        "modes": sorted(modes),
        "tags": sorted(tags),
        "language": language,
        "commands_rev": commands_rev,
    }
    return {"host": host, "ts": ts, "rev": _digest(body), **body}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:16]
