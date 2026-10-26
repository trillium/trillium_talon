# Herdr tab voice focus

Say a Herdr tab's label ("mayor", "fixer") to focus that tab and bring WezTerm forward, from any app.

- `plugin/recall/herdr_tabs.py` — pure-Python resolver (cached `herdr tab list`, label -> (workspace_id, tab_id), duplicate/empty labels refused, `ssh <host> herdr ...` variant, never raises). Tests: `.tests/test_herdr_tabs.py`.
- `plugin/recall/herdr_tab_voice.py` — `user.herdr_tab_names` list, rebuilt by a 10s cron; `user.herdr_tab_focus(label)`.
- `plugin/recall/herdr_tab.talon` — `^{user.herdr_tab_names}$`.
- Saved recall window names/aliases and `forbidden_recall_names` are excluded from the list, so saved windows win.

## Follow-ups (files not on this base)

`herdr_focus.py`, `recall_herdr_agents.py`, `recall_herdr_panels.py` and `recall_alias.py` exist only in the live checkout, not on `main`. Repoint them at `herdr_tabs.resolve()` / `herdr_tabs.focus_tab()` / `herdr_tabs.get_tabs(allow_fetch=False)` once they land: herdr agents have no `name` field, so `agent focus <name>` and `agent:<name>` keys never resolve.

## Next / previous tab (local Herdr)

"herdr tab next" / "herdr tab previous" (any app) and plain "tab next" / "tab previous" (in WezTerm) run `herdr tab focus` against this MacBook's Herdr, so they work even when the focused pane is an ssh session into a mini. Order is `herdr tab list` order within the focused workspace (not `number`), wrapping at the ends; no keystrokes, no ssh.

## Remote tabs and the Goto picker

The Herdr client's selected machine is UI-only state, so a remote tab (or any tab while the client is viewing a remote machine) is reached through the Goto picker: `ctrl-b g`, `/`, search text, Enter (`herdr_tabs.goto_steps`, driven by `user.herdr_tab_focus`).

The search text is the tab's **raw label with its emoji** (`herdr_tabs.picker_query`), not the cleaned spoken text. The picker matches machine names, workspace names and terminal rows, and a machine or workspace hit pulls in every terminal under it, so typing `zephyr` matches the machine `mini0-zephyr` and Enter opens that machine's first terminal (`fm-advisor`) instead of the Zephyr tab. Labels with emoji (`💎0️⃣ Zephyr`) match only their own tab's rows. Multi-word queries match only inside a single row/header, so you cannot combine a machine name with a tab name. A plain label with no emoji that is a substring of a machine or workspace name would still collide.

This supersedes the uncommitted copy of these files in the live `~/.talon/user/trillium_talon` checkout.
