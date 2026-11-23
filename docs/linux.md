# Running this config on Linux

First brought up on an Arch/Omarchy laptop: Talon 1.0.0 under an X11 (Cinnamon)
session, with Hyprland/Wayland also installed. The rule: anything that differs
by operating system is an `os: linux` override file or context beside the
original, so macOS keeps doing exactly what it did.

## Launching Talon

Talon 1.0.0 needs an X11 session (it only sees X11/XWayland windows) and a
runtime directory. Start it with `XDG_RUNTIME_DIR` set, for example:

```bash
XDG_RUNTIME_DIR=/run/user/$(id -u) /path/to/talon
```

Without it Talon cannot create its sockets and parts of the UI fail to start.
Clone this repo to `~/.talon/user/trillium_talon` as on macOS.

## What each override does

| File                                                                                      | Scope                                                  | Effect                                                                                                                                                                                                                                                           |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `trillium/microphone/change_mic.py`                                                       | `os: mac` (was unscoped)                               | The OpenSuperWhisper sync shells out to a Mac-only binary, so this context now matches macOS only.                                                                                                                                                               |
| `trillium/microphone/change_mic_linux.py`                                                 | `os: linux`                                            | `mic main` picks the "Wireless GO" input by name and calls Talon's own `set_microphone`; no OpenSuperWhisper step.                                                                                                                                               |
| `trillium/plugin/mode_indicator/mode_indicator.py`, `trillium/quota_panel/quota_panel.py` | all OS, compatibility only                             | Older Talon skia builds raise when a paint's `shader`/`imagefilter` is set to `None` and lack the 4th `arc_to_with_oval` argument. The helper `_compat_clear` and an `arc_to` shim handle both; newer builds take the original path.                             |
| `trillium/plugin/mode_indicator/mode_indicator.py`                                        | all OS, default 1.0                                    | New setting `user.mode_indicator_ui_scale` multiplies every size in the indicator. 1.0 draws exactly as before.                                                                                                                                                  |
| `trillium/mode_indicator/mode_indicator-linux.talon`                                      | `os: linux`                                            | Sets `user.mode_indicator_ui_scale = 2.0` (Linux reports raw pixels, macOS points).                                                                                                                                                                              |
| `trillium/plugin/mode_indicator/mode_indicator_state.py`                                  | Linux branch only                                      | The system-monitor stats file is read from `$MONITOR_DATA_DIR`, else `${XDG_DATA_HOME:-~/.local/share}/system-monitor/stats.json`. Other OSes keep the old `~/code/system-monitor/data/stats.json`.                                                              |
| `trillium/plugin/herder/herdr_prefix_linux.{py,talon}`                                    | `os: linux`, WezTerm                                   | `prefix`, `prefix <letter>` and Caps Lock (`f19`, sent by keyd) send herdr's real prefix key, read from `~/.config/herdr/config.toml` `[keys] prefix`. macOS hard-codes `ctrl-b`. If the file is missing or unreadable it falls back to `ctrl-b` and prints why. |
| `plugin/recall/herdr_tab_wezterm_linux.talon`                                             | `os: linux`, WezTerm                                   | `tab next` / `tab previous` drive herdr's CLI, as the macOS `herdr_tab_wezterm.talon` does (that file matches `app: WezTerm`, which never matches on Linux).                                                                                                     |
| `plugin/recall/herdr_tab_voice_linux.py`                                                  | `os: linux`                                            | Overrides `user.herdr_tab_focus`; see below.                                                                                                                                                                                                                     |
| `linux/hyprland_bridge/hyprland_bridge.py`                                                | `os: linux`, polls only when `app.platform == "linux"` | Under Hyprland Talon sees only XWayland windows. The bridge fills `user.running` from `hyprctl clients -j` and makes `user.switcher_focus` call `omarchy hyprland focus app <class>`. Delete the folder to undo.                                                 |

## System-monitor dependency

The CPU per-core bars and the memory line in the indicator read `stats.json`
written by the system-monitor collector. On Linux that needs
[trillium/system-monitor PR 1](https://github.com/trillium/system-monitor/pull/1)
(procfs collector plus a systemd user service). Without it the bars stay empty.
The quota cells (`CC`, `OC`, ...) come from `quota-axi` and are independent of it.

## How recall differs on Linux

The macOS recall path activates apps with `open -a` and AppleScript-style
window handling. On Linux, `herdr_tab_voice_linux.py`:

- keeps the `fm-*` tabs in the spoken tab-name list;
- resolves a spoken tab name against a live `herdr tab list` (not the 10 s cache),
  focuses it by tab id with `herdr workspace focus` / `herdr tab focus`, then
  checks herdr reports it focused, retrying once;
- raises the WezTerm window with `xdotool` (needs `xdotool` installed) instead of `open -a`;
- for a tab on another machine, reads the window title (`<host>: <workspace>`)
  to find which herdr is in front and uses `herdr --machine`; if the tab is
  not reachable that way it types herdr's Goto picker, but only after WezTerm
  is verified as the active window, so no stray keys reach another app.

## Tests

`python -m pytest` (CI config in `.github/workflows/ci.yml`). `.tests/test_linux_overrides.py`
covers the Linux-only paths and that they stay inert when the platform is macOS.
Ten tests in `.tests/test_herdr_picker.py` already fail on `main` in this
environment, before and after these changes.
