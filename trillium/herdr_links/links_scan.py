"""Non-blocking `herdr-links --json` runner, driven by a cron tick.

Pure Python, no talon import. One scan runs at a time as a child process
whose stdout goes to a temp file (a full pipe cannot deadlock it); `tick()`
only polls, so nothing here ever waits on herdr. No Python thread is started.
A scan still running after `timeout` seconds is killed (herdr-links' own
herdr calls are bounded too, but a dead ssh leg must not hold the queue).
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

SCAN_TIMEOUT = 15.0
# Talon's environment may lack the user's shell PATH; herdr-links needs
# python3 and herdr, and lives in ~/.local/bin.
EXTRA_PATH = [
    str(Path.home() / ".local" / "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]


def scan_env():
    env = dict(os.environ)
    parts = env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join(parts + [p for p in EXTRA_PATH if p not in parts])
    return env


def find_tool(name, env=None):
    """Absolute path to `name` on the extended PATH, else the bare name."""
    return shutil.which(name, path=(env or scan_env())["PATH"]) or name


def scan_argv(tool, host, tab_id):
    """argv for one tab's scan; a remote host goes through `--machine`
    (herdr-links accepts a herdr machine label, id or ssh target)."""
    argv = [tool, "--json", "--tab", tab_id]
    if host:
        argv += ["--machine", host]
    return argv


class Job:
    """One tab to scan. `label` is the tab's display label at enqueue time."""

    __slots__ = ("host", "tab_id", "label")

    def __init__(self, host, tab_id, label=""):
        self.host, self.tab_id, self.label = host or "", tab_id, label

    @property
    def key(self):
        return (self.host, self.tab_id)


class Result:
    __slots__ = ("job", "data", "error")

    def __init__(self, job, data=None, error=None):
        self.job, self.data, self.error = job, data, error


class ScanRunner:
    def __init__(
        self,
        tool="herdr-links",
        popen=subprocess.Popen,
        clock=time.monotonic,
        timeout=SCAN_TIMEOUT,
        tmp_dir=None,
    ):
        self.tool = tool
        self._popen = popen
        self._clock = clock
        self.timeout = timeout
        self._tmp_dir = tmp_dir
        self.queue = []
        self.current = None  # (job, proc, out_path, started)

    @property
    def busy(self):
        return self.current is not None

    def pending(self, key):
        """True if this tab is queued or scanning now."""
        if self.current and self.current[0].key == key:
            return True
        return any(j.key == key for j in self.queue)

    def enqueue(self, job, front=False):
        """Queue a scan unless that tab is already queued or running.
        front=True moves an already-queued tab to the head."""
        if self.current and self.current[0].key == job.key:
            return
        existing = [j for j in self.queue if j.key == job.key]
        if existing and not front:
            return
        self.queue = [j for j in self.queue if j.key != job.key]
        if front:
            self.queue.insert(0, job)
        else:
            self.queue.append(job)

    def _start(self, job):
        fd, out_path = tempfile.mkstemp(
            prefix="talon-links-", suffix=".json", dir=self._tmp_dir
        )
        os.close(fd)
        try:
            with open(out_path, "w") as out:
                proc = self._popen(
                    scan_argv(self.tool, job.host, job.tab_id),
                    stdout=out,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    env=scan_env(),
                )
        except Exception as e:
            _unlink(out_path)
            return Result(job, error=f"could not start herdr-links: {e}")
        self.current = (job, proc, out_path, self._clock())
        return None

    def _finish(self):
        job, proc, out_path, started = self.current
        self.current = None
        try:
            with open(out_path) as f:
                raw = f.read()
        except OSError as e:
            raw, err = "", str(e)
        else:
            err = None
        _unlink(out_path)
        if err:
            return Result(job, error=err)
        try:
            data = json.loads(raw)
        except ValueError:
            return Result(
                job, error=f"herdr-links exited {proc.returncode} with no JSON"
            )
        if isinstance(data, dict) and data.get("error"):
            detail = data.get("detail") or ""
            return Result(job, error=f"{data['error']} {detail}".strip())
        return Result(job, data=data)

    def _kill(self):
        job, proc, out_path, started = self.current
        self.current = None
        try:
            proc.kill()
            proc.poll()  # reap if already gone; subprocess reaps stragglers later
        except Exception:
            pass
        _unlink(out_path)
        return Result(job, error=f"scan timed out after {self.timeout:.0f}s")

    def tick(self):
        """Poll the running scan, start the next queued one. Returns finished
        Results (usually 0 or 1). Never raises, never blocks on the child."""
        results = []
        try:
            if self.current:
                job, proc, _, started = self.current
                if proc.poll() is not None:
                    results.append(self._finish())
                elif self._clock() - started > self.timeout:
                    results.append(self._kill())
            while not self.current and self.queue:
                failed = self._start(self.queue.pop(0))
                if failed is None:
                    break
                results.append(failed)
        except Exception as e:
            print(f"[herdr_links] tick failed: {e}")
        return results


def _unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass
