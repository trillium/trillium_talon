# Rowing pacer voice commands
# Control the animated dot pacer for rowing pace training

pacer start [<number_small>]: user.rowing_pacer_start(number_small or 18)
pacer stop: user.rowing_pacer_stop()
pacer toggle: user.rowing_pacer_toggle()
pacer set <number> [SPM]: user.rowing_pacer_set_pace(number)
pacer faster: user.rowing_pacer_set_pace(24)
pacer slower: user.rowing_pacer_set_pace(16)
