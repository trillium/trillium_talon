#!/bin/bash
# Wrapper script to call the Python version using Talon's Python
exec "$HOME/.talon/.venv/bin/python" "$HOME/.talon/user/trillium/happy_run.py" "$@"
