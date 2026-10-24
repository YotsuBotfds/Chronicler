#!/usr/bin/env python3
"""Prove that the viewer-panel snapshot fields are additive only.

``compare BASE_DIR NEW_DIR``
    Every file must match byte for byte (``chronicle_bundle.json`` after
    dropping ``metadata.generated_at``), as in ``scripts/diplomacy_identity.py``.
    Use it for runs with the systems switched off.

``compare-additive BASE_DIR NEW_DIR``
    The same, except that ``history[n].diplomacy.pairs`` and
    ``history[n].techniques.regions`` are removed from the NEW bundle before
    comparing, and the BASE bundle must not carry them. Use it for runs with
    ``--diplomacy --techniques`` (and the other systems) switched on: it shows
    the new fields are the only change, so every simulation outcome and every
    other output byte is unchanged.

Run BASE with the base commit's source on ``PYTHONPATH`` and NEW with this
branch, same interpreter, native extension, arguments and
``PYTHONHASHSEED=0``. See docs/integration/viewer-systems.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

IGNORED_NAMES = frozenset({"run_manifest.json"})
#: (snapshot field, key) pairs added for the viewer panels.
ADDED = (("diplomacy", "pairs"), ("techniques", "regions"))


def _bundle_bytes(path: Path, *, strip: bool, side: str) -> bytes:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.get("metadata", {}).pop("generated_at", None)
    for snap in data.get("history", []):
        for field, key in ADDED:
            section = snap.get(field)
            if not isinstance(section, dict):
                continue
            if side == "base" and key in section:
                raise SystemExit(f"{path}: base bundle already carries {field}.{key}")
            if strip:
                section.pop(key, None)
    return json.dumps(data, sort_keys=True).encode("utf-8")


def compare(base: Path, new: Path, *, additive: bool) -> tuple[int, list[str]]:
    base_files = {p.relative_to(base) for p in base.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
    problems: list[str] = []
    for rel in sorted(base_files ^ new_files):
        if rel.name not in IGNORED_NAMES:
            problems.append(f"only in {'base' if rel in base_files else 'new'}: {rel}")
    checked = stripped = 0
    for rel in sorted(base_files & new_files):
        if rel.name in IGNORED_NAMES or rel.suffix == ".log":
            continue
        if rel.name == "chronicle_bundle.json":
            a = _bundle_bytes(base / rel, strip=False, side="base")
            b = _bundle_bytes(new / rel, strip=additive, side="new")
            if additive:
                raw = json.loads((new / rel).read_text(encoding="utf-8"))
                stripped += sum(1 for s in raw.get("history", []) for f, k in ADDED
                                if isinstance(s.get(f), dict) and k in s[f])
        else:
            a, b = (base / rel).read_bytes(), (new / rel).read_bytes()
        checked += 1
        if a != b:
            problems.append(f"differs: {rel} ({hashlib.sha256(a).hexdigest()[:12]} != "
                            f"{hashlib.sha256(b).hexdigest()[:12]})")
    if additive and not stripped:
        problems.append("no added viewer field found in the new bundle (were the systems on?)")
    return checked, problems


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in ("compare", "compare-additive"):
        print(__doc__)
        return 2
    checked, problems = compare(Path(argv[1]), Path(argv[2]), additive=argv[0] == "compare-additive")
    for line in problems:
        print(line)
    print(f"{checked} files compared, {len(problems)} differences")
    return 0 if not problems and checked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
