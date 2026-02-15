"""Ticket state management."""

TICKET_TIMEOUT_MS = 90_000  # 90 seconds

# Global state
ticket_active = False
timeout_job = None
scope = None        # str: normalized scope
raw_scope = None    # str: original utterance
text_buffer = []    # list[str]: accumulated dictation chunks


def reset_state():
    """Reset all ticket state."""
    global ticket_active, scope, raw_scope, text_buffer
    ticket_active = False
    scope = None
    raw_scope = None
    text_buffer = []
