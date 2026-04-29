"""Context capture utilities for friction reports."""

import json
from datetime import datetime
from pathlib import Path

from talon import registry, scope

COMMANDS_JSONL = Path.home() / ".talon" / "recordings" / "command_history.jsonl"


def get_recent_commands(limit: int = 10) -> list[dict]:
    """Get recent commands from JSONL command history (tail read, instant)."""
    if not COMMANDS_JSONL.exists():
        return []

    try:
        # Read last 8KB — more than enough for 10 commands
        size = COMMANDS_JSONL.stat().st_size
        read_bytes = min(size, 8192)
        with open(COMMANDS_JSONL, "rb") as f:
            f.seek(max(0, size - read_bytes))
            tail = f.read().decode("utf-8", errors="replace")

        lines = tail.strip().split("\n")
        # Skip first line (may be partial from seek)
        if size > read_bytes:
            lines = lines[1:]

        commands = []
        for line in reversed(lines[-limit:]):
            try:
                data = json.loads(line)
                commands.append({
                    "timestamp": data.get("timestamp", ""),
                    "trigger": data.get("trigger", ""),
                })
            except Exception:
                pass
        return commands[:limit]
    except Exception:
        return []


def get_talon_context() -> dict:
    """Capture current Talon context."""
    ctx = {}

    try:
        ctx["app_name"] = scope.get("app.name", "")
        ctx["app_bundle"] = scope.get("app.bundle", "")
        ctx["win_title"] = scope.get("win.title", "")
        ctx["mode"] = list(scope.get("mode", set()))
        ctx["tags"] = list(registry.tags)
    except Exception as e:
        ctx["error"] = str(e)

    return ctx


def build_context_notes(scope_utterance: str) -> str:
    """Build context notes for a friction report."""
    context = get_talon_context()
    recent = get_recent_commands(10)

    notes_parts = [
        f"**Captured:** {datetime.now().isoformat()}",
        f"**App:** {context.get('app_name', 'unknown')} ({context.get('app_bundle', '')})",
        f"**Window:** {context.get('win_title', '')}",
        f"**Scope utterance:** {scope_utterance}",
    ]
    if recent:
        notes_parts.append("\n**Recent commands:**")
        for cmd in recent[:5]:
            notes_parts.append(f"- {cmd.get('trigger', '')}")

    return "\n".join(notes_parts)
