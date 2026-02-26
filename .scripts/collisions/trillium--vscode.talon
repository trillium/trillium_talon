#custom vscode commands go here
app: vscode
-
tag(): user.find_and_replace
tag(): user.line_commands
tag(): user.multiple_cursors
tag(): user.splits
tag(): user.tabs
(super find it | find in (file | files)): key(cmd-shift-f)

bar (copilot | pilot): user.vscode("workbench.panel.chat.view.copilot.focus")
bar none: user.vscode("workbench.action.toggleSidebarVisibility")

# run active file:
#     user.vscode("workbench.action.terminal.runActiveFile")

workspace (hunt | search) [<user.text>]:
    user.vscode("workbench.action.openRecent")
    sleep(150ms)
    insert(text or "")

workspace (hunt | search) [<user.text>] bravely:
    user.vscode("workbench.action.openRecent")
    sleep(150ms)
    insert(text or "")
    insert(enter)

reload window: user.vscode("workbench.action.reloadWindow")

active file path copy:
    user.vscode("copyFilePath")

match case:
    key(cmd-alt-c)

match [whole] word:
    key(cmd-alt-w)

match case and [whole] word:
    key(cmd-alt-c)
    key(cmd-alt-w)

match [whole] word and case:
    key(cmd-alt-c)
    key(cmd-alt-w)

git stage file:
    user.vscode("git.stage")

^chat (continue | go)$:
    user.vscode("workbench.panel.chat.view.copilot.focus")
    key(cmd-enter)

^chat yes$:
    user.vscode("workbench.panel.chat.view.copilot.focus")
    key(cmd-a)
    insert("yes")
    key(enter)

increase [view] size:
    user.vscode("workbench.action.increaseViewSize")

decrease [view] size:
    user.vscode("workbench.action.decreaseViewSize")

reset view layout:
    user.vscode("workbench.action.resetViewLocations")

(chat | copilot) ask [mode]:
    user.vscode("workbench.action.chat.openAsk")

(chat | copilot) agent [mode]:
    user.vscode("workbench.action.chat.openAgent")

[(chat | copilot)] (next code [block] | code [block] next):
    user.vscode("workbench.action.chat.nextCodeBlock")

[(chat | copilot)] (previous code [block] | code [block] previous):
    user.vscode("workbench.action.chat.previousCodeBlock")

agent next:
    key(ctrl-x)
    key(right)

agent main:
    key(ctrl-x)
    key(up)

bash <user.cursorless_target>:
    x = user.cursorless_get_text(cursorless_target)
    user.vscode("workbench.action.terminal.focus")
    user.paste_transient(x)

bash <user.cursorless_target> bravely:
    x = user.cursorless_get_text(cursorless_target)
    user.vscode("workbench.action.terminal.focus")
    user.paste_transient(x)
    key(enter)
