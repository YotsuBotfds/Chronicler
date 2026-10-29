#!/usr/bin/env python3
"""Bounded saved-artifact readout for the fixed fourteen-role forecast study.

Only stdlib is imported. This reads original ordinary files and opaque native
checkpoint sections; it never imports the simulation/native extension, restores
a World, unpickles Python, samples RNG or calls a native getter. A small owner
summary cannot replace a missing original body. No efficacy score is produced.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zlib


ROLE_NAMES = (
    "legacy-default", "candidate-default", "candidate-off", "legacy-fixed", "candidate-fixed",
    "local-parent", "local-normal", "local-withheld", "local-reference",
    "exact-4", "exact-6", "exact-8", "exact-10", "exact-13",
)
CHECKPOINT_TURNS = {name: ([4] if name == "local-parent" else [26] if name == "local-reference"
    or name.startswith("exact-") and name != "exact-4" else [6, 8, 10, 13, 26] if name == "exact-4" else [])
    for name in ROLE_NAMES}
ORDINARY_PAIRS = [
    ("legacy-default", "candidate-default", None, False),
    ("candidate-default", "candidate-off", None, False),
    ("legacy-fixed", "candidate-fixed", None, False),
    ("local-parent", "local-reference", None, False),
    ("local-parent", "local-normal", 4, True),
    *[("local-reference", "exact-" + str(turn), turn, False) for turn in (4, 6, 8, 10, 13)],
]
MAGIC = b"\x89CHRONICLER-CKPT\r\n\x1a\n"
MAXIMA = {
    "max_member_bytes": 256 * 1024**2, "max_total_bytes": 2 * 1024**3,
    "max_files": 4096, "max_header_bytes": 1024**2,
    "max_native_raw_bytes": 256 * 1024**2, "max_native_total_bytes": 1024**3,
    "max_json_nodes": 2_000_000, "max_depth": 160,
}
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE = re.compile(r"[0-9a-f]{40}\Z")
_NATIVE_NAME = re.compile(r"native\.(agent|ecology|politics)\.(0|[1-9][0-9]*)\Z")
_SIDECAR = re.compile(r"validation_summary/(graph|needs|aggregate|community|economy)_turn_([0-9]{3,})\.json\Z")
_CHECKPOINT = re.compile(r"checkpoint_turn_(0|[1-9][0-9]*)\.ckpt\Z")
_RESERVED = {"~d", "~o", "~r", "~l", "~t", "~n"}
KINDS = {"AgentSimulator": ("agent", 1), "EcologySimulator": ("ecology", 2),
         "PoliticsSimulator": ("politics", 3)}
BASELINE = "94b308e65bf3c7febc41f09b73004b1db2056a1d"
BASELINE_PACKAGE = "1235282cff8707015ffa90e94018fe4e2dafdb4eaf818db28420e09fbed5a9c0"
NATIVE_SHA256 = "38dddb970b7e832ccaacced1a51df860cb7d7bbd73c137a3936ecd91a65d56a5"
NATIVE_BYTES = 13737112


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def _limits(registration):
    supplied = registration.get("budgets", {})
    require(type(supplied) is dict, "BUDGETS")
    result = {}
    for name, cap in MAXIMA.items():
        value = supplied.get(name, cap)
        require(type(value) is int and 0 < value <= cap, "BUDGET_VALUE")
        result[name] = value
    return result


def _name(name):
    require(type(name) is str and 0 < len(name) <= 4096 and "\\" not in name and "\x00" not in name, "PATH_NAME")
    path = PurePosixPath(name)
    require(not path.is_absolute() and str(path) == name
            and all(part not in ("", ".", "..") for part in path.parts), "PATH_COMPONENT")
    return path


def _path(root, name):
    relative = _name(name)
    current = Path(root)
    require(current.is_dir() and not current.is_symlink() and current.absolute() == current.resolve(), "ROOT_DIRECTORY")
    for part in relative.parts:
        current = current / part
        info = current.lstat()
        require(not stat.S_ISLNK(info.st_mode), "LINK_INPUT")
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "REGULAR_INPUT")
    return current


def _file_pin(path, limit):
    before = path.stat(follow_symlinks=False)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= limit, "FILE_BOUND")
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        require(os.fstat(stream.fileno()) == before, "FILE_OPEN_IDENTITY")
        while block := stream.read(min(1024**2, limit - count + 1)):
            count += len(block)
            require(count <= limit and count <= before.st_size, "FILE_GROWTH")
            digest.update(block)
        after = os.fstat(stream.fileno())
    require(before == after == path.stat(follow_symlinks=False) and count == before.st_size, "FILE_CHANGED")
    return {"bytes": count, "sha256": digest.hexdigest()}


def inventory(root, budgets=None):
    """Rehash every original ordinary member; includes logs and checkpoints."""
    bounds = dict(MAXIMA) if budgets is None else budgets
    root = Path(root)
    require(root.is_dir() and not root.is_symlink() and root.absolute() == root.resolve(), "INVENTORY_ROOT")
    files, total = {}, 0
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode), "INVENTORY_LINK")
        if stat.S_ISDIR(info.st_mode):
            continue
        require(stat.S_ISREG(info.st_mode), "INVENTORY_SPECIAL")
        name = path.relative_to(root).as_posix()
        _name(name)
        require(len(files) < bounds["max_files"], "INVENTORY_COUNT")
        value = _file_pin(path, bounds["max_member_bytes"])
        total += value["bytes"]
        require(total <= bounds["max_total_bytes"], "INVENTORY_BYTES")
        files[name] = value
    require(files, "EMPTY_INVENTORY")
    return files


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _float(text):
    value = float(text)
    require(math.isfinite(value), "JSON_NONFINITE")
    return value


def _json(raw, bounds):
    require(len(raw) <= bounds["max_member_bytes"], "JSON_BYTE_BOUND")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_float=_float,
                           parse_constant=lambda value: require(False, "JSON_NONFINITE"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Refused("JSON_PARSE") from exc
    _tree_bound(value, bounds)
    return value


def _tree_bound(value, bounds):
    pending, count = [(value, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        require(count <= bounds["max_json_nodes"] and depth <= bounds["max_depth"], "JSON_TREE_BOUND")
        if type(node) is dict:
            pending.extend((item, depth + 1) for item in node.values())
        elif type(node) is list:
            pending.extend((item, depth + 1) for item in node)
        elif type(node) is float:
            require(math.isfinite(node), "JSON_NONFINITE")


def _read_json(root, name, bounds):
    path = _path(root, name)
    original = _file_pin(path, bounds["max_member_bytes"])
    with path.open("rb") as stream:
        raw = stream.read(bounds["max_member_bytes"] + 1)
    require(len(raw) == original["bytes"] and hashlib.sha256(raw).hexdigest() == original["sha256"]
            and _file_pin(path, bounds["max_member_bytes"]) == original, "JSON_ORIGINAL_CHANGED")
    return _json(raw, bounds)


def _same(left, right):
    """Match source bundle_codec.same: types, dict/list order and signed zero."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return len(left) == len(right) and all(a == b and _same(x, y)
            for (a, x), (b, y) in zip(left.items(), right.items()))
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if type(left) is float:
        return left == right and (left != 0.0 or str(left) == str(right))
    return left == right


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _apply(previous, patch):
    """The existing v6 JSON patch protocol, with no product-module import."""
    if type(patch) is not dict:
        return patch
    if "~r" in patch:
        require(len(patch) == 1, "BUNDLE_REPLACEMENT")
        return patch["~r"]
    if type(previous) is dict:
        require(not (_RESERVED & patch.keys() - {"~d", "~o"}), "BUNDLE_OBJECT_PATCH")
        deleted = patch.get("~d")
        require(deleted is None or (type(deleted) is list and all(type(k) is str and k in previous for k in deleted)), "BUNDLE_DELETED")
        removed = set(deleted or [])
        result = {key: _apply(value, patch[key]) if key in patch else value
                  for key, value in previous.items() if key not in removed}
        for key, value in patch.items():
            if key not in previous and key not in _RESERVED:
                result[key] = value
        order = patch.get("~o")
        if order is not None:
            require(type(order) is list and len(order) == len(result)
                    and all(type(k) is str for k in order) and set(order) == set(result), "BUNDLE_ORDER")
            result = {key: result[key] for key in order}
        return result
    if type(previous) is list:
        require("~l" in patch and not (patch.keys() - {"~l", "~t", "~n"}), "BUNDLE_LIST_PATCH")
        result = list(previous)
        length = patch.get("~n")
        if length is not None:
            require(type(length) is int and 0 <= length <= len(result), "BUNDLE_LIST_LENGTH")
            del result[length:]
        changes = patch["~l"]
        require(type(changes) is list, "BUNDLE_LIST_CHANGES")
        for change in changes:
            require(type(change) is list and len(change) == 2 and type(change[0]) is int
                    and 0 <= change[0] < len(result), "BUNDLE_LIST_INDEX")
            result[change[0]] = _apply(result[change[0]], change[1])
        tail = patch.get("~t")
        require(tail is None or type(tail) is list, "BUNDLE_LIST_TAIL")
        if tail:
            result.extend(tail)
        return result
    require(not (_RESERVED & patch.keys()), "BUNDLE_SCALAR_PATCH")
    return patch


def decode_bundle(encoded, bounds):
    """Decode only the existing plain JSON history/v6 layout, never pickle."""
    require(type(encoded) is dict, "BUNDLE_OBJECT")
    metadata = encoded.get("metadata")
    require(type(metadata) is dict and metadata.get("bundle_version") in (5, 6), "BUNDLE_VERSION")
    require(not ("history" in encoded and "history_delta" in encoded), "BUNDLE_AMBIGUOUS_HISTORY")
    result = {}
    for key, value in encoded.items():
        if key == "history_delta":
            require(metadata["bundle_version"] == 6 and type(value) is list and len(value) <= 32, "BUNDLE_HISTORY_BOUND")
            history, previous = [], None
            for index, patch in enumerate(value):
                previous = patch if index == 0 else _apply(previous, patch)
                require(type(previous) is dict, "BUNDLE_SNAPSHOT")
                _tree_bound(previous, bounds)
                history.append(copy.deepcopy(previous))
            result["history"] = history
        elif key == "world_state" and type(value) is dict:
            world = dict(value)
            for field in ("events_timeline", "named_events"):
                if field in world and world[field] is None and field in encoded:
                    world[field] = copy.deepcopy(encoded[field])
            result[key] = world
        else:
            result[key] = copy.deepcopy(value)
    _tree_bound(result, bounds)
    require(type(result.get("history")) is list and len(result["history"]) == 26, "BUNDLE_HISTORY_COVERAGE")
    require([row.get("turn") for row in result["history"]] == list(range(1, 27)), "BUNDLE_SNAPSHOT_TURNS")
    return result


def checkpoint_summary(root, name, budgets=None):
    """Hash original CP and bounded complete native streams, never Python data.

    All packed sections (including Python) receive their original packed digest
    check. Python's declared raw_length is bounded but is not independently
    inflated/validated. Native raw_length and exact one-stream EOF are checked.
    """
    bounds = dict(MAXIMA) if budgets is None else budgets
    path = _path(root, name)
    original = _file_pin(path, bounds["max_member_bytes"])
    with path.open("rb") as stream:
        require(stream.read(len(MAGIC)) == MAGIC, "CP_MAGIC")
        length_raw = stream.read(4)
        require(len(length_raw) == 4, "CP_HEADER_LENGTH")
        length = struct.unpack("<I", length_raw)[0]
        require(0 < length <= bounds["max_header_bytes"], "CP_HEADER_BOUND")
        raw = stream.read(length)
        require(len(raw) == length, "CP_HEADER_TRUNCATED")
        header = _json(raw, bounds)
        require(type(header) is dict and header.get("format") == "chronicler-run-checkpoint"
                and type(header.get("version")) is int and header["version"] == 1, "CP_FORMAT")
        sections = header.get("sections")
        require(type(sections) is list and 1 <= len(sections) <= 16, "CP_SECTION_COUNT")
        offset, native_total, names, native_rows, packed_rows = 0, 0, [], [], []
        counters = {"agent": 0, "ecology": 0, "politics": 0}
        for index, section in enumerate(sections):
            require(type(section) is dict and set(section) == {"name", "codec", "offset", "length", "raw_length", "sha256"}, "CP_SECTION_FIELDS")
            member = section["name"]
            require(type(member) is str and member not in names, "CP_SECTION_NAME")
            names.append(member)
            require(type(section["offset"]) is int and section["offset"] == offset
                    and type(section["length"]) is int and 0 < section["length"] <= bounds["max_member_bytes"]
                    and type(section["raw_length"]) is int and 0 < section["raw_length"] <= bounds["max_native_raw_bytes"]
                    and type(section["sha256"]) is str and _HEX.fullmatch(section["sha256"]), "CP_SECTION_EXTENT")
            is_native = index > 0
            if not is_native:
                require(member == "python" and section["codec"] == "pickle5+zlib", "CP_PYTHON_SECTION")
            else:
                match = _NATIVE_NAME.fullmatch(member)
                require(match is not None and section["codec"] == "native+zlib", "CP_NATIVE_SECTION")
                kind, sequence = match.groups()
                require(int(sequence) == counters[kind], "CP_NATIVE_SEQUENCE")
                counters[kind] += 1
            packed_hash, unpacked_hash, remaining, unpacked = hashlib.sha256(), hashlib.sha256(), section["length"], 0
            prefix = bytearray()
            inflater = zlib.decompressobj() if is_native else None
            while remaining:
                block = stream.read(min(1024**2, remaining))
                require(block, "CP_TRUNCATED")
                remaining -= len(block)
                packed_hash.update(block)
                if inflater is not None:
                    try:
                        decoded = inflater.decompress(block, section["raw_length"] - unpacked + 1)
                    except zlib.error as exc:
                        raise Refused("CP_NATIVE_ZLIB") from exc
                    unpacked += len(decoded)
                    require(unpacked <= section["raw_length"] and not inflater.unconsumed_tail
                            and not inflater.unused_data, "CP_NATIVE_STREAM_BOUND")
                    unpacked_hash.update(decoded)
                    if len(prefix) < 21:
                        prefix.extend(decoded[:21 - len(prefix)])
            require(packed_hash.hexdigest() == section["sha256"], "CP_PACKED_DIGEST")
            packed_rows.append({"name": member, "bytes": section["length"], "sha256": packed_hash.hexdigest()})
            if inflater is not None:
                require(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail
                        and unpacked == section["raw_length"], "CP_NATIVE_EOF_LENGTH")
                native_total += unpacked
                require(native_total <= bounds["max_native_total_bytes"], "CP_NATIVE_TOTAL")
                require(len(prefix) == 21 and prefix[:8] == b"CHRNSTAT", "CP_NATIVE_MAGIC")
                version, native_kind, fingerprint = struct.unpack("<IBQ", prefix[8:])
                require(version == 1 and native_kind == {"agent": 1, "ecology": 2, "politics": 3}[kind],
                        "CP_NATIVE_VERSION_KIND")
                native_rows.append({"name": member, "bytes": unpacked, "sha256": unpacked_hash.hexdigest(),
                    "packed_bytes": section["length"], "packed_sha256": packed_hash.hexdigest(),
                    "original_native_prefix": {"magic": "CHRNSTAT", "version": version, "kind": native_kind,
                        "fingerprint": f"{fingerprint:016x}"}})
            offset += section["length"]
        require(not stream.read(1) and len(MAGIC) + 4 + length + offset == original["bytes"], "CP_TRAILING_BYTES")
    require(_file_pin(path, bounds["max_member_bytes"]) == original, "CP_CHANGED")
    require(native_rows, "CP_NATIVE_MISSING")
    return {"original_file": original, "header": header, "packed_sections": packed_rows,
            "native_sections": native_rows, "python_unpickled": False, "python_raw_length_verified": False}


def _ordinary_names(files):
    # Excluded files are still independently inventoried, never silently lost.
    excluded = {name for name in files if name.endswith(".log") or _CHECKPOINT.fullmatch(name)}
    return set(files) - excluded, sorted(excluded)


def compare_roles(left_root, right_root, left_files, right_files, *, split_turn=None,
                  compare_bundle=True, state_only=False, budgets=None):
    bounds = dict(MAXIMA) if budgets is None else budgets
    left_names, left_excluded = _ordinary_names(left_files)
    right_names, right_excluded = _ordinary_names(right_files)
    allowed_prefix = []
    if state_only:
        left_names, right_names = {"state.json"}, {"state.json"}
    elif split_turn is not None:
        require(type(split_turn) is int and split_turn in (4, 6, 8, 10, 13), "COMPARISON_SPLIT")
        for name in sorted(left_names - right_names):
            match = _SIDECAR.fullmatch(name)
            # These source-clock JSONs are sampled before world.turn increments.
            # In particular CP10 resumes source turn10 and must emit its sample.
            if match is not None and int(match.group(2)) < split_turn:
                allowed_prefix.append(name)
        left_names -= set(allowed_prefix)
    mismatches, compared = [], {}
    if left_names != right_names:
        mismatches.append({"code": "ORDINARY_FILE_SET", "left_only": sorted(left_names - right_names), "right_only": sorted(right_names - left_names)})
    for name in sorted(left_names & right_names):
        require(name in left_files and name in right_files, "COMPARISON_REQUIRED_FILE")
        if name == "chronicle_bundle.json" and compare_bundle and not state_only:
            left = decode_bundle(_read_json(left_root, name, bounds), bounds)
            right = decode_bundle(_read_json(right_root, name, bounds), bounds)
            for bundle in (left, right):
                stamp = bundle["metadata"].get("generated_at")
                require(type(stamp) is str and len(stamp) <= 128, "BUNDLE_GENERATED_AT")
                try:
                    require(datetime.fromisoformat(stamp).utcoffset() is not None, "BUNDLE_GENERATED_AT")
                except ValueError as exc:
                    raise Refused("BUNDLE_GENERATED_AT") from exc
                del bundle["metadata"]["generated_at"]
            equal = _same(left, right)
            compared[name] = {"equal": equal, "kind": "complete_decoded_v6_only_generated_at_removed",
                              "left_sha256": _digest(left), "right_sha256": _digest(right)}
        else:
            equal = left_files[name] == right_files[name]
            compared[name] = {"equal": equal, "kind": "original_raw_bytes",
                              "left": left_files[name], "right": right_files[name]}
        if not equal:
            mismatches.append({"code": "ORDINARY_CONTENT", "path": name})
    require("state.json" in compared and (state_only or "chronicle_bundle.json" in compared), "COMPARISON_MINIMUM")
    return {"equal": not mismatches, "files": compared, "mismatches": mismatches,
            "allowed_pre_split_source_clock_json_omissions": allowed_prefix,
            "separately_inventoried_exclusions": {"left": left_excluded, "right": right_excluded},
            "normalization": ["metadata.generated_at"] if compare_bundle and not state_only else []}


def _header_identity(header, role, observed, layouts):
    require(header.get("exact") is True and type(header.get("seed")) is int and header["seed"] == 42
            and type(header.get("turn")) is int and header["turn"] in role["checkpoint_turns"]
            and type(header.get("num_turns")) is int and header["num_turns"] == 26
            and type(header.get("start_turn")) is int and header["start_turn"] == 0, "CP_ROLE_BOUNDARY")
    identity = header.get("identity")
    source = {key: observed["source"].get(key) for key in ("git_sha", "package_digest")}
    native = {key: observed["native"].get(key) for key in ("status", "sha256", "bytes")}
    native["state_layouts"] = layouts
    environment = {key: observed["environment"].get(key) for key in (
        "python", "implementation", "machine", "affinity_cpu_count", "thread_env", "packages")}
    environment["hash_seed"] = observed["environment"].get("hash_seed",
        observed["environment"].get("thread_env", {}).get("PYTHONHASHSEED"))
    require(type(identity) is dict and identity.get("source") == source
            and identity.get("native") == native
            and identity.get("environment") == environment, "CP_ACTUAL_IDENTITY")
    flags = header.get("flags")
    require(type(flags) is dict and all(flags.get(key) is True for key in (
        "harvest_forecasts", "grain_reserves", "contact_ledger")) and all(flags.get(key) is False
        for key in ("health_care", "ritual_gatherings", "scientific_claims")), "CP_FORECAST_FLAGS")
    require(header.get("run_config", {}).get("resume_info") is None, "CP_EXACT_RESUME_INFO")
    expected = role.get("expected_header", {})
    require(type(expected) is dict, "CP_EXPECTED_HEADER")
    for key, value in expected.items():
        require(_same(header.get(key), value), "CP_REGISTERED_HEADER")
    lineage = header.get("lineage")
    require(type(lineage) is list and lineage == header.get("run_config", {}).get("lineage"), "CP_LINEAGE")
    expected_lineage = []
    if role["name"] == "exact-4":
        expected_lineage = [{"resumed_at": 4, "kind": "checkpoint", "exact": True}]
    elif role["name"].startswith("exact-"):
        expected_lineage = [{"resumed_at": 4, "kind": "checkpoint", "exact": True},
                            {"resumed_at": role["start_turn"], "kind": "checkpoint", "exact": True}]
    require(lineage == expected_lineage, "CP_REGISTERED_LINEAGE")


def _worker_identity(root, name, record, bounds):
    expected_path = "roles/" + name + "/worker_identity.json"
    require(record.get("worker_identity_path") == expected_path, "WORKER_IDENTITY_PATH")
    raw = _read_json(root, expected_path, bounds)
    require(type(raw) is dict and type(raw.get("schema_version")) is int and raw["schema_version"] == 2
            and raw.get("environment_stable") is True and raw.get("identities_stable") is True, "WORKER_IDENTITY_SCHEMA")
    expected_runner = record.get("runner_sha256")
    require(type(expected_runner) is str and _HEX.fullmatch(expected_runner)
            and raw.get("runner_sha256") == raw.get("runner_sha256_after") == expected_runner, "WORKER_RUNNER_PIN")
    before, after = raw.get("before"), raw.get("after")
    require(type(before) is dict and type(after) is dict and type(before.get("environment")) is dict
            and before["environment"] and before["environment"] == after.get("environment"), "WORKER_ENVIRONMENT")
    actual = record["identity"]
    for observation in (before, after):
        require(type(observation.get("source")) is dict and type(observation.get("native")) is dict, "WORKER_SOURCE_NATIVE")
        require(all(observation["source"].get(key) == actual["source"].get(key)
                    for key in ("git_sha", "package_digest")), "WORKER_SOURCE")
        require(all(observation["native"].get(key) == actual["native"].get(key)
                    for key in ("status", "sha256", "bytes")), "WORKER_NATIVE")
    require(before["environment"] == actual["environment"], "WORKER_RECORDED_ENVIRONMENT")
    return {"path": expected_path, "original_file": _file_pin(_path(root, expected_path), bounds["max_member_bytes"]),
            "runner_sha256": expected_runner, "runner_kind": raw.get("runner_kind", "stock_expansion_runner")}


def schema_layouts(schemas):
    """Check retained source-owned tuples and their FNV-1a descriptor relation.

    These are saved bootstrap assertions. Reading them is not a fresh native
    schema/class observation. CP prefixes are independently read from raw bytes.
    """
    require(type(schemas) is dict and set(schemas) == set(KINDS), "SCHEMA_KIND_SET")
    layouts = {}
    for name, (kind, _) in KINDS.items():
        row = schemas[name]
        require(type(row) is list and len(row) == 3 and type(row[0]) is int and row[0] == 1
                and type(row[1]) is str and re.fullmatch(r"[0-9a-f]{16}", row[1]) is not None
                and type(row[2]) is str and 0 < len(row[2].encode("utf-8")) <= 65536, "SCHEMA_TUPLE")
        fingerprint = 0xcbf29ce484222325
        for byte in row[2].encode("utf-8"):
            fingerprint = ((fingerprint ^ byte) * 0x100000001b3) & 0xffffffffffffffff
        require(row[1] == f"{fingerprint:016x}", "SCHEMA_DESCRIPTOR_FINGERPRINT")
        layouts[kind] = f"v{row[0]}:{row[1]}"
    return layouts


def _binding(registration):
    binding = registration.get("binding")
    require(type(binding) is dict and set(binding) == {"baseline", "candidate", "candidate_ci", "native"}, "SOURCE_BINDING")
    baseline, candidate, ci, native = (binding[key] for key in ("baseline", "candidate", "candidate_ci", "native"))
    require(type(baseline) is dict and baseline.get("source") == BASELINE
            and baseline.get("package_digest") == BASELINE_PACKAGE, "BASELINE_BINDING")
    require(type(candidate) is dict and type(candidate.get("source")) is str and _SOURCE.fullmatch(candidate["source"])
            and all(type(candidate.get(key)) is str and _HEX.fullmatch(candidate[key])
                    for key in ("package_digest", "runner_sha256", "pyproject_sha256", "lock_sha256")), "CANDIDATE_BINDING")
    require(type(ci) is dict and ci.get("source") == candidate["source"] and type(ci.get("run_id")) is int
            and ci["run_id"] > 0 and type(ci.get("attempt")) is int and ci["attempt"] == 1
            and ci.get("conclusion") == "success" and all(type(ci.get(key)) is str and _HEX.fullmatch(ci[key])
                for key in ("root_receipt_sha256", "independent_receipt_sha256")), "CANDIDATE_FULL_CI_BINDING")
    require(type(native) is dict and native.get("sha256") == NATIVE_SHA256
            and type(native.get("bytes")) is int and native["bytes"] == NATIVE_BYTES
            and native.get("crate") == "04866c3962ec9d5c77477fc727107a553fc1d6df", "NATIVE_BINDING")
    return binding


def _float_witness(value):
    return None if value is None else {"value": value, "binary64_hex": struct.pack(">d", float(value)).hex()}


def _finite(value, *, upper=None):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0 and (upper is None or value <= upper)


def forecast_trace(bundle, state, *, withheld=False):
    """Audit recorded local facts, with no reconstruction of hidden inputs.

    Natural report selection/contact candidates, raw production/demand and
    historical recipient population are not all in these exports. This audits
    the dates/arithmetic/joins that are present, and names those limits.
    """
    forecast = state.get("harvest_forecasts")
    require(type(forecast) is dict and forecast.get("preparation_policy") == "local_credibility"
            and forecast.get("policy") == ("withhold" if withheld else "normal"), "TRACE_POLICY")
    regions, civilizations = state.get("regions"), state.get("civilizations")
    require(type(regions) is list and len(regions) == 8 and type(civilizations) is list, "TRACE_GEOGRAPHY")
    snapshots = {row["turn"] - 1: row for row in bundle["history"]}
    immutable = ("id", "source_region", "source_region_name", "recipient_region", "recipient_region_name",
        "owner", "owner_name", "issued_turn", "delivery_turn", "expires_turn", "target_start", "target_end",
        "probability", "confidence", "predicted_ratio", "issued_event_id")
    catalog, status_chains, preparation = {}, {}, []
    for source_turn, snapshot in snapshots.items():
        section = snapshot.get("harvest_forecasts")
        require(type(section) is dict and type(section.get("source_turn")) is int
                and section["source_turn"] == source_turn, "TRACE_SOURCE_TURN")
        require(type(section.get("reports")) is list and type(section.get("outcomes")) is list, "TRACE_REPORT_ARRAYS")
        rows = section["reports"] + section["outcomes"]
        require(len(rows) <= 128, "TRACE_REPORT_BOUND")
        seen = set()
        for report in rows:
            require(type(report) is dict and type(report.get("id")) is str and report["id"] not in seen, "TRACE_REPORT_ID")
            seen.add(report["id"])
            key = report["id"]
            if key in catalog:
                prior = catalog[key]
                require(all(_same(report.get(field), prior.get(field)) for field in immutable), "TRACE_REPORT_IMMUTABLE")
                for field in ("delivered_turn", "delivered_event_id", "resolved_turn"):
                    if prior.get(field) not in (None, ""):
                        require(_same(report.get(field), prior[field]), "TRACE_REPORT_RECEIPT_CHANGED")
                previous_observations = prior.get("credibility_observations", [])
                require(_same(report.get("credibility_observations", [])[:len(previous_observations)], previous_observations),
                        "TRACE_OBSERVATIONS_REWRITTEN")
                if prior.get("status") in ("resolved", "unscored", "cancelled"):
                    require(_same(report, prior), "TRACE_TERMINAL_REPORT_CHANGED")
            else:
                require(report.get("issued_turn") == source_turn and report.get("status") == "pending", "TRACE_FIRST_REPORT_VIEW")
            require(type(report.get("issued_turn")) is int and report["issued_turn"] <= source_turn, "TRACE_REPORT_FUTURE")
            observations = report.get("credibility_observations", [])
            require(type(observations) is list and len(observations) <= 3
                    and all(type(pair) is list and len(pair) == 2 and type(pair[0]) is int and pair[0] <= source_turn
                            and _finite(pair[1]) for pair in observations), "TRACE_RECORDED_OBSERVATIONS")
            year = report["issued_turn"] // 12
            dates = [pair[0] for pair in observations]
            require(dates == sorted(set(dates)) and all(year * 12 + 9 <= turn <= year * 12 + 11 for turn in dates),
                    "TRACE_RECORDED_OBSERVATION_DATES")
            require(type(report.get("evaluation_count")) is int and 0 <= report["evaluation_count"] <= 3
                    and len(observations) <= report["evaluation_count"] and _finite(report.get("evaluation_sum")), "TRACE_EVALUATION_RECORD")
            status = report.get("status")
            require(status in ("pending", "delivered", "withheld", "resolved", "unscored", "cancelled"), "TRACE_STATUS")
            chain = status_chains.setdefault(key, [])
            if not chain or chain[-1]["status"] != status:
                if chain:
                    allowed = {"pending": {"delivered", "withheld", "cancelled"},
                               "delivered": {"resolved", "unscored", "cancelled"},
                               "withheld": {"resolved", "unscored", "cancelled"}}
                    require(status in allowed.get(chain[-1]["status"], set()), "TRACE_STATUS_TRANSITION")
                chain.append({"source_turn": source_turn, "status": status})
            catalog[key] = report
        require(type(section.get("preparedness")) is list and len(section["preparedness"]) <= 8, "TRACE_PREPARATION_BOUND")
        require(len({row.get("region") for row in section["preparedness"] if type(row) is dict})
                == len(section["preparedness"]), "TRACE_PREPARATION_REGION_UNIQUE")
        for row in section["preparedness"]:
            require(type(row) is dict, "TRACE_PREPARATION")
            preparation.append((source_turn, row, snapshot))
    require(len(catalog) <= 16 and len({(report["issued_turn"] // 12, report["recipient_region"])
            for report in catalog.values()}) == len(catalog), "TRACE_REPORT_YEAR_RECIPIENT")
    final_section = snapshots[25]["harvest_forecasts"]
    require(_same(forecast.get("reports"), final_section["reports"])
            and _same(forecast.get("outcomes"), final_section["outcomes"]), "TRACE_FINAL_REPORT_STATE")
    # The fixed two-year horizon has at most two reports per recipient and
    # therefore cannot evict a genuine local result from the four-entry memory.
    memory_by_recipient, evidence_count = {}, 0
    require(type(forecast.get("observers")) is list and len(forecast["observers"]) <= 8, "TRACE_OBSERVER_BOUND")
    for observer in forecast["observers"]:
        require(type(observer) is dict, "TRACE_OBSERVER")
        rid, rows = observer.get("region"), observer.get("credibility_memory", [])
        require(type(rid) is int and 0 <= rid < 8 and rid not in memory_by_recipient
                and type(rows) is list and len(rows) <= 4, "TRACE_MEMORY_BOUND")
        require(all(type(row) is dict for row in rows), "TRACE_MEMORY_ROW")
        require(len({row.get("report_id") for row in rows}) == len(rows)
                and all(a["issued_turn"] < b["issued_turn"] for a, b in zip(rows, rows[1:])), "TRACE_MEMORY_ORDER")
        memory_by_recipient[rid] = rows
        for row in rows:
            require(type(row) is dict and row.get("report_id") in catalog, "TRACE_MEMORY_REPORT")
            report = catalog[row["report_id"]]
            for field in ("source_region", "recipient_region", "owner", "owner_name", "issued_turn", "delivered_turn",
                          "resolved_turn", "probability", "observed_ratio", "outcome_shortfall", "brier",
                          "issued_event_id", "delivered_event_id"):
                require(_same(row.get(field), report.get(field)), "TRACE_MEMORY_REPORT_JOIN")
            require(row["recipient_region"] == rid and report.get("status") == "resolved", "TRACE_MEMORY_RECIPIENT")
            observations = row.get("observations")
            require(type(observations) is list and len(observations) == 3
                    and _same(observations, report.get("credibility_observations")), "TRACE_LOCAL_OBSERVATIONS")
            require(all(type(pair) is list and len(pair) == 2 and type(pair[0]) is int and _finite(pair[1])
                        for pair in observations), "TRACE_OBSERVATION_VALUES")
            year = row["issued_turn"] // 12
            require(row["report_id"] == f"harvest:{year}:{row['source_region']}:{rid}"
                    and row["issued_turn"] == year * 12 + 5
                    and [pair[0] for pair in observations] == [year * 12 + 9, year * 12 + 10, year * 12 + 11]
                    and type(row["delivered_turn"]) is int
                    and row["issued_turn"] < row["delivered_turn"] < year * 12 + 9
                    and row["delivered_turn"] >= row["issued_turn"] + (1 if row["source_region"] == rid else 2)
                    and type(row["resolved_turn"]) is int and row["resolved_turn"] > year * 12 + 11, "TRACE_LOCAL_DATES")
            total = 0.0
            for _, value in observations:
                total += value
            mean = total / 3
            shortfall = mean < 0.6
            require(report.get("evaluation_count") == 3 and _same(report.get("evaluation_sum"), total)
                    and _same(row["observed_ratio"], mean) and row["outcome_shortfall"] is shortfall
                    and _same(row["brier"], (row["probability"] - float(shortfall)) ** 2), "TRACE_LOCAL_ARITHMETIC")
            resolved = snapshots.get(row["resolved_turn"])
            require(resolved is not None and resolved.get("region_control", {}).get(regions[rid]["name"]) == row["owner_name"], "TRACE_RESOLUTION_OWNER")
            evidence_count += 1
    events = {}
    require(type(bundle.get("events_timeline")) is list, "TRACE_EVENT_TIMELINE")
    for event in bundle["events_timeline"]:
        require(type(event) is dict, "TRACE_EVENT_ROW")
        identifier = event.get("event_id")
        if identifier:
            require(identifier not in events, "TRACE_EVENT_ID")
            events[identifier] = event
    chains = []
    false_alarms = missed_warnings = scored = delivered = 0
    for identifier, report in catalog.items():
        rid, source, owner = report.get("recipient_region"), report.get("source_region"), report.get("owner")
        require(type(rid) is int and 0 <= rid < 8 and type(source) is int and 0 <= source < 8
                and type(owner) is int and 0 <= owner < len(civilizations)
                and civilizations[owner].get("name") == report.get("owner_name")
                and regions[rid].get("name") == report.get("recipient_region_name")
                and regions[source].get("name") == report.get("source_region_name"), "TRACE_REPORT_OWNERSHIP")
        issue = report["issued_turn"]
        year = issue // 12
        require(identifier == f"harvest:{year}:{source}:{rid}" and issue == year * 12 + 5
                and report.get("target_start") == year * 12 + 9 and report.get("target_end") == year * 12 + 11
                and report.get("expires_turn") == year * 12 + 11
                and report.get("delivery_turn") == issue + (1 if source == rid else 2)
                and _finite(report.get("probability"), upper=1) and _finite(report.get("confidence"), upper=1)
                and _finite(report.get("predicted_ratio")), "TRACE_REPORT_DATES_VALUES")
        issued_event = events.get(report.get("issued_event_id"))
        require(issued_event is not None and issued_event.get("event_type") == "harvest_forecast_issued"
                and issued_event.get("turn") == issue and issued_event.get("region") == report["recipient_region_name"]
                and issued_event.get("actors") == [report["owner_name"]], "TRACE_ISSUED_EVENT")
        delivery = report.get("delivered_turn")
        if delivery is not None:
            delivered += 1
            event = events.get(report.get("delivered_event_id"))
            require(type(delivery) is int and delivery >= report["delivery_turn"] and delivery <= report["expires_turn"]
                    and event is not None and event.get("event_type") == "harvest_forecast_delivered"
                    and event.get("turn") == delivery and report["issued_event_id"] in event.get("causes", [])
                    and event.get("region") == report["recipient_region_name"]
                    and event.get("actors") == [report["owner_name"]], "TRACE_DELIVERY_EVENT")
        resolved = report.get("resolved_turn")
        if report["status"] in ("resolved", "unscored", "cancelled"):
            require(type(resolved) is int and issue < resolved <= 25, "TRACE_RESOLVED_DATE")
            require(report["status"] == "cancelled" or resolved > report["expires_turn"], "TRACE_RESOLVED_BEFORE_EXPIRY")
            closure = [event for event in events.values() if event.get("event_type") == "harvest_forecast_resolved"
                and event.get("turn") == resolved and report["issued_event_id"] in event.get("causes", [])]
            require(len(closure) == 1 and closure[0].get("region") == report["recipient_region_name"]
                    and closure[0].get("actors") == [report["owner_name"]]
                    and (delivery is None or report["delivered_event_id"] in closure[0].get("causes", [])), "TRACE_RESOLUTION_EVENT")
        else:
            require(resolved is None, "TRACE_PREMATURE_RESOLVED_DATE")
        if report.get("brier") is not None:
            require(report.get("status") == "resolved" and report.get("evaluation_count") == 3
                    and _finite(report.get("evaluation_sum")) and _finite(report.get("observed_ratio"))
                    and _same(report["observed_ratio"], report["evaluation_sum"] / 3)
                    and type(report.get("outcome_shortfall")) is bool
                    and report["outcome_shortfall"] is (report["observed_ratio"] < 0.6)
                    and _same(report["brier"], (report["probability"] - float(report["outcome_shortfall"])) ** 2), "TRACE_GLOBAL_SCORE")
            scored += 1
            false_alarms += int(delivery is not None and report["probability"] >= 0.6 and report["outcome_shortfall"] is False)
            missed_warnings += int(delivery is not None and report["probability"] < 0.6 and report["outcome_shortfall"] is True)
        if withheld:
            require(delivery is None and not report.get("delivered_event_id")
                    and not report.get("credibility_observations"), "TRACE_WITHHELD_LOCAL_EXPOSURE")
        chains.append({"id": identifier, "issued_event_id": report["issued_event_id"],
            "delivered_event_id": report.get("delivered_event_id", ""), "statuses": status_chains[identifier],
            "source_region": source, "recipient_region": rid, "owner": owner,
            "issued_turn": issue, "delivered_turn": delivery, "resolved_turn": report.get("resolved_turn"),
            "probability": report["probability"], "brier": report.get("brier"),
            "outcome_shortfall": report.get("outcome_shortfall"),
            "recorded_local_observation_count": len(report.get("credibility_observations", [])),
            "recorded_local_observations": [[turn, _float_witness(value)] for turn, value in report.get("credibility_observations", [])],
            "float_witnesses": {key: _float_witness(report.get(key)) for key in
                ("probability", "confidence", "predicted_ratio", "evaluation_sum", "observed_ratio", "brier")}})
    used_rows, purchases, paid, actions = 0, 0.0, 0, []
    for source_turn, row, snapshot in preparation:
        rid, identifier = row.get("region"), row.get("forecast_id")
        require(type(rid) is int and 0 <= rid < 8 and identifier in catalog, "TRACE_ACTION_REPORT")
        report = catalog[identifier]
        require(row.get("preparation_policy") == "local_credibility"
                and report.get("recipient_region") == rid and row.get("owner") == report.get("owner")
                and row.get("owner_name") == report.get("owner_name") and report["probability"] >= 0.6
                and report.get("delivered_turn") is not None and report["delivered_turn"] <= source_turn
                and report["delivery_turn"] <= source_turn <= report["expires_turn"], "TRACE_ACTION_ELIGIBILITY")
        eligible = [evidence for evidence in memory_by_recipient.get(rid, [])
                    if evidence["source_region"] == report["source_region"] and evidence["owner"] == report["owner"]
                    and evidence["owner_name"] == report["owner_name"]
                    and evidence["resolved_turn"] < report["issued_turn"] <= source_turn]
        discount = (2.0 + sum(1.0 - evidence["brier"] for evidence in eligible)) / (2.0 + len(eligible))
        require(row.get("credibility_evidence_ids") == [evidence["report_id"] for evidence in eligible]
                and _same(row.get("credibility_discount"), discount), "TRACE_ACTION_DISCOUNT")
        require(all(_finite(row.get(key)) for key in ("base_target", "extra_target", "bought_during_warning"))
                and type(row.get("paid_during_warning")) is int and row["paid_during_warning"] >= 0, "TRACE_ACTION_NONNEGATIVE")
        grain = snapshot.get("grain_reserves")
        require(type(grain) is dict and grain.get("source_turn") == source_turn, "TRACE_GRAIN_SOURCE_TURN")
        granaries = {g["region"]: g for g in grain.get("granaries", [])}
        require(rid in granaries and granaries[rid].get("owner") == report["owner"]
                and _finite(granaries[rid].get("target"))
                and abs(granaries[rid]["target"] - row["base_target"] - row["extra_target"]) <= 1e-9, "TRACE_TARGET_ACCOUNTING")
        flows = [flow for flow in grain.get("flows", []) if flow.get("kind") == "bought" and flow.get("region") == rid]
        require(all(_finite(flow.get("amount")) and type(flow.get("cost")) is int and flow["cost"] >= 0 for flow in flows), "TRACE_PURCHASE_FLOWS")
        require(row["bought_during_warning"] == math.fsum(flow["amount"] for flow in flows)
                and row["paid_during_warning"] == sum(flow["cost"] for flow in flows)
                and all(flow.get("buyer") == report["owner"] for flow in flows), "TRACE_RECORDED_PURCHASE_JOIN")
        payment_events = [event for event in events.values() if event.get("event_type") == "harvest_preparedness"
            and event.get("turn") == source_turn and event.get("region") == report["recipient_region_name"]
            and report["delivered_event_id"] in event.get("causes", [])]
        require((not payment_events if row["paid_during_warning"] == 0 else len(payment_events) == 1
                 and payment_events[0].get("actors") == [report["owner_name"]]), "TRACE_PAYMENT_EVENT")
        used_rows += int(bool(eligible));purchases += row["bought_during_warning"];paid += row["paid_during_warning"]
        actions.append({"source_turn": source_turn, "region": rid, "forecast_id": identifier,
            "evidence_ids": row["credibility_evidence_ids"], "discount": discount,
            "base_target": row["base_target"], "extra_target": row["extra_target"],
            "bought_during_warning": row["bought_during_warning"], "paid_during_warning": row["paid_during_warning"],
            "float_witnesses": {key: _float_witness(row[key]) for key in
                ("credibility_discount", "base_target", "extra_target", "bought_during_warning")},
            "payment_event_ids": [event["event_id"] for event in payment_events]})
    if withheld:
        require(not evidence_count and not actions, "TRACE_WITHHELD_MEMORY_ACTION")
    return {"report_chains": chains, "preparation_actions": actions,
        "denominators": {"unique_reports": len(catalog), "delivered_reports": delivered, "scored_reports": scored,
            "local_memory_results": evidence_count, "actions": len(actions), "actions_using_prior_results": used_rows,
            "false_alarms": false_alarms, "missed_warnings": missed_warnings},
        "recorded_warning_purchases": purchases, "recorded_warning_payments": paid,
        "learning_use_coverage": "OBSERVED_RECORDED_JOIN" if used_rows else "UNOBSERVED",
        "false_alarm_coverage": "OBSERVED" if false_alarms else "UNOBSERVED",
        "missed_warning_coverage": "OBSERVED" if missed_warnings else "UNOBSERVED",
        "withheld_report_exposure": len(catalog) if withheld else None,
        "incomplete_window_reports": sum(report["status"] == "unscored" for report in catalog.values()),
        "cancelled_reports": sum(report["status"] == "cancelled" for report in catalog.values()),
        "owner_change_boundary_coverage": None,
        "owner_change_boundary_reason": "A source cancellation status alone does not independently establish its within-turn ownership timing.",
        "no_purchase_coverage": "UNOBSERVED" if not any(action["bought_during_warning"] > 0 for action in actions) else "OBSERVED_RECORDED_JOIN",
        "raw_production_demand_recomputation": None, "historical_recipient_population_revalidation": None,
        "treasury_balance_or_excess_purchase_causal_attribution": None,
        "interpretation": "Dates, local evidence arithmetic and available recorded flow/target joins only. Empty exposure is preserved; no efficacy, forecast-skill or favorable-seed claim."}


def read_study(root, registration, role_records):
    """Re-read the fixed study's original bodies and return mechanical facts.

    Call only after owned workers quiesce. Invalid bindings or unsafe inputs
    raise Refused; genuine content inequality is retained as a negative result.
    """
    require(type(registration) is dict and type(registration.get("schema_version")) is int and registration["schema_version"] == 1
            and type(registration.get("seed")) is int and registration["seed"] == 42
            and type(registration.get("horizon")) is int and registration["horizon"] == 26, "FIXED_REGISTRATION")
    roles = registration.get("roles")
    require(type(roles) is list and [row.get("name") for row in roles] == list(ROLE_NAMES), "FIXED_ROLE_ORDER")
    require(type(role_records) is dict and set(role_records) == set(ROLE_NAMES), "ROLE_RECORD_SET")
    bounds = _limits(registration)
    binding = _binding(registration)
    admission = _read_json(root, "admission.json", bounds)
    require(type(admission) is dict and type(admission.get("actual_Worlds")) is int
            and admission["actual_Worlds"] == 0 and type(admission.get("identity")) is dict, "BOOTSTRAP_RECORD")
    admitted_identity = admission["identity"]
    require(admitted_identity.get("source", {}).get("git_sha") == binding["candidate"]["source"]
            and admitted_identity["source"].get("package_digest") == binding["candidate"]["package_digest"]
            and admitted_identity.get("native", {}).get("sha256") == NATIVE_SHA256
            and admitted_identity["native"].get("bytes") == NATIVE_BYTES, "BOOTSTRAP_BINDING")
    schemas = admission.get("schemas")
    layouts = schema_layouts(schemas)
    require(_same(registration.get("bootstrap_schemas"), schemas), "REGISTERED_BOOTSTRAP_TUPLES")
    admission_pin = _file_pin(_path(root, "admission.json"), bounds["max_member_bytes"])
    observed_roles, checkpoints, decoded, states, total_bytes, total_files, ticks = {}, {}, {}, {}, 0, 0, 0
    for role in roles:
        name = role["name"]
        expected_start = int(name[6:]) if name.startswith("exact-") else (4 if name in ("local-normal", "local-withheld") else 0)
        require(role.get("directory") == "roles/" + name + "/ordinary" and type(role.get("start_turn")) is int
                and role["start_turn"] == expected_start and type(role.get("turns")) is int
                and role["turns"] == 26 and role.get("kind") == ("exact" if name.startswith("exact-") else "fork" if name in ("local-normal", "local-withheld") else "plain"), "ROLE_REGISTRATION")
        require(type(role.get("source")) is str and _SOURCE.fullmatch(role["source"])
                and type(role.get("package_digest")) is str and _HEX.fullmatch(role["package_digest"])
                and type(role.get("native_sha256")) is str and _HEX.fullmatch(role["native_sha256"]), "UNBOUND_ROLE_IDENTITY")
        alias = "baseline" if name in ("legacy-default", "legacy-fixed") else "candidate"
        require(role["source"] == binding[alias]["source"]
                and role["package_digest"] == binding[alias]["package_digest"]
                and role["native_sha256"] == binding["native"]["sha256"], "ROLE_SOURCE_BINDING")
        record = role_records[name]
        require(type(record) is dict, "ROLE_RECORD")
        if name in ("local-parent", "local-normal", "local-withheld", "local-reference"):
            require(record.get("entrypoint") == "normal_runner_job"
                    and record.get("runner_sha256") == binding["candidate"]["runner_sha256"], "ROLE_NORMAL_RUNNER_BINDING")
        else:
            require(record.get("entrypoint") == "stock_cli", "ROLE_STOCK_CLI_BINDING")
        require(type(record) is dict and record.get("status") == "complete" and record.get("returncode") == 0
                and record.get("completed_horizon") == 26 and record.get("start_turn") == expected_start
                and type(record.get("observed_ticks")) is int and record["observed_ticks"] == 26 - expected_start, "ROLE_NOT_COMPLETE")
        ticks += record["observed_ticks"]
        actual_identity = record.get("identity")
        require(type(actual_identity) is dict and type(actual_identity.get("source")) is dict
            and actual_identity["source"].get("git_sha") == role["source"]
            and actual_identity["source"].get("package_digest") == role["package_digest"]
            and actual_identity.get("native", {}).get("status") == "found"
            and actual_identity["native"].get("sha256") == role["native_sha256"]
            and type(actual_identity["native"].get("bytes")) is int and actual_identity["native"]["bytes"] > 0
            and type(actual_identity.get("environment")) is dict and actual_identity["environment"], "ROLE_ACTUAL_IDENTITY")
        require(_same(record.get("schemas"), schemas)
                and _same(actual_identity["environment"], admitted_identity.get("environment")), "ROLE_ADMITTED_SCHEMAS_ENVIRONMENT")
        worker_identity = _worker_identity(root, name, record, bounds)
        folder = Path(root) / role["directory"]
        files = inventory(folder, bounds)
        require(files == record.get("inventory"), "OBSERVED_INVENTORY_DIFFERS")
        total_bytes += sum(row["bytes"] for row in files.values());total_files += len(files)
        require(total_bytes <= bounds["max_total_bytes"] and total_files <= bounds["max_files"], "STUDY_AGGREGATE_BOUND")
        require({"state.json", "chronicle_bundle.json", "chronicle.md"} <= files.keys(), "ORDINARY_MINIMUM")
        bundle = decode_bundle(_read_json(folder, "chronicle_bundle.json", bounds), bounds)
        require(bundle["metadata"].get("seed") == 42 and bundle["metadata"].get("total_turns") == 26
                and bundle.get("world_state", {}).get("turn") == 26, "ORDINARY_HORIZON")
        state = _read_json(folder, "state.json", bounds)
        require(type(state) is dict and state.get("turn") == 26, "STATE_HORIZON")
        # A normal exact continuation inherits the original experiment receipt;
        # its bundle has no synthetic resume metadata. Fork labels remain real.
        if role["kind"] != "fork":
            require("resume" not in bundle["metadata"], "UNEXPECTED_RESUME_METADATA")
        else:
            require(bundle["metadata"].get("resume") == {"kind": "experiment-fork", "exact": False, "turn": 4}, "FORK_RESUME_METADATA")
        declared = role.get("checkpoint_turns")
        require(type(declared) is list and all(type(t) is int and 0 < t <= 26 for t in declared)
                and declared == CHECKPOINT_TURNS[name], "CP_DECLARATION")
        actual_cp = {name for name in files if _CHECKPOINT.fullmatch(name)}
        require(actual_cp == {f"checkpoint_turn_{turn}.ckpt" for turn in declared}, "CP_EXACT_FILE_SET")
        per_role = {}
        for cp_name in sorted(actual_cp):
            cp = checkpoint_summary(folder, cp_name, bounds)
            require(cp["original_file"] == files[cp_name], "CP_ORIGINAL_INVENTORY")
            _header_identity(cp["header"], role, actual_identity, layouts)
            for native_section in cp["native_sections"]:
                kind = _NATIVE_NAME.fullmatch(native_section["name"]).group(1)
                prefix = native_section["original_native_prefix"]
                require(layouts[kind] == f"v{prefix['version']}:{prefix['fingerprint']}", "CP_RAW_LAYOUT_ADMISSION_JOIN")
            per_role[cp_name] = cp
        checkpoints[name] = per_role
        decoded[name] = bundle
        states[name] = state
        observed_roles[name] = {"directory": role["directory"], "files": files,
            "original_body_bytes": sum(row["bytes"] for row in files.values()),
            "observed_ticks": record["observed_ticks"], "checkpoint_files": sorted(per_role), "worker_identity": worker_identity,
            "history_snapshots": len(bundle["history"]), "state_sha256": files["state.json"]["sha256"]}
    require(ticks == 315, "FIXED_TOTAL_TICKS")
    by_name = {row["name"]: row for row in roles}
    comparisons = []
    specs = registration.get("comparisons")
    require(type(specs) is list and [(s.get("left"), s.get("right"), s.get("split_turn"), s.get("state_only", False))
        for s in specs] == ORDINARY_PAIRS and all(s.get("compare_bundle", True) is True or s.get("state_only") is True
        for s in specs) and all(type(s.get("state_only", False)) is bool and type(s.get("compare_bundle", True)) is bool
        for s in specs), "FIXED_ORDINARY_COMPARISONS")
    for spec in specs:
        require(type(spec) is dict and spec.get("left") in by_name and spec.get("right") in by_name, "COMPARISON_ROLES")
        left, right = spec["left"], spec["right"]
        comparison = compare_roles(Path(root) / by_name[left]["directory"], Path(root) / by_name[right]["directory"],
            observed_roles[left]["files"], observed_roles[right]["files"], split_turn=spec.get("split_turn"),
            compare_bundle=spec.get("compare_bundle", True), state_only=spec.get("state_only", False), budgets=bounds)
        comparisons.append({"name": spec["name"], "left": left, "right": right, **comparison})
    native_comparisons = []
    native_specs = registration.get("checkpoint_comparisons")
    require(type(native_specs) is list and [(s.get("left_role"), s.get("left_path"), s.get("right_role"), s.get("right_path"), s.get("turn"))
        for s in native_specs] == [("local-reference", "checkpoint_turn_26.ckpt", "exact-" + str(turn), "checkpoint_turn_26.ckpt", 26)
        for turn in (4, 6, 8, 10, 13)], "FIXED_NATIVE_COMPARISONS")
    for spec in native_specs:
        left = checkpoints[spec["left_role"]][spec["left_path"]]
        right = checkpoints[spec["right_role"]][spec["right_path"]]
        for cp in (left, right):
            require(cp["header"]["turn"] == spec["turn"], "NATIVE_COMPARISON_TURN")
            for key, expected in spec.get("expected_header", {}).items():
                require(_same(cp["header"].get(key), expected), "NATIVE_COMPARISON_HEADER")
        a = [{key: row[key] for key in ("name", "bytes", "sha256")} for row in left["native_sections"]]
        b = [{key: row[key] for key in ("name", "bytes", "sha256")} for row in right["native_sections"]]
        same_layout = left["header"]["identity"]["native"]["state_layouts"] == right["header"]["identity"]["native"]["state_layouts"]
        native_comparisons.append({"name": spec["name"], "equal": a == b and same_layout,
            "left_original": left["original_file"], "right_original": right["original_file"],
            "left_native_sections": a, "right_native_sections": b, "layout_equal": same_layout,
            "scope": "original_complete_emitted_native_serialized_sections_only"})
    # Mechanical success cannot be manufactured by an empty comparison list.
    require(len(comparisons) == 10 and len(native_comparisons) == 5, "FIXED_COMPARISON_COUNT")
    traces = {name: forecast_trace(decoded[name], states[name], withheld=name == "local-withheld")
              for name in ("local-parent", "local-normal", "local-withheld", "local-reference",
                           "exact-4", "exact-6", "exact-8", "exact-10", "exact-13")}
    return {"schema_version": 1, "kind": "forecast-credibility-mechanical-readout",
        "complete": all(row["equal"] for row in comparisons + native_comparisons),
        "roles": observed_roles, "actual_roles": 14, "actual_physics_ticks": ticks,
        "ordinary_comparisons": comparisons, "native_checkpoint_comparisons": native_comparisons,
        "forecast_traces": traces,
        "checkpoints": checkpoints, "original_body_bytes": total_bytes, "original_file_count": total_files,
        "metadata_only_native_claim": False, "full_graph_equivalence": None,
        "global_rng_equivalence": None, "raw_economy_contact_candidate_evidence": None,
        "bootstrap_full_descriptor_independent_verification": None,
        "retained_bootstrap_metadata": {"path": "admission.json", "original_file": admission_pin,
            "tuples_match_registered_and_all_roles": True, "descriptor_fingerprints_recomputed": True,
            "layout_references": layouts, "scope": "source_owned_saved_assertions_not_fresh_native_observation"},
        "limits": ["Original raw checkpoint files were required and rehashed; no small metadata record substitutes for them.",
            "Only complete emitted native serialized sections are decompressed/compared; Python pickle graph, private caches and RNG are unobserved.",
            "CP headers expose layout version:fingerprint references, not the separately observed full bootstrap descriptors.",
            "Full decoded-v6 ordinary identity retains types/key/event order and signed zero; only metadata.generated_at is removed.",
            "Logs/manifests/checkpoints remain inventoried provenance, not ordinary physics identity. No efficacy, skill, realism, speedup or adoption verdict."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("registration", type=Path)
    parser.add_argument("role_records", type=Path)
    args = parser.parse_args(argv)
    bounds = dict(MAXIMA)
    # The owner owns publication/atomic writes and captures this bounded stdout.
    registration = _read_json(args.registration.absolute().parent, args.registration.name, bounds)
    records = _read_json(args.role_records.absolute().parent, args.role_records.name, bounds)
    result = read_study(args.root, registration, records)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
