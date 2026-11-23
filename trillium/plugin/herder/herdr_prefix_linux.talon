# Linux-only override of herder_panel.talon / herdr_prefix.talon (which hard-code ctrl-b).
# Matches the WezTerm window by its Linux app name; sends herdr's configured prefix.
os: linux
app.name: /wezterm/i
-
prefix: user.herdr_send_prefix()
prefix <user.letter>: user.herdr_send_prefix(letter)
# Caps Lock tapped alone (keyd sends F19) -> herdr prefix
key(f19): user.herdr_send_prefix()
