"""Linux-only: send herdr's real prefix key (read from ~/.config/herdr/config.toml).

macOS hard-codes ctrl-b in herder_panel.talon. This module only backs the
Linux-scoped herdr_prefix_linux.talon, so nothing on macOS changes.
"""

from pathlib import Path

from talon import Module, actions

try:
    import tomllib
except ImportError:  # Python < 3.11 (older Talon builds, e.g. macOS); never used there
    tomllib = None

mod = Module()

CONFIG = Path.home() / ".config" / "herdr" / "config.toml"
DEFAULT_PREFIX = "ctrl+b"


def _talon_key(herdr_key: str) -> str:
    """'ctrl+space' (herdr) -> 'ctrl-space' (Talon)."""
    return herdr_key.strip().lower().replace("+", "-")


def herdr_prefix_lookup():
    """(talon_key, source) where source says what was read. Never silent: any
    fallback to herdr's documented default (ctrl+b, `herdr --default-config`)
    prints which file it read and why."""
    if tomllib is None:
        print(f"[herdr_prefix_linux] FALLBACK to {DEFAULT_PREFIX}: no tomllib in this Python")
        return _talon_key(DEFAULT_PREFIX), f"fallback {DEFAULT_PREFIX}: no tomllib"
    try:
        with open(CONFIG, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        reason = f"{CONFIG} not found"
    except (OSError, tomllib.TOMLDecodeError) as e:
        reason = f"{CONFIG} unreadable ({e})"
    else:
        value = data.get("keys", {}).get("prefix")
        if isinstance(value, str) and value.strip():
            return _talon_key(value), f"{CONFIG} [keys] prefix = {value!r}"
        reason = f"{CONFIG} has no [keys] prefix string (keys section: {sorted(data.get('keys', {}))[:6]})"
    print(f"[herdr_prefix_linux] FALLBACK to {DEFAULT_PREFIX}: {reason}")
    return _talon_key(DEFAULT_PREFIX), f"fallback {DEFAULT_PREFIX}: {reason}"


def herdr_prefix_key() -> str:
    return herdr_prefix_lookup()[0]


@mod.action_class
class Actions:
    def herdr_send_prefix(letter: str = ""):
        """Press herdr's prefix key (from its config), then optionally a letter (Linux)."""
        actions.key(herdr_prefix_key())
        if letter:
            actions.sleep("30ms")
            actions.key(letter)

    def herdr_prefix_key_name() -> str:
        """Return herdr's configured prefix as a Talon key string (Linux)."""
        return herdr_prefix_key()
