# Bare agent names — active ONLY when the WezTerm/herdr terminal is active.
# "muse" → go to the muse agent (the in-panel shortcut for "herder muse").
# See herder_panel.py for the tag + activator matcher.

tag: user.herder_panel
-
<user.herder_targets>$:
    user.herder_focus(herder_targets)

# Trigger herdr's prefix key (ctrl-b), optionally followed by a letter.
# "prefix"     -> ctrl-b        "prefix bat" -> ctrl-b then b
prefix: key(ctrl-b)
prefix <user.letter>:
    key(ctrl-b)
    sleep(30ms)
    key(letter)
