#!/usr/bin/env python3
"""Convert, decode, compare and measure chronicle bundles (bundle version 6).

    convert BATCH_OR_BUNDLE...  rewrite each chronicle_bundle.json in place as
                                version 6 (version 4 is pruned first, as
                                scripts/prune_dead_civ_snapshots.py does); the
                                written file is decoded and checked against
                                the source before the next one
    decode BUNDLE OUT           write the decoded bundle (the version-5 layout,
                                metadata.bundle_version kept) for tools that
                                read ``history`` directly
    compare BASE NEW            two bundles, or two run directories (each
                                chronicle_bundle.json by relative path): equal
                                once decoded, apart from metadata.generated_at
                                and metadata.bundle_version (values, number
                                types and key order); exit status 0 when equal
    breakdown BUNDLE [--json OUT]
                                bytes and share of the file by top-level field
                                and by history snapshot field; for a version-6
                                file also the bytes of each field's deltas

See docs/performance/bundle-v6.md and src/chronicler/bundle_codec.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chronicler.bundle_codec import (  # noqa: E402
    BUNDLE_VERSION,
    HISTORY_DELTA_KEY,
    decode_bundle,
    dumps_bundle,
    is_encoded,
    same,
)
from chronicler.snapshot_pruning import PRUNED_CIV_STATS_KEY, prune_bundle  # noqa: E402

BUNDLE = "chronicle_bundle.json"
IGNORED_METADATA = ("generated_at", "bundle_version")
MIB = 2 ** 20


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _bundles(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        found.extend([path] if path.is_file() else sorted(path.rglob(BUNDLE)))
    return found


def _logical(bundle: dict) -> dict:
    """A decoded bundle without the fields a conversion or a rerun changes."""
    out = dict(decode_bundle(bundle))
    if isinstance(out.get("metadata"), dict):
        out["metadata"] = {k: v for k, v in out["metadata"].items() if k not in IGNORED_METADATA}
    return out


def first_difference(a, b, path: str = "") -> str | None:
    """The path of the first strict difference, or None."""
    if same(a, b):
        return None
    if type(a) is dict and type(b) is dict:
        if list(a) != list(b):
            return f"{path or '/'}: keys {sorted(set(a) ^ set(b)) or 'order'}"
        for key in a:
            found = first_difference(a[key], b[key], f"{path}/{key}")
            if found:
                return found
    if type(a) is list and type(b) is list:
        if len(a) != len(b):
            return f"{path or '/'}: length {len(a)} != {len(b)}"
        for index, (x, y) in enumerate(zip(a, b)):
            found = first_difference(x, y, f"{path}[{index}]")
            if found:
                return found
    return f"{path or '/'}: {_dumps(a)[:80]} != {_dumps(b)[:80]}"


def convert(paths: list[Path]) -> int:
    before = after = 0
    for path in _bundles(paths):
        raw = path.read_text(encoding="utf-8")
        bundle = json.loads(raw)
        if is_encoded(bundle):
            print(f"{path}: already version {bundle.get('metadata', {}).get('bundle_version')}")
            continue
        version = (bundle.get("metadata") or {}).get("bundle_version") or 0
        if version < 5 and PRUNED_CIV_STATS_KEY not in bundle:
            bundle = prune_bundle(bundle)
        source = _logical(bundle)
        if isinstance(bundle.get("metadata"), dict):
            bundle = {**bundle, "metadata": {**bundle["metadata"], "bundle_version": BUNDLE_VERSION}}
        text = dumps_bundle(bundle)
        found = first_difference(source, _logical(json.loads(text)))
        if found:
            print(f"{path}: not converted, the decoded file would differ at {found}")
            return 1
        path.write_text(text, encoding="utf-8")
        before += len(raw.encode("utf-8"))
        after += len(text.encode("utf-8"))
        print(f"{path}: {len(raw.encode('utf-8')):,} -> {len(text.encode('utf-8')):,} bytes")
    if before:
        print(f"total: {before:,} -> {after:,} bytes ({after / before:.1%})")
    return 0


def decode(source: Path, out: Path) -> int:
    bundle = decode_bundle(json.loads(source.read_text(encoding="utf-8")))
    out.write_text(_dumps(bundle), encoding="utf-8")
    print(f"{out}: {out.stat().st_size:,} bytes")
    return 0


def compare(base: Path, new: Path) -> int:
    if base.is_file() and new.is_file():
        pairs = [(base, new, base.name)]
    else:
        rels = sorted({p.relative_to(base) for p in base.rglob(BUNDLE)}
                      | {p.relative_to(new) for p in new.rglob(BUNDLE)})
        pairs = [(base / rel, new / rel, str(rel)) for rel in rels]
    problems = 0
    for a, b, name in pairs:
        if not (a.exists() and b.exists()):
            print(f"{name}: only in {'base' if a.exists() else 'new'}")
            problems += 1
            continue
        found = first_difference(_logical(json.loads(a.read_text(encoding="utf-8"))),
                                 _logical(json.loads(b.read_text(encoding="utf-8"))))
        print(f"{name}: {'differs at ' + found if found else 'equal once decoded'}")
        problems += bool(found)
    print(f"{len(pairs)} bundles compared, {problems} differences")
    return 0 if pairs and not problems else 1


def _field_bytes(key: str, value) -> int:
    return len(_dumps({key: value}).encode("utf-8")) - 2


def breakdown(path: Path, out: Path | None) -> int:
    raw = path.read_bytes()
    encoded = json.loads(raw)
    total = len(raw)
    result: dict = {"bytes": total, "bundle_version": encoded.get("metadata", {}).get("bundle_version"),
                    "top": {k: _field_bytes(k, v) for k, v in encoded.items()}}
    history = decode_bundle(encoded).get("history", [])
    snapshot: dict[str, int] = {}
    for snap in history:
        for key, value in snap.items():
            snapshot[key] = snapshot.get(key, 0) + _field_bytes(key, value)
    result["snapshots"] = len(history)
    result["history_fields"] = snapshot
    if HISTORY_DELTA_KEY in encoded:
        deltas: dict[str, int] = {}
        for item in encoded[HISTORY_DELTA_KEY]:
            for key, value in item.items():
                deltas[key] = deltas.get(key, 0) + _field_bytes(key, value)
        result["delta_fields"] = deltas
    print(f"{path}: {total:,} bytes ({total / MIB:.2f} MiB), version {result['bundle_version']}, "
          f"{len(history)} snapshots")
    print("top-level fields:")
    for key, size in sorted(result["top"].items(), key=lambda kv: -kv[1]):
        print(f"  {key:32s} {size / MIB:8.3f} MiB {100 * size / total:6.1f}%")
    deltas = result.get("delta_fields", {})
    print("history fields, decoded" + (" | as written" if deltas else "") + ":")
    for key, size in sorted(snapshot.items(), key=lambda kv: -kv[1]):
        if size < 0.01 * MIB and deltas.get(key, 0) < 0.01 * MIB:
            continue
        line = f"  {key:32s} {size / MIB:8.3f} MiB"
        if deltas:
            line += f" | {deltas.get(key, 0) / MIB:8.3f} MiB {100 * deltas.get(key, 0) / total:6.1f}%"
        print(line)
    if out:
        out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("convert")
    p.add_argument("paths", nargs="+", type=Path)
    p = sub.add_parser("decode")
    p.add_argument("bundle", type=Path)
    p.add_argument("out", type=Path)
    p = sub.add_parser("compare")
    p.add_argument("base", type=Path)
    p.add_argument("new", type=Path)
    p = sub.add_parser("breakdown")
    p.add_argument("bundle", type=Path)
    p.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.command == "convert":
        return convert(args.paths)
    if args.command == "decode":
        return decode(args.bundle, args.out)
    if args.command == "compare":
        return compare(args.base, args.new)
    return breakdown(args.bundle, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
