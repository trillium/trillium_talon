#!/usr/bin/env python3
"""Apply cursorless VSCode settings from vscode-settings.jsonc into the local VSCode settings.json.

Merges cursorless.* keys into the existing settings file, preserving all other settings.
Handles JSONC (trailing commas, comments) in both input and output.

Usage:
    python3 apply-vscode-settings.py [--dry-run]
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

VSCODE_SETTINGS_PATHS = [
    Path.home() / "Library/Application Support/Code/User/settings.json",
    Path.home() / ".config/Code/User/settings.json",  # Linux
]

SOURCE = Path(__file__).parent / "vscode-settings.jsonc"


def strip_jsonc(text: str) -> str:
    """Strip // comments and trailing commas so standard json can parse it."""
    # Remove single-line comments
    text = re.sub(r'//[^\n]*', '', text)
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def find_vscode_settings() -> Path | None:
    for p in VSCODE_SETTINGS_PATHS:
        if p.exists():
            return p
    return None


def main():
    dry_run = "--dry-run" in sys.argv

    dest = find_vscode_settings()
    if not dest:
        print("ERROR: Could not find VSCode settings.json", file=sys.stderr)
        sys.exit(1)

    # Parse source cursorless settings
    source_text = SOURCE.read_text()
    source_data = json.loads(strip_jsonc(source_text))
    cursorless_keys = {k: v for k, v in source_data.items() if k.startswith("cursorless.")}

    # Parse existing VSCode settings (JSONC)
    dest_text = dest.read_text()
    dest_data = json.loads(strip_jsonc(dest_text))

    # Show what will change
    changed = {}
    added = {}
    for k, v in cursorless_keys.items():
        if k not in dest_data:
            added[k] = v
        elif dest_data[k] != v:
            changed[k] = {"old": dest_data[k], "new": v}

    if not changed and not added:
        print("Already up to date — no changes needed.")
        return

    if added:
        print(f"Adding {len(added)} keys:")
        for k, v in added.items():
            print(f"  + {k}: {json.dumps(v)}")
    if changed:
        print(f"Updating {len(changed)} keys:")
        for k, diff in changed.items():
            print(f"  ~ {k}")
            print(f"      old: {json.dumps(diff['old'])}")
            print(f"      new: {json.dumps(diff['new'])}")

    if dry_run:
        print("\n--dry-run: no changes written.")
        return

    # Backup
    backup = dest.with_suffix(".json.bak")
    shutil.copy2(dest, backup)
    print(f"\nBacked up to {backup}")

    # Merge and write — preserve JSONC format by doing line-based replacement
    # For simplicity, write clean JSON (VSCode handles it fine)
    dest_data.update(cursorless_keys)

    # Write back as JSONC with trailing commas (VSCode style)
    out = json.dumps(dest_data, indent=2)
    # Add trailing commas after each value line (VSCode expects JSONC)
    out = re.sub(r'([^{[\s])(\n\s*[}\]])', r'\1,\2', out)
    dest.write_text(out)
    print(f"Written to {dest}")


if __name__ == "__main__":
    main()
