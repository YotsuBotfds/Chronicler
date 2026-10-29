#!/usr/bin/env python3
"""Closed, dormant CBF-to-090 default-export qualification; never a speed gate.

Only ``run --execute`` may prepare an environment or run the original matrix.
The original helper and C76/95 adapter remain byte-exact authenticated utilities.
Their pair-specific orchestration and registries are never called or patched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import time
from types import MappingProxyType, ModuleType

SCRIPT = Path(__file__).resolve()
KERNELS = MappingProxyType({
    "arc_output_identity_qualification.py": (34186, "0d3a2c5db023a47a82307d3a9b789eebd979915e52be66e7208f0c93a94540f5"),
    "native_default_output_identity_qualification.py": (41999, "fe7129a6c3d9386cc5aed7e4a6430509d552e4e87101510b02ddb016ef7f38d1"),
})


def load_utilities(directory=SCRIPT.parent):
    """Authenticate both exact source buffers before executing either; no .pyc."""
    buffers = {}
    for name, (size, digest) in KERNELS.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
            raise RuntimeError("immutable utility identity refused: " + name)
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError("immutable utility bytes changed: " + name)
        buffers[name] = raw
    name = "_cbf_090_authenticated_export_utilities"
    module = ModuleType(name)
    module.__file__ = str(directory / "native_default_output_identity_qualification.py")
    sys.modules[name] = module  # dataclasses resolves postponed annotations here.
    exec(compile(buffers["native_default_output_identity_qualification.py"], module.__file__, "exec"), module.__dict__)
    return module


A = load_utilities()
H, require, Refusal = A.H, A.require, A.Refusal
SOURCES = MappingProxyType({
    "baseline": "cbf6e368ebd218c1f54179bee4accffc1ab2a4c0",
    "candidate": "0900f3d203cc74102809bb871a1a057ba91a951f",
})
CRATES = MappingProxyType({"baseline": "912a1a2489f8f8c548df19302bb2c0a4365fc32e",
                          "candidate": "803c79c8d5c024cbb8d67c58af7ffa731d79c129"})
ACTIVE_BRANCH = "lead/cloud-cbf-090-default-identity-v2-20261029"
WORKFLOW_PATH = ".github/workflows/cbf-090-default-identity-v2.yml"
TEMPLATE_PATH = "docs/experiments/cbf-090-default-identity-v2-workflow.yml"
JOB_KEY = "cbf-090-default-identity-v2"
WORKFLOW_SHA = "46beb45f1021a0ba939aa3c886fe85a3b798d7d5a38be284a15b250cac7af295"
ARTIFACTS = MappingProxyType({
    "baseline-wheel": A.ArtifactPin(12882944002, 40841527996, 123338805674, SOURCES["baseline"],
        "native-wheel-" + SOURCES["baseline"], 3850581,
        "9cc55c9dbf7939056f0b0613e3e54e74798a782463719185d41b1fe129ebe2cf",
        "2026-11-12T08:33:42Z", ".github/workflows/tests.yml"),
    "baseline-preflight": A.ArtifactPin(12883297720, 40841527996, 123338805674, SOURCES["baseline"],
        "python-native-" + SOURCES["baseline"], 143075,
        "3e32164e432c7f666d214ab7df470bf656992a1dde88b56405de0b8f1a745af4",
        "2026-11-12T08:33:41Z", ".github/workflows/tests.yml"),
    "candidate-wheel": A.ArtifactPin(12893517727, 40865043984, 123417559998, SOURCES["candidate"],
        "native-wheel-" + SOURCES["candidate"], 3850543,
        "a8be042cacdbc049c099738e89b90961492b724561963e30c30e843cb2a52fac",
        "2026-11-12T11:35:09Z", ".github/workflows/tests.yml"),
    "candidate-preflight": A.ArtifactPin(12894166162, 40865043984, 123417559998, SOURCES["candidate"],
        "python-native-" + SOURCES["candidate"], 143055,
        "992884c0bc8df0d5cda19a07418e384c1229fc9735262e0a678a44e81ef90db0",
        "2026-11-12T11:35:08Z", ".github/workflows/tests.yml"),
})
WHEELS = MappingProxyType({
    "baseline": A.WheelPin("baseline-wheel", "chronicler-agents/target/wheels/" + A.WHEEL_NAME,
        3915395, "556c6677c4cb998cd6ad4b284d0f67a7e79368f86831b458c3885943de3b95ac",
        13695168, "3ee06a53b3c16dcba01bc53c8fe1dd97e530754a61d65fe2c1396b158b48e6d0"),
    "candidate": A.WheelPin("candidate-wheel", "chronicler-agents/target/wheels/" + A.WHEEL_NAME,
        3915587, "928db20c6cfbb6a79e2ad01469392d72093ebc1448c1b90d8c34f44f245b6532",
        13693904, "14a67f283cf57dc738e05d43d7b86aeca9039821e453e70274dfc1bb42e70e8c"),
})
# Expected values only. Candidate changes no Persist definitions/schema machinery;
# standard CI did NOT measure these schemas. Actual fields start null below.
EXPECTED_SCHEMAS = json.loads(json.dumps(A.SCHEMAS))
CI_QUALIFICATION = MappingProxyType({
    "candidate_root": "384415aab76a180370173e18918a640ab973c741b578fbe94ad01213e09dec77",
    "candidate_peer": "1bbdea1d6774e0bb38bdafd1a6463a5a959e193e96e94aa85c04f606e993b958",
    "scope": "Full standard CI only; no default-output, performance or science grant",
})
SHARED_FILES = ("uv.lock", "pyproject.toml", "scripts/turn_speed_identity.py",
                "scripts/cities_identity.py", "src/chronicler/bundle_codec.py")
NATIVE_STEPS = ((12, "Build Rust extension wheel"),
                (13, "Run Python tests with real native extension preloaded"),
                (14, "Retain native Python test results"), (15, "Retain the identified native wheel"))


def producer_context(env):
    require(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == A.REPOSITORY
        and env.get("GITHUB_EVENT_NAME") == "push" and env.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH
        and env.get("GITHUB_WORKFLOW_REF") == A.REPOSITORY + "/" + WORKFLOW_PATH + "@refs/heads/" + ACTIVE_BRANCH
        and env.get("GITHUB_JOB") == JOB_KEY and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and re.fullmatch("[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")) is not None
        and re.fullmatch("[0-9a-f]{40}", env.get("GITHUB_SHA", "")) is not None,
        "closed first-attempt CBF-to-090 push required")
    return {"control_sha": env["GITHUB_SHA"], "run_id": env["GITHUB_RUN_ID"], "run_attempt": "1",
            "job_key": JOB_KEY, "event": "push", "branch": ACTIVE_BRANCH, "workflow_ref": env["GITHUB_WORKFLOW_REF"]}


def workflow_contract(control, *, active_required=True):
    template, active = control / TEMPLATE_PATH, control / WORKFLOW_PATH
    require(not template.is_symlink() and H.sha(template) == WORKFLOW_SHA, "reviewed template changed")
    if active_required or active.exists() or active.is_symlink():
        require(not active.is_symlink() and active.read_bytes() == template.read_bytes(), "active workflow differs")


def validate_publication(pin, run, job, artifact, now):
    value = A.validate_publication(pin, run, job, artifact, now)
    require(job.get("name") == "Python native execution", "wrong native producer role")
    steps = job.get("steps")
    require(type(steps) is list and all(type(s) is dict and type(s.get("number")) is int for s in steps)
        and len({s["number"] for s in steps}) == len(steps), "invalid native producer steps")
    require(all(sum(s["number"] == number and s.get("name") == name and s.get("status") == "completed"
        and s.get("conclusion") == "success" for s in steps) == 1 for number, name in NATIVE_STEPS),
        "native build/preflight/publication steps incomplete")
    return value


def bounded_zip(stream):
    """Reject ZIP64 and oversized central-directory claims before ZipFile allocates."""
    stream.seek(0, 2); size = stream.tell()
    stream.seek(max(0, size - 65557)); tail = stream.read(65557)
    at = tail.rfind(b"PK\x05\x06")
    require(at >= 0 and at + 22 <= len(tail), "ZIP end record missing")
    sig, disk, cd_disk, local_count, count, cd_size, cd_offset, comment = struct.unpack_from("<4s4H2IH", tail, at)
    require(disk == cd_disk == 0 and local_count == count and 0 < count <= A.MAX_ENTRIES
        and cd_size <= A.MAX_MEMBER and cd_offset + cd_size == size - len(tail) + at
        and at + 22 + comment == len(tail) and b"PK\x06\x07" not in tail[max(0, at-20):at],
        "ZIP central directory bounds refused")
    stream.seek(0)


def inspect_input(path, pin, selected):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size == pin.size
        and H.sha(path) == pin.sha256, "input bytes differ before ZIP admission")
    with path.open("rb") as stream:
        bounded_zip(stream)
    return A.inspect_artifact(path, pin, selected)


def validate_ci_arm(arm, pins, payloads, preflight_pins, preflight_payloads):
    wheel = WHEELS[arm]
    require(set(pins) == {"ci-native-wheel/manifest.json", wheel.member}
        and set(preflight_pins) == {"native-identity.json", "native.xml"}
        and preflight_pins["native.xml"]["bytes"] > 0, "CI publication member set changed")
    manifest, identity = (H.strict_json(payloads["ci-native-wheel/manifest.json"]),
                          H.strict_json(preflight_payloads["native-identity.json"]))
    require(set(manifest) == {"schema_version", "source_commit", "wheel", "installed_native", "scope", "python", "classes"}
        and set(identity) == {"source_commit", "python", "executable", "compiled_extension", "sha256", "classes"},
        "CI JSON schema changed")
    require(A.exact_int(manifest["schema_version"], 1)
        and manifest["source_commit"] == identity["source_commit"] == SOURCES[arm], "CI arm source mismatch")
    require(manifest["wheel"] == {"filename": A.WHEEL_NAME, "bytes": wheel.size, "sha256": wheel.sha256,
        "native_member": A.NATIVE_MEMBER} and pins[wheel.member] == {"bytes": wheel.size, "sha256": wheel.sha256},
        "CI wheel descriptor differs")
    require(manifest["installed_native"] == {"filename": Path(A.NATIVE_MEMBER).name, "bytes": wheel.native_size,
        "sha256": wheel.native_sha256, "wheel_member_sha256": wheel.native_sha256}
        and identity["sha256"] == wheel.native_sha256, "CI compiled/preflight identity differs")
    require(manifest["classes"] == identity["classes"] == list(EXPECTED_SCHEMAS)
        and manifest["python"] == identity["python"] and manifest["python"].startswith(A.PYTHON + " ")
        and type(identity["executable"]) is str and identity["executable"].startswith("/")
        and type(identity["compiled_extension"]) is str and identity["compiled_extension"].startswith("/")
        and identity["compiled_extension"].endswith("/" + A.NATIVE_MEMBER), "CI real class/runtime preflight differs")
    return {"manifest": manifest, "preflight": identity, "historical_paths_only": True,
            "actual_fresh_schema_observation": None}


def admit_inputs(root, supervisor, deadline):
    transport = A.Transport(os.environ.get("GITHUB_TOKEN"), supervisor, deadline)
    publications, contents, paths = {}, {}, {}
    for role, pin in ARTIFACTS.items():
        before = transport.metadata(pin)
        validate_publication(pin, *[before["observed"][k] for k in ("run", "job", "artifact")], datetime.now(timezone.utc))
        path = root / "inputs" / (str(pin.artifact_id) + ".zip")
        transport.download(pin, path)
        arm = role.split("-", 1)[0]
        selected = {"ci-native-wheel/manifest.json", WHEELS[arm].member} if role.endswith("-wheel") else {"native-identity.json"}
        contents[role] = inspect_input(path, pin, selected)
        after = transport.metadata(pin)
        validate_publication(pin, *[after["observed"][k] for k in ("run", "job", "artifact")], datetime.now(timezone.utc))
        require(before["identity"] == after["identity"], "input publication changed during transfer")
        publications[role] = {"before": before, "after": after}; paths[role] = path
    admission = {"publications": publications, "arms": {}, "members": {k: v[0] for k, v in contents.items()}}
    for arm, wheel in WHEELS.items():
        admission["arms"][arm] = validate_ci_arm(arm, *contents[arm+"-wheel"], *contents[arm+"-preflight"])
        raw = contents[wheel.artifact][1][wheel.member]
        bounded_zip(io.BytesIO(raw))
        admission["arms"][arm]["wheel_members"] = A.validate_wheel(raw, wheel)
        path = root / "wheels" / arm / A.WHEEL_NAME
        with path.open("xb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        path.chmod(0o444)
    H.write(root / "input-admission.json", admission)
    return paths


def case_rows():
    return [{"arm": arm, "case": name, "status": "not_attempted"} for arm in SOURCES for name in H.CASES]


def require_complete(rows):
    require([(r.get("arm"), r.get("case")) for r in rows] == [(r["arm"], r["case"]) for r in case_rows()],
        "registered case order changed")
    require(all(r.get("status") == "complete" and re.fullmatch("[0-9a-f]{64}", r.get("audit_sha256", ""))
        for r in rows), "registered cases incomplete")


def package_digest(snapshot):
    digest = hashlib.sha256()
    for name, row in sorted(snapshot["files"].items()):
        if name.startswith("src/chronicler/") and name.endswith(".py"):
            digest.update(name.removeprefix("src/chronicler/").encode()); digest.update(b"\0")
            digest.update(row["sha256"].encode("ascii")); digest.update(b"\n")
    return digest.hexdigest()


def validate_probe(value, arm, source, prefix, digest, runtime=None):
    wheel, actual = WHEELS[arm], value["runtime"]
    require(value["source"]["git_sha"] == SOURCES[arm] and value["source"]["package_digest"] == digest
        and Path(value["source"]["package_dir"]).resolve() == source / "src/chronicler"
        and Path(value["source_file"]).resolve() == source / "src/chronicler/__init__.py", "wrong own-source package")
    native = value["native"]
    require(Path(value["prefix"]).resolve() == prefix and Path(value["native_file"]).resolve().is_relative_to(prefix)
        and native["module_file"] == value["native_file"] and native["status"] == "found" and native["source"] == "imported"
        and native["sha256"] == wheel.native_sha256 and A.exact_int(native["bytes"], wheel.native_size)
        and value["schemas"] == EXPECTED_SCHEMAS, "actual imported native/schema differs")
    require(actual["python"] == A.PYTHON and actual["implementation"] == "CPython"
        and actual["version"].startswith(A.PYTHON + " ") and actual["machine"] == "x86_64"
        and type(actual["affinity"]) is list and len(actual["affinity"]) == 1
        and type(actual["affinity"][0]) is int and actual["affinity"][0] >= 0 and actual["affinity"] == value["affinity"]
        and A.exact_int(actual["cpu_count"], 1) and A.exact_int(actual["process_cpu_count"], 1), "actual runtime policy differs")
    require(actual["prefix"] == str(prefix) and Path(actual["executable"]).is_absolute()
        and A.exact_int(actual["optimize"], 0) and A.exact_int(actual["no_user_site"], 1) and actual["dont_write_bytecode"] is True
        and actual["thread_env"] == {**H.CAPS, "PYTHONHASHSEED": "0", "OPENBLAS_THREAD_TIMEOUT": "16"}
        and set(actual["packages"]) == set(A.PACKAGE_NAMES)
        and all(type(v) is str and v for v in actual["packages"].values()), "actual runtime seal incomplete")
    expected_environment = {k: actual[k] for k in ("python", "implementation", "platform", "machine", "cpu_count", "process_cpu_count", "packages")}
    expected_environment.update(executable=value["environment"]["executable"], affinity_cpu_count=1,
        thread_env={k: v for k, v in actual["thread_env"].items() if k != "CARGO_BUILD_JOBS"})
    require(value["environment"] == expected_environment
        and Path(value["environment"]["executable"]).resolve() == Path(actual["executable"]), "duplicated runtime fields differ")
    require(runtime is None or runtime == actual, "actual arm runtime changed")
    return actual


def probe(args):
    require(args.expected_sha == SOURCES[args.arm], "unregistered probe source")
    H.probe(args)  # Original real class/schema/source probe, no simulator instance.
    value = H.strict_json(Path(args.out).read_bytes())
    value["runtime"] = A.runtime_seal()
    H.write(args.out, value)


def run_cases(root, roots, py, prefix, env, supervisor, report, snapshots):
    runtime, current_arm, native_copies = None, None, {}
    for row in report["cases"]:
        arm, name = row["arm"], row["case"]
        source, wheel = roots[arm], WHEELS[arm]
        if arm != current_arm:
            wheel_path, installer = root / "wheels" / arm / A.WHEEL_NAME, report["installer"]["uv"]
            require(H.sha(wheel_path) == wheel.sha256 and H.sha(installer["path"]) == installer["sha256"], "installer/wheel changed")
            supervisor.command("install-"+arm, A.install_command(py, wheel_path, installer["path"]), env, root)
            supervisor.admission("prepared-"+arm, 6, 2); current_arm = arm
        arm_root = root / "raw" / arm; arm_root.mkdir(exist_ok=True)
        child_env = dict(env, PYTHONPATH=str(source / "src"))
        for stage in ("before", "after"):
            out = root / "probes" / (arm+"-"+name+"-"+stage+".json")
            supervisor.command("probe-"+arm+"-"+name+"-"+stage,
                [py, str(SCRIPT), "probe", "--arm", arm, "--source-root", str(source), "--expected-sha", SOURCES[arm],
                 "--venv", str(prefix), "--out", str(out)], child_env, arm_root)
            identity = H.strict_json(out.read_bytes())
            runtime = validate_probe(identity, arm, source, prefix, package_digest(snapshots[arm]), runtime)
            report["actual_observations"][arm] = {"schemas": identity["schemas"], "native": identity["native"], "source": identity["source"]}
            report.update(installed_native_path=identity["native_file"], installed_native_arm=arm)
            if arm not in native_copies:
                copy = root / "native" / arm / Path(identity["native_file"]).name
                shutil.copyfile(identity["native_file"], copy)
                require(H.sha(copy) == wheel.native_sha256, "retained native copy differs")
                copy.chmod(0o444); native_copies[arm] = copy
            if stage == "before":
                row["status"] = "started"
                supervisor.command("world-"+arm+"-"+name, [py, str(source/"scripts/turn_speed_identity.py"), "run", str(arm_root),
                    "--source-root", str(source), "--case", name], child_env, arm_root)
                which = (arm_root/"which.txt").read_text()
                require(which == "chronicler "+identity["source_file"]+"\nnative "+identity["native_file"]+" "+wheel.native_sha256+"\n", "driver loaded identity differs")
                (root/"probes"/(arm+"-"+name+"-which.txt")).write_text(which)
        audit = root / "audits" / (arm+"-"+name+".json")
        supervisor.command("audit-"+arm+"-"+name, [py, str(H.SCRIPT), "inspect", "--case-root", str(arm_root/name),
            "--case", name, "--out", str(audit)], child_env, arm_root)
        row.update(status="complete", audit_sha256=H.sha(audit))
        supervisor.event("case_complete", arm=arm, case=name, audit_sha256=row["audit_sha256"])
    require_complete(report["cases"])
    H.require_case_sets(*[{p.name for p in (root/"raw"/arm).iterdir() if p.is_dir()} for arm in SOURCES])
    supervisor.command("compare", [py, str(roots["candidate"]/"scripts/turn_speed_identity.py"), "compare",
        str(root/"raw/baseline"), str(root/"raw/candidate")], dict(env, PYTHONPATH=str(roots["candidate"]/"src")), root)
    report["runtime"] = runtime
    return native_copies


def finish_report(root, report, quiescent, deadline):
    H.finish_evidence(root, report, quiescent, deadline)  # Same original 4800s clock.
    if time.monotonic() > deadline or not report["qualified"]:
        report.update(qualified=False, status="refused")
        H.write(root/"result.json", report)  # A late terminal write cannot grant a positive result.


def final_checks(root, roots, expected, before, inputs, copies, report, supervisor, deadline):
    require(supervisor.cleanup_complete, "cleanup unverified; final inventories withheld")
    require(all(A.utc(pin.expiry) > datetime.now(timezone.utc) for pin in ARTIFACTS.values()), "original input expiry reached")
    after = {k: H.source_snapshot(v, expected[k], deadline) for k, v in roots.items()}
    H.write(root/"sources-after.json", after)
    require(before == after, "tracked source standing/bytes changed")
    for role, path in inputs.items():
        require(H.sha(path) == ARTIFACTS[role].sha256, "input artifact changed")
    for arm, wheel in WHEELS.items():
        require(H.sha(root/"wheels"/arm/A.WHEEL_NAME) == wheel.sha256, "retained wheel changed")
    for arm, copy in copies.items():
        require(H.sha(copy) == WHEELS[arm].native_sha256, "retained native changed")
    if "installer" in report:
        require(H.sha(report["installer"]["uv"]["path"]) == report["installer"]["uv"]["sha256"], "installer changed")
    if "installed_native_path" in report:
        require(H.sha(report["installed_native_path"]) == WHEELS[report["installed_native_arm"]].native_sha256, "last installed native changed")
    for row in report["cases"]:
        if row["status"] == "complete":
            audit = root/"audits"/(row["arm"]+"-"+row["case"]+".json")
            require(H.sha(audit) == row["audit_sha256"] and H.payload_inventory(root/"raw"/row["arm"]/row["case"]) ==
                H.strict_json(audit.read_bytes())["files"], "exports/audit changed")
    require(time.monotonic() <= deadline, "aggregate wall budget exceeded")


def execute(args):
    require(args.execute is True, "inactive: explicit --execute required")
    producer = producer_context(os.environ)
    require(not [k for k in os.environ if k.startswith("GIT_") and k != "GIT_PAGER"], "ambient Git override refused")
    require(not [k for k in os.environ if k.startswith("CHRONICLER_") and k != "CHRONICLER_QUIET"], "unexpected simulation switch")
    root = Path(args.evidence).resolve()
    roots = {"baseline": Path(args.baseline_root).resolve(), "candidate": Path(args.candidate_root).resolve(), "control": SCRIPT.parents[1]}
    require(len(set(roots.values())) == 3 and all(not root.is_relative_to(v) for v in roots.values()), "external distinct roots required")
    root.mkdir(parents=True, exist_ok=False)
    for folder in ("logs", "probes", "audits", "raw", "inputs", "wheels", "native"):
        (root/folder).mkdir()
    for arm in SOURCES:
        (root/"wheels"/arm).mkdir(); (root/"native"/arm).mkdir()
    deadline = time.monotonic() + H.WALL_SECONDS
    supervisor = H.Supervisor(root, deadline)
    env = dict(os.environ, **H.CAPS, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               PYTHONOPTIMIZE="0", OPENBLAS_THREAD_TIMEOUT="16", CHRONICLER_QUIET="1")
    for key in tuple(env):
        if key in ("GITHUB_TOKEN", "GH_TOKEN", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV") or key.startswith(("PIP_", "UV_")):
            env.pop(key)
    env["PIP_CONFIG_FILE"] = os.devnull
    expected = {**SOURCES, "control": producer["control_sha"]}
    report = {"schema_version": 1, "qualified": False, "status": "pending", "sources": dict(SOURCES), "crates": dict(CRATES),
        "producer": producer, "cases": case_rows(), "expected_schemas": EXPECTED_SCHEMAS,
        "actual_observations": {arm: None for arm in SOURCES}, "CI_qualification": dict(CI_QUALIFICATION),
        "native_sha256_by_arm": {arm: w.native_sha256 for arm, w in WHEELS.items()},
        "wheel_sha256_by_arm": {arm: w.sha256 for arm, w in WHEELS.items()},
        "normalization": "metadata.generated_at only; original .log/run_manifest exclusions",
        "limitations": ["Exact CBF-to-090 default exports only; no checkpoint/RNG/science/performance/adoption grant",
                        "Requires separate completed-job/publication and independent artifact qualification",
                        "Standard CI did not measure schemas; actual fresh fields stay null until real probes"]}
    before, inputs, copies = {}, {}, {}
    py = str(Path(args.python).absolute()); prefix = Path(py).parent.parent.resolve()
    try:
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        supervisor.admission("initial", 12, 2)
        before = {k: H.source_snapshot(v, expected[k], deadline) for k, v in roots.items()}
        workflow_contract(roots["control"])
        require(all(before[k]["crate_tree"] == CRATES[k] for k in SOURCES), "wrong native crate")
        for relative in SHARED_FILES:
            require(before["baseline"]["files"][relative] == before["candidate"]["files"][relative], "shared input differs: "+relative)
        require(package_digest(before["baseline"]) == package_digest(before["candidate"]), "running Python packages differ")
        for arm in SOURCES:
            H.require_matrix(roots[arm]/"scripts/turn_speed_identity.py")
        H.write(root/"freeze.json", {"sources": before, "matrix": H.CASES, "utilities": dict(KERNELS),
            "adapter_sha256": H.sha(SCRIPT), "thread_caps": H.CAPS, "affinity": sorted(os.sched_getaffinity(0))})
        report["installer"] = A.prepare_environment(root, roots, py, prefix, env, supervisor)
        inputs = admit_inputs(root, supervisor, deadline)
        supervisor.admission("inputs-prepared", 6, 2)
        copies = run_cases(root, roots, py, prefix, env, supervisor, report, before)
        require_complete(report["cases"])
        report.update(qualified=True, status="exports_complete_pending_completed_job")
    except Exception as error:
        report["error"] = type(error).__name__+": "+str(error)[:2048]
    finally:
        try:
            final_checks(root, roots, expected, before, inputs, copies, report, supervisor, deadline)
        except Exception as error:
            report.update(qualified=False, final_identity_error=type(error).__name__+": "+str(error)[:2048])
        for row in report["cases"]:
            if row["status"] == "started": row["status"] = "failed"
        if not report["qualified"]: report["status"] = "refused"
        finish_report(root, report, supervisor.cleanup_complete, deadline)
    print(json.dumps({k: report.get(k) for k in ("qualified", "status", "error", "final_identity_error", "inventory_sha256", "elapsed_wall_seconds")}))
    return 0 if report["qualified"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("describe")
    run = sub.add_parser("run")
    run.add_argument("--execute", action="store_true")
    for name in ("baseline-root", "candidate-root", "python", "evidence"):
        run.add_argument("--"+name, required=True)
    p = sub.add_parser("probe")
    p.add_argument("--arm", choices=tuple(SOURCES), required=True)
    for name in ("source-root", "expected-sha", "venv", "out"):
        p.add_argument("--"+name, required=True)
    args = parser.parse_args(argv)
    if args.command == "run": return execute(args)
    if args.command == "probe": probe(args); return 0
    print(json.dumps({"status": "inactive", "sources": dict(SOURCES), "crates": dict(CRATES), "worlds": len(case_rows()),
        "physics_ticks": 2*sum(int(cli[cli.index("--turns")+1]) for cli, _ in H.CASES.values()),
        "input_artifacts": {k: vars(v) for k, v in ARTIFACTS.items()}, "expected_schemas": EXPECTED_SCHEMAS,
        "actual_observations": {arm: None for arm in SOURCES}, "activation_authorized": False,
        "scope": "Source registration only; no probe/setup/download/world performed"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
