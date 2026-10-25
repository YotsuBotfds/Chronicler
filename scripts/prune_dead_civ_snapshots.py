#!/usr/bin/env python3
"""Convert version-4 bundles to version 5 and check the conversion.

    convert BATCH_OR_BUNDLE...   rewrite each version-4 chronicle_bundle.json in
                                 place as version 5 (dead civs pruned from the
                                 history snapshots, docs/performance/dead-civ-pruning.md)
    check V4_BUNDLE V5_BUNDLE    verify a version-5 bundle against the
                                 version-4 bundle of the same run: the pruned
                                 history equals the conversion of the version-4
                                 history, restoring it gives the version-4
                                 civ_stats exactly (values, types and key
                                 order), and nothing else differs apart from
                                 the bundle version and generated_at

Converted bundles are written in the version-5 layout; ``scripts/bundle_v6.py
convert`` converts either version to version 6. ``check`` decodes a version-6
V5_BUNDLE first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chronicler.bundle_codec import decode_bundle  # noqa: E402
from chronicler.snapshot_pruning import (  # noqa: E402
    PRUNED_CIV_STATS_KEY,
    prune_bundle,
    restore_history,
)

BUNDLE = "chronicle_bundle.json"


def _dumps(bundle: dict) -> str:
    return json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))


def _bundles(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        found.extend([path] if path.is_file() else sorted(path.rglob(BUNDLE)))
    return found


def convert(paths: list[Path]) -> int:
    before = after = 0
    for path in _bundles(paths):
        raw = path.read_text(encoding="utf-8")
        bundle = json.loads(raw)
        if PRUNED_CIV_STATS_KEY in bundle:
            print(f"{path}: already version {bundle.get('metadata', {}).get('bundle_version')}")
            continue
        text = _dumps(prune_bundle(bundle))
        path.write_text(text, encoding="utf-8")
        before += len(raw.encode("utf-8"))
        after += len(text.encode("utf-8"))
        print(f"{path}: {len(raw.encode('utf-8')):,} -> {len(text.encode('utf-8')):,} bytes")
    if before:
        print(f"total: {before:,} -> {after:,} bytes ({after / before:.1%})")
    return 0


def _strict(a, b) -> bool:
    """Equal JSON text: values, number types and key order."""
    return _dumps(a) == _dumps(b)


def check(v4_path: Path, v5_path: Path) -> int:
    v4 = json.loads(v4_path.read_text(encoding="utf-8"))
    v5 = decode_bundle(json.loads(v5_path.read_text(encoding="utf-8")))
    problems: list[str] = []
    if PRUNED_CIV_STATS_KEY in v4:
        problems.append(f"{v4_path} is not a version-4 bundle")
    if PRUNED_CIV_STATS_KEY not in v5:
        problems.append(f"{v5_path} has no {PRUNED_CIV_STATS_KEY}")
    if not problems:
        expected = prune_bundle(v4)
        for key in ("history", PRUNED_CIV_STATS_KEY):
            if not _strict(expected[key], v5[key]):
                problems.append(f"{key} differs from the conversion of the version-4 bundle")
        restored = restore_history(v5["history"], v5[PRUNED_CIV_STATS_KEY])
        if len(restored) != len(v4["history"]):
            problems.append("restored history length differs")
        for old, new in zip(v4["history"], restored):
            if not _strict(old["civ_stats"], new["civ_stats"]):
                problems.append(f"restored civ_stats differ at turn {old.get('turn')}")
                break
        rest4 = {k: v for k, v in v4.items() if k not in ("history", "metadata")}
        rest5 = {k: v for k, v in v5.items() if k not in ("history", "metadata", PRUNED_CIV_STATS_KEY)}
        if not _strict(rest4, rest5):
            problems.append("fields outside history and metadata differ")
        meta4 = {k: v for k, v in v4.get("metadata", {}).items() if k not in ("generated_at", "bundle_version")}
        meta5 = {k: v for k, v in v5.get("metadata", {}).items() if k not in ("generated_at", "bundle_version")}
        if not _strict(meta4, meta5):
            problems.append("metadata differs beyond generated_at and bundle_version")
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        print(f"OK {v5_path}: {v4_path.stat().st_size:,} -> {v5_path.stat().st_size:,} bytes")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    conv = sub.add_parser("convert", help="rewrite version-4 bundles in place as version 5")
    conv.add_argument("paths", nargs="+", type=Path)
    chk = sub.add_parser("check", help="verify a version-5 bundle against its version-4 bundle")
    chk.add_argument("v4", type=Path)
    chk.add_argument("v5", type=Path)
    args = parser.parse_args()
    if args.command == "convert":
        return convert(args.paths)
    return check(args.v4, args.v5)


if __name__ == "__main__":
    sys.exit(main())
