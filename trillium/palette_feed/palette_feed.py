"""Talon glue: serve /state, /commands, /execute on 127.0.0.1 for the phone palette.

Publish tailnet-only with `tailscale serve`; see docs/palette-feed.md. The token lives in
a mode-0600 file outside the repo; without it the server does not start.
"""

import os
import socket
import sys
import time
import types

from talon import actions, app, cron, registry, scope, speech_system

from . import server
from .api import Config, PaletteApi
from .auth import TokenError, find_repo_root, is_within, load_token
from .dispatch import DispatchTimeout, run_scheduled
from .limits import RateLimiter
from .serialize import RawImpl, serialize_commands, serialize_state
from .simparse import NoMatch

HOST = server.DEFAULT_HOST
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
        grouped.append(
            [
                RawImpl(
                    trigger=impl.trigger,
                    context=getattr(impl.ctx, "path", str(impl.ctx)),
                    lineno=impl.lineno,
                    score=tuple(getattr(impl.ctx, "_active_scores", ())),
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


def start_server():
    if _holder.server is not None:
        server.stop(_holder.server)
        _holder.server = None
    if REPO_ROOT and is_within(TOKEN_PATH, REPO_ROOT):
        print(f"palette_feed: refusing token file inside the repo: {TOKEN_PATH}")
        return
    try:
        token = load_token(TOKEN_PATH)
    except TokenError as exc:
        print(f"palette_feed: not starting: {exc}")
        return
    api = PaletteApi(token, TalonBackend(), RateLimiter(*EXECUTE_RATE), Config())
    try:
        _holder.server, _ = server.start(api, HOST, PORT)
    except OSError as exc:
        print(f"palette_feed: cannot bind {HOST}:{PORT}: {exc.strerror}")
        return
    print(f"palette_feed: listening on {HOST}:{PORT}")


app.register("ready", start_server)
