tag: user.speak_history_active
-

^next$: user.speak_history_next()
^previous$: user.speak_history_previous()
^replay <user.overlay_select>$: user.speak_history_replay(overlay_select)
^replay last <number_small>$: user.speak_history_replay_last(number_small)
^show all$: user.speak_history_clear_filter()
^show {user.speak_history_caller}$: user.speak_history_filter(speak_history_caller)
^skip$: user.speak_history_skip()
^spoken sudo kill$: user.speak_history_kill()
^spoken sudo restart$: user.speak_history_restart()
key(escape): user.speak_history_stop()
^spoken close$: user.speak_history_stop()
