# text_injector.py - Verify window state, then inject appropriate input
#
# This is a state machine, not just a typing function.
# Before injecting anything, we must:
#   1. Verify our target window is the active window
#   2. Detect what state the app is in
#   3. Inject the right thing for that state
#
# ## Window states
#
# | State            | How to detect                  | What to inject       |
# |------------------|--------------------------------|----------------------|
# | shell_ready      | title stable, no ✳             | "happy" + enter      |
# | happy_ready      | ✳ in title                     | user prompt + enter  |
# | needs_consent    | interactive prompt (e.g. "1")  | number + enter       |
# | still_loading    | title changing                 | nothing, keep polling|
#
# ## Injection method
#
# Uses Talon's built-in actions.insert() + actions.key("enter")
# NOT char-by-char ctrl.key_press — insert() is more robust
# and works correctly when the window has focus.
#
# ## Focus verification
#
# Before injecting, confirm ui.active_window() matches our target window.
# If not, use user.switcher_focus_window(window) from community app_switcher.
#
# ## Open questions
#
# - How to detect "needs_consent" state? Title? Content? Timeout heuristic?
# - What are the possible consent prompts? Just "1" or others?
# - Should we retry focus if switcher_focus_window fails?
