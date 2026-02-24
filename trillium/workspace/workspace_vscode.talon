# Workspace Registry - VSCode-only commands
app: vscode
mode: command
-

workspace add (this | current):
    user.workspace_add_current()

workspace remove (this | current):
    user.workspace_remove_current()
