"""Bounded metadata and original-role upload eligibility; no product/CP decoder.

The raw action uploads existing files directly. Local eligibility, action output
and later independent original-ZIP acceptance are separate evidence states.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import resource
import signal
import shutil
import stat
import sys
import time

MEMBER_LIMIT = 8 * 1024**2
TOTAL_LIMIT = 16 * 1024**2
FILE_LIMIT = 128
GIB = 1024**3
ROLE_BYTES = 128 * 1024**2
ROLE_FILES = 256
LOG_BYTES = 2 * 1024**2
ROOT_BYTES = 2 * GIB
ROOT_FILES = 4096
MANIFEST_BYTES = 4 * 1024**2
PLAN_BYTES = 64 * 1024
PREPARE_WALL = 30
PREPARE_CPU = 20
METADATA_WALL = 20
METADATA_CPU = 10
PUBLICATION_AS = 256 * 1024**2
METADATA_TAIL_WALL = 1.0
METADATA_TAIL_CPU = 0.25
MAX_ENTRIES = 10000
MAX_DEPTH = 64
PATH_BYTES = 512
ROLE_NAMES = ("legacy-default", "candidate-default", "candidate-off", "legacy-fixed", "candidate-fixed",
    "local-parent", "local-normal", "local-withheld", "local-reference", "exact-4", "exact-6", "exact-8", "exact-10", "exact-13")
STARTS = (0, 0, 0, 0, 0, 0, 4, 4, 0, 4, 6, 8, 10, 13)
AUTHORITIES = frozenset(("result.json", "terminal.json", "terminal-failure.json"))
MANIFEST = "raw-retention-manifest.json"
PLAN = "raw-retention-plan.json"
RAW_LOGS = tuple("logs/role-" + str(index) + ".log" for index in range(14))
REASONS = frozenset(("RAW_ROOT", "RAW_PATH", "RAW_ALIAS", "RAW_SYMLINK", "RAW_MEMBER", "RAW_SCAN",
    "RAW_CHANGED", "RAW_HASH_CAP", "RAW_METADATA_CAP", "RAW_DEADLINE", "RAW_CPU", "RAW_SOURCE", "RAW_CLOCK",
    "RAW_CLEANUP", "RAW_INVENTORY", "RAW_FIXED_PATHS", "RAW_CASEFOLD", "RAW_ROLE_CAP", "RAW_ROLE_STATUS",
    "RAW_BINDING", "RAW_JOINT_CAP", "RAW_OUTPUT", "RAW_OCCUPIED", "RAW_PLAN", "RAW_UPLOAD_RESERVE", "RAW_REFUSED"))
UPLOAD_CLIENT = {"source_review_sha256": "074c5f325232d4e0756b22579ce15172684bbbd044ab90bfd11e27a7e3e1912e",
    "bundled_source_sha256": "0165b8a75330f3228f2c7a234b4ff8a107b9139c2b519147f4c8e9fe99b262d8",
    "conditional_client_zip_bytes_max": 1887243378, "conditional_central_directory_bytes_max": 2000430,
    "upload_concurrency": 1, "buffer_pool_bytes_max": 8 * 1024**2,
    "backend_original_archive_equivalence": None, "backend_original_archive_size": None, "total_RSS": None,
    "scope": "Pinned client source only. Internal SDK/Azure HTTP retries may occur; no zero-HTTP-retry claim."}
PLAN_FIELDS = frozenset(("schema_version", "kind", "complete", "raw_eligible", "source", "control_producer", "boot_id",
    "monotonic_deadline", "manifest", "expected_artifact_name", "matrix_state", "refusal_code", "observed_selected_bytes",
    "observed_selected_files", "joint_accounting", "phase", "raw_original_artifact_qualified", "scope"))
MANIFEST_FIELDS = frozenset(("schema_version", "kind", "control_producer", "runtime_binding", "registration_sha256",
    "source_pins_sha256", "owner_result_sha256", "owner_terminal_sha256", "matrix_state", "raw_eligible", "refusal_code",
    "role_status", "members", "observed_selected_bytes", "observed_selected_files", "original_authorities",
    "original_name_order_sha256", "original_file_identities", "joint_accounting", "raw_original_artifact_qualified",
    "upload_client", "independent_reason"))


class Refused(ValueError):
    def __init__(self, code):
        if code not in REASONS: raise ValueError("unregistered raw refusal")
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition: raise Refused(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


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


def _sha(value, length=64):
    return type(value) is str and len(value) == length and all(c in "0123456789abcdef" for c in value)


def _stable(info):
    return tuple(getattr(info, name) for name in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))


def _canonical_root(path):
    require(isinstance(path, Path) and path.is_absolute() and path == path.resolve()
            and not path.is_symlink() and all(not parent.is_symlink() for parent in path.parents), "RAW_ROOT")
    return path


def _relative(name):
    require(type(name) is str and 0 < len(name.encode("utf-8")) <= PATH_BYTES and "\\" not in name and "\x00" not in name, "RAW_PATH")
    path = PurePosixPath(name)
    require(not path.is_absolute() and str(path) == name and all(part not in ("", ".", "..") for part in path.parts), "RAW_PATH")
    return name


def read_regular(path, limit=MEMBER_LIMIT):
    for parent in path.parents:
        if parent.is_symlink(): raise ValueError("metadata symlink parent")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 <= before.st_size <= limit:
            raise ValueError("metadata type/size")
        pieces, size = [], 0
        while block := os.read(descriptor, min(1024**2, limit - size + 1)):
            size += len(block)
            if size > limit: raise ValueError("metadata member cap")
            pieces.append(block)
        if _stable(before) != _stable(os.fstat(descriptor)) or _stable(before) != _stable(path.stat(follow_symlinks=False)) or size != before.st_size:
            raise ValueError("metadata changed")
        return b"".join(pieces)
    finally: os.close(descriptor)


class Budget:
    """One publication mode's finite intake/walk/time counters; no child runner."""
    def __init__(self, wall, cpu, *, now=None, cpu_now=None, cpu_origin=None, enforce_os=False):
        self.now = time.monotonic if now is None else now
        self.cpu_now = _cpu if cpu_now is None else cpu_now
        self.started, self.cpu_started = self.now(), self.cpu_now()
        self.cpu_origin = self.cpu_started if cpu_origin is None else cpu_origin
        self.deadline, self.cpu_limit = self.started + wall, cpu
        self.enforce_os = enforce_os
        self.entries = self.hashed = self.metadata_bytes = 0

    def check(self):
        require(self.now() <= self.deadline, "RAW_DEADLINE")
        require(self.cpu_now() - self.cpu_origin <= self.cpu_limit, "RAW_CPU")

    def read(self, path, limit=MEMBER_LIMIT):
        self.check()
        raw = read_regular(path, limit)
        self.metadata_bytes += len(raw)
        require(self.metadata_bytes <= TOTAL_LIMIT, "RAW_METADATA_CAP")
        self.check()
        return raw


def _cpu():
    value = resource.getrusage(resource.RUSAGE_SELF)
    return value.ru_utime + value.ru_stime


def scan_original(root, budget, *, hash_files):
    """Bounded original descriptor walk; second pass reads no body bytes."""
    _canonical_root(root)
    require(root.is_dir(), "RAW_ROOT")
    rows, identities, directories, total = {}, {}, set(), 0
    def visit(folder, relative, depth):
        nonlocal total
        require(depth <= MAX_DEPTH, "RAW_SCAN")
        with os.scandir(folder) as entries:
            for entry in entries:
                budget.check(); budget.entries += 1
                require(budget.entries <= MAX_ENTRIES, "RAW_SCAN")
                name = _relative((relative + "/" if relative else "") + entry.name)
                info = entry.stat(follow_symlinks=False)
                require(not stat.S_ISLNK(info.st_mode), "RAW_SYMLINK")
                if stat.S_ISDIR(info.st_mode):
                    directories.add(name)
                    descriptor = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
                    try:
                        opened = os.fstat(descriptor)
                        require((opened.st_dev, opened.st_ino, opened.st_mode) == (info.st_dev, info.st_ino, info.st_mode), "RAW_CHANGED")
                        visit(descriptor, name, depth + 1)
                    finally: os.close(descriptor)
                    continue
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "RAW_ALIAS")
                require(0 <= info.st_size <= ROLE_BYTES and len(rows) < ROOT_FILES and total + info.st_size <= ROOT_BYTES, "RAW_MEMBER")
                identity = _stable(info)
                if hash_files:
                    descriptor = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
                    try:
                        require(_stable(os.fstat(descriptor)) == identity, "RAW_CHANGED")
                        hashed, size = hashlib.sha256(), 0
                        while block := os.read(descriptor, min(1024**2, info.st_size - size + 1)):
                            budget.check(); size += len(block); budget.hashed += len(block)
                            require(size <= info.st_size and budget.hashed <= ROOT_BYTES, "RAW_HASH_CAP")
                            hashed.update(block)
                        require(size == info.st_size and _stable(os.fstat(descriptor)) == identity
                                and _stable(os.stat(entry.name, dir_fd=folder, follow_symlinks=False)) == identity, "RAW_CHANGED")
                    finally: os.close(descriptor)
                    row = {"bytes": size, "sha256": hashed.hexdigest()}
                else:
                    row = {"bytes": info.st_size}
                rows[name], identities[name] = row, list(identity)
                total += info.st_size
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: visit(descriptor, "", 0)
    finally: os.close(descriptor)
    return {"files": dict(sorted(rows.items())), "identities": identities, "directories": directories,
            "bytes": total, "file_count": len(rows)}


def _pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _load_control(control, budget):
    _canonical_root(control)
    pin_name = "docs/experiments/forecast-credibility-source-pins.json"
    protocol_name = "docs/experiments/forecast-credibility-registration.md"
    pins_raw = budget.read(control / pin_name, 65536)
    pins = strict_json(pins_raw)
    require(type(pins) is dict and 4 <= len(pins) <= 64, "RAW_SOURCE")
    require({"scripts/forecast_credibility_owner.py", "scripts/forecast_credibility_study.py", "scripts/forecast_credibility_publish.py",
            "docs/experiments/forecast-credibility-inputs.json", "docs/experiments/forecast-credibility-jobs.json"} <= set(pins), "RAW_SOURCE")
    sources = {}
    for name, expected in pins.items():
        _relative(name)
        require(type(expected) is dict and set(expected) == {"bytes", "sha256"}
                and type(expected["bytes"]) is int and 0 <= expected["bytes"] <= 128 * 1024 and _sha(expected["sha256"]), "RAW_SOURCE")
        raw = budget.read(control / name, 128 * 1024)
        require(_pin(raw) == expected, "RAW_SOURCE")
        if name in ("scripts/forecast_credibility_owner.py", "scripts/forecast_credibility_study.py", "docs/experiments/forecast-credibility-inputs.json",
                    "docs/experiments/forecast-credibility-jobs.json"):
            sources[name] = raw
    owner_tree = ast.parse(sources["scripts/forecast_credibility_owner.py"])
    controls = [node.value for node in owner_tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "CONTROL_FILES" for target in node.targets)]
    require(len(controls) == 1, "RAW_SOURCE")
    expected_names = ast.literal_eval(controls[0])
    require(type(expected_names) is tuple and all(type(name) is str for name in expected_names)
            and len(set(expected_names)) == len(expected_names)
            and set(pins) == set(expected_names) - {pin_name, protocol_name}, "RAW_SOURCE")
    protocol_raw = budget.read(control / protocol_name, 65536)
    require(("Source manifest SHA-256: `" + hashlib.sha256(pins_raw).hexdigest() + "`").encode() in protocol_raw, "RAW_SOURCE")
    module_name = "_forecast_publication_source_study"
    spec = importlib.util.spec_from_file_location(module_name, control / "scripts/forecast_credibility_study.py")
    module = importlib.util.module_from_spec(spec)
    # Compile only the already rehashed pure stdlib source; no product imports.
    exec(compile(sources["scripts/forecast_credibility_study.py"], str(control / "scripts/forecast_credibility_study.py"), "exec"), module.__dict__)
    config = strict_json(sources["docs/experiments/forecast-credibility-inputs.json"])
    jobs = module.validate_jobs(strict_json(sources["docs/experiments/forecast-credibility-jobs.json"]))
    binding = module.validate_binding(config["binding"])
    require(_sha(config.get("execution_approval")), "RAW_BINDING")
    return module, binding, jobs, {"registration_sha256": hashlib.sha256(protocol_raw).hexdigest(),
        "source_pins_sha256": hashlib.sha256(pins_raw).hexdigest()}


def _boot_id():
    value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(len(value) == 36, "RAW_CLOCK")
    return value


def _clock(root, source, core, budget, *, boot_id=None):
    clock_raw = budget.read(root / "job-clock.json", 2 * 1024**2)
    clock = strict_json(clock_raw)
    require(type(clock) is dict and type(clock.get("observed")) is dict, "RAW_CLOCK")
    producer, observed = clock.get("control_producer"), clock["observed"]
    require(type(producer) is dict and producer.get("source") == source, "RAW_CLOCK")
    try:
        expected = {"run", "jobs", "http_date", "monotonic_before", "monotonic_after",
                    "http_age", "run_http_age", "utc_before", "utc_after"}
        require(set(observed) == expected, "RAW_CLOCK")
        admitted = core.admit_job_clock(producer, observed["run"], observed["jobs"],
            **{key: value for key, value in observed.items() if key not in {"run", "jobs"}}, boot_id=clock["boot_id"])
    except (KeyError, TypeError, ValueError):
        raise Refused("RAW_CLOCK") from None
    require(canonical(admitted) == canonical(clock) and clock["boot_id"] == (_boot_id() if boot_id is None else boot_id), "RAW_CLOCK")
    require(type(clock["monotonic_deadline"]) is float and math.isfinite(clock["monotonic_deadline"])
            and observed["monotonic_after"] <= budget.now(), "RAW_CLOCK")
    return clock, clock_raw


def _owner(root, source, budget):
    raw_result = budget.read(root / "result.json")
    raw_terminal = budget.read(root / "terminal.json", 65536)
    result, terminal = strict_json(raw_result), strict_json(raw_terminal)
    require(type(result) is dict and type(terminal) is dict
            and result.get("cleanup_complete") is True and terminal.get("cleanup_complete") is True, "RAW_CLEANUP")
    require(result.get("producer", {}).get("GITHUB_SHA") == source, "RAW_SOURCE")
    if "result_sha256" in terminal:
        require(terminal["result_sha256"] == hashlib.sha256(raw_result).hexdigest(), "RAW_INVENTORY")
    require(type(result.get("complete")) is bool and type(terminal.get("complete")) is bool
            and result["complete"] is terminal["complete"], "RAW_INVENTORY")
    if result["complete"]:
        require(terminal.get("result_sha256") == hashlib.sha256(raw_result).hexdigest()
                and terminal.get("required_wrapper_exit") == 0 and result.get("errors") == []
                and result.get("actual_simulation_roles") == 14 and result.get("actual_executed_ticks") == 315
                and result.get("actual_fresh_Worlds") == 7 and result.get("actual_restored_roles") == 7
                and not (root / "terminal-failure.json").exists(), "RAW_ROLE_STATUS")
        mechanics_raw = budget.read(root / "mechanics.json")
        mechanics = strict_json(mechanics_raw)
        require(type(mechanics) is dict and mechanics.get("complete") is True
                and result.get("mechanical_readout_sha256") == hashlib.sha256(mechanics_raw).hexdigest(), "RAW_INVENTORY")
        before = strict_json(budget.read(root / "packages-before.json", 1024**2))
        after = strict_json(budget.read(root / "packages-after.json", 1024**2))
        require(type(before) is list and before and before == after, "RAW_BINDING")
    retained = result.get("retained_inventory")
    require(type(retained) is dict and type(retained.get("files")) is dict
            and type(retained.get("bytes")) is int and type(retained.get("file_count")) is int, "RAW_INVENTORY")
    require(len(retained["files"]) <= ROOT_FILES and retained["file_count"] == len(retained["files"])
            and retained["bytes"] == sum(row["bytes"] for row in retained["files"].values()), "RAW_INVENTORY")
    for name, pin in retained["files"].items():
        _relative(name)
        require(name not in AUTHORITIES and type(pin) is dict and set(pin) == {"bytes", "sha256"}
                and type(pin["bytes"]) is int and 0 <= pin["bytes"] <= ROLE_BYTES and _sha(pin["sha256"]), "RAW_INVENTORY")
    return result, terminal, raw_result, raw_terminal


def _producer_join(result, producer):
    expected = {"GITHUB_SHA": producer["source"], "GITHUB_RUN_ID": str(producer["run_id"]),
        "GITHUB_RUN_ATTEMPT": "1", "GITHUB_JOB": producer["job"],
        "GITHUB_WORKFLOW_REF": producer["repository"] + "/" + producer["workflow"]
            + "@refs/heads/lead/cloud-forecast-local-credibility-h26-20261029"}
    require(result.get("producer") == expected, "RAW_SOURCE")


def _clock_join(result, clock, clock_raw):
    observed = result.get("job_clock")
    require(type(observed) is dict and observed.get("path") == "job-clock.json"
            and observed.get("sha256") == hashlib.sha256(clock_raw).hexdigest()
            and observed.get("monotonic_deadline") == clock["monotonic_deadline"]
            and type(observed.get("publication_reserve_seconds")) is int and observed["publication_reserve_seconds"] == 255
            and type(observed.get("effective_owner_deadline")) in (int, float)
            and math.isfinite(observed["effective_owner_deadline"])
            and observed["effective_owner_deadline"] <= clock["monotonic_deadline"] - 255, "RAW_CLOCK")


def _selected(original):
    files = original["files"]
    require("roles" in original["directories"] and all(name in files for name in RAW_LOGS), "RAW_FIXED_PATHS")
    members = {}
    for name, value in files.items():
        parts = PurePosixPath(name).parts
        if parts[0] == "roles":
            require(len(parts) >= 3 and parts[1] in ROLE_NAMES, "RAW_FIXED_PATHS")
            members[name] = value
        elif name in RAW_LOGS:
            require(value["bytes"] <= LOG_BYTES, "RAW_ROLE_CAP")
            members[name] = value
        elif name.startswith("logs/role-"):
            raise Refused("RAW_FIXED_PATHS")
    for directory in original["directories"]:
        parts = PurePosixPath(directory).parts
        if parts[0] == "roles" and len(parts) >= 2:
            require(parts[1] in ROLE_NAMES, "RAW_FIXED_PATHS")
    require(0 < len(members) <= 14 * ROLE_FILES and sum(row["bytes"] for row in members.values()) <= 14 * ROLE_BYTES, "RAW_ROLE_CAP")
    folded = {}
    for name in (*members, MANIFEST):
        parts = PurePosixPath(name).parts
        for end in range(1, len(parts) + 1):
            ancestor = "/".join(parts[:end]); key = ancestor.casefold()
            require(key not in folded or folded[key] == ancestor, "RAW_CASEFOLD")
            folded[key] = ancestor
    for index, role in enumerate(ROLE_NAMES):
        names = [name for name in members if name.startswith("roles/" + role + "/")] + [RAW_LOGS[index]]
        require(len(names) <= ROLE_FILES and sum(members[name]["bytes"] for name in names) <= ROLE_BYTES, "RAW_ROLE_CAP")
    return dict(sorted(members.items()))


def _status(result, records, original):
    status = result.get("role_status")
    require(type(status) is dict and set(status) == set(ROLE_NAMES) and type(records) is dict
            and set(records) <= set(ROLE_NAMES), "RAW_ROLE_STATUS")
    rows = {}
    for index, (name, start) in enumerate(zip(ROLE_NAMES, STARTS)):
        observed = status[name]
        require(type(observed) is dict and observed.get("status") in ("unattempted", "started", "complete", "failed_or_killed"), "RAW_ROLE_STATUS")
        ticks = observed.get("observed_ticks")
        if observed["status"] == "complete":
            record = records.get(name)
            require(type(ticks) is int and ticks == 26 - start and type(record) is dict
                    and record.get("status") == "complete" and record.get("observed_ticks") == ticks, "RAW_ROLE_STATUS")
            prefix = "roles/" + name + "/ordinary/"
            ordinary = {path[len(prefix):]: pin for path, pin in original["files"].items() if path.startswith(prefix)}
            require(ordinary and record.get("inventory") == ordinary, "RAW_INVENTORY")
        else:
            require(ticks is None, "RAW_ROLE_STATUS")
        directory_present = "roles/" + name in original["directories"]
        if result["complete"]:
            require(observed["status"] == "complete" and directory_present, "RAW_ROLE_STATUS")
        rows[name] = {"status": observed["status"], "observed_ticks": ticks,
            "directory_present": directory_present, "log_present": RAW_LOGS[index] in original["files"]}
    return rows


def joint_reserve(original_bytes, original_files, *, new_bytes=MANIFEST_BYTES + PLAN_BYTES, new_files=2,
                  publication_bytes=TOTAL_LIMIT, publication_files=FILE_LIMIT):
    require(all(type(v) is int and v >= 0 for v in (original_bytes, original_files, new_bytes, new_files, publication_bytes, publication_files)), "RAW_JOINT_CAP")
    require(original_bytes + new_bytes + publication_bytes <= ROOT_BYTES
            and original_files + new_files + publication_files <= ROOT_FILES, "RAW_JOINT_CAP")
    return {"original_all_file_bytes": original_bytes, "original_all_file_count": original_files,
        "reserved_new_authority_bytes": new_bytes, "reserved_new_authority_files": new_files,
        "reserved_metadata_copy_bytes": publication_bytes, "reserved_metadata_copy_files": publication_files,
        "joint_byte_cap": ROOT_BYTES, "joint_file_cap": ROOT_FILES}


def _write_fresh(path, value, cap):
    raw = canonical(value)
    require(len(raw) <= cap and not path.exists() and not path.is_symlink(), "RAW_OUTPUT")
    with path.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
    return _pin(raw)


def _negative(source, code):
    return {"schema_version": 1, "kind": "forecast-raw-retention-plan-v1", "raw_eligible": False,
        "complete": False, "source": source, "refusal_code": code, "observed_selected_bytes": None,
        "observed_selected_files": None, "raw_original_artifact_qualified": None,
        "scope": "No durable original body claim. Local files and metadata remain separate evidence."}


def prepare_raw(root, control, *, source, owner_outcome, budget=None, boot_id=None):
    """Prepare exact existing role/log members; never create an archive or copy bodies."""
    budget = Budget(PREPARE_WALL, PREPARE_CPU) if budget is None else budget
    original = None
    try:
        _canonical_root(root); _canonical_root(control)
        require(_sha(source, 40), "RAW_SOURCE")
        require(all(not (root / name).exists() and not (root / name).is_symlink() for name in (MANIFEST, PLAN)), "RAW_OCCUPIED")
        core, binding, jobs, control_pins = _load_control(control, budget)
        clock, clock_raw = _clock(root, source, core, budget, boot_id=boot_id)
        # Leave metadata20 + metadata-upload60 + raw-upload120 + safety25.
        budget.deadline = min(budget.deadline, clock["monotonic_deadline"] - 225)
        budget.check()
        result, terminal, raw_result, raw_terminal = _owner(root, source, budget)
        _producer_join(result, clock["control_producer"])
        _clock_join(result, clock, clock_raw)
        if result["complete"]: require(owner_outcome == "success", "RAW_ROLE_STATUS")
        original = scan_original(root, budget, hash_files=True)
        retained = result["retained_inventory"]
        require({name: pin for name, pin in original["files"].items() if name not in AUTHORITIES} == retained["files"], "RAW_INVENTORY")
        require(original["files"].get("result.json") == _pin(raw_result)
                and original["files"].get("terminal.json") == _pin(raw_terminal)
                and original["files"].get("job-clock.json") == _pin(clock_raw), "RAW_CHANGED")
        accounting = joint_reserve(original["bytes"], original["file_count"])
        require(shutil.disk_usage(root).free >= 3 * GIB + MANIFEST_BYTES + PLAN_BYTES + TOTAL_LIMIT, "RAW_JOINT_CAP")
        registration = strict_json(budget.read(root / "registration.json"))
        records = strict_json(budget.read(root / "roles.json"))
        expected = core.registration(binding, jobs)
        require(type(registration) is dict and all(registration.get(key) == value for key, value in expected.items()), "RAW_BINDING")
        members = _selected(original)
        role_status = _status(result, records, original)
        names = sorted(original["files"])
        producer = clock["control_producer"]
        manifest = {"schema_version": 1, "kind": "forecast-original-role-bodies-v1",
            "control_producer": producer, "runtime_binding": binding, **control_pins,
            "owner_result_sha256": _pin(raw_result)["sha256"], "owner_terminal_sha256": _pin(raw_terminal)["sha256"],
            "matrix_state": "complete" if result["complete"] else "negative", "raw_eligible": True, "refusal_code": None,
            "role_status": role_status, "members": members, "observed_selected_bytes": sum(row["bytes"] for row in members.values()),
            "observed_selected_files": len(members), "original_authorities": {name: original["files"][name] for name in AUTHORITIES if name in original["files"]},
            "original_name_order_sha256": hashlib.sha256(canonical(names)).hexdigest(),
            "original_file_identities": [original["identities"][name] for name in names],
            "joint_accounting": accounting, "raw_original_artifact_qualified": None,
            "upload_client": UPLOAD_CLIENT, "independent_reason": "original_official_archive_not_received"}
        manifest_pin = _write_fresh(root / MANIFEST, manifest, MANIFEST_BYTES)
        after = scan_original(root, budget, hash_files=False)
        require(set(after["files"]) == set(original["files"]) | {MANIFEST}
                and all(after["identities"][name] == original["identities"][name] for name in original["files"]), "RAW_CHANGED")
        budget.check()
        artifact_name = _artifact_name(producer)
        plan = {"schema_version": 1, "kind": "forecast-raw-retention-plan-v1", "complete": True,
            "raw_eligible": True, "source": source, "control_producer": producer, "boot_id": clock["boot_id"],
            "monotonic_deadline": clock["monotonic_deadline"], "manifest": {"path": MANIFEST, **manifest_pin},
            "expected_artifact_name": artifact_name, "matrix_state": manifest["matrix_state"], "refusal_code": None,
            "observed_selected_bytes": manifest["observed_selected_bytes"], "observed_selected_files": len(members),
            "joint_accounting": accounting, "phase": "pre_upload", "raw_original_artifact_qualified": None,
            "scope": "Only a sealed VM-local body set is eligible. Action outcome and independent original ZIP acceptance remain separate."}
        _write_fresh(root / PLAN, plan, PLAN_BYTES)
        budget.check()
        require(shutil.disk_usage(root).free >= 3 * GIB, "RAW_JOINT_CAP")
        return plan
    except Exception as exc:
        code = exc.code if isinstance(exc, Refused) else "RAW_REFUSED"
        negative = _negative(source, code)
        # No finally-write promise after hard kill. Unknown/unsafe original
        # footprint gets no added root file; metadata creates its own fallback.
        try:
            if original is not None and not (root / PLAN).exists() and not (root / PLAN).is_symlink():
                joint_reserve(original["bytes"] + ((root / MANIFEST).stat().st_size if (root / MANIFEST).is_file() else 0),
                    original["file_count"] + int((root / MANIFEST).exists()), new_bytes=PLAN_BYTES, new_files=1)
                budget.check(); _write_fresh(root / PLAN, negative, PLAN_BYTES)
        except Exception: pass
        return negative


def _plan(root, source, budget):
    raw = budget.read(root / PLAN, PLAN_BYTES)
    plan = strict_json(raw)
    require(type(plan) is dict and set(plan) == PLAN_FIELDS and plan.get("schema_version") == 1 and type(plan.get("schema_version")) is int
            and plan.get("kind") == "forecast-raw-retention-plan-v1" and plan.get("source") == source
            and plan.get("complete") is True and plan.get("raw_eligible") is True
            and plan.get("refusal_code") is None and plan.get("raw_original_artifact_qualified") is None, "RAW_PLAN")
    return plan, raw


def _artifact_name(producer):
    require(type(producer) is dict and _sha(producer.get("source"), 40)
            and type(producer.get("run_id")) is int and producer["run_id"] > 0, "RAW_PLAN")
    return "forecast-credibility-original-" + producer["source"] + "-" + str(producer["run_id"]) + "-1"


def _remaining_metadata(work):
    wall, cpu = work["charged_serialization_wall_seconds"], work["charged_serialization_cpu_seconds"]
    require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in (wall, cpu))
            and METADATA_TAIL_WALL <= wall < METADATA_WALL and METADATA_TAIL_CPU <= cpu < METADATA_CPU, "RAW_PLAN")
    remaining = {"remaining_wall_milliseconds": math.floor((METADATA_WALL - wall) * 1000),
                 "remaining_cpu_seconds": math.floor(METADATA_CPU - cpu)}
    require(1 <= remaining["remaining_wall_milliseconds"] <= METADATA_WALL * 1000
            and 1 <= remaining["remaining_cpu_seconds"] <= METADATA_CPU, "RAW_PLAN")
    return remaining


def _metadata_work_budget(budget, root, output, source, retained):
    charged_wall = budget.now() - budget.started + METADATA_TAIL_WALL
    charged_cpu = budget.cpu_now() - budget.cpu_origin + METADATA_TAIL_CPU
    require(0 <= charged_wall <= METADATA_WALL and 0 <= charged_cpu <= METADATA_CPU, "RAW_DEADLINE")
    clock_binding = None
    if "job-clock.json" in retained:
        try: clock = strict_json(retained["job-clock.json"])
        except (ValueError, TypeError): clock = None
        if type(clock) is dict:
            clock_binding = {"boot_id": clock.get("boot_id"), "monotonic_deadline": clock.get("monotonic_deadline"),
                             "sha256": hashlib.sha256(retained["job-clock.json"]).hexdigest()}
    return {"schema_version": 1, "scope": "one_shared_metadata_serialization_and_late_gate_envelope",
        "source": source, "root": str(root), "output": str(output), "clock_binding": clock_binding,
        "max_wall_seconds": METADATA_WALL, "max_cpu_seconds": METADATA_CPU,
        "charged_serialization_wall_seconds": charged_wall, "charged_serialization_cpu_seconds": charged_cpu,
        "tail_wall_reserve_seconds": METADATA_TAIL_WALL, "tail_cpu_reserve_seconds": METADATA_TAIL_CPU}


def _metadata_tail_enforce(report, budget):
    """Successful process exit must fit the sealed final-write/guard/exit tail."""
    work = report["metadata_work_budget"]
    budget.deadline = min(budget.deadline, budget.started + work["charged_serialization_wall_seconds"])
    budget.cpu_limit = min(budget.cpu_limit, work["charged_serialization_cpu_seconds"])
    budget.check()
    if budget.enforce_os:
        signal.setitimer(signal.ITIMER_REAL, max(0.000001, budget.deadline - budget.now()))
        signal.setitimer(signal.ITIMER_PROF, max(0.000001, budget.cpu_limit - (budget.cpu_now() - budget.cpu_origin)))


def _metadata_postcommit(report, budget):
    work = report["metadata_work_budget"]
    budget.check()
    require(budget.now() - budget.started <= work["charged_serialization_wall_seconds"], "RAW_DEADLINE")
    require(budget.cpu_now() - budget.cpu_origin <= work["charged_serialization_cpu_seconds"], "RAW_CPU")


def _share_metadata_budget(publication, budget, *, source, root, output,
                           remaining_wall_milliseconds, remaining_cpu_seconds):
    work = publication.get("metadata_work_budget")
    fields = {"schema_version", "scope", "source", "root", "output", "clock_binding", "max_wall_seconds",
              "max_cpu_seconds", "charged_serialization_wall_seconds", "charged_serialization_cpu_seconds",
              "tail_wall_reserve_seconds", "tail_cpu_reserve_seconds"}
    require(type(work) is dict and set(work) == fields and type(work["schema_version"]) is int and work["schema_version"] == 1
            and work["scope"] == "one_shared_metadata_serialization_and_late_gate_envelope"
            and work["source"] == source and work["root"] == str(root) and work["output"] == str(output)
            and work["max_wall_seconds"] == METADATA_WALL and work["max_cpu_seconds"] == METADATA_CPU
            and work["tail_wall_reserve_seconds"] == METADATA_TAIL_WALL and work["tail_cpu_reserve_seconds"] == METADATA_TAIL_CPU,
            "RAW_PLAN")
    remaining = _remaining_metadata(work)
    require(remaining_wall_milliseconds == str(remaining["remaining_wall_milliseconds"])
            and remaining_cpu_seconds == str(remaining["remaining_cpu_seconds"]), "RAW_PLAN")
    budget.deadline = min(budget.deadline, budget.started + remaining["remaining_wall_milliseconds"] / 1000)
    budget.cpu_limit = min(budget.cpu_limit, remaining["remaining_cpu_seconds"])
    budget.check()
    if budget.enforce_os:
        # This process's boot-sampled ACTIVE work excludes metadata-upload wait.
        signal.setitimer(signal.ITIMER_REAL, max(0.000001, budget.deadline - budget.now()))
        signal.setitimer(signal.ITIMER_PROF, max(0.000001, budget.cpu_limit - (budget.cpu_now() - budget.cpu_origin)))
    return work


def _launcher_budget(mode, launch_boot_seconds, *, now=None, boot_now=None):
    """Conservative /proc/uptime sample includes Python startup; no job-D source."""
    wall, cpu = (PREPARE_WALL, PREPARE_CPU) if mode == "prepare" else (METADATA_WALL, METADATA_CPU)
    require(type(launch_boot_seconds) is str and len(launch_boot_seconds) <= 32
            and launch_boot_seconds.count(".") == 1
            and all(part.isascii() and part.isdecimal() for part in launch_boot_seconds.split(".")), "RAW_CLOCK")
    launched = float(launch_boot_seconds)
    # Enclose scheduling delay conservatively: monotonic BEFORE boot sample.
    sampled = time.monotonic() if now is None else now
    current = time.clock_gettime(time.CLOCK_BOOTTIME) if boot_now is None else boot_now
    require(math.isfinite(launched) and type(current) in (int, float) and math.isfinite(current)
            and 0 <= current - launched < wall, "RAW_DEADLINE")
    require(type(sampled) in (int, float) and math.isfinite(sampled), "RAW_CLOCK")
    return sampled - (current - launched)


def gate_raw_upload(root, control, *, source, prepare_outcome, metadata_outcome, metadata_output,
                    serializer_exit, metadata_budget_complete, publication_outcome, remaining_wall_milliseconds,
                    remaining_cpu_seconds, budget=None, boot_id=None):
    """A stat-only late gate after metadata upload; never hashes bodies twice."""
    budget = Budget(METADATA_WALL, METADATA_CPU) if budget is None else budget
    try:
        require(prepare_outcome == metadata_outcome == publication_outcome == "success"
                and serializer_exit in ("0", "2") and metadata_budget_complete == "true", "RAW_PLAN")
        _canonical_root(root)
        _canonical_root(metadata_output)
        require(root != metadata_output and root not in metadata_output.parents and metadata_output not in root.parents, "RAW_ROOT")
        publication = strict_json(budget.read(metadata_output / "publication.json", PLAN_BYTES))
        require(type(publication) is dict and publication.get("source") == source and publication.get("metadata_only") is True, "RAW_PLAN")
        work = _share_metadata_budget(publication, budget, source=source, root=root, output=metadata_output,
            remaining_wall_milliseconds=remaining_wall_milliseconds, remaining_cpu_seconds=remaining_cpu_seconds)
        core, binding, _jobs, control_pins = _load_control(control, budget)
        clock, clock_raw = _clock(root, source, core, budget, boot_id=boot_id)
        require(work["clock_binding"] == {"boot_id": clock["boot_id"], "monotonic_deadline": clock["monotonic_deadline"],
                "sha256": hashlib.sha256(clock_raw).hexdigest()}, "RAW_CLOCK")
        plan, raw_plan = _plan(root, source, budget)
        manifest_raw = budget.read(root / MANIFEST, MANIFEST_BYTES)
        require(plan.get("manifest") == {"path": MANIFEST, **_pin(manifest_raw)}
                and plan.get("control_producer") == clock["control_producer"] and plan.get("boot_id") == clock["boot_id"]
                and plan.get("monotonic_deadline") == clock["monotonic_deadline"]
                and plan.get("expected_artifact_name") == _artifact_name(clock["control_producer"]), "RAW_PLAN")
        manifest = strict_json(manifest_raw)
        require(type(manifest) is dict and set(manifest) == MANIFEST_FIELDS
                and type(manifest.get("schema_version")) is int and manifest["schema_version"] == 1
                and manifest.get("kind") == "forecast-original-role-bodies-v1"
                and manifest.get("raw_eligible") is True and manifest.get("control_producer") == clock["control_producer"]
                and manifest.get("runtime_binding") == binding and all(manifest.get(key) == value for key, value in control_pins.items())
                and manifest.get("matrix_state") == plan.get("matrix_state")
                and manifest.get("raw_original_artifact_qualified") is None and manifest.get("refusal_code") is None
                and manifest.get("upload_client") == UPLOAD_CLIENT, "RAW_PLAN")
        require(type(publication) is dict and publication.get("source") == source
                and publication.get("metadata_only") is True and publication.get("files", {}).get(PLAN) == _pin(raw_plan)
                and publication.get("raw_retention", {}).get("manifest") == plan["manifest"]
                and publication["raw_retention"].get("local_manifest_eligible") is True
                and publication["raw_retention"].get("phase") == "pre_upload"
                and publication["raw_retention"].get("raw_original_artifact_qualified") is None, "RAW_PLAN")
        result, _terminal, raw_result, raw_terminal = _owner(root, source, budget)
        _producer_join(result, clock["control_producer"])
        _clock_join(result, clock, clock_raw)
        require(manifest.get("owner_result_sha256") == _pin(raw_result)["sha256"]
                and manifest.get("owner_terminal_sha256") == _pin(raw_terminal)["sha256"], "RAW_CHANGED")
        expected_members = {name: value for name, value in result["retained_inventory"]["files"].items()
                            if name.startswith("roles/") or name in RAW_LOGS}
        require(manifest.get("members") == expected_members
                and manifest["matrix_state"] == ("complete" if result["complete"] else "negative"), "RAW_PLAN")
        current = scan_original(root, budget, hash_files=False)
        old_names = sorted(set(current["files"]) - {MANIFEST, PLAN})
        require(hashlib.sha256(canonical(old_names)).hexdigest() == manifest.get("original_name_order_sha256")
                and [current["identities"][name] for name in old_names] == manifest.get("original_file_identities"), "RAW_CHANGED")
        selected = _selected(current)
        require(set(selected) == set(manifest.get("members", {}))
                and all(selected[name]["bytes"] == manifest["members"][name]["bytes"] for name in selected), "RAW_CHANGED")
        require(manifest.get("observed_selected_files") == len(selected)
                and manifest.get("observed_selected_bytes") == sum(row["bytes"] for row in selected.values()), "RAW_PLAN")
        joint_reserve(current["bytes"], current["file_count"], new_bytes=0, new_files=0)
        budget.check()
        require(clock["monotonic_deadline"] - budget.now() >= 145, "RAW_UPLOAD_RESERVE")
        require(shutil.disk_usage(root).free >= 3 * GIB, "RAW_JOINT_CAP")
        return {"upload_raw": True, "expected_artifact_name": plan["expected_artifact_name"],
            "monotonic_deadline": clock["monotonic_deadline"],
            "phase": "pre_upload_after_metadata", "raw_original_artifact_qualified": None}
    except Exception as exc:
        return {"upload_raw": False, "refusal_code": exc.code if isinstance(exc, Refused) else "RAW_REFUSED",
            "phase": "pre_upload_after_metadata", "raw_original_artifact_qualified": None}


def selected_paths():
    # Existing fifteen metadata proofs retain their original completeness gate.
    return ["result.json", "terminal.json", "terminal-failure.json", "registration.json", "roles.json",
            "admission.json", "input-before.json", "input-after.json", "packages-before.json", "packages-after.json",
            "mechanics.json", "source-witnesses.json", "progress.jsonl", "pure-preflight/receipt.json",
            "pure-preflight/junit.xml"]


def _raw_status(root, source, prepare_outcome, budget, retained=None):
    status = {"phase": "pre_upload", "as_of_metadata_seal": True, "local_manifest_eligible": False,
        "raw_original_artifact_qualified": None, "reason": "missing_malformed_or_terminated_preparation"}
    try:
        require(prepare_outcome == "success", "RAW_PLAN")
        retained = {} if retained is None else retained
        if PLAN in retained:
            plan = strict_json(retained[PLAN])
            require(type(plan) is dict and set(plan) == PLAN_FIELDS and plan.get("complete") is plan.get("raw_eligible") is True
                    and plan.get("source") == source, "RAW_PLAN")
        else:
            plan, _raw = _plan(root, source, budget)
        require(type(plan.get("manifest")) is dict and plan["manifest"].get("path") == MANIFEST, "RAW_PLAN")
        manifest_raw = retained[MANIFEST] if MANIFEST in retained else budget.read(root / MANIFEST, MANIFEST_BYTES)
        require(plan["manifest"] == {"path": MANIFEST, **_pin(manifest_raw)}, "RAW_PLAN")
        status.update(local_manifest_eligible=True, reason="awaiting_action_then_independent_original_archive",
            expected_artifact_name=plan["expected_artifact_name"], manifest=plan["manifest"], matrix_state=plan["matrix_state"])
    except Exception: pass
    return status


def publish(root, output, *, owner_outcome, source, prepare_outcome=None, budget=None):
    budget = Budget(METADATA_WALL, METADATA_CPU) if budget is None else budget
    if (not root.is_absolute() or not output.is_absolute() or root == output or root in output.parents
            or output in root.parents or root != root.resolve() or output != output.resolve()):
        raise ValueError("disjoint absolute publication paths")
    if not _sha(source, 40): raise ValueError("publication source SHA")
    if output.exists() or output.is_symlink(): raise ValueError("fresh publication required")
    output.mkdir(parents=True)
    report = {"complete": False, "metadata_only": True, "source_publication_qualified": False,
              "owner_step_outcome": owner_outcome, "source": source, "files": {}, "omissions": [],
              "raw_payload_retained": False, "raw_retention": {"phase": "pre_upload", "as_of_metadata_seal": True,
                  "local_manifest_eligible": False, "raw_original_artifact_qualified": None, "reason": "not_yet_read"},
              "scope": "Copied bounded metadata only. Raw upload and independent original-body acceptance are separate gates."}
    def seal():
        raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        if len(raw) > PLAN_BYTES: raise ValueError("publication authority cap")
        with (output / "publication.json").open("wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    seal()  # Negative metadata authority exists even if preparation was killed.
    total, retained = 0, {}
    try:
        footprint = scan_original(root, budget, hash_files=False)
        report["joint_accounting"] = joint_reserve(footprint["bytes"], footprint["file_count"], new_bytes=0, new_files=0)
        copying = True
    except Exception:
        # Unknown/overbound bodies are preserved, with bounded diagnostic only.
        report["joint_accounting"] = None
        report["raw_retention"]["reason"] = "original_aggregate_unclosed"
        copying = False
    if copying:
        for name in selected_paths() + ["job-clock.json", PLAN, MANIFEST]:
            path = root / name
            try:
                budget.check()
                raw = budget.read(path, MANIFEST_BYTES if name == MANIFEST else MEMBER_LIMIT)
                if len(report["files"]) + 1 >= FILE_LIMIT or total + len(raw) + PLAN_BYTES > TOTAL_LIMIT:
                    raise ValueError("publication aggregate cap")
                target = output / name; target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                report["files"][name] = _pin(raw)
                retained[name] = raw; total += len(raw)
            except (OSError, ValueError) as exc:
                report["omissions"].append({"path": name, "reason": type(exc).__name__})
        report["raw_retention"] = _raw_status(root, source, prepare_outcome, budget, retained)
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
    report["metadata_work_budget"] = _metadata_work_budget(budget, root, output, source, retained)
    _metadata_tail_enforce(report, budget)
    budget.check(); seal(); _metadata_postcommit(report, budget)
    return report


def _enforce(mode, remaining_wall_milliseconds=None, remaining_cpu_seconds=None):
    wall, cpu = (PREPARE_WALL, PREPARE_CPU) if mode == "prepare" else (METADATA_WALL, METADATA_CPU)
    if mode == "upload-gate":
        require(type(remaining_wall_milliseconds) is str and remaining_wall_milliseconds.isascii()
                and remaining_wall_milliseconds.isdecimal() and 1 <= int(remaining_wall_milliseconds) <= METADATA_WALL * 1000
                and str(int(remaining_wall_milliseconds)) == remaining_wall_milliseconds
                and type(remaining_cpu_seconds) is str and remaining_cpu_seconds.isascii()
                and remaining_cpu_seconds.isdecimal() and 1 <= int(remaining_cpu_seconds) <= METADATA_CPU
                and str(int(remaining_cpu_seconds)) == remaining_cpu_seconds, "RAW_PLAN")
        wall, cpu = int(remaining_wall_milliseconds) / 1000, int(remaining_cpu_seconds)
    resource.setrlimit(resource.RLIMIT_AS, (PUBLICATION_AS, PUBLICATION_AS))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MANIFEST_BYTES if mode == "prepare" else TOTAL_LIMIT,) * 2)
    def alarm(_sig, _frame): raise TimeoutError("bounded publication wall/CPU limit")
    signal.signal(signal.SIGALRM, alarm); signal.signal(signal.SIGPROF, alarm)
    signal.setitimer(signal.ITIMER_REAL, wall)
    signal.setitimer(signal.ITIMER_PROF, max(0.000001, cpu - _cpu()))
    return wall, cpu


def _workflow_output(values):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path: return
    allowed = {"raw_eligible", "upload_raw", "expected_artifact_name", "metadata_budget_complete",
               "remaining_wall_milliseconds", "remaining_cpu_seconds"}
    require(set(values) <= allowed, "RAW_OUTPUT")
    lines = []
    for name, value in values.items():
        value = ("true" if value else "false") if type(value) is bool else value
        require(type(value) is str and len(value) <= 256 and "\n" not in value and "\r" not in value, "RAW_OUTPUT")
        lines.append(name + "=" + value + "\n")
    with Path(path).open("a") as stream:
        stream.write("".join(lines)); stream.flush(); os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--control", type=Path)
    parser.add_argument("--owner-outcome", default="unknown")
    parser.add_argument("--prepare-outcome")
    parser.add_argument("--metadata-outcome")
    parser.add_argument("--publication-outcome")
    parser.add_argument("--serializer-exit")
    parser.add_argument("--metadata-budget-complete")
    parser.add_argument("--remaining-wall-milliseconds")
    parser.add_argument("--remaining-cpu-seconds")
    parser.add_argument("--launcher-boot-seconds", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--mode", choices=("metadata", "prepare", "upload-gate"), default="metadata")
    args = parser.parse_args(argv)
    wall, cpu = _enforce(args.mode, args.remaining_wall_milliseconds, args.remaining_cpu_seconds)
    launched = _launcher_budget(args.mode, args.launcher_boot_seconds)
    limits = Budget(wall, cpu, cpu_origin=0.0, enforce_os=True)
    limits.started = launched
    limits.deadline = min(limits.deadline, launched + wall)
    limits.check()
    if args.mode == "prepare":
        require(args.control is not None, "RAW_SOURCE")
        result = prepare_raw(args.root, args.control, source=args.source, owner_outcome=args.owner_outcome, budget=limits)
        if result["raw_eligible"]: _workflow_output({"raw_eligible": True})
        limits.check()
        return 0 if result["raw_eligible"] else 2
    if args.mode == "upload-gate":
        require(args.control is not None and args.output is not None, "RAW_SOURCE")
        result = gate_raw_upload(args.root, args.control, source=args.source,
            prepare_outcome=args.prepare_outcome, metadata_outcome=args.metadata_outcome, metadata_output=args.output,
            publication_outcome=args.publication_outcome, serializer_exit=args.serializer_exit,
            metadata_budget_complete=args.metadata_budget_complete, remaining_wall_milliseconds=args.remaining_wall_milliseconds,
            remaining_cpu_seconds=args.remaining_cpu_seconds, budget=limits)
        if result["upload_raw"]: _workflow_output({"upload_raw": True, "expected_artifact_name": result["expected_artifact_name"]})
        limits.check()
        # Output append/flush/fsync and the local guard may consume job reserve.
        # Keep D internal; a final refusal leaves a non-success step even if a
        # partial true output exists. The action also requires step success.
        if result["upload_raw"]:
            require(result["monotonic_deadline"] - limits.now() >= 145, "RAW_UPLOAD_RESERVE")
        return 0 if result["upload_raw"] else 2
    require(args.output is not None, "RAW_OUTPUT")
    report = publish(args.root, args.output, owner_outcome=args.owner_outcome, source=args.source,
        prepare_outcome=args.prepare_outcome, budget=limits)
    remaining = _remaining_metadata(report["metadata_work_budget"])
    _metadata_postcommit(report, limits)
    _workflow_output({"metadata_budget_complete": True, **{name: str(value) for name, value in remaining.items()}})
    _metadata_postcommit(report, limits)
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
