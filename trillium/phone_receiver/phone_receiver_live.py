"""Talon glue: the `user.phone_receiver_enabled` gate, one action to hand a TPE1 payload to the
live engine, and the HTTP listener (`POST /emission`) that calls the same path.
Settings and Python only: no voice commands, no recordings.

The listener starts only when the gate is on at Talon's `ready` (or at module reload); with
the gate off no socket is opened. `user.phone_receiver_bind` picks where: `127.0.0.1` (the
default) or this Mac's tailnet address from `tailscale ip -4`; any other value is refused and
no socket is opened. On loopback it answers 403 unless `Tailscale-User-Login` is in
`user.phone_receiver_allowed_logins` (empty denies all). On the tailnet it answers 403 unless
`X-Talon-Phone-Key` matches the secret in `~/.config/talon-phone/key`, created 0600 if missing.
`user.phone_receiver_mode` picks the body it accepts: `emission` (TPE1) or `pcm` (seam c).

The setting defaults to off. With it off `user.phone_receiver_handle` returns `disabled`
and never touches the engine; microphone dictation is unaffected either way, because the
encoder is swapped only for the duration of one injected utterance. The action also refuses
while `speech.record_all` is on (`record_all_on`). See docs/phone-receiver.md.
"""

import sys
import types

from talon import Module, actions, app, cron, settings, speech_system

from ..palette_feed.dispatch import run_scheduled
from . import hop, keyfile, listener, netbind
from .live import LiveInstall, active_engine
from .service import PhoneService, PhraseTap

try:
    from talon.scripting import rctx
except ImportError:  # the test stubs have no resource contexts
    rctx = None

SETTING = "user.phone_receiver_enabled"
DEFAULT_BIND = "127.0.0.1"

mod = Module()

mod.setting(
    "phone_receiver_enabled",
    type=bool,
    default=False,
    desc="If true, user.phone_receiver_handle feeds a phone-computed acoustic emission "
    "to the live speech engine in place of its encoder. Off by default; refused while "
    "speech.record_all is on.",
)
mod.setting(
    "phone_receiver_mode",
    type=str,
    default=listener.MODE_EMISSION,
    desc="Body the phone listener accepts on POST /emission: 'emission' (a TPE1 packed "
    "acoustic emission, the engine's encoder is replaced) or 'pcm' (16 kHz mono PCM16, "
    "the engine runs its own frontend and acoustic model). Takes effect on the next request.",
)
mod.setting(
    "phone_receiver_allowed_logins",
    type=str,
    default="",
    desc="Comma or space separated Tailscale logins (the Tailscale-User-Login header) "
    "allowed to POST to the phone listener. Empty denies everyone; there is no wildcard.",
)
mod.setting(
    "phone_receiver_bind",
    type=str,
    default=DEFAULT_BIND,
    desc="Address the phone listener binds: 127.0.0.1 (default, identity-header auth) or this "
    "Mac's tailnet address from `tailscale ip -4` (shared-secret auth, plain HTTP over the "
    "tailnet). Anything else is refused and the listener stays off. Read at start or reload.",
)

MODE_SETTING = "user.phone_receiver_mode"
ALLOWED_SETTING = "user.phone_receiver_allowed_logins"
BIND_SETTING = "user.phone_receiver_bind"
DISPATCH_TIMEOUT_S = 5.0


def _engine():
    # `speech_system.engine` is the proxy of the active engine; `active_engine` raises
    # `NoEngine` saying which link is missing, and the refusal reply carries that.
    return active_engine(speech_system)


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
_tap = PhraseTap(awake=lambda: actions.speech.enabled())
_service = PhoneService(_install, _tap)

# Hot reload re-executes this module, but Talon has no unload hook: the listener and the
# phrase tap outlive module globals, so both are kept on a holder and replaced on reload.
_HOLDER_KEY = "_trillium_phone_listener"
_holder = sys.modules.setdefault(
    _HOLDER_KEY, types.SimpleNamespace(server=None, tap=None)
)


def _owner():
    # The context this module is loaded under: it lasts until Talon reloads the module. A worker
    # thread's own context is the one of whoever started the listener (a REPL statement, say) and
    # may already be freed, which makes every `cron.after` from it raise `ResourceClosed`.
    try:
        return rctx.active() if rctx is not None else None
    except (
        Exception
    ):  # noqa: BLE001 - an older Talon: fall back to the calling thread's context
        return None


_schedule = hop.main_thread(lambda job: cron.after("0ms", job), _owner())


def _on_main_thread(fn):
    # Commands can drive UI and keys, so the injected phrase runs on Talon's main thread.
    return run_scheduled(_schedule, fn, DISPATCH_TIMEOUT_S)


def start_listener():
    if _holder.server is not None:
        listener.stop(_holder.server)
        _holder.server = None
    if _holder.tap is not None:
        speech_system.unregister("phrase", _holder.tap)
        _holder.tap = None
    if not _enabled():
        return
    try:
        plan = netbind.resolve_bind(settings.get(BIND_SETTING) or DEFAULT_BIND)
        key = keyfile.ensure_key() if plan.tailnet else None
    except (netbind.BindError, keyfile.KeyFileError) as exc:
        print(f"phone_listener: not started: {exc}")  # never carries the key itself
        return
    except (
        Exception
    ) as exc:  # noqa: BLE001 - nothing may escape into Talon's ready callback
        print(f"phone_listener: not started: {type(exc).__name__}")
        return
    speech_system.register("phrase", _tap.on_phrase)
    _holder.tap = _tap.on_phrase
    api = listener.ListenerApi(
        _service,
        lambda: settings.get(MODE_SETTING),
        lambda: settings.get(ALLOWED_SETTING),
        runner=_on_main_thread,
        key=(lambda: key) if key is not None else None,
    )
    try:
        _holder.server, _ = listener.start(api, listener.DEFAULT_PORT, plan.host)
    except (OSError, netbind.BindError) as exc:
        print(
            f"phone_listener: cannot bind {plan.host}:{listener.DEFAULT_PORT}: "
            f"{getattr(exc, 'strerror', None) or exc}"
        )
        return
    print(
        f"phone_listener: listening on {plan.host}:{listener.DEFAULT_PORT} "
        f"({'tailnet, key auth' if plan.tailnet else 'loopback, identity auth'}; "
        f"mode {settings.get(MODE_SETTING)})"
    )


app.register("ready", start_listener)


@mod.action_class
class Actions:
    def phone_receiver_handle(payload: bytes) -> str:
        """Validate a TPE1 emission and run it through the live engine; returns "ok" or an error code"""
        r = _install.handle(payload)
        return "ok" if r.ok else (r.error or "error")
