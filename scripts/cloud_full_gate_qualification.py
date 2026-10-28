#!/usr/bin/env python3
"""Fixed four-cohort full-gate controller; no physics or oracle policy changes."""
from __future__ import annotations
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import zipfile

SCRIPT = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("fixed_identity_controls", SCRIPT.with_name("default_output_identity_qualification.py"))
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)
require, Refusal, sha, write = controls.require, controls.Refusal, controls.sha, controls.write
BASE, CANDIDATE = controls.BASE, controls.CANDIDATE
SOURCES = {"baseline": BASE, "candidate": CANDIDATE}
CAPS = dict(controls.CAPS, PYTHON_CPU_COUNT="2")
BUILD_SECONDS, SMOKE_SECONDS, COHORT_SECONDS = 80 * 60, 80 * 60, 330 * 60
MAX_FILE_BYTES, MAX_LIGHT_BYTES, MAX_LIGHT_FILES = 32 * 1024 ** 2, 128 * 1024 ** 2, 64
CLASS_NAMES = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
KINDS = {name: "chronicler-cloud-full-gate-" + name for name in
         ("build", "cohort", "smoke", "provenance", "raw-inventory", "light-index")}
REPORT_FILES = {
    "report/validate_report_full.json": "raw/full_gate/batch_42/validate_report_full.json",
    "report/gate_decision_full.json": "raw/full_gate/batch_42/gate_decision_full.json",
    "report/gate_summary_full.md": "raw/full_gate/batch_42/gate_summary_full.md",
    "report/run_manifest.json": "raw/full_gate/batch_42/run_manifest.json",
    "report/batch_manifest.json": "raw/full_gate/batch_42/batch_manifest.json",
    "report/ablation_manifest.json": "raw/full_gate/ablation_42/ablation_manifest.json",
}
LIGHT_SOURCES = dict(REPORT_FILES, **{
    "provenance.json": "provenance.json", "build-manifest.json": "build-manifest.json",
    "raw-inventory.json": "raw-inventory.json",
})
RUNTIME_KEYS = ("python", "implementation", "machine", "thread_env", "packages", "affinity_cpu_count")


def expected(worldgen, stage="full"):
    require(worldgen in ("template", "procedural"), "unknown world generator")
    require(stage in ("smoke", "full"), "unknown qualification stage")
    procedural = worldgen == "procedural"
    turns, count, step = (300, 100, 20) if procedural else (500, 200, 100)
    if stage == "smoke":
        turns, count = 125, 2
    forks = list(range(100, turns - 20, step))
    return dict(profile="subset" if stage == "smoke" else "full", worldgen=worldgen, seed_start=42, seed_count=count,
                turns=turns, regions=32 if procedural else 8, civs=10 if procedural else 4,
                parallel=2, cpus=2, threads=1, arms=["needs", "kin_roots"],
                fork_turns=forks, checkpoint_turns=[turn + 1 for turn in forks],
                fork_count=count * len(forks) * 2, window_turns=20,
                require_strict_regression=stage == "full", causal_oracles_required=False)


def report_files(stage):
    if stage == "full":
        return REPORT_FILES
    require(stage == "smoke", "unknown report stage")
    return {key.replace("_full.", "_subset."): value.replace("raw/full_gate/", "raw/oracle_subset/").replace("_full.", "_subset.")
            for key, value in REPORT_FILES.items()}


def light_sources(stage):
    return dict(report_files(stage), **{name: value for name, value in LIGHT_SOURCES.items() if not name.startswith("report/")})


def native_shape(record):
    require(isinstance(record, dict) and isinstance(record.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]), "native hash missing")
    schemas = record.get("schemas")
    require(isinstance(schemas, dict) and set(schemas) == set(CLASS_NAMES), "three native schemas required")
    for value in schemas.values():
        require(isinstance(value, dict) and set(value) == {"version", "fingerprint", "schema_sha256"},
                "native schema fields differ")
        require(type(value["version"]) is int and value["version"] >= 0, "native schema version is not an integer")
        require(isinstance(value["fingerprint"], str) and value["fingerprint"], "native schema fingerprint missing")
        require(isinstance(value["schema_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["schema_sha256"]),
                "native schema hash missing")


def outcome_flags(stage, execution_complete, identities_stable, gate_pass):
    ready = execution_complete and identities_stable
    return {"qualified": stage == "full" and ready and gate_pass,
            "smoke_pass": stage == "smoke" and ready}


def copy_build_light(root):
    light = root / "light"
    light.mkdir()
    names = ("source-snapshot-before.json", "source-snapshot-after.json",
             "probes/before.json", "probes/after.json", "raw-inventory.json")
    files, missing, total = {}, [], 0
    for name in names:
        source, target = root / name, light / name
        if not source.is_file() or source.is_symlink():
            missing.append(name)
            continue
        size = source.stat().st_size
        require(size <= MAX_FILE_BYTES and total + size <= MAX_LIGHT_BYTES, "builder light bounds exceeded")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        require(sha(source) == sha(target), "builder light copy differs")
        files[name], total = dict(bytes=size, sha256=sha(target)), total + size
    write(light / "artifact-index.json", dict(schema_version=1,
        kind="chronicler-cloud-full-gate-build-light-index", complete=not missing, missing=missing,
        file_count=len(files), total_bytes=total, files=files))
    return not missing


def bounded_json(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), "required JSON is not a regular file: " + str(path))
    require(path.stat().st_size <= MAX_FILE_BYTES, "JSON exceeds registered byte cap")
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    require(len(raw) <= MAX_FILE_BYTES, "JSON grew beyond registered byte cap")
    result = controls.strict_json(raw)
    require(isinstance(result, dict), "JSON object required")
    return result


def runtime_signature(environment):
    require(isinstance(environment, dict) and all(key in environment for key in RUNTIME_KEYS),
            "runtime identity fields missing")
    return {key: environment[key] for key in RUNTIME_KEYS}


def activate_environment():
    require(not [key for key in os.environ if key.startswith("CHRONICLER_") and key != "CHRONICLER_QUIET"],
            "unexpected simulation environment switch")
    available = sorted(os.sched_getaffinity(0))
    require(len(available) >= 2, "two actual CPUs required")
    os.sched_setaffinity(0, set(available[:2]))
    return dict(os.environ, **CAPS, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1",
                PYTHONNOUSERSITE="1", CHRONICLER_QUIET="1")


class Supervisor(controls.Supervisor):
    """Same owned-child cleanup, with this protocol's explicit independent budget."""
    def __init__(self, root, deadline, minutes):
        super().__init__(root, deadline, budget_label=f"{minutes}-minute")
        self.printed_phases = set()

    def admission(self, phase, disk, ram):
        visible = controls.resource_visibility(self.root)
        self.event("resource_visibility", phase=phase, **visible)
        if phase not in self.printed_phases:
            print(json.dumps({"event": "resource_visibility", "phase": phase, **visible}), flush=True)
            self.printed_phases.add(phase)
        try:
            row = controls.resources(self.root)
            self.event("resources", phase=phase, **row)
            controls.admit(row, disk, ram)
        except Exception as exc:
            print(json.dumps({"event": "resource_refusal", "phase": phase, "error": str(exc)[:2048],
                              "visibility": visible}), flush=True)
            raise


def probe(args):
    import chronicler
    import chronicler_agents as package
    import chronicler_agents.chronicler_agents as native
    from chronicler.batch_manifest import source_identity, native_identity, environment_identity
    require(sys.version_info[:2] == (3, 13), "Python 3.13 required")
    require(Path(sys.prefix).resolve() == Path(args.venv).resolve(), "wrong Python environment")
    require(Path(chronicler.__file__).resolve() == Path(args.source_root).resolve() / "src/chronicler/__init__.py",
            "wrong running source package")
    source = source_identity()
    require(source["git_sha"] == args.source_sha, "wrong running source revision")
    require(Path(source["package_dir"]).resolve() == Path(args.source_root).resolve() / "src/chronicler",
            "wrong running package directory")
    origin = Path(native.__file__).resolve()
    require(str(origin).endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)), "module is not a compiled extension")
    require(origin.is_relative_to(Path(args.venv).resolve()), "compiled extension is outside qualified environment")
    schemas = {}
    for name in CLASS_NAMES:
        cls = getattr(package, name)
        require(isinstance(cls, type) and cls is getattr(native, name), "native class export mismatch")
        version, fingerprint, schema = cls.checkpoint_schema()
        schemas[name] = dict(version=version, fingerprint=fingerprint,
                             schema_sha256=hashlib.sha256(schema.encode()).hexdigest())
    require(len(os.sched_getaffinity(0)) == 2, "actual affinity must contain two CPUs")
    require(all(os.environ.get(key) == value for key, value in CAPS.items()), "thread or CPU cap changed")
    native_record = native_identity()
    native_record["schemas"] = schemas
    write(args.out, dict(source=source, native=native_record, environment=environment_identity(),
          affinity=sorted(os.sched_getaffinity(0)), prefix=sys.prefix,
          source_file=chronicler.__file__, host={key: os.environ.get(key) for key in
          ("ImageOS", "ImageVersion", "RUNNER_OS", "RUNNER_ARCH")}))


def inspect_probe(supervisor, label, py, source, source_sha, environment, root):
    path = root / "probes" / (label + ".json")
    env = dict(environment, PYTHONPATH=str(source / "src"))
    supervisor.command("probe-" + label, [py, str(SCRIPT), "probe", "--source-root", str(source),
        "--source-sha", source_sha, "--venv", str(Path(py).parent.parent), "--out", str(path)], env, root)
    return bounded_json(path)


def cohort_command(py, source, worldgen, output, stage="full"):
    config = expected(worldgen, stage)
    command = [py, str(source / "scripts/m53b_run_validation.py"), "--profile", config["profile"],
               "--worldgen", worldgen, "--parallel", "2", "--output-root", str(output)]
    if stage == "smoke":
        command += ["--seed-start", "42", "--seeds", "2", "--turns", "125", "--ablation-oracles"]
    else:
        command.append("--require-strict-regression")
    return command


def validate_build(manifest, path, wheel, expected_manifest_sha, expected_wheel_sha):
    require(sha(path) == expected_manifest_sha, "builder manifest SHA mismatch")
    require(type(manifest.get("schema_version")) is int and manifest["schema_version"] == 1,
            "unknown builder schema")
    require(manifest.get("kind") == KINDS["build"] and manifest.get("qualified") is True,
            "builder did not qualify the shared wheel")
    require(manifest.get("baseline_sha") == BASE and manifest.get("candidate_sha") == CANDIDATE,
            "builder source pair differs")
    require(manifest.get("control_sha") == os.environ["GITHUB_SHA"], "builder controls differ")
    require(manifest.get("github_run_id") == os.environ["GITHUB_RUN_ID"] and
            manifest.get("github_run_attempt") == os.environ["GITHUB_RUN_ATTEMPT"],
            "builder artifact belongs to another workflow attempt")
    spec = manifest["wheel"]
    require(Path(spec["filename"]).name == spec["filename"] and wheel.name == spec["filename"],
            "wheel filename differs")
    require(spec["sha256"] == expected_wheel_sha == sha(wheel), "shared wheel SHA mismatch")
    require(spec["bytes"] == wheel.stat().st_size, "wheel byte count differs")
    require(manifest["native"]["sha256"] == spec["native_sha256"], "wheel/native identity differs")
    native_shape(manifest["native"])


def validate_records(run, batch, ablation, report, decision, config, source_sha, native_sha):
    seeds = list(range(42, 42 + config["seed_count"]))
    require(run.get("profile") == config["profile"] and run.get("worldgen") == config["worldgen"],
            "wrong run profile/world")
    for key, value in (("seeds", config["seed_count"]), ("turns", config["turns"]), ("seed_start", 42),
                       ("parallel", 2), ("ablation_forks", config["fork_count"]),
                       ("ablation_fork_turns", config["fork_turns"]), ("ablation_arms", config["arms"]),
                       ("require_strict_regression", config["require_strict_regression"]), ("causal_oracles_required", False),
                       ("ablation_oracles", True), ("exploratory_comparison", False)):
        require(type(run.get(key)) is type(value) and run[key] == value, "run manifest differs: " + key)
    require(run.get("baseline_report_path") is None and run.get("comparison_status") is None,
            "generation must not compare or rebaseline")
    require(batch.get("status") == "complete" and batch.get("seeds") == seeds
            and all(type(seed) is int for seed in batch["seeds"])
            and type(batch.get("turns")) is int and batch["turns"] == config["turns"], "incomplete parent cohort")
    parent_rows = batch.get("runs")
    require(isinstance(parent_rows, list) and len(parent_rows) == len(seeds), "parent count differs")
    require(all(type(row.get("seed")) is int for row in parent_rows) and
            sorted(row["seed"] for row in parent_rows) == seeds, "parent seed set differs")
    require(all(type(row.get("total_turns")) is int and row["total_turns"] == config["turns"]
                for row in parent_rows), "parent horizon differs")
    require(all(isinstance(row.get("files"), dict) and row["files"] for row in parent_rows),
            "parent validation-file hashes missing")
    simulation = batch["simulation"]
    require(simulation.get("agents") == "hybrid" and simulation.get("regions") == config["regions"]
            and simulation.get("civs") == config["civs"], "wrong parent simulation shape")
    require(simulation.get("worldgen") in ((None, "template") if config["worldgen"] == "template" else ("procedural",)),
            "wrong parent world generator")
    for manifest in (batch, ablation):
        require(manifest["source"]["git_sha"] == source_sha and manifest["native"]["sha256"] == native_sha,
                "recorded source/native identity differs")
    require(ablation.get("status") == "complete" and type(ablation.get("schema_version")) is int
            and ablation["schema_version"] == 2 and type(ablation.get("design")) is int and ablation["design"] == 2 and ablation.get("seeds") == seeds
            and ablation.get("arms") == config["arms"] and ablation.get("fork_turns") == config["fork_turns"]
            and ablation.get("window_turns") == 20 and ablation.get("fork_count") == config["fork_count"],
            "ablation design/count differs")
    rows = ablation.get("forks")
    require(isinstance(rows, list) and len(rows) == config["fork_count"], "fork record count differs")
    actual = [(row.get("arm"), row.get("seed"), row.get("fork_turn")) for row in rows]
    wanted = {(arm, seed, turn) for arm in config["arms"] for seed in seeds for turn in config["fork_turns"]}
    require(len(actual) == len(set(actual)) and set(actual) == wanted, "fork tuple coverage differs")
    for row in rows:
        require(all(type(row.get(key)) is int for key in ("seed", "fork_turn", "total_turns")),
                "fork numeric aliases are not accepted")
        require(row.get("total_turns") == row["fork_turn"] + 22, "fork horizon differs")
        require(row.get("decision_ablation") == dict(name=row["arm"], start_turn=row["fork_turn"] + 1,
                                                   forked_at=row["fork_turn"] + 1), "fork intervention differs")
        require(set(row.get("files", {})) == {"agent_events.arrow", "fork.json"}, "fork file hashes missing")
    require(report.get("profile") == config["profile"] and report.get("causal_oracles_required") is False
            and report.get("batch_manifest", {}).get("status") == "verified"
            and report.get("ablation_arms", {}).get("status") == "verified", "validator did not verify cohort inputs")
    require(decision.get("profile") == config["profile"] and decision.get("require_strict_regression") is config["require_strict_regression"]
            and decision.get("causal_oracles_required") is False, "original gate policy differs")
    require(type(decision.get("ok")) is bool and type(decision.get("exit_code")) is int and decision["exit_code"] in (0, 2),
            "malformed original gate decision")
    require(run.get("gate_exit_code") == decision["exit_code"]
            and run.get("gate_status") == ("PASS" if decision["ok"] else "FAIL")
            and decision["exit_code"] == (0 if decision["ok"] else 2), "original gate statuses disagree")
    return dict(parent_count=len(parent_rows), fork_count=len(rows), gate_pass=decision["ok"],
                gate_exit_code=decision["exit_code"])


def check_manifest_hashes(root, batch, ablation, inventory, stage="full"):
    files = inventory["files"]
    prefix = "raw/full_gate/" if stage == "full" else "raw/oracle_subset/"
    for row in batch["runs"]:
        for relative, digest in row["files"].items():
            key = prefix + "batch_42/" + relative
            require(key in files and files[key]["sha256"] == digest, "parent validation input changed: " + relative)
    for row in ablation["forks"]:
        require(row["dir"] == f'{row["arm"]}/seed_{row["seed"]}/fork_{row["fork_turn"]}',
                "unexpected fork output path")
        for relative, digest in row["files"].items():
            key = prefix + "ablation_42/" + row["dir"] + "/" + relative
            require(key in files and files[key]["sha256"] == digest, "fork validation input changed")
    require(ablation["plain_manifest_sha256"] == sha(root / prefix / "batch_42/batch_manifest.json"),
            "ablation parent-manifest crosslink changed")


def inventory(root):
    files = controls.payload_inventory(root, exclude=("raw-inventory.json", "result.json", "provenance.json"))
    return dict(schema_version=1, kind=KINDS["raw-inventory"], complete=True,
                scope="worker payload before derived light copies; excludes final receipts and inventory",
                file_count=len(files), total_bytes=sum(row["bytes"] for row in files.values()), files=files)


def copy_light(root, stage="full"):
    light = root / "light"
    light.mkdir()
    missing, files, total = [], {}, 0
    for relative, source in light_sources(stage).items():
        path = root / source
        if not path.is_file() or path.is_symlink():
            missing.append(relative)
            continue
        size = path.stat().st_size
        require(size <= MAX_FILE_BYTES, "lightweight file exceeds registered cap: " + relative)
        total += size
        require(total <= MAX_LIGHT_BYTES and len(files) + 1 <= MAX_LIGHT_FILES,
                "lightweight package exceeds registered bounds")
        target = light / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        require(sha(path) == sha(target), "lightweight copy differs")
        files[relative] = dict(bytes=size, sha256=sha(target))
    index = dict(schema_version=1, kind=KINDS["light-index"], complete=not missing, missing=missing,
                 file_count=len(files), total_bytes=total, files=files)
    write(light / "artifact-index.json", index)
    return index


def summarize(report):
    summary = {key: report.get(key) for key in ("kind", "qualified", "smoke_pass", "stage", "execution_complete", "gate_pass",
        "gate_exit_code", "arm", "worldgen", "source_sha", "wheel_sha256", "native_sha256",
        "build_manifest_sha256", "raw_inventory_sha256", "light_index_sha256", "elapsed_wall_seconds")}
    for key in ("error", "final_identity_error", "inventory_error", "light_error"):
        summary[key] = str(report[key])[:2048] if key in report else None
    print(json.dumps(summary, allow_nan=False), flush=True)


def build(args):
    root = Path(args.evidence).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for name in ("logs", "probes", "wheels"):
        (root / name).mkdir()
    started, deadline = time.monotonic(), time.monotonic() + BUILD_SECONDS
    supervisor = Supervisor(root, deadline, 80)
    roots = dict(baseline=Path(args.baseline_root).resolve(), candidate=Path(args.candidate_root).resolve(),
                 control=SCRIPT.parents[1])
    revisions = dict(SOURCES, control=os.environ["GITHUB_SHA"])
    report = dict(schema_version=1, kind=KINDS["build"], qualified=False, baseline_sha=BASE,
                  candidate_sha=CANDIDATE, control_sha=revisions["control"],
                  github_run_id=os.environ["GITHUB_RUN_ID"], github_run_attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                  budget_seconds=BUILD_SECONDS)
    before, native_file, wheel = {}, None, None
    wheel_sha = None
    try:
        env = activate_environment()
        require(len(set(roots.values())) == 3 and all(not root.is_relative_to(path) for path in roots.values()),
                "fresh external evidence and separate sources required")
        before = {name: controls.source_snapshot(path, revisions[name], deadline) for name, path in roots.items()}
        write(root / "source-snapshot-before.json", before)
        require(before["baseline"]["crate_tree"] == before["candidate"]["crate_tree"], "crate trees differ")
        for relative in ("uv.lock", "pyproject.toml"):
            require(sha(roots["baseline"] / relative) == sha(roots["candidate"] / relative), "lock inputs differ")
        report.update(crate_tree=before["candidate"]["crate_tree"], lock_sha256=sha(roots["candidate"] / "uv.lock"),
                      pyproject_sha256=sha(roots["candidate"] / "pyproject.toml"))
        target = Path(os.environ["CARGO_TARGET_DIR"]).resolve()
        require(not target.exists() and all(not target.is_relative_to(path) for path in roots.values()),
                "Cargo target must be fresh and external")
        for label, command in (("rustc-version", ["rustc", "--version", "--verbose"]),
                               ("cargo-version", ["cargo", "--version"]),
                               ("maturin-version", [args.python, "-m", "maturin", "--version"]),
                               ("uv-version", ["uv", "--version"])):
            supervisor.command(label, command, env, root)
        supervisor.admission("before_build", 12, 2)
        supervisor.command("build", [args.python, "-m", "maturin", "build", "--release", "--locked",
            "--manifest-path", str(roots["candidate"] / "chronicler-agents/Cargo.toml"),
            "--out", str(root / "wheels")], env, root)
        wheels = list((root / "wheels").glob("*.whl"))
        require(len(wheels) == 1, "exactly one fresh wheel required")
        wheel, wheel_sha = wheels[0], sha(wheels[0])
        with zipfile.ZipFile(wheel) as archive:
            members = [name for name in archive.namelist() if name.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))]
            require(len(members) == 1, "one compiled wheel member required")
            native_sha = hashlib.sha256(archive.read(members[0])).hexdigest()
        report["wheel"] = dict(filename=wheel.name, bytes=wheel.stat().st_size, sha256=wheel_sha,
                               native_member=members[0], native_sha256=native_sha)
        supervisor.command("install", ["uv", "pip", "install", "--no-deps", "--python", args.python, str(wheel)], env, root)
        supervisor.admission("after_build", 6, 2)
        first = inspect_probe(supervisor, "before", args.python, roots["candidate"], CANDIDATE, env, root)
        second = inspect_probe(supervisor, "after", args.python, roots["candidate"], CANDIDATE, env, root)
        require(first == second and first["native"]["sha256"] == native_sha, "native/source/environment changed")
        native_file = Path(first["native"]["module_file"])
        report.update(native=dict(sha256=native_sha, schemas=first["native"]["schemas"]),
                      python_version=first["environment"]["python"], environment=first["environment"])
        report["qualified"] = True
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        try:
            require(supervisor.cleanup_complete, "owned-child cleanup incomplete")
            after = {name: controls.source_snapshot(path, revisions[name], deadline) for name, path in roots.items()}
            write(root / "source-snapshot-after.json", after)
            require(before == after, "source bytes/modes/standing changed")
            if wheel:
                require(sha(wheel) == wheel_sha, "fresh wheel changed")
            if native_file:
                require(sha(native_file) == report["native"]["sha256"], "loaded native binary changed")
            report["source_snapshot_before_sha256"] = sha(root / "source-snapshot-before.json")
            report["source_snapshot_after_sha256"] = sha(root / "source-snapshot-after.json")
            record = inventory(root)
            write(root / "raw-inventory.json", record)
            report["raw_inventory_sha256"] = sha(root / "raw-inventory.json")
            require(time.monotonic() <= deadline, "80-minute builder budget exceeded")
        except Exception as exc:
            report["qualified"] = False
            report["final_identity_error"] = type(exc).__name__ + ": " + str(exc)
        try:
            require(supervisor.cleanup_complete, "cleanup unverified; builder light copies withheld")
            require(copy_build_light(root), "builder lightweight records incomplete")
            report["light_index_sha256"] = sha(root / "light/artifact-index.json")
            require(time.monotonic() <= deadline, "80-minute builder finalization budget exceeded")
        except Exception as exc:
            report["qualified"] = False
            report["light_error"] = type(exc).__name__ + ": " + str(exc)
            (root / "light").mkdir(exist_ok=True)
        report["elapsed_wall_seconds"] = time.monotonic() - started
        write(root / "build-manifest.json", report)
        write(root / "light/build-manifest.json", report)
    summarize(report)
    return 0 if report["qualified"] else 1


def cohort(args):
    root = Path(args.evidence).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for name in ("logs", "probes"):
        (root / name).mkdir()
    source, control = Path(args.source_root).resolve(), SCRIPT.parents[1]
    source_sha, config = SOURCES[args.arm], expected(args.worldgen, args.stage)
    seconds = SMOKE_SECONDS if args.stage == "smoke" else COHORT_SECONDS
    started, deadline = time.monotonic(), time.monotonic() + seconds
    supervisor = Supervisor(root, deadline, seconds // 60)
    report = dict(schema_version=1, kind=KINDS["smoke"] if args.stage == "smoke" else KINDS["cohort"],
        stage=args.stage, arm=args.arm, worldgen=args.worldgen,
        expected=config, source_sha=source_sha, control_sha=os.environ["GITHUB_SHA"],
        github_run_id=os.environ["GITHUB_RUN_ID"], github_run_attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        execution_complete=False, gate_pass=False, gate_exit_code=None, qualified=False, smoke_pass=False,
        identities_stable=False, budget_seconds=seconds)
    before, first, second, manifest, batch, ablation = {}, None, None, None, None, None
    native_file, runner_code = None, None
    try:
        env = activate_environment()
        require(source != control and not root.is_relative_to(source) and not root.is_relative_to(control),
                "source/control/evidence must be separate")
        before = {"source": controls.source_snapshot(source, source_sha, deadline),
                  "control": controls.source_snapshot(control, os.environ["GITHUB_SHA"], deadline)}
        write(root / "source-snapshot-before.json", before)
        manifest_path, wheel = Path(args.build_manifest).resolve(), Path(args.wheel).resolve()
        manifest = bounded_json(manifest_path)
        validate_build(manifest, manifest_path, wheel, args.build_manifest_sha256, args.wheel_sha256)
        require(before["source"]["crate_tree"] == manifest["crate_tree"] and
                sha(source / "uv.lock") == manifest["lock_sha256"] and
                sha(source / "pyproject.toml") == manifest["pyproject_sha256"], "consumer source/build inputs differ")
        shutil.copyfile(manifest_path, root / "build-manifest.json")
        report.update(build_manifest_sha256=sha(manifest_path), wheel_sha256=sha(wheel),
                      native_sha256=manifest["native"]["sha256"])
        supervisor.command("install", ["uv", "pip", "install", "--no-deps", "--python", args.python, str(wheel)], env, root)
        first = inspect_probe(supervisor, "before", args.python, source, source_sha, env, root)
        require(first["native"]["sha256"] == manifest["native"]["sha256"] and
                first["native"]["schemas"] == manifest["native"]["schemas"], "consumer native identity differs")
        require(runtime_signature(first["environment"]) == runtime_signature(manifest["environment"]),
                "consumer runtime environment differs from builder")
        require(first["environment"]["python"] == manifest["python_version"], "Python patch version differs")
        native_file = Path(first["native"]["module_file"])
        supervisor.admission("before_simulation", 20, 6)
        runner_code = supervisor.command("runner", cohort_command(args.python, source, args.worldgen, root / "raw", args.stage),
              dict(env, PYTHONPATH=str(source / "src")), root, allowed_exit_codes=(0, 2))
        second = inspect_probe(supervisor, "after", args.python, source, source_sha, env, root)
        require(first == second, "running source/native/environment identity changed")
        records = {name: bounded_json(root / relative) for name, relative in report_files(args.stage).items()
                   if relative.endswith(".json")}
        run, batch = records["report/run_manifest.json"], records["report/batch_manifest.json"]
        ablation, validation = records["report/ablation_manifest.json"], records["report/validate_report_" + config["profile"] + ".json"]
        decision = records["report/gate_decision_" + config["profile"] + ".json"]
        assessment = validate_records(run, batch, ablation, validation, decision, config, source_sha, report["native_sha256"])
        require(runner_code == assessment["gate_exit_code"], "runner and original decision exit differ")
        write(root / "cohort-assessment.json", assessment)
        report.update(execution_complete=True, gate_pass=assessment["gate_pass"],
                      gate_exit_code=assessment["gate_exit_code"])
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        try:
            require(supervisor.cleanup_complete, "cleanup unverified; final payload inventory withheld")
            after = {"source": controls.source_snapshot(source, source_sha, deadline),
                     "control": controls.source_snapshot(control, os.environ["GITHUB_SHA"], deadline)}
            write(root / "source-snapshot-after.json", after)
            require(before == after, "tracked source bytes/modes/standing changed")
            if native_file:
                require(sha(native_file) == report["native_sha256"], "installed native binary changed")
            if manifest:
                require(sha(Path(args.wheel)) == report["wheel_sha256"] and
                        sha(root / "build-manifest.json") == report["build_manifest_sha256"], "builder artifact changed")
            report["identities_stable"] = first is not None and second is not None and first == second
            record = inventory(root)
            if batch is not None and ablation is not None:
                check_manifest_hashes(root, batch, ablation, record, args.stage)
            write(root / "raw-inventory.json", record)
            report["raw_inventory_sha256"] = sha(root / "raw-inventory.json")
        except Exception as exc:
            report["final_identity_error"] = type(exc).__name__ + ": " + str(exc)
            report["identities_stable"] = False
        provenance = dict(schema_version=1, kind=KINDS["provenance"], stage=args.stage, arm=args.arm, worldgen=args.worldgen,
            source_sha=source_sha, control_sha=os.environ["GITHUB_SHA"],
            github_run_id=os.environ["GITHUB_RUN_ID"], github_run_attempt=os.environ["GITHUB_RUN_ATTEMPT"],
            before=first, after=second, identities_stable=report["identities_stable"],
            source_snapshot_before_sha256=sha(root / "source-snapshot-before.json") if (root / "source-snapshot-before.json").is_file() else None,
            source_snapshot_after_sha256=sha(root / "source-snapshot-after.json") if (root / "source-snapshot-after.json").is_file() else None,
            build_manifest_sha256=report.get("build_manifest_sha256"), wheel_sha256=report.get("wheel_sha256"),
            native_sha256=report.get("native_sha256"), runtime_signature_keys=list(RUNTIME_KEYS),
            retained_platform_note="Full platform/kernel/executable/affinity/image records retained; only declared semantic runtime keys compared across VMs.")
        write(root / "provenance.json", provenance)
        report["provenance_sha256"] = sha(root / "provenance.json")
        write(root / "result.json", report)
        try:
            require(supervisor.cleanup_complete, "cleanup unverified; report copies withheld")
            index = copy_light(root, args.stage)
            report["light_index_sha256"] = sha(root / "light/artifact-index.json")
            require(index["complete"], "required lightweight records missing")
            require(time.monotonic() <= deadline, f"{seconds // 60}-minute aggregate budget exceeded during finalization")
            report.update(outcome_flags(args.stage, report["execution_complete"], report["identities_stable"], report["gate_pass"]))
        except Exception as exc:
            report["qualified"] = report["smoke_pass"] = False
            report["light_error"] = type(exc).__name__ + ": " + str(exc)
            (root / "light").mkdir(exist_ok=True)
        report["elapsed_wall_seconds"] = time.monotonic() - started
        write(root / "result.json", report)
        write(root / "light/result.json", report)
    summarize(report)
    if report["qualified"] or report["smoke_pass"]:
        return 0
    return report["gate_exit_code"] if report["execution_complete"] and report["gate_exit_code"] in (2,) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    builder = modes.add_parser("build")
    for key in ("baseline-root", "candidate-root", "python", "evidence"):
        builder.add_argument("--" + key, required=True)
    worker = modes.add_parser("cohort")
    worker.add_argument("--stage", choices=("smoke", "full"), required=True)
    worker.add_argument("--arm", choices=tuple(SOURCES), required=True)
    worker.add_argument("--worldgen", choices=("template", "procedural"), required=True)
    for key in ("source-root", "python", "build-manifest", "build-manifest-sha256", "wheel", "wheel-sha256", "evidence"):
        worker.add_argument("--" + key, required=True)
    native = modes.add_parser("probe")
    for key in ("source-root", "source-sha", "venv", "out"):
        native.add_argument("--" + key, required=True)
    args = parser.parse_args()
    if args.mode == "probe":
        probe(args)
        return 0
    return build(args) if args.mode == "build" else cohort(args)


if __name__ == "__main__":
    raise SystemExit(main())
