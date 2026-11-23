"""Linux-only herdr tab recall (X11/Cinnamon, herdr inside WezTerm).

Overrides, for os: linux only, the macOS-flavoured parts of herdr_tab_voice.py:
  * the spoken tab-name list keeps fm-* tabs (they are real tabs the captain uses);
  * user.herdr_tab_focus resolves against a LIVE `herdr tab list` (not a 10 s cache),
    focuses by tab id through herdr's own CLI, then verifies it took, and raises the
    WezTerm window with xdotool instead of macOS `open -a`;
  * it never types a key unless WezTerm is verified to be the active window.
Nothing here is used on macOS: every override sits in an os: linux Context.
"""

import socket
import subprocess

from talon import Context, actions, app, cron, ui

from . import herdr_tab_voice, herdr_tabs, recall_state

ctx = Context()
ctx.matches = "os: linux"

WEZTERM_CLASS = "org.wezfurlong.wezterm"
_LINUX = app.platform == "linux"


def _norm(label):
    return herdr_tabs._norm(label)


def pick_local_tab(tabs, label):
    """Pure: the tab dict to focus for `label` among local tabs, else None.

    Exact cleaned-label match. When several tabs share a label prefer the one in the
    currently focused workspace, then the first in herdr's own order; never guess
    across a different label."""
    want = _norm(label)
    if not want:
        return None
    matches = [
        t for t in tabs or [] if _norm(t.get("label")) == want and t.get("tab_id")
    ]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    focused_ws = next((t.get("workspace_id") for t in tabs if t.get("focused")), None)
    in_ws = [t for t in matches if t.get("workspace_id") == focused_ws]
    return (in_ws or matches)[0]


def _focused_tab_id(tabs):
    return next((t.get("tab_id") for t in tabs or [] if t.get("focused")), None)


def focus_local(label):
    """Focus a local tab by label; True only if herdr reports it focused after."""
    tabs = herdr_tabs.fetch_tabs()
    tab = pick_local_tab(tabs, label)
    if not tab:
        return False
    for attempt in range(2):
        if tab.get("workspace_id"):
            subprocess.run(
                herdr_tabs.herdr_cmd(["workspace", "focus", tab["workspace_id"]]),
                check=False,
                timeout=herdr_tabs.TIMEOUT,
                capture_output=True,
            )
        subprocess.run(
            herdr_tabs.herdr_cmd(["tab", "focus", tab["tab_id"]]),
            check=False,
            timeout=herdr_tabs.TIMEOUT,
            capture_output=True,
        )
        if _focused_tab_id(herdr_tabs.fetch_tabs()) == tab["tab_id"]:
            return True
    print(f"[herdr_tab_voice_linux] focus of {tab['tab_id']} did not take")
    return False


def _wezterm_windows():
    out = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--class", WEZTERM_CLASS],
        capture_output=True,
        text=True,
        timeout=3,
    ).stdout
    return [w for w in out.split() if w.isdigit()]


def raise_wezterm():
    """Bring a WezTerm window forward; True if WezTerm is the active window after."""
    try:
        wins = _wezterm_windows()
        if not wins:
            return False
        subprocess.run(["xdotool", "windowactivate", wins[-1]], check=False, timeout=3)
        actions.sleep("150ms")
        return _wezterm_active()
    except Exception as e:
        print(f"[herdr_tab_voice_linux] raise failed: {e}")
        return False


def _wezterm_active():
    try:
        return (
            WEZTERM_CLASS in (ui.active_app().name or "").lower()
            or "wezterm" in (ui.active_app().name or "").lower()
        )
    except Exception:
        return False


def host_from_title(title, known_hosts, local=None):
    """Pure: which herdr machine a WezTerm title shows. Titles read
    "<server hostname>: <workspace>". Returns None for this machine or when the
    title is unreadable/unknown (treated as local), else the machine label."""
    local = (local or socket.gethostname()).split(".")[0].lower()
    host = (title or "").replace("[mosh]", "").split(":")[0].strip().lower()
    if not host or host == local:
        return None
    for label in known_hosts or []:
        if label.lower() == host:
            return label
    return None


def foreground_host():
    """Machine label of the herdr client in front (None = this laptop's herdr).

    The in-front client is the active WezTerm window, else the topmost visible
    WezTerm window whose title looks like "<host>: <workspace>"."""
    try:
        wins = [w for w in ui.windows() if "wezterm" in (w.app.name or "").lower()]
        active = ui.active_window()
        ordered = [w for w in wins if w == active] + [w for w in wins if w != active]
        for w in ordered:
            if ":" in (w.title or ""):
                return host_from_title(w.title, herdr_tabs.HOSTS)
    except Exception as e:
        print(f"[herdr_tab_voice_linux] foreground host unreadable: {e}")
    return None


def focus_on_host(label, host):
    """Focus `label` on machine `host`'s herdr (the instance in front), verified."""
    tabs = herdr_tabs.fetch_tabs(host)
    tab = pick_local_tab(tabs, label)
    if not tab:
        return False
    for _ in range(2):
        if tab.get("workspace_id"):
            subprocess.run(
                herdr_tabs.herdr_cmd(["workspace", "focus", tab["workspace_id"]], host),
                check=False,
                timeout=herdr_tabs.TIMEOUT,
                capture_output=True,
            )
        subprocess.run(
            herdr_tabs.herdr_cmd(["tab", "focus", tab["tab_id"]], host),
            check=False,
            timeout=herdr_tabs.TIMEOUT,
            capture_output=True,
        )
        if _focused_tab_id(herdr_tabs.fetch_tabs(host)) == tab["tab_id"]:
            return True
    print(f"[herdr_tab_voice_linux] focus of {tab['tab_id']} on {host} did not take")
    return False


def _build_names():
    """Spoken names for the herdr instance in front first (unique within it),
    then every other machine's names that are unique across all machines."""
    merged = herdr_tabs.merge_tabs()  # cache only, no subprocess
    blocked = herdr_tab_voice._blocked_names()
    names = {}
    front = foreground_host()
    front_tabs = [t for h, t in merged if h == front]
    for key, label in herdr_tabs.unique_labels(front_tabs).items():
        names[key] = label
    for key, label in herdr_tabs.unique_labels_all(merged).items():
        names.setdefault(key, label)
    return {
        label: label
        for key, label in names.items()
        if key not in blocked and not recall_state.is_forbidden(key)
    }


def _apply_names():
    try:
        name_map = _build_names()
        ctx.lists["user.herdr_tab_names"] = (
            actions.user.create_spoken_forms_from_map(
                name_map, generate_subsequences=False
            )
            if name_map
            else {}
        )
    except Exception as e:
        print(f"[herdr_tab_voice_linux] list rebuild failed: {e}")


@ctx.action_class("user")
class UserActions:
    def herdr_tab_focus(label: str):
        # Act on the herdr instance in front: the machine the focused WezTerm
        # client is showing. Local when it shows this laptop.
        front = foreground_host()
        if front and focus_on_host(label, front):
            raise_wezterm()
            return
        if not front and focus_local(label):
            raise_wezterm()
            return
        # Not a local tab: a remote one goes through herdr's Goto picker, typed only
        # into a verified-WezTerm window so no stray keys reach another app.
        target = herdr_tabs.resolve_any(label)
        if not target or (not target[0] and not front):
            print(f"[herdr_tab_voice_linux] no unique tab for {label!r}")
            return
        if not raise_wezterm():
            print(
                "[herdr_tab_voice_linux] WezTerm not active; not typing the picker keys"
            )
            return
        prefix = actions.user.herdr_prefix_key_name()
        for kind, value in herdr_tabs.goto_steps(label):
            if not _wezterm_active():
                print("[herdr_tab_voice_linux] lost WezTerm focus; stopping")
                return
            if kind == "key":
                actions.key(prefix if value == herdr_tabs.PREFIX_KEY else value)
            else:
                actions.insert(value)
            actions.sleep("80ms")


if _LINUX:
    cron.interval("3s", _apply_names)
    cron.after("3s", _apply_names)
