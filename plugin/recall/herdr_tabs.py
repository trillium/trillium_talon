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
import re
import subprocess
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

HERDR = "herdr"
HOST_APP = "WezTerm"
CACHE_TTL = 10.0
TIMEOUT = 5

# Remote hosts whose tabs join the spoken list (ssh aliases). Edit this list.
HOSTS = ["mini0"]
# Spoken list skips transient worker tabs whose cleaned label starts with one
# of these; EXTRA_ALLOWED re-admits specific labels (e.g. "fm-advisor").
FM_PREFIXES = ("fm-",)
EXTRA_ALLOWED = []
# Never let a dead host stall a refresh; BatchMode forbids password prompts.
SSH_OPTS = ["-o", "ConnectTimeout=3", "-o", "BatchMode=yes"]
# Consecutive failed refreshes before a host's stale cache is dropped.
MAX_MISSES = 3

_cache = {}  # host-key -> {"at": float, "tabs": list}
_misses = {}  # host-key -> consecutive failed refreshes


def herdr_cmd(args, host=None):
    """argv for a herdr call, local or `ssh <host> herdr ...` for a remote leg."""
    argv = [HERDR, *args]
    return ["ssh", *SSH_OPTS, host, *argv] if host else argv


def fetch_tabs(host=None):
    """One live `herdr tab list`. Returns a list of tab dicts, or None if
    herdr is unavailable / returns junk. Never raises."""
    try:
        out = subprocess.run(
            herdr_cmd(["tab", "list"], host),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
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
        _misses[key] = 0
    else:
        _misses[key] = _misses.get(key, 0) + 1
        if _misses[key] >= MAX_MISSES:
            _cache.pop(key, None)
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
    # keycap emoji "0️⃣" is digit + optional FE0F + U+20E3: drop the digit too
    text = re.sub("[0-9#*]\ufe0f?\u20e3", "", str(label or ""))
    for ch in text:
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
    return {
        k: clean_label(v[0]["label"])
        for k, v in label_index(tabs).items()
        if len(v) == 1
    }


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
            subprocess.run(argv, check=False, timeout=TIMEOUT, capture_output=True)
        return True
    except Exception as e:
        print(f"[herdr_tabs] focus {label!r} failed: {e}")
        return False


# --- multi-host: local + HOSTS merged, labels unique across all of them ---


def refresh_all(hosts=None):
    """Refresh local + every host in parallel (bounded by TIMEOUT; unreachable
    hosts just count a miss). Returns merge_tabs() of the caches."""
    hosts = list(HOSTS if hosts is None else hosts)
    legs = [None, *hosts]
    with ThreadPoolExecutor(max_workers=len(legs)) as pool:
        list(pool.map(refresh, legs))
    return merge_tabs(hosts)


def merge_tabs(hosts=None):
    """[(host-or-None, tab)] from the caches only; never runs a subprocess."""
    hosts = list(HOSTS if hosts is None else hosts)
    return [(h, t) for h in [None, *hosts] for t in get_tabs(h, allow_fetch=False)]


def unique_labels_all(merged):
    """{normalised label: label as shown} for labels held by exactly one tab
    across ALL hosts."""
    return unique_labels([t for _, t in merged])


def voice_labels(merged):
    """unique_labels_all minus FM_PREFIXES labels (unless in EXTRA_ALLOWED)."""
    allowed = {_norm(x) for x in EXTRA_ALLOWED}
    return {
        k: v
        for k, v in unique_labels_all(merged).items()
        if k in allowed or not k.startswith(tuple(p.lower() for p in FM_PREFIXES))
    }


def resolve_any(label, hosts=None):
    """(host, workspace_id, tab_id) for a label unique across every host,
    from cache only, else None. Never raises."""
    try:
        merged = merge_tabs(hosts)
        matches = [(h, t) for h, t in merged if _norm(t.get("label")) == _norm(label)]
        if len(matches) != 1 or not _norm(label):
            if len(matches) > 1:
                print(f"[herdr_tabs] ambiguous label {label!r}: {len(matches)} tabs")
            return None
        host, tab = matches[0]
        tid = tab.get("tab_id")
        return (host, tab.get("workspace_id"), tid) if tid else None
    except Exception as e:
        print(f"[herdr_tabs] resolve_any failed: {e}")
        return None


def focus_any(label, hosts=None):
    """Focus a label unique across local + HOSTS, routing to its host. Cache
    only for resolution (no ssh on the voice path); the focus legs run ssh."""
    try:
        target = resolve_any(label, hosts)
        if not target:
            return False
        host, ws, tid = target
        for argv in focus_commands(ws, tid, host=host):
            subprocess.run(argv, check=False, timeout=TIMEOUT, capture_output=True)
        return True
    except Exception as e:
        print(f"[herdr_tabs] focus {label!r} failed: {e}")
        return False
