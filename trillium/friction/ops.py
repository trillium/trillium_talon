"""Friction capture — JSONL-based local storage.

Captures friction events instantly to a local JSONL file with zero dependencies.
A separate triage step promotes entries into real beads (bd/ops/life/ideas) later.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

FRICTION_LOG = Path.home() / ".talon" / "friction.jsonl"


def create_issue(title: str, notes: str, scope: str = "general", needs_review: bool = False) -> str | None:
    """Create a friction entry and return the entry ID."""
    issue_id = f"friction-{uuid.uuid4().hex[:6]}"
    labels = ["friction", "triage", scope]
    if needs_review:
        labels.append("review")
    entry = {
        "type": "create",
        "id": issue_id,
        "title": title,
        "notes": notes,
        "scope": scope,
        "needs_review": needs_review,
        "labels": labels,
        "created": datetime.now().isoformat(),
    }
    try:
        with open(FRICTION_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[friction] Saved to JSONL: {issue_id} — {title[:50]}")
        return issue_id
    except Exception as e:
        print(f"[friction] JSONL write failed: {e}")
        return None


def append_to_issue(issue_id: str, text: str):
    """Append text to a friction entry."""
    entry = {
        "type": "append",
        "id": issue_id,
        "text": text,
        "timestamp": datetime.now().isoformat(),
    }
    try:
        with open(FRICTION_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
