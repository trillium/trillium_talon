"""Twitch IRC chat client.

Connects to Twitch IRC on app ready, maintains a buffer of recent messages,
and exposes callbacks for consumers (e.g. HUD bridge) to receive messages.
"""
from talon import app, settings
import socket
import ssl
import threading
import time
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

_PRIVMSG_RE = re.compile(
    r"(?:@\S+ )?:(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.+)"
)


@dataclass
class ChatMessage:
    username: str
    text: str
    timestamp: float = field(default_factory=time.time)


MessageCallback = Callable[[ChatMessage], None]


class TwitchChatClient:
    """Standalone Twitch IRC client with message buffer and callbacks."""

    def __init__(self, max_buffer: int = 200):
        self.messages: deque[ChatMessage] = deque(maxlen=max_buffer)
        self._callbacks: list[MessageCallback] = []
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.connected = False

    def on_message(self, callback: MessageCallback):
        """Register a callback for incoming messages."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: MessageCallback):
        """Remove a previously registered callback."""
        self._callbacks = [cb for cb in self._callbacks if cb is not callback]

    def start(self):
        """Start the IRC connection in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Disconnect and stop the background thread."""
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                print("Twitch IRC: error closing socket during stop")
        self._sock = None
        self.connected = False

    def _get_token(self) -> str:
        from user.trillium_talon.trillium.plugin.twitch.twitch_auth import get_oauth_token
        return get_oauth_token()

    def _send(self, msg: str):
        self._sock.send(f"{msg}\r\n".encode("utf-8"))

    def _read_until_welcome(self, timeout: float = 10.0) -> bool:
        """Read server responses after auth, return True if we get 001 (welcome)."""
        self._sock.settimeout(timeout)
        buf = ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data = self._sock.recv(4096).decode("utf-8", errors="replace")
                if not data:
                    return False
                buf += data
                while "\r\n" in buf:
                    line, buf = buf.split("\r\n", 1)
                    if line.startswith("PING"):
                        try:
                            self._send(f"PONG{line[4:]}")
                        except Exception:
                            print("Twitch IRC: error sending PONG during welcome")
                    elif "Login authentication failed" in line or "Improperly formatted auth" in line:
                        print(f"Twitch IRC: auth failed: {line}")
                        return False
                    elif " 001 " in line:
                        return True
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Twitch IRC: error reading welcome: {e}")
                return False
        print("Twitch IRC: timed out waiting for welcome")
        return False

    def _connect(self, channel: str, token: str, username: str) -> bool:
        raw_sock = None
        try:
            raw_sock = socket.socket()
            ctx = ssl.create_default_context()
            for ca_path in ["/etc/ssl/cert.pem", "/opt/homebrew/etc/openssl@3/cert.pem"]:
                try:
                    ctx.load_verify_locations(ca_path)
                    break
                except Exception:
                    continue
            self._sock = ctx.wrap_socket(raw_sock, server_hostname="irc.chat.twitch.tv")
            self._sock.settimeout(10.0)
            self._sock.connect(("irc.chat.twitch.tv", 6697))
            self._send("CAP REQ :twitch.tv/membership twitch.tv/tags twitch.tv/commands")
            self._send(f"PASS {token}")
            self._send(f"NICK {username}")
            if not self._read_until_welcome():
                self._sock.close()
                self._sock = None
                return False
            self._send(f"JOIN #{channel}")
            self._sock.settimeout(5.0)
            print(f"Twitch IRC: connected to #{channel}")
            return True
        except Exception as e:
            print(f"Twitch IRC: connection failed: {e}")
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    print("Twitch IRC: error closing socket after failed connect")
                self._sock = None
            elif raw_sock:
                try:
                    raw_sock.close()
                except Exception:
                    print("Twitch IRC: error closing raw socket after failed connect")
            return False

    def _run(self):
        channel = settings.get("user.twitch_channel")
        username = settings.get("user.twitch_bot_username")

        if not channel or not username:
            print(f"Twitch IRC: missing config (channel={channel!r}, username={username!r})")
            return

        backoff = 5
        max_backoff = 120

        while not self._stop_event.is_set():
            token = self._get_token()
            if not token:
                print("Twitch IRC: no token available, retrying...")
                self._stop_event.wait(backoff)
                continue

            if not self._connect(channel, token, username):
                print("Twitch IRC: connect failed, refreshing token...")
                from user.trillium_talon.trillium.plugin.twitch.twitch_auth import refresh_oauth_token
                token = refresh_oauth_token()
                if not token or not self._connect(channel, token, username):
                    print(f"Twitch IRC: reconnect failed, retrying in {backoff}s")
                    self._stop_event.wait(backoff)
                    backoff = min(backoff * 2, max_backoff)
                    continue

            self.connected = True
            backoff = 5  # Reset on successful connect
            buf = ""
            while not self._stop_event.is_set():
                try:
                    data = self._sock.recv(4096).decode("utf-8", errors="replace")
                    if not data:
                        print("Twitch IRC: server closed connection")
                        break
                    buf += data
                    while "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                        self._handle_line(line)
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Twitch IRC: recv error: {e}")
                    break

            self.connected = False
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

            if not self._stop_event.is_set():
                print(f"Twitch IRC: disconnected, reconnecting in {backoff}s")
                self._stop_event.wait(backoff)

    def _handle_line(self, line: str):
        if line.startswith("PING") or (line.startswith(":") and "PING" not in line and line.endswith("PING")):
            try:
                self._send(f"PONG{line[4:]}")
            except Exception:
                print("Twitch IRC: error sending PONG")
            return

        if "PING" in line and line.startswith("PING"):
            try:
                self._send(f"PONG{line[4:]}")
            except Exception:
                print("Twitch IRC: error sending PONG")
            return

        if "Login authentication failed" in line:
            print("Twitch IRC: auth failed mid-session, refreshing token")
            from user.trillium_talon.trillium.plugin.twitch.twitch_auth import refresh_oauth_token
            token = refresh_oauth_token()
            if token:
                self._stop_event.set()
            return

        match = _PRIVMSG_RE.match(line)
        if match:
            msg = ChatMessage(
                username=match.group(1),
                text=match.group(2).strip(),
            )
            self.messages.append(msg)
            for cb in self._callbacks:
                try:
                    cb(msg)
                except Exception as e:
                    print(f"Twitch IRC: callback error: {e}")


# Stop any previous instance from a prior reload
_previous_client = None
try:
    import sys
    _prev_mod = sys.modules.get(__name__)
    if _prev_mod and hasattr(_prev_mod, 'client'):
        _previous_client = _prev_mod.client
        _previous_client.stop()
        print("Twitch IRC: stopped previous client instance on reload")
except Exception:
    pass

# Module-level singleton
client = TwitchChatClient()


def on_ready():
    client.start()

app.register("ready", on_ready)
