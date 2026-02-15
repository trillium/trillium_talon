# Workspace Registry - global commands (work from anywhere)
mode: command
-

workspace <user.workspace_alias>:
    user.workspace_open(workspace_alias)

workspace list:
    user.workspace_list()

workspace alias:
    user.workspace_edit_aliases()

workspace remove <user.workspace_alias>:
    user.workspace_remove_by_alias(workspace_alias)

workspace next: app.window_next()
workspace (last | previous): app.window_previous()
