"""Turn Talon registry data into the JSON the palette serves. No Talon imports."""

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
    """One CommandImpl reduced to plain data. `score` is ctx._active_scores."""

    trigger: str
    context: str
    lineno: int
    score: tuple


def impl_to_raw(impl: Any) -> RawImpl:
    """Reduce one live Talon CommandImpl to plain data, tolerating both shapes Talon ships.

    Talon 0.4.0 (115.0) has CommandImpl(ctx, rule, script, experiments) with no `trigger` and no
    `lineno`: the rule text is `impl.rule.rule` and the line is `impl.script.start_line`. Builds with
    the CommandImpl(ScriptImpl) refactor (0.4.0-1561-9c3d and later) answer both directly. The newer,
    Talon-computed values win where present, so the newer build's output cannot change; the fallbacks
    reproduce them — the 18 rules active on both builds in the same file yielded byte-identical ids
    (task-ykd7c). Every read is a `getattr` chain, so a future build that renames rather than deletes
    degrades instead of failing the request.
    """
    rule = getattr(impl, "rule", None)
    ctx = getattr(impl, "ctx", None)
    lineno = getattr(impl, "lineno", None)
    if lineno is None:
        lineno = getattr(getattr(impl, "script", None), "start_line", 0) or 0
    return RawImpl(
        trigger=str(getattr(impl, "trigger", None) or getattr(rule, "rule", "") or ""),
        context=str(getattr(ctx, "path", str(ctx))),
        lineno=int(lineno),
        score=tuple(getattr(ctx, "_active_scores", ()) or ()),
    )


def command_id(context: str, lineno: int, trigger: str) -> str:
    """Stable id for a command definition."""
    digest = hashlib.sha1(f"{context}:{lineno}:{trigger}".encode("utf-8")).hexdigest()
    return digest[:10]


def pick_winner(impls: list[RawImpl]) -> RawImpl:
    """Highest `_active_scores` wins; ties go to the first registered."""
    return max(impls, key=lambda impl: impl.score)


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
            }
        )
    commands.sort(key=lambda c: (c["rule"], c["id"]))
    return {
        "commands_rev": _digest([[c["id"], c["rule"]] for c in commands]),
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
