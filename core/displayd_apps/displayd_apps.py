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
- ``capture_request.json`` -> ``capture_response.json``: the bridge
  writes ``{"id", "x", "y", "w", "h", "ts"}``; the same tick
  captures the rect via the real ``screen.capture_rect`` entry point
  (the mouse-grid zoom uses the same call), writes the PNG to the
  FIXED ``capture_image.png`` beside them, and answers
  ``{"id", "ok"}``. Same TTL shape. The bridge reads the file, so
  no image bytes cross the JSON; the filename is fixed, never from
  the channel.

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
CAPTURE_TTL = 10.0
CAPTURE_IMAGE = "capture_image.png"
CAPTURE_MAX_W, CAPTURE_MAX_H = 960, 720
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


def _rect_numbers(doc):
    """(x, y, w, h) floats from a capture request, else None."""
    try:
        x = float(doc.get("x"))
        y = float(doc.get("y"))
        w = float(doc.get("w"))
        h = float(doc.get("h"))
    except (TypeError, ValueError, AttributeError):
        return None
    if abs(x) > 100000 or abs(y) > 100000:
        return None
    if not (0 < w <= CAPTURE_MAX_W and 0 < h <= CAPTURE_MAX_H):
        return None
    if w * h > 4 * 480 * 360:
        return None
    return (x, y, w, h)


def handle_capture_doc(doc, rect_of, shoot, image_path):
    """Execute one capture request. Returns the response doc (never raises).

    TTL-expiry and out-of-bounds rects refuse WITHOUT capturing.
    ``rect_of`` builds the rect, ``shoot`` captures it to ``image_path``
    (both injected so tests run without Talon); the PNG filename is
    fixed, never taken from the request. Runs inside the existing
    150ms tick like focus -- a synchronous in-process capture, no new
    blocking primitive, no canvas to hide (the panel is not a Talon
    canvas, unlike the mouse grid)."""
    req_id = doc.get("id") if isinstance(doc, dict) else None
    if not isinstance(doc, dict) or not req_id:
        return {"id": req_id, "ok": False, "error": "bad request"}
    try:
        age = time.time() - float(doc.get("ts", 0))
    except (TypeError, ValueError):
        age = float("inf")
    if age < 0 or age > CAPTURE_TTL:
        return {"id": req_id, "ok": False, "error": "stale request"}
    nums = _rect_numbers(doc)
    if nums is None:
        return {"id": req_id, "ok": False, "error": "bad rect"}
    try:
        rect = rect_of(*nums)
    except Exception as exc:
        return {"id": req_id, "ok": False,
                "error": str(exc)[:120]}
    try:
        shoot(rect, image_path)
    except Exception as exc:
        return {"id": req_id, "ok": False,
                "error": str(exc)[:120]}
    return {"id": req_id, "ok": True}


try:
    from talon import Module, actions, app, cron, screen, ui

    mod = Module()
    _DIR = comm_dir()
    _STATE = os.path.join(_DIR, "apps_state.json")
    _REQUEST = os.path.join(_DIR, "focus_request.json")
    _RESPONSE = os.path.join(_DIR, "focus_response.json")
    _CAPTURE_REQUEST = os.path.join(_DIR, "capture_request.json")
    _CAPTURE_RESPONSE = os.path.join(_DIR, "capture_response.json")
    _CAPTURE_IMAGE = os.path.join(_DIR, CAPTURE_IMAGE)

    def _write_state():
        try:
            names = [a.name for a in ui.apps(background=False)]
            active = ui.active_app()
            _atomic_write(_STATE, build_state_doc(
                names, active.name if active is not None else ""))
        except Exception as exc:
            print("displayd_apps state write failed: %s" % exc)

    def _consume(path):
        """Unlink-on-read one request file; None when absent/unreadable."""
        if not os.path.exists(path):
            return None
        try:
            doc = read_json(path)
        except Exception:
            doc = None
        try:
            os.unlink(path)
        except Exception:
            pass
        return doc

    def _tick():
        # Each verb independent: no early return may starve the other.
        doc = _consume(_REQUEST)
        if doc is not None:
            resp = handle_focus_doc(doc, actions.user.switcher_focus)
            try:
                _atomic_write(_RESPONSE, resp)
            except Exception as exc:
                print("displayd_apps response write failed: %s" % exc)
        cap_doc = _consume(_CAPTURE_REQUEST)
        if cap_doc is None:
            return

        def _shoot(rect, path):
            screen.capture_rect(rect).write_file(path)

        cap_resp = handle_capture_doc(cap_doc, ui.Rect, _shoot,
                                      _CAPTURE_IMAGE)
        try:
            _atomic_write(_CAPTURE_RESPONSE, cap_resp)
        except Exception as exc:
            print("displayd_apps capture write failed: %s" % exc)

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
