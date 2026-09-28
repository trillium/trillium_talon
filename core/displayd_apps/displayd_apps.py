"""displayd panel app-switcher server (Talon side).

Exposes (a) the running-application list and (b) a focus action to the
wall panel WITHOUT the command_client keystroke path: driving app focus
from a panel must never depend on first focusing an editor to inject a
keystroke into. Instead this module owns a tiny file protocol in a tmp
comm dir (``displayd-apps-<uid>/``, same convention as command_client's
``get_communication_dir_path``):

- ``apps_state.json``: Talon-written, event-driven (app_launch /
  app_close / ready, plus a 60s resync safety net). The Mac-side bridge
  reads it on mtime change only, so the steady-state cost is ~zero.
- ``focus_request.json`` -> ``focus_response.json``: the bridge writes
  ``{"id", "name", "ts"}``; a 150ms cron tick consumes it (unlink on
  read, so a retried fetch never double-fires), focuses via the real
  ``actions.user.switcher_focus`` entry point, and answers
  ``{"id", "ok", "focused"}``. TTL 10s: stale requests never run.

brain-15l95 avoidance (the command_client CRITICAL): the busy-wait
lives in the BRIDGE process (its own OS process/thread), never on
Talon's serial main thread. Talon's side of this protocol is one
non-blocking stat per tick plus work only when a request exists -- no
fourth copy of the rpc_client blocking primitive is added or used.

Payload is bounded on purpose: at most MAX_APPS names, each sanitized
(control characters stripped, truncated), no window titles, no paths.
"""

import json
import os
import tempfile
import time

MAX_APPS = 30
NAME_CHARS = 48
FOCUS_TTL = 10.0
TICK = "150ms"
RESYNC = "60s"


def comm_dir():
    """Tmp comm dir for this protocol (bridge + Talon agree here)."""
    suffix = "-%s" % os.getuid() if hasattr(os, "getuid") else ""
    path = os.path.join(tempfile.gettempdir(), "displayd-apps%s" % suffix)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def clean_name(name):
    """Bound one OS app name for the wire. Never raises."""
    text = name if isinstance(name, str) else ""
    text = "".join(ch for ch in text.strip() if ch.isprintable())
    return text[:NAME_CHARS]


def build_state_doc(names, focused):
    """One apps_state.json document from raw OS names. Bounded."""
    seen, apps = set(), []
    for raw in names or []:
        name = clean_name(raw)
        if name and name not in seen:
            seen.add(name)
            apps.append(name)
        if len(apps) >= MAX_APPS:
            break
    # Sorted: the OS order is arbitrary, and stable rows keep panel
    # tap targets from jumping around between ticks.
    apps.sort(key=str.casefold)
    return {"ts": time.time(), "apps": apps,
            "focused": clean_name(focused)}


def _atomic_write(path, doc):
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def handle_focus_doc(doc, focus):
    """Execute one focus request. Returns the response doc (never raises).

    TTL-expiry and unknown/empty names refuse WITHOUT calling focus;
    the name comes from the bridge but is resolved against live apps by
    switcher_focus itself, so a forged name can only ever no-op."""
    req_id = doc.get("id") if isinstance(doc, dict) else None
    name = clean_name(doc.get("name")) if isinstance(doc, dict) else ""
    try:
        age = time.time() - float(doc.get("ts", 0))
    except (TypeError, ValueError):
        age = float("inf")
    if not name:
        return {"id": req_id, "ok": False, "error": "empty app name"}
    if age < 0 or age > FOCUS_TTL:
        return {"id": req_id, "ok": False, "error": "stale request"}
    try:
        focus(name)
    except Exception as exc:
        return {"id": req_id, "ok": False,
                "error": str(exc)[:120]}
    return {"id": req_id, "ok": True, "focused": name}


try:
    from talon import Module, actions, app, cron, ui

    mod = Module()
    _DIR = comm_dir()
    _STATE = os.path.join(_DIR, "apps_state.json")
    _REQUEST = os.path.join(_DIR, "focus_request.json")
    _RESPONSE = os.path.join(_DIR, "focus_response.json")

    def _write_state():
        try:
            names = [a.name for a in ui.apps(background=False)]
            active = ui.active_app()
            _atomic_write(_STATE, build_state_doc(
                names, active.name if active is not None else ""))
        except Exception as exc:
            print("displayd_apps state write failed: %s" % exc)

    def _tick():
        if not os.path.exists(_REQUEST):
            return
        try:
            doc = read_json(_REQUEST)
        except Exception:
            doc = None
        try:
            os.unlink(_REQUEST)
        except Exception:
            pass
        if doc is None:
            return
        resp = handle_focus_doc(doc, actions.user.switcher_focus)
        try:
            _atomic_write(_RESPONSE, resp)
        except Exception as exc:
            print("displayd_apps response write failed: %s" % exc)

    def _on_ready():
        _write_state()

    def _on_app_event(_arg=None):
        _write_state()

    ui.register("app_launch", _on_app_event)
    ui.register("app_close", _on_app_event)
    app.register("ready", _on_ready)
    cron.interval(TICK, _tick)
    cron.interval(RESYNC, _write_state)
except ImportError:
    pass
