"""Talon glue for herdr_tabs: the `herdr_tab_names` dynamic list + focus action.

The list is rebuilt from `herdr tab list` on local + herdr_tabs.HOSTS by a cron job. The cron callback is the
only place that runs the subprocess; the voice action resolves from the cache. Saved recall window names/aliases WIN on a clash, so
today's recall behaviour is unchanged.
"""

import socket
import subprocess

from talon import Context, Module, actions, cron, ui

from . import herdr_tabs, recall_state

mod = Module()
ctx = Context()

mod.list("herdr_tab_names", desc="Spoken forms of herdr tab labels")

REFRESH_INTERVAL = "10s"


def _blocked_names():
    names = {n.lower() for n in recall_state.saved_windows}
    for info in recall_state.saved_windows.values():
        names.update(a.lower() for a in info.get("aliases", []))
    return names


def build_name_map(merged, blocked):
    """{label: label} for unique, non-empty, non-blocked, non-fm-* labels
    across all hosts. merged: [(host, tab)]."""
    return {
        label: label
        for key, label in herdr_tabs.voice_labels(merged).items()
        if key not in blocked and not recall_state.is_forbidden(key)
    }


def _apply(merged):
    """merged: [(host, tab)] across local + remote hosts."""
    name_map = build_name_map(merged, _blocked_names())
    if not name_map:
        ctx.lists["self.herdr_tab_names"] = {}
        return
    ctx.lists["self.herdr_tab_names"] = actions.user.create_spoken_forms_from_map(
        name_map, generate_subsequences=False
    )


def refresh_names():
    """Cron tick (every REFRESH_INTERVAL, never on the voice path): one
    `herdr tab list` with a short timeout, then rebuild the list."""
    try:
        _apply(herdr_tabs.refresh_all())
    except Exception as e:
        print(f"[herdr_tab_voice] refresh failed: {e}")


def _viewing_remote():
    """True when the WezTerm/Herdr window title names a machine other than this
    one (the title is "<server hostname>: <workspace>"). Unreadable -> False."""
    try:
        local = socket.gethostname().split(".")[0].lower()
        for w in ui.windows():
            if w.app.name == herdr_tabs.HOST_APP:
                host = w.title.replace("[mosh]", "").split(":")[0].strip().lower()
                return bool(host) and host != local
    except Exception as e:
        print(f"[herdr_tab_voice] view detect failed: {e}")
    return False


@mod.action_class
class Actions:
    def herdr_tab_focus(label: str):
        """Focus the herdr tab with this label and bring WezTerm forward."""
        # The client's selected machine is UI-only state, so a CLI focus on the
        # wrong machine is invisible. Use the Goto picker whenever the target is
        # remote OR the client is currently viewing a remote machine.
        if herdr_tabs.remote_target(label) or _viewing_remote():
            subprocess.run(
                ["open", "-a", herdr_tabs.HOST_APP],
                check=False,
                timeout=herdr_tabs.TIMEOUT,
            )
            actions.sleep("300ms")
            print(f"[herdr_tab_voice] goto picker for {label!r}")
            for kind, value in herdr_tabs.goto_steps(label):
                if kind == "key":
                    actions.key(value)
                else:
                    actions.insert(value)
                actions.sleep("80ms")
            return
        herdr_tabs.focus_any(label)

    def herdr_tab_next():
        """Focus the next tab in the local (MacBook) Herdr, whatever the focused pane is connected to."""
        herdr_tabs.step_local_tab(1)

    def herdr_tab_previous():
        """Focus the previous tab in the local (MacBook) Herdr, whatever the focused pane is connected to."""
        herdr_tabs.step_local_tab(-1)


cron.interval(REFRESH_INTERVAL, refresh_names)
cron.after("2s", refresh_names)
