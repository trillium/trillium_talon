# Voice commands for the window recall system
#
# Save a window:     "recall assign edgar" or "recall save edgar"
# Switch to it:      "edgar"
# Dictate into it:   "edgar hello world"
# Press number:      "edgar 1"
# Switch + Enter:    "edgar bravely"
# Dictate + Enter:   "edgar hello world bravely" (see dictation_ender list)
# List all:          "recall list"
# Forget one:        "recall forget edgar"
# Forget all:        "recall forget all"
# Add alias:         "recall alias edgar egger"
# Remove alias:      "recall unalias egger"
# Combine:           "recall combine velma vilma"
# Rename:            "recall rename edgar newname"
# Promote alias:     "recall promote vilma"
# Set default cmd:   "recall config edgar claude"
# Clear default cmd:  "recall config edgar clear"
# Restore terminal:  "recall restore edgar"
# Revive archived:   "recall revive boat"
# Show archive:      "recall archive"
# Purge from archive:"recall purge boat"
# Window status:     "recall status"
# Help screen:       "recall help"
# Dismiss overlay:   "recall close"

(recall save | save recall | recall assign) <user.text>:
    user.save_window(text)

<user.saved_window_names>:
    user.recall_window(saved_window_names)

(recall forget | forget recall) <user.saved_window_names>:
    user.forget_window(saved_window_names)

(recall list | list recalls):
    user.list_saved_windows()

recall forget all:
    user.forget_all_windows()

recall alias <user.saved_window_names> <user.word>:
    user.add_recall_alias(saved_window_names, word)

recall (unalias | remove alias) <user.saved_window_names>:
    user.remove_recall_alias(saved_window_names)

recall edit (command | commands | list):
    user.recall_edit_commands()

recall config <user.saved_window_names> clear:
    user.recall_clear_command(saved_window_names)

recall config <user.saved_window_names> <user.recall_command_name>:
    user.recall_set_command(saved_window_names, recall_command_name)

recall restore <user.saved_window_names>:
    user.restore_window(saved_window_names)

recall rename <user.saved_window_names> <user.word>:
    user.recall_rename(saved_window_names, word)

recall promote <user.text>:
    user.recall_promote(text)

recall combine <user.saved_window_names> <user.saved_window_names>:
    user.recall_combine(saved_window_names_1, saved_window_names_2)

recall combine <user.saved_window_names>:
    user.recall_combine_start(saved_window_names)

recall revive <user.word>:
    user.recall_revive(word)

recall archive:
    user.recall_list_archive()

recall purge <user.word>:
    user.recall_purge(word)

recall (status | info):
    user.show_recall_status()

recall (help | show):
    user.show_recall_help()

recall border:
    user.recall_toggle_border()

recall close:
    user.hide_recall_overlay()

<user.saved_window_names> {user.dictation_ender}$:
    user.recall_window_and_enter(saved_window_names)

<user.saved_window_names> <number_small>$:
    user.recall_number(saved_window_names, number_small)

<user.saved_window_names> <user.raw_prose> {user.dictation_ender}$:
    user.dictate_to_window_and_enter(saved_window_names, raw_prose)

<user.saved_window_names> <user.raw_prose>:
    user.dictate_to_window(saved_window_names, raw_prose)
