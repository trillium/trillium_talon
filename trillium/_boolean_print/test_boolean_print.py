"""
Test file for boolean_print functionality.

From Talon REPL, run these commands:

# Test 1: Print when tag is not in ignore list (should print all with brackets)
actions.user.boolean_print("repeater", "This message should print")
actions.user.boolean_print("mouse", "This message should also print")
actions.user.boolean_print("debug", "Another message that should print")

# Output will be:
# [repeater] This message should print
# [mouse] This message should also print
# [debug] Another message that should print

# Test 2: Add tags to ignore list
# Edit debug_ignore_tags.csv and add (WITHOUT brackets):
#   repeater
#   mouse
# The file will auto-reload!

# Then test again:
actions.user.boolean_print("repeater", "This should NOT print")
actions.user.boolean_print("mouse", "This should NOT print")
actions.user.boolean_print("debug", "This SHOULD print")

# Output will be:
# [debug] This SHOULD print
"""
