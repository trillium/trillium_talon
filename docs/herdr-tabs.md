# Herdr tab voice focus

Say a Herdr tab's label ("mayor", "fixer") to focus that tab and bring WezTerm forward, from any app.

- `plugin/recall/herdr_tabs.py` — pure-Python resolver (cached `herdr tab list`, label -> (workspace_id, tab_id), duplicate/empty labels refused, `ssh <host> herdr ...` variant, never raises). Tests: `.tests/test_herdr_tabs.py`.
- `plugin/recall/herdr_tab_voice.py` — `user.herdr_tab_names` list, rebuilt by a 10s cron; `user.herdr_tab_focus(label)`.
- `plugin/recall/herdr_tab.talon` — `^{user.herdr_tab_names}$`.
- Saved recall window names/aliases and `forbidden_recall_names` are excluded from the list, so saved windows win.

## Follow-ups (files not on this base)

`herdr_focus.py`, `recall_herdr_agents.py`, `recall_herdr_panels.py` and `recall_alias.py` exist only in the live checkout, not on `main`. Repoint them at `herdr_tabs.resolve()` / `herdr_tabs.focus_tab()` / `herdr_tabs.get_tabs(allow_fetch=False)` once they land: herdr agents have no `name` field, so `agent focus <name>` and `agent:<name>` keys never resolve.
