"""Bounded stdlib records for the inactive, timing-only current6a2 diagnostic.

This module never imports a project/native module or decodes an output body.
Exact ordinary-byte observations cannot qualify the old090 profile contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

PRODUCER_SOURCE = "6a2a7b84b7d6ea10bfa4f6574e1f5dc793c092e8"
PRODUCER_DIGEST = "513b1087cfb977306df70075118b78c082644f2bade337c68934d08b6b318a53"
NATIVE_SHA256 = "1ec3282dd43bc1ecfa2459960f19047aec5d8744406b5655aef44202585eaf72"

PROTOCOL = "current6a2-timing-only-v1"
SUMMARY_BYTES = 64 * 1024
DETAIL_BYTES = 8 * 1024**2
METADATA_BYTES = 64 * 1024**2
METADATA_FILES = 128
ROLE_BYTES = 512 * 1024**2
TOTAL_BYTES = 3 * 1024**3
TOTAL_FILES = 5000
HASH_CHUNK = 1024**2
MAX_ENTRIES = 10000
MAX_DEPTH = 64
UNKNOWN = {name: None for name in (
    "accepted090_profile", "full_graph_equal", "checkpoint_equivalence",
    "global_RNG_equivalence", "default_trajectory_parity", "semantic_output_equal",
    "actual_native_ticks", "actual_native_population", "actual_schema_tuples",
    "Rust_internal_hotspots", "live_RSS_PSS", "per_phase_allocations",
    "profiler_overhead_correction", "controlled_speedup", "scientific_efficacy",
    "adoption", "main_promotion", "durable_original_body_qualification",
)}


def metadata_names():
    names = ["owner-summary.json", "terminal.json", "terminal-failure.json", "initial-rng.json"]
    for leaf in ("summary.json", "detail.json", "detail-status.json", "ordinary-inventory.json"):
        names += [f"roles/{i}/{leaf}" for i in range(6)]
    for case in ("small", "agents", "regions"):
        names += [f"comparisons/{case}.json", f"comparisons/{case}-status.json"]
    return tuple(names)


class Refused(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def integer(value, low=0, high=2**63 - 1):
    require(type(value) is int and low <= value <= high, "integer domain")
    return value


def seconds(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            "finite nonnegative seconds")
    return value


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw, limit=DETAIL_BYTES):
    require(type(raw) is bytes and len(raw) <= limit, "JSON byte cap")
    def invalid(_value):
        raise Refused("nonfinite JSON")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Refused("invalid bounded JSON") from exc
    require(type(value) is dict, "JSON object required")
    stack = [(value, 0)]
    visited = 0
    while stack:
        item, depth = stack.pop()
        visited += 1
        require(visited <= 1000000 and depth <= 64, "JSON structure bound")
        if type(item) is float:
            require(math.isfinite(item), "nonfinite JSON number")
        elif type(item) is dict:
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
    return value


def absolute(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts and str(path) == os.path.normpath(str(path)),
            "canonical absolute path")
    for parent in reversed(path.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode), "symlink or non-directory ancestor")
    return path


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def hash_regular(path, limit, *, guard=lambda: None, include_identity=False):
    """One descriptor hash; link/type/identity changes refuse, including ancestors."""
    path = absolute(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "regular unique file")
    require(0 <= before.st_size <= limit, "file byte cap")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    count, hashed = 0, hashlib.sha256()
    try:
        require(_identity(os.fstat(descriptor)) == _identity(before), "file changed before open")
        while True:
            guard()
            chunk = os.read(descriptor, min(HASH_CHUNK, limit + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            require(count <= limit, "actual read byte cap")
            hashed.update(chunk)
        after = os.fstat(descriptor)
        require(_identity(after) == _identity(before) and count == before.st_size,
                "file changed during read")
    finally:
        os.close(descriptor)
    require(_identity(path.lstat()) == _identity(before), "file changed after read")
    result = {"bytes": count, "sha256": hashed.hexdigest()}
    if include_identity:
        result["identity"] = list(_identity(before))
    return result


def read_json(path, limit=DETAIL_BYTES):
    pin = hash_regular(path, limit)
    descriptor = os.open(absolute(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(descriptor, min(HASH_CHUNK, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
    finally:
        os.close(descriptor)
    require(len(raw) == pin["bytes"] and hashlib.sha256(raw).hexdigest() == pin["sha256"],
            "JSON changed between bounded reads")
    return strict_json(bytes(raw), limit)


def write_new(path, value, limit=SUMMARY_BYTES, *, guard=lambda: None):
    """Immutable atomic commit. Failed .writing data remains; nothing is overwritten."""
    path = absolute(path)
    raw = canonical(value)
    require(len(raw) <= limit, "serialized JSON byte cap")
    pending = path.with_name(path.name + ".writing")
    guard()
    with pending.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    guard()
    os.link(pending, path, follow_symlinks=False)
    pending.unlink()
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    guard()
    pin = hash_regular(path, limit, guard=guard)
    require(pin == {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
            "committed JSON identity")
    return pin


def inventory(root, *, maximum_bytes=ROLE_BYTES, maximum_files=TOTAL_FILES,
              guard=lambda: None):
    """Closed names and streaming bytes after owned quiescence; no body decoding."""
    root = absolute(root)
    first = root.lstat()
    require(stat.S_ISDIR(first.st_mode), "inventory root directory")
    integer(maximum_bytes, 0, TOTAL_BYTES)
    integer(maximum_files, 0, TOTAL_FILES)
    files, identities, visited, total = {}, {}, 0, 0
    def walk(directory, parts):
        nonlocal visited, total
        require(len(parts) <= MAX_DEPTH, "inventory depth cap")
        guard()
        before = directory.lstat()
        require(stat.S_ISDIR(before.st_mode), "inventory directory type")
        with os.scandir(directory) as entries:
            names = sorted(entry.name for entry in entries)
        visited += len(names)
        require(visited <= MAX_ENTRIES, "inventory entry cap")
        for name in names:
            guard()
            require(name not in ("", ".", "..") and not any(c in name for c in ("\\", "\0")),
                    "unsafe inventory name")
            relative = "/".join((*parts, name))
            try:
                require(len(relative.encode("utf-8")) <= 2048, "inventory path byte cap")
            except UnicodeError as exc:
                raise Refused("inventory UTF8 path") from exc
            path = directory / name
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                walk(path, (*parts, name))
            else:
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                        "inventory special or aliased file")
                require(len(files) < maximum_files, "inventory file cap")
                pin = hash_regular(path, maximum_bytes - total, guard=guard, include_identity=True)
                total += pin["bytes"]
                identities[relative] = pin.pop("identity")
                files[relative] = pin
        with os.scandir(directory) as entries:
            after_names = sorted(entry.name for entry in entries)
        require(after_names == names and _identity(directory.lstat()) == _identity(before),
                "inventory directory changed")
    walk(root, ())
    require(_identity(root.lstat()) == _identity(first), "inventory root changed")
    return {"files": files, "identities": identities, "root_identity": [first.st_dev, first.st_ino],
            "bytes": total, "count": len(files), "visited_entries": visited}


def stat_inventory(root, *, maximum_bytes=TOTAL_BYTES, maximum_files=TOTAL_FILES,
                   guard=lambda: None):
    """Closed type/name/identity/size rescan without reading any body a second time."""
    root = absolute(root)
    integer(maximum_bytes, 0, TOTAL_BYTES)
    integer(maximum_files, 0, TOTAL_FILES)
    files, visited, total = {}, 0, 0
    def walk(directory, parts):
        nonlocal visited, total
        require(len(parts) <= MAX_DEPTH, "stat inventory depth")
        guard()
        before = directory.lstat()
        require(stat.S_ISDIR(before.st_mode), "stat directory type")
        with os.scandir(directory) as entries:
            names = sorted(entry.name for entry in entries)
        visited += len(names)
        require(visited <= MAX_ENTRIES, "stat visited entry cap")
        for name in names:
            guard()
            require(name not in ("", ".", "..") and not any(c in name for c in ("\\", "\0")),
                    "stat unsafe name")
            relative = "/".join((*parts, name))
            require(len(relative.encode("utf-8")) <= 2048, "stat UTF8 path cap")
            path = directory / name
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                walk(path, (*parts, name))
            else:
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "stat special or aliased file")
                require(len(files) < maximum_files and 0 <= info.st_size <= maximum_bytes - total,
                        "stat aggregate file/byte cap")
                total += info.st_size
                files[relative] = list(_identity(info))
        with os.scandir(directory) as entries:
            after_names = sorted(entry.name for entry in entries)
        require(after_names == names and _identity(directory.lstat()) == _identity(before),
                "stat directory changed")
    before = root.lstat()
    walk(root, ())
    require(_identity(root.lstat()) == _identity(before), "stat root changed")
    return {"identities": files, "root_identity": [before.st_dev, before.st_ino],
            "bytes": total, "count": len(files), "visited_entries": visited}


def validate_inventory(value):
    require(type(value) is dict and set(value) == {"files", "identities", "root_identity", "bytes", "count", "visited_entries"},
            "closed ordinary inventory fields")
    files, identities = value["files"], value["identities"]
    require(type(files) is dict and type(identities) is dict and set(files) == set(identities),
            "ordinary map identity membership")
    integer(value["count"], 0, TOTAL_FILES)
    require(len(files) == value["count"], "ordinary file count")
    integer(value["visited_entries"], value["count"], MAX_ENTRIES)
    integer(value["bytes"], 0, ROLE_BYTES)
    require(type(value["root_identity"]) is list and len(value["root_identity"]) == 2,
            "ordinary root identity")
    for item in value["root_identity"]:
        integer(item, 0, 2**64 - 1)
    total = 0
    for name, pin in files.items():
        require(type(name) is str and not name.startswith("/") and "\\" not in name
                and all(part not in ("", ".", "..") for part in name.split("/"))
                and len(name.encode("utf-8")) <= 2048, "ordinary map path")
        require(type(pin) is dict and set(pin) == {"bytes", "sha256"}, "ordinary pin fields")
        integer(pin["bytes"], 0, ROLE_BYTES)
        require(type(pin["sha256"]) is str and re.fullmatch("[0-9a-f]{64}", pin["sha256"]), "ordinary SHA256")
        identity = identities[name]
        require(type(identity) is list and len(identity) == 7, "ordinary file identity")
        for item in identity:
            integer(item, 0, 2**64 - 1)
        require(stat.S_ISREG(identity[2]) and identity[3] == 1 and identity[4] == pin["bytes"],
                "ordinary unique regular size")
        total += pin["bytes"]
    require(total == value["bytes"], "ordinary map byte total")
    return value


def compare_inventories(left, right):
    validate_inventory(left); validate_inventory(right)
    a, b = left["files"], right["files"]
    differences = [name for name in sorted(a.keys() | b.keys()) if a.get(name) != b.get(name)]
    require(len(a) <= TOTAL_FILES and len(b) <= TOTAL_FILES, "ordinary comparison file cap")
    return {"kind": "EXACT_ORDINARY_HASH_OBSERVATION", "protocol": PROTOCOL,
            "exact_file_set_and_bytes_equal": not differences, "difference_paths": differences,
            "normalization": None, "body_decoding": False, "unknown": dict(UNKNOWN)}


def validate_summary(value):
    require(type(value) is dict and set(value) == {"kind", "protocol", "request", "identity", "execute_run_returned",
        "role_complete", "completed_world_turn_boundaries", "closed_windows", "execute_run_clock",
        "process_lifetime_peak_RSS_bytes", "RSS_scope", "profiled", "bare_CLI_baseline", "failure_code", "unknown"},
        "closed role summary fields")
    require(type(value) is dict and value.get("kind") == "TIMING_ONLY_ROLE_SUMMARY"
            and value.get("protocol") == PROTOCOL, "distinct diagnostic summary kind")
    require(value.get("unknown") == UNKNOWN and all(v is None for v in value["unknown"].values()),
            "unqualified field promoted")
    request = value.get("request")
    expected = []
    for case, regions, target, roles in (("small", 12, 2000, ("plain", "profiled")),
            ("agents", 12, 20000, ("profiled", "plain")), ("regions", 48, 20000, ("plain", "profiled"))):
        for role in roles:
            expected.append(dict(index=len(expected), case=case, regions=regions,
                aggregate_target_request=target, role=role, seed=42, civilizations=4, requested_turns=97))
    require(type(request) is dict and request in expected
            and all(type(request.get(k)) is int for k in ("index", "regions", "aggregate_target_request", "seed", "civilizations", "requested_turns"))
            and type(request.get("case")) is str and type(request.get("role")) is str,
            "exact registered summary request")
    require(type(value.get("execute_run_returned")) is bool and type(value.get("role_complete")) is bool,
            "summary completion booleans")
    require(type(value.get("profiled")) is bool and value["profiled"] == (request["role"] == "profiled")
            and value.get("bare_CLI_baseline") is False, "instrumentation scope")
    code = value.get("failure_code")
    require(code in (None, "CLOCK_READ_FAILED", "RESOURCE_READ_FAILED", "STOP_FAILED", "EXECUTE_RAISED",
                     "OBSERVED_ROLE_BUDGET", "INCOMPLETE_BOUNDARIES"), "closed role failure code")
    require((code is None) == value["role_complete"], "role status code")
    identity = value.get("identity")
    required_identity = {"producer_source", "source_digest", "native_sha256", "native_bytes", "compiled_classes",
                         "runtime_flags", "actual_schema_tuples", "installed_new_API_execution", "initial_rng_input_sha256"}
    require(type(identity) is dict and set(identity) == required_identity
            and identity["producer_source"] == PRODUCER_SOURCE and identity["source_digest"] == PRODUCER_DIGEST
            and identity["native_sha256"] == NATIVE_SHA256 and type(identity["native_bytes"]) is int
            and identity["native_bytes"] == 13765672
            and identity["compiled_classes"] == ["AgentSimulator", "EcologySimulator", "PoliticsSimulator"]
            and identity["actual_schema_tuples"] is None and identity["installed_new_API_execution"] is None,
            "exact current6a2 identity and held schema/API")
    require(type(identity["initial_rng_input_sha256"]) is str
            and re.fullmatch("[0-9a-f]{64}", identity["initial_rng_input_sha256"]), "initial RNG input digest")
    flags = identity["runtime_flags"]
    require(type(flags) is dict and set(flags) == {"safe_path", "no_user_site", "ignore_environment", "isolated",
                "hash_randomization", "logical_CPUs", "affinity_CPUs", "RSS_unit", "python"}
            and flags["safe_path"] is True and flags["no_user_site"] is True
            and flags["ignore_environment"] is False and flags["isolated"] is False
            and flags["hash_randomization"] is False
            and type(flags["logical_CPUs"]) is int and flags["logical_CPUs"] == 1
            and type(flags["affinity_CPUs"]) is int and flags["affinity_CPUs"] == 1
            and flags["RSS_unit"] == "LinuxKiB" and type(flags["python"]) is str
            and flags["python"].startswith("3.13.") and len(flags["python"].encode("utf-8")) <= 4096,
            "admitted runtime flag identity")
    observed = value.get("completed_world_turn_boundaries")
    require(observed is None or type(observed) is int and 0 <= observed <= 97,
            "witnessed boundary count")
    require(not value["role_complete"] or value["execute_run_returned"] and observed == 97,
            "completion requires actual return and boundaries")
    clock = value.get("execute_run_clock")
    require(type(clock) is dict and set(clock) == {"cpu_seconds", "wall_seconds"}, "run clock fields")
    for item in clock.values():
        if item is None:
            require(not value["role_complete"] and code == "CLOCK_READ_FAILED", "unknown clock requires clock failure")
        else:
            seconds(item)
    peak = value.get("process_lifetime_peak_RSS_bytes")
    if peak is None:
        require(not value["role_complete"] and code in ("RESOURCE_READ_FAILED", "CLOCK_READ_FAILED"),
                "unknown RSS requires read failure")
    else:
        integer(peak)
    if value["role_complete"]:
        require(clock["cpu_seconds"] <= 240 and clock["wall_seconds"] <= 300 and peak <= 2 * 1024**3,
                "complete role observed limits")
    require(value.get("RSS_scope") == "Linux process-lifetime high-water, including imports/setup/exports",
            "RSS scope")
    windows = value.get("closed_windows")
    require(type(windows) is list and len(windows) <= 2, "closed windows cap")
    seen = []
    for window in windows:
        require(type(window) is dict and set(window) == {"start", "end", "cpu_seconds", "wall_seconds"},
                "window fields")
        pair = (window["start"], window["end"])
        require(pair in ((8, 16), (88, 96)) and pair not in seen, "registered unique windows")
        seen.append(pair)
        seconds(window["cpu_seconds"]); seconds(window["wall_seconds"])
    require(not value["role_complete"] or seen == [(8, 16), (88, 96)], "complete windows")
    return value


def validate_metadata_leaf(name, value):
    require(name in metadata_names(), "registered metadata leaf only")
    if name.endswith("/summary.json"):
        return validate_summary(value)
    if name.endswith("ordinary-inventory.json"):
        return validate_inventory(value)
    if name.endswith("-status.json"):
        require(set(value) == {"available", "reason"} and type(value["available"]) is bool,
                "closed optional status")
        expected = "PROFILE_DETAIL_REFUSED" if name.endswith("detail-status.json") else "BOUNDED_COMPARISON_REFUSED"
        require(value["reason"] is None if value["available"] else value["reason"] == expected,
                "optional status reason")
        return value
    kinds = {"owner-summary.json": "TIMING_ONLY_OWNER_SUMMARY", "terminal.json": "TIMING_ONLY_TERMINAL",
             "terminal-failure.json": "TIMING_ONLY_TERMINAL_FAILURE", "initial-rng.json": "TIMING_ONLY_INITIAL_RNG_INPUT"}
    kind = "TIMING_ONLY_COMPLETE_PROFILE_DETAIL" if name.endswith("detail.json") else (
        "EXACT_ORDINARY_HASH_OBSERVATION" if name.startswith("comparisons/") else kinds.get(name))
    require(value.get("kind") == kind and value.get("protocol") == PROTOCOL and value.get("unknown") == UNKNOWN,
            "known metadata kind/protocol and unqualified fields")
    if name.endswith("detail.json"):
        require(value.get("table_complete") is True and type(value.get("profiled")) is bool
                and value.get("timer") == "time.process_time floating CPU seconds"
                and value.get("timer_event_overhead_measured") is False
                and value.get("native_internal_attribution") is None
                and value.get("unresolved_label_coverage_is_zero") is False,
                "profile clock/coverage scope")
        rows, edges = value.get("function_rows"), value.get("selected_caller_edges")
        require(type(rows) is list and len(rows) <= 40000 and type(edges) is list and len(edges) <= 80000,
                "profile complete table/edge bounds")
        keys = set()
        per_window = [0, 0]
        def function_key(item):
            require(type(item) is dict and set(item) == {"filename", "line", "function"}, "profile key fields")
            require(type(item["filename"]) is str and type(item["function"]) is str
                    and len(item["filename"].encode("utf-8")) <= 2048
                    and len(item["function"].encode("utf-8")) <= 2048, "bounded profile labels")
            integer(item["line"])
            return (item["filename"], item["line"], item["function"])
        def counters(item):
            integer(item["primitive_calls"]); integer(item["calls"])
            require(item["calls"] >= item["primitive_calls"], "profile call count ordering")
            seconds(item["self_cpu_seconds"]); seconds(item["cumulative_cpu_seconds"])
        for row in rows:
            require(type(row) is dict and set(row) == {"window", "filename", "line", "function",
                    "primitive_calls", "calls", "self_cpu_seconds", "cumulative_cpu_seconds"}, "profile row fields")
            integer(row["window"], 0, 1)
            key = (row["window"], function_key({key: row[key] for key in ("filename", "line", "function")}))
            require(key not in keys, "duplicate profile function row")
            keys.add(key)
            per_window[row["window"]] += 1
            require(per_window[row["window"]] <= 20000, "per-window profile row cap")
            counters(row)
        per_window = [0, 0]
        edge_keys = set()
        for edge in edges:
            require(type(edge) is dict and set(edge) == {"window", "callee", "caller", "primitive_calls", "calls",
                    "self_cpu_seconds", "cumulative_cpu_seconds"}, "selected edge fields")
            integer(edge["window"], 0, 1)
            callee, caller = function_key(edge["callee"]), function_key(edge["caller"])
            key = (edge["window"], callee, caller)
            require((edge["window"], callee) in keys and key not in edge_keys, "selected edge membership/duplicates")
            edge_keys.add(key)
            per_window[edge["window"]] += 1
            require(per_window[edge["window"]] <= 40000, "per-window caller edge cap")
            counters(edge)
    return value


def publish_metadata(source, output, *, owner_step_outcome="unknown"):
    """Copy only the preregistered metadata leaves; ordinary bodies stay local."""
    source, output = absolute(source), absolute(output)
    require(owner_step_outcome in ("unknown", "success", "failure", "cancelled", "skipped"),
            "closed actual owner-step outcome")
    require(not output.exists(), "fresh publication directory")
    output.mkdir()
    names = metadata_names()
    present, missing, total = {}, [], 0
    for name in names:
        path = source / name
        if not path.exists() and not path.is_symlink():
            missing.append(name)
            continue
        limit = DETAIL_BYTES if name.endswith(("detail.json", "ordinary-inventory.json")) else SUMMARY_BYTES
        raw_value = read_json(path, limit)
        validate_metadata_leaf(name, raw_value)
        raw = canonical(raw_value)
        require(hash_regular(path, limit) == {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
                "source metadata must retain exact canonical original bytes")
        total += len(raw)
        require(total + SUMMARY_BYTES <= METADATA_BYTES and len(present) + 1 < METADATA_FILES,
                "joint metadata reserve")
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        present[name] = write_new(target, raw_value, limit)
    status = {"kind": "TIMING_ONLY_METADATA_PUBLICATION", "protocol": PROTOCOL,
              "present": present, "missing": missing, "selected_bytes": total,
              "unknown": dict(UNKNOWN), "metadata_only": True,
              "owner_step_outcome": owner_step_outcome,
              "original_body_retention": None}
    write_new(output / "publication.json", status, SUMMARY_BYTES)
    return status


def read_publication(root):
    """Bounded metadata-only receiver; official origin and archive acceptance remain NULL."""
    root = absolute(root)
    observed = stat_inventory(root, maximum_bytes=METADATA_BYTES, maximum_files=METADATA_FILES)
    index_pin = hash_regular(root / "publication.json", SUMMARY_BYTES)
    status = read_json(root / "publication.json", SUMMARY_BYTES)
    require(status.get("kind") == "TIMING_ONLY_METADATA_PUBLICATION" and status.get("protocol") == PROTOCOL
            and status.get("unknown") == UNKNOWN and status.get("metadata_only") is True,
            "metadata-only publication kind/unknowns")
    present = status.get("present")
    require(type(present) is dict and set(present) <= set(metadata_names())
            and set(observed["identities"]) == set(present) | {"publication.json"},
            "closed metadata publication set")
    missing = status.get("missing")
    require(type(missing) is list and all(type(name) is str for name in missing)
            and len(missing) == len(set(missing)) and set(missing) == set(metadata_names()) - set(present),
            "closed missing metadata membership")
    total = 0
    for name, pin in present.items():
        require(type(name) is str and name in observed["identities"]
                and pin == hash_regular(root / name, DETAIL_BYTES),
                "published metadata pin")
        total += pin["bytes"]
        limit = DETAIL_BYTES if name.endswith(("detail.json", "ordinary-inventory.json")) else SUMMARY_BYTES
        value = read_json(root / name, limit)
        validate_metadata_leaf(name, value)
        if "unknown" in value:
            require(value["unknown"] == UNKNOWN, "published unqualified field promoted")
    require(total == status.get("selected_bytes"), "published metadata byte total")
    complete = False
    if status.get("owner_step_outcome") == "success" and "terminal-failure.json" not in present:
        require("terminal.json" in present and "owner-summary.json" in present, "completed metadata authorities")
        owner = read_json(root / "owner-summary.json", SUMMARY_BYTES)
        terminal = read_json(root / "terminal.json", SUMMARY_BYTES)
        require(terminal.get("owner_summary") == present["owner-summary.json"], "terminal owner digest")
        if owner.get("matrix_complete") is True and terminal.get("matrix_complete") is True:
            require(owner.get("whole_owner_cleanup_certified") is True and terminal.get("whole_owner_cleanup_certified") is True
                    and owner.get("errors") == [], "completed source-owned cleanup")
            require(type(owner.get("completed_roles")) is list and len(owner["completed_roles"]) == 6,
                    "six completed role records")
            for index in range(6):
                name = f"roles/{index}/summary.json"
                require(name in present, "missing completed role summary")
                summary = validate_summary(read_json(root / name, SUMMARY_BYTES))
                require(summary["request"]["index"] == index and summary["role_complete"] is True,
                        "distinct witnessed complete role")
                require(owner.get("producer_source") == PRODUCER_SOURCE
                        and type(owner.get("control_source")) is str
                        and re.fullmatch("[0-9a-f]{40}", owner["control_source"]), "owner current producer/control source")
                completed = owner["completed_roles"][index]
                require(type(completed) is dict and set(completed) == {"index", "request", "completed_world_turn_boundaries",
                    "actual_native_ticks", "actual_native_population", "ordinary_bytes_hashed"}
                    and type(completed["index"]) is int and completed["index"] == index
                    and completed["request"] == summary["request"]
                    and type(completed["completed_world_turn_boundaries"]) is int
                    and completed["completed_world_turn_boundaries"] == summary["completed_world_turn_boundaries"] == 97
                    and completed["actual_native_ticks"] is None and completed["actual_native_population"] is None,
                    "owner/role witnessed boundaries and unknown native counts")
                integer(completed["ordinary_bytes_hashed"], 0, ROLE_BYTES)
                if index == 0:
                    common_identity = summary["identity"]
                else:
                    require(summary["identity"] == common_identity, "identical admitted role identity/RNG input")
            complete = True
    require(hash_regular(root / "publication.json", SUMMARY_BYTES) == index_pin,
            "publication index changed during receiver")
    for name, pin in present.items():
        require(hash_regular(root / name, DETAIL_BYTES) == pin, "metadata changed at receiver closure")
    require(stat_inventory(root, maximum_bytes=METADATA_BYTES, maximum_files=METADATA_FILES) == observed,
            "metadata names/identity changed at receiver closure")
    return {"kind": "TIMING_ONLY_METADATA_READOUT", "protocol": PROTOCOL,
            "source_owned_matrix_completion_claim": complete,
            "official_origin_or_original_archive_qualification": None,
            "unknown": dict(UNKNOWN)}


def main():
    # These limits apply only to this fresh CLI, never on metadata-module import.
    import resource
    import signal
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read-publication", type=Path)
    parser.add_argument("--owner-step-outcome", choices=("unknown", "success", "failure", "cancelled", "skipped"), default="unknown")
    args = parser.parse_args()
    require(sys.platform == "linux", "bounded metadata CLI requires Linux")
    reading = args.read_publication is not None
    require(reading and args.source is None and args.output is None or
            not reading and args.source is not None and args.output is not None, "one metadata CLI operation")
    cpu, wall = (30, 60) if reading else (10, 20)
    for kind, maximum in ((resource.RLIMIT_AS, 256 * 1024**2), (resource.RLIMIT_CPU, cpu),
                          (resource.RLIMIT_FSIZE, DETAIL_BYTES)):
        _soft, hard = resource.getrlimit(kind)
        selected = maximum if hard == resource.RLIM_INFINITY else min(maximum, hard)
        resource.setrlimit(kind, (selected, selected))
    def deadline(_signal, _frame):
        raise Refused("metadata CLI wall cap")
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(wall)
    try:
        result = read_publication(args.read_publication) if reading else publish_metadata(
            args.source, args.output, owner_step_outcome=args.owner_step_outcome)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    main()
