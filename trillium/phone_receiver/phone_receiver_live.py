"""Talon glue: the `user.phone_receiver_enabled` gate and one action to hand a TPE1 payload
to the live engine. Settings and Python only: no voice commands, no socket, no recordings.

The setting defaults to off. With it off `user.phone_receiver_handle` returns `disabled`
and never touches the engine; microphone dictation is unaffected either way, because the
encoder is swapped only for the duration of one injected utterance. The action also refuses
while `speech.record_all` is on (`record_all_on`). See docs/phone-receiver.md.
"""

from talon import Module, settings, speech_system

from .live import LiveInstall

SETTING = "user.phone_receiver_enabled"

mod = Module()

mod.setting(
    "phone_receiver_enabled",
    type=bool,
    default=False,
    desc="If true, user.phone_receiver_handle feeds a phone-computed acoustic emission "
    "to the live speech engine in place of its encoder. Off by default; refused while "
    "speech.record_all is on.",
)


def _engine():
    return speech_system.engine.engine


def _enabled() -> bool:
    return bool(settings.get(SETTING))


def _record_all() -> bool:
    # A missing or unreadable setting counts as on: refuse rather than risk a recording.
    try:
        return bool(settings.get("speech.record_all"))
    except Exception:  # noqa: BLE001
        return True


# Hot reload re-executes this module; the install holds no threads or sockets, so a fresh
# one per load is enough.
_install = LiveInstall(_engine, _enabled, _record_all)


@mod.action_class
class Actions:
    def phone_receiver_handle(payload: bytes) -> str:
        """Validate a TPE1 emission and run it through the live engine; returns "ok" or an error code"""
        r = _install.handle(payload)
        return "ok" if r.ok else (r.error or "error")
