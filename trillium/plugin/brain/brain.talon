mode: command
-
# Start brain capture (enters brain mode for multi-utterance capture)
^brain <user.text>$:
    user.brain_capture(text)

# Append to the last brain entry (after brain_end)
^brain more <user.text>$:
    user.brain_more(text)
