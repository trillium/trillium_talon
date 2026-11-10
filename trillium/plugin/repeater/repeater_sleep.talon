# Sleep-mode parrot sounds -> repeater's armed overrides.
#
# While Talon is asleep (not pondering, not deep sleep) with parrot on, the
# tongue-click consumes the armed repeat override (e.g. the "submit" lined up
# by click_to_finish.py on a pondering finish) and kitty-cmere consumes the
# armed opposite override (e.g. re-enter pondering). Neither ever repeats the
# last command while Talon is asleep.
#
# kitty-cmere in sleep lives in repeater_sleep_cmere.talon: it is opt-in
# (tag user.sleep_cmere_relaunches_pondering, default off) because a cmere
# false-positive while asleep opened SuperWhisper (task-umnrph). The tongue-click
# stays a no-op when nothing is armed.
#
# All header lines are AND'd (same-type matchers would OR by default — see the
# talon.wiki combined-matcher rules — so each clause uses explicit `and`).
mode: sleep
and tag: user.parrot_on
and not tag: user.pondering
and not tag: user.deep_sleep
-
parrot(tongue-click):
    user.repeater_sleep_repeat()
