# Editor Overlay — Changelog

## 2026-05-22

- Fixed line numbers not displaying final visible line: added +2 buffer to `visible_lines` calculation
- Added scroll sync: 100ms cron polls `scroll_offset` from `custom_input_manager` and shifts visible line range
- Added `ui_elements_get_input_scroll_offset(id)` action to talon-ui-elements fork to expose internal scroll state
- Fixed textarea not accepting input: removed `overflow="hidden"` from wrapper div (corrupted blockable canvas carve-out); switched to per-side border radii
- Fixed tab key: patched fork's `custom_input.py` to insert 4 spaces in multiline inputs instead of passing through
- Added `autofocus=True` and `show_hints=False` to prevent hint system from intercepting keys
- Added line numbers column with `overflow_y=hidden` and `height=400` to prevent growth beyond textarea bounds
- Initial implementation: monospace textarea overlay with Menlo 14pt, rounded corners, toggle via `cmd-ctrl-alt-shift-w`
- Forked `rokubop/talon-ui-elements` to `github.com/trillium/talon-ui-elements`, cloned to `~/.talon/user/talon-ui-elements/`
