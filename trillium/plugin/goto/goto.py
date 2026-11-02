"""
Go to — unified addressing: ONE word focuses the herdr pane AND the Parlay tab.

"go to muse"  →  herdr agent focus muse   +   POST /api/chat/select-tab {channel:"muse"}

The "one vocabulary, every surface" payoff (see ~/muse-overnight-ideas.md §Theme 3):
because Parlay tabs and herdr panes share agent names, a single utterance drives both.

Forward-compatible by design: the Parlay half needs the small additive select-tab
endpoint (spec at ~/parlay-select-tab-patch.md). Until that's applied, the curl 404s
harmlessly (-m 2, errors swallowed) and the herdr focus still works — so shipping this
now costs nothing and lights up automatically once the patch lands. No Talon change later.
"""

import shlex

from talon import Module, actions

mod = Module()

_PARLAY = "http://localhost:31337"
_ENV = 'PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH" '  # GUI-process PATH safety (see herder.py)


@mod.action_class
class Actions:
    def goto_surface(name: str):
        """Focus both the herdr pane and the Parlay tab for an agent by name."""
        actions.user.system_command_nb(_ENV + f"herdr agent focus {shlex.quote(name)}")
        # Parlay half — harmless until the select-tab endpoint exists.
        payload = f'{{"channel":"{name}"}}'
        actions.user.system_command_nb(
            f"curl -s -m 2 -X POST {_PARLAY}/api/chat/select-tab "
            f"-H 'Content-Type: application/json' -d {shlex.quote(payload)} "
            f">/dev/null 2>&1 || true"
        )
