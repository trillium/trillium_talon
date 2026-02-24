key(super-ctrl-alt-shift-t:up):
    insert(user.time_format_utc("T"))
    insert(user.time_format_utc("%Y-%m-%dT%H:%M:%S+00:00"))

# timestamp insert: insert(user.time_format_utc("%Y-%m-%dT%H:%M:%S+00:00"))
timestamp insert: insert(user.time_format_utc())
# timestamp pomodoro: insert(user.pomodoro_get_end_time("%Y-%m-%dT%H:%M:%S%z"))
timestamp pomodoro: insert(user.pomodoro_get_end_time())
timestamp local: insert(user.get_time_local())
timestamp [local] <number_small> [minute] [minutes] (ago | past): insert(user.get_time_local_ago(number_small))
timestamp [local] <number_small> [minute] [minutes] (future | ahead | from now): insert(user.get_time_local_future(number_small))
