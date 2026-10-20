# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**

- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->

## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Testing Talon Plugins

### Overview

This project includes a comprehensive testing harness that lets you test Talon plugins **without Talon running**. The stubs at `.tests/stubs/talon/` mock the entire Talon API surface.

```bash
python -m pytest .tests/ -v    # Run all tests
```

### Talon Runtime Model (What Agents Need to Know)

Talon is a voice-coding framework with a custom Python runtime. Key concepts:

| Concept          | Description                                       | How to test                               |
| ---------------- | ------------------------------------------------- | ----------------------------------------- |
| **Module**       | Declares actions, lists, settings, tags, captures | Stubs auto-register actions               |
| **Context**      | Activates based on OS, app, tags, modes           | Set `Context.matches` in tests            |
| **Actions**      | Named functions called by voice commands          | `actions.register_test_action()`          |
| **Settings**     | User-configurable values (`user.my_setting`)      | `Settings.set("user.my_setting", val)`    |
| **Canvas**       | Screen overlay for visual UI (uses Skia)          | `Canvas.from_screen()` + mock Skia canvas |
| **Cron**         | Timer scheduling (`interval`, `after`)            | `Cron.trigger(job_id)` fires manually     |
| **Noise/Parrot** | Mouth noise detection (pop, hiss)                 | `ParrotSystem.simulate_noise("pop")`      |
| **Clip**         | Clipboard access                                  | `Clip.set_text()` / `Clip.text()`         |

### Available Stubs

```
.tests/stubs/talon/
├── __init__.py              # Core: Module, Context, Actions, Settings, App,
│                            #   Clip, Cron, Ctrl, Noise, Scope, Fs, Registry
├── canvas.py                # Canvas overlay + MouseEvent
├── screen.py                # Screen enumeration
├── grammar.py               # Phrase, Capture, vm.VMCapture
├── debug.py                 # log_exception
├── ui.py                    # Rect, Window, Screen, UIErr, events
├── skia/
│   ├── __init__.py          # Paint, Rect, Path
│   ├── canvas.py            # Drawing canvas (records operations for assertions)
│   └── imagefilter.py       # ImageFilter (blur, shadow)
├── types/
│   ├── __init__.py          # Rect
│   └── point.py             # Point2d
├── experimental/
│   ├── textarea.py          # TextArea stubs
│   └── parrot.py            # ParrotSystem, ParrotDelegate, ParrotFrame
└── scripting/
    └── types.py             # ListTypeFull
```

<!-- END BEADS INTEGRATION -->

## Talon runtime facts (verified live)

- Palette HTTP feed lives in `trillium/palette_feed/` on port 7399. Bind (`TALON_PALETTE_BIND` / `user.palette_feed_bind`), read auth (`TALON_PALETTE_OPEN_READS` / `user.palette_feed_open_reads`) and execute auth (`TALON_PALETTE_OPEN_EXECUTE` / `user.palette_feed_open_execute`) are per-host, all defaulting closed; while `open_execute` is on, the bind address and the tailnet are the whole boundary. `GET /` serves the phone search page (`page.html` via `page.py`), which holds no credential. Token setup, the full matrix and the phone page: `docs/palette-feed.md`.
- Talon drops a `.talon` `settings():` assignment whose setting has no `mod.setting` declaration in Python (`palette_feed.py` declares its three): the log says "settings skipped because they have no matching declaration", `settings.get` keeps returning the default, and the host looks configured while ignoring the value. Verify a setting with `settings.get` in the REPL, not by reading the `.talon` file.
- Verifying the palette page in a browser: `chrome-devtools-axi` launches Chrome but fails every page-scoped command (`pageId` never set; `robots-yujg4`). Drive headless Chrome over CDP instead, or run `.tests/palette_page_check.mjs` / `.tests/palette_page_dom_check.mjs`.
- `~/.talon/bin/repl` takes one statement per stdin line (a piped second line fails with "multiple statements"; put everything in one `exec("...")`); its `sim()` only prints. The real call is `speech_system._sim(phrase)`, which returns text and raises `RuntimeError("Failed to parse")`.
- The phone listener (`trillium/phone_receiver/listener.py`) is port 7403, default off, bound to `127.0.0.1` or this Mac's own tailnet address only (`user.phone_receiver_bind`); the tailnet bind is plain HTTP authenticated by the `X-Talon-Phone-Key` secret in `~/.config/talon-phone/key`, and there is no `tailscale serve` (captain's choice). Never print, log or commit that key; see `docs/phone-receiver.md`.
- In the Talon REPL a bare `trillium.*` import resolves to the live `~/.talon/user/trillium_talon` checkout (Talon's `PluginFinder`), not a task worktree, and Talon's environment may carry a stale `PHONE_LAB_REPO`. `.tests/lab/phone_listener_lab.py` loads worktree modules by file path under a `phlab` name.
- A thread inherits the resource context of whoever started it. Threads (and objects loaded) inside a Talon REPL statement are orphaned when it ends: `cron.after` raises `talon.scripting.rctx.ResourceClosed`, `print` raises `SystemExit`, and a private `W2lEngine` loses its `encoder`. This broke the live phone listener (started from the REPL, every request `500 internal`); `trillium/phone_receiver/hop.py` is the fix. A lab that outlives its statement must create and use everything under `rctx.manager.context(name)` + `.enter()` and `.free()` it afterwards.
- Talon's frames have no `f_code`, so `traceback.walk_tb` fails there; use `traceback.extract_tb`.
- Talon logs a stack-trace warning for every thread a user script starts, and has no module-unload hook: a deleted module's threads keep running.
- `actions.mimic` did nothing while the macOS session was locked (`CGSSessionScreenIsLocked`), even from the REPL. Verify mimic-driven code with the screen unlocked.
- `~/.talon` is itself a git repo; keep secrets in `~/.config/...`, not under `~/.talon`.
- A private `W2lEngine` (`W2lEngine(info=live._model_info)`, never registered) is the safe target for decoder experiments; a wrongly shaped array handed to the native decoder aborts Talon. The phone-emission receiver and its lab script are in `docs/phone-receiver.md`; the encoder frame count is `ceil(((n_pcm+8000-400)//160+1)/3)`.
- The live Talon loads `~/.talon/user/trillium_talon`, a separate checkout from any task worktree, and `settings.talon` there sets `speech.record_all = 1` (Talon has no public runtime setter). Anything that injects audio-less utterances (`trillium/phone_receiver/`) refuses while it is on; never touch `~/.talon/recordings`.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
