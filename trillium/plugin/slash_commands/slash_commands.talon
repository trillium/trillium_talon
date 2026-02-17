# Slash commands for Claude Code and similar tools
# Say "slash help", "slash model opus", etc.
# Add "bravely" (or other dictation_ender) to also press Enter.
slash {user.slash_command}:
    insert(slash_command)

slash {user.slash_command} {user.dictation_ender}$:
    insert(slash_command)
    key(enter)
