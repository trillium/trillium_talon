tag: terminal
os: mac
-
# tags should be activated for each specific terminal in the respective talon file
(but dev | boot dev): "bootdev "
yarn dev: "yarn dev"
PM PM test: "pnpm test"
P N P M test: "pnpm test"
AP test: "pnpm test"
P test: "pnpm test"

git status:
    insert("gs")
    key(enter)

(terminal stop | terminal stop): key(ctrl-c)

terminal pane next: user.vscode("workbench.action.terminal.focusNextPane")
terminal pane (last | previous): user.vscode("workbench.action.terminal.focusPreviousPane")
(terminal switch | terminal pane switch): user.vscode("workbench.action.terminal.focusNextPane")
