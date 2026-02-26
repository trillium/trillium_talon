#!/usr/bin/env python3
"""Talon user directory snapshot, diff, and reconciliation tool.

Captures the complete state of ~/.talon/user/ across machines,
compares snapshots, and produces agent-friendly reconciliation instructions.

Zero external dependencies — stdlib only.
"""

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_TALON_USER = os.path.expanduser("~/.talon/user")
HASH_SIZE_LIMIT = 10 * 1024 * 1024  # 10MB — skip sha256 for files larger than this


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: str) -> tuple[int, str]:
    """Run a git command, return (returncode, stdout stripped)."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip()


def snapshot_git_repo(dir_path: str) -> dict:
    """Capture full git state for a repository."""
    git = {}

    # Remotes
    rc, out = _git(["remote", "-v"], dir_path)
    remotes = {}
    if rc == 0:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and "(fetch)" in line:
                remotes[parts[0]] = parts[1]
    git["remotes"] = remotes

    # Current branch
    rc, out = _git(["branch", "--show-current"], dir_path)
    git["branch"] = out if rc == 0 and out else None

    # HEAD SHA
    rc, out = _git(["rev-parse", "HEAD"], dir_path)
    git["head_sha"] = out if rc == 0 else None

    # Tracking branch
    rc, out = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], dir_path)
    git["tracking"] = out if rc == 0 and out else None

    # Ahead/behind
    if git["tracking"]:
        rc, out = _git(["rev-list", f"{git['tracking']}..HEAD", "--count"], dir_path)
        git["ahead"] = int(out) if rc == 0 and out.isdigit() else None
        rc, out = _git(["rev-list", f"HEAD..{git['tracking']}", "--count"], dir_path)
        git["behind"] = int(out) if rc == 0 and out.isdigit() else None
    else:
        git["ahead"] = None
        git["behind"] = None

    # Status (dirty + untracked)
    # NOTE: Don't use _git() here — its .strip() eats the leading space
    # from porcelain output (e.g. " M src/foo.py" becomes "M src/foo.py")
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=dir_path, capture_output=True, text=True,
    )
    dirty_files = []
    untracked_files = []
    if porcelain.returncode == 0 and porcelain.stdout:
        for line in porcelain.stdout.splitlines():
            if line.startswith("?? "):
                untracked_files.append(line[3:])
            elif line.strip():
                status = line[:2].strip()
                path = line[3:]
                dirty_files.append({"status": status, "path": path})
    git["dirty_files"] = dirty_files
    git["untracked_files"] = untracked_files

    # Stash count
    rc, out = _git(["stash", "list"], dir_path)
    git["stash_count"] = len(out.splitlines()) if rc == 0 and out else 0

    # Submodules (look for .gitmodules recursively)
    submodules = []
    for root, dirs, files in os.walk(dir_path):
        # Skip .git directories
        dirs[:] = [d for d in dirs if d != ".git"]
        if ".gitmodules" in files:
            rel_root = os.path.relpath(root, dir_path)
            if rel_root == ".":
                rel_root = ""
            modules_path = os.path.join(root, ".gitmodules")
            nested = _parse_gitmodules(modules_path)
            if nested:
                entry = {"path": rel_root if rel_root else "(root)"}
                if rel_root:
                    entry["nested_submodules"] = nested
                else:
                    entry["submodules"] = nested
                submodules.append(entry)
    git["submodules"] = submodules

    return git


def _parse_gitmodules(path: str) -> list[dict]:
    """Parse a .gitmodules file into a list of {name, path, url}."""
    modules = []
    current = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                m = re.match(r'\[submodule "(.+)"\]', line)
                if m:
                    if current:
                        modules.append(current)
                    current = {"name": m.group(1)}
                elif "=" in line and current:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if key in ("path", "url"):
                        current[key] = val
        if current:
            modules.append(current)
    except OSError:
        pass
    return modules


# ---------------------------------------------------------------------------
# Plain directory helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: str) -> str | None:
    """Compute sha256 hex digest of a file, or None if too large."""
    try:
        size = os.path.getsize(path)
        if size > HASH_SIZE_LIMIT:
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def snapshot_plain_dir(dir_path: str) -> list[dict]:
    """Capture file listing with sizes, mtimes, and hashes for a non-git directory."""
    files = []
    for root, dirs, filenames in os.walk(dir_path):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, dir_path)
            try:
                st = os.stat(full)
                entry = {
                    "path": rel,
                    "size": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                }
                sha = _sha256_file(full)
                if sha:
                    entry["sha256"] = sha
                files.append(entry)
            except OSError:
                continue
    files.sort(key=lambda f: f["path"])
    return files


# ---------------------------------------------------------------------------
# Hostname file scanner
# ---------------------------------------------------------------------------

def find_hostname_files(talon_user_path: str) -> list[dict]:
    """Scan .talon and .talon-list files for hostname: context matchers."""
    results = []
    hostname_re = re.compile(r"^hostname:\s*(.+)$", re.MULTILINE)

    for root, dirs, files in os.walk(talon_user_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if not (name.endswith(".talon") or name.endswith(".talon-list")):
                continue
            full = os.path.join(root, name)
            try:
                with open(full) as f:
                    content = f.read()
                matches = hostname_re.findall(content)
                if matches:
                    rel = os.path.relpath(full, talon_user_path)
                    results.append({
                        "path": rel,
                        "hostnames_referenced": [m.strip() for m in matches],
                    })
            except OSError:
                continue

    results.sort(key=lambda r: r["path"])
    return results


# ---------------------------------------------------------------------------
# Snapshot orchestrator
# ---------------------------------------------------------------------------

def create_snapshot(talon_user_path: str) -> dict:
    """Create a full snapshot of the Talon user directory."""
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "hostname": socket.gethostname(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "talon_user_path": talon_user_path,
        "directories": {},
    }

    for entry in sorted(os.listdir(talon_user_path)):
        full = os.path.join(talon_user_path, entry)
        if not os.path.isdir(full):
            continue
        if entry.startswith("."):
            continue

        git_dir = os.path.join(full, ".git")
        if os.path.isdir(git_dir) or os.path.isfile(git_dir):
            snapshot["directories"][entry] = {
                "type": "git",
                "git": snapshot_git_repo(full),
            }
        else:
            snapshot["directories"][entry] = {
                "type": "plain",
                "files": snapshot_plain_dir(full),
            }

    snapshot["hostname_files"] = find_hostname_files(talon_user_path)
    return snapshot


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def compute_diff(snap_a: dict, snap_b: dict) -> dict:
    """Compare two snapshots and produce a structured diff."""
    dirs_a = set(snap_a["directories"].keys())
    dirs_b = set(snap_b["directories"].keys())

    diff = {
        "schema_version": SCHEMA_VERSION,
        "compared": {
            "a": {"hostname": snap_a["hostname"], "timestamp": snap_a["timestamp"]},
            "b": {"hostname": snap_b["hostname"], "timestamp": snap_b["timestamp"]},
        },
        "only_in_a": sorted(dirs_a - dirs_b),
        "only_in_b": sorted(dirs_b - dirs_a),
        "directories": {},
    }

    # Add detail for dirs only on one side
    diff["only_in_a_detail"] = {
        name: _summarize_dir(snap_a["directories"][name])
        for name in diff["only_in_a"]
    }
    diff["only_in_b_detail"] = {
        name: _summarize_dir(snap_b["directories"][name])
        for name in diff["only_in_b"]
    }

    for name in sorted(dirs_a & dirs_b):
        da = snap_a["directories"][name]
        db = snap_b["directories"][name]

        entry = {
            "presence": "both",
            "type_a": da["type"],
            "type_b": db["type"],
            "type_match": da["type"] == db["type"],
        }

        if da["type"] == "git" and db["type"] == "git":
            entry["git_diff"] = _diff_git(da["git"], db["git"])
        elif da["type"] == "plain" and db["type"] == "plain":
            entry["plain_diff"] = _diff_plain(da["files"], db["files"])
        # If types don't match, the type_match=false flag is enough

        diff["directories"][name] = entry

    # Hostname file analysis
    hostnames_a = set()
    hostnames_b = set()
    for hf in snap_a.get("hostname_files", []):
        for h in hf["hostnames_referenced"]:
            hostnames_a.add(h)
    for hf in snap_b.get("hostname_files", []):
        for h in hf["hostnames_referenced"]:
            hostnames_b.add(h)

    diff["hostname_analysis"] = {
        "hostnames_found_a": sorted(hostnames_a),
        "hostnames_found_b": sorted(hostnames_b),
        "hostname_files_a": snap_a.get("hostname_files", []),
        "hostname_files_b": snap_b.get("hostname_files", []),
    }

    return diff


def _summarize_dir(d: dict) -> dict:
    """Summarize a directory entry for the only_in_X sections."""
    summary = {"type": d["type"]}
    if d["type"] == "git":
        g = d["git"]
        summary["branch"] = g.get("branch")
        summary["head_sha"] = g.get("head_sha")
        summary["remotes"] = g.get("remotes", {})
    elif d["type"] == "plain":
        summary["file_count"] = len(d.get("files", []))
    return summary


def _diff_git(ga: dict, gb: dict) -> dict:
    """Diff two git repo snapshots."""
    d = {}

    d["branch"] = {
        "a": ga["branch"], "b": gb["branch"],
        "match": ga["branch"] == gb["branch"],
    }
    d["head_sha"] = {
        "a": ga["head_sha"], "b": gb["head_sha"],
        "match": ga["head_sha"] == gb["head_sha"],
    }

    # Remotes
    d["remotes_match"] = ga.get("remotes") == gb.get("remotes")
    if not d["remotes_match"]:
        d["remotes_a"] = ga.get("remotes", {})
        d["remotes_b"] = gb.get("remotes", {})

    # Tracking
    d["tracking"] = {
        "a": ga.get("tracking"),
        "b": gb.get("tracking"),
    }
    d["ahead"] = {"a": ga.get("ahead"), "b": gb.get("ahead")}
    d["behind"] = {"a": ga.get("behind"), "b": gb.get("behind")}

    # Dirty files
    dirty_a = {f["path"] for f in ga.get("dirty_files", [])}
    dirty_b = {f["path"] for f in gb.get("dirty_files", [])}
    d["dirty_a_only"] = sorted(dirty_a - dirty_b)
    d["dirty_b_only"] = sorted(dirty_b - dirty_a)
    d["dirty_both"] = sorted(dirty_a & dirty_b)

    # Untracked
    untracked_a = set(ga.get("untracked_files", []))
    untracked_b = set(gb.get("untracked_files", []))
    d["untracked_a_only"] = sorted(untracked_a - untracked_b)
    d["untracked_b_only"] = sorted(untracked_b - untracked_a)
    d["untracked_both"] = sorted(untracked_a & untracked_b)

    # Stash
    d["stash"] = {"a": ga.get("stash_count", 0), "b": gb.get("stash_count", 0)}

    return d


def _diff_plain(files_a: list[dict], files_b: list[dict]) -> dict:
    """Diff two plain directory file listings."""
    map_a = {f["path"]: f for f in files_a}
    map_b = {f["path"]: f for f in files_b}
    paths_a = set(map_a.keys())
    paths_b = set(map_b.keys())

    same = []
    different = []
    for p in sorted(paths_a & paths_b):
        fa, fb = map_a[p], map_b[p]
        sha_a = fa.get("sha256")
        sha_b = fb.get("sha256")
        if sha_a and sha_b:
            if sha_a == sha_b:
                same.append(p)
            else:
                different.append({"path": p, "a_sha256": sha_a, "b_sha256": sha_b})
        elif fa.get("size") == fb.get("size"):
            same.append(p)
        else:
            different.append({
                "path": p,
                "a_size": fa.get("size"),
                "b_size": fb.get("size"),
                "note": "hash unavailable, sizes differ",
            })

    return {
        "files_a_only": sorted(paths_a - paths_b),
        "files_b_only": sorted(paths_b - paths_a),
        "files_both_same": same,
        "files_both_different": different,
    }


# ---------------------------------------------------------------------------
# Reconciliation report
# ---------------------------------------------------------------------------

def generate_reconciliation(snap_a: dict, snap_b: dict) -> str:
    """Produce a Markdown reconciliation report from two snapshots."""
    diff = compute_diff(snap_a, snap_b)
    host_a = diff["compared"]["a"]["hostname"]
    host_b = diff["compared"]["b"]["hostname"]
    ts_a = diff["compared"]["a"]["timestamp"]
    ts_b = diff["compared"]["b"]["timestamp"]

    lines = []
    w = lines.append

    w(f"# Reconciliation: {host_a} <-> {host_b}")
    w(f"")
    w(f"Snapshots: {host_a} at {ts_a}, {host_b} at {ts_b}")
    w("")

    # --- Missing directories ---
    if diff["only_in_a"] or diff["only_in_b"]:
        w("## Missing Directories")
        w("")
        for name in diff["only_in_a"]:
            detail = diff["only_in_a_detail"][name]
            w(f"### `{name}` — exists on **{host_a}** only")
            if detail["type"] == "git":
                origin = detail.get("remotes", {}).get("origin", "unknown")
                branch = detail.get("branch", "unknown")
                w(f"- Type: git repo, branch `{branch}`")
                w(f"- Origin: `{origin}`")
                w(f"- **Action on {host_b}:**")
                w(f"  ```bash")
                w(f"  cd ~/.talon/user && git clone {origin} {name}")
                if branch and branch != "main" and branch != "master":
                    w(f"  cd ~/.talon/user/{name} && git checkout {branch}")
                w(f"  ```")
            else:
                w(f"- Type: plain directory ({detail.get('file_count', '?')} files)")
                w(f"- **Action:** Copy from {host_a} to {host_b} via scp/rsync")
            w("")

        for name in diff["only_in_b"]:
            detail = diff["only_in_b_detail"][name]
            w(f"### `{name}` — exists on **{host_b}** only")
            if detail["type"] == "git":
                origin = detail.get("remotes", {}).get("origin", "unknown")
                branch = detail.get("branch", "unknown")
                w(f"- Type: git repo, branch `{branch}`")
                w(f"- Origin: `{origin}`")
                w(f"- **Action on {host_a}:**")
                w(f"  ```bash")
                w(f"  cd ~/.talon/user && git clone {origin} {name}")
                if branch and branch != "main" and branch != "master":
                    w(f"  cd ~/.talon/user/{name} && git checkout {branch}")
                w(f"  ```")
            else:
                w(f"- Type: plain directory ({detail.get('file_count', '?')} files)")
                w(f"- **Action:** Copy from {host_b} to {host_a} via scp/rsync")
            w("")

    # --- Per-directory analysis ---
    has_branch_divergence = False
    has_commit_divergence = False
    has_dirty = False
    has_plain_diff = False
    has_type_mismatch = False

    for name, entry in diff["directories"].items():
        if not entry["type_match"]:
            has_type_mismatch = True
        if "git_diff" in entry:
            gd = entry["git_diff"]
            if not gd["branch"]["match"]:
                has_branch_divergence = True
            elif not gd["head_sha"]["match"]:
                has_commit_divergence = True
            if (gd["dirty_a_only"] or gd["dirty_b_only"] or gd["dirty_both"]
                    or gd["untracked_a_only"] or gd["untracked_b_only"]):
                has_dirty = True
        if "plain_diff" in entry:
            pd = entry["plain_diff"]
            if pd["files_a_only"] or pd["files_b_only"] or pd["files_both_different"]:
                has_plain_diff = True

    # Type mismatches (anomaly)
    if has_type_mismatch:
        w("## Type Mismatches (Anomaly)")
        w("")
        for name, entry in diff["directories"].items():
            if not entry["type_match"]:
                w(f"### `{name}`")
                w(f"- {host_a}: {entry['type_a']}")
                w(f"- {host_b}: {entry['type_b']}")
                w(f"- **Action:** Investigate — one machine has this as a git repo, the other doesn't")
                w("")

    # Branch divergence
    if has_branch_divergence:
        w("## Branch Divergence")
        w("")
        for name, entry in diff["directories"].items():
            if "git_diff" not in entry:
                continue
            gd = entry["git_diff"]
            if gd["branch"]["match"]:
                continue
            ba, bb = gd["branch"]["a"], gd["branch"]["b"]
            w(f"### `{name}`")
            w(f"- {host_a}: branch `{ba}`")
            w(f"- {host_b}: branch `{bb}`")

            # Check if branch names contain hostnames
            is_hostname_branch = False
            for h in [host_a, host_b, "mini", "laptop", "macbook"]:
                if h and (h in (ba or "") or h in (bb or "")):
                    is_hostname_branch = True
                    break
            if is_hostname_branch:
                w(f"- **Expected:** These appear to be hostname-specific branches")
                w(f"- **Action:** Verify both branches are pushed to origin. Consider merging shared changes into a common branch (e.g. `main`)")
            else:
                w(f"- **Action:** Determine which branch is correct and switch the other machine")
            w("")

    # Commit divergence (same branch, different SHA)
    if has_commit_divergence:
        w("## Commit Divergence (Same Branch, Different Commits)")
        w("")
        for name, entry in diff["directories"].items():
            if "git_diff" not in entry:
                continue
            gd = entry["git_diff"]
            if not gd["branch"]["match"] or gd["head_sha"]["match"]:
                continue
            sha_a = gd["head_sha"]["a"]
            sha_b = gd["head_sha"]["b"]
            branch = gd["branch"]["a"]
            w(f"### `{name}` (branch: `{branch}`)")
            w(f"- {host_a}: `{sha_a[:12]}`")
            w(f"- {host_b}: `{sha_b[:12]}`")

            ahead_a = gd["ahead"].get("a")
            behind_a = gd["behind"].get("a")
            if ahead_a is not None and behind_a is not None:
                if ahead_a > 0 and behind_a == 0:
                    w(f"- {host_a} is **{ahead_a} commits ahead** of remote")
                    w(f"- **Action on {host_a}:** `cd ~/.talon/user/{name} && git push`")
                    w(f"- **Action on {host_b}:** `cd ~/.talon/user/{name} && git pull`")
                elif behind_a > 0 and ahead_a == 0:
                    w(f"- {host_a} is **{behind_a} commits behind** remote")
                    w(f"- **Action on {host_a}:** `cd ~/.talon/user/{name} && git pull`")
                elif ahead_a > 0 and behind_a > 0:
                    w(f"- {host_a}: {ahead_a} ahead, {behind_a} behind remote — **diverged**")
                    w(f"- **Action:** Manual resolution needed — rebase or merge")
                else:
                    w(f"- **Action:** One machine needs to push, then the other pulls. Check which is newer.")
            else:
                w(f"- No tracking info — compare SHAs manually:")
                w(f"  ```bash")
                w(f"  cd ~/.talon/user/{name} && git log --oneline -5")
                w(f"  ```")
            w("")

    # Uncommitted changes
    if has_dirty:
        w("## Uncommitted Changes")
        w("")
        w("**These must be resolved before syncing (commit, stash, or discard).**")
        w("")
        for name, entry in diff["directories"].items():
            if "git_diff" not in entry:
                continue
            gd = entry["git_diff"]
            sections = []
            if gd["dirty_a_only"]:
                sections.append((host_a, "Modified (tracked)", gd["dirty_a_only"]))
            if gd["dirty_b_only"]:
                sections.append((host_b, "Modified (tracked)", gd["dirty_b_only"]))
            if gd["dirty_both"]:
                sections.append(("BOTH", "Modified on both machines", gd["dirty_both"]))
            if gd["untracked_a_only"]:
                sections.append((host_a, "Untracked", gd["untracked_a_only"]))
            if gd["untracked_b_only"]:
                sections.append((host_b, "Untracked", gd["untracked_b_only"]))

            if not sections:
                continue

            w(f"### `{name}`")
            for host, label, files in sections:
                w(f"**{host}** — {label}:")
                for f in files:
                    fname = f if isinstance(f, str) else f
                    w(f"  - `{fname}`")
            w("")

    # Plain directory differences
    if has_plain_diff:
        w("## Config File Differences (Non-Git Directories)")
        w("")
        for name, entry in diff["directories"].items():
            if "plain_diff" not in entry:
                continue
            pd = entry["plain_diff"]
            if not (pd["files_a_only"] or pd["files_b_only"] or pd["files_both_different"]):
                continue

            w(f"### `{name}`")
            if pd["files_a_only"]:
                w(f"**Only on {host_a}:**")
                for f in pd["files_a_only"]:
                    w(f"  - `{f}`")
            if pd["files_b_only"]:
                w(f"**Only on {host_b}:**")
                for f in pd["files_b_only"]:
                    w(f"  - `{f}`")
            if pd["files_both_different"]:
                w(f"**Content differs:**")
                for f in pd["files_both_different"]:
                    w(f"  - `{f['path']}` — {f.get('note', 'hash mismatch')}")
            w(f"- **Action:** Compare and reconcile manually. These are unversioned files.")
            w("")

    # Hostname-specific files
    w("## Hostname-Specific Files")
    w("")
    w("These files use Talon's `hostname:` context matcher and are **expected to differ** between machines.")
    w("They should exist on **both** machines — Talon's hostname matcher ensures only the correct one activates.")
    w("")
    all_hostname_files = {}
    for hf in diff["hostname_analysis"].get("hostname_files_a", []):
        all_hostname_files[hf["path"]] = hf["hostnames_referenced"]
    for hf in diff["hostname_analysis"].get("hostname_files_b", []):
        if hf["path"] not in all_hostname_files:
            all_hostname_files[hf["path"]] = hf["hostnames_referenced"]
    for path in sorted(all_hostname_files):
        hosts = ", ".join(all_hostname_files[path])
        w(f"- `{path}` (hostname: {hosts})")
    w("")

    # Summary of all actions
    w("---")
    w("")
    w("## Summary of Actions")
    w("")
    w("Review the sections above and execute the suggested commands on each machine.")
    w("Recommended order:")
    w("1. Commit or stash all uncommitted changes on both machines")
    w("2. Push all unpushed branches from both machines")
    w("3. Pull/clone missing repos on each machine")
    w("4. Reconcile any branch divergence (merge shared changes)")
    w("5. Manually compare non-git config file differences")
    w("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_snapshot(args):
    talon_path = args.talon_user or DEFAULT_TALON_USER
    if not os.path.isdir(talon_path):
        print(f"Error: {talon_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Snapshotting {talon_path}...", file=sys.stderr)
    snap = create_snapshot(talon_path)

    if args.output:
        out_path = args.output
    else:
        hostname = snap["hostname"]
        date = datetime.now().strftime("%Y%m%d")
        out_path = f"talon-snapshot-{hostname}-{date}.json"

    with open(out_path, "w") as f:
        json.dump(snap, f, indent=2)

    print(f"Snapshot written to {out_path}", file=sys.stderr)
    print(f"  Hostname: {snap['hostname']}", file=sys.stderr)
    print(f"  Directories: {len(snap['directories'])}", file=sys.stderr)
    git_count = sum(1 for d in snap["directories"].values() if d["type"] == "git")
    plain_count = sum(1 for d in snap["directories"].values() if d["type"] == "plain")
    print(f"  Git repos: {git_count}, Plain dirs: {plain_count}", file=sys.stderr)
    print(f"  Hostname files found: {len(snap['hostname_files'])}", file=sys.stderr)


def cmd_diff(args):
    with open(args.snapshot_a) as f:
        snap_a = json.load(f)
    with open(args.snapshot_b) as f:
        snap_b = json.load(f)

    diff = compute_diff(snap_a, snap_b)

    if args.output:
        out_path = args.output
    else:
        out_path = "talon-diff.json"

    with open(out_path, "w") as f:
        json.dump(diff, f, indent=2)

    print(f"Diff written to {out_path}", file=sys.stderr)
    print(f"  Only on {diff['compared']['a']['hostname']}: {len(diff['only_in_a'])} dirs", file=sys.stderr)
    print(f"  Only on {diff['compared']['b']['hostname']}: {len(diff['only_in_b'])} dirs", file=sys.stderr)
    print(f"  In common: {len(diff['directories'])} dirs", file=sys.stderr)


def cmd_reconcile(args):
    with open(args.snapshot_a) as f:
        snap_a = json.load(f)
    with open(args.snapshot_b) as f:
        snap_b = json.load(f)

    report = generate_reconciliation(snap_a, snap_b)

    if args.output:
        out_path = args.output
    else:
        out_path = "talon-reconciliation.md"

    with open(out_path, "w") as f:
        f.write(report)

    print(f"Reconciliation report written to {out_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Talon user directory snapshot, diff, and reconciliation tool"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # snapshot
    p_snap = sub.add_parser("snapshot", help="Capture state of ~/.talon/user/")
    p_snap.add_argument("--output", "-o", help="Output JSON file path")
    p_snap.add_argument("--talon-user", help=f"Talon user directory (default: {DEFAULT_TALON_USER})")

    # diff
    p_diff = sub.add_parser("diff", help="Compare two snapshots")
    p_diff.add_argument("snapshot_a", help="First snapshot JSON")
    p_diff.add_argument("snapshot_b", help="Second snapshot JSON")
    p_diff.add_argument("--output", "-o", help="Output diff JSON file path")

    # reconcile
    p_rec = sub.add_parser("reconcile", help="Generate reconciliation report")
    p_rec.add_argument("snapshot_a", help="First snapshot JSON")
    p_rec.add_argument("snapshot_b", help="Second snapshot JSON")
    p_rec.add_argument("--output", "-o", help="Output Markdown file path")

    args = parser.parse_args()
    if args.command == "snapshot":
        cmd_snapshot(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "reconcile":
        cmd_reconcile(args)


if __name__ == "__main__":
    main()
