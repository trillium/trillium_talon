"""The shared secret the phone sends as `X-Talon-Phone-Key` when the listener is on the tailnet.

Pure stdlib, no `talon` import. The secret lives in a 0600 file outside any repo
(`~/.config/talon-phone/key`) and is never printed, logged or put in an error message: every
failure here names the path and the problem, not the content. `python -m
trillium.phone_receiver.keyfile` creates the file if it is missing and prints only its path.
"""

import hashlib
import hmac
import os
import secrets
import stat
import sys

from ..palette_feed.auth import find_repo_root, is_within

KEY_PATH = os.path.join("~", ".config", "talon-phone", "key")
HEADER = "x-talon-phone-key"
MIN_KEY_LEN = 32  # secrets.token_urlsafe(32) is 43 characters
MAX_PRESENTED_LEN = 256


class KeyFileError(Exception):
    """The key file is missing, unsafe or unusable. The listener fails closed."""


def _expand(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _outside_repo(path: str) -> None:
    root = find_repo_root(path)
    if root is not None and is_within(path, root):
        raise KeyFileError(f"key file {path} is inside a git repository ({root})")


def load_key(path: str = KEY_PATH) -> str:
    """Read the key, insisting on a private regular file outside any repo."""
    path = _expand(path)
    _outside_repo(path)
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise KeyFileError(f"cannot stat key file {path}: {exc.strerror}") from exc
    if not stat.S_ISREG(st.st_mode):  # lstat: a symlink is refused, not followed
        raise KeyFileError(f"key path {path} is not a regular file")
    if st.st_mode & 0o077:
        raise KeyFileError(
            f"key file {path} must not be group/world accessible (chmod 600)"
        )
    if st.st_uid != os.getuid():
        raise KeyFileError(f"key file {path} is not owned by the current user")
    try:
        with open(path, encoding="utf-8") as fh:
            key = fh.read().strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise KeyFileError(f"cannot read key file {path}") from exc
    if len(key) < MIN_KEY_LEN:
        raise KeyFileError(f"key in {path} is shorter than {MIN_KEY_LEN} characters")
    return key


def ensure_key(path: str = KEY_PATH) -> str:
    """Create the key file if it is missing (0600, directory 0700), then load it.

    An existing file is never overwritten, so a key the phone already holds survives.
    """
    path = _expand(path)
    _outside_repo(path)
    if not os.path.lexists(path):
        directory = os.path.dirname(path)
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass  # lost a race with another creator; load whatever won
        except OSError as exc:
            raise KeyFileError(
                f"cannot create key file {path}: {exc.strerror}"
            ) from exc
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(secrets.token_urlsafe(32) + "\n")
    return load_key(path)


def matches(presented: object, key: str) -> bool:
    """Constant-time check of a presented header value against `key`.

    Both sides are hashed first so the comparison time depends on neither the content nor
    the length of what the caller sent.
    """
    if (
        not isinstance(presented, str)
        or not presented
        or len(presented) > MAX_PRESENTED_LEN
        or len(key) < MIN_KEY_LEN
    ):
        return False
    a = hashlib.sha256(presented.encode("utf-8", "surrogatepass")).digest()
    b = hashlib.sha256(key.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


def main(argv: list[str] | None = None) -> int:
    path = _expand((argv or sys.argv[1:] or [KEY_PATH])[0])
    try:
        ensure_key(path)
    except KeyFileError as exc:
        print(f"phone key: {exc}", file=sys.stderr)
        return 1
    print(path)  # the path only; read the key from the file when pairing the phone
    return 0


if __name__ == "__main__":
    sys.exit(main())
