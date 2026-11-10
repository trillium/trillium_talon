# Sleep-mode kitty-cmere -> repeater's armed opposite override / re-launch pondering.
#
# OPT-IN: only active when tag `user.sleep_cmere_relaunches_pondering` is enabled
# (default off, declared in core/click_to_finish.py; Talon match headers cannot read
# settings, so the opt-in is a tag). With nothing armed, repeater reserves
# kitty-cmere for re-launching pondering, so any cmere false-positive while asleep
# opened SuperWhisper (task-umnrph). Turn it on from any always-active .talon file with:
#     tag(): user.sleep_cmere_relaunches_pondering
mode: sleep
and tag: user.parrot_on
and not tag: user.pondering
and not tag: user.deep_sleep
and tag: user.sleep_cmere_relaunches_pondering
-

parrot(kitty-cmere):
    user.repeater_sleep_opposite()
