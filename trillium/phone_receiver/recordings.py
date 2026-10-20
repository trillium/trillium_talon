"""Writing a new snippet file into Talon's recordings folder, and nothing else there.

Pure stdlib, no `talon` import: the folder comes from a callable the glue supplies
(`actions.path.talon_home() / "recordings"`, the same place Talon's `speech.record_all` writes
and `core/system_paths.py` names), never a literal here.

The captain authorized exactly one action in that folder, and this module is that action:
create new files. So it never lists the folder, never opens an existing entry, never reads,
copies, moves, renames or deletes one, and never overwrites. A write is temp, fsync, then a hard
link to the final name (which fails if the name is taken, so a collision draws a new name rather
than replacing a file), then the temp name is removed (our own `.phone-snippet-*.tmp`, the only
thing this module ever unlinks) and the folder is fsynced. Once `save` returns, the file is
durable under its final name and `Saved.size` is what `stat` reports for it; the content is not
read back.

One more thing touches the folder, and only for a name this module itself reserved: `confirm`
stats that one path (its size, nothing else; it is never opened) and fsyncs the folder. The
service writes a pending ledger entry naming the file before `save`, so a crash or a failed
folder fsync after the link leaves a record, and the retry `confirm`s that file instead of
saving a second copy.

Naming follows Talon's own files, `<phrase>-<8 random letters or digits>.flac`, with the fixed
phrase `phone-snippet`. A real phrase is words separated by spaces and never contains a hyphen,
so `phone-snippet` cannot be a spoken command and the files are told apart by name alone.
"""

import errno
import os
import re
import secrets
import string
from dataclasses import dataclass
from typing import Callable

PREFIX = "phone-snippet"
EXT = ".flac"
SUFFIX_LEN = 8
ALPHABET = string.ascii_letters + string.digits
TMP_PREFIX = ".phone-snippet-"
TMP_EXT = ".tmp"
MAX_ATTEMPTS = 16
FILE_MODE = 0o644
# `link` unsupported on the volume: fall back to a guarded rename
_NO_LINK = (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV, errno.ENOSYS)
_NAME = re.compile(rf"{PREFIX}-[A-Za-z0-9]{{{SUFFIX_LEN}}}{re.escape(EXT)}")


class SaveError(Exception):
    """The file was not written. `code` is the stable error code; the folder is unchanged."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Saved:
    name: str  # the basename only, never the directory
    size: int


def random_suffix() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(SUFFIX_LEN))


def final_name(suffix: str) -> str:
    return f"{PREFIX}-{suffix}{EXT}"


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def _fsync_dir(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class RecordingsWriter:
    def __init__(
        self,
        get_dir: Callable[[], str | None],
        suffix: Callable[[], str] = random_suffix,
    ):
        self._get_dir = get_dir
        self._suffix = suffix

    def _folder(self) -> str:
        folder = self._get_dir()
        if not isinstance(folder, str) or not folder:
            raise SaveError("no_recordings_dir")
        # An existing, writable folder only: creating Talon's own folder is Talon's business.
        if not os.path.isdir(folder) or not os.access(folder, os.W_OK | os.X_OK):
            raise SaveError("no_recordings_dir")
        return folder

    def reserve(self) -> str:
        """A final name to try first. Nothing is created or checked: `save` still never replaces."""
        return final_name(self._suffix())

    def confirm(self, name: str) -> int | None:
        """Size of the file `name` if it exists, after fsyncing the folder; None if it does not.

        Only for a name this module handed out (`reserve`/`save`); anything else is refused. One
        `stat` of that path and the folder fsync: the file is not opened and its content is not
        read. `SaveError` when the folder cannot be fsynced (not durable, so no ack).
        """
        if not _NAME.fullmatch(name):
            return None
        folder = self._folder()
        try:
            size = os.stat(os.path.join(folder, name)).st_size
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SaveError("save_failed") from exc
        try:
            _fsync_dir(folder)
        except OSError as exc:
            raise SaveError("save_failed") from exc
        return size

    def save(self, data: bytes, first: str | None = None) -> Saved:
        """Write `data` as a new `phone-snippet-<8>.flac`, trying the name `first` before others.

        `SaveError` before the rename leaves no file. After it (the folder fsync or the size
        check failed) the file exists but is not confirmed durable, so the caller must not ack.
        """
        folder = self._folder()
        tmp = os.path.join(folder, f"{TMP_PREFIX}{self._suffix()}{TMP_EXT}")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        except OSError as exc:
            raise SaveError("save_failed") from exc
        try:
            try:
                _write_all(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            name = self._publish(folder, tmp, first)
            _fsync_dir(folder)
            size = os.stat(os.path.join(folder, name)).st_size
        except SaveError:
            raise
        except OSError as exc:
            raise SaveError("save_failed") from exc
        finally:
            try:
                os.unlink(
                    tmp
                )  # our own temp name, present only if it was not renamed away
            except OSError:
                pass
        if size != len(data):
            raise SaveError("save_failed")
        return Saved(name, size)

    def _publish(self, folder: str, tmp: str, first: str | None = None) -> str:
        """Give `tmp` a final name no existing file has. Never replaces anything."""
        for attempt in range(MAX_ATTEMPTS):
            name = (
                first
                if attempt == 0 and first is not None and _NAME.fullmatch(first)
                else final_name(self._suffix())
            )
            final = os.path.join(folder, name)
            try:
                os.link(tmp, final)
                return name
            except FileExistsError:
                continue  # taken: draw another name
            except OSError as exc:
                if exc.errno not in _NO_LINK:
                    raise
            # No hard links here: rename, after checking the name is free. The window between
            # the check and the rename is one 62**8 name wide and only this writer uses the name.
            if os.path.lexists(final):
                continue
            os.rename(tmp, final)
            return name
        raise SaveError("save_failed")
