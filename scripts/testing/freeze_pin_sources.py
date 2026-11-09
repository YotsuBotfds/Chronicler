"""Build and verify the frozen snapshot of the source-witnessed files.

The witness fixtures (``tests/fixtures/*inverse*.json``) and the four
``health_care*`` digests in ``tests/test_health_care_policy.py`` bind exact
source bytes. This one-off tool copies those bytes, as of one reviewed commit,
to ``tests/fixtures/frozen_pin_sources/<path>.txt`` and records them in
``MANIFEST.json`` as ``{"freeze_commit": <sha>, "files": {path: sha256}}``.

  --write   copy the working-tree bytes and write MANIFEST.json. Refuses when
            any working-tree file differs from ``git show <commit>:<path>``.
  --verify  compare every copy with MANIFEST.json and with
            ``git show <freeze_commit>:<path>`` (needs that commit's objects,
            so a full clone or a fetched freeze tag).

The copies are frozen history: never edit, re-hash or regenerate them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FROZEN_DIR = "tests/fixtures/frozen_pin_sources"
MANIFEST_NAME = "MANIFEST.json"
INVERSE_GLOB = "tests/fixtures/*inverse*.json"
# Whole-file digests pinned directly by the care source-binding test
# (tests/test_health_care_policy.py) and named by no inverse fixture.
DIGEST_PINNED = (
    "chronicler-agents/src/health_care.rs",
    "chronicler-agents/src/health_care_observation.rs",
    "src/chronicler/health_care.py",
    "src/chronicler/health_care_state.py",
)


def pinned_paths(root: Path = ROOT) -> list[str]:
    """The union of every inverse fixture's files/new_files plus DIGEST_PINNED."""
    paths: set[str] = set(DIGEST_PINNED)
    fixtures = sorted(root.glob(INVERSE_GLOB))
    if not fixtures:
        raise FileNotFoundError(f"no inverse fixtures match {INVERSE_GLOB} under {root}")
    for fixture in fixtures:
        data = json.loads(fixture.read_text(encoding="utf-8"))
        for key in ("files", "new_files"):
            paths.update(data.get(key, {}))
    return sorted(paths)


def copy_path(rel: str, root: Path = ROOT) -> Path:
    return root / FROZEN_DIR / f"{rel}.txt"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True).stdout


def _git_blob(root: Path, commit: str, rel: str) -> bytes | None:
    try:
        return _git(root, "show", f"{commit}:{rel}")
    except subprocess.CalledProcessError:
        return None


def write(root: Path, commit: str) -> int:
    freeze_commit = _git(root, "rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    files: dict[str, str] = {}
    problems = []
    for rel in pinned_paths(root):
        source = root / rel
        if not source.is_file():
            problems.append(f"missing in working tree: {rel}")
            continue
        data = source.read_bytes()
        if _git_blob(root, freeze_commit, rel) != data:
            problems.append(f"working tree differs from {freeze_commit[:12]}: {rel}")
            continue
        files[rel] = _sha256(data)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"refused: {len(problems)} problem(s); nothing written", file=sys.stderr)
        return 1
    for rel in files:
        target = copy_path(rel, root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / rel).read_bytes())
    manifest = {"freeze_commit": freeze_commit, "files": files}
    (root / FROZEN_DIR / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(files)} frozen copies at {freeze_commit}")
    return 0


def verify(root: Path) -> int:
    manifest = json.loads((root / FROZEN_DIR / MANIFEST_NAME).read_text(encoding="utf-8"))
    freeze_commit = manifest["freeze_commit"]
    problems = []
    expected = pinned_paths(root)
    if sorted(manifest["files"]) != expected:
        missing = sorted(set(expected) - set(manifest["files"]))
        extra = sorted(set(manifest["files"]) - set(expected))
        problems.append(f"manifest paths differ from the pinned set: missing={missing} extra={extra}")
    try:
        _git(root, "cat-file", "-e", f"{freeze_commit}^{{commit}}")
    except subprocess.CalledProcessError:
        print(f"freeze commit {freeze_commit} is not available; fetch it (full clone) first",
              file=sys.stderr)
        return 2
    for rel, digest in sorted(manifest["files"].items()):
        target = copy_path(rel, root)
        if not target.is_file():
            problems.append(f"copy missing: {rel}")
            continue
        data = target.read_bytes()
        if _sha256(data) != digest:
            problems.append(f"copy differs from MANIFEST: {rel}")
        if _git_blob(root, freeze_commit, rel) != data:
            problems.append(f"copy differs from {freeze_commit[:12]}:{rel}")
    for problem in problems:
        print(problem)
    print(f"{len(manifest['files'])} files, {len(problems)} mismatches")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--commit", default="HEAD",
                        help="freeze commit for --write (default HEAD); working tree must match it")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    return write(root, args.commit) if args.write else verify(root)


if __name__ == "__main__":
    raise SystemExit(main())
