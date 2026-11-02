# Snag — "type what you see" by spoken fragment. See grab.py.
# You're looking at a herdr pane; say a distinctive fragment of a token on screen
# and it types the WHOLE token into the focused pane (paths, SHAs, branches, ids).
# Bridge until the herdr hat layer renders — same token source, fragment picker.
#
# NOTE: loads globally for the prototype; scope to the terminal app once happy.

# Cross-pane (herdr-only): pull a token from another agent's pane into this one.
# "snag from muse parlay" -> types muse's on-screen "parlay…" token where you're typing.
snag from {user.herder_targets} <user.text>$:
    user.snag_type_from(user.text, herder_targets)

snag open <user.text>$:
    user.snag_open(user.text)

snag copy <user.text>$:
    user.snag_copy(user.text)

snag <user.text>$:
    user.snag_type(user.text)
