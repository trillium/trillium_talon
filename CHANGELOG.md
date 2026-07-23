# trillium_talon — Changelog

## 2026-07-22 — Edgar (task-bg4y)

Files: trillium/plugin/repeater/opposite_mappings.py, trillium/plugin/repeater/repeater.py

Keep the reverse-sound double-click chain viable after a line-ender command.
Line-enders (bravely/gravely/slap/lap) submit a line but have NO natural
opposite, so after one fired, repeater's `opposite()` hit "No opposite defined"
and the reverse (cmere) double-click had nothing to fire — the chain went dead.

- Added `LINE_ENDER_TRIGGERS` (+ `LINE_ENDER_REVERSE_ACTION`) to
  opposite_mappings.py — the extensible line-ender set, kept in sync with
  dictation_ender.talon-list; their reverse action is `user.pondering_enable`.
- repeater.py `opposite()`: before the "no opposite" fallback, if the last
  command is a line-ender (in the set, or its trigger contains `dictation_ender`),
  the reverse RE-ARMS the SuperWhisper reverse-listen / pondering queue
  (re-enter pondering) instead of no-op'ing. So the reverse double-click survives
  a submit. (dictation `<user.raw_prose>` enders were already excluded from
  repeater tracking, so this targets command-mode `lap` and the bare ender.)
- Needs a live mouth-sound confirm (say a line-ender → cmere re-enters pondering);
  loads clean, logic verified by construction.

## 2026-07-21 — Edgar (task-nmc9 Part A)

Files: trillium/pomodoro/pomodoro.py

Expose the Pomodoro timer's end time to external tools (row.sh `row pomodoro`
reads it, Part B). The timer runs on `time.monotonic()` in-memory; added a
wall-clock projection persisted to `~/.talon/pomodoro-state.json`:

    {"active": bool, "end_iso": ISO8601, "end_epoch": int, "paused": bool}

- New `_write_state()` (atomic tmp+rename) computes `end = now + remaining`
  (remaining = current_duration − (pause_time or monotonic − start_time), clamped
  ≥0) and writes the contract file. Called on every state change:
  `pomodoro_start` / `pomodoro_pause` / `pomodoro_unpause` / `pomodoro_cancel`.
  `active=false` (empty end) when nothing is running.
- Fixed a pre-existing NameError in `pomodoro_unpause`: it referenced an
  undefined `current_time` global. Now correctly shifts `start_time` forward by
  the paused span so `remaining` is unchanged on resume — which also makes the
  resumed state file correct.
- NOTE (out of scope, flagged): pomodoro.talon binds `^pomodoro (unpause|resume)$`
  to `pomodoro_pause()` (should be unpause). "resume timer"/"resume pomodoro"
  correctly unpause via the other binding.

## 2026-07-21 — Edgar (task-rg2q + task-1rxa)

Files: trillium/core/click_to_finish.py, trillium/core/click_to_finish.talon

Sound-only submit + re-enter for the pondering flow, built on repeater.py's
NATIVE "line up the next action" API (`set_next_repeat_action` /
`set_next_opposite_action`) — NOT a custom state machine:

    (pondering) tongue-click -> finish pondering + write text
    on finish, line up via repeater:
        next tongue-click (repeat)  -> user.click_submit_now  (press Enter)
        next cmere        (opposite) -> user.pondering_enable  (re-dictate)

- task-rg2q (submit): after a click finishes pondering + writes the text, the
  next tongue-click submits. Submit key is configurable: `click action <keys>` /
  `click action default` (default `key(enter)`); `click fire` submits manually.
  A `debounce_s=1.0` guards against an accidental fast double-submit.
- task-1rxa (re-enter): the opposite sound (cmere, repeater's native reverse)
  re-enters pondering to dictate again — mirroring the tongue-click exit.
- WHY this replaced the first attempt: I first built a custom armed-state machine
  with COMPETING contexts to intercept the tongue-click. It reloaded clean but
  NEVER fired — talon.log showed the 2nd click going to repeater ("Logged repeat
  action"), even after a `mode: command` specificity fix. repeater's own
  override API runs the lined-up action with repeater's handler, so there is no
  context to lose. All the `click_armed_*` tags/contexts were deleted.
- Overrides clear when a new command is spoken (native repeater semantics).
- NEEDS a live mouth-sound test; watch talon.log for "Set next repeat action" on
  the finish and "Using override repeat action: user.click_submit_now" on submit.

## 2026-07-14 — session a5b266ee

Files: trillium/core/click_to_finish.py, trillium/core/pondering_hotkey.talon
## 2026-07-13 — session bfd4ac10

Files: trillium/core/click_to_finish.py
## 2026-06-29 — session d9615840

Files: plugin/cursorless_scope_support/scope_support_overlay.py, trillium/plugin/mode_indicator/mode_indicator_state.py, trillium/plugin/mode_indicator/rowing_pacer.py, plugin/recall/recall.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-29 — session 41ab6ec1

Files: trillium/plugin/repeater/gaze_ocr_choice.py, trillium/plugin/repeater/repeater.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-22 — session 3bd7bfef

Files: trillium/plugin/mode_indicator/poll_usage.py, trillium/plugin/mode_indicator/ccjuggler.py, trillium/plugin/mode_indicator/accounts.json, trillium/plugin/mode_indicator/scrape_usage.ts, trillium/plugin/mode_indicator/poll_interceptor.ts

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-21 — session 63fec7b8

Files: trillium/anki/anki.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-14 — session 0b84ff3e

Files: core/overlay_kit/primitives.py, core/overlay_kit/styling.py, core/overlay_kit/lifecycle.py, core/overlay_kit/__init__.py, plugin/recall/recall_overlay_shared.py, plugin/cursorless_scope_support/__init__.py, plugin/cursorless_scope_support/scope_support_overlay.py, plugin/cursorless_scope_support/scope_support.talon, plugin/cursorless_scope_support/scope_support_hide.talon

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-14 — session e4003b37

Files: plugin/recall/recall_overlay_persistent.py, plugin/recall/recall_session_state.py, plugin/recall/recall_save.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-14 — session b8d5a009

Files: core/vocabulary/vocabulary.talon-list

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-14 — session b9a5ad55

Files: trillium/plugin/mode_indicator/sysmon_graph.py, trillium/plugin/mode_indicator/poll_usage.py, trillium/plugin/mode_indicator/mode_indicator.py, trillium/plugin/mode_indicator/check_subscription_end.py, trillium/plugin/mode_indicator/mode_indicator_state.py, trillium/plugin/mode_indicator/subscription_override.json

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-13 — session b15d7d25

Files: trillium/anki/anki_connect.py, trillium/anki/anki_state.py, trillium/anki/anki_draw.py, trillium/anki/anki.py, trillium/anki/anki.talon, trillium/anki/anki_review.talon, trillium/anki/anki_renderer.py, trillium/anki/anki_ui_elements.py, trillium/anki/anki_parrot.talon

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-11 — session af677811

Files: plugin/recall/recall_overlay_persistent.py, plugin/recall/recall_state.py, plugin/recall/recall_pill_colors.py, plugin/recall/recall_session_state.py, plugin/recall/recall_overlay_draw.py, test/test_claude_pills.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-08 — session 5847490d

Files: settings/words_to_replace.csv

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-03 — session d3895255

Files: trillium/mode_indicator/mode_indicator-macbookpro.lan.talon, trillium/plugin/mode_indicator/poll_usage.py, trillium/plugin/mode_indicator/mode_indicator.py, plugin/recall/recall_meta.py, trillium/plugin/speak_history/speak_history.py, trillium/plugin/speak_history/speak_history_overlay.py, trillium/plugin/speak_history/speak_history_all.talon, trillium/plugin/speak_history/speak_history_active.talon, trillium/plugin/mode_indicator/mode_indicator_state.py, core/app_switcher/app_switcher.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-27 — session d3895255

Files: trillium/mode_indicator/mode_indicator-macbookpro.lan.talon, trillium/plugin/mode_indicator/poll_usage.py, trillium/plugin/mode_indicator/mode_indicator.py, plugin/recall/recall_meta.py, trillium/plugin/speak_history/speak_history.py, trillium/plugin/speak_history/speak_history_overlay.py, trillium/plugin/speak_history/speak_history_all.talon, trillium/plugin/speak_history/speak_history_active.talon, trillium/plugin/mode_indicator/mode_indicator_state.py, core/app_switcher/app_switcher.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-25 — session 11199fc5

Files: core/system/logs/logs_data.py, core/system/logs/logs_overlay.py, core/system/logs/logs_draw.py, core/system/logs/logs.py, core/system/logs/logs.talon, core/system/logs/logs_active.talon, core/system/logs/logs_entry_active.talon, core/system/logs/logs_ignore_active.talon, trillium/plugin/mode_indicator/mode_indicator_state.py, trillium/mode_indicator/mode_indicator_commands.talon

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-25 — session b77c3149

Files: plugin/recall/recall_save.py, plugin/recall/recall.py, plugin/recall/recall_meta.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-25 — session 26fe074f

Files: trillium/plugin/mode_indicator/mode_indicator.py, trillium/plugin/mode_indicator/mode_indicator_state.py, trillium/plugin/mode_indicator/sysmon_graph.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-23 — session 953f2d22

Files: trillium/plugin/prose_overlay/prose_overlay.talon, trillium/plugin/prose_overlay/prose_overlay_cursorless.talon

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-23 — session 0f53b1ea

Files: trillium/editor.py, trillium/editor.talon, trillium/editor_test.py, trillium/SPEC.md, trillium/CHANGELOG.md

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-22 — session c77720d6

Files: trillium/plugin/prose_overlay/prose_overlay_actions_js.py, trillium/plugin/prose_overlay/prose_overlay.py, trillium/plugin/prose_overlay/prose_overlay.talon, trillium/plugin/prose_overlay/prose_overlay_state.py, trillium/plugin/prose_overlay/prose_overlay_draw.py, trillium/plugin/prose_overlay/prose_overlay_canvas.py, trillium/plugin/prose_overlay/prose_overlay_cursorless.talon, trillium/plugin/prose_overlay/prose_overlay_hats_js.py, trillium/plugin/prose_overlay/HAT_ALLOC_OVERFLOW_ANALYSIS.md, trillium/plugin/prose_overlay/prose_overlay_start.talon

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-22 — session 0bd6fa08

Files: trillium/plugin/prose_overlay/prose_overlay_draw.py, trillium/plugin/prose_overlay/prose_overlay.py, trillium/plugin/prose_overlay/prose_overlay_canvas.py, trillium/plugin/prose_overlay/prose_overlay.talon, trillium/plugin/prose_overlay/prose_overlay_state.py, trillium/plugin/prose_overlay/prose_overlay_pre_post.talon, trillium/plugin/prose_overlay/prose_overlay_head_tail.talon, trillium/plugin/prose_overlay/prose_overlay_bring_move.talon

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-22 — session 82c7ba45

Files: trillium/plugin/prose_overlay/prose_overlay_hats_js.py, trillium/plugin/prose_overlay/prose_overlay.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-21 — session a5ab8dd3

Files: plugin/recall/recall.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-20 — session 084bbd8f

Files: plugin/recall/recall_save.py, plugin/recall/recall.py, plugin/recall/recall_overlay_persistent.py, plugin/recall/recall_overlay_draw.py, plugin/recall/recall_diag.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-19 — session 8c37d892

Files: plugin/recall/recall_overlay.py, plugin/recall/recall_overlay_persistent.py, test/stubs/talon/ui.py, test/test_recall_overlay_persistent.py, test/stubs/talon/canvas.py

> AI summary pending — check ProjectDocs Handover in next session.
