app: vscode
# Looks for special string in window title.
# NOTE: This requires you to add a special setting to your VSCode settings.json
# See [our vscode docs](./README.md#terminal)
win.title: /focus:\[Chat\]/
-

^(continue | go)$:
    key(cmd-enter)

^yes$:
    user.vscode("workbench.panel.chat.view.copilot.focus")
    key(cmd-a)
    insert("yes")
    key(enter)

