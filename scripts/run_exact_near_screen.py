#!/usr/bin/env python3
"""One hosted, same-binary synthetic screen. No simulation/World entry point.

The inactive YAML is the sole launcher. All children use selected qualified
C60/27f ownership and bounded intake. A terminal record starts negative; source,
resources and actual executable/runtime hashes close only after child cleanup.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys
import sysconfig
import time
import types

def _pinned_dependency(name, expected):
    path = Path(__file__).resolve().parent / (name + ".py")
    if path.is_symlink() or path.stat().st_size > 16384:
        raise RuntimeError("qualified dependency source refused")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError("qualified dependency hash refused")
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    sys.modules[name] = module
    return module


# Authenticate these exact qualified bytes before executing their definitions.
R44 = _pinned_dependency("wealth_floor_build_resources", "44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2")
D2 = _pinned_dependency("wealth_floor_hosted_deployment", "d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8")
import exact_near_screen_process as P
memory_admission = R44.memory_admission
hosted_vm_precondition = D2.hosted_vm_precondition

BASE = "0900f3d203cc74102809bb871a1a057ba91a951f"
BRANCH = "lead/cloud-exact-marriage-screen-20261029"
WORKFLOW = ".github/workflows/exact-marriage-broadphase-screen.yml"
TEMPLATE = "docs/experiments/exact-marriage-broadphase-screen-workflow.yml"
DOCUMENT = "docs/experiments/exact-marriage-broadphase-screen-2026-10-29.md"
PREFIX_BYTES = 106534
PREFIX_SHA = "f5fba731c541c211f3df23558e036a538ad10d8b0ac6be0f9c486d6d3a96a35f"
APPEND_SHA = "edb8e9b27867b24306f81d2efff4e78faf9151e48721247ea57861f03cb70d1d"
RESOURCE_SHA = "44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2"
DEPLOYMENT_SHA = "d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8"
CAPS = {key: "1" for key in ("CARGO_BUILD_JOBS", "RUST_TEST_THREADS", "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS", "RAYON_NUM_THREADS", "PYTHON_CPU_COUNT")}
CAPS.update(PYTHONHASHSEED="0", CHRONICLER_EXACT_NEAR_SCREEN="fixed-synthetic-v1")
CASES = ("empty0", "singleton1", "small16", "spread255", "spread256", "spread257",
    "spread1024", "spread4096", "dense1024", "dense4096", "boundaries1024", "outside1024",
    "nan1024", "infinity1024", "zeros1024")
SOURCE_PATHS = ("chronicler-agents/src/formation.rs", "docs/CONTINUATION.md", DOCUMENT, TEMPLATE,
    WORKFLOW, "scripts/wealth_floor_build_resources.py", "scripts/wealth_floor_hosted_deployment.py",
    "scripts/exact_near_screen_session.py", "scripts/exact_near_screen_process.py",
    "scripts/run_exact_near_screen.py", "tests/test_exact_near_screen_control.py")
INPUTS = (*SOURCE_PATHS, "chronicler-agents/Cargo.toml", "chronicler-agents/Cargo.lock")
MAX_FILE = 2 * 1024**2
MAX_LIGHT = 8 * 1024**2
MAX_LIGHT_FILES = 48
MAX_LOG_COPY = 256 * 1024
OWNER_SECONDS = 2500
require = P.B.require


def canonical(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def write_json(path, value):
    raw = canonical(value)
    require(len(raw) <= MAX_FILE, "control JSON byte cap")
    temporary = path.with_name("pending-" + path.name)
    with temporary.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def file_identity(path, limit=256 * 1024**2):
    path = Path(path)
    require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), "nonregular identity input")
    before = path.stat()
    require(before.st_size <= limit, "identity input byte cap")
    count, digest = 0, hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            count += len(block); require(count <= limit, "identity input grew past cap"); digest.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and count == after.st_size,
        "identity input changed during hash")
    return {"bytes": count, "sha256": digest.hexdigest()}


def require_context(env):
    expected = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": "YotsuBotfds/Chronicler",
        "GITHUB_REF": "refs/heads/" + BRANCH, "GITHUB_JOB": "synthetic-screen", "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": "YotsuBotfds/Chronicler/" + WORKFLOW + "@refs/heads/" + BRANCH}
    require(all(env.get(key) == value for key, value in expected.items()), "sealed one-shot hosted context refused")
    require(re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", "")) is not None, "source SHA shape")
    require(re.fullmatch(r"[1-9][0-9]{0,19}", env.get("GITHUB_RUN_ID", "")) is not None, "run identity shape")
    require(all(env.get(key) == value for key, value in CAPS.items()), "fixed thread/case caps differ")
    return {**expected, "GITHUB_SHA": env["GITHUB_SHA"], "GITHUB_RUN_ID": env["GITHUB_RUN_ID"]}


def admission(root, disk_gib, ram_gib):
    result = {"admitted": False, "resolver_sha256": RESOURCE_SHA,
        "required_disk_bytes": disk_gib * 1024**3, "required_memory_bytes": ram_gib * 1024**3,
        "observed_disk_free_bytes": shutil.disk_usage(root).free, "memory_observation": None}
    try:
        result["memory_observation"] = memory_admission()
        result["admitted"] = (result["observed_disk_free_bytes"] >= result["required_disk_bytes"]
            and result["memory_observation"]["available_bytes"] >= result["required_memory_bytes"])
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


def source_snapshot(source, command, phase):
    def git(label, *args):
        return command(phase + "-" + label, ["git", "-c", "core.fsmonitor=false", "-C", str(source), *args]).decode().strip()
    require(git("sha", "rev-parse", "HEAD") == os.environ["GITHUB_SHA"], "actual source SHA differs")
    require(not git("status", "status", "--porcelain=v1", "--untracked-files=all"), "actual source is dirty")
    changed = set(git("changed", "diff", "--name-only", BASE, "HEAD").splitlines())
    require(changed <= set(SOURCE_PATHS) and "chronicler-agents/src/formation.rs" in changed, "source change allowlist differs")
    facts = {name: file_identity(source / name, MAX_FILE) for name in INPUTS}
    raw = (source / "chronicler-agents/src/formation.rs").read_bytes()
    require(hashlib.sha256(raw[:PREFIX_BYTES]).hexdigest() == PREFIX_SHA
        and hashlib.sha256(raw[PREFIX_BYTES:]).hexdigest() == APPEND_SHA, "production prefix or test appendix differs")
    require((source / TEMPLATE).read_bytes() == (source / WORKFLOW).read_bytes(), "dormant/active workflow bytes differ")
    require(facts["scripts/wealth_floor_build_resources.py"]["sha256"] == RESOURCE_SHA, "R44 source differs")
    require(facts["scripts/wealth_floor_hosted_deployment.py"]["sha256"] == DEPLOYMENT_SHA, "D2 source differs")
    return {"sha": os.environ["GITHUB_SHA"], "crate_tree": git("crate", "rev-parse", "HEAD:chronicler-agents"),
        "base": BASE, "base_crate": "803c79c8d5c024cbb8d67c58af7ffa731d79c129", "changed_paths": sorted(changed),
        "files": facts, "original_prefix_sha256": PREFIX_SHA, "append_sha256": APPEND_SHA}


def runtime_snapshot(source, env, command, phase):
    tools = {}
    for name in ("rustc", "cargo", "rustup", "git", "ldd", "timeout", "taskset"):
        located = shutil.which(name, path=env["PATH"])
        require(located is not None, "required tool unavailable")
        real = Path(located).resolve(strict=True)
        tools[name] = {"path": located, "resolved": str(real), **file_identity(real)}
    tools["time"] = {"path": "/usr/bin/time", "resolved": str(Path("/usr/bin/time").resolve(strict=True)),
        **file_identity(Path("/usr/bin/time").resolve(strict=True))}
    versions = {}
    for name, argv in (("rustc", ["rustc", "--version", "--verbose"]), ("cargo", ["cargo", "--version"]),
        ("timeout", ["timeout", "--version"]), ("taskset", ["taskset", "--version"]), ("time", ["/usr/bin/time", "--version"])):
        versions[name] = command(phase + "-" + name, argv).decode()
    # PATH entries are often rustup shims. Bind the actual same-cwd/env dispatch.
    dispatched_compilers = {}
    for name in ("rustc", "cargo"):
        lines = command(phase + "-which-" + name, ["rustup", "which", name]).decode().splitlines()
        require(len(lines) == 1 and bool(lines[0]), "one dispatched compiler path required")
        actual = Path(lines[0])
        require(actual.is_absolute() and not actual.is_symlink(), "unsafe dispatched compiler path")
        real = actual.resolve(strict=True)
        dispatched_compilers[name] = {"path": str(actual), "resolved": str(real), **file_identity(real)}
    require(platform.python_version() == "3.13.5", "registered Python runtime differs")
    libdir, library = sysconfig.get_config_var("LIBDIR"), sysconfig.get_config_var("LDLIBRARY")
    require(libdir and library, "Python linkage configuration unavailable")
    config_paths = {Path(env.get("CARGO_HOME", str(Path.home() / ".cargo"))) / name for name in ("config", "config.toml")}
    for ancestor in (source, *source.parents):
        config_paths.update(ancestor / ".cargo" / name for name in ("config", "config.toml"))
    require(not any(path.exists() or path.is_symlink() for path in config_paths), "unreviewed Cargo configuration")
    flags = ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
        "RUSTC", "RUSTDOC", "CARGO_BUILD_TARGET", "CC", "CXX", "AR", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "LD_PRELOAD")
    require(not any(env.get(key) for key in flags), "unreviewed compiler/loader override")
    return {"python": sys.version, "python_executable": str(Path(sys.executable).resolve()),
        "python_executable_identity": file_identity(Path(sys.executable).resolve()),
        "python_library": str((Path(libdir) / library).resolve(strict=True)),
        "python_library_identity": file_identity((Path(libdir) / library).resolve(strict=True)),
        "tools": tools, "dispatched_compilers": dispatched_compilers,
        "versions": versions, "caps": {key: env.get(key) for key in CAPS},
        "affinity": sorted(os.sched_getaffinity(0)), "clk_tck": os.sysconf("SC_CLK_TCK"),
        "loader_paths": {key: env.get(key) for key in ("PYO3_PYTHON", "LIBRARY_PATH", "LD_LIBRARY_PATH", "CARGO_TARGET_DIR")},
        "cargo_config_paths_absent": sorted(str(path) for path in config_paths), "compiler_override_names_absent": list(flags)}


def binary_from_build(raw, target):
    require(len(raw) <= P.MAX_LOG_BYTES, "bounded build intake required")
    binaries = []
    for line in raw.splitlines():
        require(len(line) <= P.B.MAX_TRACE_LINE, "build JSON line cap")
        if not line.startswith(b"{"):
            continue  # Cargo's stderr progress shares the bounded owned pipe.
        row = json.loads(line)
        if row.get("reason") == "compiler-artifact" and row.get("profile", {}).get("test") is True \
                and row.get("executable") and row.get("target", {}).get("name") == "chronicler_agents":
            binaries.append(row["executable"])
    require(len(binaries) == 1, "one fresh test executable required")
    path = Path(binaries[0])
    require(path.is_absolute() and not path.is_symlink(), "unsafe compiler executable path")
    path = path.resolve(strict=True)
    require(path.is_relative_to(target.resolve(strict=True)), "compiler executable outside fresh target")
    return path


def linkage_snapshot(binary, command, phase):
    text = command(phase + "-linkage", ["ldd", str(binary)]).decode()
    require("not found" not in text, "unresolved test linkage")
    paths = set()
    for line in text.splitlines():
        match = re.search(r"(?:=>\s+|^\s*)(/\S+)", line)
        if match:
            paths.add(Path(match[1]).resolve(strict=True))
    require(paths, "actual linkage identities unavailable")
    return {str(path): file_identity(path) for path in sorted(paths)}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def nonfinite(_):
        raise P.B.BridgeRefused("nonfinite JSON")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def screen_result(raw, status):
    require(type(status) is int and status in (0, 101), "screen exit was timeout/resource/other failure")
    require(type(raw) is bytes and len(raw) <= P.MAX_LOG_BYTES, "bounded screen bytes required")
    rows = []
    for line in raw.splitlines():
        require(len(line) <= P.B.MAX_TRACE_LINE, "screen JSON line cap")
        at = line.find(b"EXACT_NEAR ")
        if at >= 0:
            rows.append(strict_json(line[at + len(b"EXACT_NEAR "):]))
    require(all(type(row) is dict and row.get("kind") in ("header", "parity", "sample", "decision", "final") for row in rows), "screen record kind differs")
    by_kind = {kind: [row for row in rows if row["kind"] == kind] for kind in ("header", "parity", "sample", "decision", "final")}
    expected_records = [("header", None)]
    for case in CASES:
        expected_records.extend([("parity", case), *[("sample", case)] * 10, ("decision", case)])
    expected_records.append(("final", None))
    require([(row["kind"], row.get("case")) for row in rows] == expected_records, "full screen record order differs")
    require(len(by_kind["header"]) == 1 and by_kind["header"][0] == {"kind": "header", "version": 1,
        "synthetic_only": True, "cases": 15, "pairs": 5, "crossover": 256, "wall_seconds_cap": 60,
        "cpu_seconds_cap": 60, "rss_kib_cap": 524288}, "fixed header differs")
    require(type(by_kind["header"][0]["synthetic_only"]) is bool
        and all(type(value) is int for key, value in by_kind["header"][0].items() if key not in ("kind", "synthetic_only")), "header field types differ")
    numeric_parity = {"old_distances", "new_distances", "new_words", "near_results", "later_far", "incest", "hostile", "valid"}
    routes = {"ReferenceNonFinite", "LinearSmall", "LinearOutOfDomain", "LinearAll", "Grid"}
    for row in by_kind["parity"]:
        require(set(row) == numeric_parity | {"kind", "case", "route", "ordered_near_d2_fnv"}, "parity schema differs")
        require(row["route"] in routes and re.fullmatch(r"[0-9a-f]{16}", row["ordered_near_d2_fnv"]) is not None, "parity identity differs")
        require(all(type(row[key]) is int and 0 <= row[key] < 2**128 for key in numeric_parity), "invalid parity integer")
        require(row["new_distances"] <= row["old_distances"], "candidate distance count exceeds reference")
    require(tuple(row["case"] for row in by_kind["parity"]) == CASES
        and tuple(row["case"] for row in by_kind["decision"]) == CASES, "case order/set differs")
    expected_order = [(case, pair, arm) for case in CASES for pair in range(5)
        for arm in (("old", "candidate") if pair % 2 == 0 else ("candidate", "old"))]
    samples = by_kind["sample"]
    require(len(samples) == 150 and all(type(row.get("pair")) is int for row in samples)
        and [(row["case"], row["pair"], row["arm"]) for row in samples] == expected_order, "sample order/count differs")
    require(all(type(row.get("pass")) is bool for row in by_kind["decision"]), "decision boolean differs")
    numeric_sample = {"pair", "setup_ns", "query_ns", "total_ns_with_drop", "cpu_ticks", "peak_process_rss_kib",
        "index_live_bytes", "index_peak_bytes", "scratch_capacity_bytes", "words", "distances", "gathered"}
    for row in samples:
        require(set(row) == numeric_sample | {"kind", "case", "arm", "route"}, "sample schema differs")
        require(all(type(row[key]) is int and 0 <= row[key] < 2**128 for key in numeric_sample), "invalid sample integer")
        require(row["route"] in routes, "sample route differs")
        require(row["peak_process_rss_kib"] <= 524288, "sample RSS cap exceeded")
    for row in by_kind["decision"]:
        require(set(row) == {"kind", "case", "old_median_ns", "candidate_median_ns", "limit_ns", "pass"}, "decision schema differs")
        require(all(type(row[key]) is int and 0 <= row[key] < 2**128
            for key in ("old_median_ns", "candidate_median_ns", "limit_ns")), "invalid decision integer")
        old = sorted(sample["total_ns_with_drop"] for sample in samples if sample["case"] == row["case"] and sample["arm"] == "old")[2]
        new = sorted(sample["total_ns_with_drop"] for sample in samples if sample["case"] == row["case"] and sample["arm"] == "candidate")[2]
        limit = old * (90 if row["case"] in ("spread1024", "spread4096") else 105) // 100
        if row["case"] in ("empty0", "singleton1", "small16", "spread255", "spread256", "nan1024", "infinity1024"):
            limit += 5000
        require((row["old_median_ns"], row["candidate_median_ns"], row["limit_ns"], row["pass"])
            == (old, new, limit, new <= limit), "decision contradicts fixed sample medians/criteria")
    accepted = all(row["pass"] for row in by_kind["decision"])
    require(len(by_kind["final"]) == 1 and by_kind["final"][0] == {"kind": "final", "complete_cases": 15,
        "samples": 150, "accepted_for_later_planner_work": accepted, "production_promoted": False, "worlds": 0}, "fixed final differs")
    require(type(by_kind["final"][0]["accepted_for_later_planner_work"]) is bool
        and by_kind["final"][0]["production_promoted"] is False
        and all(type(by_kind["final"][0][key]) is int for key in ("worlds", "samples", "complete_cases")), "final field types differ")
    require(status == (0 if accepted else 101), "screen exit contradicts decisions")
    require(re.search(rb"test result: " + (b"ok" if accepted else b"FAILED")
        + rb"\. " + (b"1 passed; 0 failed;" if accepted else b"0 passed; 1 failed;"), raw) is not None,
        "ignored Rust test terminal summary differs")
    return {"execution_complete": True, "screen_accepted": accepted, "screen_exit": status,
        "decisions": by_kind["decision"], "cases": list(CASES), "samples": 150}


def stage_light(root, report):
    light = root / "light"
    require(light.is_dir() and not light.is_symlink(), "fresh light directory missing")
    omissions = []
    # Named metadata + bounded child log excerpts only, never the binary/target.
    for path in sorted(root.iterdir()):
        if path.name.endswith((".json", ".time")):
            require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), "unsafe metadata publication input")
            require(path.stat().st_size <= MAX_FILE, "metadata input exceeds publication cap")
            shutil.copyfile(path, light / path.name)
    for path in sorted((root / "logs").glob("*.log")):
        require(not path.is_symlink() and path.stat().st_size <= P.MAX_LOG_BYTES, "unsafe/oversize raw child log")
        size = path.stat().st_size
        with path.open("rb") as stream:
            head = stream.read(MAX_LOG_COPY // 2)
            if size > MAX_LOG_COPY:
                stream.seek(-MAX_LOG_COPY // 2, os.SEEK_END)
                raw = head + b"\n[explicit middle omission]\n" + stream.read(MAX_LOG_COPY // 2)
            else:
                raw = head + stream.read(MAX_LOG_COPY // 2)
        (light / path.name).write_bytes(raw)
        omissions.append({"name": path.name, "raw": file_identity(path, P.MAX_LOG_BYTES),
            "published_bytes": len(raw), "middle_omitted": size > MAX_LOG_COPY})
    report["log_publication"] = omissions
    report["progress"] = file_identity(root / "progress.jsonl", P.MAX_PROGRESS_BYTES) if (root / "progress.jsonl").exists() else None
    # Keep cleanup/return/resource observations in the bounded terminal too.
    if (root / "progress.jsonl").exists():
        events = [json.loads(line) for line in (root / "progress.jsonl").read_bytes().splitlines()]
        report["child_outcomes"] = [row for row in events if row.get("event") in ("child_cleanup", "child_exit")]
    files = {path.name: file_identity(path, MAX_FILE) for path in light.iterdir() if path.name != "terminal.json"}
    require(len(files) + 1 <= MAX_LIGHT_FILES and sum(row["bytes"] for row in files.values()) + len(canonical(report)) <= MAX_LIGHT,
        "bounded light pack admission refused")
    report["payloads"] = files
    write_json(light / "terminal.json", report)
    require(sum(path.stat().st_size for path in light.iterdir()) <= MAX_LIGHT, "final light pack byte cap")


def final_files(source, binary, runtime):
    result = {"source": {}, "binary": None, "runtime_files": {}, "errors": {}}
    for name in INPUTS:
        try:
            result["source"][name] = file_identity(source / name, MAX_FILE)
        except BaseException as exc:
            result["errors"][name] = type(exc).__name__
    if binary is not None:
        try:
            result["binary"] = {"path": str(binary), **file_identity(binary)}
        except BaseException as exc:
            result["errors"]["binary"] = type(exc).__name__
    if runtime is not None:
        paths = {row["resolved"] for row in runtime["tools"].values()}
        paths.update(row["resolved"] for row in runtime["dispatched_compilers"].values())
        paths.update((runtime["python_executable"], runtime["python_library"]))
        for name in sorted(paths):
            try:
                result["runtime_files"][name] = file_identity(Path(name))
            except BaseException as exc:
                result["errors"][name] = type(exc).__name__
    return result


def run():
    start = time.monotonic(); deadline = start + OWNER_SECONDS
    root = Path(os.environ["RUNNER_TEMP"]).resolve() / "exact-marriage-screen"
    source = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    report = {"schema_version": 1, "kind": "exact-near-synthetic-owner", "status": "incomplete",
        "execution_complete": False, "screen_accepted": False, "cleanup_complete": False,
        "worlds": 0, "production_promoted": False, "whole_planner_speedup_claim": False,
        "phases_reached": [], "owner_wall_limit_seconds": OWNER_SECONDS}
    failed = None; supervisor = None; cancellation = None; binary = None; runtime = None; before = None
    try:
        require(root.is_dir() and not root.is_symlink() and (root / "light/terminal.json").is_file(), "bootstrap negative receipt missing")
        require(set(path.name for path in root.iterdir()) == {"light"}, "fresh external owner paths required")
        (root / "logs").mkdir()
        report["context"] = require_context(os.environ)
        require(Path(__file__).resolve() == source / "scripts/run_exact_near_screen.py", "actual owner source path differs")
        require(sys.platform == "linux" and platform.python_version() == "3.13.5", "Linux/Python3.13.5 required")
        report["deployment_before"] = hosted_vm_precondition()
        for name, digest in (("wealth_floor_build_resources.py", RESOURCE_SHA), ("wealth_floor_hosted_deployment.py", DEPLOYMENT_SHA)):
            require(file_identity(source / "scripts" / name)["sha256"] == digest, "qualified dependency hash differs")
        for name in tuple(os.environ):
            require(not name.startswith("GIT_"), "inherited Git override refused")
        target = Path(os.environ["RUNNER_TEMP"]).resolve() / "exact-marriage-target"
        require(not target.exists() and not target.is_symlink(), "fresh build target required")
        cpu = min(os.sched_getaffinity(0)); os.sched_setaffinity(0, {cpu})
        env = dict(os.environ, CARGO_TARGET_DIR=str(target), CHRONICLER_SCREEN_CLK_TCK=str(os.sysconf("SC_CLK_TCK")), PYO3_PYTHON=sys.executable)
        libdir = sysconfig.get_config_var("LIBDIR")
        require(libdir and Path(libdir).is_dir(), "Python library directory unavailable")
        for key in ("LIBRARY_PATH", "LD_LIBRARY_PATH"):
            env[key] = libdir + (":" + env[key] if env.get(key) else "")
        cancellation = P.Cancellation(); cancellation.__enter__()
        with P.SubreaperLease() as lease:
            supervisor = P.make_supervisor(P.legacy, root, deadline, lease, cancellation)
            def command(label, argv, allowed=(0,)):
                report["phases_reached"].append(label)
                # This adapter intentionally never exposes the omitted trace branch.
                return supervisor.command(label, argv, env, source, allowed_exit_codes=allowed, trace=False)
            phase_failed = False
            try:
                before = source_snapshot(source, command, "before")
                write_json(root / "source-before.json", before)
                runtime = runtime_snapshot(source, env, command, "before")
                write_json(root / "runtime-before.json", runtime)
                build_admission = admission(root, 12, 2)
                write_json(root / "build-memory-admission.json", build_admission)
                require(build_admission["admitted"], "registered build admission refused")
                raw = command("build", ["/usr/bin/time", "-v", "-o", str(root / "build-process.time"),
                    "timeout", "--signal=TERM", "--kill-after=10s", "2100s", "taskset", "-c", str(cpu),
                    "cargo", "test", "--release", "--locked", "--manifest-path", "chronicler-agents/Cargo.toml",
                    "--lib", "--no-run", "--message-format=json"])
                binary = binary_from_build(raw, target)
                binary_before = {"path": str(binary), **file_identity(binary)}
                write_json(root / "test-binary-before.json", binary_before)
                linkage = linkage_snapshot(binary, command, "before")
                write_json(root / "linkage-before.json", linkage)
                test_admission = admission(root, 3, 1)
                write_json(root / "test-memory-admission.json", test_admission)
                require(test_admission["admitted"], "registered test admission refused")
                raw = command("contracts", ["timeout", "--signal=TERM", "--kill-after=5s", "60s", "taskset", "-c", str(cpu), str(binary),
                    "formation::exact_near_broadphase_experiment::", "--test-threads=1", "--nocapture"])
                require(re.search(rb"test result: ok\. 6 passed; 0 failed; 1 ignored;", raw) is not None, "six ordinary contracts did not pass")
                raw = command("original-radius", ["timeout", "--signal=TERM", "--kill-after=5s", "15s", "taskset", "-c", str(cpu), str(binary),
                    "formation::tests::marriage_radius_threshold_is_exact", "--exact", "--test-threads=1"])
                require(re.search(rb"test result: ok\. 1 passed; 0 failed; 0 ignored;", raw) is not None, "original radius contract did not pass")
                raw = command("screen", ["/usr/bin/time", "-v", "-o", str(root / "screen-process.time"),
                    "timeout", "--signal=TERM", "--kill-after=5s", "70s", "taskset", "-c", str(cpu), str(binary),
                    "formation::exact_near_broadphase_experiment::exact_near_broadphase_fixed_screen", "--exact", "--ignored", "--nocapture", "--test-threads=1"], (0, 101))
                # Exit is recorded by the qualified supervisor after owned cleanup.
                exit_rows = [json.loads(line) for line in (root / "progress.jsonl").read_bytes().splitlines()]
                status = [row["returncode"] for row in exit_rows if row.get("event") == "child_exit" and row.get("label") == "screen"]
                require(len(status) == 1, "one screen child exit required")
                outcome = screen_result(raw, status[0]); write_json(root / "screen-result.json", outcome)
                after = source_snapshot(source, command, "after"); write_json(root / "source-after.json", after)
                runtime_after = runtime_snapshot(source, env, command, "after"); write_json(root / "runtime-after.json", runtime_after)
                binary_after = {"path": str(binary), **file_identity(binary)}; write_json(root / "test-binary-after.json", binary_after)
                linkage_after = linkage_snapshot(binary, command, "after"); write_json(root / "linkage-after.json", linkage_after)
                require(before == after and runtime == runtime_after and binary_before == binary_after and linkage == linkage_after,
                    "final source/runtime/executable/linkage identity changed")
                report.update(outcome)
                report["deployment_after"] = hosted_vm_precondition()
                require(report["deployment_before"] == report["deployment_after"], "deployment context changed")
                supervisor.check(final=True)
            except BaseException:
                phase_failed = True
                raise
            finally:
                try:
                    terminal_source = source_snapshot(source, command, "terminal")
                    write_json(root / "source-terminal.json", terminal_source)
                    if before is not None:
                        require(terminal_source == before, "terminal Git/source identity changed")
                except BaseException as exc:
                    report["terminal_git_error"] = type(exc).__name__
                    if not phase_failed:
                        raise
                finally:
                    report["final_files"] = final_files(source, binary, runtime)
                    if not phase_failed:
                        require(not report["final_files"]["errors"], "terminal file observation incomplete")
                        require(report["final_files"]["source"] == before["files"], "terminal actual source bytes changed")
                        require(report["final_files"]["binary"] == binary_before, "terminal executable bytes changed")
                        expected_runtime = {row["resolved"]: {key: row[key] for key in ("bytes", "sha256")} for row in runtime["tools"].values()}
                        expected_runtime.update({row["resolved"]: {key: row[key] for key in ("bytes", "sha256")}
                            for row in runtime["dispatched_compilers"].values()})
                        expected_runtime.update({runtime["python_executable"]: runtime["python_executable_identity"],
                            runtime["python_library"]: runtime["python_library_identity"]})
                        require(report["final_files"]["runtime_files"] == expected_runtime, "terminal runtime bytes changed")
        require(not P.direct_children() and supervisor.cleanup_complete, "final owned child quiescence unverified")
        report["cleanup_complete"] = True
    except BaseException as exc:
        failed = exc
        report["error"] = type(exc).__name__
    finally:
        # Source and actual binary identities on early failure are observations,
        # never silently filled with the before values or granted completion.
        if "final_files" not in report:
            report["final_files"] = final_files(source, binary, runtime)
            report["terminal_git_error"] = "unavailable_before_owned_context"
        if supervisor is not None:
            report["supervisor_cleanup_complete"] = supervisor.cleanup_complete
        try:
            require(not P.direct_children(), "late owned descendant remains")
            if cancellation is not None:
                cancellation.check(); cancellation.__exit__(None, None, None); cancellation = None
            final = admission(root, 3, 1); write_json(root / "final-memory-admission.json", final)
            require(final["admitted"] and time.monotonic() <= deadline, "final budget/resource closure refused")
            if failed is None:
                report["status"] = "complete-accepted" if report["screen_accepted"] else "complete-rejected"
            else:
                report["execution_complete"] = False; report["screen_accepted"] = False
            report["wall_seconds_before_publication"] = time.monotonic() - start
            stage_light(root, report)
            report["post_pack_memory_admission"] = admission(root, 3, 1)
            require(report["post_pack_memory_admission"]["admitted"], "post-pack resource closure refused")
            require(sum(path.stat().st_size for path in (root / "light").iterdir() if path.name != "terminal.json")
                + len(canonical(report)) <= MAX_LIGHT, "post-pack terminal byte cap")
            write_json(root / "light/terminal.json", report)
            require(not P.direct_children() and time.monotonic() <= deadline, "late cleanup/publication deadline failure")
        except BaseException as exc:
            failed = failed or exc
            report.update(status="incomplete", execution_complete=False, screen_accepted=False, finalization_error=type(exc).__name__)
            try:
                write_json(root / "light/terminal.json", report)
            except BaseException:
                pass  # The always closure step retains the initial negative if no safe write succeeds.
        if cancellation is not None:
            try:
                cancellation.__exit__(type(failed), failed, None)
            except BaseException:
                failed = failed or P.B.BridgeRefused("signal handler restoration failed")
                report.update(status="incomplete", execution_complete=False, screen_accepted=False)
                try:
                    write_json(root / "light/terminal.json", report)
                except BaseException:
                    pass
    print(json.dumps({key: report[key] for key in ("status", "execution_complete", "screen_accepted", "cleanup_complete", "worlds")}))
    return 0 if failed is None and report["screen_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
