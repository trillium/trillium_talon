# Say a herdr tab's label (e.g. "mayor", "fixer") to focus that tab and bring
# WezTerm forward. Works in any app. Saved recall window names win on a clash.
# "herdr tab next" / "herdr tab previous" step the LOCAL MacBook Herdr even when
# the focused pane is an ssh session into a mini (see herdr_tab_wezterm.talon
# for plain "tab next" / "tab previous" inside WezTerm).
-
^{user.herdr_tab_names}$: user.herdr_tab_focus(herdr_tab_names)
herdr tab next: user.herdr_tab_next()
herdr tab (last | previous): user.herdr_tab_previous()
