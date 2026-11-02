"""
Herder panel context — bare agent names when the panel is the active window.

The interaction model (Trillium, 2026-07-15):
  - "herder <agent>"  → go to that agent, from ANYWHERE (panel not focused).  [global, in herder.talon]
  - "<agent>" (bare)  → go to that agent, ONLY when the herder/Parlay panel is active.  [this file]
Both land on the same agent; the bare name is the in-panel shortcut.

Scoped by `tag: user.herder_panel` so bare agent names can't collide with anything
outside the panel. The tag is turned on by the activator Context below.

The same Context also turns on `tag: user.tabs`, which lights up Talon's generic
tab vocabulary (core/windows_and_tabs/tabs.talon: "tab next/open/close/previous",
etc.). wezterm.py overrides the generic `app.tab_*` actions so that grammar drives
herdr instead of the default macOS keystrokes — same app-override pattern as
apps/tmux, apps/vscode, apps/iterm. tabs.talon is the only consumer of user.tabs.

MATCHER GROUNDED (2026-07-15) from Trillium's correction + his window-focus log:
  the "herder panel" is the WezTerm terminal running herdr — Talon reports it as
  `app='WezTerm'` (1019× in the log). herdr is Trillium's WezTerm environment, so
  matching the WezTerm app == being in herdr. This distinguishes it from his Terminal /
  iTerm2 usage. (Talon exposes this via `ui.active_app().name` — his own
  window_focus_announcer logs `app='WezTerm', title='[N/M] herdr'`.)

To scope more tightly to herdr specifically (vs any WezTerm window), add
`and win.title: /herdr/i` — but the WezTerm title reflects the active pane's title, so it
is not reliably 'herdr'; app.name is the stable signal.
"""

from talon import Context, Module

mod = Module()
mod.tag("herder_panel", desc="The WezTerm/herdr terminal is the active window")

ctx = Context()
ctx.matches = r"""
app.name: WezTerm
"""
ctx.tags = ["user.herder_panel", "user.tabs"]
