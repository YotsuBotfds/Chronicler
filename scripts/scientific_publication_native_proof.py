#!/usr/bin/env python3
"""Execute the registered bounded mechanical fixture, never a world-benefit gate."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import re
import resource
import subprocess
import sys
import time

SOURCE = "aae7f337be0fc76d40e61662083f50047af7fda6"
PACKAGE = "320316b63413ef814e231bddb42773c54697f000691e08932c86e27bfcae20b4"
NATIVE = "fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317"
ARMS = ("legacy_direct", "legacy_resume", "v2_fork", "v2_direct")
FEATURES = ("health_care", "harvest_forecasts", "ritual_gatherings", "scientific_claims", "transaction_receipts")
SCRIPT = Path(__file__).resolve()
REGISTRATION = SCRIPT.parents[1] / "docs/experiments/scientific-publication-native-composition-2026-10-28.md"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def identity():
    import chronicler_agents  # Capture the actual loaded binary both times.
    from chronicler.batch_manifest import source_identity, native_identity, environment_identity
    return dict(source=source_identity(), native=native_identity(), environment=environment_identity(),
                runner_sha256=sha(SCRIPT), registration_sha256=sha(REGISTRATION))


def controlled(seed, v2):
    from chronicler.world_gen import generate_world
    from chronicler.scholarship_state import ScholarshipState, Seat, ACADEMY
    from chronicler.techniques_state import TechniqueState, TECHNIQUE_INDEX
    from chronicler.scientific_claims import set_scientific_claims_enabled
    from chronicler.utils import sync_civ_population
    world = generate_world(seed=seed, num_regions=8, num_civs=4, worldgen="template")
    world.turn, world.name = 2, "Registered native publication mechanical fixture"
    world.tuning_overrides["climate.trend_share"] = 1.
    world.scholarship = ScholarshipState()
    world.techniques = TechniqueState(initialized_turn=2)
    for ri, region in enumerate(world.regions):
        region.terrain, region.population, region.carrying_capacity = "plains", 60, 1000
        region.resource_types = [0, 5, 255]
        region.resource_base_yields = [1., 1., 0.]
        region.resource_effective_yields = [1., 1., 0.]
        region.resource_reserves = [1., .5, 0.]
        region.ecology.soil, region.ecology.water = .8, .7
        ci = next(i for i, civ in enumerate(world.civilizations) if civ.name == region.controller)
        for recipe in ("irrigation", "masonry"):
            world.techniques.rows.append((ri, TECHNIQUE_INDEX[recipe], .5, -1, 6, ci))
        if ri < 5:
            world.scholarship.seats.append(Seat(region=ri, kind=ACADEMY, name=f"Controlled academy {ri}",
                founded_turn=1, founder=ci, lord=ci, scholars=10.))
    for civ in world.civilizations:
        civ.treasury = 500
        sync_civ_population(civ, world)
    set_scientific_claims_enabled(world, True)
    if v2:
        world.scientific_claims.publication_rule = "funded-context-v2"
    return world


def rng_identity():
    import numpy as np
    state = np.random.get_state()
    return dict(python=digest(random.getstate()), numpy=digest([state[0], state[1].tolist(), *state[2:]]))


def worker(args):
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    import numpy as np
    import chronicler_agents as ca
    from importlib import util
    from importlib.machinery import EXTENSION_SUFFIXES
    from chronicler import main
    from chronicler.models import ActionType
    from chronicler.bundle_codec import load_bundle
    from chronicler.run_checkpoint import read_checkpoint
    from chronicler.expansion_experiment import controls_for_state
    before = identity()
    assert (before["source"]["git_sha"] == SOURCE and before["source"]["package_digest"] == PACKAGE
            and before["native"]["sha256"] == NATIVE)
    assert Path(before["source"]["package_dir"]).resolve() == Path(args.source_root).resolve() / "src/chronicler"
    origin = util.find_spec("chronicler_agents.chronicler_agents").origin
    assert origin.endswith(tuple(EXTENSION_SUFFIXES))
    schemas = {}
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(ca, name)
        assert isinstance(cls, type)
        version, fingerprint, schema = cls.checkpoint_schema()
        schemas[name] = dict(version=version, fingerprint=fingerprint, schema_sha256=hashlib.sha256(schema.encode()).hexdigest())
    out = Path(args.output_root) / f"seed-{args.seed}" / args.arm
    out.mkdir(parents=True, exist_ok=False)
    started, cpu = time.perf_counter(), time.process_time()
    random.seed(314159)
    np.random.seed(314159)
    main.ActionEngine.select_action = lambda *a, **k: ActionType.DEVELOP
    cli = ["--seed", str(args.seed), "--regions", "8", "--civs", "4", "--turns", "16",
           "--agents", "hybrid", "--simulate-only", "--output", str(out / "chronicle.md"),
           "--state", str(out / "state.json"), "--checkpoint-turns", "3,16", "--validation-sidecar",
           "--relationship-stats", "--scholarship", "--techniques", "--grain-reserves", "--contact-ledger"]
    cli += ["--" + name.replace("_", "-") for name in FEATURES]
    run_args = main._build_parser().parse_args(cli)
    request = loaded = world = None
    if args.arm in ("legacy_direct", "v2_direct"):
        world = controlled(args.seed, args.arm == "v2_direct")
    else:
        parent = out.parent / "legacy_direct/checkpoint_turn_3.ckpt"
        loaded = read_checkpoint(parent)
        assert loaded.exact and loaded.state.world.turn == 3
        if args.arm == "v2_fork":
            request = dict(schema_version=1, experiment="native-publication-mechanical", cohort="development",
                feature="scientific_claims", arm="funded_context_v2", fork=True,
                controls={"publication_rule": "funded-context-v2"},
                parent_checkpoint=dict(path=str(parent), sha256=sha(parent)),
                registration=dict(path=str(REGISTRATION), sha256=sha(REGISTRATION)))
    try:
        main.execute_run(run_args, world=world, checkpoint_resume=loaded, expansion_experiment=request)
        rng = rng_identity()
        final = read_checkpoint(out / "checkpoint_turn_16.ckpt")
        world = final.state.world
        assert world.turn == 16 and final.state.agent_bridge is not None
        native_blob = final.state.agent_bridge._sim.checkpoint_state()
        (out / "native-agent-final.bin").write_bytes(native_blob)
        bundle = load_bundle(out / "chronicle_bundle.json")
        state = world.scientific_claims
        summary = dict(seed=args.seed, arm=args.arm, first_source_turn=2, final_turn=world.turn,
            history_turns=[row["turn"] for row in bundle["history"]],
            controls=controls_for_state("scientific_claims", state),
            trial_spent=state.trial_spent, effort_spent=state.effort_spent,
            trials=[trial.model_dump(mode="json") for trial in state.trials],
            receipts=[receipt.model_dump(mode="json") for receipt in state.receipts],
            last_effort=[row.model_dump(mode="json") for row in state.last_effort],
            events=dict(Counter(e.event_type for e in world.events_timeline)),
            feature_sections={name: sum(isinstance(row.get(name), dict) for row in bundle["history"]) for name in FEATURES},
            native_agent_final_sha256=hashlib.sha256(native_blob).hexdigest(), rng=rng,
            checkpoint_sections=[row["name"] for row in final.header["sections"]], schemas=schemas)
        write(out / "mechanical-summary.json", summary)
    finally:
        after = identity()
        write(out / "worker-identity.json", dict(before=before, after=after, identities_stable=before == after,
            seconds=time.perf_counter()-started, process_cpu_seconds=time.process_time()-cpu))
        assert before == after


def files(folder, *, after=3):
    result = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix == ".ckpt" or path.name in (
                "mechanical-summary.json", "worker-identity.json", "native-agent-final.bin"):
            continue
        match = re.search(r"_turn_(\d+)\.json$", path.name)
        if match and int(match[1]) <= after:
            continue
        result[path.relative_to(folder).as_posix()] = path
    return result


def compare(a, b, *, v2=False):
    from chronicler.bundle_codec import load_bundle
    left, right = files(a), files(b)
    result = dict(file_set_equal=left.keys() == right.keys(), files_compared=len(left), differences=[])
    for name in sorted(left.keys() & right.keys()):
        if name == "chronicle_bundle.json":
            x, y = load_bundle(left[name]), load_bundle(right[name])
            if v2:
                x = {key: x[key] for key in ("world_state", "history", "events_timeline")}
                y = {key: y[key] for key in ("world_state", "history", "events_timeline")}
                x["history"] = [row for row in x["history"] if row["turn"] >= 4]
                y["history"] = [row for row in y["history"] if row["turn"] >= 4]
            else:
                x["metadata"].pop("generated_at", None)
                y["metadata"].pop("generated_at", None)
            equal = x == y
        else:
            equal = left[name].read_bytes() == right[name].read_bytes()
        if not equal:
            result["differences"].append(name)
    x, y = (json.loads((folder / "mechanical-summary.json").read_text()) for folder in (a, b))
    result.update(native_agent_equal=x["native_agent_final_sha256"] == y["native_agent_final_sha256"],
                  rng_equal=x["rng"] == y["rng"])
    return result


def orchestrate(args):
    from chronicler.run_checkpoint import read_checkpoint
    root = Path(args.output_root)
    root.mkdir(parents=True, exist_ok=False)
    before = identity()
    write(root / "freeze.json", before)
    runs = []
    for seed in (42, 7):
        for arm in ARMS:
            log = root / f"seed-{seed}-{arm}.log"
            used = resource.getrusage(resource.RUSAGE_CHILDREN)
            if used.ru_utime + used.ru_stime >= 90:
                runs.append(dict(seed=seed, arm=arm, status="budget_censored"))
                continue
            command = [sys.executable, "-B", str(SCRIPT), "--source-root", args.source_root,
                       "--output-root", args.output_root, "--seed", str(seed), "--arm", arm]
            with log.open("w") as stream:
                try:
                    completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=60)
                    status = "complete" if completed.returncode == 0 else "failed"
                    row = dict(seed=seed, arm=arm, status=status, returncode=completed.returncode)
                except subprocess.TimeoutExpired:
                    row = dict(seed=seed, arm=arm, status="wall_timeout_censored")
            runs.append(row)
            write(root / "progress.json", runs)
            print(json.dumps(row), flush=True)
    comparisons = []
    for seed in (42, 7):
        folder = root / f"seed-{seed}"
        if all(row["status"] == "complete" for row in runs if row["seed"] == seed):
            comparisons.append(dict(seed=seed, legacy_resume=compare(folder / "legacy_direct", folder / "legacy_resume"),
                direct_v2_vs_fork=compare(folder / "v2_direct", folder / "v2_fork", v2=True)))
            a = read_checkpoint(folder / "legacy_direct/checkpoint_turn_3.ckpt")
            b = read_checkpoint(folder / "v2_direct/checkpoint_turn_3.ckpt")
            x, y = a.state.world.model_dump(mode="json"), b.state.world.model_dump(mode="json")
            y["scientific_claims"].pop("publication_rule")
            comparisons[-1]["direct_parent_boundary"] = dict(world_equal_except_rule=x == y,
                native_agent_equal=a.state.agent_bridge._sim.checkpoint_state() == b.state.agent_bridge._sim.checkpoint_state(),
                legacy_controls=a.header["flags"], v2_controls=b.header["flags"])
    after = identity()
    used = resource.getrusage(resource.RUSAGE_CHILDREN)
    report = dict(protocol_sha256=sha(REGISTRATION), source_freeze=before, after=after,
        identities_stable=before == after, worker_cpu_seconds=used.ru_utime+used.ru_stime,
        runs=runs, comparisons=comparisons,
        files={str(path.relative_to(root)): sha(path) for path in sorted(root.rglob("*")) if path.is_file()})
    write(root / "report.json", report)
    print(json.dumps(dict(comparisons=comparisons, worker_cpu_seconds=report["worker_cpu_seconds"])), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--seed", type=int, choices=(42, 7))
    parser.add_argument("--arm", choices=ARMS)
    options = parser.parse_args()
    worker(options) if options.arm else orchestrate(options)
