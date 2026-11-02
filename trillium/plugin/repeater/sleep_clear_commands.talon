# Sleep-mode voice commands to discard text entered while Talon is asleep.
#
# Same matchers as repeater_sleep.talon — this authorizes exactly two voice
# commands, "destroy" (clear the last dictation) and "nuke left" (nuke left of
# the cursor), in the sleep context so the hands-free loop can discard what it
# just entered without waking Talon.
#
# All header lines are AND'd (same-type matchers would OR by default — see the
# talon.wiki combined-matcher rules — so each clause uses explicit `and`).
mode: sleep
and tag: user.parrot_on
and not tag: user.pondering
and not tag: user.deep_sleep
-
# Each command arms the sleep tongue-click to repeat it (see
# sleep_passthrough_commands.py) so a cluck after any of them replays the action
# without waking Talon.
^destroy$:
    user.sleep_cmd_destroy()

# Fully anchored (^…$) like "destroy" so stray background speech during sleep
# won't fire it — press escape without waking Talon. "scrape" is the common
# misrecognition of "escape".
^(escape | scrape)$:
    user.sleep_cmd_escape()

(nuke left | new cleft | nu cleft | new left):
    user.sleep_cmd_nuke_left()

# Slide navigation without waking Talon. Anchored like "escape" so background
# speech can't fire it. Each arms tongue-click to repeat and kitty-cmere to
# reverse (see sleep_passthrough_commands.py).
^slide next$:
    user.sleep_cmd_slide_next()

^slide previous$:
    user.sleep_cmd_slide_previous()
