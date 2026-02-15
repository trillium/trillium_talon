mode: command
-
# Start ticket capture (enters ticket mode)
^ticket <user.text>$:
    user.ticket_capture(user.text)
