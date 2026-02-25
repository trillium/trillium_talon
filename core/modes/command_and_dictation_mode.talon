mode: command
mode: dictation
-
^(dictation mode | mode dictation)$: user.dictation_mode()
^(command mode | mode command)$: user.command_mode()
^(mixed mode | mode mixed)$: user.mixed_mode()
