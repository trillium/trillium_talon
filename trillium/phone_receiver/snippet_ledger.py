"""The snippet idempotency table: utterance id to the ack that was sent for it.

The durable layer behind `ledger.Ledger` (memory only, a ten minute expiry), which owns the id
scheme and the in-flight and replay rules for `/emission` and `/snippet` alike. This one adds the
file-ack semantics: a snippet's retry has to be recognised across a Talon restart and for as long
as the phone keeps the audio. An entry with `"pending": true` is written before the file is, and
replaced by the ack after (see `snippet`).

Pure stdlib, no `talon` import. A retry of an upload the Mac already saved (the phone never saw
the ack) must get the same ack back and write nothing, and that has to survive a Talon restart,
so every entry is appended to a JSON-lines file and fsynced before the ack leaves. The file holds
ids, basenames, sizes, checksums and timings only: no audio, no phrase text, no key. It lives
beside the key (`~/.config/talon-phone/snippets.jsonl`, directory 0700, file 0600), not in the
recordings folder.

Bounded: the newest `capacity` ids are kept in memory and the file is rewritten (temp then
rename) at load when it has grown past twice that, so an id older than the last `capacity`
snippets is forgotten and a late retry of it would be saved again.
"""

import json
import os
import threading
from collections import OrderedDict
from typing import Any

DEFAULT_PATH = os.path.join("~", ".config", "talon-phone", "snippets.jsonl")
DEFAULT_CAPACITY = 10000


class LedgerError(Exception):
    """The entry is in memory but could not be written to disk."""


class SnippetLedger:
    def __init__(
        self, path: str | None = DEFAULT_PATH, capacity: int = DEFAULT_CAPACITY
    ):
        self._path = os.path.abspath(os.path.expanduser(path)) if path else None
        self._capacity = capacity
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lines = 0
        self._loaded = False  # read on first use, so importing the glue touches no disk

    def _load(self) -> None:
        self._loaded = True
        if self._path is None:
            return
        try:
            with open(self._path, encoding="utf-8") as fh:
                for line in fh:
                    self._lines += 1
                    try:
                        row = json.loads(line)
                        self._remember(row["id"], row["ack"])
                    except (ValueError, KeyError, TypeError):
                        continue  # a torn last line from a crash; the rest is still good
        except OSError:
            return  # no file yet
        if self._lines > 2 * self._capacity:
            self._rewrite()

    def _remember(self, key: str, ack: dict[str, Any]) -> None:
        if not isinstance(key, str) or not isinstance(ack, dict):
            raise TypeError("bad row")
        self._entries[key] = ack
        self._entries.move_to_end(key)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    def _rewrite(self) -> None:
        tmp = f"{self._path}.tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for key, ack in self._entries.items():
                    fh.write(_row(key, ack))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
            self._lines = len(self._entries)
        except OSError:
            pass  # compaction is housekeeping; the old file is intact

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            if not self._loaded:
                self._load()
            ack = self._entries.get(key)
            return dict(ack) if ack is not None else None

    def put(self, key: str, ack: dict[str, Any]) -> None:
        """Remember `ack` under `key`. Raises `LedgerError` if it could not reach the disk."""
        with self._lock:
            if not self._loaded:
                self._load()
            self._remember(key, ack)
            if self._path is None:
                return
            try:
                os.makedirs(os.path.dirname(self._path), mode=0o700, exist_ok=True)
                fd = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.write(fd, _row(key, ack).encode("utf-8"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self._lines += 1
            except OSError as exc:
                raise LedgerError("ledger_write_failed") from exc


def _row(key: str, ack: dict[str, Any]) -> str:
    return json.dumps({"id": key, "ack": ack}, separators=(",", ":")) + "\n"
