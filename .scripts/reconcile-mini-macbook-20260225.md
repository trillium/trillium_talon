# Reconciliation: trillium-mini <-> macbookpro.lan

Snapshots: trillium-mini at 2026-02-26T05:25:39.219800+00:00, macbookpro.lan at 2026-02-26T05:50:33.467681+00:00

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
  - `.scripts/talon_snapshot.py`
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

## Filename Collisions (Consolidation Candidates)

These filenames appear in multiple repos/directories on the same machine.
Each copy has been written to `.scripts/collisions/` with a sanitized path name.
**Action:** Pick a canonical location and naming convention, remove duplicates.

### `__init__.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/vendor/__init__.py` → `collisions/cursorless-talon--src--vendor--__init__.py`
  - `most_recent_command_playback/__init__.py` → `collisions/most_recent_command_playback--__init__.py`
  - `most_recent_command_playback/utils/__init__.py` → `collisions/most_recent_command_playback--utils--__init__.py`
  - `trillium/friction/__init__.py` → `collisions/trillium--friction--__init__.py`
  - `trillium/ticket/__init__.py` → `collisions/trillium--ticket--__init__.py`
  - `trillium/mouse-clock/src/__init__.py` → `collisions/trillium--mouse-clock--src--__init__.py`
  - `trillium/mouse-clock/src/core/__init__.py` → `collisions/trillium--mouse-clock--src--core--__init__.py`
  - `trillium/mouse-clock/src/core/geometry/__init__.py` → `collisions/trillium--mouse-clock--src--core--geometry--__init__.py`
  - `trillium/mouse-clock/src/util/__init__.py` → `collisions/trillium--mouse-clock--src--util--__init__.py`
  - `trillium/mouse-clock/src/input/__init__.py` → `collisions/trillium--mouse-clock--src--input--__init__.py`
  - `trillium/mouse-clock/src/features/__init__.py` → `collisions/trillium--mouse-clock--src--features--__init__.py`
  - `trillium/mouse-clock/src/features/shared/__init__.py` → `collisions/trillium--mouse-clock--src--features--shared--__init__.py`
  - `trillium/mouse-clock/src/features/clock_letters/__init__.py` → `collisions/trillium--mouse-clock--src--features--clock_letters--__init__.py`
  - `trillium/mouse-clock/src/talon_integration/__init__.py` → `collisions/trillium--mouse-clock--src--talon_integration--__init__.py`
  - `trillium/mouse-clock/src/rendering/__init__.py` → `collisions/trillium--mouse-clock--src--rendering--__init__.py`
  - `trillium/mouse-clock/src/rendering/drawing/__init__.py` → `collisions/trillium--mouse-clock--src--rendering--drawing--__init__.py`
  - `trillium/mouse-clock/src/rendering/canvas/__init__.py` → `collisions/trillium--mouse-clock--src--rendering--canvas--__init__.py`
  - `trillium_talon/test/stubs/talon/__init__.py` → `collisions/trillium_talon--test--stubs--talon--__init__.py`
  - `trillium_talon/trillium/friction/__init__.py` → `collisions/trillium_talon--trillium--friction--__init__.py`
  - `trillium_talon/trillium/ticket/__init__.py` → `collisions/trillium_talon--trillium--ticket--__init__.py`

### `_wav.py`
**macbookpro.lan** (all copies identical):
  - `trillium/utils/_wav.py` → `collisions/trillium--utils--_wav.py`
  - `trillium_talon/trillium/utils/_wav.py` → `collisions/trillium_talon--trillium--utils--_wav.py`

### `abort.py`
**macbookpro.lan** (all copies identical):
  - `trillium/core/on_phrase/abort/abort.py` → `collisions/trillium--core--on_phrase--abort--abort.py`
  - `trillium_talon/trillium/core/on_phrase/abort/abort.py` → `collisions/trillium_talon--trillium--core--on_phrase--abort--abort.py`

### `actions.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/actions/actions.py` → `collisions/cursorless-talon--src--actions--actions.py`
  - `cursorless-talon/src/cheatsheet/sections/actions.py` → `collisions/cursorless-talon--src--cheatsheet--sections--actions.py`
  - `trillium/mouse-clock/src/talon_integration/actions.py` → `collisions/trillium--mouse-clock--src--talon_integration--actions.py`

### `agent.py`
**macbookpro.lan** (all copies identical):
  - `trillium/ticket/agent.py` → `collisions/trillium--ticket--agent.py`
  - `trillium_talon/trillium/ticket/agent.py` → `collisions/trillium_talon--trillium--ticket--agent.py`

### `animation.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mouse-clock/src/core/animation.py` → `collisions/trillium--mouse-clock--src--core--animation.py`
  - `trillium/mouse-clock/src/rendering/animation.py` → `collisions/trillium--mouse-clock--src--rendering--animation.py`

### `anki_tools.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/anki_tools.talon` → `collisions/trillium--anki_tools.talon`
  - `trillium_talon/trillium/anki_tools.talon` → `collisions/trillium_talon--trillium--anki_tools.talon`

### `app_switcher.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_obs/window_management/app_switcher.py` → `collisions/trillium_obs--window_management--app_switcher.py`
  - `trillium_talon/core/app_switcher/app_switcher.py` → `collisions/trillium_talon--core--app_switcher--app_switcher.py`

### `bingo.py`
**macbookpro.lan** (all copies identical):
  - `trillium/hex_grid/bingo.py` → `collisions/trillium--hex_grid--bingo.py`
  - `trillium_talon/trillium/hex_grid/bingo.py` → `collisions/trillium_talon--trillium--hex_grid--bingo.py`

### `bingo.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/hex_grid/bingo.talon` → `collisions/trillium--hex_grid--bingo.talon`
  - `trillium_talon/trillium/hex_grid/bingo.talon` → `collisions/trillium_talon--trillium--hex_grid--bingo.talon`

### `boolean_print.py`
**macbookpro.lan** (all copies identical):
  - `trillium/boolean_print/boolean_print.py` → `collisions/trillium--boolean_print--boolean_print.py`
  - `trillium_talon/trillium/_boolean_print/boolean_print.py` → `collisions/trillium_talon--trillium--_boolean_print--boolean_print.py`

### `brightness.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/brightness.talon` → `collisions/trillium--brightness.talon`
  - `trillium_talon/trillium/brightness.talon` → `collisions/trillium_talon--trillium--brightness.talon`

### `brightness_w_app_vscode.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/brightness_w_app_vscode.talon` → `collisions/trillium--brightness_w_app_vscode.talon`
  - `trillium_talon/trillium/brightness_w_app_vscode.talon` → `collisions/trillium_talon--trillium--brightness_w_app_vscode.talon`

### `cancel_in_flight_phrase.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/cancel_in_flight_phrase.py` → `collisions/trillium--cancel_in_flight_phrase.py`
  - `trillium_talon/core/cancel_in_flight_phrase.py` → `collisions/trillium_talon--core--cancel_in_flight_phrase.py`

### `centroid_mouse.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mouse_grid_centroid/centroid_mouse.talon` → `collisions/trillium--mouse_grid_centroid--centroid_mouse.talon`
  - `trillium_talon/trillium/mouse_grid_centroid/centroid_mouse.talon` → `collisions/trillium_talon--trillium--mouse_grid_centroid--centroid_mouse.talon`

### `centroid_mouse_grid.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mouse_grid_centroid/centroid_mouse_grid.py` → `collisions/trillium--mouse_grid_centroid--centroid_mouse_grid.py`
  - `trillium_talon/trillium/mouse_grid_centroid/centroid_mouse_grid.py` → `collisions/trillium_talon--trillium--mouse_grid_centroid--centroid_mouse_grid.py`

### `centroid_mouse_grid_always.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/mouse_grid_centroid/centroid_mouse_grid_always.talon` → `collisions/trillium--mouse_grid_centroid--centroid_mouse_grid_always.talon`
  - `trillium_talon/trillium/mouse_grid_centroid/centroid_mouse_grid_always.talon` → `collisions/trillium_talon--trillium--mouse_grid_centroid--centroid_mouse_grid_always.talon`

### `centroid_mouse_grid_open.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/mouse_grid_centroid/centroid_mouse_grid_open.talon` → `collisions/trillium--mouse_grid_centroid--centroid_mouse_grid_open.talon`
  - `trillium_talon/trillium/mouse_grid_centroid/centroid_mouse_grid_open.talon` → `collisions/trillium_talon--trillium--mouse_grid_centroid--centroid_mouse_grid_open.talon`

### `centroid_mouse_grid_settings.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/mouse_grid_centroid/centroid_mouse_grid_settings.talon` → `collisions/trillium--mouse_grid_centroid--centroid_mouse_grid_settings.talon`
  - `trillium_talon/trillium/mouse_grid_centroid/centroid_mouse_grid_settings.talon` → `collisions/trillium_talon--trillium--mouse_grid_centroid--centroid_mouse_grid_settings.talon`

### `change_mic.py`
**macbookpro.lan** (all copies identical):
  - `trillium/microphone/change_mic.py` → `collisions/trillium--microphone--change_mic.py`
  - `trillium_talon/trillium/microphone/change_mic.py` → `collisions/trillium_talon--trillium--microphone--change_mic.py`

### `change_mic.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/microphone/change_mic.talon` → `collisions/trillium--microphone--change_mic.talon`
  - `trillium_talon/trillium/microphone/change_mic.talon` → `collisions/trillium_talon--trillium--microphone--change_mic.talon`

### `check_community_repo.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/check_community_repo.py` → `collisions/cursorless-talon--src--check_community_repo.py`
  - `rango-talon/src/check_community_repo.py` → `collisions/rango-talon--src--check_community_repo.py`

### `chrome.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/chrome.talon` → `collisions/trillium--chrome.talon`
  - `trillium_talon/trillium/chrome.talon` → `collisions/trillium_talon--trillium--chrome.talon`
  - `trillium_talon/apps/chrome/chrome.talon` → `collisions/trillium_talon--apps--chrome--chrome.talon`

### `clear_text_commands.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/clear_text_commands.py` → `collisions/trillium--clear_text_commands.py`
  - `trillium_talon/trillium/clear_text_commands.py` → `collisions/trillium_talon--trillium--clear_text_commands.py`

### `clear_text_commands.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/clear_text_commands.talon` → `collisions/trillium--clear_text_commands.talon`
  - `trillium_talon/trillium/clear_text_commands.talon` → `collisions/trillium_talon--trillium--clear_text_commands.talon`

### `clock.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mouse-clock/src/core/geometry/clock.py` → `collisions/trillium--mouse-clock--src--core--geometry--clock.py`
  - `trillium/mouse-clock/src/rendering/canvas/clock.py` → `collisions/trillium--mouse-clock--src--rendering--canvas--clock.py`

### `code_common_function.talon-list`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/lang/go/code_common_function.talon-list` → `collisions/trillium_talon--lang--go--code_common_function.talon-list`
  - `trillium_talon/lang/python/code_common_function.talon-list` → `collisions/trillium_talon--lang--python--code_common_function.talon-list`
  - `trillium_talon/lang/css/code_common_function.talon-list` → `collisions/trillium_talon--lang--css--code_common_function.talon-list`
  - `trillium_talon/lang/r/code_common_function.talon-list` → `collisions/trillium_talon--lang--r--code_common_function.talon-list`
  - `trillium_talon/lang/lua/code_common_function.talon-list` → `collisions/trillium_talon--lang--lua--code_common_function.talon-list`
  - `trillium_talon/lang/cpp/code_common_function.talon-list` → `collisions/trillium_talon--lang--cpp--code_common_function.talon-list`
  - `trillium_talon/lang/csharp/code_common_function.talon-list` → `collisions/trillium_talon--lang--csharp--code_common_function.talon-list`
  - `trillium_talon/lang/javascript/code_common_function.talon-list` → `collisions/trillium_talon--lang--javascript--code_common_function.talon-list`
  - `trillium_talon/lang/c/code_common_function.talon-list` → `collisions/trillium_talon--lang--c--code_common_function.talon-list`
  - `trillium_talon/lang/stata/code_common_function.talon-list` → `collisions/trillium_talon--lang--stata--code_common_function.talon-list`
  - `trillium_talon/lang/sql/code_common_function.talon-list` → `collisions/trillium_talon--lang--sql--code_common_function.talon-list`

### `code_common_method.talon-list`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/lang/python/code_common_method.talon-list` → `collisions/trillium_talon--lang--python--code_common_method.talon-list`
  - `trillium_talon/lang/java/code_common_method.talon-list` → `collisions/trillium_talon--lang--java--code_common_method.talon-list`

### `code_keyword.talon-list`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/lang/go/code_keyword.talon-list` → `collisions/trillium_talon--lang--go--code_keyword.talon-list`
  - `trillium_talon/lang/python/code_keyword.talon-list` → `collisions/trillium_talon--lang--python--code_keyword.talon-list`
  - `trillium_talon/lang/java/code_keyword.talon-list` → `collisions/trillium_talon--lang--java--code_keyword.talon-list`
  - `trillium_talon/lang/cpp/code_keyword.talon-list` → `collisions/trillium_talon--lang--cpp--code_keyword.talon-list`
  - `trillium_talon/lang/c/code_keyword.talon-list` → `collisions/trillium_talon--lang--c--code_keyword.talon-list`

### `code_keyword_unprefixed.talon-list`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/lang/python/code_keyword_unprefixed.talon-list` → `collisions/trillium_talon--lang--python--code_keyword_unprefixed.talon-list`
  - `trillium_talon/lang/cpp/code_keyword_unprefixed.talon-list` → `collisions/trillium_talon--lang--cpp--code_keyword_unprefixed.talon-list`
  - `trillium_talon/lang/c/code_keyword_unprefixed.talon-list` → `collisions/trillium_talon--lang--c--code_keyword_unprefixed.talon-list`

### `code_type.talon-list`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/lang/go/code_type.talon-list` → `collisions/trillium_talon--lang--go--code_type.talon-list`
  - `trillium_talon/lang/python/code_type.talon-list` → `collisions/trillium_talon--lang--python--code_type.talon-list`

### `command.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/command.py` → `collisions/cursorless-talon--src--command.py`
  - `rango-talon/src/command.py` → `collisions/rango-talon--src--command.py`

### `command_logger.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/plugin/repeater/command_logger.py` → `collisions/trillium--plugin--repeater--command_logger.py`
  - `trillium_talon/trillium/plugin/repeater/command_logger.py` → `collisions/trillium_talon--trillium--plugin--repeater--command_logger.py`

### `confetti.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/confetti.talon` → `collisions/trillium--confetti.talon`
  - `trillium_talon/trillium/confetti.talon` → `collisions/trillium_talon--trillium--confetti.talon`

### `config.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mouse-clock/src/core/config.py` → `collisions/trillium--mouse-clock--src--core--config.py`
  - `trillium/mouse-clock/src/features/clock_letters/config.py` → `collisions/trillium--mouse-clock--src--features--clock_letters--config.py`
  - `trillium_obs/config.py` → `collisions/trillium_obs--config.py`

### `context.py`
**macbookpro.lan** (all copies identical):
  - `trillium/friction/context.py` → `collisions/trillium--friction--context.py`
  - `trillium_talon/trillium/friction/context.py` → `collisions/trillium_talon--trillium--friction--context.py`

### `cursorless_repeater.py`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/repeater/cursorless_repeater.py` → `collisions/trillium--plugin--repeater--cursorless_repeater.py`
  - `trillium_talon/trillium/plugin/repeater/cursorless_repeater.py` → `collisions/trillium_talon--trillium--plugin--repeater--cursorless_repeater.py`

### `cursorless_repeater.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/repeater/cursorless_repeater.talon` → `collisions/trillium--plugin--repeater--cursorless_repeater.talon`
  - `trillium_talon/trillium/plugin/repeater/cursorless_repeater.talon` → `collisions/trillium_talon--trillium--plugin--repeater--cursorless_repeater.talon`

### `datetimeinsert.py`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/datetimeinsert/datetimeinsert.py` → `collisions/trillium--plugin--datetimeinsert--datetimeinsert.py`
  - `trillium_talon/trillium/plugin/datetimeinsert/datetimeinsert.py` → `collisions/trillium_talon--trillium--plugin--datetimeinsert--datetimeinsert.py`

### `debug.py`
**macbookpro.lan** (all copies identical):
  - `trillium/mouse_grid_centroid/debug.py` → `collisions/trillium--mouse_grid_centroid--debug.py`
  - `trillium_talon/trillium/mouse_grid_centroid/debug.py` → `collisions/trillium_talon--trillium--mouse_grid_centroid--debug.py`

### `displayplacer.py`
**macbookpro.lan** (all copies identical):
  - `trillium/displayplacer.py` → `collisions/trillium--displayplacer.py`
  - `trillium_talon/trillium/displayplacer.py` → `collisions/trillium_talon--trillium--displayplacer.py`

### `displayplacer.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/displayplacer.talon` → `collisions/trillium--displayplacer.talon`
  - `trillium_talon/trillium/displayplacer.talon` → `collisions/trillium_talon--trillium--displayplacer.talon`

### `double_tap.py`
**macbookpro.lan** (all copies identical):
  - `trillium/hooks/double_tap.py` → `collisions/trillium--hooks--double_tap.py`
  - `trillium_talon/trillium/hooks/double_tap.py` → `collisions/trillium_talon--trillium--hooks--double_tap.py`

### `double_tap.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/hooks/double_tap.talon` → `collisions/trillium--hooks--double_tap.talon`
  - `trillium_talon/trillium/hooks/double_tap.talon` → `collisions/trillium_talon--trillium--hooks--double_tap.talon`

### `edge.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mouse-clock/src/rendering/canvas/edge.py` → `collisions/trillium--mouse-clock--src--rendering--canvas--edge.py`
  - `trillium_talon/apps/edge/edge.py` → `collisions/trillium_talon--apps--edge--edge.py`

### `edit.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/edit.talon` → `collisions/trillium--edit.talon`
  - `trillium_talon/core/edit/edit.talon` → `collisions/trillium_talon--core--edit--edit.talon`
  - `trillium_talon/trillium/edit.talon` → `collisions/trillium_talon--trillium--edit.talon`

### `emoji.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/emoji/emoji.talon` → `collisions/trillium--emoji--emoji.talon`
  - `trillium_talon/tags/emoji/emoji.talon` → `collisions/trillium_talon--tags--emoji--emoji.talon`
  - `trillium_talon/trillium/emoji/emoji.talon` → `collisions/trillium_talon--trillium--emoji--emoji.talon`

### `excluded_commands_manager.py`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/repeater/excluded_commands_manager.py` → `collisions/trillium--plugin--repeater--excluded_commands_manager.py`
  - `trillium_talon/trillium/plugin/repeater/excluded_commands_manager.py` → `collisions/trillium_talon--trillium--plugin--repeater--excluded_commands_manager.py`

### `friction.py`
**macbookpro.lan** (all copies identical):
  - `trillium/friction/friction.py` → `collisions/trillium--friction--friction.py`
  - `trillium_talon/trillium/friction/friction.py` → `collisions/trillium_talon--trillium--friction--friction.py`

### `friction.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/friction/friction.talon` → `collisions/trillium--friction--friction.talon`
  - `trillium_talon/trillium/friction/friction.talon` → `collisions/trillium_talon--trillium--friction--friction.talon`

### `friction_mode.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/friction/friction_mode.talon` → `collisions/trillium--friction--friction_mode.talon`
  - `trillium_talon/trillium/friction/friction_mode.talon` → `collisions/trillium_talon--trillium--friction--friction_mode.talon`

### `google_docs.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/google_docs.talon` → `collisions/trillium--google_docs.talon`
  - `trillium_talon/trillium/google_docs.talon` → `collisions/trillium_talon--trillium--google_docs.talon`

### `happy_run.py`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/happy_run.py` → `collisions/trillium--happy_run--happy_run.py`
  - `trillium_talon/trillium/happy_run/happy_run.py` → `collisions/trillium_talon--trillium--happy_run--happy_run.py`

### `happy_run.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/happy_run.talon` → `collisions/trillium--happy_run--happy_run.talon`
  - `trillium_talon/trillium/happy_run/happy_run.talon` → `collisions/trillium_talon--trillium--happy_run--happy_run.talon`

### `happy_run_action.py`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/happy_run_action.py` → `collisions/trillium--happy_run--happy_run_action.py`
  - `trillium_talon/trillium/happy_run/happy_run_action.py` → `collisions/trillium_talon--trillium--happy_run--happy_run_action.py`

### `hex_grid.py`
**macbookpro.lan** (all copies identical):
  - `trillium/hex_grid/hex_grid.py` → `collisions/trillium--hex_grid--hex_grid.py`
  - `trillium_talon/trillium/hex_grid/hex_grid.py` → `collisions/trillium_talon--trillium--hex_grid--hex_grid.py`

### `hex_grid.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/hex_grid/hex_grid.talon` → `collisions/trillium--hex_grid--hex_grid.talon`
  - `trillium_talon/trillium/hex_grid/hex_grid.talon` → `collisions/trillium_talon--trillium--hex_grid--hex_grid.talon`

### `holiday.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/holiday.talon` → `collisions/trillium--holiday.talon`
  - `trillium_talon/trillium/holiday.talon` → `collisions/trillium_talon--trillium--holiday.talon`

### `homophones.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/actions/homophones.py` → `collisions/cursorless-talon--src--actions--homophones.py`
  - `trillium_talon/core/homophones/homophones.py` → `collisions/trillium_talon--core--homophones--homophones.py`

### `info.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/info.talon` → `collisions/trillium--info.talon`
  - `trillium_talon/trillium/info.talon` → `collisions/trillium_talon--trillium--info.talon`

### `insert_timestamp.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/insert_timestamp.talon` → `collisions/trillium--insert_timestamp.talon`
  - `trillium_talon/trillium/insert_timestamp.talon` → `collisions/trillium_talon--trillium--insert_timestamp.talon`

### `keyboard_mode_all.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/keyboard_mode_all.talon` → `collisions/trillium--keyboard_mode_all.talon`
  - `trillium_talon/trillium/keyboard_mode_all.talon` → `collisions/trillium_talon--trillium--keyboard_mode_all.talon`

### `keyboard_mode_command.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/keyboard_mode_command.talon` → `collisions/trillium--keyboard_mode_command.talon`
  - `trillium_talon/trillium/keyboard_mode_command.talon` → `collisions/trillium_talon--trillium--keyboard_mode_command.talon`

### `keyboard_mode_dictation.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/keyboard_mode_dictation.talon` → `collisions/trillium--keyboard_mode_dictation.talon`
  - `trillium_talon/trillium/keyboard_mode_dictation.talon` → `collisions/trillium_talon--trillium--keyboard_mode_dictation.talon`

### `keyboard_mode_sleep.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/keyboard_mode_sleep.talon` → `collisions/trillium--keyboard_mode_sleep.talon`
  - `trillium_talon/trillium/keyboard_mode_sleep.talon` → `collisions/trillium_talon--trillium--keyboard_mode_sleep.talon`

### `keys.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/keys.talon` → `collisions/trillium--keys.talon`
  - `trillium_talon/core/keys/keys.talon` → `collisions/trillium_talon--core--keys--keys.talon`
  - `trillium_talon/trillium/keys.talon` → `collisions/trillium_talon--trillium--keys.talon`

### `launch_timestamp.py`
**macbookpro.lan** (all copies identical):
  - `trillium/core/launch_timestamp.py` → `collisions/trillium--core--launch_timestamp.py`
  - `trillium_talon/trillium/core/launch_timestamp.py` → `collisions/trillium_talon--trillium--core--launch_timestamp.py`

### `launcher.py`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/launcher.py` → `collisions/trillium--happy_run--launcher.py`
  - `trillium_talon/trillium/happy_run/launcher.py` → `collisions/trillium_talon--trillium--happy_run--launcher.py`

### `layout.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mouse-clock/src/features/shared/layout.py` → `collisions/trillium--mouse-clock--src--features--shared--layout.py`
  - `trillium/mouse-clock/src/features/clock_letters/layout.py` → `collisions/trillium--mouse-clock--src--features--clock_letters--layout.py`

### `media.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/media/media.talon` → `collisions/trillium--plugin--media--media.talon`
  - `trillium_talon/trillium/plugin/media/media.talon` → `collisions/trillium_talon--trillium--plugin--media--media.talon`

### `messages.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/messages/messages.talon` → `collisions/trillium--messages--messages.talon`
  - `trillium_talon/trillium/messages/messages.talon` → `collisions/trillium_talon--trillium--messages--messages.talon`

### `microphone_selection.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/microphone_selection/microphone_selection.talon` → `collisions/trillium--plugin--microphone_selection--microphone_selection.talon`
  - `trillium_talon/trillium/plugin/microphone_selection/microphone_selection.talon` → `collisions/trillium_talon--trillium--plugin--microphone_selection--microphone_selection.talon`

### `migrate_parrot_logs.py`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/repeater/migrate_parrot_logs.py` → `collisions/trillium--plugin--repeater--migrate_parrot_logs.py`
  - `trillium_talon/trillium/plugin/repeater/migrate_parrot_logs.py` → `collisions/trillium_talon--trillium--plugin--repeater--migrate_parrot_logs.py`

### `mode_indicator.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mode_indicator/mode_indicator.talon` → `collisions/trillium--mode_indicator--mode_indicator.talon`
  - `trillium_talon/trillium/mode_indicator/mode_indicator.talon` → `collisions/trillium_talon--trillium--mode_indicator--mode_indicator.talon`

### `modes.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/core/modes/modes.py` → `collisions/trillium--core--modes--modes.py`
  - `trillium_talon/core/modes/modes.py` → `collisions/trillium_talon--core--modes--modes.py`
  - `trillium_talon/trillium/core/modes/modes.py` → `collisions/trillium_talon--trillium--core--modes--modes.py`

### `modifier_key.talon-list`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/core/keys/win/modifier_key.talon-list` → `collisions/trillium_talon--core--keys--win--modifier_key.talon-list`
  - `trillium_talon/core/keys/mac/modifier_key.talon-list` → `collisions/trillium_talon--core--keys--mac--modifier_key.talon-list`

### `modifiers.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/modifiers/modifiers.py` → `collisions/cursorless-talon--src--modifiers--modifiers.py`
  - `cursorless-talon/src/cheatsheet/sections/modifiers.py` → `collisions/cursorless-talon--src--cheatsheet--sections--modifiers.py`

### `mouse.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/plugin/mouse/mouse.talon` → `collisions/trillium--plugin--mouse--mouse.talon`
  - `trillium_talon/plugin/mouse/mouse.talon` → `collisions/trillium_talon--plugin--mouse--mouse.talon`

### `notify.py`
**macbookpro.lan** (all copies identical):
  - `trillium/notify/notify.py` → `collisions/trillium--notify--notify.py`
  - `trillium_talon/trillium/notify/notify.py` → `collisions/trillium_talon--trillium--notify--notify.py`

### `obs.py`
**macbookpro.lan** (all copies identical):
  - `trillium/obs.py` → `collisions/trillium--obs.py`
  - `trillium_talon/trillium/obs.py` → `collisions/trillium_talon--trillium--obs.py`

### `obs.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/obs.talon` → `collisions/trillium--obs.talon`
  - `trillium_talon/trillium/obs.talon` → `collisions/trillium_talon--trillium--obs.talon`

### `opposite_mappings.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/plugin/repeater/opposite_mappings.py` → `collisions/trillium--plugin--repeater--opposite_mappings.py`
  - `trillium_talon/trillium/plugin/repeater/opposite_mappings.py` → `collisions/trillium_talon--trillium--plugin--repeater--opposite_mappings.py`

### `ops.py`
**macbookpro.lan** (all copies identical):
  - `trillium/friction/ops.py` → `collisions/trillium--friction--ops.py`
  - `trillium_talon/trillium/friction/ops.py` → `collisions/trillium_talon--trillium--friction--ops.py`

### `parrot.py`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/parrot/parrot.py` → `collisions/trillium--plugin--parrot--parrot.py`
  - `trillium_talon/trillium/plugin/parrot/parrot.py` → `collisions/trillium_talon--trillium--plugin--parrot--parrot.py`

### `parrot.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/parrot/parrot.talon` → `collisions/trillium--plugin--parrot--parrot.talon`
  - `trillium_talon/trillium/plugin/parrot/parrot.talon` → `collisions/trillium_talon--trillium--plugin--parrot--parrot.talon`

### `parrot_always.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/parrot/parrot_always.talon` → `collisions/trillium--plugin--parrot--parrot_always.talon`
  - `trillium_talon/trillium/plugin/parrot/parrot_always.talon` → `collisions/trillium_talon--trillium--plugin--parrot--parrot_always.talon`

### `parrot_integration.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/plugin/parrot/parrot_integration.py` → `collisions/trillium--plugin--parrot--parrot_integration.py`
  - `trillium_talon/trillium/plugin/parrot/parrot_integration.py` → `collisions/trillium_talon--trillium--plugin--parrot--parrot_integration.py`

### `parrot_logger.py`
**macbookpro.lan** (all copies identical):
  - `trillium/plugin/repeater/parrot_logger.py` → `collisions/trillium--plugin--repeater--parrot_logger.py`
  - `trillium_talon/trillium/plugin/repeater/parrot_logger.py` → `collisions/trillium_talon--trillium--plugin--repeater--parrot_logger.py`

### `pomodoro.py`
**macbookpro.lan** (all copies identical):
  - `trillium/pomodoro/pomodoro.py` → `collisions/trillium--pomodoro--pomodoro.py`
  - `trillium_talon/trillium/pomodoro/pomodoro.py` → `collisions/trillium_talon--trillium--pomodoro--pomodoro.py`

### `pomodoro.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/pomodoro/pomodoro.talon` → `collisions/trillium--pomodoro--pomodoro.talon`
  - `trillium_talon/trillium/pomodoro/pomodoro.talon` → `collisions/trillium_talon--trillium--pomodoro--pomodoro.talon`

### `presentation.py`
**macbookpro.lan** (all copies identical):
  - `trillium/presentation_files/presentation.py` → `collisions/trillium--presentation_files--presentation.py`
  - `trillium_talon/trillium/presentation_files/presentation.py` → `collisions/trillium_talon--trillium--presentation_files--presentation.py`

### `presentation_files.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/presentation_files/presentation_files.talon` → `collisions/trillium--presentation_files--presentation_files.talon`
  - `trillium_talon/trillium/presentation_files/presentation_files.talon` → `collisions/trillium_talon--trillium--presentation_files--presentation_files.talon`

### `presentation_files_not_beta.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/presentation_files/presentation_files_not_beta.talon` → `collisions/trillium--presentation_files--presentation_files_not_beta.talon`
  - `trillium_talon/trillium/presentation_files/presentation_files_not_beta.talon` → `collisions/trillium_talon--trillium--presentation_files--presentation_files_not_beta.talon`

### `qt.py`
**macbookpro.lan** (all copies identical):
  - `trillium/getHired/qt.py` → `collisions/trillium--getHired--qt.py`
  - `trillium_talon/trillium/getHired/qt.py` → `collisions/trillium_talon--trillium--getHired--qt.py`

### `rapid_delete.py`
**macbookpro.lan** (all copies identical):
  - `trillium/rapid_delete.py` → `collisions/trillium--rapid_delete.py`
  - `trillium_talon/trillium/rapid_delete.py` → `collisions/trillium_talon--trillium--rapid_delete.py`

### `rapid_delete.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/rapid_delete.talon` → `collisions/trillium--rapid_delete.talon`
  - `trillium_talon/trillium/rapid_delete.talon` → `collisions/trillium_talon--trillium--rapid_delete.talon`

### `ray.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/ray.talon` → `collisions/trillium--ray.talon`
  - `trillium_talon/trillium/ray.talon` → `collisions/trillium_talon--trillium--ray.talon`
  - `trillium_talon/apps/raycast/ray.talon` → `collisions/trillium_talon--apps--raycast--ray.talon`

### `readiness_poller.py`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/readiness_poller.py` → `collisions/trillium--happy_run--readiness_poller.py`
  - `trillium_talon/trillium/happy_run/readiness_poller.py` → `collisions/trillium_talon--trillium--happy_run--readiness_poller.py`

### `rename_recordings.py`
**macbookpro.lan** (all copies identical):
  - `trillium/rename_recordings.py` → `collisions/trillium--rename_recordings.py`
  - `trillium_talon/trillium/rename_recordings.py` → `collisions/trillium_talon--trillium--rename_recordings.py`

### `repeater.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/plugin/repeater/repeater.py` → `collisions/trillium--plugin--repeater--repeater.py`
  - `trillium_talon/trillium/plugin/repeater/repeater.py` → `collisions/trillium_talon--trillium--plugin--repeater--repeater.py`

### `repeater.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/plugin/repeater/repeater.talon` → `collisions/trillium--plugin--repeater--repeater.talon`
  - `trillium_talon/trillium/plugin/repeater/repeater.talon` → `collisions/trillium_talon--trillium--plugin--repeater--repeater.talon`

### `restart_talon.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/restart_talon.py` → `collisions/trillium--restart_talon.py`
  - `trillium_talon/trillium/restart_talon.py` → `collisions/trillium_talon--trillium--restart_talon.py`

### `restart_talon.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/restart_talon.talon` → `collisions/trillium--restart_talon.talon`
  - `trillium_talon/trillium/restart_talon.talon` → `collisions/trillium_talon--trillium--restart_talon.talon`

### `safari.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `rango-talon/src/overrides/safari.py` → `collisions/rango-talon--src--overrides--safari.py`
  - `trillium_talon/apps/safari/safari.py` → `collisions/trillium_talon--apps--safari--safari.py`

### `scopes.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/modifiers/scopes.py` → `collisions/cursorless-talon--src--modifiers--scopes.py`
  - `cursorless-talon/src/cheatsheet/sections/scopes.py` → `collisions/cursorless-talon--src--cheatsheet--sections--scopes.py`

### `screenshot.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/screenshot.talon` → `collisions/trillium--screenshot.talon`
  - `trillium/plugin/screenshot/screenshot.talon` → `collisions/trillium--plugin--screenshot--screenshot.talon`
  - `trillium_talon/trillium/screenshot.talon` → `collisions/trillium_talon--trillium--screenshot.talon`
  - `trillium_talon/trillium/plugin/screenshot/screenshot.talon` → `collisions/trillium_talon--trillium--plugin--screenshot--screenshot.talon`

### `settings.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `Mouse Control Chicken Data/settings.talon` → `collisions/Mouse Control Chicken Data--settings.talon`
  - `trillium/settings.talon` → `collisions/trillium--settings.talon`
  - `trillium_talon/settings.talon` → `collisions/trillium_talon--settings.talon`
  - `trillium_talon/trillium/settings.talon` → `collisions/trillium_talon--trillium--settings.talon`

### `slack.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/slack.talon` → `collisions/trillium--slack.talon`
  - `trillium_talon/trillium/slack.talon` → `collisions/trillium_talon--trillium--slack.talon`
  - `trillium_talon/apps/slack/slack.talon` → `collisions/trillium_talon--apps--slack--slack.talon`

### `slash_command.talon-list`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/trillium/plugin/slash_commands/slash_command.talon-list` → `collisions/trillium_talon--trillium--plugin--slash_commands--slash_command.talon-list`
  - `trillium_talon_deck/slash_command.talon-list` → `collisions/trillium_talon_deck--slash_command.talon-list`

### `slash_commands.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/trillium/plugin/slash_commands/slash_commands.py` → `collisions/trillium_talon--trillium--plugin--slash_commands--slash_commands.py`
  - `trillium_talon_deck/slash_commands.py` → `collisions/trillium_talon_deck--slash_commands.py`

### `slash_commands.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/trillium/plugin/slash_commands/slash_commands.talon` → `collisions/trillium_talon--trillium--plugin--slash_commands--slash_commands.talon`
  - `trillium_talon_deck/slash_commands.talon` → `collisions/trillium_talon_deck--slash_commands.talon`

### `sleep_mode.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/sleep_mode.talon` → `collisions/trillium--sleep_mode.talon`
  - `trillium_talon/core/modes/sleep_mode.talon` → `collisions/trillium_talon--core--modes--sleep_mode.talon`

### `snippet_types.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/snippets/snippet_types.py` → `collisions/cursorless-talon--src--snippets--snippet_types.py`
  - `trillium_talon/core/snippets/snippet_types.py` → `collisions/trillium_talon--core--snippets--snippet_types.py`

### `snippets.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/snippets/snippets.py` → `collisions/cursorless-talon--src--snippets--snippets.py`
  - `trillium_talon/core/snippets/snippets.py` → `collisions/trillium_talon--core--snippets--snippets.py`

### `sound.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/core/sound/sound.py` → `collisions/trillium--core--sound--sound.py`
  - `trillium/utils/sound.py` → `collisions/trillium--utils--sound.py`
  - `trillium_talon/trillium/core/sound/sound.py` → `collisions/trillium_talon--trillium--core--sound--sound.py`
  - `trillium_talon/trillium/utils/sound.py` → `collisions/trillium_talon--trillium--utils--sound.py`

### `speak_aloud.py`
**macbookpro.lan** (all copies identical):
  - `trillium/speak_aloud.py` → `collisions/trillium--speak_aloud.py`
  - `trillium_talon/trillium/speak_aloud.py` → `collisions/trillium_talon--trillium--speak_aloud.py`

### `speak_aloud.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/speak_aloud.talon` → `collisions/trillium--speak_aloud.talon`
  - `trillium_talon/trillium/speak_aloud.talon` → `collisions/trillium_talon--trillium--speak_aloud.talon`

### `special_key.talon-list`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/core/keys/win/special_key.talon-list` → `collisions/trillium_talon--core--keys--win--special_key.talon-list`
  - `trillium_talon/core/keys/mac/special_key.talon-list` → `collisions/trillium_talon--core--keys--mac--special_key.talon-list`

### `startup_status.py`
**macbookpro.lan** (all copies identical):
  - `trillium/core/startup_status.py` → `collisions/trillium--core--startup_status.py`
  - `trillium_talon/trillium/core/startup_status.py` → `collisions/trillium_talon--trillium--core--startup_status.py`

### `stata.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/lang/stata/stata.py` → `collisions/trillium_talon--lang--stata--stata.py`
  - `trillium_talon/apps/stata/stata.py` → `collisions/trillium_talon--apps--stata--stata.py`

### `state.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/friction/state.py` → `collisions/trillium--friction--state.py`
  - `trillium/ticket/state.py` → `collisions/trillium--ticket--state.py`
  - `trillium_talon/trillium/friction/state.py` → `collisions/trillium_talon--trillium--friction--state.py`
  - `trillium_talon/trillium/ticket/state.py` → `collisions/trillium_talon--trillium--ticket--state.py`

### `system_paths-MacBookPro.lan1.talon-list`
**macbookpro.lan** (all copies identical):
  - `trillium/core/system_paths-MacBookPro.lan1.talon-list` → `collisions/trillium--core--system_paths-MacBookPro.lan1.talon-list`
  - `trillium_talon/trillium/core/system_paths-MacBookPro.lan1.talon-list` → `collisions/trillium_talon--trillium--core--system_paths-MacBookPro.lan1.talon-list`

### `tags.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `rango-talon/src/tags.py` → `collisions/rango-talon--src--tags.py`
  - `trillium_talon/core/tags.py` → `collisions/trillium_talon--core--tags.py`

### `talon_debug.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/talon_debug.talon` → `collisions/trillium--talon_debug.talon`
  - `trillium_talon/trillium/talon_debug.talon` → `collisions/trillium_talon--trillium--talon_debug.talon`

### `talon_helpers.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `rango-talon/src/talon_helpers.talon` → `collisions/rango-talon--src--talon_helpers.talon`
  - `talon-axkit/talon_helpers.talon` → `collisions/talon-axkit--talon_helpers.talon`
  - `trillium_talon/plugin/talon_helpers/talon_helpers.talon` → `collisions/trillium_talon--plugin--talon_helpers--talon_helpers.talon`

### `terminal.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/terminal.talon` → `collisions/trillium--terminal.talon`
  - `trillium_talon/tags/terminal/terminal.talon` → `collisions/trillium_talon--tags--terminal--terminal.talon`
  - `trillium_talon/trillium/terminal.talon` → `collisions/trillium_talon--trillium--terminal.talon`

### `terraform.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/lang/terraform/terraform.py` → `collisions/trillium_talon--lang--terraform--terraform.py`
  - `trillium_talon/apps/terraform/terraform.py` → `collisions/trillium_talon--apps--terraform--terraform.py`

### `terraform.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium_talon/lang/terraform/terraform.talon` → `collisions/trillium_talon--lang--terraform--terraform.talon`
  - `trillium_talon/apps/terraform/terraform.talon` → `collisions/trillium_talon--apps--terraform--terraform.talon`

### `test.py`
**macbookpro.lan** (all copies identical):
  - `trillium/test.py` → `collisions/trillium--test.py`
  - `trillium_talon/trillium/test.py` → `collisions/trillium_talon--trillium--test.py`

### `test_boolean_print.py`
**macbookpro.lan** (all copies identical):
  - `trillium/boolean_print/test_boolean_print.py` → `collisions/trillium--boolean_print--test_boolean_print.py`
  - `trillium_talon/trillium/_boolean_print/test_boolean_print.py` → `collisions/trillium_talon--trillium--_boolean_print--test_boolean_print.py`

### `test_mode_all.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/test_mode_all.talon` → `collisions/trillium--test_mode_all.talon`
  - `trillium_talon/trillium/test_mode_all.talon` → `collisions/trillium_talon--trillium--test_mode_all.talon`

### `test_mode_command.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/test_mode_command.talon` → `collisions/trillium--test_mode_command.talon`
  - `trillium_talon/trillium/test_mode_command.talon` → `collisions/trillium_talon--trillium--test_mode_command.talon`

### `test_readiness_poller.py`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/tests/test_readiness_poller.py` → `collisions/trillium--happy_run--tests--test_readiness_poller.py`
  - `trillium_talon/trillium/happy_run/tests/test_readiness_poller.py` → `collisions/trillium_talon--trillium--happy_run--tests--test_readiness_poller.py`

### `test_window_tracker.py`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/tests/test_window_tracker.py` → `collisions/trillium--happy_run--tests--test_window_tracker.py`
  - `trillium_talon/trillium/happy_run/tests/test_window_tracker.py` → `collisions/trillium_talon--trillium--happy_run--tests--test_window_tracker.py`

### `text_injector.py`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/text_injector.py` → `collisions/trillium--happy_run--text_injector.py`
  - `trillium_talon/trillium/happy_run/text_injector.py` → `collisions/trillium_talon--trillium--happy_run--text_injector.py`

### `then.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/then.talon` → `collisions/trillium--then.talon`
  - `trillium_talon/trillium/then.talon` → `collisions/trillium_talon--trillium--then.talon`

### `ticket.py`
**macbookpro.lan** (all copies identical):
  - `trillium/ticket/ticket.py` → `collisions/trillium--ticket--ticket.py`
  - `trillium_talon/trillium/ticket/ticket.py` → `collisions/trillium_talon--trillium--ticket--ticket.py`

### `to_wake_mode.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/to_wake_mode.talon` → `collisions/trillium--to_wake_mode.talon`
  - `trillium_talon/core/modes/to_wake_mode.talon` → `collisions/trillium_talon--core--modes--to_wake_mode.talon`
  - `trillium_talon/trillium/to_wake_mode.talon` → `collisions/trillium_talon--trillium--to_wake_mode.talon`

### `utils.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/mouse-clock/src/features/shared/utils.py` → `collisions/trillium--mouse-clock--src--features--shared--utils.py`
  - `trillium/mouse-clock/src/rendering/canvas/utils.py` → `collisions/trillium--mouse-clock--src--rendering--canvas--utils.py`

### `versions.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `cursorless-talon/src/versions.py` → `collisions/cursorless-talon--src--versions.py`
  - `rango-talon/src/versions.py` → `collisions/rango-talon--src--versions.py`

### `virtual_coffee_demo.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/virtual_coffee_demo.talon` → `collisions/trillium--virtual_coffee_demo.talon`
  - `trillium_talon/trillium/virtual_coffee_demo.talon` → `collisions/trillium_talon--trillium--virtual_coffee_demo.talon`

### `vscode.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/vscode.talon` → `collisions/trillium--vscode.talon`
  - `trillium_talon/trillium/vscode.talon` → `collisions/trillium_talon--trillium--vscode.talon`
  - `trillium_talon/apps/vscode/vscode.talon` → `collisions/trillium_talon--apps--vscode--vscode.talon`

### `vscode_bar_copilot.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/vscode_bar_copilot.talon` → `collisions/trillium--vscode_bar_copilot.talon`
  - `trillium_talon/trillium/vscode_bar_copilot.talon` → `collisions/trillium_talon--trillium--vscode_bar_copilot.talon`

### `vscode_chat.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/apps/vscode/vscode_chat.talon` → `collisions/trillium--apps--vscode--vscode_chat.talon`
  - `trillium_talon/trillium/apps/vscode/vscode_chat.talon` → `collisions/trillium_talon--trillium--apps--vscode--vscode_chat.talon`

### `vscode_empty.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/apps/vscode/vscode_empty.talon` → `collisions/trillium--apps--vscode--vscode_empty.talon`
  - `trillium_talon/trillium/apps/vscode/vscode_empty.talon` → `collisions/trillium_talon--trillium--apps--vscode--vscode_empty.talon`

### `vscode_terminal.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/vscode_terminal.talon` → `collisions/trillium--vscode_terminal.talon`
  - `trillium_talon/trillium/vscode_terminal.talon` → `collisions/trillium_talon--trillium--vscode_terminal.talon`
  - `trillium_talon/apps/vscode/vscode_terminal.talon` → `collisions/trillium_talon--apps--vscode--vscode_terminal.talon`

### `webflow.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/webflow.talon` → `collisions/trillium--webflow.talon`
  - `trillium_talon/trillium/webflow.talon` → `collisions/trillium_talon--trillium--webflow.talon`

### `wifi.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/os_controls/wifi.talon` → `collisions/trillium--os_controls--wifi.talon`
  - `trillium_talon/trillium/os_controls/wifi.talon` → `collisions/trillium_talon--trillium--os_controls--wifi.talon`

### `window_focus_announcer.py`
**macbookpro.lan** (all copies identical):
  - `trillium/window_focus_announcer.py` → `collisions/trillium--window_focus_announcer.py`
  - `trillium_talon/trillium/window_focus_announcer.py` → `collisions/trillium_talon--trillium--window_focus_announcer.py`

### `window_history.py`
**macbookpro.lan** (all copies identical):
  - `trillium/window_history/window_history.py` → `collisions/trillium--window_history--window_history.py`
  - `trillium_talon/trillium/window_history/window_history.py` → `collisions/trillium_talon--trillium--window_history--window_history.py`

### `window_management.talon`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/window_management.talon` → `collisions/trillium--window_management.talon`
  - `trillium_talon/core/windows_and_tabs/window_management.talon` → `collisions/trillium_talon--core--windows_and_tabs--window_management.talon`

### `window_tracker.py`
**macbookpro.lan** (all copies identical):
  - `trillium/happy_run/window_tracker.py` → `collisions/trillium--happy_run--window_tracker.py`
  - `trillium_talon/trillium/happy_run/window_tracker.py` → `collisions/trillium_talon--trillium--happy_run--window_tracker.py`

### `window_utils.py`
**macbookpro.lan** (all copies identical):
  - `trillium/core/app_switcher/window_utils.py` → `collisions/trillium--core--app_switcher--window_utils.py`
  - `trillium_talon/trillium/core/app_switcher/window_utils.py` → `collisions/trillium_talon--trillium--core--app_switcher--window_utils.py`

### `workspace.py`
**macbookpro.lan** (all copies identical):
  - `trillium/workspace/workspace.py` → `collisions/trillium--workspace--workspace.py`
  - `trillium_talon/trillium/workspace/workspace.py` → `collisions/trillium_talon--trillium--workspace--workspace.py`

### `workspace.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/workspace/workspace.talon` → `collisions/trillium--workspace--workspace.talon`
  - `trillium_talon/trillium/workspace/workspace.talon` → `collisions/trillium_talon--trillium--workspace--workspace.talon`

### `workspace_vscode.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/workspace/workspace_vscode.talon` → `collisions/trillium--workspace--workspace_vscode.talon`
  - `trillium_talon/trillium/workspace/workspace_vscode.talon` → `collisions/trillium_talon--trillium--workspace--workspace_vscode.talon`

### `write_the_clipboard.py`
**macbookpro.lan** (**copies differ — review needed**):
  - `trillium/write_the_clipboard/write_the_clipboard.py` → `collisions/trillium--write_the_clipboard--write_the_clipboard.py`
  - `trillium/mode_indicator/write_the_clipboard.py` → `collisions/trillium--mode_indicator--write_the_clipboard.py`
  - `trillium_talon/trillium/write_the_clipboard/write_the_clipboard.py` → `collisions/trillium_talon--trillium--write_the_clipboard--write_the_clipboard.py`
  - `trillium_talon/trillium/mode_indicator/write_the_clipboard.py` → `collisions/trillium_talon--trillium--mode_indicator--write_the_clipboard.py`

### `write_the_clipboard.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/write_the_clipboard/write_the_clipboard.talon` → `collisions/trillium--write_the_clipboard--write_the_clipboard.talon`
  - `trillium_talon/trillium/write_the_clipboard/write_the_clipboard.talon` → `collisions/trillium_talon--trillium--write_the_clipboard--write_the_clipboard.talon`

### `zoom.py`
**macbookpro.lan** (all copies identical):
  - `trillium/apps/zoom/zoom.py` → `collisions/trillium--apps--zoom--zoom.py`
  - `trillium_talon/trillium/apps/zoom/zoom.py` → `collisions/trillium_talon--trillium--apps--zoom--zoom.py`

### `zoom.talon`
**macbookpro.lan** (all copies identical):
  - `trillium/zoom.talon` → `collisions/trillium--zoom.talon`
  - `trillium_talon/trillium/zoom.talon` → `collisions/trillium_talon--trillium--zoom.talon`

### `zoom_mac.py`
**macbookpro.lan** (all copies identical):
  - `trillium/core/zoom/zoom_mac.py` → `collisions/trillium--core--zoom--zoom_mac.py`
  - `trillium_talon/trillium/core/zoom/zoom_mac.py` → `collisions/trillium_talon--trillium--core--zoom--zoom_mac.py`

---

## Summary of Actions

Review the sections above and execute the suggested commands on each machine.
Recommended order:
1. Commit or stash all uncommitted changes on both machines
2. Push all unpushed branches from both machines
3. Pull/clone missing repos on each machine
4. Reconcile any branch divergence (merge shared changes)
5. Manually compare non-git config file differences
