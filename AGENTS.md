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

This project includes a comprehensive testing harness that lets you test Talon plugins **without Talon running**. The stubs at `test/stubs/talon/` mock the entire Talon API surface.

```bash
python -m pytest test/ -v    # Run all tests
```

### Talon Runtime Model (What Agents Need to Know)

Talon is a voice-coding framework with a custom Python runtime. Key concepts:

| Concept | Description | How to test |
|---------|-------------|-------------|
| **Module** | Declares actions, lists, settings, tags, captures | Stubs auto-register actions |
| **Context** | Activates based on OS, app, tags, modes | Set `Context.matches` in tests |
| **Actions** | Named functions called by voice commands | `actions.register_test_action()` |
| **Settings** | User-configurable values (`user.my_setting`) | `Settings.set("user.my_setting", val)` |
| **Canvas** | Screen overlay for visual UI (uses Skia) | `Canvas.from_screen()` + mock Skia canvas |
| **Cron** | Timer scheduling (`interval`, `after`) | `Cron.trigger(job_id)` fires manually |
| **Noise/Parrot** | Mouth noise detection (pop, hiss) | `ParrotSystem.simulate_noise("pop")` |
| **Clip** | Clipboard access | `Clip.set_text()` / `Clip.text()` |

### Available Stubs

```
test/stubs/talon/
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
