"""Twitch Helix API client for stream status queries and channel management."""
import json as _json
from dataclasses import dataclass
from typing import Optional

from user.trillium_talon.trillium.plugin.twitch.twitch_auth import get_bearer_token, get_client_id, http_request, refresh_oauth_token


@dataclass
class StreamStatus:
    is_live: bool
    viewer_count: int
    title: str
    game_name: str
    started_at: str


def _helix_get(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to the Helix API, handling 401 with one token refresh retry."""
    bearer = get_bearer_token()
    client_id = get_client_id()
    if not bearer or not client_id:
        print("Twitch Helix: missing bearer token or client_id")
        return {}

    url = f"https://api.twitch.tv/helix/{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"

    headers = {
        "Authorization": f"Bearer {bearer}",
        "Client-Id": client_id,
    }

    data = http_request(url, headers=headers)

    # Handle 401 by refreshing token and retrying once
    if data.get("status") == 401 or data.get("error") == "Unauthorized":
        print("Twitch Helix: got 401, refreshing token and retrying")
        new_token = refresh_oauth_token()
        if not new_token:
            print("Twitch Helix: token refresh failed")
            return {}
        bearer = new_token[6:] if new_token.startswith("oauth:") else new_token
        headers["Authorization"] = f"Bearer {bearer}"
        data = http_request(url, headers=headers)

    return data


def _helix_patch(endpoint: str, data: dict) -> dict:
    """Make a PATCH request to the Helix API with JSON body, handling 401 with one retry."""
    bearer = get_bearer_token()
    client_id = get_client_id()
    if not bearer or not client_id:
        print("Twitch Helix: missing bearer token or client_id")
        return {}

    url = f"https://api.twitch.tv/helix/{endpoint}"
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Client-Id": client_id,
        "Content-Type": "application/json",
    }
    body = _json.dumps(data)

    result = http_request(url, headers=headers, method="PATCH", data=body)

    if result.get("status") == 401 or result.get("error") == "Unauthorized":
        print("Twitch Helix: got 401 on PATCH, refreshing token and retrying")
        new_token = refresh_oauth_token()
        if not new_token:
            return {}
        bearer = new_token[6:] if new_token.startswith("oauth:") else new_token
        headers["Authorization"] = f"Bearer {bearer}"
        result = http_request(url, headers=headers, method="PATCH", data=body)

    return result


def get_broadcaster_id(channel: str) -> str:
    """Get the numeric broadcaster ID for a channel login name."""
    data = _helix_get("users", {"login": channel})
    users = data.get("data", [])
    return users[0]["id"] if users else ""


def get_channel_title(channel: str) -> str:
    """Get the current stream title (works whether live or offline)."""
    broadcaster_id = get_broadcaster_id(channel)
    if not broadcaster_id:
        return ""
    data = _helix_get("channels", {"broadcaster_id": broadcaster_id})
    channels = data.get("data", [])
    return channels[0].get("title", "") if channels else ""


def set_channel_title(channel: str, title: str) -> bool:
    """Update the stream title via Helix API. Returns True on success."""
    broadcaster_id = get_broadcaster_id(channel)
    if not broadcaster_id:
        return False
    result = _helix_patch(f"channels?broadcaster_id={broadcaster_id}", {"title": title})
    # 204 No Content → http_request returns {} (no JSON body) → success
    return "error" not in result


def get_stream_status(channel: str) -> Optional[StreamStatus]:
    """Get the stream status for a channel. Returns None if offline or on error."""
    data = _helix_get("streams", {"user_login": channel})
    streams = data.get("data", [])
    if not streams:
        return None

    stream = streams[0]
    return StreamStatus(
        is_live=True,
        viewer_count=stream.get("viewer_count", 0),
        title=stream.get("title", ""),
        game_name=stream.get("game_name", ""),
        started_at=stream.get("started_at", ""),
    )
