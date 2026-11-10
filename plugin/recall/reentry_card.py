"""Event emitter for Sidecar's re-entry card (inbox-8ckg).

Talon only reports what happened; Sidecar builds and shows the card (sidecar docs/events.md).
Two events, both POST /v1/events, fire-and-forget on a daemon thread:
  agent.switch  {agent, tab_id?}   a voice tab switch
  voice.phrase  {text}             each spoken phrase

Never delays or breaks a switch: every error is swallowed. The token is read from disk per call, never printed.
"""

import json
import threading
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8791/v1/events"
TOKEN_FILE = Path.home() / ".config/sidecar/token"
TIMEOUT = 2


def _post(body):
    try:
        req = urllib.request.Request(
            URL,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + TOKEN_FILE.read_text().strip(),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=TIMEOUT).close()
    except Exception:
        pass


def emit(body):
    """Send one event without blocking the caller."""
    try:
        threading.Thread(target=_post, args=(body,), daemon=True).start()
    except Exception:
        pass


def on_switch(key, tab_id=None):
    body = {"type": "agent.switch", "agent": key}
    if tab_id:
        body["tab_id"] = tab_id
    emit(body)


def _register_phrase_hook():
    try:
        from talon import speech_system

        def _on_phrase(j):
            words = j.get("text") if isinstance(j, dict) else None
            if words:
                emit({"type": "voice.phrase", "text": words})

        speech_system.register("post:phrase", _on_phrase)
    except Exception:
        pass


_register_phrase_hook()
