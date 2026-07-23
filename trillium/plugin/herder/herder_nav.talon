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
pane left$:   user.herder_pane_focus("left")
pane right$:  user.herder_pane_focus("right")
pane up$:     user.herder_pane_focus("up")
pane down$:   user.herder_pane_focus("down")

# Zoom the current pane full-screen (toggle).
pane zoom$:   user.herder_pane_zoom()

# Split the current pane and jump into the new one.
split right$: user.herder_pane_split("right")
split down$:  user.herder_pane_split("down")

# Cycle / create tabs.
tab next$:    user.herder_tab_cycle(1)
tab back$:    user.herder_tab_cycle(-1)
tab new$:     user.herder_tab_new()

# Cycle / create workspaces.
space next$:  user.herder_ws_cycle(1)
space back$:  user.herder_ws_cycle(-1)
space new$:   user.herder_ws_new()
