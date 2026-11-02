from talon import Module, actions

mod = Module()


def _snapshot_phrase_history() -> str:
    """Build a string from phrase history (oldest to newest)."""
    from ..core.text import phrase_history as ph_module

    history = ph_module.phrase_history
    if not history:
        return ""
    # phrase_history is most-recent-first; reverse to get chronological order
    return "".join(reversed(history))


@mod.action_class
class Actions:
    def rapid_backspace(count: int = 300):
        """Execute backspace rapidly multiple times"""
        for _ in range(count):
            actions.key("backspace")

    def rapid_delete(count: int = 300):
        """Execute delete key rapidly multiple times"""
        for _ in range(count):
            actions.key("delete")

    def nuke_left():
        """Nuke left: save phrase history buffer, then rapid backspace.

        Pushes to the shared destroy stack so it can be restored with
        'restore destroy' or 'restore nuke'.
        """
        from .clear_text_commands import _destroy_stack

        deleted = _snapshot_phrase_history()
        if deleted:
            _destroy_stack.append(deleted)
        print(f"nuke_left: saved {len(deleted)} chars to destroy stack")
        actions.user.rapid_backspace(300)
        # Panel intentionally suppressed. `show_follow_on_hints("destroy", deleted)`
        # would pop the whole destroy panel, but it offers nothing useful here:
        # rapid_backspace blindly presses backspace 300x, and `deleted` is only the
        # phrase-history snapshot — there is no way to assess how many characters
        # were ACTUALLY removed from the field we're in, so the panel's count is
        # misleading. The destroy-stack save above still enables 'restore nuke'.
        # actions.user.show_follow_on_hints("destroy", deleted)
