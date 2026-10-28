#!/usr/bin/env python3
"""Run registered expansion controls from shared parent checkpoints.

This writes evidence, not a gate verdict. Each seed first runs through normal
fresh-world configuration to the fork boundary, then each arm restores that
same checkpoint with an explicitly recorded intervention. Each worker is a
fresh process; worker count and native thread budgets are bounded separately.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = ROOT
_LOADED_SOURCE = False


def _load_source(root):
    """Select simulation code before importing it; never mix loaded packages."""
    global _SOURCE_ROOT, _LOADED_SOURCE, atomic_write_json, strict_json_loads, THREAD_ENV_VARS
    global check_batch_destination, environment_identity, file_sha256, native_identity, source_identity
    global CONTROL_FIELDS, SCHEMA_VERSION, allowed_control_fields, RESEARCH_CONFIGURATION_SUPPORTED
    root = Path(root).resolve()
    if _LOADED_SOURCE and root == _SOURCE_ROOT:
        return
    package = root / "src" / "chronicler"
    if not (package / "main.py").is_file():
        raise ValueError("--source-root must contain src/chronicler/main.py")
    existing = sys.modules.get("chronicler")
    if existing is not None and Path(existing.__file__).parent.resolve() != package:
        raise ValueError("a different Chronicler source is already imported; use a fresh runner process")
    sys.path.insert(0, str(root / "src"))
    from chronicler.artifact_io import atomic_write_json, strict_json_loads
    from chronicler.batch_manifest import (
        THREAD_ENV_VARS, check_batch_destination, environment_identity, file_sha256,
        native_identity, source_identity,
    )
    from chronicler.expansion_experiment import CONTROL_FIELDS, SCHEMA_VERSION
    from chronicler import expansion_experiment as source_experiment
    RESEARCH_CONFIGURATION_SUPPORTED = hasattr(source_experiment, "allowed_control_fields")
    allowed_control_fields = getattr(source_experiment, "allowed_control_fields",
                                    lambda feature: set(CONTROL_FIELDS[feature]))
    _SOURCE_ROOT = root
    _LOADED_SOURCE = True

MANIFEST = "expansion_experiment_manifest.json"
WORKER_IDENTITY_SCHEMA_VERSION = 2
ARMS = {
    "harvest_forecasts": {"normal": {"policy": "normal"}, "withheld": {"policy": "withhold"},
                          "shuffled": {"policy": "shuffle"}},
    "ritual_gatherings": {"normal": {"contact_enabled": True, "bonds_enabled": True},
                          "no_contact": {"contact_enabled": False, "bonds_enabled": True},
                          "no_bonds": {"contact_enabled": True, "bonds_enabled": False},
                          "cost_only": {"contact_enabled": False, "bonds_enabled": False}},
    "health_care": {"care": {"care_enabled": True}, "no_care": {"care_enabled": False}},
    "scientific_claims": {
        "normal": {"withhold_information": False, "transmission_enabled": True, "uninformative_tests": False},
        "withheld": {"withhold_information": True, "transmission_enabled": True, "uninformative_tests": False},
        "no_transmission": {"withhold_information": False, "transmission_enabled": False, "uninformative_tests": False},
        "uninformative": {"withhold_information": False, "transmission_enabled": True, "uninformative_tests": True},
    },
}


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _positive(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_seeds(text):
    seeds = []
    for part in text.split(","):
        if not re.fullmatch(r"\d+(?:-\d+)?", part):
            raise ValueError("seeds must be nonnegative integers or inclusive ranges")
        ends = [int(value) for value in part.split("-")]
        first, last = ends[0], ends[-1]
        if last < first or last - first > 100_000:
            raise ValueError("invalid or excessive seed range")
        seeds.extend(range(first, last + 1))
    if len(set(seeds)) != len(seeds):
        raise ValueError("duplicate seeds are not independent replicates")
    return sorted(seeds)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--source-root", type=Path, default=ROOT,
                        help="immutable simulation checkout, selected before imports")
    parser.add_argument("--feature", choices=tuple(ARMS))
    parser.add_argument("--cohort", choices=("development", "confirmatory"))
    parser.add_argument("--name", default="expansion")
    parser.add_argument("--seeds", help="inclusive ranges and/or comma-separated seeds")
    parser.add_argument("--turns", type=_positive)
    parser.add_argument("--fork-turn", type=_positive, default=4)
    parser.add_argument("--arms", help="comma-separated registered arm names; default all")
    parser.add_argument("--controls", type=Path, help="JSON object of shared source-owned control overrides")
    parser.add_argument("--scientific-research-agendas", action=argparse.BooleanOptionalAction, default=None,
                        help="initial finite research policy in the shared science parent; resumes inherit it")
    parser.add_argument("--registration", type=Path, help="frozen preregistration file; required for confirmatory")
    parser.add_argument("--worldgen", choices=("template", "procedural"), default="template")
    parser.add_argument("--regions", type=_positive)
    parser.add_argument("--civs", type=_positive)
    parser.add_argument("--workers", type=_positive, default=1)
    parser.add_argument("--output-root", type=Path)
    return parser


def _simulation_args(seed, turns, path, config, *, resume=None, checkpoint=None):
    args = ["--seed", str(seed), "--turns", str(turns), "--simulate-only", "--agents", "hybrid",
            "--regions", str(config["regions"]), "--civs", str(config["civs"]),
            "--worldgen", config["worldgen"], "--validation-sidecar",
            "--output", str(path / "chronicle.md"), "--state", str(path / "state.json"),
            "--" + config["feature"].replace("_", "-")]
    if config["feature"] == "harvest_forecasts":
        args.extend(["--grain-reserves", "--contact-ledger"])
    elif config["feature"] == "scientific_claims":
        args.extend(["--scholarship", "--techniques"])
    if resume is None and config.get("scientific_research_agendas") is not None:
        args.append("--" + ("" if config["scientific_research_agendas"] else "no-") + "scientific-research-agendas")
    if resume is not None:
        args.extend(["--resume", str(resume)])
    if checkpoint is not None:
        args.extend(["--checkpoint-turns", str(checkpoint)])
    return args


def run_job(path: Path):
    """The real simulation worker; no fabricated outcome/report fallback."""
    job = strict_json_loads(path.read_text(), label="experiment job")
    if Path(job["source_root"]).resolve() != _SOURCE_ROOT:
        raise ValueError("worker job source root differs from the selected simulation source")
    from chronicler.main import _adopt_checkpoint_args, _build_parser, execute_run
    parser = _build_parser()
    args = parser.parse_args(job["simulation_args"])
    before = {"source": source_identity(), "native": native_identity(), "environment": environment_identity()}
    runner_before = file_sha256(Path(__file__))
    # No supplied world: normal fresh-world defaults must run before controls.
    try:
        checkpoint = None
        if args.resume:
            parent = job["request"].get("parent_checkpoint")
            if (not isinstance(parent, dict) or not isinstance(parent.get("path"), str)
                    or Path(parent["path"]).resolve() != Path(args.resume).resolve()):
                raise ValueError("experiment request parent differs from the checkpoint being resumed")
            from chronicler.run_checkpoint import read_checkpoint
            checkpoint = read_checkpoint(Path(args.resume))
            conflicts = _adopt_checkpoint_args(parser, args, checkpoint)
            if conflicts:
                raise ValueError("; ".join(conflicts))
        execute_run(args, checkpoint_resume=checkpoint, expansion_experiment=job["request"])
    finally:
        after = {"source": source_identity(), "native": native_identity(), "environment": environment_identity()}
        runner_after = file_sha256(Path(__file__))
        environment_stable = before["environment"] == after["environment"]
        stable = (_identity_key(before) == _identity_key(after) and environment_stable
                  and runner_before == runner_after)
        atomic_write_json(path.parent / "worker_identity.json", {
            "schema_version": WORKER_IDENTITY_SCHEMA_VERSION,
            "before": before, "after": after,
            "environment_stable": environment_stable, "identities_stable": stable,
            "runner_sha256": runner_before, "runner_sha256_after": runner_after,
        })
    if not stable:
        raise RuntimeError("source/native/worker environment or external runner identity changed during a simulation worker")


def _identity_key(receipt):
    source, native = receipt["source"], receipt["native"]
    return (source.get("git_sha"), source.get("package_digest"),
            native.get("status"), native.get("sha256"))


def _verify_worker_identity(path, simulation_receipt):
    """Verify actual child observations; the orchestration environment differs.

    Never infer an old worker's environment from a checkpoint or the parent
    process. Older evidence remains readable by its own producer contract.
    """
    worker = strict_json_loads(path.read_text(), label="worker identity")
    if (not isinstance(worker, dict) or worker.get("schema_version") != WORKER_IDENTITY_SCHEMA_VERSION
            or worker.get("environment_stable") is not True or worker.get("identities_stable") is not True):
        raise RuntimeError("worker identity receipt is missing, unsupported or unstable")
    before, after = worker.get("before"), worker.get("after")
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or not isinstance(before.get("environment"), dict) or not before["environment"]
            or not isinstance(after.get("environment"), dict) or not after["environment"]
            or not all(isinstance(row.get(key), dict) for row in (before, after) for key in ("source", "native"))):
        raise RuntimeError("worker identity receipt lacks actual source/native/environment observations")
    if (before["environment"] != after["environment"]
            or _identity_key(before) != _identity_key(after)
            or _identity_key(before) != _identity_key(simulation_receipt)
            or worker.get("runner_sha256") != file_sha256(Path(__file__))
            or worker.get("runner_sha256_after") != worker.get("runner_sha256")):
        raise RuntimeError("worker source/native/environment or external runner identity differs")
    return worker


def _worker_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_SOURCE_ROOT / "src")
    env["PYTHONHASHSEED"] = "0"
    for name in ("RAYON_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"):
        env[name] = "1"
    return env


def _inventory(path):
    files = {}
    for file in sorted(path.rglob("*")):
        if file.is_symlink():
            raise ValueError(f"unexpected link in experiment output: {file}")
        if file.is_file():
            files[str(file.relative_to(path))] = file_sha256(file)
    return files


def _execute(path, seed, horizon, args, request, env):
    path.mkdir(parents=True, exist_ok=False)
    job_path = path / "job.json"
    atomic_write_json(job_path, {"source_root": str(_SOURCE_ROOT), "simulation_args": args, "request": request})
    command = [sys.executable, str(Path(__file__).resolve()), "--source-root", str(_SOURCE_ROOT),
               "--job", str(job_path)]
    started = time.perf_counter()
    record = {"seed": seed, "arm": request["arm"], "directory": str(path),
              "requested_horizon": horizon, "command": command, "simulation_args": args,
              "request": request, "status": "failed"}
    try:
        with (path / "worker.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=_SOURCE_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        record["returncode"] = result.returncode
        if result.returncode != 0:
            raise RuntimeError(f"simulation worker exited {result.returncode}; see worker.log")
        bundle = strict_json_loads((path / "chronicle_bundle.json").read_text(), label="simulation bundle")
        completed = bundle.get("world_state", {}).get("turn")
        record["completed_horizon"] = completed
        if completed != horizon or bundle.get("metadata", {}).get("seed") != seed:
            raise RuntimeError("simulation ended before the registered horizon or with a different seed")
        receipt = bundle.get("metadata", {}).get("expansion_experiment")
        if (not isinstance(receipt, dict) or receipt.get("arm") != request["arm"]
                or receipt.get("feature") != request["feature"]
                or not isinstance(receipt.get("controls_after"), dict)
                or set(receipt["controls_after"]) != set(CONTROL_FIELDS[request["feature"]])):
            raise RuntimeError("simulation bundle has no matching experiment receipt")
        _verify_worker_identity(path / "worker_identity.json", receipt)
        record["receipt"] = receipt
        record["worker_identity_verified"] = True
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
    record["seconds"] = time.perf_counter() - started
    try:
        record["files"] = _inventory(path)
    except Exception as exc:
        record.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
    return record


def _seed_runs(seed, root, config, env):
    feature = config["feature"]
    common = {"schema_version": SCHEMA_VERSION, "experiment": config["name"],
              "cohort": config["cohort"], "feature": feature, "registration": config["registration"]}
    parent_dir = root / f"seed_{seed}" / "parent"
    parent_request = dict(common, arm="parent", controls=config["controls"], fork=False)
    # Run the normal parent through the final horizon, retaining an earlier
    # checkpoint. Stopping it at the fork would force final-turn settlement
    # detection there and change the otherwise ordinary shared prefix.
    parent = _execute(parent_dir, seed, config["turns"], _simulation_args(
        seed, config["turns"], parent_dir, config, checkpoint=config["fork_turn"]), parent_request, env)
    records = [parent]
    if parent["status"] != "complete":
        return records
    from chronicler.ablation_arms import CHECKPOINT_TURN_FILENAME
    checkpoint = parent_dir / CHECKPOINT_TURN_FILENAME.format(turn=config["fork_turn"])
    if not checkpoint.is_file():
        parent.update(status="failed", error={"type": "RuntimeError", "message": "parent checkpoint missing"})
        return records
    parent_identity = {"path": str(checkpoint), "sha256": file_sha256(checkpoint)}
    for arm in config["arms"]:
        directory = root / f"seed_{seed}" / arm
        controls = {**config["controls"], **ARMS[feature][arm]}
        request = dict(common, arm=arm, controls=controls, fork=True, parent_checkpoint=parent_identity)
        row = _execute(directory, seed, config["turns"], _simulation_args(
            seed, config["turns"], directory, config, resume=checkpoint), request, env)
        parent_controls = parent.get("receipt", {}).get("controls_after")
        research_policy = row.get("receipt", {}).get("research_policy")
        research_unchanged = research_policy is None or research_policy["before"] == research_policy["after"]
        if (row["status"] == "complete" and research_unchanged and isinstance(parent_controls, dict)
                and row["receipt"]["controls_after"] == parent_controls):
            equal = (row["files"].get("state.json") is not None
                     and row["files"].get("state.json") == parent["files"].get("state.json"))
            row["no_op_parent_state_identity"] = equal
            if not equal:
                row.update(status="failed", error={"type": "RuntimeError",
                           "message": "no-op control fork differs from the full parent final state"})
        records.append(row)
    return records


def run_experiment(args):
    _load_source(args.source_root)
    for name in ("feature", "cohort", "seeds", "turns", "output_root"):
        if getattr(args, name) is None:
            raise ValueError(f"--{name.replace('_', '-')} is required")
    if args.feature not in CONTROL_FIELDS:
        raise ValueError("selected simulation source does not register this experiment feature")
    if args.scientific_research_agendas is not None and (
            args.feature != "scientific_claims" or not RESEARCH_CONFIGURATION_SUPPORTED):
        raise ValueError("initial research policy requires science and a source supporting finite research")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.name):
        raise ValueError("experiment name must be a bounded plain identifier")
    if args.turns <= args.fork_turn:
        raise ValueError("--turns must extend past --fork-turn")
    seeds = parse_seeds(args.seeds)
    arms = list(ARMS[args.feature]) if args.arms is None else args.arms.split(",")
    if not arms or len(set(arms)) != len(arms) or any(arm not in ARMS[args.feature] for arm in arms):
        raise ValueError("unknown or duplicate experiment arms")
    controls = {} if args.controls is None else strict_json_loads(args.controls.read_text(), label="controls")
    if not isinstance(controls, dict) or set(controls) - allowed_control_fields(args.feature):
        raise ValueError("unknown shared experiment controls")
    # Arm-defining controls are fixed by their names, not silently overridden.
    arm_fields = set().union(*(set(row) for row in ARMS[args.feature].values()))
    if set(controls) & arm_fields:
        raise ValueError("shared controls cannot override arm-defining controls")
    registration = None
    if args.registration is not None:
        registration = {"path": str(args.registration.resolve()), "sha256": file_sha256(args.registration)}
    if args.cohort == "confirmatory" and registration is None:
        raise ValueError("confirmatory experiments require --registration")
    config = {"name": args.name, "feature": args.feature, "cohort": args.cohort,
              "seeds": seeds, "turns": args.turns, "fork_turn": args.fork_turn,
              "arms": arms, "controls": controls, "registration": registration,
              "worldgen": args.worldgen, "regions": args.regions or (32 if args.worldgen == "procedural" else 8),
              "civs": args.civs or (10 if args.worldgen == "procedural" else 4)}
    if args.scientific_research_agendas is not None:
        config["scientific_research_agendas"] = args.scientific_research_agendas
    root = args.output_root.resolve()
    check_batch_destination(root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        with (root / MANIFEST).open("x", encoding="utf-8"):
            pass
    except FileExistsError as exc:
        raise ValueError("experiment destination was claimed concurrently") from exc
    env = _worker_env()
    source_before, native_before = source_identity(), native_identity()
    manifest = {"kind": "chronicler-expansion-experiment", "schema_version": 1, "status": "running",
                "worker_identity_schema_version": WORKER_IDENTITY_SCHEMA_VERSION,
                "started_at": _utc(), "config": config, "workers": min(args.workers, len(seeds)),
                "source_root": str(_SOURCE_ROOT), "source": source_before, "native": native_before,
                "environment": environment_identity(),
                "worker_thread_environment": {name: env.get(name) for name in THREAD_ENV_VARS},
                "runner_sha256": file_sha256(Path(__file__)), "runs": []}
    atomic_write_json(root / MANIFEST, manifest)
    with ThreadPoolExecutor(max_workers=manifest["workers"]) as pool:
        futures = {pool.submit(_seed_runs, seed, root, config, env): seed for seed in seeds}
        for future in as_completed(futures):
            try:
                manifest["runs"].extend(future.result())
            except Exception as exc:
                manifest["runs"].append({"seed": futures[future], "status": "failed",
                                         "error": {"type": type(exc).__name__, "message": str(exc)}})
            manifest["runs"].sort(key=lambda row: (row["seed"], row.get("arm", "")))
            atomic_write_json(root / MANIFEST, manifest)
            print(f"seed {futures[future]} completed; evidence: {root / MANIFEST}", flush=True)
    manifest["finished_at"] = _utc()
    manifest["source_after"] = source_identity()
    manifest["native_after"] = native_identity()
    manifest["runner_sha256_after"] = file_sha256(Path(__file__))
    identity_before = {"source": source_before, "native": native_before}
    stable = (manifest["runner_sha256_after"] == manifest["runner_sha256"]
              and _identity_key(manifest) == _identity_key(
                  {"source": manifest["source_after"], "native": manifest["native_after"]}))
    for row in manifest["runs"]:
        if row["status"] == "complete" and _identity_key(row["receipt"]) != _identity_key(identity_before):
            row.update(status="failed", error={"type": "RuntimeError",
                       "message": "worker receipt source/native identity differs from the experiment"})
            stable = False
    manifest["identities_stable"] = stable
    expected = len(seeds) * (1 + len(arms))
    manifest["status"] = ("complete" if stable and len(manifest["runs"]) == expected
                          and all(row["status"] == "complete" for row in manifest["runs"]) else "failed")
    atomic_write_json(root / MANIFEST, manifest)
    return manifest


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _load_source(args.source_root)
        if args.job is not None:
            run_job(args.job)
            return 0
        manifest = run_experiment(args)
        return 0 if manifest["status"] == "complete" else 1
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
