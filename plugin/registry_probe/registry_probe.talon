mode: command
-

# On-demand registry snapshot. Output goes to ~/.talon/registry_probe.jsonl —
# tail / grep / jq it post-hoc.
registry probe dump: user.registry_probe_dump("voice")

# Truncate the JSONL log between repro attempts to keep diffs clean.
registry probe clear: user.registry_probe_clear()
