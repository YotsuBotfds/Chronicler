#!/usr/bin/env python3
"""Dormant fixed late-checkpoint / production-runtime primer for source503.

No default command installs native code or executes a world. The successful926
bootstrap remains a separate prerequisite; this is prospective extra coverage.
The qualified P/C/B/R/D dependencies are reused unchanged. Final A pins stay null.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import sys
import time
from types import MappingProxyType

SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parent))
import wealth_floor_candidate_proof as P

B, C = P.B, P.C
require, exact = P.require, P.exact
ACTIVE_BRANCH = "lead/cloud-wealth-floor-production-primer-20261029"
WORKFLOW_PATH = ".github/workflows/wealth-floor-production-primer.yml"
TEMPLATE_PATH = "docs/experiments/wealth-floor-production-primer.yml.inactive"
WORKFLOW_SHA256 = "4535b7f8c564f0b6b51d56bdbf1b10bf84e54478cb35f4b381e9ee2dca7c2f50"
P_SHA256 = "13239d13a68fee3e25732d9e1323edaaa20e117ce679b15a5c847585b383249f"
ROOT_BOOTSTRAP_RECEIPT_SHA256 = "208b35e77f662d182984cc772ab6281fbe906d950e9a6a6858246716c2d37196"
BOOTSTRAP = MappingProxyType(dict(control_sha="40db80d3ab8beb34522e9025125c68d2954511a1",
    run_id=40824399844, job_id=123283990102, attempt=1,
    artifact_id=12875209033, artifact_bytes=489021,
    artifact_sha256="5a7d01a33b0f1f422d649d4740a041b09d6248e73680b56e01640c8060d0e3bc",
    artifact_expires_at="2026-11-28T05:38:30Z",
    completion_sha256="5bc03830e9220afe7b51db995bb6a783da594af31c6c856c00e9662b1320ec30",
    proof_sha256="2baca79073b861957aa50d4108df67aa5c1fff6e084ecc5c9dbb1a8d24df7fd1",
    negative_sha256="568a823d53108a54c710626e99f3f828af4d52f2799513d0b87d85ee658f399c"))
THREAD_KEYS = tuple(key for key in C.CAPS if key.endswith("THREADS") or key == "CARGO_BUILD_JOBS")
WALL_SECONDS = P.WALL_SECONDS
REPEAT_EXECUTION_SCOPE = ("Observed pre-exec scientific parent and inherited affinity/env for serial scientific subprocesses. "
    "Exact source503 determinism profile runs repeats synchronously; parallel2 is requested/recorded, not concurrent-worker coverage.")
RAW_FILES = frozenset(("progress.jsonl", "control-sources-before.json", "control-sources-after.json",
    "control-git-before.json", "control-git-after.json", "candidate-source-before.json", "candidate-source-after.json",
    "candidate-probe.json", "checkpoint-report.json", "template-runtime.json", "procedural-runtime.json"))
LIGHT_FILES = tuple(sorted(RAW_FILES - {"progress.jsonl"}))


def plans():
    """Fixed prospective schedule; no seed/window selection from observed data."""
    rows = []
    for worldgen, turns, regions, civs, cps in (
        ("template", 422, 8, 4, [101, 201, 301, 401]),
        ("procedural", 282, 32, 10, list(range(101, 262, 20))),
    ):
        rows.append(dict(worldgen=worldgen, seed=42, turns=turns, regions=regions, civs=civs,
            checkpoint_turns=cps, executions=1 + len(cps), physics_ticks=turns + sum(turns-k for k in cps)))
    return tuple(rows)


def registration():
    build = dict(P.registration())
    require(B.hash_shape(ROOT_BOOTSTRAP_RECEIPT_SHA256) and B.hash_shape(P.ROOT_BUILD_RECEIPT_SHA256), "root prerequisite pins")
    require(sum(p["executions"] for p in plans()) == 15 and sum(p["physics_ticks"] for p in plans()) == 2297, "fixed checkpoint budget")
    return dict(build=build, bootstrap=dict(BOOTSTRAP), build_root_review_sha256=P.ROOT_BUILD_RECEIPT_SHA256,
        bootstrap_root_review_sha256=ROOT_BOOTSTRAP_RECEIPT_SHA256)


def validate_runtime(value):
    require(type(value) is dict and set(value) == {"python", "logical_cpu_count", "affinity", "caps"}, "runtime observation shape")
    affinity = value["affinity"]
    require(value["python"] == B.PYTHON_VERSION and type(value["logical_cpu_count"]) is int
        and value["logical_cpu_count"] == 2, "registered Python/logical CPU2 required")
    require(type(affinity) is list and len(affinity) == 2 and all(type(v) is int and v >= 0 for v in affinity)
        and affinity == sorted(set(affinity)), "observed actual two-CPU affinity required")
    require(exact(value["caps"], {key: "1" for key in THREAD_KEYS}), "registered thread caps1 required")
    return value


def observe_runtime():
    return validate_runtime(dict(python=platform.python_version(), logical_cpu_count=os.cpu_count(),
        affinity=sorted(os.sched_getaffinity(0)), caps={key: os.environ.get(key) for key in THREAD_KEYS}))


def repeat_command(python, source, worldgen, output):
    return P.kernel_command(python, Path(source), worldgen, Path(output)) + ["--parallel", "2"]


def source_bindings(control):
    rows = P.source_bindings(control)
    require(rows["scripts/wealth_floor_candidate_proof.py"]["sha256"] == P_SHA256, "frozen bootstrap dependency differs")
    raw = P.read_bytes(control, "scripts/wealth_floor_production_primer.py")
    rows["scripts/wealth_floor_production_primer.py"] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return rows


def workflow_contract(template, active=None):
    require(hashlib.sha256(template).hexdigest() == WORKFLOW_SHA256, "reviewed primer workflow differs")
    if active is not None:
        require(active == template, "active primer workflow differs from reviewed dormant copy")
    return True


def validate_bootstrap_publication(metadata, *, now):
    """Fresh official origin/expiry, separate from staged authority content."""
    require(type(metadata) is dict and set(metadata) == {"run", "jobs", "artifact"}, "bootstrap metadata shape")
    run, jobs, artifact = metadata["run"], metadata["jobs"], metadata["artifact"]
    require(type(run) is dict and run.get("id") == BOOTSTRAP["run_id"] and type(run.get("id")) is int
        and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
        and run.get("head_sha") == BOOTSTRAP["control_sha"] and run.get("head_branch") == P.ACTIVE_BRANCH
        and run.get("path") == P.WORKFLOW_PATH and run.get("repository", {}).get("full_name") == P.REPOSITORY
        and run.get("status") == "completed" and run.get("conclusion") == "success", "bootstrap completed run origin")
    require(type(jobs) is dict and type(jobs.get("jobs")) is list and len(jobs["jobs"]) <= 32, "bounded bootstrap jobs")
    matched = [row for row in jobs["jobs"] if type(row) is dict and type(row.get("id")) is int and row["id"] == BOOTSTRAP["job_id"]]
    require(len(matched) == 1 and matched[0].get("run_id") == BOOTSTRAP["run_id"]
        and type(matched[0].get("run_id")) is int and matched[0].get("head_sha") == BOOTSTRAP["control_sha"]
        and matched[0].get("status") == "completed" and matched[0].get("conclusion") == "success", "bootstrap completed job")
    require(type(artifact) is dict and type(artifact.get("id")) is int and artifact["id"] == BOOTSTRAP["artifact_id"]
        and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] == BOOTSTRAP["artifact_bytes"]
        and artifact.get("digest") == "sha256:" + BOOTSTRAP["artifact_sha256"] and artifact.get("expired") is False
        and artifact.get("expires_at") == BOOTSTRAP["artifact_expires_at"]
        and artifact.get("name") == "wealth-candidate-proof-light-40824399844-1"
        and type(artifact.get("workflow_run", {}).get("id")) is int and artifact["workflow_run"]["id"] == BOOTSTRAP["run_id"]
        and artifact["workflow_run"].get("head_sha") == BOOTSTRAP["control_sha"], "bootstrap light publication")
    require(now < P.expiry(BOOTSTRAP["artifact_expires_at"]), "bootstrap expired")


def admit_bootstrap(root, metadata, *, now, check=lambda: None):
    registration()
    validate_bootstrap_publication(metadata, now=now)
    files = P.inventory(root, max_bytes=8*B.MIB, max_files=32, check=check)
    for name, slot in (("completion.json", "completion_sha256"), ("proof.json", "proof_sha256"), ("cross-native.json", "negative_sha256")):
        require(files.get(name, {}).get("sha256") == BOOTSTRAP[slot], "reviewed bootstrap authority differs")
    completion = P.read_json(root, "completion.json", check)
    require(completion.get("publication_complete") is True and completion.get("candidate_worlds_admitted") is False
        and type(completion.get("files")) is dict and exact(dict(completion["files"], **{"completion.json": files["completion.json"]}), files), "bootstrap exact sealed authority set")
    negative = P.read_json(root, "cross-native.json", check)
    P.negative_result(negative, "0495e6f149ec55c9f7ec0c5e4e01228b3e15a5eb0cd6c93af24d07dfd0059198",
        P.REVIEWED_BUILD["candidate_native_sha256"], B.OLD_NATIVE)
    proof = P.read_json(root, "proof.json", check)
    require(proof.get("status") == "proof_complete_pending_job" and proof.get("physics_ticks_registered") == 926
        and exact(proof.get("producer"), dict(control_sha=BOOTSTRAP["control_sha"], run_id=str(BOOTSTRAP["run_id"]), run_attempt="1", job_key="proof")), "bootstrap proof producer/scope")
    return B.canonical_bytes(files)


def validate_checkpoint_report(value):
    require(type(value) is dict and set(value) == {"runtime", "source_sha", "native_sha256", "worlds", "executions", "physics_ticks"}, "checkpoint report closed shape")
    validate_runtime(value["runtime"])
    require(value["source_sha"] == B.CANDIDATE_SOURCE and value["native_sha256"] == P.REVIEWED_BUILD["candidate_native_sha256"], "checkpoint source/native identity")
    require(type(value["worlds"]) is list and len(value["worlds"]) == 2, "both planned checkpoint worlds required")
    for actual, plan in zip(value["worlds"], plans()):
        require(type(actual) is dict and set(actual) == {"plan", "checkpoints"} and exact(actual["plan"], plan), "fixed checkpoint plan differs")
        require(type(actual["checkpoints"]) is list and len(actual["checkpoints"]) == len(plan["checkpoint_turns"]), "all registered checkpoints required")
        for row, turn in zip(actual["checkpoints"], plan["checkpoint_turns"]):
            require(type(row) is dict and set(row) == {"turn", "path", "bytes", "sha256", "header", "identity_matches", "comparison"}, "checkpoint row shape")
            require(type(row["turn"]) is int and row["turn"] == turn
                and row["path"] == f"checkpoints/{plan['worldgen']}/straight/checkpoint_turn_{turn}.ckpt"
                and type(row["bytes"]) is int and 0 < row["bytes"] <= 64*B.MIB and B.hash_shape(row["sha256"])
                and row["identity_matches"] is True, "candidate-owned checkpoint binding")
            header = row["header"]
            require(type(header) is dict and header.get("exact") is True and type(header.get("seed")) is int and header["seed"] == 42
                and type(header.get("turn")) is int and header["turn"] == turn
                and header.get("identity", {}).get("native", {}).get("sha256") == value["native_sha256"]
                and header.get("run_config", {}).get("agent_mode") == "hybrid"
                and [s.get("name") for s in header.get("sections", [])] == ["python", "native.agent.0"], "checkpoint hybrid header identity")
            comparison = row["comparison"]
            require(type(comparison) is dict and set(comparison) == {"status", "expected_files", "actual_files", "keys_sha256", "expected_outputs_sha256", "actual_outputs_sha256", "mismatches"}
                and comparison["status"] == "PASS" and type(comparison["expected_files"]) is int and comparison["expected_files"] > 0
                and type(comparison["actual_files"]) is int and comparison["actual_files"] == comparison["expected_files"]
                and B.hash_shape(comparison["keys_sha256"]) and B.hash_shape(comparison["expected_outputs_sha256"])
                and comparison["expected_outputs_sha256"] == comparison["actual_outputs_sha256"] and exact(comparison["mismatches"], []), "unchanged native checkpoint output comparison must PASS")
    require(type(value["executions"]) is int and value["executions"] == 15
        and type(value["physics_ticks"]) is int and value["physics_ticks"] == 2297, "checkpoint execution/tick budget")
    return value


def compare_outputs(expected, got):
    """Compare the unmodified native test's already-decoded output maps."""
    require(type(expected) is dict and type(got) is dict and expected
        and all(type(name) is str and type(raw) is bytes for name, raw in expected.items())
        and all(type(name) is str and type(raw) is bytes for name, raw in got.items()), "native checkpoint output map shape")
    require(got.keys() == expected.keys(), "checkpoint output keysets differ")
    require(all(got[name] == expected[name] for name in got), "checkpoint output values differ")
    outputs = lambda rows: B.digest({name: hashlib.sha256(raw).hexdigest() for name, raw in rows.items()})
    return dict(status="PASS", expected_files=len(expected), actual_files=len(got), keys_sha256=B.digest(sorted(expected)),
        expected_outputs_sha256=outputs(expected), actual_outputs_sha256=outputs(got), mismatches=[])


def bind_scientific_payload(report, files):
    """Bind scientific result rows to the actual post-cleanup physical copy."""
    validate_checkpoint_report(report["checkpoint"])
    for world in report["checkpoint"]["worlds"]:
        for row in world["checkpoints"]:
            require(exact(files.get("payload/" + row["path"]), dict(bytes=row["bytes"], sha256=row["sha256"])), "retained checkpoint differs from scientific report")
    for worldgen in ("template", "procedural"):
        result = report[worldgen]
        require(result["status"] == "PASS" and result["explicit_parallel"] == 2
            and result["execution_scope"] == REPEAT_EXECUTION_SCOPE, "registered repeat result scope")
        for row in result["bundles"]:
            name = f"payload/repeats/{worldgen}/determinism_hybrid/batch_42/" + row["path"]
            require(exact(files.get(name), dict(bytes=row["bytes"], sha256=row["sha256"])), "retained repeat bundle differs from scientific report")
    return True


def child(args):
    registration()
    runtime = observe_runtime()
    source, output = Path(args.source).resolve(), Path(args.output)
    for name, expected in P.KERNELS.items():
        require(hashlib.sha256(P.read_bytes(source, name)).hexdigest() == expected, "unchanged scientific source required")
    if args.child in ("template", "procedural"):
        C.write_json(args.out, runtime)
        command = repeat_command(sys.executable, source, args.child, output)
        os.execv(sys.executable, command)
    sys.path.insert(0, str(source / "src"))
    spec = importlib.util.spec_from_file_location("registered_native_checkpoint_kernel", source / "tests/test_run_checkpoint_native.py")
    kernel = importlib.util.module_from_spec(spec); spec.loader.exec_module(kernel)
    kernel._native()  # A skip is a child failure, never a qualifying result.
    import chronicler.run_checkpoint as rc
    worlds = []
    for plan in plans():
        folder = output / "checkpoints" / plan["worldgen"]
        straight = folder / "straight"
        extra = dict(validation_sidecar=True, checkpoint_turns=plan["checkpoint_turns"], regions=plan["regions"], civs=plan["civs"])
        if plan["worldgen"] == "procedural":
            extra["worldgen"] = "procedural"
        kernel.execute_run(kernel._args(straight, plan["turns"], "hybrid", **extra))
        rows = []
        for turn in plan["checkpoint_turns"]:
            checkpoint = straight / f"checkpoint_turn_{turn}.ckpt"
            header = rc.describe(checkpoint)
            require(rc._compare_identity(header["identity"], rc.runtime_identity(), True) == [], "fresh candidate checkpoint identity")
            resumed = folder / f"resumed_{turn}"
            # Identical existing native test rule: resume config comes from CP;
            # only the output destinations/horizon come from the off-mode args.
            kernel.execute_run(kernel._args(resumed, plan["turns"], "off"), checkpoint_resume=rc.read_checkpoint(checkpoint))
            expected, got = kernel._outputs(straight, after=turn), kernel._outputs(resumed)
            comparison = compare_outputs(expected, got)
            rows.append(dict(turn=turn, path=checkpoint.relative_to(output).as_posix(), bytes=checkpoint.stat().st_size,
                sha256=C.sha(checkpoint), header=header, identity_matches=True,
                comparison=comparison))
        worlds.append(dict(plan=plan, checkpoints=rows))
    report = dict(runtime=runtime, source_sha=B.CANDIDATE_SOURCE, native_sha256=P.REVIEWED_BUILD["candidate_native_sha256"],
        worlds=worlds, executions=15, physics_ticks=2297)
    C.write_json(args.out, validate_checkpoint_report(report))
    return 0


def retain_payload(root, *, cleanup_complete, children_gone, check):
    """Qualified physical copier, without permitting pytest aliases in this lane."""
    require(cleanup_complete is True and children_gone is True, "owned cleanup required before payload retention")
    root = Path(root)
    if not (root / "scratch").exists():
        return dict(status="not_created")
    require(not (root / "payload").exists(), "partial/existing payload is preserved, never replaced")
    copied = P.retain_pytest_outputs(root / "scratch", root / "payload", check)
    require(copied["pytest_scratch_aliases"] == [], "primer has no permitted aliases")
    return dict(status="retained", physical_files=copied["physical_files"], physical_bytes=copied["physical_bytes"],
        scope="All physical primer outputs, including own checkpoints and resume/repeat exports; original scratch remains until runner teardown.")


def staging_observation(temporary):
    row = P.read_json(temporary, "wealth-primer-preflight.json")
    require(type(row) is dict and set(row) == {"started_monotonic", "control_sha", "run_id", "attempt"}, "primer staging clock shape")
    require(row["control_sha"] == os.environ.get("GITHUB_SHA") and row["run_id"] == os.environ.get("GITHUB_RUN_ID")
        and row["attempt"] == os.environ.get("GITHUB_RUN_ATTEMPT"), "primer staging producer")
    start = row["started_monotonic"]
    require(type(start) in (int, float) and math.isfinite(start) and start > 0 and 0 <= time.monotonic()-start <= P.STAGING_WALL_SECONDS, "bounded180s staging window")
    return dict(elapsed_wall_seconds=time.monotonic()-start, limit_seconds=P.STAGING_WALL_SECONDS)


def proof(args):
    pins = registration()
    start, usage_before = time.monotonic(), resource.getrusage(resource.RUSAGE_CHILDREN)
    deadline = start + WALL_SECONDS
    require(sys.platform == "linux" and platform.python_version() == B.PYTHON_VERSION, "registered Linux/Python runtime")
    require(os.environ.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH and os.environ.get("GITHUB_JOB") == "primer"
        and os.environ.get("GITHUB_RUN_ATTEMPT") == "1" and re.fullmatch("[1-9][0-9]*", os.environ.get("GITHUB_RUN_ID", ""))
        and re.fullmatch("[0-9a-f]{40}", os.environ.get("GITHUB_SHA", "")), "closed first-attempt primer producer")
    workspace, temporary = Path(os.environ["GITHUB_WORKSPACE"]).resolve(), Path(os.environ["RUNNER_TEMP"]).resolve()
    control, source, root = SCRIPT.parents[1], Path(args.source).resolve(), Path(args.output).resolve()
    require(control == workspace / "control" and source == workspace / "candidate" and root == temporary / "wealth-production-primer", "closed primer paths")
    staging = staging_observation(temporary)
    require(not root.exists(), "fresh primer output required")
    root.mkdir(); (root / "logs").mkdir()
    before = source_bindings(control); C.write_json(root / "control-sources-before.json", before)
    workflow_contract(P.read_bytes(control, TEMPLATE_PATH), P.read_bytes(control, WORKFLOW_PATH))
    legacy = C.legacy_helpers(control)
    cancellation = C.Cancellation(); cancellation.__enter__()
    supervisor, failed, retained = None, None, None
    stage = "deployment"
    report = dict(schema_version=1, kind="wealth-floor-production-runtime-primer", status="incomplete",
        final_outcome_proof_pins_remain_null=True, historical_reuse_admitted=False, candidate_worlds_admitted=False,
        executions_registered=19, physics_ticks_registered=3097, prerequisite_registration=pins,
        producer=dict(control_sha=os.environ["GITHUB_SHA"], run_id=os.environ["GITHUB_RUN_ID"], run_attempt="1", job_key="primer"))
    try:
        report["deployment"] = P.hosted_vm_precondition()
        report["staging_observation"] = staging
        with C.SubreaperLease() as lease:
            supervisor = C.make_supervisor(legacy, root, deadline, lease, cancellation)
            supervisor.admission("production-primer", 12, 2)
            available = sorted(os.sched_getaffinity(0)); require(len(available) >= 2, "two actual CPUs required")
            os.sched_setaffinity(0, set(available[:2]))
            control_before = C.source_snapshot(legacy, control, os.environ["GITHUB_SHA"], deadline)
            C.write_json(root / "control-git-before.json", control_before)
            stage = "prerequisite_content_admission"
            now = datetime.now(timezone.utc)
            build = P.admit_build(temporary / "wealth-build-input", P.read_json(temporary, "wealth-build-publication.json"), now=now, check=supervisor.check)
            bootstrap_root = temporary / "wealth-bootstrap-input"
            bootstrap_inventory = admit_bootstrap(bootstrap_root, P.read_json(temporary, "wealth-bootstrap-publication.json"), now=now, check=supervisor.check)
            initial = C.source_snapshot(legacy, source, B.CANDIDATE_SOURCE, deadline)
            require(initial["crate_tree"] == B.CANDIDATE_CRATE, "candidate crate differs")
            for name, expected in P.KERNELS.items():
                require(hashlib.sha256(P.read_bytes(source, name)).hexdigest() == expected, "registered scientific kernel differs")
            C.write_json(root / "candidate-source-before.json", initial)
            env = C.build_environment(temporary, sys.executable)
            for key in list(env):
                if key.startswith(("GITHUB_", "RUNNER_", "CODEX_", "OIC_", "UV_")) or key in ("GH_TOKEN", "GITHUB_TOKEN"):
                    env.pop(key)
            env.update(PYTHONPATH=str(source / "src"), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
            env.pop("CARGO_TARGET_DIR", None); env.pop("PYO3_PYTHON", None)
            stage = "candidate_environment_and_probe"
            target = temporary / "wealth-primer-candidate-env"
            require(not target.exists(), "fresh candidate environment required")
            role_env = dict(env, UV_PROJECT_ENVIRONMENT=str(target))
            supervisor.command("candidate-locked-env", ["uv", "sync", "--project", str(source), "--frozen", "--no-install-project", "--python", sys.executable], role_env, control)
            python = target / "bin/python"
            P.recheck_build(build, supervisor.check)
            supervisor.command("candidate-wheel-install", ["uv", "pip", "install", "--no-deps", "--python", str(python), str(build.root / "wheels/candidate" / B.WHEEL_NAME)], role_env, control)
            supervisor.command("candidate-isolated-probe", [str(python), "-I", "-B", str(control / "scripts/wealth_floor_native_build_controller.py"), "probe", "--environment-root", str(target), "--out", str(root / "candidate-probe.json")], role_env, control)
            observed = P.read_json(root, "candidate-probe.json", supervisor.check)
            require(observed.get("native_sha256") == pins["build"]["candidate_native_sha256"] and observed.get("native_pools_created") == 0, "fresh native probe differs")
            stage = "late_checkpoint_continuations"
            supervisor.command("late-checkpoint-continuations", [str(python), "-B", str(SCRIPT), "--child", "checkpoints", "--source", str(source), "--output", str(root / "scratch"), "--out", str(root / "checkpoint-report.json")], env, source)
            report["checkpoint"] = validate_checkpoint_report(P.read_json(root, "checkpoint-report.json", supervisor.check))
            for worldgen in ("template", "procedural"):
                stage = "repeat_" + worldgen
                supervisor.command("production-repeat-" + worldgen, [str(python), "-B", str(SCRIPT), "--child", worldgen, "--source", str(source), "--output", str(root / "scratch/repeats"), "--out", str(root / (worldgen + "-runtime.json"))], env, source)
                runtime = validate_runtime(P.read_json(root, worldgen + "-runtime.json", supervisor.check))
                require(exact(runtime, report["checkpoint"]["runtime"]), "runtime changed between scientific children")
                batch = root / "scratch/repeats" / worldgen / "determinism_hybrid/batch_42"
                result = P.determinism_result(batch, worldgen, pins["build"]["candidate_native_sha256"], supervisor.check)
                summary = P.read_json(batch, "run_manifest.json", supervisor.check)
                require(type(summary.get("parallel")) is int and summary["parallel"] == 2, "explicit production parallel2 required")
                report[worldgen] = dict(result, runtime=runtime, explicit_parallel=2,
                    execution_scope=REPEAT_EXECUTION_SCOPE)
            stage = "source_input_and_owned_cleanup"
            final = C.source_snapshot(legacy, source, B.CANDIDATE_SOURCE, deadline)
            require(exact(initial, final), "candidate source changed")
            C.write_json(root / "candidate-source-after.json", final)
            control_after = C.source_snapshot(legacy, control, os.environ["GITHUB_SHA"], deadline)
            require(exact(control_before, control_after), "control Git source changed")
            C.write_json(root / "control-git-after.json", control_after)
            P.recheck_build(build, supervisor.check)
            require(bootstrap_inventory == B.canonical_bytes(P.inventory(bootstrap_root, max_bytes=8*B.MIB, max_files=32, check=supervisor.check)), "bootstrap authority changed")
            supervisor.check(final=True)
        require(supervisor.cleanup_complete and not C.direct_children(), "owned descendants remain")
        stage = "physical_payload_retention"
        retained = retain_payload(root, cleanup_complete=supervisor.cleanup_complete, children_gone=not C.direct_children(), check=lambda: supervisor.check(final=True))
        report["payload_retention"] = retained
        require(exact(before, source_bindings(control)), "control sources drifted")
        C.write_json(root / "control-sources-after.json", before)
        stage = "authority_publication"
        report["status"] = "proof_complete_pending_job"
        report["scope"] = "Seed42 hybrid CP101/201/301/401 through422 template and CP101..261/20 through282 procedural; unchanged native-test file comparison, generated_at-only decoded bundle scrub. Two genuine200T decoded bundle pairs with explicit parallel2. No all-raw/global-RNG/world identity, full outcome/cohort pass, historical reuse or finalA admission. Reuses sealed926 cross-native negative; no old-wheel world/restore rerun."
        used = resource.getrusage(resource.RUSAGE_CHILDREN)
        report["measured"] = dict(wall_seconds=time.monotonic()-start, wall_limit_seconds=WALL_SECONDS,
            controller_cpu_seconds=time.process_time(), waited_children_cpu_seconds=(used.ru_utime+used.ru_stime)-(usage_before.ru_utime+usage_before.ru_stime),
            scope="Observation after cleanup and physical retention, before publication hashing; no aggregate live-tree CPU admission or closed end-to-end total.")
        publication = root / "publication"; publication.mkdir()
        C.write_json(publication / "proof.json", report)
        for name in LIGHT_FILES:
            shutil.copyfile(root / name, publication / name)
        files = P.inventory(root, max_bytes=P.MAX_OUTPUT_BYTES, max_files=P.MAX_OUTPUT_FILES, check=lambda: supervisor.check(final=True), exclude=("scratch", "publication"))
        require(RAW_FILES <= files.keys() and all(n in RAW_FILES or n.startswith(("logs/", "payload/")) for n in files), "closed raw upload coverage")
        bind_scientific_payload(report, files)
        C.write_json(publication / "raw-payload-index.json", files)
        authority = P.inventory(publication, max_bytes=8*B.MIB, max_files=32, check=lambda: supervisor.check(final=True))
        C.write_json(publication / "completion.json", P.authority_completion(authority))
        supervisor.check(final=True)
        require(exact(before, source_bindings(control)), "control drift after publication")
        print(json.dumps(dict(kind="post_publication_observation", wall_seconds=time.monotonic()-start,
            source_bindings_unchanged=True, scope="After heavy checks; stdout emission and artifact upload remain outside observation.")))
    except BaseException as exc:
        failed = exc; report.update(status="incomplete", error=type(exc).__name__, failure_stage=stage)
    finally:
        if time.monotonic() > deadline or C.direct_children() or cancellation.cancelled:
            failed = failed or P.ProofRefused("late cleanup/deadline failure")
        try:
            cancellation.__exit__(type(failed) if failed else None, failed, None)
        except BaseException as exc:
            failed = failed or exc
        if failed:
            if supervisor is not None and retained is None:
                try:
                    retained = retain_payload(root, cleanup_complete=supervisor.cleanup_complete, children_gone=not C.direct_children(), check=lambda: supervisor.check(final=True))
                except BaseException as exc:
                    retained = dict(status="incomplete", error=type(exc).__name__, scope="Original scratch and partial payload untouched; no budget extension.")
            publication = root / "publication"; publication.mkdir(exist_ok=True)
            C.write_json(publication / "failure.json", dict(report, status="incomplete", payload_retention=retained))
            C.write_json(publication / "completion.json", dict(publication_complete=False, status="incomplete", error=type(failed).__name__,
                failure_stage=stage, payload_retention=retained, candidate_worlds_admitted=False))
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--registration", action="store_true")
    parser.add_argument("--validate-publication", action="store_true")
    parser.add_argument("--child", choices=("checkpoints", "template", "procedural"))
    for key in ("source", "output", "out"):
        parser.add_argument("--" + key)
    args = parser.parse_args(argv)
    if args.child:
        return child(args)
    if args.registration or args.validate_publication:
        pins = registration()
        require(os.environ.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "registered first-attempt primer branch")
        temporary = Path(os.environ["RUNNER_TEMP"])
        if args.validate_publication:
            staging_observation(temporary)
            now = datetime.now(timezone.utc)
            P.validate_publication(P.read_json(temporary, "wealth-build-publication.json"), pins["build"], now=now)
            validate_bootstrap_publication(P.read_json(temporary, "wealth-bootstrap-publication.json"), now=now)
            return 0
        started = time.monotonic()
        require(sys.platform == "linux" and platform.python_version() == B.PYTHON_VERSION, "registered preflight runtime")
        P.hosted_vm_precondition()
        from wealth_floor_build_resources import memory_admission
        require(shutil.disk_usage(temporary).free >= 12*1024**3 and memory_admission()["available_bytes"] >= 2*1024**3, "pre-transfer12GiB/2GiB admission")
        C.write_json(temporary / "wealth-primer-preflight.json", dict(started_monotonic=started, control_sha=os.environ["GITHUB_SHA"], run_id=os.environ["GITHUB_RUN_ID"], attempt="1"))
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="ascii") as stream:
            for role in ("build", "bootstrap"):
                for key in ("run_id", "artifact_id"):
                    stream.write(f"{role}_{key}={pins[role][key]}\n")
        return 0
    if not args.execute:
        print(json.dumps(dict(status="inactive", executions_registered=19, physics_ticks_registered=3097,
            source=B.CANDIDATE_SOURCE, final_outcome_proof_pins="unchanged/null", candidate_worlds_admitted=False)))
        return 0
    return proof(args)


if __name__ == "__main__":
    raise SystemExit(main())
