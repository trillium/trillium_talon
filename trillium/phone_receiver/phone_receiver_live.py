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

`POST /snippet` saves an uploaded FLAC/WAV as a new `phone-snippet-<8>.flac` in Talon's own
recordings folder (`<talon_home>/recordings`), the one write this module makes there, and only
when `user.phone_receiver_snippets_enabled` is also on (default off). `GET /metrics` returns
request timings and byte counts, and every few minutes a one-line summary goes to the log.
It never changes a Talon setting, in particular not `speech.record_all`.

The setting defaults to off. With it off `user.phone_receiver_handle` returns `disabled`
and never touches the engine; microphone dictation is unaffected either way, because the
encoder is swapped only for the duration of one injected utterance. The action also refuses
while `speech.record_all` is on (`record_all_on`). See docs/phone-receiver.md.
"""

import os
import sys
import types

from talon import Module, actions, app, cron, settings, speech_system

try:
    from talon.lib import flac
except (
    ImportError
):  # the test stubs have no flac library; a WAV snippet is then refused
    flac = None

from ..palette_feed.dispatch import run_scheduled
from . import audio, hop, keyfile, listener, netbind, snippet_ledger
from .live import LiveInstall, active_engine
from .metrics import Metrics
from .recordings import RecordingsWriter
from .service import PhoneService, PhraseTap
from .snippet import SnippetService

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

mod.setting(
    "phone_receiver_snippets_enabled",
    type=bool,
    default=False,
    desc="If true (and the listener is on), POST /snippet saves an uploaded 16 kHz mono "
    "FLAC/WAV as a new phone-snippet-<8>.flac in Talon's recordings folder. Off by default. "
    "Read per request.",
)

MODE_SETTING = "user.phone_receiver_mode"
SNIPPETS_SETTING = "user.phone_receiver_snippets_enabled"
METRICS_LOG_INTERVAL = "5m"
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
_metrics = Metrics()


def _recordings_dir() -> str:
    # Talon's own folder (`speech.record_all` writes here); never created by this module.
    return os.path.join(str(actions.path.talon_home()), "recordings")


def _snippets_enabled() -> bool:
    return _enabled() and bool(settings.get(SNIPPETS_SETTING))


def _encode_wav(pcm: bytes) -> bytes:
    # Talon's own encoder, with its defaults (16 kHz, mono): the recordings are its output.
    return flac.encode(
        audio.pcm16_to_floats(pcm), sample_rate=audio.SAMPLE_RATE, channels=1
    )


_snippets = SnippetService(
    RecordingsWriter(_recordings_dir),
    snippet_ledger.SnippetLedger(),
    _snippets_enabled,
    encode=_encode_wav if flac is not None else None,
)

# Hot reload re-executes this module, but Talon has no unload hook: the listener and the
# phrase tap outlive module globals, so both are kept on a holder and replaced on reload.
_HOLDER_KEY = "_trillium_phone_listener"
_holder = sys.modules.setdefault(
    _HOLDER_KEY, types.SimpleNamespace(server=None, tap=None)
)
if not hasattr(_holder, "metrics_job"):  # a holder from before the metrics line existed
    _holder.metrics_job = None


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


def _log_metrics():
    line = _metrics.tick_line()
    if line:
        print(f"phone_listener: {line}")


def start_listener():
    if _holder.metrics_job is not None:
        cron.cancel(_holder.metrics_job)
        _holder.metrics_job = None
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
        snippets=_snippets,
        metrics=_metrics,
    )
    try:
        _holder.server, _ = listener.start(api, listener.DEFAULT_PORT, plan.host)
    except (OSError, netbind.BindError) as exc:
        print(
            f"phone_listener: cannot bind {plan.host}:{listener.DEFAULT_PORT}: "
            f"{getattr(exc, 'strerror', None) or exc}"
        )
        return
    _holder.metrics_job = cron.interval(METRICS_LOG_INTERVAL, _log_metrics)
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
