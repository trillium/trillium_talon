# Reconciliation: trillium-mini <-> macbookpro.lan

Snapshots: trillium-mini at 2026-02-26T05:25:39.219800+00:00, macbookpro.lan at 2026-02-26T05:43:38.602712+00:00

## Missing Directories

### `parrot.py` — exists on **trillium-mini** only
- Type: git repo (plain clone), branch `master`
- Origin: `https://github.com/trillium/parrot.py.git`
- **Action on macbookpro.lan:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/trillium/parrot.py.git parrot.py
  ```

### `talon_backup_repo_user` — exists on **trillium-mini** only
- Type: plain directory (1 files)
- **Action:** Copy from trillium-mini to macbookpro.lan via scp/rsync

### `talon_mcp` — exists on **trillium-mini** only
- Type: git repo (plain clone), branch `main`
- Origin: `https://github.com/trillium/talon_mcp.git`
- **Action on macbookpro.lan:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/trillium/talon_mcp.git talon_mcp
  ```

### `Mouse Control Chicken Data` — exists on **macbookpro.lan** only
- Type: plain directory (3 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `MouseControlChicken` — exists on **macbookpro.lan** only
- **Status: CLEAR TO REMOVE** — no longer in use
- **Action on macbookpro.lan:** `rm -rf ~/.talon/user/MouseControlChicken`

### `__talon_community` — exists on **macbookpro.lan** only
- Type: plain directory (1 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `docs` — exists on **macbookpro.lan** only
- Type: plain directory (0 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `flex-mouse-grid` — exists on **macbookpro.lan** only
- Type: git repo (plain clone), branch `master`
- Origin: `https://github.com/brollin/flex-mouse-grid`
- **Action on trillium-mini:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/brollin/flex-mouse-grid flex-mouse-grid
  ```

### `most_recent_command_playback` — exists on **macbookpro.lan** only
- Type: git repo (fork (owned)), branch `main`
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
- Type: git repo (plain clone), branch `main`
- Origin: `https://github.com/phillco/talon-axkit`
- **Action on trillium-mini:**
  ```bash
  cd ~/.talon/user && git clone https://github.com/phillco/talon-axkit talon-axkit
  ```

### `trillium` — exists on **macbookpro.lan** only
- Type: plain directory (374 files)
- **Action:** Copy from macbookpro.lan to trillium-mini via scp/rsync

### `trillium_obs` — exists on **macbookpro.lan** only
- Type: git repo (plain clone), branch `main`
- Origin: `unknown`
- **Action on trillium-mini:**
  ```bash
  cd ~/.talon/user && git clone unknown trillium_obs
  ```

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
- **Action:** Determine which branch is correct and switch the other machine

### `rango-talon`
- trillium-mini: branch `main`
- macbookpro.lan: branch `trillium`
- **Action:** Determine which branch is correct and switch the other machine

### `talon-gaze-ocr`
- trillium-mini: branch `trillium`
- macbookpro.lan: branch `beta`
- **Action:** Determine which branch is correct and switch the other machine

### `trillium_talon`
- trillium-mini: branch `mini`
- macbookpro.lan: branch `macbook`
- **Expected:** These appear to be hostname-specific branches
- **Action:** Verify both branches are pushed to origin. Consider merging shared changes into a common branch (e.g. `main`)

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
**macbookpro.lan** — Untracked:
  - `.scripts/talon_snapshot.py`

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

## Summary of Actions

Review the sections above and execute the suggested commands on each machine.
Recommended order:
1. Commit or stash all uncommitted changes on both machines
2. Push all unpushed branches from both machines
3. Pull/clone missing repos on each machine
4. Reconcile any branch divergence (merge shared changes)
5. Manually compare non-git config file differences
