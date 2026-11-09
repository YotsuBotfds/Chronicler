#!/usr/bin/env python3
"""Prove that epidemiology switched off changes no output byte.

``compare BASE_DIR NEW_DIR``
    Walk two run directories (one run, or a batch of ``seed_*`` runs) and
    compare every file they contain. ``chronicle_bundle.json`` is compared
    after dropping ``metadata.generated_at`` (the wall-clock stamp); every
    other file must match byte for byte. Files present on only one side are
    reported. Exit status 0 when identical.

Run BASE with the base commit's source on ``PYTHONPATH`` and NEW with this
branch, same interpreter, native extension, arguments and
``PYTHONHASHSEED=0``. See docs/integration/epidemiology.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

IGNORED_NAMES = frozenset({"run_manifest.json"})  # gate tooling, records its own flags


def _bundle_bytes(path: Path) -> bytes:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.get("metadata", {}).pop("generated_at", None)
    return json.dumps(data, sort_keys=True).encode("utf-8")


def _content(path: Path) -> bytes:
    if path.name == "chronicle_bundle.json":
        return _bundle_bytes(path)
    return path.read_bytes()


def compare(base: Path, new: Path) -> tuple[int, list[str]]:
    base_files = {p.relative_to(base) for p in base.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
    problems: list[str] = []
    for rel in sorted(base_files ^ new_files):
        if rel.name not in IGNORED_NAMES:
            problems.append(f"only in {'base' if rel in base_files else 'new'}: {rel}")
    checked = 0
    for rel in sorted(base_files & new_files):
        if rel.name in IGNORED_NAMES or rel.suffix in (".log",):
            continue
        a, b = _content(base / rel), _content(new / rel)
        checked += 1
        if a != b:
            problems.append(f"differs: {rel} ({hashlib.sha256(a).hexdigest()[:12]} != "
                            f"{hashlib.sha256(b).hexdigest()[:12]})")
    return checked, problems


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "compare":
        print(__doc__)
        return 2
    checked, problems = compare(Path(argv[1]), Path(argv[2]))
    for line in problems:
        print(line)
    print(f"{checked} files compared, {len(problems)} differences")
    return 0 if not problems and checked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
