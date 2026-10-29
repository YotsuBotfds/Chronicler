#!/usr/bin/env python3
"""Copy a closed metadata allowlist byte-for-byte under fixed publication caps.

No simulation artifact is parsed, summarized or adjudicated. Full raw evidence
remains authoritative and is uploaded separately, including when staging fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

MAX_BYTES = 8 * 1024**2
MAX_FILES = 32
OUTPUT_NAME = "natural-research-light"
ALLOWLIST = (
    "natural-research-contracts/junit.xml", "natural-research-contracts/guard.json",
    "natural-research-wheel/build-manifest.json", "natural-research-wheel/verification.json",
    "natural-research-wheel/failure.json", "natural-research-wheel/incomplete-verification.json",
    "natural-research-freeze.json",
    "natural-research-evidence/execution.json", "natural-research-evidence/execution-receipt.json",
    "natural-research-evidence/admission.json", "natural-research-evidence/pending-execution-receipt.json",
    "natural-research-evidence/incomplete-execution.json", "natural-research-evidence/incomplete-execution-receipt.json",
    "natural-research-evidence/incomplete-pending-execution-receipt.json",
    "natural-research-evidence/incomplete-finalization-execution-receipt.json",
    "natural-research-readout/readout.json", "natural-research-readout/receipt.json", "natural-research-readout/completion.json",
    "natural-research-readout/pending-receipt.json", "natural-research-readout/pending-completion.json",
    "natural-research-readout/incomplete-readout.json", "natural-research-readout/incomplete-receipt.json",
    "natural-research-readout/incomplete-completion.json", "natural-research-readout/incomplete-pending-receipt.json",
    "natural-research-readout/incomplete-pending-completion.json",
    "natural-research-readout/incomplete-1-readout.json", "natural-research-readout/incomplete-1-receipt.json",
    "natural-research-readout/incomplete-1-completion.json", "natural-research-readout/incomplete-1-pending-receipt.json",
    "natural-research-readout/incomplete-1-pending-completion.json",
)
assert len(ALLOWLIST) == len(set(ALLOWLIST)) <= MAX_FILES - 1
assert all(not Path(n).is_absolute() and not set(Path(n).parts) & {".", ".."} for n in ALLOWLIST)


class StagingRefused(ValueError):
    pass


def require(condition):
    if not condition:
        raise StagingRefused("bounded metadata staging refused")


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def open_relative(root_fd, name, *, writing=False):
    """Anchor every directory and final file without following links."""
    current = os.dup(root_fd)
    try:
        parts = name.split("/")
        for part in parts[:-1]:
            if writing:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL if writing else os.O_RDONLY | os.O_NONBLOCK
        fd = os.open(parts[-1], flags | os.O_NOFOLLOW, 0o600, dir_fd=current)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise StagingRefused("metadata source is not a regular file")
        return fd
    finally:
        os.close(current)


def source_record(root_fd, name, *, hashing=True):
    try:
        fd = open_relative(root_fd, name)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(before.st_size <= MAX_BYTES)
        digest, count = hashlib.sha256(), 0
        if hashing:
            while block := stream.read(min(64 * 1024, before.st_size + 1 - count)):
                count += len(block)
                require(count <= before.st_size)
                digest.update(block)
            require(count == before.st_size and stamp(before) == stamp(os.fstat(stream.fileno())))
        return dict(stamp=stamp(before), bytes=before.st_size, sha256=digest.hexdigest() if hashing else None)


def encoded(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()


def index_bytes(records):
    payload_bytes = sum(r["bytes"] for r in records if r["status"] == "copied")
    value = dict(schema_version=1, kind="natural-research-light-artifacts", staging_complete=True,
        scientific_qualification=False, limits=dict(bytes=MAX_BYTES, files=MAX_FILES),
        file_count=1 + sum(r["status"] == "copied" for r in records), total_bytes=0, index_bytes=0, files=records)
    for _ in range(16):
        raw = encoded(value)
        if value["index_bytes"] == len(raw) and value["total_bytes"] == payload_bytes + len(raw):
            return raw
        value.update(index_bytes=len(raw), total_bytes=payload_bytes + len(raw))
    raise StagingRefused("index size did not converge")


def admit(payload_bytes, metadata_bytes, file_count):
    require(type(payload_bytes) is int and type(metadata_bytes) is int and type(file_count) is int)
    require(payload_bytes >= 0 and metadata_bytes >= 0 and payload_bytes + metadata_bytes <= MAX_BYTES
            and 1 <= file_count <= MAX_FILES)


def copy_file(source_fd, output_fd, name, expected):
    with os.fdopen(open_relative(source_fd, name), "rb") as source:
        require(stamp(os.fstat(source.fileno())) == expected["stamp"])
        with os.fdopen(open_relative(output_fd, name, writing=True), "wb") as destination:
            count, digest = 0, hashlib.sha256()
            while block := source.read(min(64 * 1024, expected["bytes"] + 1 - count)):
                count += len(block)
                require(count <= expected["bytes"])
                digest.update(block)
                destination.write(block)
            require(count == expected["bytes"] and digest.hexdigest() == expected["sha256"]
                    and stamp(os.fstat(source.fileno())) == expected["stamp"])


def write_index(output_fd, raw):
    with os.fdopen(open_relative(output_fd, "pending-index.json", writing=True), "wb") as stream:
        stream.write(raw)
    os.replace("pending-index.json", "index.json", src_dir_fd=output_fd, dst_dir_fd=output_fd)


def closed_output_inventory(output_fd, expected):
    """Visit only the finite expected directory trie; reject before descent."""
    children = {"": {}}
    for name in expected:
        parent = ""
        parts = name.split("/")
        for component in parts[:-1]:
            children[parent][component] = "directory"
            parent = parent + "/" + component if parent else component
            children.setdefault(parent, {})
        children[parent][parts[-1]] = "file"
    entry_limit = len(expected) + len(children) - 1
    seen_count, file_count, total_bytes = 0, 0, 0

    def visit(directory_fd, prefix):
        nonlocal seen_count, file_count, total_bytes
        before, seen = os.fstat(directory_fd), set()
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                seen_count += 1
                require(seen_count <= entry_limit and entry.name not in seen and entry.name in children[prefix])
                seen.add(entry.name)
                name = prefix + "/" + entry.name if prefix else entry.name
                info = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
                if children[prefix][entry.name] == "directory":
                    require(stat.S_ISDIR(info.st_mode))
                    child_fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                    try:
                        require(stamp(info)[:2] == stamp(os.fstat(child_fd))[:2])
                        visit(child_fd, name)
                    finally:
                        os.close(child_fd)
                else:
                    require(stat.S_ISREG(info.st_mode) and info.st_size == expected[name]["bytes"])
                    file_count += 1
                    total_bytes += info.st_size
                    require(file_count <= MAX_FILES and total_bytes <= MAX_BYTES)
        require(seen == set(children[prefix]) and stamp(before) == stamp(os.fstat(directory_fd)))

    visit(output_fd, "")
    require(file_count == len(expected) and total_bytes == sum(row["bytes"] for row in expected.values()))
    return file_count, total_bytes


def roots_stable(source, source_fd, source_identity, output, output_fd, output_identity):
    for path, fd, identity in ((source, source_fd, source_identity), (output, output_fd, output_identity)):
        actual = os.stat(path, follow_symlinks=False)
        require(stat.S_ISDIR(actual.st_mode) and stamp(actual)[:2] == identity == stamp(os.fstat(fd))[:2])


def stage(source_root, output_root):
    source, output = Path(source_root), Path(output_root)
    require(source.is_absolute() and source == source.resolve() and source.is_dir())
    require(output == source / OUTPUT_NAME and not output.exists() and not output.is_symlink())
    source_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    source_identity = stamp(os.fstat(source_fd))[:2]
    output_fd = None
    copied_bytes, copied_files = 0, 0
    try:
        # Admit the complete source set by lengths before hashing or copying.
        preliminary = {name: source_record(source_fd, name, hashing=False) for name in ALLOWLIST}
        selected = [r for r in preliminary.values() if r is not None]
        require(sum(r["bytes"] for r in selected) <= MAX_BYTES and len(selected) + 1 <= MAX_FILES)
        observed = {name: source_record(source_fd, name) for name in ALLOWLIST}
        require(all((preliminary[n] is None and observed[n] is None) or preliminary[n] is not None
            and observed[n] is not None and preliminary[n]["stamp"] == observed[n]["stamp"] for n in ALLOWLIST))
        records = [dict(path=name, status="missing") if observed[name] is None else
            dict(path=name, status="copied", bytes=observed[name]["bytes"], sha256=observed[name]["sha256"]) for name in ALLOWLIST]
        raw = index_bytes(records)
        # The fixed negative index is smaller than this complete allowlist index.
        admit(sum(r["bytes"] for r in selected), len(raw), len(selected) + 1)
        output.mkdir(mode=0o700)
        output_fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        output_identity = stamp(os.fstat(output_fd))[:2]
        for name in ALLOWLIST:
            if observed[name] is not None:
                copy_file(source_fd, output_fd, name, observed[name])
                copied_bytes += observed[name]["bytes"]
                copied_files += 1
        # Rehash every source, including confirming missing paths stayed missing.
        require(observed == {name: source_record(source_fd, name) for name in ALLOWLIST})
        for name, expected in observed.items():
            if expected is not None:
                actual = source_record(output_fd, name)
                require(actual is not None and all(actual[k] == expected[k] for k in ("bytes", "sha256")))
        require(stamp(os.stat(output, follow_symlinks=False))[:2] == output_identity)
        write_index(output_fd, raw)
        require(observed == {name: source_record(source_fd, name) for name in ALLOWLIST})
        expected_output = {name: dict(bytes=row["bytes"], sha256=row["sha256"]) for name, row in observed.items() if row is not None}
        expected_output["index.json"] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        roots_stable(source, source_fd, source_identity, output, output_fd, output_identity)
        closed_output_inventory(output_fd, expected_output)
        for name, expected in expected_output.items():
            if name != "index.json":
                actual = source_record(output_fd, name)
                require(actual is not None and all(actual[k] == expected[k] for k in ("bytes", "sha256")))
        closed_output_inventory(output_fd, expected_output)
        staged_index = source_record(output_fd, "index.json")
        require(staged_index is not None and all(staged_index[k] == expected_output["index.json"][k] for k in ("bytes", "sha256")))
        roots_stable(source, source_fd, source_identity, output, output_fd, output_identity)
        # No scientific verdict or record is changed by successful staging.
        return 0
    except BaseException:
        if output_fd is None:
            output.mkdir(mode=0o700)
            output_fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        # Keep all copied bytes. The single derived index slot becomes negative;
        # adding a second index would violate the 32-file cap at its boundary.
        try:
            os.replace("pending-index.json", "index.json", src_dir_fd=output_fd, dst_dir_fd=output_fd)
        except FileNotFoundError:
            pass
        negative = encoded(dict(schema_version=1, kind="natural-research-light-artifacts", staging_complete=False,
            scientific_qualification=False, completed_copy_files=copied_files, completed_copy_bytes=copied_bytes,
            error="staging_refused"))
        # This fixed negative record is smaller than the admitted full index.
        # With no copies, it is also the only file created after admission fails.
        if len(negative) <= MAX_BYTES:
            try:
                fd = os.open("index.json", os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK | os.O_NOFOLLOW,
                    0o600, dir_fd=output_fd)
                with os.fdopen(fd, "wb") as stream:
                    require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode))
                    os.ftruncate(stream.fileno(), 0)
                    stream.write(negative)
            except BaseException:
                pass
        return 1
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(source_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args(argv)
    require(os.environ.get("RUNNER_TEMP") is not None and Path(args.source_root) == Path(os.environ["RUNNER_TEMP"]))
    return stage(Path(args.source_root), Path(args.output_root))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Light artifact staging refused: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
