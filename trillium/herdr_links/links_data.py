"""Links data: `herdr-links --json` scans merged into a per-tab URL history.

Pure Python, no talon import, so it unit-tests without the Talon runtime.

A history record is one URL seen in one Herdr tab on one host:
    {url, context, host, tab_id, tab_label, pane_id, first_seen, last_seen, seen_count}
`host` is "" for the local Herdr, else the herdr_tabs host string. The file
lives outside ~/.talon (a git repo) because URLs can carry tokens.
"""

import json
import os
import tempfile
from pathlib import Path

HISTORY_FILE = Path.home() / ".local" / "share" / "talon-links" / "history.json"
MAX_RECORDS = 300
PAGE_SIZE = 9
# Same exclusion herdr-links applies to its aggregated list (it does not
# filter the per-pane lists, which is what this module reads).
LOCAL_MARKERS = ("localhost", "127.0.0.1", "macbook")


def is_local_url(url):
    low = url.lower()
    return any(m in low for m in LOCAL_MARKERS)


def record_key(rec):
    return (rec.get("host") or "", rec.get("tab_id") or "", rec.get("url"))


def records_from_scan(data, host, tab_label, now):
    """Flatten one scan into fresh records, one per (tab, url). Panes with a
    read_error or no tab_id are skipped. Never raises on junk input."""
    out = {}
    if not isinstance(data, dict):
        return []
    for pane in data.get("panes") or []:
        if not isinstance(pane, dict) or pane.get("read_error"):
            continue
        tab_id = pane.get("tab_id")
        if not tab_id:
            continue
        for u in pane.get("urls") or []:
            url = (u or {}).get("url") if isinstance(u, dict) else None
            if not url or is_local_url(url):
                continue
            key = (host or "", tab_id, url)
            if key in out:
                continue
            out[key] = {
                "url": url,
                "context": (u.get("context") or "")[:100],
                "host": host or "",
                "tab_id": tab_id,
                "tab_label": tab_label or "",
                "pane_id": pane.get("pane_id"),
                "first_seen": now,
                "last_seen": now,
                "seen_count": 1,
            }
    return list(out.values())


def merge(history, fresh, max_records=MAX_RECORDS):
    """New history list: fresh records update last_seen/seen_count/context of
    existing ones (first_seen kept) or are added; the oldest last_seen are
    dropped past max_records."""
    by_key = {record_key(r): dict(r) for r in history or [] if isinstance(r, dict)}
    for rec in fresh:
        key = record_key(rec)
        old = by_key.get(key)
        if old is None:
            by_key[key] = dict(rec)
            continue
        old["last_seen"] = rec["last_seen"]
        old["seen_count"] = old.get("seen_count", 0) + 1
        old["pane_id"] = rec.get("pane_id") or old.get("pane_id")
        old["context"] = rec.get("context") or old.get("context", "")
        if rec.get("tab_label"):
            old["tab_label"] = rec["tab_label"]
    merged = sorted(by_key.values(), key=lambda r: r.get("last_seen", 0), reverse=True)
    return merged[:max_records]


def tab_rows(history, host, tab_id):
    """Records for one tab, newest last_seen first."""
    rows = [
        r
        for r in history or []
        if (r.get("host") or "") == (host or "") and r.get("tab_id") == tab_id
    ]
    return sorted(rows, key=lambda r: r.get("last_seen", 0), reverse=True)


def extend_frozen(frozen_urls, rows):
    """Row order for an open view: existing numbers never move; URLs not yet
    shown are appended in `rows` order."""
    seen = set(frozen_urls)
    return list(frozen_urls) + [r["url"] for r in rows if r["url"] not in seen]


def page_count(n, size=PAGE_SIZE):
    return max(1, (n + size - 1) // size)


def page_bounds(page, n, size=PAGE_SIZE):
    """(start, end) indexes of `page`, clamped to a valid page."""
    page = min(max(page, 0), page_count(n, size) - 1)
    return page * size, min(n, (page + 1) * size)


def short_age(seconds):
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def load(path=HISTORY_FILE):
    """History list from disk; [] when missing or unreadable."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return [r for r in data if isinstance(r, dict) and r.get("url")]
    except (OSError, ValueError, TypeError):
        return []


def save(history, path=HISTORY_FILE):
    """Atomic write, mode 0600."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".history-", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(history, f, indent=1)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
