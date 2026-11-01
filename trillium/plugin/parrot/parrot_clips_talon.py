"""Talon side of parrot clips: settings, 'parrot missed [<sound>]', kill switch."""

import logging

from talon import Context, Module, actions, settings

from .parrot_clips import service

mod = Module()
ctx = Context()

mod.setting(
    "parrot_clips_enabled",
    type=bool,
    default=True,
    desc="Kill switch: keep a short RAM audio buffer and save clips around mouth sounds",
)
mod.setting("parrot_clips_dir", type=str, default="", desc="Clip folder; empty = ~/.talon/parrot_clips")
mod.setting("parrot_clips_buffer_seconds", type=float, default=5.0, desc="RAM-only rolling buffer length")
mod.setting("parrot_clips_missed_seconds", type=float, default=5.0, desc="Audio saved by 'parrot missed'")
mod.setting("parrot_clips_power_floor", type=float, default=20.0, desc="Frame power that counts as a sound event")
mod.setting("parrot_clips_max_mb", type=float, default=200.0, desc="Clip folder size cap; oldest auto clips go first")
mod.setting("parrot_clips_max_age_days", type=float, default=30.0, desc="Clips older than this are pruned")
mod.setting("parrot_clips_max_clips", type=int, default=2000, desc="Clip count cap")

mod.list("parrot_missed_sound", desc="Spoken sound names -> parrot model labels (clip folder names)")

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


def apply_settings(*_args) -> None:
    from pathlib import Path

    try:
        root = settings.get("user.parrot_clips_dir") or str(Path.home() / ".talon" / "parrot_clips")
        service.configure(
            enabled=bool(settings.get("user.parrot_clips_enabled")) and not _runtime_off[0],
            root=root,
            sample_rate=_sample_rate[0],
            buffer_seconds=settings.get("user.parrot_clips_buffer_seconds"),
            power_floor=settings.get("user.parrot_clips_power_floor"),
            max_mb=settings.get("user.parrot_clips_max_mb"),
            max_age_days=settings.get("user.parrot_clips_max_age_days"),
            max_clips=settings.get("user.parrot_clips_max_clips"),
            missed_seconds=settings.get("user.parrot_clips_missed_seconds"),
        )
    except Exception:
        logging.exception("[parrot_clips] configure failed")


def start(sample_rate: int) -> None:
    """Called by parrot_integration once the ParrotSystem exists."""
    _sample_rate[0] = int(sample_rate)
    apply_settings()
    settings.register("user.parrot_clips_enabled", apply_settings)


@mod.action_class
class Actions:
    def parrot_missed(sound: str = ""):
        """Save the last few seconds of mic audio from RAM as a sound that should have registered"""
        if not service.enabled:
            actions.user.notify("parrot clips are off", 1)
            return
        ok = service.mark_missed(sound or None)
        actions.user.notify(
            f"kept {sound or 'unlabeled'}" if ok else "nothing to keep (queue full or no audio yet)", 1
        )

    def parrot_clips_on():
        """Turn parrot clip capture on"""
        _runtime_off[0] = False
        apply_settings()

    def parrot_clips_off():
        """Turn parrot clip capture off and drop the RAM buffer"""
        _runtime_off[0] = True
        apply_settings()
