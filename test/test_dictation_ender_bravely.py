"""Lock the bravely ender so it still submits when dictation mode is off.

Command history on 2026-10-13: dictation mode was off all afternoon, "bravely"
matched nothing, and "lap" still pressed Enter via a command-mode literal in
test_mode_command.talon. The focused agent never got a newline.

The recall comment promises "edgar hello world bravely" submits. That phrase
used to match `<user.saved_window_names> <user.raw_prose>` and the ender was
dictated as a word, so Enter never fired.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _talon(rel: str) -> str:
    return (ROOT / rel).read_text()


def _header(text: str) -> str:
    """Return the context header, the lines above the first standalone '-'."""
    lines = []
    for line in text.splitlines():
        if line.strip() == "-":
            break
        lines.append(line)
    return "\n".join(lines)


def _rules(text: str) -> str:
    """Command body. Files with no context header have no '-' separator."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "-":
            return "\n".join(lines[i + 1 :])
    return text


def test_bravely_ender_is_active_in_command_mode():
    header = _header(_talon("trillium/core/modes/dictation_bravely.talon"))
    assert "mode: dictation" in header
    assert "mode: command" in header

    body = _rules(_talon("trillium/core/modes/dictation_bravely.talon"))
    assert "<user.raw_prose> {user.dictation_ender}$:" in body
    parts = body.split("{user.dictation_ender}$:")
    # parts[0] is the "<user.raw_prose> " prefix, parts[1] that rule's body,
    # parts[2] the bare ender body.
    assert parts[0].strip() == "<user.raw_prose>"
    prose_body = parts[1]
    assert "user.dictation_insert(raw_prose)" in prose_body
    assert "key(enter)" in prose_body
    bare = parts[2]
    assert "key(enter)" in bare
    assert "dictation_insert" not in bare


def test_ender_list_includes_bravely():
    listing = _talon("trillium/core/modes/dictation_ender.talon-list")
    assert listing.startswith("list: user.dictation_ender")
    spoken = [
        line.split(":", 1)[0].strip()
        for line in listing.splitlines()
        if line.strip() and not line.startswith("list:") and line.strip() != "-"
    ]
    assert "bravely" in spoken
    # lap is an ender, not a separate command-mode shortcut.
    assert "lap" in spoken


def test_command_mode_has_no_lap_only_enter_shortcut():
    """A literal `lap:` in command mode hides a dead bravely rule."""
    body = _rules(_talon("trillium/test_mode_command.talon"))
    commands = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            continue
        commands.append(stripped.split(":", 1)[0].strip())
    assert "lap" not in commands


def test_recall_dictate_plus_ender_presses_enter():
    body = _rules(_talon("plugin/recall/recall.talon"))
    marker = "^<user.saved_window_names> <user.raw_prose> {user.dictation_ender}$:"
    assert marker in body
    rule = body.split(marker, 1)[1].split("\n^", 1)[0]
    assert "user.dictate_to_window_and_enter(saved_window_names, raw_prose)" in rule

    # The prose-only rule must not be the one that handles an ender phrase.
    swallow = body.split("^<user.saved_window_names> <user.raw_prose>$:", 1)[1].split(
        "\n^", 1
    )[0]
    assert "dictate_to_window_and_enter" not in swallow
    assert "key(enter)" not in swallow


def test_dictate_to_window_and_enter_focuses_before_submit():
    source = _talon("plugin/recall/recall.py")
    start = source.index("def dictate_to_window_and_enter")
    fn = source[start:].split("\n    def ", 1)[0]
    focus = fn.index("recall_window")
    insert = fn.index("dictation_insert")
    enter = fn.index('key("enter")')
    assert focus < insert < enter
    # A sleep sits between focus and insert so the submit hits the new window.
    between = fn[focus:insert]
    assert "sleep" in between
