# Voice commands for the window recall system

(recall save | save recall) <user.text>:
    user.boolean_print("recall.talon", "save_window triggered with: {text}")
    user.save_window(text)

recall <user.saved_window_names>:
    user.boolean_print("recall.talon", "recall_window triggered with: {saved_window_names}")
    user.recall_window(saved_window_names)

(recall forget | forget recall) <user.saved_window_names>:
    user.boolean_print("recall.talon", "forget_window triggered with: {saved_window_names}")
    user.forget_window(saved_window_names)

(recall list | list recalls):
    user.boolean_print("recall.talon", "list_saved_windows triggered")
    user.list_saved_windows()

recall forget all:
    user.boolean_print("recall.talon", "forget_all_windows triggered")
    user.forget_all_windows()
