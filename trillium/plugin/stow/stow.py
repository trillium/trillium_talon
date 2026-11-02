"""
Stow — one-utterance capture/fetch across the brain federation stores.

Kills the "federated bead store" friction (see ~/muse-overnight-ideas.md §8): the
SPOKEN word never equals the typed command. You say a clean store name; a
.talon-list translates it to the real store CLI. You never voice "bd".

  "stow ideas voice command surface"   -> ideas create "voice command surface"   (background)
  "stow robots hook misfired on save"  -> robots create "hook misfired on save"
  "fetch decisions hat renderer"        -> types `decisions search "hat renderer"` into
                                           the focused terminal + Enter (visible results)

Capture is fire-and-forget (non-blocking + a Talon notification) — it serves the
documentation ethos without stealing focus. Fetch reuses the recall idiom (insert +
Enter into the focused terminal) so results are visible where you're looking.

Grounded in the real store wrappers on PATH (brain, ideas, robots, decisions,
questions, inbox, projects, life, person, handoff, dump), each `<store> create [title]`.
"""

import shlex

from talon import Module, actions, app

mod = Module()

_ENV = 'PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH" '  # GUI-process PATH safety (see herder.py)

# bare name; Talon namespaces to user.brain_store ("user." prefix here → dots error).
mod.list("brain_store", desc="Clean spoken store names -> federation store CLI")


@mod.action_class
class Actions:
    def store_capture(store: str, text: str):
        """Capture text to a federation store as a new entry (background)."""
        actions.user.system_command_nb(_ENV + f"{shlex.quote(store)} create {shlex.quote(text)}")
        app.notify("stowed", f"→ {store}: {text}")

    def store_fetch(store: str, text: str):
        """Type a store search into the focused terminal so results are visible."""
        actions.insert(f'{store} search {shlex.quote(text)}')
        actions.key("enter")
