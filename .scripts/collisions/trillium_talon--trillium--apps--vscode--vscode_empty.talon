app: vscode
# Looks for special string in window title.
# NOTE: This requires you to add a special setting to your VSCode settings.json
# See [our vscode docs](./README.md#terminal)
win.title: /focus:\[\]/
-
^(cancel | oops | nope)$: key(esc)

^(save | yes | okay)$: key(enter)

^(don't | no) [save]$: key(cmd-backspace)
