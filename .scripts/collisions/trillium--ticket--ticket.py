"""Ticket capture Talon actions."""

from talon import Context, Module, actions, cron

from . import agent, state

mod = Module()
ctx = Context()

mod.tag("ticket_mode", desc="Active when capturing ticket dictation")


def _ticket_timeout():
    """Auto-end ticket mode after timeout."""
    actions.user.ticket_end()


def _start_timeout():
    """Start or restart the ticket timeout."""
    if state.timeout_job:
        cron.cancel(state.timeout_job)
    state.timeout_job = cron.after(f"{state.TICKET_TIMEOUT_MS}ms", _ticket_timeout)


def _enter_ticket_mode():
    """Enter ticket mode with visual indicator."""
    state.ticket_active = True
    ctx.tags = ["user.ticket_mode"]
    actions.user.mode_indicator_set_color("ff8800")
    _start_timeout()


def _exit_ticket_mode():
    """Exit ticket mode, clear indicator, and spawn background agent."""
    scope = state.scope
    raw_scope = state.raw_scope
    text_chunks = list(state.text_buffer)

    state.reset_state()
    ctx.tags = []
    actions.user.mode_indicator_clear_color()
    if state.timeout_job:
        cron.cancel(state.timeout_job)
        state.timeout_job = None

    if text_chunks:
        raw_text = " ".join(text_chunks)
        agent.spawn_refinement_agent(raw_text, scope, raw_scope)
    else:
        print("[ticket] No text captured, skipping agent")


def _parse_scope(scope_utterance: str) -> str:
    """Parse scope utterance into normalized scope."""
    return scope_utterance.replace(" ", "").lower()


@mod.action_class
class Actions:
    def ticket_capture(scope_utterance: str):
        """Enter ticket mode with a scope. Dictation afterwards captures the idea."""
        print(f"[ticket] ticket_capture called with scope: {scope_utterance}")
        state.scope = _parse_scope(scope_utterance)
        state.raw_scope = scope_utterance
        state.text_buffer = []
        _enter_ticket_mode()

    def ticket_append(text: str):
        """Append dictated text to the ticket buffer."""
        state.text_buffer.append(text)
        _start_timeout()

    def ticket_end():
        """End ticket capture and spawn refinement agent."""
        _exit_ticket_mode()

    def ticket_is_active() -> bool:
        """Check if ticket mode is active."""
        return state.ticket_active
