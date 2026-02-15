"""Manager for adding/removing commands from excluded_commands.csv"""

import csv
from pathlib import Path
from talon import Module, actions, app

mod = Module()

# Path to the excluded commands CSV file
EXCLUDED_COMMANDS_PATH = Path(__file__).parent / "excluded_commands.csv"


def read_excluded_commands():
    """Read all excluded commands from CSV, preserving descriptions"""
    commands = {}
    try:
        with open(EXCLUDED_COMMANDS_PATH, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
            if len(rows) >= 1:
                # Skip header row
                for row in rows[1:]:
                    if len(row) == 0:
                        continue
                    trigger = row[0].strip()
                    description = row[1].strip() if len(row) > 1 else ""
                    if trigger:
                        commands[trigger] = description
    except FileNotFoundError:
        # File doesn't exist yet, return empty dict
        pass
    return commands


def write_excluded_commands(commands):
    """Write all excluded commands back to CSV"""
    with open(EXCLUDED_COMMANDS_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Command trigger", "Description"])
        for trigger, description in commands.items():
            writer.writerow([trigger, description])


@mod.action_class
class Actions:
    def repeater_exclude_last_command():
        """Add the last executed command to the exclusion list"""
        last_cmd, _ = actions.core.last_command()

        if not last_cmd:
            app.notify("No command to exclude")
            return

        trigger = last_cmd.trigger

        # Read current exclusions
        commands = read_excluded_commands()

        if trigger in commands:
            app.notify(f"'{trigger}' is already excluded")
            return

        # Add the command with a generic description
        commands[trigger] = "User excluded command"

        # Write back to CSV
        write_excluded_commands(commands)

        app.notify(f"Excluded: {trigger}")
        actions.user.boolean_print("repeater", f"Added '{trigger}' to exclusions")

    def repeater_include_last_command():
        """Remove the last executed command from the exclusion list"""
        last_cmd, _ = actions.core.last_command()

        if not last_cmd:
            app.notify("No command to include")
            return

        trigger = last_cmd.trigger

        # Read current exclusions
        commands = read_excluded_commands()

        if trigger not in commands:
            app.notify(f"'{trigger}' is not excluded")
            return

        # Remove the command
        del commands[trigger]

        # Write back to CSV
        write_excluded_commands(commands)

        app.notify(f"Included: {trigger}")
        actions.user.boolean_print("repeater", f"Removed '{trigger}' from exclusions")

    def repeater_list_excluded():
        """List all excluded commands"""
        commands = read_excluded_commands()

        if not commands:
            app.notify("No commands are excluded")
            return

        count = len(commands)
        triggers = list(commands.keys())

        # Show first few in notification
        preview = ", ".join(triggers[:3])
        if count > 3:
            preview += f"... ({count} total)"

        app.notify(f"Excluded: {preview}")
        actions.user.boolean_print("repeater", f"Excluded commands ({count}):")
        for trigger, description in commands.items():
            actions.user.boolean_print("repeater", f"  - {trigger}: {description}")
