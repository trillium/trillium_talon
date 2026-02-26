from talon import Module

mod = Module()

mod.list("slash_command", desc="Slash commands for AI/coding tools")

@mod.capture(rule="{user.slash_command}")
def slash_command(m) -> str:
    return m.slash_command
