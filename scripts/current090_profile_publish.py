"""Bounded metadata-only late publication; never imports producer or opens CP bodies."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

MEMBER_LIMIT = 8 * 1024**2
TOTAL_LIMIT = 64 * 1024**2
FILE_LIMIT = 128


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
    # Fixed semantic keep set. No glob/rglob, raw CP, Arrow, state JSON, wheel,
    # installer cache, or ordinary simulation bundle is read by this publisher.
    paths = ["result.json", "terminal.json", "terminal-failure.json", "admission.json", "input-before.json",
             "input-after.json", "progress.jsonl", "pure-preflight/receipt.json", "pure-preflight/junit.xml",
             "pure-preflight/pytest.log", "pure-preflight/oracle-list.txt"]
    cases = ("small", "small", "agents", "agents", "regions", "regions")
    roles = ("plain", "profiled", "profiled", "plain", "plain", "profiled")
    paths += [f"roles/{index}-{case}-{role}/role.json" for index, (case, role) in enumerate(zip(cases, roles))]
    paths += [case + "-comparison.json" for case in ("small", "agents", "regions")]
    return paths


def publish(root, output, *, owner_outcome, source):
    if not root.is_absolute() or not output.is_absolute() or root == output or root in output.parents:
        raise ValueError("disjoint absolute publication paths")
    if output.exists() or output.is_symlink(): raise ValueError("fresh publication required")
    output.mkdir(parents=True)
    report = {"complete": False, "metadata_only": True, "source_publication_qualified": False,
              "owner_step_outcome": owner_outcome, "source": source, "files": {}, "omissions": [],
              "raw_payload_retained": False, "scope": "Copied fixed metadata only; no original-body repeat proof."}
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
        terminal = json.loads(retained["terminal.json"])
        result = json.loads(retained["result.json"])
        expected = selected_paths()
        optional = {"terminal-failure.json"}
        present = set(retained)
        report["complete"] = (owner_outcome == "success" and terminal.get("complete") is True
            and terminal.get("cleanup_complete") is True and terminal.get("required_wrapper_exit") == 0
            and "terminal-failure.json" not in present
            and not (root / "terminal-failure.json").exists() and not (root / "terminal-failure.json").is_symlink()
            and terminal.get("result_sha256") == hashlib.sha256(retained["result.json"]).hexdigest()
            and result.get("complete") is True and result.get("instrumentation_equal") is True
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
