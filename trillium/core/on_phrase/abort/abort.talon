# Registers {user.abort_phrase}$ as a back-anchored Talon grammar rule.
# Required so abort.py's get_capture() synthetic VMCapture resolves correctly
# in Talon's executor when a phrase ends with the abort word (e.g. "say hello cancel").
# Without this file, Talon's executor throws KeyError on the encoded rule name.
{user.abort_phrase}$:
    user.abort_phrase_command()
