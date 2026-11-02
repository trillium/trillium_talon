"""Status -> color + badge text for the recall pill overlay. Pure stdlib, no Talon imports."""

STATUS_IDLE = "idle"
STATUS_ACTIVE = "active"
STATUS_CHURNING = "churning"  # 2+ concurrent agents
STATUS_UNKNOWN = "unknown"

COLOR_MAP = {
    STATUS_IDLE:     "22aa44",  # green
    STATUS_ACTIVE:   "4488ff",  # blue
    STATUS_CHURNING: "ff4444",  # red
    STATUS_UNKNOWN:  "666666",  # gray
}


def status_to_color(status: str) -> str:
    """Return 6-char hex color for a status string. Defaults to STATUS_UNKNOWN color."""
    return COLOR_MAP.get(status, COLOR_MAP[STATUS_UNKNOWN])


def derive_status(agent_count: int, monitor_count: int, base_status: str) -> str:
    """Derive final status: churning if 2+ agents, else base_status if valid, else unknown."""
    if agent_count >= 2:
        return STATUS_CHURNING
    return base_status if base_status in COLOR_MAP else STATUS_UNKNOWN


def format_badge(agent_count: int, monitor_count: int) -> str:
    """Format badge text for pill corner ('', '2A', '1M', or '2A 1M')."""
    parts = []
    if agent_count > 0:
        parts.append(f"{agent_count}A")
    if monitor_count > 0:
        parts.append(f"{monitor_count}M")
    return " ".join(parts)
