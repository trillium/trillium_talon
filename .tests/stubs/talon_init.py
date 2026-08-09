"""talon_init stub — Talon runtime bootstrap values.

The production on_phrase/analyze_phrase chain imports TALON_HOME for path
resolution. In tests any directory is fine since get_path() is only called
on filenames that don't exist.
"""

from pathlib import Path

TALON_HOME = str(Path(__file__).resolve().parent)
