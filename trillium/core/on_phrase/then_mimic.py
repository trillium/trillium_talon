"""Then-mimic — splits phrases on "then" and executes segments sequentially.

Called by the central on_phrase.py orchestrator, not self-registering.
"""

from talon import scope, actions, cron

_pending_mimics: list[list[str]] = []


def on_pre_phrase(d):
    global _pending_mimics

    # Only split on "then" when command mode is active
    modes = scope.get("mode", set())
    if "command" not in modes:
        return

    # Don't split on "then" during pondering — it's normal dictation text
    tags = scope.get("tag", set())
    if "user.pondering" in tags:
        return

    words = d.get("phrase", [])
    if not words:
        return

    word_strings = [str(w) for w in words]
    if "then" not in word_strings:
        return

    # Split on "then" into segments
    segments = []
    current = []
    for w in word_strings:
        if w == "then":
            if current:
                segments.append(current)
                current = []
        else:
            current.append(w)
    if current:
        segments.append(current)

    # Need at least 2 segments for "then" to be meaningful
    if len(segments) < 2:
        return

    # Cancel the current phrase entirely — we'll mimic each segment
    d["phrase"] = []
    if "parsed" in d:
        d["parsed"]._sequence = []

    _pending_mimics = segments


def on_post_phrase(_):
    global _pending_mimics
    segments = _pending_mimics
    _pending_mimics = []
    if segments:
        _run_segment(0, segments)


def _run_segment(idx, segments):
    if idx >= len(segments):
        return
    words = segments[idx]
    actions.mimic(" ".join(words))
    if idx + 1 < len(segments):
        cron.after("10ms", lambda: _run_segment(idx + 1, segments))
