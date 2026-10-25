"""Herdr tab resolver: spoken tab label -> (workspace_id, tab_id) -> focus.

Pure Python, no talon import, so it unit-tests without the Talon runtime.

Facts (verified 2026-10-24): `herdr tab focus` takes an ID only; labels come
from `herdr tab list` (JSON {result:{tabs:[{label, tab_id, workspace_id, ...}]}});
tab `number` is NOT unique and labels can repeat, so duplicate labels refuse
to resolve rather than guess.

Nothing here raises. `get_tabs()` serves a TTL cache and only shells out on a
cache miss; call `refresh()` from a timer/thread, never from a draw path or a
Talon hot path (use `get_tabs(allow_fetch=False)` there).
"""

import json
import subprocess
import time
import unicodedata

HERDR = "herdr"
HOST_APP = "WezTerm"
CACHE_TTL = 10.0
TIMEOUT = 5

_cache = {}  # host-key -> {"at": float, "tabs": list}


def herdr_cmd(args, host=None):
    """argv for a herdr call, local or `ssh <host> herdr ...` for a remote leg."""
    argv = [HERDR, *args]
    return ["ssh", host, *argv] if host else argv


def fetch_tabs(host=None):
    """One live `herdr tab list`. Returns a list of tab dicts, or None if
    herdr is unavailable / returns junk. Never raises."""
    try:
        out = subprocess.run(
            herdr_cmd(["tab", "list"], host),
            capture_output=True, text=True, timeout=TIMEOUT,
        ).stdout
        tabs = json.loads(out).get("result", {}).get("tabs")
        if not isinstance(tabs, list):
            return None
        return [t for t in tabs if isinstance(t, dict)]
    except Exception as e:
        print(f"[herdr_tabs] tab list failed ({host or 'local'}): {e}")
        return None


def refresh(host=None):
    """Live fetch into the cache. On failure the previous cache is kept.
    Returns the cached tabs."""
    key = host or ""
    tabs = fetch_tabs(host)
    if tabs is not None:
        _cache[key] = {"at": time.time(), "tabs": tabs}
    return list(_cache.get(key, {}).get("tabs", []))


def get_tabs(host=None, allow_fetch=True):
    """Cached tabs; refresh when older than CACHE_TTL (unless allow_fetch is
    False, in which case this never runs a subprocess)."""
    entry = _cache.get(host or "")
    if entry and (time.time() - entry["at"] < CACHE_TTL or not allow_fetch):
        return list(entry["tabs"])
    if not allow_fetch:
        return []
    return refresh(host)


def clean_label(label):
    """Label text with emoji/symbols, variation selectors, ZWJ and surrounding
    whitespace removed ("💎💎 Fixer" -> "Fixer"). Matching and spoken forms use
    this text only."""
    kept = []
    for ch in str(label or ""):
        cat = unicodedata.category(ch)
        if cat[0] == "S" or cat in ("Cf", "Co", "Cs", "Cc"):
            continue
        if 0xFE00 <= ord(ch) <= 0xFE0F or 0xE0100 <= ord(ch) <= 0xE01EF:
            continue
        if cat == "Mn" and kept and unicodedata.category(kept[-1])[0] == "S":
            continue
        kept.append(ch)
    return " ".join("".join(kept).split())


def _norm(label):
    return clean_label(label).lower()


def label_index(tabs):
    """{normalised label: [tab, ...]} skipping empty labels."""
    index = {}
    for t in tabs or []:
        key = _norm(t.get("label"))
        if key:
            index.setdefault(key, []).append(t)
    return index


def unique_labels(tabs):
    """{normalised label: label as shown} for labels held by exactly one tab."""
    return {k: clean_label(v[0]["label"]) for k, v in label_index(tabs).items() if len(v) == 1}


def resolve(label, host=None, allow_fetch=True):
    """Return (workspace_id, tab_id) for a unique, case-insensitive label match,
    else None (missing, duplicate, empty, herdr down). Never raises."""
    try:
        matches = label_index(get_tabs(host, allow_fetch)).get(_norm(label), [])
        if len(matches) != 1:
            if len(matches) > 1:
                print(f"[herdr_tabs] ambiguous label {label!r}: {len(matches)} tabs")
            return None
        tab = matches[0]
        ws, tid = tab.get("workspace_id"), tab.get("tab_id")
        return (ws, tid) if tid else None
    except Exception as e:
        print(f"[herdr_tabs] resolve failed: {e}")
        return None


def focus_commands(workspace_id, tab_id, host=None):
    """argv list for: workspace focus, tab focus, bring the host app forward."""
    cmds = []
    if workspace_id:
        cmds.append(herdr_cmd(["workspace", "focus", workspace_id], host))
    cmds.append(herdr_cmd(["tab", "focus", tab_id], host))
    cmds.append(["open", "-a", HOST_APP])
    return cmds


def focus_tab(label, host=None):
    """Focus the tab labelled `label` and bring WezTerm forward. Returns True
    if the focus commands ran. Never raises."""
    try:
        target = resolve(label, host)
        if not target:
            return False
        for argv in focus_commands(*target, host=host):
            subprocess.run(argv, check=False, timeout=TIMEOUT,
                           capture_output=True)
        return True
    except Exception as e:
        print(f"[herdr_tabs] focus {label!r} failed: {e}")
        return False
