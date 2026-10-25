"""Re-entry card: after a voice tab switch, show a short "where you are" card
on the captain's Sidecar pane (phase 1 of inbox-8ckg).

Fields (fixed, short, deterministic, no LLM): what you last said to this agent,
what it is doing, its state, and what changed since you last looked.

Rules: never delay or break the switch (call `on_switch` and move on; it runs on
a daemon thread and swallows every error), Sidecar is local-only, and nothing
beyond the card text is kept: per agent we store only the last spoken command
(<= MAX_ASKED chars), a timestamp, and the last state/title seen.

"What you said" covers voice commands only (typed text is not seen by Talon).

Pure helpers (`build_card`, `state_word`, `since_text`) take plain data so they
unit-test without the Talon runtime; only `_register_phrase_hook` imports talon.
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

HERDR = "herdr"
SIDECAR = os.path.expanduser("~/.local/bin/sidecar")
SIDECAR_URL = "http://127.0.0.1:8791"
TOKEN_FILE = Path.home() / ".config/sidecar/token"
STATE_DIR = Path.home() / ".local/state/talon-reentry"
STATE_FILE = STATE_DIR / "state.json"
CARD_DIR = STATE_DIR / "cards"
MAX_ASKED = 160
TIMEOUT = 3

_lock = threading.Lock()
_current = None  # key of the agent the captain is currently "in"


def state_word(agent_status):
    """herdr agent_status -> the three words the card uses."""
    s = (agent_status or "").lower()
    if s == "working":
        return "working"
    if s == "blocked":
        return "blocked"
    if s in ("idle", "done"):
        return "waiting on you"
    return "unknown"


def since_text(prev, now_state, now_title, now_ts):
    """One short line: what changed since the captain last looked."""
    if not prev or not prev.get("seen"):
        return "first look"
    mins = max(0, int((now_ts - prev["seen"]) // 60))
    away = "just now" if mins < 1 else f"{mins}m ago"
    changes = []
    if prev.get("state") and prev["state"] != now_state:
        changes.append(f"{prev['state']} -> {now_state}")
    if prev.get("title") and now_title and prev["title"] != now_title:
        changes.append("new activity")
    return f"last looked {away}; " + ("; ".join(changes) if changes else "no change")


def build_card(key, asked, title, state, since):
    """Markdown card, a handful of lines so it never needs to scroll."""
    lines = [f"# {key}", ""]
    lines.append(f"**You asked:** {asked or '(nothing yet)'}")
    lines.append(f"**Doing:** {title or '(no title)'}")
    lines.append(f"**State:** {state}")
    lines.append(f"**Since:** {since}")
    return "\n".join(lines) + "\n"


def _load():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save(data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, STATE_FILE)


def note_utterance(text, now=None):
    """Record a spoken command against the agent the captain is currently in."""
    try:
        text = (text or "").strip()
        if not text:
            return
        with _lock:
            if not _current:
                return
            data = _load()
            # the switch phrase itself ("mayor") is not something you asked
            if text.lower() in {k.lower() for k in data} | {_current.lower()}:
                return
            rec = data.setdefault(_current, {})
            rec["asked"] = text[:MAX_ASKED]
            rec["asked_at"] = now or time.time()
            _save(data)
    except Exception:
        pass


def _agent_for_tab(tab_id):
    """herdr agent dict whose tab_id matches (local server only), else None."""
    if not tab_id:
        return None
    out = subprocess.run(
        [HERDR, "agent", "list"], capture_output=True, text=True, timeout=TIMEOUT
    ).stdout
    for a in json.loads(out).get("result", {}).get("agents", []):
        if a.get("tab_id") == tab_id:
            return a
    return None


def _show(path, title):
    env = dict(os.environ, SIDECAR_URL=SIDECAR_URL)
    env["SIDECAR_TOKEN"] = TOKEN_FILE.read_text().strip()
    subprocess.run(
        [SIDECAR, "show", str(path), "--title", title],
        env=env,
        capture_output=True,
        timeout=TIMEOUT,
        check=False,
    )


def _run(key, tab_id):
    global _current
    now = time.time()
    agent = None
    try:
        agent = _agent_for_tab(tab_id)
    except Exception:
        pass
    state = state_word(agent.get("agent_status") if agent else None)
    title = (agent or {}).get("terminal_title_stripped") or ""
    with _lock:
        data = _load()
        rec = data.setdefault(key, {})
        card = build_card(key, rec.get("asked"), title, state, since_text(rec, state, title, now))
        rec.update(seen=now, state=state, title=title)
        _save(data)
        _current = key
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    path = CARD_DIR / (key.lower().replace(" ", "-") + ".md")
    path.write_text(card)
    _show(path, key)


def on_switch(key, tab_id=None):
    """Fire-and-forget. Never raises, never blocks the caller."""
    global _current
    try:
        with _lock:
            _current = key  # attribute following utterances even if the card fails
        threading.Thread(target=_safe_run, args=(key, tab_id), daemon=True).start()
    except Exception:
        pass


def _safe_run(key, tab_id):
    try:
        _run(key, tab_id)
    except Exception:
        pass


def _register_phrase_hook():
    try:
        from talon import speech_system

        def _on_phrase(j):
            words = j.get("text") if isinstance(j, dict) else None
            if words:
                note_utterance(words)

        speech_system.register("post:phrase", _on_phrase)
    except Exception:
        pass


_register_phrase_hook()
