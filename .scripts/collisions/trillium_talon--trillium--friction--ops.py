"""Ops integration for friction tickets."""

import subprocess
from pathlib import Path

OPS_DB = Path.home() / ".openclaw" / ".ops" / "beads.db"


def create_issue(title: str, notes: str, scope: str = "general", needs_review: bool = False) -> str | None:
    """Create an ops issue and return the issue ID."""
    print(f"[friction] Creating ops issue: {title[:50]}... (scope: {scope}, needs_review: {needs_review})")
    labels = f"friction,triage,{scope}"
    if needs_review:
        labels += ",review"
    try:
        result = subprocess.run(
            ["ops", "--db", str(OPS_DB), "create", "--title", title, "--type", "task", "--priority", "3",
             "--labels", labels, "--notes", notes, "--silent"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        print(f"[friction] ops create returncode: {result.returncode}")
        print(f"[friction] ops create stdout: {result.stdout}")
        print(f"[friction] ops create stderr: {result.stderr}")
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"[friction] ops create failed: {result.stderr}")
    except Exception as e:
        print(f"[friction] ops create exception: {e}")
    return None


def append_to_issue(issue_id: str, text: str):
    """Append text to an ops issue's notes."""
    try:
        subprocess.run(
            ["ops", "--db", str(OPS_DB), "update", issue_id, "--append-notes", text],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        pass
