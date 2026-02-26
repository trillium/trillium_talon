"""
Write startup status file after Talon launches.
Parses the log for errors and warnings from the current startup sequence.
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

from talon import app

TALON_LOG = Path.home() / ".talon" / "talon.log"
STATUS_FILE = Path.home() / ".talon" / "startup_status.json"
STATUS_HISTORY_DIR = Path.home() / ".talon" / "startup_history"


def parse_startup_warnings(log_content: str) -> list[dict]:
    """Parse Python warnings from log content."""
    warnings = []

    for line in log_content.split("\n"):
        # Python warnings: WARNING /path/file.py:123: SyntaxWarning: message
        match = re.match(r".*WARNING\s+([^:]+):(\d+):\s+(\w+Warning):\s+(.+)", line)
        if match:
            warnings.append({
                "type": match.group(3),
                "file": match.group(1),
                "line": int(match.group(2)),
                "message": match.group(4).strip(),
            })

    return warnings


def parse_startup_errors(log_content: str) -> list[dict]:
    """Parse errors from log content."""
    errors = []
    lines = log_content.split("\n")

    for i, line in enumerate(lines):
        # TalonScript parse errors
        parse_match = re.search(r'ERROR Failed to parse TalonScript in "([^"]+)" for "([^"]+)"', line)
        if parse_match:
            errors.append({
                "type": "parse",
                "file": parse_match.group(1),
                "message": f'Failed to parse command "{parse_match.group(2)}"',
            })
            continue

        # Callback errors
        cb_match = re.search(r'ERROR cb error topic="([^"]+)" cb=(\S+)', line)
        if cb_match:
            error_msg = f"{cb_match.group(1)} callback error in {cb_match.group(2)}"
            # Look for actual error message on following lines
            for j in range(i + 1, min(i + 5, len(lines))):
                if re.match(r"^[A-Z][a-zA-Z]*Error:", lines[j]):
                    error_msg = lines[j].strip()
                    break
            errors.append({
                "type": "callback",
                "message": error_msg,
            })
            continue

    return errors


def get_startup_log_content() -> str:
    """Get log content from current startup session."""
    if not TALON_LOG.exists():
        return ""

    content = TALON_LOG.read_text()

    # Find the last "Loading Talon" marker which indicates startup began
    # Or find the last instance of the Talon version/startup banner
    markers = [
        "Loading Talon",
        "Talon starting",
        "--- Talon",
    ]

    last_start = 0
    for marker in markers:
        idx = content.rfind(marker)
        if idx > last_start:
            last_start = idx

    return content[last_start:] if last_start > 0 else content[-50000:]  # Last 50KB if no marker


def parse_summary_counts(log_content: str) -> tuple[int, int]:
    """Parse the summary error/warning counts from log."""
    error_count = 0
    warning_count = 0

    error_match = re.search(r"\[!\] (\d+) error\(s\) during startup", log_content)
    if error_match:
        error_count = int(error_match.group(1))

    warn_match = re.search(r"\[!\] (\d+) warning\(s\) during startup", log_content)
    if warn_match:
        warning_count = int(warn_match.group(1))

    return error_count, warning_count


def write_startup_status():
    """Write startup status after Talon is ready."""
    try:
        log_content = get_startup_log_content()
        error_count, warning_count = parse_summary_counts(log_content)
        errors = parse_startup_errors(log_content)
        warnings = parse_startup_warnings(log_content)

        timestamp = datetime.now().isoformat()

        status = {
            "timestamp": timestamp,
            "error_count": error_count,
            "warning_count": warning_count,
            "errors": errors,
            "warnings": warnings,
            "success": error_count == 0,
        }

        # Write current status
        STATUS_FILE.write_text(json.dumps(status, indent=2))

        # Also save to history
        STATUS_HISTORY_DIR.mkdir(exist_ok=True)
        history_file = STATUS_HISTORY_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        history_file.write_text(json.dumps(status, indent=2))

        # Clean up old history files (keep last 20)
        history_files = sorted(STATUS_HISTORY_DIR.glob("*.json"), reverse=True)
        for old_file in history_files[20:]:
            old_file.unlink()

        if errors or warnings:
            app.notify(
                f"Startup: {error_count} error(s), {warning_count} warning(s)",
                "See ~/.talon/startup_status.json for details"
            )
    except Exception as e:
        print(f"Failed to write startup status: {e}")


app.register("ready", write_startup_status)
