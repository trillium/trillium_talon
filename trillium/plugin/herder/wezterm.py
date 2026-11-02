"""
WezTerm app-action overrides — route Talon's generic tab vocabulary to herdr.

When the WezTerm/herdr terminal is frontmost, herder_panel.py turns on
`tag: user.tabs`, which lights up core/windows_and_tabs/tabs.talon's generic
grammar ("tab next", "tab open"/"tab new", "tab close", "tab previous"/"tab last").
This file overrides the generic `app.tab_*` actions so that grammar drives the real
herdr CLI via the existing actions.user.herder_tab_* helpers (herder_nav.py) instead
of Talon's default macOS keystrokes.

Same app-override pattern as apps/tmux/tmux.py, apps/vscode/vscode.py,
apps/iterm/iterm.py: the app's own file scopes on the app and overrides app.tab_*
per-context. Matched on `app.name: WezTerm` — the same focus signal herder_panel.py
uses (WezTerm running == herdr running in this setup).

Only the four commands with a real herdr equivalent are overridden:
  "tab open" / "tab new"        -> app.tab_open     -> herder_tab_new()
  "tab close"                   -> app.tab_close    -> herder_tab_close()
  "tab next"                    -> app.tab_next     -> herder_tab_cycle(1)
  "tab previous" / "tab last"   -> app.tab_previous -> herder_tab_cycle(-1)

("tab close" reaches app.tab_close via core's user.tab_close_wrapper, which calls
actions.app.tab_close().) The rest of tabs.talon ("tab reopen", "go tab <n>",
"go tab final", "tab duplicate") stays speakable but inert here — herdr exposes no
CLI for them, which is expected, not a bug.

Also overrides edit.line_start / edit.line_end: core/edit/edit_mac.py implements
these as cmd-left / cmd-right, the GUI text-field convention. Shells (readline/zsh)
don't bind those — they respond to literal Home/End. "head" and "tail"
(core/edit/edit.talon) already speak through edit.line_start/edit.line_end, so
overriding the action here (rather than adding new herdr-scoped commands) makes
"head"/"tail" work AND keeps them going through the existing generic OPPOSITES
entry (opposite_mappings.py: head <-> tail -> edit.line_end/line_start) for
repeat/reverse — no separate reverse wiring needed, since the repeater dispatches
through actions.edit.line_end/line_start too and picks up this same override.
"""

from talon import Context, actions

ctx = Context()
ctx.matches = r"""
app.name: WezTerm
"""


@ctx.action_class("app")
class AppActions:
    def tab_open():
        actions.user.herder_tab_new()

    def tab_close():
        actions.user.herder_tab_close()

    def tab_next():
        actions.user.herder_tab_cycle(1)

    def tab_previous():
        actions.user.herder_tab_cycle(-1)


@ctx.action_class("edit")
class EditActions:
    def line_start():
        actions.key("home")

    def line_end():
        actions.key("end")
