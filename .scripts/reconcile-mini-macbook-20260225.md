# Reconciliation: trillium-mini <-> macbookpro.lan

Snapshots: trillium-mini at 2026-02-26T05:25:39.219800+00:00, macbookpro.lan at 2026-02-26T05:33:00.982671+00:00

## Missing Directories

### `parrot.py` — exists on **trillium-mini** only
- Type: git repo, branch `master`
- Origin: `https://github.com/trillium/parrot.py.git`
- **Action on macbookpro.lan:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/trillium/parrot.py.git parrot.py
  ```

### `talon_backup_repo_user` — exists on **trillium-mini** only
- Type: plain directory (1 files)
- **Action:** Copy from trillium-mini to macbookpro.lan via scp/rsync

### `talon_mcp` — exists on **trillium-mini** only
- Type: git repo, branch `main`
- Origin: `https://github.com/trillium/talon_mcp.git`
- **Action on macbookpro.lan:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/trillium/talon_mcp.git talon_mcp
  ```

### `Mouse Control Chicken Data` — exists on **macbookpro.lan** only
- Type: plain directory (3 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `MouseControlChicken` — exists on **macbookpro.lan** only
- Type: git repo, branch `main` (0 ahead, 42 behind origin)
- Origin: `https://github.com/FireChickenProductivity/MouseControlChicken/`
- **Action on trillium-mini:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/FireChickenProductivity/MouseControlChicken/ MouseControlChicken
  ```

### `__talon_community` — exists on **macbookpro.lan** only
- Type: plain directory (1 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `docs` — exists on **macbookpro.lan** only
- Type: plain directory (0 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `flex-mouse-grid` — exists on **macbookpro.lan** only
- Type: git repo, branch `master` (0 ahead, 10 behind origin)
- Origin: `https://github.com/brollin/flex-mouse-grid`
- Upstream: `https://github.com/tararoys/dense-mouse-grid.git`
- **Action on trillium-mini:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/brollin/flex-mouse-grid flex-mouse-grid
  ```

### `most_recent_command_playback` — exists on **macbookpro.lan** only
- Type: git repo, branch `main` (0 ahead, 0 behind)
- Origin: `https://github.com/trillium/most_recent_command_playback.git`
- **Action on trillium-mini:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/trillium/most_recent_command_playback.git most_recent_command_playback
  ```

### `notes` — exists on **macbookpro.lan** only
- Type: plain directory (0 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `opposite_actions` — exists on **macbookpro.lan** only
- Type: plain directory (0 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `recordings` — exists on **macbookpro.lan** only
- Type: plain directory (8 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `settings` — exists on **macbookpro.lan** only
- Type: plain directory (9 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `talon-axkit` — exists on **macbookpro.lan** only
- Type: git repo, branch `main` (0 ahead, 0 behind)
- Origin: `https://github.com/phillco/talon-axkit`
- **Action on trillium-mini:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/phillco/talon-axkit talon-axkit
  ```

### `trillium` — exists on **macbookpro.lan** only
- Type: plain directory (374 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `trillium_obs` — exists on **macbookpro.lan** only
- Type: git repo, branch `main` (no remote configured)
- **Action on trillium-mini:** Source repo has no remote — obtain from macbookpro.lan directly

### `trillium_talon_deck` — exists on **macbookpro.lan** only
- Type: plain directory (5 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `voice_over` — exists on **macbookpro.lan** only
- Type: plain directory (15 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

## Branch Divergence

### `cursorless-talon`
- trillium-mini: branch `main`
- macbookpro.lan: branch `trillium`
- Remotes (macbook): origin=`https://github.com/trillium/cursorless-talon.git`, upstream=`https://github.com/cursorless-dev/cursorless-talon.git`
- **Action:** macbook is on the `trillium` fork branch — likely correct. Switch mini:
  ```bash
  # on trillium-mini
  cd ~/.talon/user/cursorless-talon
  git fetch origin
  git checkout trillium
  ```

### `rango-talon`
- trillium-mini: branch `main`
- macbookpro.lan: branch `trillium`
- Remotes (macbook): origin=`https://github.com/david-tejada/rango-talon`
- **Action:** macbook is on `trillium` — switch mini to match:
  ```bash
  # on trillium-mini
  cd ~/.talon/user/rango-talon
  git fetch origin
  git checkout trillium
  ```

### `talon-gaze-ocr`
- trillium-mini: branch `trillium`
- macbookpro.lan: branch `beta`
- Remotes (macbook): origin=`https://github.com/trillium/talon-gaze-ocr`, upstream=`https://github.com/wolfmanstout/talon-gaze-ocr/`
- macbook: 2 ahead, 35 behind origin
- **Action:** Determine which branch is correct and switch the other machine

### `trillium_talon`
- trillium-mini: branch `mini`
- macbookpro.lan: branch `macbook`
- Remotes (macbook): origin=`https://github.com/trillium/trillium_talon`, upstream=`https://github.com/knausj85/knausj_talon.git`
- **Expected:** These are hostname-specific branches — this divergence is intentional
- **Action:** Verify both branches are pushed to origin. Merge shared changes into `main` periodically.

## Uncommitted Changes

**These must be resolved before syncing (commit, stash, or discard).**

### `cursorless-talon`
**trillium-mini** — Modified (tracked):
  - `src/actions/generate_snippet.py`
  - `src/actions/wrap.py`
  - `src/cheatsheet/sections/actions.py`
  - `src/cheatsheet/sections/modifiers.py`
  - `src/csv_overrides.py`
  - `src/cursorless.talon`
  - `src/modifiers/modifiers.py`
  - `src/scope_visualizer.py`
  - `src/spoken_forms.json`
  - `src/spoken_forms.py`
**trillium-mini** — Untracked:
  - `src/modifiers/reference.py`
**macbookpro.lan** — Untracked:
  - `src/vendor/__pycache__/`

### `rango-talon`
**trillium-mini** — Modified (tracked):
  - `src/modes/direct_clicking.talon`

### `talon-gaze-ocr`
**macbookpro.lan** — Modified (tracked):
  - `gaze_ocr_talon.py`

### `trillium_talon`
**trillium-mini** — Modified (tracked):
  - `trillium/keys.talon`
**macbookpro.lan** — Modified (tracked):
  - `.beads/config.yaml`
**trillium-mini** — Untracked:
  - `core/system_paths-trillium-mini.talon-list`
  - `trillium/blade_phrases.talon-list`

## Config File Differences (Non-Git Directories)

### `cursorless-settings`
**Only on macbookpro.lan:**
  - `experimental/insertion_snippets.csv`
  - `experimental/insertion_snippets_single_phrase.csv`
  - `experimental/miscellaneous.csv`
  - `experimental/wrapper_snippets.csv`
**Content differs:**
  - `actions.csv` — hash mismatch
  - `hat_styles.csv` — hash mismatch
  - `modifier_scope_types.csv` — hash mismatch
  - `modifiers.csv` — hash mismatch
  - `paired_delimiters.csv` — hash mismatch
- **Action:** Compare and reconcile manually. These are unversioned files.

## Hostname-Specific Files

These files use Talon's `hostname:` context matcher and are **expected to differ** between machines.
They should exist on **both** machines — Talon's hostname matcher ensures only the correct one activates.

- `trillium/core/system_paths-MacBookPro.lan1.talon-list` (hostname: MacBookPro.lan1)
- `trillium_talon/core/modes/modes_laptop.talon` (hostname: laptop)
- `trillium_talon/core/modes/modes_mini.talon` (hostname: trillium-mini)
- `trillium_talon/core/modes/sleep_mode_laptop.talon` (hostname: laptop)
- `trillium_talon/core/modes/sleep_mode_mini.talon` (hostname: trillium-mini)
- `trillium_talon/core/system_paths-MacBookPro.localdomain.talon-list` (hostname: MacBookPro.localdomain)
- `trillium_talon/core/system_paths-laptop.talon-list` (hostname: laptop)
- `trillium_talon/core/system_paths-mac-mini.lan.talon-list` (hostname: mac-mini.lan)
- `trillium_talon/core/system_paths-macbookpro.lan.talon-list` (hostname: macbookpro.lan)
- `trillium_talon/core/system_paths-mini.talon-list` (hostname: mini)
- `trillium_talon/core/system_paths-trillium-mini.talon-list` (hostname: trillium-mini)
- `trillium_talon/core/system_paths-trilliums-MacBook-Pro.talon-list` (hostname: trilliums-MacBook-Pro)
- `trillium_talon/core/system_paths-trilliums-mbp.lan.talon-list` (hostname: trilliums-mbp.lan)
- `trillium_talon/core/system_paths-trilliums-mini.lan.talon-list` (hostname: trilliums-mini.lan)
- `trillium_talon/trillium/core/system_paths-MacBookPro.lan1.talon-list` (hostname: MacBookPro.lan1)
- `trillium_talon/trillium/mode_indicator/mode_indicator-macbookpro.lan.talon` (hostname: macbookpro.lan)

---

## macbookpro.lan Git Repo Reference

Full state of all git repos on macbookpro.lan at snapshot time. Use this to reconcile on trillium-mini.

| Repo | Branch | Ahead | Behind | Remotes |
|------|--------|-------|--------|---------|
| `MouseControlChicken` | `main` | 0 | 42 | origin: https://github.com/FireChickenProductivity/MouseControlChicken/ |
| `cursorless-talon` | `trillium` | — | — | origin: https://github.com/trillium/cursorless-talon.git, upstream: https://github.com/cursorless-dev/cursorless-talon.git |
| `flex-mouse-grid` | `master` | 0 | 10 | origin: https://github.com/brollin/flex-mouse-grid, upstream: https://github.com/tararoys/dense-mouse-grid.git |
| `most_recent_command_playback` | `main` | 0 | 0 | origin: https://github.com/trillium/most_recent_command_playback.git |
| `rango-talon` | `trillium` | — | — | origin: https://github.com/david-tejada/rango-talon |
| `talon-axkit` | `main` | 0 | 0 | origin: https://github.com/phillco/talon-axkit |
| `talon-gaze-ocr` | `beta` | 2 | 35 | origin: https://github.com/trillium/talon-gaze-ocr, upstream: https://github.com/wolfmanstout/talon-gaze-ocr/ |
| `trillium_obs` | `main` | — | — | *(no remote)* |
| `trillium_talon` | `macbook` | — | — | origin: https://github.com/trillium/trillium_talon, upstream: https://github.com/knausj85/knausj_talon.git |

---

## Summary of Actions

Review the sections above and execute the suggested commands on each machine.
Recommended order:
1. Commit or stash all uncommitted changes on both machines
2. Push all unpushed branches from both machines
3. Pull/clone missing repos on each machine
4. Reconcile any branch divergence (merge shared changes)
5. Manually compare non-git config file differences
