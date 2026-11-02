"""
Snag — "type what you see" by spoken fragment (the hats hero verb, usable TODAY).

The value of `type <hat>` — retype a long path / SHA / branch you can already see —
doesn't need the visual hat layer. It needs only the on-screen tokens + a picker.
This picks by a spoken FRAGMENT, so it works before the herdr fork renders hats.

  "snag parlay"       -> types "parlay-spawn/herd/yolo-herdr" into the focused pane
  "snag copy a1b2c3"  -> copies the matching token to the clipboard

Backed by ~/code/herdr-hats-spike/grab.ts (herdr pane read -> fragment match ->
herdr pane send-text). Full absolute paths because Talon's shell PATH is minimal.
"""

import shlex

from talon import Module, actions

mod = Module()

_BUN = "/Users/trilliumsmith/.bun/bin/bun"
_GRAB = "/Users/trilliumsmith/code/herdr-hats-spike/grab.ts"
_ENV = 'PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH" '  # so grab.ts child spawns (herdr/open) resolve


@mod.action_class
class Actions:
    def snag_type(fragment: str):
        """Type the on-screen token matching fragment into the focused herdr pane."""
        actions.user.system_command_nb(
            _ENV + f"{_BUN} {_GRAB} {shlex.quote(fragment)} --type"
        )

    def snag_copy(fragment: str):
        """Copy the on-screen token matching fragment to the clipboard."""
        actions.user.system_command_nb(
            _ENV + f"{_BUN} {_GRAB} {shlex.quote(fragment)} --copy"
        )

    def snag_open(fragment: str):
        """Open the on-screen token matching fragment if it's a URL or existing path."""
        actions.user.system_command_nb(
            _ENV + f"{_BUN} {_GRAB} {shlex.quote(fragment)} --open"
        )

    def snag_type_from(fragment: str, source: str):
        """Cross-pane: read a token from another agent's pane, type it into the focused pane.

        The herdr-only superpower — pull a value you can SEE in agent A's output into
        what you're typing in pane B, by voice, no mouse, no clipboard.
        """
        actions.user.system_command_nb(
            _ENV
            + f"{_BUN} {_GRAB} {shlex.quote(fragment)} --from {shlex.quote(source)} --type"
        )
