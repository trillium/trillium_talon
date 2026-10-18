"""Talon glue: serve /state, /commands, /execute (and the phone page at /) on the
feed's configured bind.

The bind defaults to `127.0.0.1` with reads requiring the bearer token. Set
`TALON_PALETTE_BIND` and `TALON_PALETTE_OPEN_READS` (or `user.palette_feed_bind` and
`user.palette_feed_open_reads`) to publish on the tailnet. `user.palette_feed_open_execute`
(or `TALON_PALETTE_OPEN_EXECUTE`) additionally drops the token from `POST /execute`, so any
device that can reach the bind can run Talon commands; off by default. The token lives in
a mode-0600 file outside the repo; without one the feed still starts whenever every route
is open, and a gated route answers 401 instead. See docs/palette-feed.md.
"""

import os
import socket
import sys
import time
import types

from talon import Module, actions, app, cron, registry, scope, settings, speech_system

from . import auth, options, server
from .api import Config, PaletteApi
from .auth import find_repo_root
from .dispatch import DispatchTimeout, run_scheduled
from .limits import RateLimiter
from .serialize import RawImpl, impl_to_raw, serialize_commands, serialize_state
from .simparse import NoMatch

mod = Module()

# A `<name>.talon` `settings():` block is an assignment, and Talon only accepts it for a
# setting declared here; without these declarations the repo's own settings.talon values
# are dropped with a "settings skipped because they have no matching declaration" warning
# and the feed silently keeps the loopback/closed defaults. See task-ncz8l.
mod.setting(
    "palette_feed_bind",
    type=str,
    default=options.DEFAULT_BIND,
    desc="Address the palette feed HTTP server binds. 127.0.0.1 is loopback only; "
    "0.0.0.0 or this host's tailnet address publishes it to the network.",
)
mod.setting(
    "palette_feed_open_reads",
    type=bool,
    default=options.DEFAULT_OPEN_READS,
    desc="If true, GET /, /state, /commands and /lists/<name> answer without a bearer "
    "token. POST /execute is unaffected.",
)
mod.setting(
    "palette_feed_open_execute",
    type=bool,
    default=options.DEFAULT_OPEN_EXECUTE,
    desc="If true, POST /execute runs a phrase without a bearer token: with the feed "
    "published on the tailnet, any device on the network that can reach the bind can "
    "run Talon commands. Off by default.",
)

PORT = server.DEFAULT_PORT
TOKEN_PATH = os.environ.get(
    "TALON_PALETTE_TOKEN_FILE", os.path.expanduser("~/.config/talon-palette/token")
)
REPO_ROOT = find_repo_root(__file__)  # None when run from a plain copy
EXECUTE_RATE = (5, 1.0)  # calls per window seconds
EXECUTE_TIMEOUT_S = 5.0

# Hot reload re-executes this module; the running server must outlive module globals.
_HOLDER_KEY = "_trillium_palette_feed"
_holder = sys.modules.setdefault(_HOLDER_KEY, types.SimpleNamespace(server=None))


def _group_active_commands() -> list[list[RawImpl]]:
    grouped = []
    for impls in registry.commands.values():
        grouped.append([impl_to_raw(impl) for impl in impls])
    return [g for g in grouped if g]


def _merged_list(name: str) -> dict:
    merged: dict = {}
    for part in registry.lists.get(name, []):
        if isinstance(part, dict):
            merged.update(part)
    return merged


class TalonBackend:
    def commands(self) -> dict:
        sizes: dict = {}
        return serialize_commands(
            _group_active_commands(),
            lambda name: sizes.setdefault(name, len(_merged_list(name))),
        )

    def modes(self) -> set:
        return set(scope.get("mode") or ())

    def state(self) -> dict:
        return serialize_state(
            host=socket.gethostname(),
            ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            app=scope.get("app") or {},
            window=scope.get("win") or {},
            modes=self.modes(),
            tags=registry.tags,
            language=scope.get("code.language") or "",
            commands_rev=self.commands()["commands_rev"],
        )

    def list_entries(self, name: str) -> list:
        return sorted(_merged_list(name))

    def sim(self, phrase: str) -> str:
        try:
            return speech_system._sim(phrase)
        except RuntimeError as exc:
            if "Failed to parse" in str(exc):
                raise NoMatch() from exc
            raise

    def engine_active(self) -> bool:
        # With no engine attached `actions.mimic` neither raises nor dispatches.
        return scope.get("speech.engine") is not None

    def execute(self, phrase: str) -> None:
        # mimic can drive UI and keys, so it runs on Talon's main thread.
        run_scheduled(
            lambda job: cron.after("0ms", job),
            lambda: actions.mimic(phrase),
            EXECUTE_TIMEOUT_S,
        )


def _execution_note(open_execute: bool, plan: auth.TokenPlan) -> str:
    if open_execute:
        return "/execute open (no token needed)"
    return "/execute token-gated" if plan.token is not None else "/execute disabled"


def start_server():
    if _holder.server is not None:
        server.stop(_holder.server)
        _holder.server = None
    opts = options.resolve(os.environ, settings.get)
    for warning in opts.warnings:
        print(f"palette_feed: {warning}")
    plan = auth.plan_token(TOKEN_PATH, REPO_ROOT, opts.open_reads, opts.open_execute)
    if plan.fatal:
        print(f"palette_feed: {plan.message}")
        return
    if plan.token is None:
        print(f"palette_feed: {plan.message}")
    if opts.open_execute:
        # Loud on purpose: this is the setting that turns the tailnet into the only
        # thing between a network peer and voice control of this machine.
        print(
            "palette_feed: WARNING /execute is open: any device that can reach "
            f"{opts.bind}:{PORT} can run Talon commands"
        )
    api = PaletteApi(
        plan.token,
        TalonBackend(),
        RateLimiter(*EXECUTE_RATE),
        Config(open_reads=opts.open_reads, open_execute=opts.open_execute),
    )
    try:
        _holder.server, _ = server.start(
            api, opts.bind, PORT, allow_non_loopback=opts.allow_non_loopback
        )
    except OSError as exc:
        print(f"palette_feed: cannot bind {opts.bind}:{PORT}: {exc.strerror}")
        return
    print(
        f"palette_feed: listening on {opts.bind}:{PORT} "
        f"({opts.describe()}, {_execution_note(opts.open_execute, plan)})"
    )


app.register("ready", start_server)
