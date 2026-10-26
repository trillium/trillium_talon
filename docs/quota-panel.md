# Quota panel

One status cell per AI subscription, right of the mode-indicator bar:
`CC` Claude Code, `OC` OpenCode Go, `GPT` ChatGPT Plus (quota-axi provider
`codex`), `GRK` Grok, `AGY` Antigravity. Each cell shows percent left, time to
the limiting window's reset, and a headroom bar. Code: `trillium/quota_panel/`.

It replaces the Claude-only usage text in the bar. That text came from
`trillium/plugin/mode_indicator/poll_usage.py`, which reads the Keychain item
`Claude Code-credentials` and broke when the item lost its `claudeAiOauth` key.

## How it works

- `quota_run.QuotaRunner` starts `quota-axi --json --provider <list> --max-age 60s`
  as a child process (stdout to a temp file); a 1s cron tick only polls it and
  kills it after 25s. No thread, nothing waits on quota-axi. Same shape as
  `herdr_links`.
- `quota_data` turns the JSON into cells. Headline per provider is
  `quotaSemantics.effectiveAvailability`: the `all_models`/`all_products`
  scope, else the lowest scope. A red dot means another scope (e.g. Claude's
  Fable week) is at 0.
- Redraw on every result and every 30s (countdowns).

## Colors (percent left)

| Left | Color |
|---|---|
| >= 50 | green |
| 25-49 | yellow |
| 10-24 | orange |
| < 10 | red (0 also tints the cell red) |
| no reading | gray with `login` / `setup` / `n/a` |

Runway bumps: `projected_exhaustion` is at least orange, `exhausted_now` red.

## Failure display

- A read fails or times out: last cells stay, dimmed, sub-line prefixed `!`.
- No success for 3 intervals: sub-line `stale 7m`.
- No success yet: every cell `—` with `…` (waiting) or `err`.
- ChatGPT Plus `login`: the Codex token expired. Run `codex login`.

## Settings

`user.quota_panel_show` (on in `trillium/mode_indicator/mode_indicator.talon`),
`quota_panel_interval` (120s, min 30), `quota_panel_providers`,
`quota_panel_cell_w` (66px), `quota_panel_left_x` (0 = auto, right of the bar).
`user.mode_indicator_show_usage = false` hides the old usage text. Voice:
`quota refresh`.

The panel sits in the menu-bar strip and can cover third-party menu extras:
raise `quota_panel_left_x` or lower `quota_panel_cell_w`.
