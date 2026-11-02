# Editor Overlay — Spec

## What It Does

A floating monospace text editor overlay for Talon Voice. Triggered by `cmd-ctrl-alt-shift-w` to toggle open/close. Useful for drafting text by voice or keyboard without switching to a full application. Built on the `talon-ui-elements` UI kit.

## Architecture

Two files drive the editor:

- **editor.py** — defines the UI tree (`editor_ui`), scroll sync cron, and the `toggle_editor` action
- **editor.talon** — binds `cmd-ctrl-alt-shift-w` to `user.toggle_editor()`

The UI is a horizontal `div` containing:
1. **Line numbers column** — a `div` with per-line `text` elements, clipped at `height=400` with `overflow_y=hidden`. Displays only the lines currently visible in the textarea viewport.
2. **Textarea** — a `talon-ui-elements` `textarea` element with `id="editor"`, Menlo 14pt, `autofocus=True`, `show_hints=False`.

Scroll sync is achieved by a 100ms cron job (`_sync_scroll`) that reads `scroll_offset` from `custom_input_manager` via the `ui_elements_get_input_scroll_offset("editor")` action, converts it to a line index, and updates `scroll_line` state to shift which line numbers are rendered.

## Files

| File | Role |
|------|------|
| `editor.py` | UI definition, scroll sync cron, toggle action |
| `editor.talon` | Keybinding: `cmd-ctrl-alt-shift-w` → `user.toggle_editor()` |
| `editor_test.py` | Scratch file for bare textarea isolation testing — can be deleted |
| `~/.talon/user/talon-ui-elements/` | Forked UI kit (see below) |

## External Dependencies

- **talon-ui-elements fork** — `github.com/trillium/talon-ui-elements`, cloned to `~/.talon/user/talon-ui-elements/`
  - Two patches applied to the fork (see Gotchas)

## Fork Patches (talon-ui-elements)

| File | Change |
|------|--------|
| `src/platform/custom_input.py` | Tab in multiline inputs inserts 4 spaces instead of passing through for focus navigation |
| `ui_elements.py` | Added `ui_elements_get_input_scroll_offset(id) -> float` action to expose `InputState.scroll_offset` |

## Gotchas

- **`overflow="hidden"` on wrapper divs breaks textarea input.** It corrupts `visible_rect` (via `clip_rect`) for the textarea node, which breaks the blockable canvas carve-out calculation. The blockable canvas ends up covering the textarea area, eating mouse clicks before the textarea gets focus. Fixed by removing `overflow="hidden"` and using per-side border radii (`border_top_left_radius`, etc.) instead.
- **Scroll sync is polled, not event-driven.** The 100ms cron is a workaround — `talon-ui-elements` has no `on_scroll` callback for textarea. Fast scrolling may look slightly laggy.
- **Line height constant must match textarea internals.** `LINE_HEIGHT = FONT_SIZE + 4` mirrors `NodeTextarea._get_line_height()` which returns `paint.measure_text("X")[1].height + gap` (gap defaults to 4). If font or gap changes, update `LINE_HEIGHT`.
- **`visible_lines` has a +2 buffer** to account for the partial line visible at the bottom of the viewport and measurement imprecision.

## Last Updated

2026-05-22
