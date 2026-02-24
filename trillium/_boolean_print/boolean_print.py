"""
Debug print wrapper that filters output based on a CSV file of ignored tags.

Usage:
    actions.user.boolean_print("repeater", "some debug info")

If "repeater" exists in debug_ignore_tags.csv, the print is skipped.
Otherwise, prints: "[repeater] some debug info"

Note: Tags are stored in CSV without brackets, but printed with brackets.
"""

import csv
from pathlib import Path
from talon import Module, resource

mod = Module()

# Cache for ignored tags to avoid reading CSV on every call
_ignored_tags = None

# Path to the CSV file
CSV_PATH = Path(__file__).parent / "debug_ignore_tags.csv"


def load_ignored_tags(file):
    """Load the list of ignored tags from the CSV file."""
    global _ignored_tags
    _ignored_tags = set()

    try:
        rows = list(csv.DictReader(file))
        for row in rows:
            tag = row.get('tag', '').strip()
            if tag:
                _ignored_tags.add(tag)
        print(f"[boolean_print] Loaded {len(_ignored_tags)} ignored tags: {_ignored_tags}")
    except Exception as e:
        print(f"[boolean_print] Error loading ignored tags: {e}")


@resource.watch(str(CSV_PATH))
def on_csv_update(f):
    """Auto-reload the CSV when it changes"""
    load_ignored_tags(f)


@mod.action_class
class Actions:
    def boolean_print(tag: str, phrase: str):
        """Print debug information unless the tag is in the ignore list"""
        global _ignored_tags

        # Lazy load on first call
        if _ignored_tags is None:
            if CSV_PATH.exists():
                with open(CSV_PATH, 'r') as f:
                    load_ignored_tags(f)
            else:
                _ignored_tags = set()

        # Only print if tag is not in the ignore list
        if tag not in _ignored_tags:
            print(f"[{tag}] {phrase}")
