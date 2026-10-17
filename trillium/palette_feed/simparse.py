"""Parse the text that `speech_system._sim(phrase)` returns."""

import re
from dataclasses import dataclass

_HEADER = re.compile(r'^\[\d+\] "', re.MULTILINE)
_PATH = re.compile(r"^\s+path: (.+)$", re.MULTILINE)
_RULE = re.compile(r'^\s+rule: "(.*)"$', re.MULTILINE)


class NoMatch(Exception):
    """The phrase does not parse against any active command."""


@dataclass(frozen=True)
class SimMatch:
    rule: str
    path: str


def parse_sim(text: str) -> list[SimMatch]:
    """One SimMatch per top-level command the phrase would run (nested capture lines ignored)."""
    starts = [m.start() for m in _HEADER.finditer(text)]
    blocks = [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]
    matches = []
    for block in blocks:
        path = _PATH.search(block)
        rule = _RULE.search(block)
        if path and rule:
            matches.append(SimMatch(rule=rule.group(1), path=path.group(1)))
    return matches


def normalize_rule(rule: str) -> str:
    """Make a registry trigger and a sim rule comparable (anchors and spacing differ)."""
    return re.sub(r"\s+", "", rule).strip("^$")
