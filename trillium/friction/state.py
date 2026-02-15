"""Friction state management."""

import json
from pathlib import Path

FRICTION_STATE_FILE = Path.home() / ".talon" / "friction_state.json"
FRICTION_TIMEOUT_MS = 90_000  # 90 seconds

# Global state
friction_active = False
timeout_job = None
current_issue_id = None  # Track the ops issue ID for appending
last_issue_id = None  # Persists after friction_end for "friction more" commands
pending_scope = None  # Scope waiting for first dictation to create ticket
pending_context = None  # Context captured at friction start


def load_last_issue_id() -> str | None:
    """Load the last issue ID from disk."""
    try:
        if FRICTION_STATE_FILE.exists():
            data = json.loads(FRICTION_STATE_FILE.read_text())
            return data.get("last_issue_id")
    except Exception:
        pass
    return None


def save_last_issue_id(issue_id: str):
    """Save the last issue ID to disk."""
    print(f"[friction] Saving last issue ID: {issue_id} to {FRICTION_STATE_FILE}")
    try:
        FRICTION_STATE_FILE.write_text(json.dumps({"last_issue_id": issue_id}))
        print(f"[friction] Saved successfully")
    except Exception as e:
        print(f"[friction] Failed to save: {e}")


def reset_state():
    """Reset all friction state."""
    global friction_active, current_issue_id, pending_scope, pending_context
    friction_active = False
    current_issue_id = None
    pending_scope = None
    pending_context = None


# Load persisted state on module init
last_issue_id = load_last_issue_id()
