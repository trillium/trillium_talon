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
^destroy$:
    user.clear_last_dictation()

(nuke left | new cleft | nu cleft | new left):
    user.nuke_left()
