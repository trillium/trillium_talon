"""Twitch authentication helpers: keychain access, OAuth token management, HTTP requests."""
import json
import subprocess

_KEYCHAIN_ACCOUNT = "talon_chat_assistant"


def keychain_get(service: str) -> str:
    """Read a value from macOS keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", _KEYCHAIN_ACCOUNT, "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def keychain_set(service: str, value: str):
    """Write a value to macOS keychain (delete then add)."""
    subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", _KEYCHAIN_ACCOUNT],
        capture_output=True,
    )
    subprocess.run(
        ["security", "add-generic-password", "-a", _KEYCHAIN_ACCOUNT, "-s", service, "-w", value],
        capture_output=True,
    )


def refresh_oauth_token() -> str:
    """Refresh the Twitch OAuth token via curl. Returns 'oauth:{token}' or empty string."""
    client_id = keychain_get("twitch_client_id")
    client_secret = keychain_get("twitch_client_secret")
    refresh_token = keychain_get("twitch_refresh_token")
    if not client_id or not client_secret or not refresh_token:
        return ""
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://id.twitch.tv/oauth2/token",
         "-d", f"client_id={client_id}",
         "-d", f"client_secret={client_secret}",
         "-d", f"refresh_token={refresh_token}",
         "-d", "grant_type=refresh_token"],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(result.stdout)
        access_token = data["access_token"]
        new_refresh = data.get("refresh_token", refresh_token)
        keychain_set("twitch_oauth_token", f"oauth:{access_token}")
        keychain_set("twitch_refresh_token", new_refresh)
        return f"oauth:{access_token}"
    except Exception as e:
        print(f"Twitch: token refresh failed: {e}")
        return ""


def get_oauth_token() -> str:
    """Get the current OAuth token (oauth:xxx format), refreshing if needed."""
    token = keychain_get("twitch_oauth_token")
    if not token:
        token = refresh_oauth_token()
    return token


def get_bearer_token() -> str:
    """Get the bearer token (no oauth: prefix) for Helix API calls."""
    token = get_oauth_token()
    if token.startswith("oauth:"):
        return token[6:]
    return token


def get_client_id() -> str:
    """Read the Twitch client ID from keychain."""
    return keychain_get("twitch_client_id")


def http_request(url: str, headers: dict = None, method: str = "GET", data: str = None) -> dict:
    """Make an HTTP request via curl subprocess and return parsed JSON."""
    cmd = ["curl", "-s", "-X", method]
    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
    if data:
        cmd.extend(["-d", data])
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Twitch: http_request parse error for {url}: {e}")
        return {}
