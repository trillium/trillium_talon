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

### Test Patterns by Plugin Type

See `test/examples/` for complete working examples:

| Plugin Type | Example File | Key Pattern |
|-------------|-------------|-------------|
| Voice commands | `test_voice_command_pattern.py` | Register mocks → call action → assert |
| Canvas overlays | `test_canvas_overlay_pattern.py` | Mock Skia canvas records draw ops |
| Parrot handlers | `test_parrot_handler_pattern.py` | ParrotSystem.simulate_noise() |
| Settings-dependent | `test_settings_pattern.py` | Settings.set() → test → Settings.reset() |
| Timer-based | `test_cron_timer_pattern.py` | Cron.trigger() fires callbacks manually |

### Quick Start: Writing a Test

```python
import talon

if hasattr(talon, "test_mode"):
    from talon import actions

    def setup_function():
        actions.reset_test_actions()

    def test_my_action():
        # Import your module (registers actions via @mod.action_class)
        import path.to.my_module

        result = actions.user.my_action("input")
        assert result == "expected output"
```

### Fixtures (test/conftest.py)

| Fixture | Purpose |
|---------|---------|
| `talon_actions` | Clean action registry per test |
| `talon_settings` | Clean settings per test |
| `mock_canvas` | Skia Canvas that records draw operations |
| `mock_paint` | Fresh Skia Paint object |
| `mock_screen` | 1920x1080 Screen object |
| `screen_rect` | (0, 0, 1920, 1080) tuple |
| `talon_cron` | Clean cron/timer state |
| `talon_clip` | Clean clipboard state |
| `talon_noise` | Clean noise detection state |
| `parrot_system` | ParrotSystem for noise handler testing |

### Testing Pure Logic (No Stubs Needed)

For pure computation (geometry, parsing, formatting), extract logic into plain Python functions and test directly — no Talon imports needed:

```python
# In your plugin: extract pure logic
def calculate_angle(x, y, cx, cy):
    import math
    return math.atan2(y - cy, x - cx)

# In your test: test it directly
def test_angle_calculation():
    from my_plugin import calculate_angle
    assert calculate_angle(1, 0, 0, 0) == 0.0
```

This is the **preferred pattern** when possible — faster, simpler, no mock complexity.

<!-- BEGIN BEADS INTEGRATION -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Auto-Sync

bd automatically syncs via Dolt:

- Each write auto-commits to Dolt history
- Use `bd dolt push`/`bd dolt pull` for remote sync
- No manual export/import needed!

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and docs/QUICKSTART.md.

<!-- END BEADS INTEGRATION -->
