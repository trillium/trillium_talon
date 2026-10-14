mode: command
-
lap: key(enter)

# <user.cursorless_wrapper_paired_delimiter> {user.cursorless_wrap_action} <user.cursorless_target>:
#     user.private_cursorless_wrap_with_paired_delimiter(cursorless_wrap_action, cursorless_target, cursorless_wrapper_paired_delimiter)

squiggle <user.cursorless_target>:
    user.cursorless_command("setSelection", cursorless_target)
    mimic("take inside pair")
squiggle$:
    mimic("take inside pair")

copy path:
    user.vscode("copyRelativeFilePath")

stage [line] <user.cursorless_target>:
    user.cursorless_command("setSelection", cursorless_target)
    user.vscode("git.stageSelectedRanges")

paste without formatting:
    key(cmd-shift-v)

sleep small:
    sleep(.3)

sleep one:
    sleep(1.0)
sleep two:
    sleep(2.0)
sleep three:
    sleep(3.0)
sleep four:
    sleep(4.0)
sleep five:
    sleep(5.0)
