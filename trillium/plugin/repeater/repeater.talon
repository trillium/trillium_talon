# -1 because we are repeating, so the initial command counts as one
<user.ordinals>: core.repeat_command(ordinals - 1)
<number_small> times: core.repeat_command(number_small - 1)
(repeat that | twice): core.repeat_command(1)
repeat that <number_small> [times]: core.repeat_command(number_small)

(repeat phrase | again) [<number_small> times]:
    core.repeat_partial_phrase(number_small or 1)

# Reverse action (voice triggered version of cmere noise)
reverse: user.noise_cmere()
# Disabled: repeat() doesn't support arithmetic
# reverse <number_small> times:
#     user.noise_cmere()
#     repeat(number_small - 1)

repeater exclude last:
    user.repeater_exclude_last_command()

repeater (include | restore) last:
    user.repeater_include_last_command()

repeater list excluded:
    user.repeater_list_excluded()
