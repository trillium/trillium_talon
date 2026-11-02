# Crew Nav — voice navigation over herdr panes / tabs / workspaces.
# Companion to herder.talon (agent focus/send/rotate). See herder_nav.py.
#
# SCOPED (task-ya0t): these were loading GLOBALLY and eating VSCode/cursorless
# phrases — "split right"/"split down"/"pane left" etc. won the matcher everywhere
# (specificity [1,0,0,0,0,0]). herdr isn't a standalone macOS app (runs in
# WezTerm), so `app:` can't match it; `user.herder_panel` (set by herder_panel.py
# when the herdr terminal is the active window) is the correct focus signal. Now
# these only fire when herdr is focused; in VSCode they no longer shadow anything.
tag: user.herder_panel
-

# Directional pane focus.
pane left$: user.herder_pane_focus("left")
pane right$: user.herder_pane_focus("right")
pane up$: user.herder_pane_focus("up")
pane down$: user.herder_pane_focus("down")

# Zoom the current pane full-screen (toggle).
pane zoom$: user.herder_pane_zoom()

# Cycle panes inside the current tab (captain's grammar; herdr-only scope
# via the tag at the top of this file). Wraps herder_pane_cycle in herder_nav.py.
pane next$: user.herder_pane_cycle(1)
pane previous$: user.herder_pane_cycle(-1)

# "terminal next/previous" = same pane cycle inside herdr (VSCode keeps its own
# terminal next via the app: rule, which outranks this herdr-tagged one there).
terminal next$: user.herder_pane_cycle(1)
terminal previous$: user.herder_pane_cycle(-1)

# Split the current pane and jump into the new one.
split right$: user.herder_pane_split("right")
split down$: user.herder_pane_split("down")

# Tab vocabulary ("tab next/open/new/close/previous/last") now routes through the
# generic core/windows_and_tabs/tabs.talon grammar + wezterm.py's app.tab_* overrides,
# lit up by tag: user.tabs (set in herder_panel.py). No parallel grammar needed here.

# Fuzzy tab search / picker. herdr exposes no CLI for it, so send the literal chord a
# human presses: prefix (ctrl-b) -> g (goto/navigate mode) -> / (fuzzy filter). Wording
# mirrors Chrome's "tab search" (apps/chrome/chrome.talon) for cross-app consistency.
tab search:
    key(ctrl-b)
    sleep(30ms)
    key(g)
    sleep(300ms)
    key(/)

# Cycle / create workspaces.
space next$: user.herder_ws_cycle(1)
space (back | previous)$: user.herder_ws_cycle(-1)
space new$: user.herder_ws_new()

# Rename panel — herdr has no CLI for this, so send its own default rename
# chord directly (prefix+shift+w for workspace, prefix+shift+t for tab; see
# ~/.config/herdr/config.toml's rename_workspace/rename_tab, unset there so
# herdr's built-in defaults apply). Opens herdr's own rename prompt; type the
# new name and press Enter same as you would by hand.
space rename$:
    key(ctrl-b)
    sleep(30ms)
    key(shift-w)

tab rename$:
    key(ctrl-b)
    sleep(30ms)
    key(shift-t)

# Rapid, eye-followable scroll — same words (and same "<number>" convention)
# as Rango's "upper"/"downer" (tag: browser), reused here on purpose (tag:
# user.herder_panel above keeps them from colliding at speech time — only one
# of the two tags is ever active). See herder_scroll.py — sends real herdr
# scroll ticks one line at a time via `herdr terminal session control`, so the
# cascade is genuinely visible instead of a single silent jump. A trailing
# number multiplies how many ticks are sent, same as Rango's "upper two".
upper$: user.herder_scroll_burst("up")
upper <user.number_small>: user.herder_scroll_burst("up", number_small)
downer$: user.herder_scroll_burst("down")
downer <user.number_small>: user.herder_scroll_burst("down", number_small)

# Pane focus history — cycles through recently visited panes (pane-level, not tab-level).
# "herder back" goes to the previously focused pane; repeat to keep going back.
# "herder forward" reverses course. "herder pick" opens an fzf picker in a new tab.
# Cursor resets after 30s of inactivity or if you navigate away manually.
herder back$: user.herder_history_prev()
herder forward$: user.herder_history_next()
herder pick$: user.herder_history_pick()
