# Active while waiting for second input in a two-step recall command
# (combine, rename, alias)
tag: user.recall_pending_input
-
<user.saved_window_names>:
    user.recall_pending_finish(saved_window_names)

<user.word>:
    user.recall_pending_finish(word)

<user.raw_prose>:
    user.recall_pending_finish(raw_prose)
