"""Friction capture Talon actions."""

from talon import Context, Module, actions, cron

from . import ops, state
from .context import build_context_notes

mod = Module()
ctx = Context()

mod.tag("friction_mode", desc="Active when capturing friction")


def _friction_timeout():
    """Auto-end friction mode after timeout."""
    actions.user.friction_end()


def _start_timeout():
    """Start or restart the friction timeout."""
    if state.timeout_job:
        cron.cancel(state.timeout_job)
    state.timeout_job = cron.after(f"{state.FRICTION_TIMEOUT_MS}ms", _friction_timeout)


def _enter_friction_mode():
    """Enter friction mode with visual indicator."""
    state.friction_active = True
    ctx.tags = ["user.friction_mode"]
    actions.user.mode_indicator_set_color("ff0000")
    _start_timeout()


def _exit_friction_mode():
    """Exit friction mode and clear visual indicator."""
    state.reset_state()
    ctx.tags = []
    actions.user.mode_indicator_clear_color()
    if state.timeout_job:
        cron.cancel(state.timeout_job)
        state.timeout_job = None


def _parse_scope(scope_utterance: str) -> tuple[str, bool]:
    """Parse scope utterance into normalized scope and needs_review flag."""
    # Normalize scope: remove spaces, lowercase (handles "m c p" -> "mcp")
    scope = scope_utterance.replace(" ", "").lower()
    # Check if scope looks valid (letters/numbers only, reasonable length)
    needs_review = not scope.isalnum() or len(scope) > 20
    return scope, needs_review


@mod.action_class
class Actions:
    def friction_capture(scope_utterance: str):
        """Enter friction mode with a scope. First dictation becomes the ticket title."""
        print(f"[friction] friction_capture called with scope: {scope_utterance}")

        scope, needs_review = _parse_scope(scope_utterance)
        state.pending_scope = (scope, needs_review, scope_utterance)
        state.pending_context = build_context_notes(scope_utterance)
        state.current_issue_id = None

        _enter_friction_mode()

    def friction_append(text: str):
        """Append text to the current friction entry. Creates ticket on first dictation."""
        # First dictation after friction_capture - create the ticket
        if state.pending_scope and not state.current_issue_id:
            scope, needs_review, _ = state.pending_scope
            state.current_issue_id = ops.create_issue(text, state.pending_context, scope, needs_review)
            print(f"[friction] Created issue: {state.current_issue_id}")
            state.last_issue_id = state.current_issue_id
            if state.current_issue_id:
                state.save_last_issue_id(state.current_issue_id)
            state.pending_scope = None
            state.pending_context = None
        elif state.current_issue_id:
            # Subsequent dictation - append to existing issue
            ops.append_to_issue(state.current_issue_id, text)
        else:
            return

        _start_timeout()

    def friction_end():
        """End friction capture mode."""
        _exit_friction_mode()

    def friction_is_active() -> bool:
        """Check if friction mode is active."""
        return state.friction_active

    def friction_more(text: str):
        """Append text to the last friction ticket and re-enter friction mode."""
        if not state.last_issue_id:
            return

        ops.append_to_issue(state.last_issue_id, text)
        state.current_issue_id = state.last_issue_id
        _enter_friction_mode()

    def friction_get_last_id() -> str:
        """Get the ID of the last friction ticket."""
        return state.last_issue_id or ""
