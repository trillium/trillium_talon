"""Talon glue: serve /state, /commands, /execute on the feed's configured bind.

The bind defaults to `127.0.0.1` with reads requiring the bearer token. Set
`TALON_PALETTE_BIND` and `TALON_PALETTE_OPEN_READS` (or `user.palette_feed_bind` and
`user.palette_feed_open_reads`) to publish on the tailnet; see docs/palette-feed.md.
`/execute` always needs the token, so an open bind never means open voice control. The
token lives in a mode-0600 file outside the repo; without one the feed still starts
while reads are open, and only `/execute` is disabled.
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
from .serialize import RawImpl, serialize_commands, serialize_state
from .simparse import NoMatch

PORT = server.DEFAULT_PORT
TOKEN_PATH = os.environ.get(
    "TALON_PALETTE_TOKEN_FILE", os.path.expanduser("~/.config/talon-palette/token")
)
REPO_ROOT = find_repo_root(__file__)  # None when run from a plain copy
EXECUTE_RATE = (5, 1.0)  # calls per window seconds
EXECUTE_TIMEOUT_S = 5.0

# Local delta vs trillium_talon main (PR 23): PR 23 assigns `user.palette_feed_bind`
# and `user.palette_feed_open_reads` in trillium/settings.talon but never declares
# them, and Talon drops an undeclared assignment ("settings skipped because they have
# no matching declaration"), so options.resolve() only ever saw the defaults. Declaring
# them here is what makes the .talon assignment take effect without a Talon restart.
# Reported for upstreaming.
mod = Module()
mod.setting(
    "palette_feed_bind",
    type=str,
    default="127.0.0.1",
    desc="Palette feed bind address. 0.0.0.0 or this host's tailnet address publishes it beyond loopback",
)
mod.setting(
    "palette_feed_open_reads",
    type=bool,
    default=False,
    desc="Serve palette feed reads (GET /state, /commands, /lists/<name>) without a bearer token",
)

# Hot reload re-executes this module; the running server must outlive module globals.
_HOLDER_KEY = "_trillium_palette_feed"
_holder = sys.modules.setdefault(_HOLDER_KEY, types.SimpleNamespace(server=None))


# Local delta vs trillium_talon main (PR 23): this install keeps the context-aware
# `serialize.py` that carries `scope`/`apps`/`tags` per command (talon-palette-ios
# branch fm/palette-context-aware-20261017), so it reads `match` straight off the live
# impl instead of going through main's `impl_to_raw`. This host runs Talon
# 0.4.0-1561-9c3d, where `impl.trigger` and `impl.lineno` exist natively.
def _group_active_commands() -> list[list[RawImpl]]:
    grouped = []
    for impls in registry.commands.values():
        grouped.append(
            [
                RawImpl(
                    trigger=impl.trigger,
                    context=getattr(impl.ctx, "path", str(impl.ctx)),
                    lineno=impl.lineno,
                    score=tuple(getattr(impl.ctx, "_active_scores", ())),
                    match=repr(getattr(impl.ctx, "_match", "")),
                )
                for impl in impls
            ]
        )
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

    def execute(self, phrase: str) -> None:
        # mimic can drive UI and keys, so it runs on Talon's main thread.
        run_scheduled(
            lambda job: cron.after("0ms", job),
            lambda: actions.mimic(phrase),
            EXECUTE_TIMEOUT_S,
        )


def _execution_note(plan: auth.TokenPlan) -> str:
    return "/execute token-gated" if plan.token is not None else "/execute disabled"


def start_server():
    if _holder.server is not None:
        server.stop(_holder.server)
        _holder.server = None
    opts = options.resolve(os.environ, settings.get)
    for warning in opts.warnings:
        print(f"palette_feed: {warning}")
    plan = auth.plan_token(TOKEN_PATH, REPO_ROOT, opts.open_reads)
    if plan.fatal:
        print(f"palette_feed: {plan.message}")
        return
    if plan.token is None:
        print(f"palette_feed: {plan.message}")
    api = PaletteApi(
        plan.token,
        TalonBackend(),
        RateLimiter(*EXECUTE_RATE),
        Config(open_reads=opts.open_reads),
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
        f"({opts.describe()}, {_execution_note(plan)})"
    )


app.register("ready", start_server)
