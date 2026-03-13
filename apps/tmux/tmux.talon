app: tmux
-
tag(): user.splits
tag(): user.tabs

# Note that you will need to add something to match the tmux app in your configuration
# This is not active by default
# Adding a file with a matcher for detecting tmux active in your terminal and activating
# the tmux tag is required
# Something like:
#
# title: /^tmux/
# -
# tag(): user.tmux

# pane management - these commands use the word split to match with the splits
# tag defined in tags/splits/splits.talon
go split <user.arrow_key>: user.tmux_keybind(arrow_key)
#Say a number after this command to switch to pane
go split: user.tmux_execute_command("display-panes -d 0")

# Scrolling - mimics mouse wheel: copy-mode -e auto-exits at bottom
scroll up: user.tmux_scroll_up(5)
scroll up <number_small>: user.tmux_scroll_up(number_small)
scroll down: user.tmux_scroll_down(5)
scroll down <number_small>: user.tmux_scroll_down(number_small)
