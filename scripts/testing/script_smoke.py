#!/usr/bin/env python3
"""Smoke the safe entries of scripts/testing/script_smoke_manifest.json.

    python scripts/testing/script_smoke.py [--list] [--timeout SECONDS]

Adds a detached temporary worktree of HEAD (``git worktree add --detach``)
and reads the manifest there. Each entry marked ``safe_to_run`` runs from
the worktree root with its recorded invocation (``.py`` with this
interpreter, ``.sh`` with bash; ``PYTHONPATH`` is the worktree's ``src``),
and its exit status is compared with ``expected_exit``. Afterwards
``git status --porcelain --ignored --untracked-files=all`` in the worktree
must be empty, and the worktree is removed. Entries not marked safe never
run. Only committed files are tested. Exit status 0 when every status
matches and nothing changed.

This is not a pytest test: the bounded offline lane forbids child
processes, so tests/test_script_smoke_manifest.py checks the manifest
statically. Passing shows only that the invocations exit as recorded and
write nothing; it does not qualify any script's results.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path("scripts") / "testing" / "script_smoke_manifest.json"


def _unique(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise SystemExit(f"duplicate manifest key {key!r}")
        seen[key] = value
    return seen


def load_manifest(root: Path) -> dict:
    return json.loads((root / MANIFEST).read_text(encoding="utf-8"), object_pairs_hook=_unique)


def command(path: str, entry: dict) -> list[str]:
    interpreter = ["bash"] if path.endswith(".sh") else [sys.executable]
    return [*interpreter, path, *entry["invocation"]]


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _shown(path: str, entry: dict) -> str:
    return " ".join([path, *entry["invocation"]])


def _tail(data: bytes, lines: int = 6) -> str:
    return "\n".join("    " + line for line in data.decode("utf-8", errors="replace").splitlines()[-lines:])


def run(timeout: float) -> int:
    head = git("rev-parse", "HEAD").strip()
    print(f"HEAD {head}")
    if git("status", "--porcelain", "--untracked-files=no").strip():
        print("note: the checkout has uncommitted changes; only HEAD is tested")
    print(f"python {sys.version.split()[0]} ({sys.executable}); "
          f"chronicler_agents importable: {find_spec('chronicler_agents') is not None}")
    tmp = Path(tempfile.mkdtemp(prefix="script-smoke-"))
    worktree = tmp / "worktree"
    failures: list[str] = []
    added = False
    try:
        git("worktree", "add", "--detach", str(worktree), head)
        added = True
        print(f"worktree {worktree}")
        entries = load_manifest(worktree)["scripts"]
        safe = {path: entry for path, entry in entries.items() if entry["safe_to_run"]}
        for path in entries:
            if path not in safe:
                print(f"not run  {_shown(path, entries[path])} ({entries[path]['note']})")
        env = dict(os.environ, PYTHONPATH=str(worktree / "src"), PYTHONDONTWRITEBYTECODE="1",
                   PYTHONHASHSEED="0")
        start = time.monotonic()
        for path, entry in safe.items():
            began = time.monotonic()
            if not (worktree / path).is_file():
                code, output = None, b"missing at HEAD"
            else:
                try:
                    result = subprocess.run(command(path, entry), cwd=worktree, env=env,
                                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, timeout=timeout)
                    code, output = result.returncode, result.stdout
                except subprocess.TimeoutExpired as error:
                    code, output = None, (error.stdout or b"") + f"\n{timeout:g}-second limit".encode()
            ok = code == entry["expected_exit"]
            print(f"{'ok' if ok else 'MISMATCH':8} {_shown(path, entry)}: exit {code} "
                  f"(expected {entry['expected_exit']}), {time.monotonic() - began:.1f} s")
            if not ok:
                failures.append(path)
                print(_tail(output))
        status = git("status", "--porcelain", "--ignored", "--untracked-files=all", cwd=worktree)
        if status.strip():
            failures.append("worktree status")
            print("worktree changed:\n" + status.rstrip())
        else:
            print("worktree status: clean (git status --porcelain --ignored --untracked-files=all)")
        print(f"{len(safe) - sum(1 for f in failures if f in safe)} of {len(safe)} safe entries matched, "
              f"{len(entries) - len(safe)} not run, {time.monotonic() - start:.1f} s")
    finally:
        if added:
            git("worktree", "remove", "--force", str(worktree))
            print("worktree removed")
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not failures else f"FAIL: {', '.join(failures)}")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the checkout's entries and run nothing")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds per script (default 120)")
    args = parser.parse_args(argv)
    if args.list:
        for path, entry in load_manifest(ROOT)["scripts"].items():
            state = "run" if entry["safe_to_run"] else "not run"
            print(f"{state:8} {_shown(path, entry)} -> exit {entry['expected_exit']}")
        return 0
    return run(args.timeout)


if __name__ == "__main__":
    sys.exit(main())
