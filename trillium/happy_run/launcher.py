# launcher.py - Launch a new terminal window
#
# Uses existing Talon actions:
#   - user.switcher_focus_app() to focus Terminal
#   - key("cmd-n") to open a new window
#
# ## Existing patterns (reference)
#
# ### Terminal.app via bash function (`terminal`)
# ```bash
# terminal () {
# 	local dir="$PWD"
# 	osascript <<EOF
# tell application "Terminal"
#   activate
#   do script "cd '$dir'"
# end tell
# EOF
# }
# ```
#
# ### iTerm2 via happy_run.py
# ```python
# applescript = f'tell application "iTerm" to create window with default profile command "cd {current_dir}"'
# subprocess.run(["osascript", "-e", applescript])
# ```

from talon import Module, actions, ui

TERMINAL_BUNDLE = "com.apple.Terminal"

mod = Module()


@mod.action_class
class Actions:
    def terminal_new_window():
        """Focus Terminal.app and open a new window"""
        app = ui.apps(bundle=TERMINAL_BUNDLE)[0]
        actions.user.switcher_focus_app(app)
        actions.key("cmd-n")
