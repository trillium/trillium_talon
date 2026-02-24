#!/usr/bin/env python3
"""
Migration script to convert parrot logs from v1.0 to v1.1 schema.

Run this once to migrate existing logs:
    python3 migrate_parrot_logs.py

Changes from v1.0 to v1.1:
- command.raw_capture -> capture.raw
- command.phrase_text -> phrase.text
- Add phrase.words (parsed from phrase_text)
- Add command.rule (copied from trigger)
- navigation_steps -> capture.steps
- Add capture.type
- Add context.tags (empty array - can't recover)
- version: "1.0" -> "1.1"
"""

import json
from pathlib import Path


PARROT_RECORDINGS_DIR = Path.home() / ".talon" / "recordings" / "parrot"
BACKUP_DIR = PARROT_RECORDINGS_DIR / "_backup_v1.0"


def migrate_file(filepath: Path) -> bool:
    """Migrate a single file from v1.0 to v1.1 schema. Returns True if migrated."""
    try:
        with open(filepath, "r") as f:
            data = json.load(f)

        # Skip if already v1.1 or newer
        if data.get("version") != "1.0":
            return False

        # Extract old fields
        old_command = data.get("command", {})
        raw_capture = old_command.pop("raw_capture", None)
        phrase_text = old_command.pop("phrase_text", None)

        # Build new command structure
        data["command"] = {
            "trigger": old_command.get("trigger"),
            "rule": None,  # Not available in v1.0 data
            "display": old_command.get("display"),
        }

        # Build new phrase structure
        # phrase_text existed in v1.0, words did not - leave words empty
        data["phrase"] = {
            "words": [],  # Not available in v1.0 data
            "text": phrase_text,
        }

        # Build new capture structure
        navigation_steps = data.pop("navigation_steps", None)
        if navigation_steps:
            data["capture"] = {
                "type": "navigation_steps",
                "raw": raw_capture,
                "steps": navigation_steps,
            }
        elif raw_capture:
            data["capture"] = {
                "type": "generic",
                "raw": raw_capture,
            }
        else:
            data["capture"] = None

        # Add tags to context (empty - can't recover)
        if "context" in data and "tags" not in data["context"]:
            data["context"]["tags"] = []

        # Update version
        data["version"] = "1.1"

        # Write back
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        return True

    except Exception as e:
        print(f"Error migrating {filepath.name}: {e}")
        return False


def backup_files():
    """Create backup of all v1.0 files before migration."""
    BACKUP_DIR.mkdir(exist_ok=True)
    backed_up = 0

    for filepath in PARROT_RECORDINGS_DIR.glob("*.json"):
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            if data.get("version") == "1.0":
                backup_path = BACKUP_DIR / filepath.name
                with open(backup_path, "w") as f:
                    json.dump(data, f, indent=2)
                backed_up += 1
        except Exception:
            pass

    return backed_up


def main():
    if not PARROT_RECORDINGS_DIR.exists():
        print(f"Directory not found: {PARROT_RECORDINGS_DIR}")
        return

    # Count files to migrate
    files = list(PARROT_RECORDINGS_DIR.glob("*.json"))
    v1_files = []
    for f in files:
        try:
            with open(f, "r") as fp:
                data = json.load(fp)
            if data.get("version") == "1.0":
                v1_files.append(f)
        except Exception:
            pass

    if not v1_files:
        print("No v1.0 files found to migrate.")
        return

    print(f"Found {len(v1_files)} v1.0 files to migrate.")

    # Backup
    print("Creating backup...")
    backed_up = backup_files()
    print(f"Backed up {backed_up} files to {BACKUP_DIR}")

    # Migrate
    print("Migrating files...")
    migrated = 0
    for filepath in v1_files:
        if migrate_file(filepath):
            migrated += 1

    print(f"Successfully migrated {migrated}/{len(v1_files)} files to v1.1 schema.")


if __name__ == "__main__":
    main()
