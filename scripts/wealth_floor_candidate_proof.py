#!/usr/bin/env python3
"""Dormant, bounded mechanical proofs for the held wealth-floor candidate.

This bootstrap is separate from A's final outcome-cohort admission. No default
command stages an artifact, imports native code or creates a world. The completed
paired build is content-pinned after independent review; this bootstrap source
and its eventual execution need separate review. The parent is stdlib-only;
scientific imports occur only in supervised source503 children after admission.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import resource
import shutil
import stat
import sys
import time
from types import MappingProxyType
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parent))
import wealth_floor_native_build_bridge as B
import wealth_floor_native_build_controller as C
from wealth_floor_hosted_deployment import hosted_vm_precondition

ACTIVE_BRANCH = "lead/wealth-floor-candidate-proof-activation-20261029"
WORKFLOW_PATH = ".github/workflows/wealth-floor-candidate-proof.yml"
TEMPLATE_PATH = "docs/experiments/wealth-floor-candidate-proof.yml.inactive"
REPOSITORY = "YotsuBotfds/Chronicler"
WALL_SECONDS = 1800
STAGING_WALL_SECONDS = 180
MAX_INPUT_BYTES = 256 * B.MIB
MAX_INPUT_FILES = 512
MAX_JSON = 2 * B.MIB
MAX_OUTPUT_BYTES = 1024 * B.MIB
MAX_OUTPUT_FILES = 8192
WORKFLOW_SHA256 = "e1506e62382e57680bc6c93a72cf94876eff6d3ee9f1cc69ab4e5ca2b2d8e359"
KERNELS = MappingProxyType({
    "tests/test_run_checkpoint_native.py": "88e7baafc82a019448924d7501b2e4585b76720df718de413b5ac9713dec206e",
    "scripts/m53b_run_validation.py": "42030add6479c784546261b341686a11b481ab1b0c125bfe4ca0b6925739198a",
    "src/chronicler/run_checkpoint.py": "1c450476e4013c2d8ec7bda342d8d0495b2608501bdb8cb762cbe3b777504ce0",
})
DEPENDENCIES = MappingProxyType({
    "scripts/wealth_floor_baseline_admission.py": "9deced451f5edb3920c786a52c4d2a927cf9ae11af0ffb4e7450ff1d74fd0bed",
    "scripts/wealth_floor_native_build_bridge.py": "cb87ff673817fc655beb39cce88c39295cfa87dcd787e108e2cbf85026965373",
    "scripts/wealth_floor_native_build_controller.py": "60bb77212757f632d8d80ed226f94e6ef9864134c4453b5affeb51dc059b9dd1",
    "scripts/wealth_floor_build_resources.py": "44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2",
    "scripts/wealth_floor_hosted_deployment.py": "d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8",
    C.LEGACY_FILE: C.LEGACY_SHA,
})
# These are root-qualified source registration pins, never caller/CLI overrides.
# A's REVIEWED_CANDIDATE_PROOFS remains unchanged and null.
ROOT_BUILD_RECEIPT_SHA256 = "72e545308da0cf24d23113e350adf388f75de230ba296453a87eb7b6ba8920a6"
REVIEWED_BUILD = MappingProxyType(dict(
    control_sha="3bf976cde1f0b4809945162395714e5aacccebdd", run_id=40820753788, job_id=123272420780,
    attempt=1, artifact_id=12874494535, artifact_bytes=9041361,
    artifact_sha256="fe23a7da31d04d7dd751937ba5050e953fa6a6597b865148bc11b559270b2ff9",
    artifact_expires_at="2026-11-28T05:11:23Z", root_prefix="",
    completion_sha256="442f58798e655f241290baa0020456e26107193f7d2ec5696549f6599460ce59",
    manifest_sha256="dffb6aa2f07d89a23aad89a9988dd37f39f876cbff29c573838010cdbbb09169",
    inventory_sha256="f9cdd8fddc3dcd8ae87815ff54d721e5dc7fa04fc3b7e15cba7b4e09842faf61",
    light_index_sha256="221b28e582a3ad366f36c3f9b430a8eb52ea2c46f9503f3f0346d1793c1e4e81",
    baseline_wheel_sha256="2e491456d01c2dd7bb2f7688e6acbc06b614610bbbe5be5ea6f0832ae220759a",
    candidate_wheel_sha256="4ebf720dfb1f39d4e19069cbadb44cfd60d1476874c41ec97dd19c69ae354d9a",
    baseline_native_sha256=B.OLD_NATIVE,
    candidate_native_sha256="b56c43f16722be2c8fc6fbe5c021ec292f9a6856783d946af56d97e91575e619",
    context_sha256="5aa8f0b521fe60666789ebc2ba058b9015df9104d1287a7bfa0e22caf22cc1ab",
))
CASE_NAMES = frozenset((
    "test_resume_identity_in_each_mode[hybrid-extra0]",
    "test_resume_identity_in_each_mode[demographics-only-extra1]",
    "test_resume_identity_in_each_mode[shadow-extra2]",
    "test_resume_identity_in_each_mode[off-extra3]",
    "test_simulator_state_round_trips_and_refuses_another_simulator",
    "test_war_roster_marker_is_rebound_to_the_restored_simulator",
))
PYTEST_TEMP_PREFIXES = MappingProxyType({
    "test_resume_identity_in_each_m": frozenset(range(4)),
    "test_war_roster_marker_is_rebo": frozenset((0,)),
})
RAW_ROOT_FILES = frozenset(("progress.jsonl", "checkpoint.xml", "checkpoint-index.json", "cross-native.json",
    "control-sources-before.json", "control-sources-after.json", "control-git-before.json", "control-git-after.json",
    "candidate-source-before.json", "candidate-source-after.json", "candidate-probe.json", "baseline-probe.json"))
RAW_DIRECTORIES = frozenset(("checkpoints", "template", "procedural", "logs"))


class ProofRefused(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise ProofRefused(reason)


def exact(left, right):
    return B.canonical_bytes(left) == B.canonical_bytes(right)


def registration():
    pins = dict(REVIEWED_BUILD)
    require(all(value is not None for value in pins.values()), "completed build registration remains pending; no install or worlds")
    require(type(pins["control_sha"]) is str and re.fullmatch("[0-9a-f]{40}", pins["control_sha"]), "build control identity")
    for key in ("run_id", "job_id", "attempt", "artifact_id", "artifact_bytes"):
        require(type(pins[key]) is int and pins[key] > 0, "numeric build publication identity")
    require(pins["artifact_bytes"] <= MAX_INPUT_BYTES, "build wrapper exceeds registered bound")
    for key in pins:
        if key.endswith("sha256"):
            require(B.hash_shape(pins[key]), "build digest registration")
    require(pins["baseline_native_sha256"] != pins["candidate_native_sha256"], "distinct native identities required")
    require(type(pins["root_prefix"]) is str and (pins["root_prefix"] == "" or safe_name(pins["root_prefix"])), "staged root prefix")
    expiry(pins["artifact_expires_at"])
    return MappingProxyType(pins)


def expiry(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value), "publication expiry shape")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProofRefused("publication expiry invalid") from exc


def safe_name(value):
    require(type(value) is str and value and "\0" not in value and "\\" not in value, "unsafe staged name")
    p = PurePosixPath(value)
    require(not p.is_absolute() and p.as_posix() == value and all(part not in (".", "..") for part in p.parts), "unsafe staged name")
    return value


@contextmanager
def regular(root, name):
    """Anchor every directory; atomically refuse links, FIFOs and replacements."""
    parts = PurePosixPath(safe_name(name)).parts
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    directory = os.open(root, flags | os.O_DIRECTORY)
    opened = [directory]
    try:
        for part in parts[:-1]:
            directory = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory); opened.append(directory)
        fd = os.open(parts[-1], flags, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "staged input must be a unique regular file")
            yield stream, before
            after = os.fstat(stream.fileno())
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
            require(identity(before) == identity(after) == identity(current), "staged file changed")
    finally:
        for fd in reversed(opened):
            os.close(fd)


def read_bytes(root, name, limit=MAX_JSON, check=lambda: None):
    check()
    with regular(root, name) as (stream, info):
        require(info.st_size <= limit, "bounded staged input size")
        raw = stream.read(limit + 1)
        require(len(raw) == info.st_size and len(raw) <= limit, "bounded staged input EOF")
    check()
    return raw


def parse(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ProofRefused("nonfinite JSON")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProofRefused("invalid staged JSON") from exc


def read_json(root, name, check=lambda: None):
    return parse(read_bytes(root, name, check=check))


def inventory(root, *, max_bytes=MAX_INPUT_BYTES, max_files=MAX_INPUT_FILES, check=lambda: None, exclude=()):
    """Bounded physical inventory; no links, aliases, special files or empty trees."""
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "regular staged root required")
    files, identities, total, directories = {}, set(), 0, 0
    excluded = frozenset(exclude)
    require(all(safe_name(name) == name for name in excluded), "inventory exclusion shape")
    def visit(directory, prefix):
        nonlocal total, directories
        check(); directories += 1
        require(directories <= max_files, "staged directory cap")
        entries = []
        with os.scandir(directory) as iterator:
            for entry in iterator:
                require(len(entries) < max_files, "staged directory entry cap")
                entries.append(entry)
        require(bool(entries), "unexpected empty staged directory")
        for entry in sorted(entries, key=lambda row: row.name):
            check(); name = safe_name(prefix + entry.name)
            if name in excluded:
                continue
            info = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode), "staged symlink refused")
            if stat.S_ISDIR(info.st_mode):
                child_fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                try:
                    opened = os.fstat(child_fd)
                    require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), "staged directory changed")
                    visit(child_fd, name + "/")
                    current = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
                    require((current.st_dev, current.st_ino, current.st_mtime_ns, current.st_ctime_ns) ==
                        (opened.st_dev, opened.st_ino, opened.st_mtime_ns, opened.st_ctime_ns), "staged directory drift")
                finally:
                    os.close(child_fd)
                continue
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "staged nonregular/aliased input")
            require((info.st_dev, info.st_ino) not in identities, "physical staged alias")
            identities.add((info.st_dev, info.st_ino)); total += info.st_size
            require(len(files) < max_files and total <= max_bytes, "staged aggregate bounds")
            digest = hashlib.sha256()
            with regular(root, name) as (stream, opened):
                require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), "staged identity changed")
                actual = 0
                while block := stream.read(B.MIB):
                    check(); actual += len(block); require(actual <= info.st_size, "staged input grew"); digest.update(block)
                require(actual == info.st_size, "staged EOF differs")
            files[name] = dict(bytes=info.st_size, sha256=digest.hexdigest())
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        visit(fd, "")
    finally:
        os.close(fd)
    return files


def validate_publication(metadata, pins, *, now):
    require(type(metadata) is dict and set(metadata) == {"run", "jobs", "artifact"}, "closed publication metadata")
    run, artifact, jobs = metadata["run"], metadata["artifact"], metadata["jobs"]
    for obj in (run, artifact):
        require(type(obj) is dict, "publication metadata object")
    require(type(jobs) is dict and type(jobs.get("jobs")) is list and len(jobs["jobs"]) <= 32, "bounded completed jobs")
    require(type(run.get("id")) is int and run["id"] == pins["run_id"] and type(run.get("run_attempt")) is int
        and run["run_attempt"] == pins["attempt"] and run.get("head_sha") == pins["control_sha"]
        and run.get("head_branch") == B.ACTIVE_BRANCH and run.get("path") == B.WORKFLOW_PATH
        and run.get("status") == "completed" and run.get("conclusion") == "success"
        and run.get("repository", {}).get("full_name") == REPOSITORY, "completed build run origin")
    matching = [job for job in jobs["jobs"] if job.get("id") == pins["job_id"] and type(job.get("id")) is int]
    require(len(matching) == 1, "exact completed build job missing")
    job = matching[0]
    require(type(job.get("run_id")) is int and job["run_id"] == pins["run_id"]
        and job.get("head_sha") == pins["control_sha"] and job.get("status") == "completed"
        and job.get("conclusion") == "success", "completed build job attestation")
    require(type(artifact.get("id")) is int and artifact["id"] == pins["artifact_id"]
        and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] == pins["artifact_bytes"]
        and artifact.get("digest") == "sha256:" + pins["artifact_sha256"] and artifact.get("expired") is False
        and artifact.get("expires_at") == pins["artifact_expires_at"]
        and artifact.get("name") == f"wealth-native-raw-{pins['run_id']}-{pins['attempt']}"
        and type(artifact.get("workflow_run", {}).get("id")) is int
        and artifact["workflow_run"]["id"] == pins["run_id"]
        and artifact.get("workflow_run", {}).get("head_sha") == pins["control_sha"], "exact raw build publication")
    require(now < expiry(pins["artifact_expires_at"]), "build publication expired")


_SEAL = object()


@dataclass(frozen=True)
class AdmittedBuild:
    root: Path
    inventory_bytes: bytes
    manifest_bytes: bytes
    pins_bytes: bytes
    _seal: object


def admit_build(staged, metadata, *, now, check=lambda: None):
    pins = registration()  # This must precede any path or artifact access.
    validate_publication(metadata, pins, now=now)
    staged = Path(staged)
    all_files = inventory(staged, check=check)
    prefix = pins["root_prefix"]
    prefix = prefix + "/" if prefix else ""
    require(all(name.startswith(prefix) for name in all_files), "unexpected raw artifact root")
    root = staged / pins["root_prefix"]
    files = {name[len(prefix):]: row for name, row in all_files.items()}
    for name, slot in (("completion.json", "completion_sha256"), ("build-manifest.json", "manifest_sha256"),
                       ("raw-inventory.json", "inventory_sha256"), ("light/index.json", "light_index_sha256")):
        require(files.get(name, {}).get("sha256") == pins[slot], "reviewed build seal differs: " + name)
    completion = read_json(root, "completion.json", check)
    require(completion.get("schema_version") == 1 and type(completion.get("schema_version")) is int
        and completion.get("kind") == "wealth-floor-native-build-completion"
        and completion.get("publication_complete") is True, "build publication incomplete")
    sealed_names = {"build-manifest.json", "raw-inventory.json", "light/index.json"}
    require(type(completion.get("files")) is dict and set(completion["files"]) == sealed_names
        and all(exact(completion["files"][name], files[name]) for name in sealed_names), "build completion binding differs")
    manifest_raw = read_bytes(root, "build-manifest.json", check=check); manifest = parse(manifest_raw)
    require(manifest.get("publication_status") == "provisional_until_matching_completion_seal", "build publication status")
    phases = manifest.get("phases", {})
    require(type(phases) is dict and set(phases) == {"baseline", "candidate"}, "complete paired phases required")
    core = B.classify_pair(phases["baseline"], phases["candidate"], manifest.get("measured"))
    require(all(key in manifest and exact(manifest[key], value) for key, value in core.items()), "recomputed paired build differs")
    producer = manifest.get("producer")
    require(exact(producer, dict(control_sha=pins["control_sha"], run_id=str(pins["run_id"]),
        run_attempt=str(pins["attempt"]), job_key="paired-native-build")), "manifest producer origin differs")
    require(core["baseline_context_sha256"] == core["candidate_context_sha256"] == pins["context_sha256"], "registered context differs")
    raw_index = read_json(root, "raw-inventory.json", check); light = read_json(root, "light/index.json", check)
    require(type(raw_index.get("files")) is dict and type(light.get("files")) is dict
        and set(light["files"]) == set(C.LIGHT_NAMES), "closed build inventory/light set")
    expected = dict(raw_index["files"])
    require(not (set(expected) & (sealed_names | {"completion.json"})) and not any(name.startswith("light/") for name in expected), "recursive raw index")
    require(type(raw_index.get("file_count")) is int and raw_index["file_count"] == len(expected)
        and type(raw_index.get("total_bytes")) is int and raw_index["total_bytes"] == sum(row["bytes"] for row in expected.values()), "raw inventory totals")
    for name, row in light["files"].items():
        safe_name(name)
        require(exact(files.get(name), row), "original light payload differs")
        expected["light/" + name] = row
    for name in sealed_names | {"completion.json"}:
        expected[name] = files[name]
    require(exact(expected, files), "staged exact payload set/hash differs")
    for role in ("baseline", "candidate"):
        phase = phases[role]
        for name, value in (("source-before.json", phase["source_before_sha256"]), ("source-after.json", phase["source_after_sha256"])):
            require(files[role + "/" + name]["sha256"] == value, "phase source snapshot binding")
        for name, value in (("probe.json", phase["probe"]), ("context.json", phase["context"])):
            require(exact(read_json(root, role + "/" + name, check), value), "phase payload binding")
        wheel = read_bytes(root, f"wheels/{role}/{B.WHEEL_NAME}", B.MAX_WHEEL_BYTES, check)
        facts = B.inspect_wheel(wheel, B.WHEEL_NAME)
        require(exact(facts, phase["wheel"]) and facts["sha256"] == pins[role + "_wheel_sha256"]
            and facts["native_sha256"] == pins[role + "_native_sha256"], "staged whole wheel/native differs")
    require(exact(read_json(root, "candidate/regression-loader.json", check), manifest.get("regression_loader")), "regression loader binding")
    check()
    return AdmittedBuild(root, B.canonical_bytes(files), manifest_raw, B.canonical_bytes(dict(pins)), _SEAL)


def recheck_build(build, check=lambda: None):
    require(type(build) is AdmittedBuild and build._seal is _SEAL, "factory-admitted build required")
    require(exact(parse(build.pins_bytes), dict(registration())), "build registration drift")
    require(B.canonical_bytes(inventory(build.root, check=check)) == build.inventory_bytes, "admitted build changed")


def checkpoint_junit(raw):
    require(type(raw) is bytes and len(raw) <= B.MIB and b"<!" not in raw, "bounded plain JUnit required")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ProofRefused("invalid checkpoint JUnit") from exc
    cases = list(root.iter("testcase"))
    require(len(cases) == 6 and {case.get("name") for case in cases} == CASE_NAMES, "exact six checkpoint parent identities required")
    require(all(case.get("classname") == "tests.test_run_checkpoint_native" for case in cases), "checkpoint parent source identity")
    require(all(not list(case) for case in cases), "checkpoint tests must PASS with zero skips/failures/errors")
    suites = list(root.iter("testsuite"))
    require(bool(suites) and all(suite.get(key) in ("0", None) for suite in suites for key in ("failures", "errors", "skipped")), "checkpoint suite not clean")
    return dict(status="PASS", passed=6, skipped=0, cases=sorted(CASE_NAMES), physics_ticks=126)


def determinism_result(root, worldgen, candidate_native, check=lambda: None):
    require(worldgen in ("template", "procedural") and B.hash_shape(candidate_native), "registered determinism identity")
    root = Path(root)
    manifest = read_json(root, "batch_manifest.json", check)
    summary = read_json(root, "run_manifest.json", check)
    report = read_json(root, "validate_report_determinism_hybrid.json", check)
    require(manifest.get("status") == "complete" and exact(manifest.get("seeds"), [42, 42])
        and type(manifest.get("turns")) is int and manifest["turns"] == 200, "complete genuine repeated-seed manifest required")
    require(summary.get("profile") == "determinism-hybrid" and summary.get("worldgen") == worldgen
        and summary.get("gate_status") == "PASS" and type(summary.get("gate_exit_code")) is int and summary["gate_exit_code"] == 0
        and type(summary.get("turns")) is int and summary["turns"] == 200 and summary.get("ablation_oracles") is False,
        "registered determinism profile must pass")
    gate = report.get("results", {}).get("determinism", {})
    require(gate.get("status") == "PASS" and type(gate.get("pairs_checked")) is int and gate["pairs_checked"] == 1
        and exact(gate.get("duplicate_seeds"), [42]) and exact(gate.get("mismatches"), [])
        and gate.get("reason") == "bundles_match", "actual determinism oracle must PASS one genuine pair, never SKIP")
    require(manifest.get("native", {}).get("sha256") == candidate_native, "repeat native identity differs")
    simulation = manifest.get("simulation", {})
    require(simulation.get("agents") == "hybrid" and type(simulation.get("turns")) is int and simulation["turns"] == 200,
        "repeat simulation facts differ")
    if worldgen == "procedural":
        require(simulation.get("worldgen") == "procedural" and type(simulation.get("regions")) is int and simulation["regions"] == 32
            and type(simulation.get("civs")) is int and simulation["civs"] == 10, "procedural repeat dimensions")
    else:
        require(all(simulation.get(key) is None for key in ("worldgen", "regions", "civs")), "template uses unchanged CLI dimension defaults")
    rows = manifest.get("runs")
    require(type(rows) is list and len(rows) == 2, "two genuine repeats required")
    identities, bundles = set(), []
    for row, suffix in zip(rows, ("a", "b")):
        name = f"seed_42_{suffix}/chronicle_bundle.json"
        require(type(row) is dict and type(row.get("seed")) is int and row["seed"] == 42
            and row.get("dir") == f"seed_42_{suffix}" and row.get("bundle") == name
            and type(row.get("total_turns")) is int and row["total_turns"] == 200
            and type(row.get("files")) is dict and B.hash_shape(row["files"].get(name)), "exact independent run facts required")
        with regular(root, name) as (stream, info):
            require((info.st_dev, info.st_ino) not in identities, "repeat bundle physical alias")
            identities.add((info.st_dev, info.st_ino)); digest = hashlib.sha256(); actual = 0
            while block := stream.read(B.MIB):
                check(); actual += len(block); require(actual <= MAX_OUTPUT_BYTES, "repeat bundle cap"); digest.update(block)
            require(actual == info.st_size and digest.hexdigest() == row["files"][name], "repeat recorded bundle hash differs")
            bundles.append(dict(path=name, bytes=actual, sha256=digest.hexdigest()))
    return dict(status="PASS", seed=42, independent_runs=2, turns=200, worldgen=worldgen, bundles=bundles, physics_ticks=400)


def negative_result(value, expected_checkpoint, candidate_native, baseline_native):
    expected = dict(status="PASS", checkpoint_sha256=expected_checkpoint, candidate_native_sha256=candidate_native,
        observed_native_sha256=baseline_native, exception="CheckpointIncompatible", mismatch_fields=["native extension"],
        native_restore_calls=0, python_restore_calls=0, allow_mismatch=False, source_sha=B.CANDIDATE_SOURCE)
    require(exact(value, expected), "cross-native refusal must be solely native identity, before any restore")
    return expected


def authority_completion(files):
    require(type(files) is dict and "completion.json" not in files, "nonrecursive authority inventory")
    for name, row in files.items():
        safe_name(name)
        require(type(row) is dict and set(row) == {"bytes", "sha256"} and type(row["bytes"]) is int
            and row["bytes"] >= 0 and B.hash_shape(row["sha256"]), "authority row shape")
    completion = dict(publication_complete=True, files=files,
        status="pending_exact_artifact_digest_and_completed_successful_producer", candidate_worlds_admitted=False)
    require(len(files) + 1 <= 32 and sum(row["bytes"] for row in files.values()) + len(B.canonical_bytes(completion)) <= 8 * B.MIB,
        "authority bounds include completion itself")
    return completion


def raw_upload_coverage(files):
    require(type(files) is dict and RAW_ROOT_FILES <= files.keys(), "raw publication omits required root metadata")
    for name in files:
        safe_name(name)
        require(name in RAW_ROOT_FILES or ("/" in name and name.split("/", 1)[0] in RAW_DIRECTORIES),
            "indexed raw payload is outside exact workflow upload set")
    return files


def kernel_command(python, source, kind, output):
    if kind == "checkpoint":
        return [str(python), "-B", "-m", "pytest", "-q", "tests/test_run_checkpoint_native.py", "-p", "no:cacheprovider",
            "--basetemp=" + str(output / "scratch"), "--junitxml=" + str(output / "checkpoint.xml")]
    require(kind in ("template", "procedural"), "unknown proof kernel")
    return [str(python), "-B", str(source / "scripts/m53b_run_validation.py"), "--profile", "determinism-hybrid",
        "--worldgen", kind, "--output-root", str(output / kind)]


def source_bindings(control):
    names = dict(DEPENDENCIES)
    names["scripts/wealth_floor_candidate_proof.py"] = None
    result = {}
    for name, expected in names.items():
        raw = read_bytes(control, name, 2 * B.MIB)
        value = hashlib.sha256(raw).hexdigest()
        require(expected is None or value == expected, "reviewed dependency source differs")
        result[name] = dict(bytes=len(raw), sha256=value)
    return result


def workflow_contract(raw, active_text=None):
    require(type(raw) is bytes and hashlib.sha256(raw).hexdigest() == WORKFLOW_SHA256, "registered workflow body/path/branch differs")
    require(active_text is None or (type(active_text) is bytes and active_text == raw), "actual workflow must equal reviewed template byte-for-byte")
    return dict(status="dormant" if active_text is None else "exact_registered_copy", sha256=WORKFLOW_SHA256)


def staging_observation(temporary, *, clock=time.monotonic):
    require(type(os.environ.get("GITHUB_SHA")) is str and re.fullmatch("[0-9a-f]{40}", os.environ["GITHUB_SHA"]), "preflight control identity")
    require(all(type(os.environ.get(key)) is str and re.fullmatch("[1-9][0-9]*", os.environ[key])
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")), "preflight numeric producer identity")
    require(os.environ["GITHUB_RUN_ATTEMPT"] == "1", "same-source proof reruns are not registered")
    row = read_json(temporary, "wealth-proof-preflight.json")
    require(type(row) is dict and set(row) == {"started_monotonic", "control_sha", "run_id", "attempt", "wall_limit_seconds"}, "closed preflight observation")
    require(row["control_sha"] == os.environ.get("GITHUB_SHA") and row["run_id"] == os.environ.get("GITHUB_RUN_ID")
        and row["attempt"] == os.environ.get("GITHUB_RUN_ATTEMPT") and type(row["wall_limit_seconds"]) is int
        and row["wall_limit_seconds"] == STAGING_WALL_SECONDS, "preflight current producer binding")
    start = row["started_monotonic"]
    require(type(start) in (int, float) and math.isfinite(start) and start > 0, "preflight monotonic clock shape")
    elapsed = clock() - start
    require(0 <= elapsed <= STAGING_WALL_SECONDS, "pre-transfer/staging wall window exceeded")
    return dict(elapsed_wall_seconds=elapsed, wall_limit_seconds=STAGING_WALL_SECONDS,
        scope="Registration preflight through staged-input admission start; separate from1800-second controller and35-minute whole job.")


def child(args):
    """Internal source503 reader; invoked only by the admitted owned controller."""
    pins = registration()  # Internal entrypoints also refuse any pending pins.
    require(platform.python_version() == B.PYTHON_VERSION, "child interpreter identity")
    source = Path(args.source).resolve()
    for name, expected in KERNELS.items():
        require(hashlib.sha256(read_bytes(source, name)).hexdigest() == expected, "child scientific source differs")
    sys.path.insert(0, str(source / "src"))
    import chronicler.run_checkpoint as rc
    if args.child == "checkpoint-index":
        root = Path(args.output)
        files = inventory(root, max_bytes=MAX_OUTPUT_BYTES, max_files=MAX_OUTPUT_FILES)
        checkpoints = []
        for name, row in files.items():
            if name.endswith(".ckpt"):
                description = rc.describe(root / name)
                turn = int(Path(name).stem.removeprefix("c"))
                require(description.get("exact") is True and type(description.get("seed")) is int and description["seed"] == 42
                    and type(description.get("turn")) is int and description["turn"] == turn
                    and description.get("identity", {}).get("native", {}).get("sha256") == pins["candidate_native_sha256"],
                    "candidate checkpoint header/source native ownership")
                require(rc._compare_identity(description["identity"], rc.runtime_identity(), True) == [], "candidate checkpoint identity differs")
                checkpoints.append(dict(path=name, sha256=row["sha256"], mode=description["run_config"]["agent_mode"],
                    turn=turn))
        require(len(checkpoints) == 9 and sorted((v["mode"], v["turn"]) for v in checkpoints) == sorted(
            [(mode, turn) for mode in ("hybrid", "demographics-only", "shadow", "off") for turn in (6, 12)] + [("hybrid", 30)]),
            "all nine genuine candidate checkpoints required")
        C.write_json(args.out, dict(checkpoints=checkpoints))
    else:
        checkpoint = Path(args.checkpoint); before = read_bytes(checkpoint.parent, checkpoint.name, 64 * B.MIB)
        import chronicler_agents.chronicler_agents as native
        observed = hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
        require(observed == args.baseline_native and observed != args.candidate_native, "negative native identity")
        counts = dict(native=0, python=0)
        def section_trap(*_a, **_k):
            counts["native"] += 1; raise ProofRefused("native restore reached")
        class UnpicklerTrap:
            def __init__(self, *_a, **_k):
                counts["python"] += 1; raise ProofRefused("Python restore reached")
        rc._section = section_trap; rc._Unpickler = UnpicklerTrap
        try:
            rc.read_checkpoint(checkpoint)
        except rc.CheckpointIncompatible as exc:
            require(type(exc.mismatches) is list and len(exc.mismatches) == 1
                and exc.mismatches[0].startswith("native extension:"), "negative rejected for an unrelated identity")
        else:
            raise ProofRefused("cross-native checkpoint was accepted")
        require(read_bytes(checkpoint.parent, checkpoint.name, 64 * B.MIB) == before, "candidate checkpoint changed")
        C.write_json(args.out, negative_result(dict(status="PASS", checkpoint_sha256=hashlib.sha256(before).hexdigest(),
            candidate_native_sha256=args.candidate_native, observed_native_sha256=observed, exception="CheckpointIncompatible",
            mismatch_fields=["native extension"], native_restore_calls=counts["native"], python_restore_calls=counts["python"],
            allow_mismatch=False, source_sha=B.CANDIDATE_SOURCE), hashlib.sha256(before).hexdigest(), args.candidate_native, args.baseline_native))
    return 0


def retain_pytest_outputs(scratch, retained, check):
    """Keep every physical file; record only pytest's known sibling current links."""
    scratch, retained = Path(scratch), Path(retained)
    require(scratch.is_dir() and not scratch.is_symlink(), "physical pytest scratch root required")
    check(); retained.mkdir(); aliases, identities = [], set()
    count = total = directories = 0
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
    def visit(directory, prefix):
        nonlocal count, total, directories
        check(); directories += 1; require(directories <= MAX_OUTPUT_FILES, "pytest scratch directory bound")
        entries = []
        with os.scandir(directory) as iterator:
            for entry in iterator:
                check(); require(len(entries) < MAX_OUTPUT_FILES, "pytest scratch entry bound"); entries.append(entry.name)
        for name in sorted(entries):
            check(); relative = safe_name(prefix + name)
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(name, dir_fd=directory)
                alias_prefix = name[:-7]
                target_name = Path(target).name
                number = target_name[len(alias_prefix):] if target_name.startswith(alias_prefix) else ""
                require("/" not in relative and alias_prefix in PYTEST_TEMP_PREFIXES and number.isascii() and number.isdecimal()
                    and int(number) in PYTEST_TEMP_PREFIXES[alias_prefix] and str(int(number)) == number, "unexpected pytest alias target")
                expected = scratch / target_name
                require(name.endswith("current") and target in (expected.name, str(expected)), "unexpected pytest alias")
                target_info = os.stat(target_name, dir_fd=directory, follow_symlinks=False)
                require(stat.S_ISDIR(target_info.st_mode), "pytest current target is not physical directory")
                aliases.append(dict(path=name, target=target)); continue
            if stat.S_ISDIR(info.st_mode):
                child_fd = os.open(name, flags, dir_fd=directory)
                try:
                    opened = os.fstat(child_fd)
                    require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), "pytest directory changed")
                    (retained / relative).mkdir()
                    visit(child_fd, relative + "/")
                finally:
                    os.close(child_fd)
                continue
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and (info.st_dev, info.st_ino) not in identities,
                "pytest physical file/alias type differs")
            identities.add((info.st_dev, info.st_ino))
            with regular(scratch, relative) as (stream, opened):
                require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), "pytest file changed")
                total += opened.st_size; count += 1
                require(count <= MAX_OUTPUT_FILES and total <= MAX_OUTPUT_BYTES, "checkpoint retained bounds")
                out = retained / relative; out.parent.mkdir(parents=True, exist_ok=True)
                with out.open("xb") as sink:
                    actual = 0
                    while block := stream.read(B.MIB):
                        check(); actual += len(block); require(actual <= opened.st_size, "pytest payload grew"); sink.write(block)
                    require(actual == opened.st_size, "pytest payload EOF")
            check()
    fd = os.open(scratch, flags)
    try:
        visit(fd, "")
    finally:
        os.close(fd)
    require(count > 0, "missing genuine checkpoint outputs")
    return dict(physical_files=count, physical_bytes=total, pytest_scratch_aliases=aliases,
        scope="Every physical pytest output retained; known current aliases recorded without following them. No scientific comparison exclusion changed.")


def failure_checkpoint_retention(root, *, cleanup_complete, children_gone, check):
    """Best effort after failure/owned cleanup; never changes producer status."""
    try:
        require(cleanup_complete is True and children_gone is True, "owned cleanup remains unverified")
        root = Path(root)
        if not (root / "scratch").exists():
            return dict(status="not_created", failed_producer=True)
        if (root / "checkpoints").exists():
            return dict(status="existing_copy_preserved_unqualified", failed_producer=True)
        check()
        copied = retain_pytest_outputs(root / "scratch", root / "checkpoints", check)
        check()
        return dict(status="retained_for_failed_producer", failed_producer=True, retention=copied)
    except BaseException as exc:
        return dict(status="retention_incomplete", failed_producer=True, error=type(exc).__name__,
            scope="Original scratch and any partial physical copy are untouched; no qualification or budget extension.")


def proof(args):
    pins = registration()  # Before source/path/proc/venv/compiled access.
    start = time.monotonic(); deadline = start + WALL_SECONDS
    require(sys.platform == "linux" and platform.python_version() == B.PYTHON_VERSION, "registered Linux/Python runtime")
    require(os.environ.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH and os.environ.get("GITHUB_JOB") == "proof", "closed bootstrap producer branch/job")
    for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch("[1-9][0-9]*", os.environ.get(name, "")), "numeric bootstrap producer")
    require(os.environ["GITHUB_RUN_ATTEMPT"] == "1", "same-source proof reruns are not registered")
    require(re.fullmatch("[0-9a-f]{40}", os.environ.get("GITHUB_SHA", "")), "bootstrap control identity")
    workspace, temporary = Path(os.environ["GITHUB_WORKSPACE"]).resolve(), Path(os.environ["RUNNER_TEMP"]).resolve()
    control, source, root = SCRIPT.parents[1], Path(args.source).resolve(), Path(args.output).resolve()
    require(control == workspace / "control" and source == workspace / "candidate" and root == temporary / "wealth-candidate-proof", "closed bootstrap paths")
    staged_clock = staging_observation(temporary)
    require(not root.exists(), "fresh proof output required")
    root.mkdir(); (root / "logs").mkdir()
    before = source_bindings(control); C.write_json(root / "control-sources-before.json", before)
    workflow_contract(read_bytes(control, TEMPLATE_PATH), read_bytes(control, WORKFLOW_PATH))
    legacy = C.legacy_helpers(control); cancellation = C.Cancellation(); cancellation.__enter__()
    supervisor, failed = None, None
    report = dict(schema_version=1, kind="wealth-floor-candidate-bootstrap", status="incomplete", candidate_worlds_admitted=False,
        historical_reuse_admitted=False, outcome_proof_pins_remain_null=True, physics_ticks_registered=926,
        producer=dict(control_sha=os.environ["GITHUB_SHA"], run_id=os.environ["GITHUB_RUN_ID"],
            run_attempt=os.environ["GITHUB_RUN_ATTEMPT"], job_key="proof"))
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    stage = "deployment"
    try:
        report["deployment"] = hosted_vm_precondition()
        report["staging_observation"] = staged_clock
        with C.SubreaperLease() as lease:
            supervisor = C.make_supervisor(legacy, root, deadline, lease, cancellation)
            supervisor.admission("candidate-bootstrap", 12, 2)
            stage = "control_source"
            control_before = C.source_snapshot(legacy, control, os.environ["GITHUB_SHA"], supervisor.deadline)
            C.write_json(root / "control-git-before.json", control_before)
            metadata = read_json(temporary, "wealth-build-publication.json", supervisor.check)
            stage = "build_content_admission"
            build = admit_build(temporary / "wealth-build-input", metadata, now=datetime.now(timezone.utc), check=supervisor.check)
            stage = "candidate_source"
            initial = C.source_snapshot(legacy, source, B.CANDIDATE_SOURCE, supervisor.deadline)
            require(initial["crate_tree"] == B.CANDIDATE_CRATE, "candidate crate differs")
            for name, expected in KERNELS.items():
                require(hashlib.sha256(read_bytes(source, name)).hexdigest() == expected, "registered scientific kernel differs")
            C.write_json(root / "candidate-source-before.json", initial)
            # Both environments use precisely the same locked source, interpreter,
            # dev packages and thread caps. Only the installed wheel differs.
            env = C.build_environment(temporary, sys.executable)
            for key in list(env):
                if key.startswith(("GITHUB_", "RUNNER_", "CODEX_", "OIC_", "UV_")) or key in ("GH_TOKEN", "GITHUB_TOKEN"):
                    env.pop(key)
            env.update(PYTHONPATH=str(source / "src"), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
            env.pop("CARGO_TARGET_DIR", None); env.pop("PYO3_PYTHON", None)
            interpreters = {}
            for role in ("candidate", "baseline"):
                stage = role + "_environment_and_native_probe"
                target = temporary / ("wealth-proof-" + role + "-env")
                require(not target.exists(), "fresh independent proof environment required")
                role_env = dict(env, UV_PROJECT_ENVIRONMENT=str(target))
                supervisor.command(role + "-locked-env", ["uv", "sync", "--project", str(source), "--frozen", "--no-install-project", "--python", sys.executable], role_env, control)
                python = target / "bin/python"; interpreters[role] = python
                recheck_build(build, supervisor.check)
                supervisor.command(role + "-wheel-install", ["uv", "pip", "install", "--no-deps", "--python", str(python), str(build.root / "wheels" / role / B.WHEEL_NAME)], role_env, control)
                supervisor.command(role + "-isolated-probe", [str(python), "-I", "-B", str(control / "scripts/wealth_floor_native_build_controller.py"), "probe", "--environment-root", str(target), "--out", str(root / (role + "-probe.json"))], role_env, control)
                observed = read_json(root, role + "-probe.json", supervisor.check)
                require(observed.get("native_sha256") == pins[role + "_native_sha256"] and observed.get("native_pools_created") == 0, "fresh installed native API probe differs")
            candidate = interpreters["candidate"]
            stage = "six_checkpoint_parents"
            supervisor.command("checkpoint-six-native-parents", kernel_command(candidate, source, "checkpoint", root), env, source)
            report["checkpoint"] = checkpoint_junit(read_bytes(root, "checkpoint.xml", B.MIB, supervisor.check))
            report["checkpoint_retention"] = retain_pytest_outputs(root / "scratch", root / "checkpoints", supervisor.check)
            stage = "candidate_checkpoint_headers"
            supervisor.command("checkpoint-header-index", [str(candidate), "-B", str(SCRIPT), "--child", "checkpoint-index", "--source", str(source), "--output", str(root / "checkpoints"), "--out", str(root / "checkpoint-index.json")], env, source)
            index = read_json(root, "checkpoint-index.json", supervisor.check)
            chosen = [row for row in index["checkpoints"] if row["mode"] == "hybrid" and row["turn"] == 6]
            require(len(chosen) == 1, "unique candidate-owned negative checkpoint required")
            chosen = chosen[0]
            stage = "cross_native_refusal"
            supervisor.command("cross-native-refuses-before-restore", [str(interpreters["baseline"]), "-B", str(SCRIPT), "--child", "negative", "--source", str(source), "--checkpoint", str(root / "checkpoints" / chosen["path"]), "--candidate-native", pins["candidate_native_sha256"], "--baseline-native", pins["baseline_native_sha256"], "--out", str(root / "cross-native.json")], env, source)
            report["cross_native"] = negative_result(read_json(root, "cross-native.json", supervisor.check), chosen["sha256"], pins["candidate_native_sha256"], pins["baseline_native_sha256"])
            for worldgen in ("template", "procedural"):
                stage = "determinism_" + worldgen
                supervisor.command("genuine-repeat-" + worldgen, kernel_command(candidate, source, worldgen, root), env, source)
                report[worldgen] = determinism_result(root / worldgen / "determinism_hybrid/batch_42", worldgen, pins["candidate_native_sha256"], supervisor.check)
            final = C.source_snapshot(legacy, source, B.CANDIDATE_SOURCE, supervisor.deadline)
            stage = "source_input_and_owned_cleanup"
            require(exact(initial, final), "candidate source changed")
            C.write_json(root / "candidate-source-after.json", final)
            control_after = C.source_snapshot(legacy, control, os.environ["GITHUB_SHA"], supervisor.deadline)
            require(exact(control_before, control_after), "control Git source changed")
            C.write_json(root / "control-git-after.json", control_after)
            recheck_build(build, supervisor.check)
            report["build_registration"] = dict(pins)
            report["paired_build_classification"] = parse(build.manifest_bytes)["classification"]
            report["input_transport_scope"] = "All staged payloads/wheels independently content-hashed; ZIP wrapper digest is the pinned official metadata fact, not an in-job ZIP rehash."
            supervisor.check(final=True)
        require(supervisor.cleanup_complete and not C.direct_children(), "owned proof descendants remain")
        stage = "authority_publication"
        require(exact(before, source_bindings(control)), "loaded control source files drifted")
        C.write_json(root / "control-sources-after.json", before)
        # Scratch is retained on the runner. Publication contains every physical
        # copied checkpoint output; current aliases are described, never followed.
        report["status"] = "proof_complete_pending_job"
        report["scope"] = "Checkpoint decoded-output continuation at6/12 of14 and roster30; registered200T decoded scrubbed chronicle-bundle determinism. Retaining Arrow/raw files is not an all-file equality claim. No C76 global RNG/raw-World claim, production100+ fork proof or final outcome admission."
        used = resource.getrusage(resource.RUSAGE_CHILDREN)
        report["measured"] = dict(wall_seconds=time.monotonic()-start, wall_limit_seconds=WALL_SECONDS,
            controller_cpu_seconds=time.process_time(), waited_children_cpu_seconds=(used.ru_utime+used.ru_stime)-(usage_before.ru_utime+usage_before.ru_stime),
            scope="Observation after owned cleanup, before publication hashing; no aggregate live-tree CPU admission or closed end-to-end total.")
        publication = root / "publication"; publication.mkdir()
        C.write_json(publication / "proof.json", report)
        for name in ("checkpoint.xml", "checkpoint-index.json", "cross-native.json", "control-sources-before.json", "control-sources-after.json", "control-git-before.json", "control-git-after.json", "candidate-source-before.json", "candidate-source-after.json", "candidate-probe.json", "baseline-probe.json"):
            shutil.copyfile(root / name, publication / name)
        supervisor.check(final=True)
        raw_files = inventory(root, max_bytes=MAX_OUTPUT_BYTES, max_files=MAX_OUTPUT_FILES,
            check=lambda: supervisor.check(final=True), exclude=("scratch", "publication"))
        raw_upload_coverage(raw_files)
        C.write_json(publication / "raw-payload-index.json", raw_files)
        supervisor.check(final=True)
        authority_files = inventory(publication, max_bytes=8 * B.MIB, max_files=32, check=lambda: supervisor.check(final=True))
        C.write_json(publication / "completion.json", authority_completion(authority_files))
        supervisor.check(final=True)
        require(exact(before, source_bindings(control)), "control source drift after publication")
        print(json.dumps(dict(kind="post_publication_observation", wall_seconds=time.monotonic()-start,
            source_bindings_unchanged=True, scope="After final heavy checks; stdout emission and artifact upload remain outside this observation.")))
    except BaseException as exc:
        failed = exc; report["status"] = "incomplete"; report["error"] = type(exc).__name__; report["failure_stage"] = stage
    finally:
        if time.monotonic() > deadline or C.direct_children() or cancellation.cancelled:
            failed = failed or ProofRefused("late cleanup/deadline failure")
        try:
            cancellation.__exit__(type(failed) if failed else None, failed, None)
        except BaseException as exc:
            failed = failed or exc
        if failed:
            retained_failure = None
            if supervisor is not None and stage == "six_checkpoint_parents":
                retained_failure = failure_checkpoint_retention(root, cleanup_complete=supervisor.cleanup_complete,
                    children_gone=not C.direct_children(), check=lambda: supervisor.check(final=True))
            (root / "publication").mkdir(exist_ok=True)
            C.write_json(root / "publication/completion.json", dict(publication_complete=False, status="incomplete",
                error=type(failed).__name__, failure_stage=stage, failure_checkpoint_retention=retained_failure,
                candidate_worlds_admitted=False))
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--registration", action="store_true")
    parser.add_argument("--validate-publication", action="store_true")
    parser.add_argument("--child", choices=("checkpoint-index", "negative"))
    for key in ("source", "output", "out", "checkpoint", "candidate-native", "baseline-native"):
        parser.add_argument("--" + key)
    args = parser.parse_args(argv)
    if args.child:
        return child(args)
    if args.registration:
        started = time.monotonic()
        pins = registration()
        require(os.environ.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH, "registered proof activation branch")
        require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "same-source proof reruns are not registered")
        require(sys.platform == "linux" and platform.python_version() == B.PYTHON_VERSION, "registered preflight runtime")
        hosted_vm_precondition()
        from wealth_floor_build_resources import memory_admission
        require(shutil.disk_usage(os.environ["RUNNER_TEMP"]).free >= 12 * 1024**3
            and memory_admission()["available_bytes"] >= 2 * 1024**3, "pre-transfer12GiB/2GiB admission")
        C.write_json(Path(os.environ["RUNNER_TEMP"]) / "wealth-proof-preflight.json", dict(started_monotonic=started,
            control_sha=os.environ["GITHUB_SHA"], run_id=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
            wall_limit_seconds=STAGING_WALL_SECONDS))
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="ascii") as stream:
            for key in ("run_id", "artifact_id"):
                stream.write(f"{key}={pins[key]}\n")
        return 0
    if args.validate_publication:
        pins = registration()
        require(os.environ.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH, "registered publication validation branch")
        temporary = Path(os.environ["RUNNER_TEMP"])
        staging_observation(temporary)
        validate_publication(read_json(temporary, "wealth-build-publication.json"), pins, now=datetime.now(timezone.utc))
        return 0
    if not args.execute:
        print(json.dumps(dict(status="inactive", build_registration="source-pinned; execution unreviewed", candidate_source=B.CANDIDATE_SOURCE,
            ticks_registered=926, candidate_worlds_admitted=False, final_outcome_proof_pins="unchanged/null")))
        return 0
    return proof(args)


if __name__ == "__main__":
    raise SystemExit(main())
