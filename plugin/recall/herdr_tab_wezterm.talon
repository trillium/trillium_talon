# In WezTerm (where Herdr runs) "tab next" / "tab previous" drive the local
# Herdr via its CLI instead of sending keystrokes a remote pane would swallow.
# Other apps keep the generic keystroke tab commands.
app: WezTerm
-
tab (last | previous): user.herdr_tab_previous()
tab next: user.herdr_tab_next()
