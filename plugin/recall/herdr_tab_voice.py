"""Talon glue for herdr_tabs: the `herdr_tab_names` dynamic list + focus action.

The list is rebuilt from `herdr tab list` by a cron job. The cron callback is the
only place that runs the subprocess; the voice action resolves from the cache. Saved recall window names/aliases WIN on a clash, so
today's recall behaviour is unchanged.
"""

from talon import Context, Module, actions, cron

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


def build_name_map(tabs, blocked):
    """{label: label} for unique, non-empty, non-blocked tab labels."""
    return {
        label: label
        for key, label in herdr_tabs.unique_labels(tabs).items()
        if key not in blocked and not recall_state.is_forbidden(key)
    }


def _apply(tabs):
    name_map = build_name_map(tabs, _blocked_names())
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
        _apply(herdr_tabs.refresh())
    except Exception as e:
        print(f"[herdr_tab_voice] refresh failed: {e}")


@mod.action_class
class Actions:
    def herdr_tab_focus(label: str):
        """Focus the herdr tab with this label and bring WezTerm forward."""
        herdr_tabs.focus_tab(label)


cron.interval(REFRESH_INTERVAL, refresh_names)
cron.after("2s", refresh_names)
