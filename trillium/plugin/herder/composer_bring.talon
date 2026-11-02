# Scoped to the composer overlay's OWN focused pane via a dynamic tag
# (user.herdr_composer_focused, toggled by a cron poller in
# composer_cursorless.py comparing `herdr pane current` against a sentinel
# file composer.py writes/removes for its own pane id), not win.title —
# win.title was tried first and is architecturally impossible here: herdr
# renders all of its virtual panes/tabs inside a SINGLE real OS-level
# WezTerm window and continuously repaints that one window's title itself
# ("[N/M] herdr"), so no external title-set call (herdr's own
# `terminal title set` or a direct `wezterm cli set-window-title`) can ever
# make a win.title predicate stick — confirmed live via ~/.talon/talon.log's
# focus_change tracking across a forced OS focus-change event. app.name:
# WezTerm stays as defense-in-depth alongside the tag, not just
# app.name: WezTerm alone — otherwise "bring red air" would fire while
# dictating into any herdr pane, not only into composer.
#
# The mode/tag lines below duplicate ~/.talon/user/cursorless-talon's own
# cursorless.talon context verbatim (mode: command, mode: cursorless_spoken_form_test,
# tag: user.cursorless, not tag: mouse_clock_showing/clock_ring_showing). That
# file's `{cursorless_bring_move_action} <cursorless_bring_move_targets>` rule
# ALSO parses plain "bring <target>" and was silently winning every single
# "bring" phrase (Talon breaks same-phrase ties by context specificity — more
# match criteria wins), routing it to private_cursorless_bring_move, which
# then threw NotImplementedError (no real command-server-connected editor) -
# composer_bring_target had NEVER once fired via voice before this. Making our
# context a strict superset of theirs (all their criteria + our own
# app/tag ones) makes ours unambiguously more specific, so ours wins
# whenever both would otherwise match.
app.name: WezTerm
tag: user.herdr_composer_focused
mode: command
mode: user.cursorless_spoken_form_test
tag: user.cursorless
not tag: user.mouse_clock_showing
not tag: user.clock_ring_showing
-
bring <user.cursorless_target>:
    user.composer_bring_target(cursorless_target)

# "copy token/block/pair <hat>" - real cursorless-talon's own personal vocab
# (~/.talon/user/trillium_talon/cursorless-settings/modifier_scope_types.csv,
# paired_delimiters.csv) maps token/block/pair to scope-type modifiers
# (token/paragraph/surroundingPair-any) already forwarded verbatim by
# composer.py's HatEngine - "copy" collides with the real cursorless-talon's
# own `<cursorless_action_or_ide_command> <cursorless_target>` rule (spoken
# "copy" -> copyToClipboard, same NotImplementedError as "bring" without this
# override) so it needs the same superset-context win as above.
copy <user.cursorless_target>:
    user.composer_copy_target(cursorless_target)
