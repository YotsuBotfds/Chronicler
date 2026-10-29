"""Bounded metadata-only late publication; never imports producer or opens CP bodies."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat

MEMBER_LIMIT = 8 * 1024**2
TOTAL_LIMIT = 16 * 1024**2
FILE_LIMIT = 128


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError("duplicate metadata key")
            result[key] = value
        return result
    def number(token):
        value = float(token)
        if not math.isfinite(value): raise ValueError("nonfinite metadata")
        return value
    def constant(_token): raise ValueError("nonfinite metadata")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def read_regular(path, limit=MEMBER_LIMIT):
    for parent in path.parents:
        if parent.is_symlink(): raise ValueError("metadata symlink parent")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise ValueError("metadata type/size")
        pieces, size = [], 0
        while block := os.read(descriptor, 1024 * 1024):
            size += len(block)
            if size > limit: raise ValueError("metadata member cap")
            pieces.append(block)
        after = os.fstat(descriptor)
        identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_nlink)
        if identity(before) != identity(after) or size != before.st_size: raise ValueError("metadata changed")
        return b"".join(pieces)
    finally: os.close(descriptor)


def selected_paths():
    # Fixed semantic keep set: raw checkpoints/bundles/state/native bytes stay
    # only in the original retained archive, named by the owner's inventory.
    return ["result.json", "terminal.json", "terminal-failure.json", "registration.json", "roles.json",
            "admission.json", "input-before.json", "input-after.json", "packages-before.json", "packages-after.json",
            "mechanics.json", "source-witnesses.json", "progress.jsonl", "pure-preflight/receipt.json",
            "pure-preflight/junit.xml"]


def publish(root, output, *, owner_outcome, source):
    if (not root.is_absolute() or not output.is_absolute() or root == output or root in output.parents
            or output in root.parents or root != root.resolve() or output != output.resolve()):
        raise ValueError("disjoint absolute publication paths")
    if type(source) is not str or len(source) != 40 or any(c not in "0123456789abcdef" for c in source):
        raise ValueError("publication source SHA")
    if output.exists() or output.is_symlink(): raise ValueError("fresh publication required")
    output.mkdir(parents=True)
    report = {"complete": False, "metadata_only": True, "source_publication_qualified": False,
              "owner_step_outcome": owner_outcome, "source": source, "files": {}, "omissions": [],
              "raw_payload_retained": False, "scope": "Copied fixed bounded metadata only. Original-body verification and source publication qualification remain separate gates."}
    def seal():
        raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        if len(raw) > 65536: raise ValueError("publication authority cap")
        (output / "publication.json").write_bytes(raw)
    seal()  # Negative authority precedes all reads/copies, including absent setup.
    total, retained = 0, {}
    for name in selected_paths():
        path = root / name
        try:
            raw = read_regular(path)
            if len(report["files"]) + 1 >= FILE_LIMIT or total + len(raw) + 65536 > TOTAL_LIMIT:
                raise ValueError("publication aggregate cap")
            target = output / name; target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            report["files"][name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            retained[name] = raw; total += len(raw)
        except (OSError, ValueError) as exc:
            report["omissions"].append({"path": name, "reason": type(exc).__name__})
    try:
        terminal = strict_json(retained["terminal.json"])
        result = strict_json(retained["result.json"])
        expected = selected_paths()
        optional = {"terminal-failure.json"}
        present = set(retained)
        report["complete"] = (owner_outcome == "success" and terminal.get("complete") is True
            and terminal.get("cleanup_complete") is True and terminal.get("required_wrapper_exit") == 0
            and "terminal-failure.json" not in present
            and not (root / "terminal-failure.json").exists() and not (root / "terminal-failure.json").is_symlink()
            and terminal.get("result_sha256") == hashlib.sha256(retained["result.json"]).hexdigest()
            and result.get("complete") is True and result.get("errors") == []
            and result.get("actual_simulation_roles") == 14 and result.get("actual_executed_ticks") == 315
            and result.get("actual_fresh_Worlds") == 7 and result.get("actual_restored_roles") == 7
            and result.get("mechanical_readout_sha256") == hashlib.sha256(retained["mechanics.json"]).hexdigest()
            and strict_json(retained["mechanics.json"]).get("complete") is True
            and strict_json(retained["packages-before.json"]) == strict_json(retained["packages-after.json"])
            and result.get("producer", {}).get("GITHUB_SHA") == source
            and set(expected) - optional <= present)
    except (KeyError, ValueError, TypeError): pass
    report["retained_bytes"] = total
    seal()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--owner-outcome", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args(argv)
    return 0 if publish(args.root, args.output, owner_outcome=args.owner_outcome, source=args.source)["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
