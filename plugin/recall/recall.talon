# Voice commands for the window recall system
#
# Save a window:     "recall assign edgar" or "recall save edgar"
# Switch to it:      "edgar"
# Dictate into it:   "edgar hello world"
# List all:          "recall list"
# Forget one:        "recall forget edgar"
# Forget all:        "recall forget all"

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

<user.saved_window_names> <user.raw_prose>:
    user.dictate_to_window(saved_window_names, raw_prose)
