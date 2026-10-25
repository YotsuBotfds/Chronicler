#!/usr/bin/env python3
"""Identity checks for ``--agent-movements``.

``compare BASE_DIR NEW_DIR``
    Every file of two run directories (one run, or a batch of ``seed_*``
    runs) byte for byte; ``chronicle_bundle.json`` without
    ``metadata.generated_at``. As ``scripts/cities_identity.py``.

``compare-inert BASE_DIR NEW_DIR``
    The same after removing the layer's own fields: ``agent_movements`` from
    ``state.json`` and from every ``history[n]`` and the bundle's
    ``world_state``. Used for runs with the switch on that founded no
    movement (``--agents off``: there is no census), to show the layer is
    inert there.

Run BASE with the base commit's source and native extension on
``PYTHONPATH``, NEW with this branch; same interpreter, arguments and
``PYTHONHASHSEED=0``. See docs/integration/agent-movements.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from chronicler.bundle_codec import load_bundle

IGNORED_NAMES = frozenset({"run_manifest.json"})
FIELD = "agent_movements"


def _strip(data, inert: bool):
    if not inert or not isinstance(data, dict):
        return data
    data.pop(FIELD, None)
    for row in data.get("history", []) or []:
        if isinstance(row, dict):
            row.pop(FIELD, None)
    ws = data.get("world_state")
    if isinstance(ws, dict):
        ws.pop(FIELD, None)
    return data


def _content(path: Path, inert: bool) -> bytes:
    if path.name == "chronicle_bundle.json":
        data = load_bundle(path)  # version 6: history as deltas, decoded here
        data.get("metadata", {}).pop("generated_at", None)
        return json.dumps(_strip(data, inert), sort_keys=True).encode("utf-8")
    if inert and path.name.startswith("state") and path.suffix == ".json" and path.name.count(".") == 1:
        data = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(_strip(data, inert), sort_keys=True).encode("utf-8")
    return path.read_bytes()


def compare(base: Path, new: Path, inert: bool = False) -> tuple[int, list[str]]:
    base_files = {p.relative_to(base) for p in base.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
    problems: list[str] = []
    for rel in sorted(base_files ^ new_files):
        if rel.name not in IGNORED_NAMES and rel.suffix != ".log":
            problems.append(f"only in {'base' if rel in base_files else 'new'}: {rel}")
    checked = 0
    for rel in sorted(base_files & new_files):
        if rel.name in IGNORED_NAMES or rel.suffix == ".log":
            continue
        a, b = _content(base / rel, inert), _content(new / rel, inert)
        checked += 1
        if a != b:
            problems.append(f"differs: {rel} ({hashlib.sha256(a).hexdigest()[:12]} != "
                            f"{hashlib.sha256(b).hexdigest()[:12]})")
    return checked, problems


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in ("compare", "compare-inert"):
        print(__doc__)
        return 2
    checked, problems = compare(Path(argv[1]), Path(argv[2]), inert=argv[0] == "compare-inert")
    for line in problems:
        print(line)
    print(f"{checked} files compared, {len(problems)} differences")
    return 0 if not problems and checked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
