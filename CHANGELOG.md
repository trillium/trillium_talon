# trillium_talon — Changelog

## 2026-08-08 — reverse sound reserved for re-launching pondering

Files: trillium/plugin/repeater/repeater.py, trillium/plugin/repeater/repeater_sleep.talon, .tests/test_repeater_sleep.py

Generalized the "no natural opposite → re-enter pondering" rule beyond the
line-enders. Any action with no entry in `OPPOSITES` now uses the reverse
sound (kitty-cmere) to re-launch pondering (`LINE_ENDER_REVERSE_ACTION`) instead
of logging "No opposite defined" and no-op'ing — in command mode (`opposite()`)
and from sleep (`repeater_sleep_opposite()`). In sleep mode cmere still
consumes an ARMED opposite override first (and never executes the last
command's opposite); only when nothing is armed does the sound re-launch
pondering, so the hands-free loop stays live from a cold sleep:
sleep → cmere → dictate → tongue-click submit → back to sleep.

Tests: 3 updated, 2 added. `test_sleep_opposite_without_override_relaunches_pondering`
replaces the old no-op assertion; new `test_sleep_opposite_without_override_ignores_stored_command`
and `test_command_mode_opposite_no_mapping_relaunches_pondering`; the
dispatch-by-sound test now asserts cmere doesn't consume the repeat slot.
Full suite: 107 passed; 3 pre-existing recall failures unchanged.

## 2026-08-08

Files: trillium/plugin/repeater/repeater_sleep.talon (new), trillium/plugin/repeater/sleep_clear_commands.talon (new), trillium/plugin/repeater/repeater.py, trillium/core/click_to_finish.py, .tests/test_repeater_sleep.py (new), .tests/test_click_to_finish.py (new), .tests/stubs/talon/grammar.py, .tests/stubs/talon/__init__.py, .tests/stubs/talon/scripting/types.py, .tests/stubs/talon/engines/w2l.py (new), .tests/stubs/talon_init.py (new)

New `sleep_clear_commands.talon` authorizes exactly two voice commands —
`destroy` (→ `user.clear_last_dictation()`) and `nuke left` (→
`user.nuke_left()`, with the same aliases as rapid_delete.talon) — using the
SAME matchers as repeater_sleep.talon (`mode: sleep` + `tag: user.parrot_on` +
NOT pondering + NOT deep_sleep, every clause explicitly `and`'d). This lets the
hands-free sleep loop discard text it just entered without waking Talon.

Sleep-mode parrot sounds now consume repeater's armed overrides. New
`repeater_sleep.talon` binds tongue-click → `user.repeater_sleep_repeat()` and
kitty-cmere → `user.repeater_sleep_opposite()` while sleeping (`mode: sleep` +
`tag: user.parrot_on` + NOT pondering + NOT deep_sleep, every clause explicitly
`and`'d — same-type matchers OR by default, so un-AND'd tags would have matched
during pondering and re-created the task-rg2q context-tie). Unlike the
command-mode handlers, the sleep actions NEVER fall back to the last command:
with no override armed the sound is ignored. This lets SuperWhisper dictation
close and reopen from sleep via the follow-ups click_to_finish.py lines up
(submit on repeat, re-enter pondering on opposite).

click_to_finish.py: pondering exit now restores the pre-entry state instead of
always returning to command mode. `enable()` captures whether Talon was asleep
before `speech.disable()` drops it into mode:sleep; `disable()` returns to
sleep (`speech.disable()`) if it started asleep, else to command mode. This
makes the sleep-loop hands-free and symmetric: sleep → cmere → dictate →
tongue-click (submit) → back to sleep.

repeater.py: extracted the override-consumption path into `_consume_override()`,
shared by `repeat_last_repeatable()`/`opposite()` and the two new sleep actions
(no behavior change for command mode). Parrot logging is a no-op in sleep anyway
(`log_parrot_command` gates on command/dictation modes).

Tests: 12 new tests — 9 in `.tests/test_repeater_sleep.py` (armed/no-armed/
no-fallback/persistence/debounce/dispatch-slot isolation) and 3 in
`.tests/test_click_to_finish.py` (exit-to-command / exit-to-sleep / stale-state
reset). Test harness: added `speech_system` stub, `talon.grammar.vm`
(VMCapture/VMListCapture), `talon.engines.w2l` (DecodeWord/WordMeta),
`CommandImpl`, and `talon_init.TALON_HOME` so the repeater import chain
(→ command_logger → analyze_phrase) loads under pytest. Full suite: 105 passed;
3 pre-existing failures in test_recall_overlay_persistent.py (test expects
`on_mouse_persistent`, which doesn't exist in the module — unrelated to this
change, recall files are mid-work).

## 2026-08-03 — session 573726b5

Files: trillium/plugin/mode_indicator/poll_usage.py
## 2026-07-30 — session d29b1466

Files: trillium/plugin/herder/herder_nav.talon
## 2026-07-30 — session d0ad18fe

Files: plugin/recall/herdr_tab_alias.talon-list, trillium/plugin/media/media.talon, trillium/microphone/change_mic.py
## 2026-07-23 — Edgar (task-ya0t, P1 regression)

Files: trillium/plugin/herder/herder_nav.talon

Cursorless/editor commands ("split right", "split down", "pane left/right/up/down")
were being EATEN in VSCode. Root cause via the matcher (talon-inspect + registry
_active_scores): herder_nav.talon loaded GLOBALLY (specificity [1,0,0,0,0,0], no
app/mode/tag) so its herdr pane-nav commands won everywhere, shadowing VSCode.
(The broader "cursorless eaten" report was mostly this + action-name collisions;
bind-trace showed standard cursorless commands — take/chuck/bring/etc. — still win
cursorless.talon, so it was NOT a cursorless-grammar shadow.)

Fix: scoped herder_nav.talon to `tag: user.herder_panel` (set by herder_panel.py
when app.name=WezTerm — herdr isn't a standalone app so `app:` can't match it,
exactly as the file's own NOTE and herder_panel.py prescribe). Now the pane/split/
tab/space commands are active ONLY when the herdr terminal is focused; in VSCode
they go inactive and stop shadowing. Verified via registry: herder_nav
_active_scores tag_count=1, active only under WezTerm.


## 2026-07-22 — Edgar (task-z7bn)

Files: trillium/plugin/mode_indicator/poll_usage.py, trillium/plugin/mode_indicator/accounts.json

Fix the Claude Code usage tracker for a SINGLE subscription and get live data
flowing into the mode indicator again. It was dead — mode_indicator_state.json
had week_percent/five_hour_percent = null and accounts = [].

Root causes + fixes:
- `update_state` only wrote the legacy top-level keys the indicator reads when
  `account_name == "primary"`, but accounts.json named them "acc1"/"acc2" → those
  keys were NEVER written. Fixed: primary is now the FIRST account by position
  (`is_primary` flag threaded through main → poll_account → update_state), not a
  magic name. Works for one subscription (sole account = primary).
- Both accounts used `token_format: "raw"` (ccjuggler setup tokens, inference-
  scoped) → poll_account returns early (usage API needs a user:profile OAuth
  scope) → no usage ever fetched. Fixed: accounts.json is now a single account
  using the built-in `Claude Code-credentials` OAuth token (claude-credentials-json)
  — the real logged-in subscription that CAN fetch usage.
- Stale subscription_end (June, past) pinned week_percent to 100%. Fixed:
  effective_end_iso ignores a subscription-end already in the past (auto-renewing
  sub) and uses the live 7-day window; the primary account uses the file-based
  override path.
- VERIFIED live: restarted com.trillium.poll-usage; state now writes
  week_percent≈30 (4d21h), five_hour≈9%, static "62%  23c", subscription active.

## 2026-07-22 — Edgar (task-stke)

Files: plugin/recall/herdr_focus.py, plugin/recall/herdr_focus.talon, plugin/recall/herdr_tab_alias.talon-list

Voice-alias jump to a specific herdr tab: say "mayor"/"firstmate"/"edgar"/etc.
to focus that agent's herdr tab and bring the herdr host (WezTerm) to the front.

- `herdr_focus_tab(target)` shells to `herdr agent focus <arg>`. Named agents
  focus by name; the nameless firstmate/mayor tabs resolve DYNAMICALLY by cwd
  (`cwd:code/firstmate` → current pane_id via `herdr agent list`) since tab/pane
  ids change across restarts. Then `open -a WezTerm` foregrounds the host.
- Alias→target map lives in herdr_tab_alias.talon-list (easy to extend):
  mayor/firstmate→firstmate cwd, plus edgar/hooks/shepherd/mechanic/parlay-dev/
  danny/noreddit by name.
- Self-contained — does NOT touch recall's persistent overlay (avoids its known
  focus bug). Resolver verified read-only (cwd→w5:p1, all names present); the
  live focus + foreground needs a voice test.

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
