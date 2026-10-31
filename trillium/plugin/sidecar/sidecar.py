"""Voice control of Sidecar panes: next / previous / up / down / top / bottom,
show-by-name, pane aliases, and list modals (panes, views, controls, requests).

All CLI work goes through sidecar_cli (background thread, errors logged)."""

from talon import Context, Module, actions, cron

from . import sidecar_cli as cli
from . import sidecar_list_overlay as overlay

mod = Module()
mod.tag("sidecar_list_active", desc="A Sidecar list modal is open")
mod.list("sidecar_pane", desc="Spoken Sidecar pane aliases -> pane ids")
mod.list("sidecar_view", desc="Spoken Sidecar view names -> file or URL")

ctx = Context()

# Spoken alias -> pane id. Aliases must not collide with verbs (task-qggqy).
PANES = {"main": "dev-f5cf8b", "chrome": "dev-c49599"}
# Spoken view name -> file or allow-listed URL; add entries here.
VIEWS: dict[str, str] = {}
ctx.lists["user.sidecar_pane"] = PANES
ctx.lists["user.sidecar_view"] = VIEWS

_pane = cli.DEFAULT_PANE
_kind = ""
_rows: list[dict] = []


def _pane_name(pane_id: str) -> str:
    for alias, pid in PANES.items():
        if pid == pane_id:
            return f"{alias.capitalize()} pane"
    return pane_id


def _open_list(kind: str, title: str, rows: list[dict]):
    global _kind, _rows
    _kind, _rows = kind, rows
    ctx.tags = ["user.sidecar_list_active"]
    overlay.show(
        f"{title} · {_pane_name(_pane)}", rows, cli.footer_text(kind, len(rows))
    )


def _close_list():
    global _kind, _rows
    _kind, _rows = "", []
    ctx.tags = []
    overlay.hide()


@mod.action_class
class Actions:
    def sidecar_verb(verb: str):
        """Run a navigation verb (next, previous, up, down, top, bottom) on the current pane"""
        argv = cli.verb_argv(verb, _pane)
        if argv:
            cli.run(argv)

    def sidecar_set_pane(pane_id: str):
        """Make a Sidecar pane id the default target"""
        global _pane
        _pane = pane_id

    def sidecar_get_pane() -> str:
        """The current default Sidecar pane id"""
        return _pane

    def sidecar_show(target: str):
        """Show a file, URL or directory on the current pane"""
        cli.run(cli.show_argv(target, _pane))

    def sidecar_back():
        """Restore what the current pane showed before the last show"""
        cli.run(cli.back_argv(_pane))

    def sidecar_list(kind: str):
        """Open a modal listing panes, controls or requests"""
        argv = cli.list_argv(kind, _pane)
        if not argv:
            return

        def done(code: int, out: str):
            rows = cli.parse_rows(kind, out) if code == 0 else []
            if kind == "panes":
                rows = cli.decorate_panes(rows, PANES, _pane)
            cron.after("0ms", lambda: _open_list(kind, f"Sidecar {kind}", rows))

        cli.run(argv, done)

    def sidecar_list_views():
        """Open a modal listing the spoken view names"""
        rows = [{"id": v, "name": n, "detail": v} for n, v in sorted(VIEWS.items())]
        _open_list("views", "Sidecar views", rows)

    def sidecar_help():
        """Open a modal listing every Sidecar voice command"""
        _open_list("help", "Sidecar help", cli.help_rows())

    def sidecar_pick(index: int):
        """Act on a row of the open Sidecar list modal (0-based)"""
        if not 0 <= index < len(_rows):
            return
        row, kind = _rows[index], _kind
        if kind == "help":
            return
        _close_list()
        if kind == "panes":
            actions.user.sidecar_set_pane(row["id"])
        elif kind == "views":
            actions.user.sidecar_show(row["id"])
        elif kind == "controls":
            cli.run(cli.build_argv(["invoke", "{pane}", row["id"]], _pane))
        elif kind == "requests":
            cli.run(cli.build_argv(["requests", "show", row["id"]], _pane))

    def sidecar_close():
        """Close the Sidecar list modal"""
        _close_list()
