tag: user.ticket_mode
mode: all
-
# Continue dictating - appends to ticket buffer
^<user.text>$:
    user.ticket_append(user.text)

# End ticket capture mode
^ticket end$:
    user.ticket_end()
