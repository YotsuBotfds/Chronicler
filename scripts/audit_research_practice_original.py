#!/usr/bin/env python3
"""Dormant original-byte audit. No artifact/URL/source/budget override CLI."""
from __future__ import annotations

import time
ENTRY_MONOTONIC = time.monotonic()  # BEFORE adapter imports, auth, admission or allocation.

import argparse
import importlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

import research_practice_original_audit as A

ROOT = Path(__file__).resolve().parents[1]
WORK = A.TEMP / "practice-original-audit"
REGISTRATION = ROOT / "scripts/research_practice_original_registration.json"
OWNED_WORK = None
EXPECTED_PURE_CASES = 109
CONTRACT_COPIES = {
    "contracts-guard.json": ("practice-original-contracts/guard.json", 64 * 1024),
    "contracts-junit.xml": ("practice-original-contracts/junit.xml", 512 * 1024)}
TERMINAL_BYTES, TERMINAL_FILES = 128 * 1024, 2
CAPS = {name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS",
    "RAYON_NUM_THREADS", "PYTHON_CPU_COUNT")}


def write_raw(path, raw, *, publication=False, terminal=False):
    A.require(len(raw) <= A.PUBLICATION_BYTES, "metadata_write_bound")
    if publication or path.parent == WORK / "publication":
        A.no_links(path.parent)
        paths = list(path.parent.iterdir())
        for entry in paths:
            A.regular(entry)
        names = {entry.name for entry in paths}
        A.require(not path.exists() and not path.is_symlink(), "publication_overwrite")
        A.require(not terminal or path.name in {"completion.json", "negative.json", "terminal-negative.json"},
                  "terminal_name")
        A.require(not terminal or len(raw) <= TERMINAL_BYTES // TERMINAL_FILES, "terminal_record_bound")
        missing = {name: maximum for name, (_, maximum) in CONTRACT_COPIES.items()
                   if name not in names and name != path.name}
        reserve_bytes, reserve_files = (0, 0) if terminal else (TERMINAL_BYTES, TERMINAL_FILES)
        A.require(sum(p.stat().st_size for p in paths) + len(raw) + sum(missing.values()) + reserve_bytes
                  <= A.PUBLICATION_BYTES
                  and len(paths) + 1 + len(missing) + reserve_files <= A.PUBLICATION_FILES,
                  "cumulative_publication_bound")
    temporary = path.with_name("pending-" + path.name)
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write(path, value, *, publication=False, terminal=False):
    raw = json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    write_raw(path, raw, publication=publication, terminal=terminal)


def error_facts(error):
    import re
    code = str(error) if isinstance(error, A.Refused) else ""
    return dict(error_type=type(error).__name__, error_code=code if re.fullmatch("[a-z_]{1,80}", code) else None,
                transport=getattr(error, "facts", None), resource_observation=getattr(error, "observation", None))


def selected_helpers(root, registration):
    # Authenticate ALL transitive source before executing any helper.
    A.no_links(root)
    for name, expected in registration["source_pins"].items():
        A.require(A.pin(A.bounded(root / name)) == {k: expected[k] for k in ("bytes", "sha256")},
                  "historical_helper_source_changed")
    sys.path.insert(0, str(root / "scripts"))
    names = ("research_practice_contract", "research_practice_resources", "run_research_practice_continuation",
             "fetch_research_practice_wheel", "research_practice_trace_reader", "read_research_practice_continuation")
    result = [importlib.import_module(name) for name in names]
    for module in result:
        A.require(Path(module.__file__).resolve().parent == root / "scripts", "helper_import_origin")
    return result


def registration(env):
    A.require(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == A.REPO
        and env.get("GITHUB_EVENT_NAME") == "push" and env.get("GITHUB_REF") == "refs/heads/" + A.BRANCH
        and env.get("GITHUB_WORKFLOW_REF") == A.REPO + "/" + A.WORKFLOW + "@refs/heads/" + A.BRANCH
        and env.get("GITHUB_JOB") == "original-audit" and env.get("GITHUB_RUN_ATTEMPT") == "1",
        "closed_first_attempt_registration")
    import re
    A.require(re.fullmatch("[0-9a-f]{40}", env.get("GITHUB_SHA", ""))
              and re.fullmatch("[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")), "producer_identity")
    A.require(ROOT == A.WORKSPACE / "audit-control" and env.get("GITHUB_WORKSPACE") == str(A.WORKSPACE)
              and env.get("RUNNER_TEMP") == str(A.TEMP), "historical_context_layout")
    A.require(platform.python_version() == "3.13.17" and platform.python_implementation() == "CPython"
              and sys.platform == "linux" and platform.machine() == "x86_64", "audit_python_platform")
    import importlib.metadata
    A.require({name: importlib.metadata.version(name) for name in ("pytest", "PyYAML")} ==
              {"pytest": "9.1.1", "PyYAML": "6.0.3"}, "pure_dependency_versions")
    A.require(len(os.sched_getaffinity(0)) == 1 and all(env.get(k) == v for k, v in CAPS.items())
              and env.get("PYTHONHASHSEED") == "0" and env.get("PYTHONDONTWRITEBYTECODE") == "1", "audit_cpu_caps")
    A.require(not any(k.startswith("GIT_") and k not in {"GIT_PAGER", "GIT_NO_LAZY_FETCH"} for k in env), "ambient_git_override")
    return {k: env[k] for k in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB")}


def own_source(C, expected):
    snapshot = C.source_snapshot(ROOT, expected)
    names = ("scripts/audit_research_practice_original.py", "scripts/research_practice_original_audit.py",
        "scripts/research_practice_original_registration.json", "tests/test_research_practice_original_audit.py",
        "docs/experiments/research-practice-original-audit-workflow.yml",
        "docs/experiments/research-practice-original-audit-registration-2026-10-29.md")
    for name in (*names, A.WORKFLOW):
        A.require(A.bounded(ROOT / name) == C.git(ROOT, "show", expected + ":" + name), "actual_audit_source_not_git_blob")
    return snapshot


def validate_context(value, digest):
    A.require(A.pin(A.bounded(WORK / "context.json"))["sha256"] == digest, "context_hash")
    A.require(type(value) is dict and set(value) == {"started", "deadline", "source", "parent", "lease"}
        and type(value["started"]) is float and math.isfinite(value["started"])
        and type(value["deadline"]) is float and value["deadline"] == value["started"] + A.SECONDS
        and value["source"] == os.environ.get("GITHUB_SHA")
        and type(value["parent"]) is int and value["parent"] == os.getppid()
        and set(value["lease"]) == set(A.TOPS), "carried_clock_or_owner")
    return value


def observer_annotation_source(D):
    # The complete D file is source-pinned, including both publish assignments
    # and C.write's source-owned encoding; no AST/function replacement occurs.
    return dict(reader=A.pin(A.bounded(Path(D.__file__))),
        publication="D.publish_readout: publication_status and result.budgets.update(budget_observation())",
        encoding="unchanged C.encoded -> C.loads matches original C.write insertion-order JSON")


def readonly_inputs(base, lease):
    for name in lease:
        root = A.owned_root(base, name, lease)
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file():
                    A.regular(path)
                    path.chmod(0o444)
            for path in root.rglob("*"):
                if path.is_dir():
                    path.chmod(0o555)
            root.chmod(0o555)


def worker(context_sha):
    registered = registration(os.environ)
    context = validate_context(A.loads(A.bounded(WORK / "context.json")), context_sha)
    stage, report, imports, before = "worker-entry", {"qualified": False}, None, []
    try:
        with A.import_guard() as (imports, before):
            reg = A.loads(A.bounded(REGISTRATION))
            C, H, R, F, T, D = selected_helpers(A.WORKSPACE / "control", reg)
            def check(next_bytes=0):
                A.require(time.monotonic() < context["deadline"] - A.RESERVE, "heavy_work_deadline")
                A.unexpired_inputs()
                return A.resources(A.TEMP, H.memory_admission, next_bytes=next_bytes)
            # A one-shot timer also interrupts long original-reader work between guards.
            previous = signal.getsignal(signal.SIGALRM)
            A.require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "unleased_worker_timer")
            def expired(signum, frame):
                raise TimeoutError("audit_heavy_deadline")
            signal.signal(signal.SIGALRM, expired)
            signal.setitimer(signal.ITIMER_REAL, max(.001, context["deadline"] - A.RESERVE - time.monotonic()))
            try:
                stage = "historical-sources"
                source_before = {"control": C.source_snapshot(A.WORKSPACE / "control", A.ORIGINAL),
                                 "producer": C.source_snapshot(A.WORKSPACE / "producer", A.PRODUCER),
                                 "audit": own_source(C, registered["GITHUB_SHA"])}
                write(WORK / "publication/source-before.json", source_before)
                received = {}
                for role in ("raw", "wheel"):
                    stage = role + "-metadata-before"
                    transport = A.Transport(role, os.environ.get("GH_TOKEN"), check,
                        min(context["deadline"] - A.RESERVE, time.monotonic() + 120))
                    before_meta = transport.metadata()
                    write(WORK / ("publication/" + role + "-metadata-before.json"), before_meta)
                    stage = role + "-whole-transfer"
                    check(A.INPUTS[role]["bytes"])
                    received[role] = transport.download(WORK / (role + ".zip"))
                    stage = role + "-metadata-after"
                    after_meta = transport.metadata()
                    write(WORK / ("publication/" + role + "-metadata-after.json"), after_meta)
                    A.require(A.metadata_contract(role, before_meta) == A.metadata_contract(role, after_meta), "publication_drift")
                    write(WORK / ("publication/" + role + "-transport.json"), transport.notes)
                stage = "raw-central-and-map"
                with zipfile.ZipFile(WORK / "raw.zip") as archive:
                    rows = A.central(archive, count=2455, expanded=502390864)
                    expected = A.expected_map(archive, rows, reg, check)
                    stage = "all-original-members-and-owned-copy"
                    check(sum(v["bytes"] for v in expected.values()))
                    for name in sorted(expected):
                        A.copy_member(archive, rows[name], expected[name], A.TEMP, context["lease"], check)
                stage = "opaque-wheel-verification"
                raw = A.bounded(WORK / "wheel.zip", A.INPUTS["wheel"]["bytes"])
                manifest, wheel = F.verify_archive(raw, F.selected())
                wheel_root = A.owned_root(A.TEMP, "practice-study-wheel", context["lease"])
                A.require(manifest == A.bounded(wheel_root / "build-manifest.json"), "original_manifest_mismatch")
                for name, value in (("official-artifact.zip", raw), (Path(F.selected()["artifact"]["wheel_path"]).name, wheel)):
                    check(len(value))
                    with (wheel_root / name).open("xb") as stream:
                        stream.write(value)
                    (wheel_root / name).chmod(0o444)
                del raw, wheel
                F.verify_receipt(wheel_root / "verification.json", A.WORKSPACE / "producer")
                readonly_inputs(A.TEMP, context["lease"])
                stage = "historical-publication-seals"
                output, evidence = A.TEMP / "practice-study-readout", A.TEMP / "practice-study-evidence"
                completion = D.validate_completion(output)
                original, receipt = C.read(output / "readout.json"), C.read(output / "receipt.json")
                execution = C.read(evidence / "execution.json")
                closed = D.execution_accounting(evidence, execution)
                annotations = A.historical_annotations(C, original, closed, receipt, completion)
                stage = "unchanged-all24-semantic-replay"
                rebuilt = D.build_readout(evidence, A.WORKSPACE / "producer", guard=check, policy_name="cloud-cbf-3ee")
                replay = A.semantic_replay(C, D, rebuilt, original, annotations, A.bounded(output / "readout.md"))
                A.require(rebuilt["mechanics_verified"] is True and rebuilt["practice_observation_complete"] is True
                    and rebuilt["registered_seed_ids"] == list(range(2000, 2008))
                    and rebuilt["paired_seed_rows"] == 8 and rebuilt["errors"] == [], "all_eight_replay_not_complete")
                stage = "final-all-input-and-source-rehash"
                for name, value in expected.items():
                    A.require(A.file_pin(A.TEMP / name, check) == value, "derived_input_changed")
                for role in ("raw", "wheel"):
                    A.require(A.file_pin(WORK / (role + ".zip"), check) == received[role], "original_zip_changed")
                F.verify_receipt(wheel_root / "verification.json", A.WORKSPACE / "producer")
                source_after = {"control": C.source_snapshot(A.WORKSPACE / "control", A.ORIGINAL),
                                "producer": C.source_snapshot(A.WORKSPACE / "producer", A.PRODUCER),
                                "audit": own_source(C, registered["GITHUB_SHA"])}
                A.require(C.same(source_before, source_after), "source_changed")
                A.require(not imports.attempts and not any(A.forbidden(n) for n in sys.modules), "import_scope_changed")
                report = dict(qualified=True, stage="semantic-replay-complete", original_members=2455,
                    original_expanded_bytes=502390864, original_execution_payloads=2442,
                    replay=replay, paired_seed_ids=rebuilt["registered_seed_ids"], executions=24,
                    source_hashes={k: v["files_sha256"] for k, v in source_after.items()},
                    original_publication_completion=A.file_pin(output / "completion.json", check),
                    publication_source=observer_annotation_source(D), input_pins=received,
                    final_resources=check(),
                    import_guard=dict(before_modules=before, after_modules=sorted(sys.modules), attempts=imports.attempts),
                    checkpoint_processing="Bounded zlib section inflation; opaque pickle/native bytes hashed, never unpickled/loaded.",
                    limits="Raw Python object/runtime binding remains original worker attestation; no new historical CPU measurement.")
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
                check()
    except BaseException as error:
        report = dict(qualified=False, stage=stage, **error_facts(error),
            import_guard=dict(before_modules=before, attempts=[] if imports is None else imports.attempts,
                              loaded_forbidden=sorted(n for n in sys.modules if A.forbidden(n))))
    write(WORK / "worker-result.json", report)
    return 0 if report["qualified"] else 1


def invalidate(output):
    for name in ("completion.json", "result.json"):
        path = output / name
        if path.exists():
            destination, index = output / ("incomplete-" + name), 1
            while destination.exists():
                destination = output / (f"incomplete-{index}-" + name)
                index += 1
            os.replace(path, destination)


def publish(output, report, guard, observation):
    try:
        guard()
        write(output / "result.json", report, publication=True)
        guard()
        paths = list(output.iterdir())
        A.require(all(p.is_file() and not p.is_symlink() for p in paths), "unexpected_publication_entry")
        files = {p.name: A.file_pin(p, guard) for p in paths}
        combined = list(files.values())
        A.require(len(combined) < A.PUBLICATION_FILES and sum(r["bytes"] for r in combined) < A.PUBLICATION_BYTES - 4096,
                  "publication_total_bound")
        seal = dict(schema_version=1, kind="fresh-practice-original-byte-audit-completion",
                    qualified=report["qualified"], files=files, audit_observation=observation())
        seal_bytes = len(json.dumps(seal, indent=2, sort_keys=True, allow_nan=False).encode()) + 1
        A.require(len(combined) + 1 <= A.PUBLICATION_FILES
                  and sum(r["bytes"] for r in combined) + seal_bytes <= A.PUBLICATION_BYTES,
                  "publication_seal_total_bound")
        A.unexpired_inputs()
        write(output / "completion.json", seal, publication=True, terminal=True)
        guard()  # Covers result serialization, hashes, final seal write AND rename.
        A.unexpired_inputs()  # An expiry during the seal commit invalidates it.
    except BaseException:
        invalidate(output)
        raise


def preflight_contracts(base, *, step_outcome=None):
    paths = {"practice-original-contracts/guard.json": 64 * 1024,
             "practice-original-contracts/junit.xml": 512 * 1024}
    raw = {name: A.bounded(base / name, maximum) for name, maximum in paths.items()}
    guard = A.loads(raw["practice-original-contracts/guard.json"])
    A.require(type(step_outcome) is str and step_outcome == "success", "pure_step_outcome")
    A.require(guard["state"] == "PASS" and guard["test_reports"] ==
        {"passed": EXPECTED_PURE_CASES, "failed": 0, "skipped": 0}
        and all(type(v) is int for v in guard["test_reports"].values())
        and type(guard.get("pytest_exitstatus")) is int and guard["pytest_exitstatus"] == 0
        and guard.get("guard_active_at_finish") is True
        and guard.get("runtime_factories_replaced_before_collection") is True
        and not guard["native_modules_loaded"] and not guard["native_import_attempts_blocked"]
        and not guard["blocked_io_attempts"]
        and set(guard["python_oracle_factory_calls"]) == {"ecology", "politics"}
        and all(type(v) is int and v == 0 for v in guard["python_oracle_factory_calls"].values()), "pure_preflight_guard")
    tree = ET.fromstring(raw["practice-original-contracts/junit.xml"])
    A.require(len(tree.findall(".//testcase")) == EXPECTED_PURE_CASES
              and not any(tree.findall(".//" + name) for name in ("failure", "error", "skipped")), "pure_preflight_junit")
    return {name: A.pin(value) for name, value in raw.items()}


def copy_contracts(base, output):
    # Copy bounded original preflight bytes BEFORE interpreting PASS/FAIL, so a
    # failed test can be retained without admitting a worker or opaque input.
    result = {}
    for name, (source, maximum) in CONTRACT_COPIES.items():
        raw = A.bounded(base / source, maximum)
        write_raw(output / name, raw, publication=True)
        result[source] = A.pin(raw)
    return result


def audit(parent_imports=None):
    global OWNED_WORK
    registered = registration(os.environ)
    deadline = ENTRY_MONOTONIC + A.SECONDS
    pure_outcome = os.environ.get("PRACTICE_AUDIT_PURE_OUTCOME")
    A.no_links(WORK)
    WORK.mkdir(mode=0o700)
    created = WORK.lstat()
    OWNED_WORK = (created.st_dev, created.st_ino)
    (WORK / "publication").mkdir(mode=0o700)
    # Tiny owned negative metadata precedes authority/admission; it is never a
    # positive grant. Credentials, workers and transfers remain behind both gates.
    write(WORK / "publication/entry-pending.json", dict(qualified=False, stage="entry_pending",
        producer=registered, pure_step_outcome=pure_outcome, started_monotonic=ENTRY_MONOTONIC))
    copied_contracts = copy_contracts(A.TEMP, WORK / "publication")
    contracts = preflight_contracts(A.TEMP, step_outcome=pure_outcome)
    A.require(contracts == copied_contracts, "preflight_copy_changed")
    reg = A.loads(A.bounded(REGISTRATION))
    # Loading the source-pinned owner does not import simulation code or probe RAM.
    C, H, R, F, T, D = selected_helpers(ROOT, reg)
    def guard(final=False):
        A.require(time.monotonic() < deadline - (0 if final else A.RESERVE), "audit_deadline")
        A.unexpired_inputs()
        return A.resources(A.TEMP, H.memory_admission)
    # Required12/2 admission remains before every worker or opaque transfer.
    A.require(time.monotonic() < deadline - A.RESERVE, "bootstrap_deadline")
    A.unexpired_inputs()
    admission = A.resources(A.TEMP, H.memory_admission, initial=True)
    write(WORK / "publication/admission.json", admission)
    report, lease, child, known, cleanup_ok = {"qualified": False, "stage": "bootstrap"}, {}, None, {}, False
    try:
        with R.interruption_guard(), R.exclusive_subreaper():
            try:
                lease = A.lease_targets(A.TEMP)
                context = dict(started=ENTRY_MONOTONIC, deadline=deadline, source=registered["GITHUB_SHA"],
                               parent=os.getpid(), lease=lease)
                write(WORK / "context.json", context)
                env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
                env["GIT_NO_LAZY_FETCH"] = "1"
                with (WORK / "worker.log").open("xb") as log:
                    child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "worker",
                        A.file_pin(WORK / "context.json")["sha256"]], stdout=log, stderr=subprocess.STDOUT,
                        env=env, cwd=ROOT, start_new_session=True)
                    try:
                        def running():
                            guard()
                            A.require((WORK / "worker.log").stat().st_size <= 64 * 1024, "worker_log_bound")
                        # Reuse original ownership/wait4/pidfd mechanics unchanged.
                        # CPU assertions disabled: this audit claims WALL + truthful waited CPU only.
                        R.supervise(child, known, lambda: 0.0, running, ENTRY_MONOTONIC, ENTRY_MONOTONIC,
                            worker_cpu=math.inf, aggregate_limit=math.inf, worker_wall=A.SECONDS - A.RESERVE,
                            aggregate_wall=A.SECONDS - A.RESERVE)
                    finally:
                        R.cleanup(child, known)
                report = A.loads(A.bounded(WORK / "worker-result.json", A.PUBLICATION_BYTES))
                A.require(report.get("qualified") is True and child.returncode == 0, "worker_negative_or_missing")
            finally:
                if child is not None and R.owned_tree(child.pid, known):
                    R.cleanup(child, known)
                A.cleanup_targets(A.TEMP, lease)
                cleanup_ok = not R.direct_children()
    except BaseException as error:
        report = dict(qualified=False, stage=report.get("stage", "outer"), **error_facts(error),
                      worker_report=report)
    finally:
        for role in ("raw", "wheel"):
            path = WORK / (role + ".zip")
            if path.exists() and cleanup_ok:
                A.regular(path)
                path.unlink()
    report.update(producer=registered, cleanup_complete=cleanup_ok, original_control=A.ORIGINAL,
                  original_run=A.INPUTS["raw"]["run"], new_audit_clock=True,
                  new_worlds=0, native_imports=0, original_budgets_modified=False,
                  preflight_origin_files=contracts,
                  preflight_step_outcome=pure_outcome,
                  audit_runtime=dict(python=sys.version, executable=sys.executable,
                      affinity=sorted(os.sched_getaffinity(0)), caps={k: os.environ.get(k) for k in CAPS},
                      pure_dependencies={"pytest": "9.1.1", "PyYAML": "6.0.3"}))
    if parent_imports is not None:
        imports, before = parent_imports
        A.require(not imports.attempts and not any(A.forbidden(n) for n in sys.modules), "outer_import_scope")
        report["outer_import_guard"] = dict(before_modules=before, after_modules=sorted(sys.modules), attempts=imports.attempts)
    report["qualified"] = report["qualified"] is True and cleanup_ok
    # Only quiescent, bounded tiny worker records join the new audit publication.
    for name, limit in (("worker-result.json", A.PUBLICATION_BYTES // 2), ("worker.log", 64 * 1024)):
        path = WORK / name
        if path.exists():
            raw = A.bounded(path, limit)
            write_raw(WORK / "publication" / name, raw, publication=True)
    def observation():
        own, waited = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        return dict(wall_measured_to_seal_seconds=time.monotonic() - ENTRY_MONOTONIC,
            wall_limit_seconds=A.SECONDS, finalization_reserve_inside_wall_seconds=A.RESERVE,
            self_cpu_seconds=own.ru_utime + own.ru_stime,
            waited_child_cpu_seconds=waited.ru_utime + waited.ru_stime,
            cpu_scope="measured process-lifetime self plus waited children through seal; includes startup CPU; no hard aggregate descendant CPU cap",
            workflow_prerequisites="checkout/runtime setup excluded from script clock; separate job wall")
    try:
        if report["qualified"]:
            for role, root, expected in (("audit", ROOT, registered["GITHUB_SHA"]),
                    ("control", A.WORKSPACE / "control", A.ORIGINAL),
                    ("producer", A.WORKSPACE / "producer", A.PRODUCER)):
                guard(final=True)
                A.require(C.source_snapshot(root, expected)["files_sha256"] == report["source_hashes"][role],
                          "source_changed_after_quiescence")
        A.require(preflight_contracts(A.TEMP, step_outcome=pure_outcome) == contracts, "pure_preflight_changed")
        A.require(all(A.file_pin(WORK / "publication" / name) == contracts[source]
                      for name, (source, _) in CONTRACT_COPIES.items()), "preflight_copy_changed")
        publish(WORK / "publication", report, lambda: guard(final=True), observation)
    except BaseException as error:
        invalidate(WORK / "publication")
        write(WORK / "publication/negative.json", dict(qualified=False, **error_facts(error), report=report), terminal=True)
        return 1
    return 0 if report["qualified"] else 1


def audit_with_timer():
    """The entry clock includes bootstrap and final handler restoration."""
    previous = signal.getsignal(signal.SIGALRM)
    A.require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "unleased_outer_timer")
    def expired(signum, frame):
        raise TimeoutError("audit_terminal_deadline")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(.001, ENTRY_MONOTONIC + A.SECONDS - time.monotonic()))
    try:
        try:
            with A.import_guard() as parent_imports:
                result = audit(parent_imports)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        A.require(time.monotonic() < ENTRY_MONOTONIC + A.SECONDS, "post_teardown_deadline")
        if result == 0:
            A.unexpired_inputs()
        return result
    except BaseException as error:
        # A failed registration/preexisting path never grants ownership.
        if OWNED_WORK is not None and not WORK.is_symlink() and WORK.is_dir():
            row = WORK.lstat()
            A.require((row.st_dev, row.st_ino) == OWNED_WORK, "publication_owner_changed")
            output = WORK / "publication"
            if output.is_dir() and not output.is_symlink():
                invalidate(output)
                write(output / "terminal-negative.json", dict(qualified=False, **error_facts(error),
                      scope="Terminal failure; no positive original-byte qualification."), terminal=True)
        print(json.dumps(dict(qualified=False, **error_facts(error))), flush=True)
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("describe", "audit", "worker"), default="describe", nargs="?")
    parser.add_argument("context_sha", nargs="?")
    args = parser.parse_args(argv)
    if args.mode == "audit":
        return audit_with_timer()
    if args.mode == "worker":
        return worker(args.context_sha)
    print(json.dumps(dict(status="dormant", transfer=False, original_raw=A.INPUTS["raw"], actual_facts=None)))
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
