"""
Write a timestamp file on Talon launch.
Used by restart scripts to detect when Talon has fully started.
"""

import os
import time
from pathlib import Path
from talon import app

TIMESTAMP_FILE = Path.home() / ".talon" / "launch_timestamp"


def write_launch_timestamp():
    """Write current timestamp to file on launch."""
    TIMESTAMP_FILE.write_text(str(time.time()))


app.register("launch", write_launch_timestamp)
