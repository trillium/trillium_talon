"""Context capture utilities for friction reports."""

import json
from datetime import datetime
from pathlib import Path

from talon import registry, scope

RECORDINGS_DIR = Path.home() / ".talon" / "recordings" / "commands"


def get_recent_commands(limit: int = 10) -> list[dict]:
    """Get recent commands from recordings directory."""
    if not RECORDINGS_DIR.exists():
        return []

    files = sorted(RECORDINGS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    commands = []
    for f in files[:limit]:
        try:
            data = json.loads(f.read_text())
            commands.append({
                "timestamp": data.get("timestamp", ""),
                "trigger": data.get("command", {}).get("trigger", ""),
            })
        except Exception:
            pass
    return commands


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
