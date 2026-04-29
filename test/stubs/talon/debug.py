"""Talon debug stubs."""

import traceback


def log_exception(msg=""):
    """Log an exception. In tests, prints the traceback."""
    traceback.print_exc()
