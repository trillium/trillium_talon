"""Bearer-token auth. Pure stdlib so it unit-tests without Talon."""

import hmac
import os
import stat

MIN_TOKEN_LEN = 32  # secrets.token_urlsafe(32) is 43 chars


class TokenError(Exception):
    """The token file is missing, unsafe, or unusable. Fail closed."""


def load_token(path: str) -> str:
    """Read the token from `path`, insisting on a private regular file."""
    try:
        st = os.stat(path)
    except OSError as exc:
        raise TokenError(f"cannot stat token file {path}: {exc.strerror}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise TokenError(f"token path {path} is not a regular file")
    if st.st_mode & 0o077:
        raise TokenError(
            f"token file {path} must not be group/world accessible (chmod 600)"
        )
    with open(path, encoding="utf-8") as fh:
        token = fh.read().strip()
    if len(token) < MIN_TOKEN_LEN:
        raise TokenError(f"token in {path} is shorter than {MIN_TOKEN_LEN} characters")
    return token


def is_within(path: str, root: str) -> bool:
    """True if `path` resolves inside `root` (used to keep the token out of the repo)."""
    real_path = os.path.realpath(path)
    real_root = os.path.realpath(root)
    return os.path.commonpath([real_path, real_root]) == real_root


def find_repo_root(start: str) -> str | None:
    """Nearest ancestor of `start` holding a `.git` (dir or worktree file), else None."""
    current = os.path.dirname(os.path.realpath(start))
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def extract_bearer(header: str | None) -> str | None:
    """Return the credential from an `Authorization: Bearer ...` header, else None."""
    if not header:
        return None
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer" or not credential.strip():
        return None
    return credential.strip()


def is_authorized(header: str | None, token: str) -> bool:
    """Constant-time check of the Authorization header against the token."""
    presented = extract_bearer(header)
    if presented is None:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), token.encode("utf-8"))
