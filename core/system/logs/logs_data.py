"""Log data parsing — pure log file introspection with no Talon imports.

Provides LogEntry, log parsing, and filtering used by logs_overlay.
"""

import os
import re
from dataclasses import dataclass, field

# ── Log format ──
# 2026-05-17 05:28:52.844 DEBUG [+] /Users/trilliumsmith/...
# 2026-05-17 09:55:06.095 WARNING [watchdog] "Cron.interval..." @2.0s
# 2026-05-17 10:05:37.569    IO Twitch: http_request parse error...
# 2026-05-18 17:58:20.520 ERROR    17: ...

_TIMESTAMP_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"(DEBUG|IO|WARNING|ERROR)\s+"
    r"(.*)"
)

_CATEGORY_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)")

LEVEL_ORDER = {"DEBUG": 0, "IO": 1, "WARNING": 2, "ERROR": 3}

MAX_ROWS = 14


@dataclass
class LogEntry:
    timestamp: str
    level: str
    category: str
    message: str
    raw: str
    continuation_count: int = 0
    continuation_lines: list[str] = field(default_factory=list)


def _read_tail(path: str, max_lines: int) -> list[str]:
    """Read the last max_lines lines from a file efficiently."""
    try:
        file_size = os.path.getsize(path)
    except OSError:
        return []

    if file_size == 0:
        return []

    # Estimate ~150 bytes per line, overshoot to be safe
    chunk_size = min(file_size, max_lines * 200)
    lines: list[str] = []

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if chunk_size < file_size:
                f.seek(file_size - chunk_size)
                f.readline()  # discard partial first line
            lines = f.readlines()
    except OSError:
        return []

    # If we didn't get enough lines, read more
    if len(lines) < max_lines and chunk_size < file_size:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return []

    return lines[-max_lines:]


def parse_talon_log(path: str, max_lines: int = 1000) -> list[LogEntry]:
    """Parse the last max_lines lines of the Talon log file.

    Returns entries in reverse order (most recent first).
    Multi-line entries (stack traces) are collapsed into the parent entry
    with a (+N lines) suffix.
    """
    raw_lines = _read_tail(path, max_lines)
    entries: list[LogEntry] = []

    for line in raw_lines:
        line = line.rstrip("\n\r")
        if not line:
            continue

        m = _TIMESTAMP_RE.match(line)
        if m:
            timestamp = m.group(1)
            level = m.group(2).upper()
            rest = m.group(3).strip()

            # Extract category if present: [word] ...
            category = ""
            cm = _CATEGORY_RE.match(rest)
            if cm:
                category = cm.group(1)
                rest = cm.group(2).strip()

            entries.append(LogEntry(
                timestamp=timestamp,
                level=level,
                category=category,
                message=rest,
                raw=line,
            ))
        else:
            # Continuation line — append to previous entry
            if entries:
                entries[-1].continuation_count += 1
                entries[-1].continuation_lines.append(line)

    # Add continuation indicators
    for e in entries:
        if e.continuation_count > 0:
            e.message = f"{e.message} (+{e.continuation_count} lines)"

    entries.reverse()
    return entries


def filter_entries(
    entries: list[LogEntry],
    level_min: str | None = None,
    category: str | None = None,
    search: str | None = None,
    ignore_patterns: list[str] | None = None,
) -> list[LogEntry]:
    """Filter log entries by level, category, and/or search text.

    level_min: minimum level to show ("DEBUG"=all, "IO", "WARNING", "ERROR")
    category: substring match against entry.category (case-insensitive)
    search: substring match against entry.message (case-insensitive)
    ignore_patterns: list of substrings — entries whose message contains any of
                     these are excluded (case-insensitive blocklist)
    """
    result = entries

    if level_min and level_min in LEVEL_ORDER:
        min_ord = LEVEL_ORDER[level_min]
        result = [e for e in result if LEVEL_ORDER.get(e.level, 0) >= min_ord]

    if category:
        cat_lower = category.lower()
        result = [e for e in result if cat_lower in e.category.lower()]

    if search:
        search_lower = search.lower()
        result = [e for e in result if search_lower in e.message.lower()]

    if ignore_patterns:
        lower_patterns = [p.lower() for p in ignore_patterns]
        result = [
            e for e in result
            if not any(p in e.message.lower() for p in lower_patterns)
        ]

    return result
