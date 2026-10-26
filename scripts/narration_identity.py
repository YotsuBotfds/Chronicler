#!/usr/bin/env python3
"""Identity check for narration changes: everything but the narration is equal.

``compare BASE_DIR NEW_DIR``
    Every file of two run directories (one run, or a batch of ``seed_*``
    runs) byte for byte, except the narration itself: ``chronicle.md``, the
    captured ``prompts.jsonl`` and its ``report.json``, logs and
    ``run_manifest.json`` are skipped,
    and ``chronicle_bundle.json`` is compared decoded, without
    ``metadata.generated_at``, ``chronicle_entries`` and ``gap_summaries``.
    State, sidecars, snapshots (the bundle's history), the event timeline,
    agent events and validation sidecars must be identical.

Run BASE with the base commit's source on ``PYTHONPATH`` and NEW with this
branch; same interpreter, native extension, arguments and
``PYTHONHASHSEED=0``. See docs/integration/narration-coverage.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from chronicler.bundle_codec import load_bundle

SKIPPED_NAMES = frozenset({"run_manifest.json", "chronicle.md", "prompts.jsonl", "narrated.json", "report.json"})
NARRATION_FIELDS = ("chronicle_entries", "gap_summaries")


def _skipped(rel: Path) -> bool:
    return rel.name in SKIPPED_NAMES or rel.suffix == ".log"


def _content(path: Path) -> bytes:
    if path.name == "chronicle_bundle.json":
        data = load_bundle(path)
        data.get("metadata", {}).pop("generated_at", None)
        for key in NARRATION_FIELDS:
            data.pop(key, None)
        return json.dumps(data, sort_keys=True).encode("utf-8")
    return path.read_bytes()


def compare(base: Path, new: Path) -> tuple[int, list[str]]:
    base_files = {p.relative_to(base) for p in base.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
    problems: list[str] = []
    for rel in sorted(base_files ^ new_files):
        if not _skipped(rel):
            problems.append(f"only in {'base' if rel in base_files else 'new'}: {rel}")
    checked = 0
    for rel in sorted(base_files & new_files):
        if _skipped(rel):
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
