mode: command
mode: dictation
-
^dictation mode$:
    mode.disable("sleep")
    mode.disable("command")
    mode.enable("dictation")
    user.code_clear_language_mode()
    user.gdb_disable()
^command mode$:
    mode.disable("sleep")
    mode.disable("dictation")
    mode.enable("command")
^mode mixed$:
    mode.disable("sleep")
    mode.enable("command")
    mode.enable("dictation")
    user.dictation_format_reset()
