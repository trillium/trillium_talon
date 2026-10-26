"""
Herdr links - "<tab name> links" switches Herdr to that tab (the recall
switch, user.herdr_tab_focus) and shows the URLs seen in it.

Data comes from `herdr-links --json --tab <id> [--machine <host>]`, run by
links_scan.ScanRunner as a child process that a 1s cron tick polls: the voice
and draw paths never run a subprocess of their own and never wait on herdr.
Every voice-named tab on local + herdr_tabs.HOSTS is scanned every
`user.links_capture_interval` seconds into links_data.HISTORY_FILE, so links
stay listed after they scroll off screen; the open tab rescans every 10s.
"""

import os
import subprocess
import time

from talon import Context, Module, actions, clip, cron, settings

from ...plugin.recall import herdr_tabs
from . import links_data, links_overlay
from .links_scan import Job, ScanRunner, find_tool, scan_env

mod = Module()
mod.tag("links_active", desc="Herdr links overlay is showing")
mod.setting(
    "links_capture_interval",
    type=int,
    default=60,
    desc="Seconds between background herdr-links scans of every voice-named Herdr tab (0 = off)",
)
ctx = Context()

VIEW_RESCAN_SECONDS = 10
FIRST_CAPTURE_DELAY = 5  # after herdr_tab_voice's first tab-cache refresh (2s)

_runner = ScanRunner(tool=find_tool("herdr-links"))
_history: list[dict] = links_data.load()
_live: dict = {}  # (host, tab_id) -> urls in that tab's latest scan
_errors: dict = {}  # (host, tab_id) -> last scan error
_loaded_at = time.time()
_last_capture = 0.0
_view = None  # {"label", "host", "tab_id", "urls", "page", "status", "enqueued_at"}


# ── View ──


def _view_key():
    return (_view["host"], _view["tab_id"]) if _view and _view["tab_id"] else None


def _render():
    if not _view:
        return
    by_url = {
        r["url"]: r
        for r in links_data.tab_rows(_history, _view["host"], _view["tab_id"])
    }
    live = _live.get(_view_key(), set())
    rows = [
        {
            "url": u,
            "last_seen": by_url.get(u, {}).get("last_seen", time.time()),
            "live": u in live,
        }
        for u in _view["urls"]
    ]
    links_overlay.update(
        _view["label"], _view["host"], rows, _view["page"], _view["status"]
    )


def _sync_tag():
    ctx.tags = ["user.links_active"] if links_overlay.is_showing() else []


def _on_hide():
    global _view
    _view = None
    ctx.tags = []


links_overlay.set_on_hide(_on_hide)


def _enqueue_view_scan():
    if _view and _view["tab_id"]:
        _runner.enqueue(Job(_view["host"], _view["tab_id"], _view["label"]), front=True)
        _view["enqueued_at"] = time.time()
        _view["status"] = "scanning…"


def _open_view(label: str):
    """Show the links overlay for the tab labelled `label`, from history at
    once, then queue a fresh scan of that tab. Cache-only tab lookup."""
    global _view
    target = herdr_tabs.resolve_any(label)
    host, tab_id = (target[0] or "", target[2]) if target else ("", None)
    rows = links_data.tab_rows(_history, host, tab_id) if tab_id else []
    _view = {
        "label": herdr_tabs.clean_label(label) or label,
        "host": host,
        "tab_id": tab_id,
        "urls": [r["url"] for r in rows],
        "page": 0,
        "status": "" if tab_id else "tab not found in Herdr",
        "enqueued_at": 0.0,
    }
    _enqueue_view_scan()
    _render()
    links_overlay.show()
    _sync_tag()


def _url_at(n: int):
    if _view and 0 <= n < len(_view["urls"]):
        return _view["urls"][n]
    return None


# ── Background capture ──


def _capture_jobs():
    """One Job per voice-named tab on local + HOSTS, from the herdr_tabs
    cache (no subprocess)."""
    merged = herdr_tabs.merge_tabs()
    names = herdr_tabs.voice_labels(merged)
    jobs = []
    for host, tab in merged:
        label = herdr_tabs.clean_label(tab.get("label"))
        if label.lower() in names and tab.get("tab_id"):
            jobs.append(Job(host, tab["tab_id"], label))
    return jobs


def _handle(result):
    global _history
    key = result.job.key
    if result.error:
        _errors[key] = result.error
        print(f"[herdr_links] scan {key}: {result.error}")
    else:
        fresh = links_data.records_from_scan(
            result.data, result.job.host, result.job.label, time.time()
        )
        _history = links_data.merge(_history, fresh)
        _live[key] = {r["url"] for r in fresh}
        _errors.pop(key, None)
        try:
            links_data.save(_history)
        except OSError as e:
            print(f"[herdr_links] history save failed: {e}")
    if _view_key() == key:
        rows = links_data.tab_rows(_history, _view["host"], _view["tab_id"])
        _view["urls"] = links_data.extend_frozen(_view["urls"], rows)
        _view["status"] = (
            f"scan failed: {result.error}" if result.error else "updated just now"
        )
        _render()


def _tick():
    """Cron (1s): poll the scan runner, schedule captures. Never blocks."""
    global _last_capture
    try:
        for result in _runner.tick():
            _handle(result)
        now = time.time()
        interval = settings.get("user.links_capture_interval")
        if (
            interval
            and interval > 0
            and now - _loaded_at >= FIRST_CAPTURE_DELAY
            and now - _last_capture >= interval
        ):
            _last_capture = now
            for job in _capture_jobs():
                _runner.enqueue(job)
        if _view and now - _view["enqueued_at"] >= VIEW_RESCAN_SECONDS:
            if not _runner.pending(_view_key() or ("", "")):
                _enqueue_view_scan()
                _render()
    except Exception as e:
        print(f"[herdr_links] tick failed: {e}")


cron.interval("1s", _tick)


# ── Actions ──


@mod.action_class
class Actions:
    def links_show_tab(label: str):
        """Switch Herdr to the tab named `label` (the recall switch), then show its links"""
        actions.user.herdr_tab_focus(label)
        _open_view(label)

    def links_hide():
        """Hide the links overlay"""
        links_overlay.hide()
        _on_hide()

    def links_open(n: int):
        """Open link n (0-based index from overlay_select) of the open view"""
        url = _url_at(n)
        if not url:
            return
        env = scan_env()
        opener = find_tool("interceptor", env)
        argv = [opener, "open", url] if os.path.isabs(opener) else ["open", url]
        try:
            subprocess.Popen(
                argv,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"[herdr_links] open failed: {e}")
            return
        actions.user.links_hide()

    def links_copy(n: int):
        """Copy link n (0-based index from overlay_select) of the open view"""
        url = _url_at(n)
        if not url:
            return
        clip.set_text(url)
        _view["status"] = f"copied {n + 1}"
        _render()

    def links_next():
        """Next page of the links overlay"""
        if _view:
            last = links_data.page_count(len(_view["urls"])) - 1
            _view["page"] = min(_view["page"] + 1, last)
            _render()

    def links_previous():
        """Previous page of the links overlay"""
        if _view:
            _view["page"] = max(_view["page"] - 1, 0)
            _render()

    def links_refresh():
        """Rescan the open tab now"""
        _enqueue_view_scan()
        _render()
