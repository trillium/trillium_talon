# Always-active (no context header) so it fires in every mode, including
# mode:sleep while pondering — needed to catch the exit press too.
#
# `:passive` = observe the key WITHOUT consuming it, so the physical
# SuperWhisper hotkey (caps-space remapped to ctrl-alt-cmd-shift-space) falls
# through to SuperWhisper on its own. Talon only syncs pondering state; it does
# NOT relay a key here (that would double-toggle SuperWhisper).
-
key(ctrl-alt-cmd-shift-space:passive): user.pondering_hotkey()
