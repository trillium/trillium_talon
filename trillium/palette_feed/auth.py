"""Bearer-token auth. Pure stdlib so it unit-tests without Talon."""

import hmac
import os
import stat
from dataclasses import dataclass

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


@dataclass(frozen=True)
class TokenPlan:
    """What the feed does about the bearer token.

    `token is None` means no credential is configured, so `/execute` answers 401 and
    is effectively disabled. `fatal` means do not start the server at all.
    """

    token: str | None
    fatal: bool
    message: str


def plan_token(path: str, repo_root: str | None, open_reads: bool) -> TokenPlan:
    """Decide the token from `path`, given whether reads are open.

    A token inside the repo is always fatal, whichever endpoints need it: it is one
    commit away from leaking. Otherwise an unusable token is fatal only while reads are
    authenticated; with reads open the feed still starts and only `/execute` is disabled.
    """
    if repo_root is not None and is_within(path, repo_root):
        return TokenPlan(None, True, f"refusing token file inside the repo: {path}")
    try:
        token = load_token(path)
    except TokenError as exc:
        if open_reads:
            return TokenPlan(
                None,
                False,
                f"no usable token ({exc}); reads are open, /execute disabled",
            )
        return TokenPlan(None, True, f"not starting: {exc}")
    return TokenPlan(token, False, "token loaded")


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
