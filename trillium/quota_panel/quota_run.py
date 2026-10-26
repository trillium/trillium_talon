"""Non-blocking `quota-axi --json` runner, driven by a cron tick.

Pure Python, no talon import. The child's stdout goes to a temp file (a full
pipe cannot deadlock it); `tick()` only polls, so nothing here waits on
quota-axi. No Python thread is started. A run still going after `timeout`
seconds is killed (quota-axi may call a vendor CLI to renew a session; that
must never hold the panel). Same shape as herdr_links.links_scan.ScanRunner.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

from ..herdr_links.links_scan import find_tool, scan_env

QUOTA_TIMEOUT = 25.0  # uncached worst case seen: 5.5s
MAX_AGE = "60s"  # quota-axi reuses a reading younger than this


def quota_argv(tool, providers, max_age=MAX_AGE):
    """argv for one read. No --full: that adds account identity."""
    return [
        tool,
        "--json",
        "--provider",
        ",".join(providers),
        "--max-age",
        max_age,
    ]


class Result:
    __slots__ = ("data", "error")

    def __init__(self, data=None, error=None):
        self.data, self.error = data, error


class QuotaRunner:
    def __init__(
        self,
        tool=None,
        popen=subprocess.Popen,
        clock=time.monotonic,
        timeout=QUOTA_TIMEOUT,
        tmp_dir=None,
    ):
        self.tool = tool or find_tool("quota-axi")
        self._popen = popen
        self._clock = clock
        self.timeout = timeout
        self._tmp_dir = tmp_dir
        self.current = None  # (proc, out_path, started)

    @property
    def busy(self):
        return self.current is not None

    def start(self, providers):
        """Launch one read unless one is running. Returns a failed Result if it
        could not start, else None."""
        if self.current:
            return None
        fd, out_path = tempfile.mkstemp(
            prefix="talon-quota-", suffix=".json", dir=self._tmp_dir
        )
        os.close(fd)
        try:
            with open(out_path, "w") as out:
                proc = self._popen(
                    quota_argv(self.tool, providers),
                    stdout=out,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    env=scan_env(),
                )
        except Exception as e:
            _unlink(out_path)
            return Result(error=f"could not start quota-axi: {e}")
        self.current = (proc, out_path, self._clock())
        return None

    def _finish(self):
        proc, out_path, _ = self.current
        self.current = None
        try:
            with open(out_path) as f:
                raw = f.read()
        except OSError as e:
            _unlink(out_path)
            return Result(error=str(e))
        _unlink(out_path)
        try:
            data = json.loads(raw)
        except ValueError:
            return Result(error=f"quota-axi exited {proc.returncode} with no JSON")
        if not isinstance(data, dict) or not isinstance(data.get("providers"), list):
            return Result(error="quota-axi JSON has no providers")
        return Result(data=data)

    def _kill(self):
        proc, out_path, _ = self.current
        self.current = None
        try:
            proc.kill()
            proc.poll()  # reap if already gone; subprocess reaps stragglers later
        except Exception:
            pass
        _unlink(out_path)
        return Result(error=f"quota-axi timed out after {self.timeout:.0f}s")

    def tick(self):
        """Poll the running read. Returns a Result when one finished, else None.
        Never raises, never blocks on the child."""
        try:
            if self.current:
                proc, _, started = self.current
                if proc.poll() is not None:
                    return self._finish()
                if self._clock() - started > self.timeout:
                    return self._kill()
        except Exception as e:
            print(f"[quota_panel] tick failed: {e}")
        return None


def _unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass
