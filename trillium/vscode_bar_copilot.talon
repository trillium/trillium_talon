#custom vscode commands go here
app: vscode
-

^chat (continue | go)$:
    user.vscode("workbench.panel.chat.view.copilot.focus")
    key(cmd-enter)

^chat yes$:
    user.vscode("workbench.panel.chat.view.copilot.focus")
    key(cmd-a)
    insert("yes")
    key(enter)

^(chat clear | clear chat)$:
    user.vscode("workbench.panel.chat.view.copilot.focus")
    key(cmd-a)
    insert("/clear")
    key(enter)

# ^(chat clear | clear chat)$:
#     user.vscode("workbench.panel.chat.view.copilot.focus")
#     key(cmd-a)
#     insert("/clear")
#     key(enter)[]

^chat <user.prose>:
    user.vscode("workbench.panel.chat.view.copilot.focus")
    key(cmd-a)
    insert(prose)
    print(prose)
    # key(enter)
