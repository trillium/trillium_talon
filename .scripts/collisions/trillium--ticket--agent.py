"""Background AI agent for ticket refinement."""

import datetime
import os
import subprocess
from pathlib import Path

ASK_CMD = "/Users/trilliumsmith/bashrc_dir/commandline-ai-ask/bin/ask-user.sh"
OPS_DB = str(Path.home() / ".openclaw" / ".ops" / "beads.db")
CLAUDE_BIN = "/opt/homebrew/bin/claude"
LOG_DIR = Path.home() / ".talon" / "ticket_logs"


def _build_prompt(raw_text: str, scope: str, raw_scope: str) -> str:
    """Build the prompt for the background Claude agent."""
    return f"""You are a ticket refinement agent. A user just dictated a raw idea via voice. Your job is to refine it into a well-structured ops ticket.

## Raw Dictation
{raw_text}

## Scope
{scope} (utterance: "{raw_scope}")

## Tools Available

### Ask the user a question
Run this in bash:
```
{ASK_CMD} -m "Your question here" -v summary
```
This opens VSCode with your question. The user types their answer, saves, and closes VSCode. The answered content is returned on stdout.

### File the ticket to ops
When you have enough information, create the ticket:
```
ops --db {OPS_DB} create --title "Clear, concise title" --type task --labels "ticket,{scope}" --description "Full description" --silent
```

### Notify the user
After filing, show a macOS notification:
```
osascript -e 'display notification "Filed: ISSUE-ID - TITLE" with title "Ticket Filed"'
```

## Rules
- Ask 1-3 focused questions to clarify the idea. The user dictated this by voice so keep it quick.
- If the idea is already clear from the dictation, you may skip questions and file directly.
- Maximum 3 rounds of questions. After that, file with what you have.
- For the ticket title: make it actionable and specific (imperative form, e.g. "Add X to Y").
- For the description: synthesize the raw dictation + answers into a clear description. Include the original raw dictation at the bottom under "## Raw Dictation".
- If ask fails or the user provides no answer, file the ticket with what you have rather than looping.
- After filing, always show the macOS notification.
- Output a final summary line: "Filed: <issue-id> - <title>"
"""


def _build_env() -> dict:
    """Build environment for the background Claude process."""
    env = os.environ.copy()
    extra_paths = [
        "/Users/trilliumsmith/bin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    env["PATH"] = ":".join(extra_paths) + ":" + env.get("PATH", "")
    return env


def spawn_refinement_agent(raw_text: str, scope: str, raw_scope: str):
    """Spawn background Claude agent to refine and file a ticket."""
    prompt = _build_prompt(raw_text, scope, raw_scope)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = LOG_DIR / f"ticket-{timestamp}.log"

    print(f"[ticket] Spawning refinement agent, log: {log_file}")

    try:
        with open(log_file, "w") as log_f:
            subprocess.Popen(
                [
                    CLAUDE_BIN,
                    "-p",
                    prompt,
                    "--model", "sonnet",
                    "--permission-mode", "bypassPermissions",
                    "--allowedTools", "Bash",
                    "--no-session-persistence",
                ],
                start_new_session=True,
                stdout=log_f,
                stderr=log_f,
                env=_build_env(),
            )
    except Exception as e:
        print(f"[ticket] Failed to spawn agent: {e}")
