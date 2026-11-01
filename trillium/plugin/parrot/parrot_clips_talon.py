"""Talon side of parrot clips: settings, 'parrot missed [<sound>]', kill switch."""

import logging

from talon import Context, Module, actions, app, cron, settings

from .parrot_clips import service

mod = Module()
ctx = Context()

mod.setting(
    "parrot_clips_enabled",
    type=bool,
    default=True,
    desc="Kill switch: keep a short RAM audio buffer and save clips around mouth sounds",
)
mod.setting(
    "parrot_clips_dir",
    type=str,
    default="",
    desc="Clip folder; empty = ~/.talon/parrot_clips",
)
mod.setting(
    "parrot_clips_buffer_seconds",
    type=float,
    default=5.0,
    desc="RAM-only rolling buffer length",
)
mod.setting(
    "parrot_clips_missed_seconds",
    type=float,
    default=5.0,
    desc="Audio saved by 'parrot missed'",
)
mod.setting(
    "parrot_clips_power_floor",
    type=float,
    default=20.0,
    desc="Frame power that counts as a sound event",
)
mod.setting(
    "parrot_clips_max_mb",
    type=float,
    default=200.0,
    desc="Clip folder size cap; oldest auto clips go first",
)
mod.setting(
    "parrot_clips_max_age_days",
    type=float,
    default=30.0,
    desc="Clips older than this are pruned",
)
mod.setting("parrot_clips_max_clips", type=int, default=2000, desc="Clip count cap")

mod.list(
    "parrot_missed_sound",
    desc="Spoken sound names -> parrot model labels (clip folder names)",
)

SOUNDS = {
    "click": "alviolar_tongue_click",
    "tongue click": "alviolar_tongue_click",
    "kitty": "kitty_cmere_tongue_click",
    "pop": "lip_pop",
    "lip pop": "lip_pop",
    "hiss": "hiss_sound",
    "shh": "shh_sound",
    "oink": "piggy_oink_sound",
    "clap": "clapping_in_front_of_myself",
}
ctx.lists["user.parrot_missed_sound"] = SOUNDS

_runtime_off = [False]  # voice kill switch, on top of the setting
_sample_rate = [16000]


DEFAULTS = {
    "user.parrot_clips_enabled": True,
    "user.parrot_clips_dir": "",
    "user.parrot_clips_buffer_seconds": 5.0,
    "user.parrot_clips_missed_seconds": 5.0,
    "user.parrot_clips_power_floor": 20.0,
    "user.parrot_clips_max_mb": 200.0,
    "user.parrot_clips_max_age_days": 30.0,
    "user.parrot_clips_max_clips": 2000,
}

_configured = [False]  # True once every setting was read for real
_hooked = [False]
_retries = [0]


def _get(name: str):
    """A setting, or its default. Talon raises KeyError before the module that
    declares it has finished loading."""
    try:
        value = settings.get(name)
    except Exception:
        _configured[0] = False
        return DEFAULTS[name]
    return DEFAULTS[name] if value is None else value


def apply_settings(*_args) -> None:
    """Configure the clip service. Safe to call any time, any number of times."""
    from pathlib import Path

    try:
        _configured[0] = True  # _get() clears this if any read falls back
        root = _get("user.parrot_clips_dir") or str(
            Path.home() / ".talon" / "parrot_clips"
        )
        service.configure(
            enabled=bool(_get("user.parrot_clips_enabled")) and not _runtime_off[0],
            root=root,
            sample_rate=_sample_rate[0],
            buffer_seconds=_get("user.parrot_clips_buffer_seconds"),
            power_floor=_get("user.parrot_clips_power_floor"),
            max_mb=_get("user.parrot_clips_max_mb"),
            max_age_days=_get("user.parrot_clips_max_age_days"),
            max_clips=_get("user.parrot_clips_max_clips"),
            missed_seconds=_get("user.parrot_clips_missed_seconds"),
        )
    except Exception:
        _configured[0] = False
        logging.exception("[parrot_clips] configure failed")


def ensure_configured() -> None:
    """Lazy, retry-safe: configure with real settings if that has not worked yet."""
    if not _configured[0]:
        apply_settings()


def _hook_settings(*_args) -> None:
    """Runs once Talon is ready (or on the first retry): settings now exist."""
    ensure_configured()
    if _hooked[0] or not _configured[0]:
        return
    try:
        settings.register("user.parrot_clips_enabled", apply_settings)
        _hooked[0] = True
    except Exception:
        logging.exception("[parrot_clips] could not watch settings")


def _retry() -> None:
    _hook_settings()
    if not (_configured[0] and _hooked[0]) and _retries[0] < 10:
        _retries[0] += 1
        try:
            cron.after("2s", _retry)
        except Exception:
            pass


def start(sample_rate: int) -> None:
    """Called by parrot_integration at import. Reads no settings: they do not
    exist until this module has finished loading."""
    _sample_rate[0] = int(sample_rate)
    try:
        app.register("ready", _hook_settings)
        cron.after("2s", _retry)
    except Exception:
        logging.exception("[parrot_clips] could not defer configure")


@mod.action_class
class Actions:
    def parrot_missed(sound: str = ""):
        """Save the last few seconds of mic audio from RAM as a sound that should have registered"""
        ensure_configured()
        if not service.enabled:
            actions.user.notify("parrot clips are off", 1)
            return
        ok = service.mark_missed(sound or None)
        actions.user.notify(
            (
                f"kept {sound or 'unlabeled'}"
                if ok
                else "nothing to keep (queue full or no audio yet)"
            ),
            1,
        )

    def parrot_clips_on():
        """Turn parrot clip capture on"""
        _runtime_off[0] = False
        apply_settings()

    def parrot_clips_off():
        """Turn parrot clip capture off and drop the RAM buffer"""
        _runtime_off[0] = True
        apply_settings()
