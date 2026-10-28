#!/usr/bin/env python3
"""Registered six-worker mechanical proof; never a natural-world benefit gate."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

SCRIPT = Path(__file__).resolve()
HELPER = SCRIPT.with_name("scientific_publication_native_proof.py")
REGISTRATION = SCRIPT.parents[1] / "docs/experiments/scientific-research-native-composition-2026-10-28.md"
NATIVE = "fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317"
FEATURES = ("health_care", "harvest_forecasts", "ritual_gatherings", "scientific_claims", "transaction_receipts")
ARMS = ("finite_direct", "finite_resume", "paused_fork")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def helper():
    spec = importlib.util.spec_from_file_location("registered_publication_fixture", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity():
    import chronicler_agents as native
    from importlib.machinery import EXTENSION_SUFFIXES
    from chronicler.batch_manifest import source_identity, native_identity, environment_identity
    origin = importlib.util.find_spec("chronicler_agents.chronicler_agents").origin
    if not origin.endswith(tuple(EXTENSION_SUFFIXES)):
        raise ValueError("native runtime is not an actual compiled extension")
    classes = {}
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(native, name)
        if not isinstance(cls, type):
            raise ValueError("native simulator is not a real class")
        version, fingerprint, schema = cls.checkpoint_schema()
        classes[name] = dict(module=cls.__module__, name=cls.__qualname__, version=version,
            fingerprint=fingerprint, schema_sha256=hashlib.sha256(schema.encode()).hexdigest())
    result = dict(source=source_identity(), native=native_identity(), environment=environment_identity(),
        compiled_origin=origin, compiled_classes=classes, runner_sha256=sha(SCRIPT),
        helper_sha256=sha(HELPER), registration_sha256=sha(REGISTRATION))
    if result["native"]["sha256"] != NATIVE:
        raise ValueError("actual native binary differs from registered receipt runtime")
    return result


def assert_frozen(args):
    expected = json.loads(Path(args.freeze).read_text())
    actual = identity()
    if expected != actual or Path(actual["source"]["package_dir"]).resolve() != Path(args.source_root).resolve() / "src/chronicler":
        raise ValueError("actual source/native/environment/observer differs from prospective freeze")
    return actual


def controlled(seed):
    world = helper().controlled(seed, True)
    world.name = "Registered finite research native mechanical fixture"
    return world


def cli(folder, seed):
    return ["--seed", str(seed), "--regions", "8", "--civs", "4", "--turns", "29",
        "--agents", "hybrid", "--simulate-only", "--output", str(folder / "chronicle.md"),
        "--state", str(folder / "state.json"), "--checkpoint-turns", "27,29",
        "--validation-sidecar", "--relationship-stats", "--scholarship", "--techniques",
        "--grain-reserves", "--contact-ledger", "--scientific-research-agendas",
        *["--" + name.replace("_", "-") for name in FEATURES]]


def preflight(seed):
    from chronicler.main import _build_parser
    from chronicler.expansion_features import configure_expansion_features, expansion_feature_flags
    from chronicler.grain_reserves import set_grain_reserves_enabled
    from chronicler.contact_ledger import set_contact_ledger_enabled
    from chronicler.scientific_research import validate_state
    from chronicler.techniques_state import TECHNIQUE_INDEX
    world = controlled(seed)
    set_grain_reserves_enabled(world, True)
    set_contact_ledger_enabled(world, True)
    configure_expansion_features(world, _build_parser().parse_args(cli(Path("unused"), seed)), agent_mode="hybrid")
    validate_state(world)
    seats = []
    for index, seat in enumerate(world.scholarship.seats):
        owner = next((i for i, civ in enumerate(world.civilizations)
                      if civ.name == world.regions[seat.region].controller), -1)
        assert owner >= 0 and seat.founder == owner and seat.kind == 0 and seat.founded_turn == 1
        rows = [list(row) for row in world.techniques.rows if row[0] == seat.region]
        assert all(any(row[1] == TECHNIQUE_INDEX[recipe] and row[2] == .5 for row in rows)
                   for recipe in ("irrigation", "masonry"))
        seats.append(dict(seat=index, region=seat.region, owner=owner, birth=seat.model_dump(), practice_rows=rows))
    assert len(seats) <= 5 and world.turn == 2
    flags = expansion_feature_flags(world)
    assert all(flags[name] for name in (*FEATURES, "scientific_research_agendas"))
    assert world.scientific_claims.publication_rule == "funded-context-v2"
    return dict(seed=seed, actual_academy_count=len(seats), academies=seats, flags=flags,
        host_seal=world.scientific_claims.research_agendas.host_seal, source_turn=2,
        research=world.scientific_claims.research_agendas.model_dump())


def checkpoint_identity(loaded):
    state = loaded.state
    return dict(turn=state.world.turn, exact=loaded.header["exact"], flags=loaded.header["flags"],
        world_sha256=digest(state.world.model_dump(mode="json")),
        history_sha256=digest([row.model_dump(mode="json") for row in state.history]),
        events_sha256=digest([row.model_dump(mode="json") for row in state.world.events_timeline]),
        research=state.world.scientific_claims.research_agendas.model_dump(mode="json"),
        native_agent_sha256=hashlib.sha256(state.agent_bridge._sim.checkpoint_state()).hexdigest())


def worker(args):
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    import numpy as np
    from chronicler import main
    from chronicler.models import ActionType
    from chronicler.run_checkpoint import read_checkpoint
    from chronicler.expansion_experiment import controls_for_state
    from chronicler.bundle_codec import load_bundle
    before = assert_frozen(args)
    folder = Path(args.output_root) / f"seed-{args.seed}" / args.arm
    folder.mkdir(parents=True, exist_ok=False)
    started, cpu = time.perf_counter(), time.process_time()
    random.seed(314159)
    np.random.seed(314159)
    main.ActionEngine.select_action = lambda *a, **k: ActionType.DEVELOP
    run_args = main._build_parser().parse_args(cli(folder, args.seed))
    loaded = request = world = parent_at_restore = None
    if args.arm == "finite_direct":
        world = controlled(args.seed)
    else:
        parent = folder.parent / "finite_direct/checkpoint_turn_27.ckpt"
        loaded = read_checkpoint(parent)
        assert loaded.exact and loaded.state.world.turn == 27
        parent_at_restore = checkpoint_identity(loaded)
        conflicts = main._adopt_checkpoint_args(main._build_parser(), run_args, loaded)
        assert not conflicts, conflicts
        if args.arm == "paused_fork":
            request = dict(schema_version=1, experiment="native-finite-research-mechanical", cohort="development",
                feature="scientific_claims", arm="pause", fork=True, controls={"research_enabled": False},
                parent_checkpoint=dict(path=str(parent), sha256=sha(parent)),
                registration=dict(path=str(REGISTRATION), sha256=sha(REGISTRATION)))
    try:
        main.execute_run(run_args, world=world, checkpoint_resume=loaded, expansion_experiment=request)
        rng = helper().rng_identity()
        final = read_checkpoint(folder / "checkpoint_turn_29.ckpt")
        world, state = final.state.world, final.state.world.scientific_claims
        assert world.turn == 29 and final.state.agent_bridge is not None
        assert final.header["exact"] is (args.arm != "paused_fork")
        assert final.header["flags"]["scientific_research_agendas"] is (args.arm != "paused_fork")
        blob = final.state.agent_bridge._sim.checkpoint_state()
        (folder / "native-agent-final.bin").write_bytes(blob)
        pools = []
        for section, runtime, attribute in (("agent_bridge", final.state.agent_bridge, "_sim"),
                ("ecology_runtime", final.state.ecology_runtime, "sim"),
                ("politics_runtime", final.state.politics_runtime, "sim")):
            if runtime is not None:
                simulator = getattr(runtime, attribute)
                pools.append(dict(section=section, module=type(simulator).__module__, name=type(simulator).__qualname__))
        bundle = load_bundle(folder / "chronicle_bundle.json")
        write(folder / "mechanical-summary.json", dict(seed=args.seed, arm=args.arm,
            first_source_turn=2, final_turn=29, history_turns=[row["turn"] for row in bundle["history"]],
            parent_at_restore=parent_at_restore, final_checkpoint=checkpoint_identity(final),
            controls=controls_for_state("scientific_claims", state), science=state.model_dump(mode="json"),
            events=dict(Counter(e.event_type for e in world.events_timeline)),
            feature_sections={name: sum(isinstance(row.get(name), dict) for row in bundle["history"]) for name in FEATURES},
            active_native_pools=pools, native_agent_final_sha256=hashlib.sha256(blob).hexdigest(), rng=rng,
            resume_metadata=bundle["metadata"].get("resume"),
            experiment_receipt=bundle["metadata"].get("expansion_experiment"),
            effective_simulation_args=final.state.run_config["simulation_args"]))
    finally:
        after = assert_frozen(args)
        write(folder / "worker-identity.json", dict(before=before, after=after, identities_stable=before == after,
            seconds=time.perf_counter() - started, process_cpu_seconds=time.process_time() - cpu))


def compare(left, right):
    from chronicler.bundle_codec import load_bundle
    a, b = (helper().files(folder, after=27) for folder in (left, right))
    comparisons = {}
    for name in sorted(a.keys() & b.keys()):
        if name == "chronicle_bundle.json":
            x, y = load_bundle(a[name]), load_bundle(b[name])
            x["metadata"].pop("generated_at", None)
            y["metadata"].pop("generated_at", None)
            equal = x == y
        else:
            equal = a[name].read_bytes() == b[name].read_bytes()
        comparisons[name] = equal
    x, y = (json.loads((folder / "mechanical-summary.json").read_text()) for folder in (left, right))
    return dict(left_files=sorted(a), right_files=sorted(b), file_set_equal=a.keys() == b.keys(),
        files=comparisons, native_agent_equal=x["native_agent_final_sha256"] == y["native_agent_final_sha256"],
        rng_equal=x["rng"] == y["rng"])


def orchestrate(args):
    from chronicler.run_checkpoint import read_checkpoint
    before = assert_frozen(args)
    root = Path(args.output_root)
    root.mkdir(parents=True, exist_ok=False)
    write(root / "freeze.json", before)
    try:
        write(root / "fixture-preflight.json", [preflight(seed) for seed in (42, 7)])
    except Exception as exc:
        write(root / "fixture-preflight-failure.json", dict(type=type(exc).__name__, message=str(exc)))
        raise
    runs, halted = [], False
    for seed in (42, 7):
        for arm in ARMS:
            used = resource.getrusage(resource.RUSAGE_CHILDREN)
            if halted or used.ru_utime + used.ru_stime + 12 > 60:
                runs.append(dict(seed=seed, arm=arm, status="not_attempted_after_failure" if halted else "budget_censored"))
                continue
            command = [sys.executable, "-B", str(SCRIPT), "--source-root", args.source_root,
                "--freeze", args.freeze, "--output-root", args.output_root, "--seed", str(seed), "--arm", arm]
            with (root / f"seed-{seed}-{arm}.log").open("x") as stream:
                try:
                    completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
                    row = dict(seed=seed, arm=arm, returncode=completed.returncode,
                               status="complete" if completed.returncode == 0 else "failed")
                except subprocess.TimeoutExpired:
                    row = dict(seed=seed, arm=arm, status="wall_timeout_censored")
            runs.append(row)
            halted = row["status"] != "complete"
            write(root / f"progress-{len(runs)}.json", runs)
            print(json.dumps(row), flush=True)
    comparisons = []
    for seed in (42, 7):
        if all(row["status"] == "complete" for row in runs if row["seed"] == seed):
            folder = root / f"seed-{seed}"
            parent = checkpoint_identity(read_checkpoint(folder / "finite_direct/checkpoint_turn_27.ckpt"))
            restores = {arm: json.loads((folder / arm / "mechanical-summary.json").read_text())["parent_at_restore"]
                        for arm in ARMS[1:]}
            comparisons.append(dict(seed=seed, exact_resume=compare(folder / "finite_direct", folder / "finite_resume"),
                original_parent=parent, actual_restores=restores, shared_parent_equal=all(value == parent for value in restores.values())))
    used = resource.getrusage(resource.RUSAGE_CHILDREN)
    after = assert_frozen(args)
    write(root / "report.json", dict(protocol_sha256=sha(REGISTRATION), freeze_sha256=sha(args.freeze),
        source_freeze=before, after=after, identities_stable=before == after,
        worker_cpu_seconds=used.ru_utime + used.ru_stime, runs=runs, comparisons=comparisons,
        files={str(path.relative_to(root)): sha(path) for path in sorted(root.rglob("*")) if path.is_file()}))
    return all(row["status"] == "complete" for row in runs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--record-freeze", action="store_true")
    parser.add_argument("--output-root")
    parser.add_argument("--seed", type=int, choices=(42, 7))
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    if "chronicler" in sys.modules:
        raise ValueError("select a fresh interpreter before importing simulation source")
    sys.path.insert(0, str(Path(args.source_root).resolve() / "src"))
    if args.record_freeze:
        write(args.freeze, identity())
        return 0
    if not args.output_root:
        parser.error("--output-root is required for the registered run")
    if args.arm:
        worker(args)
        return 0
    return 0 if orchestrate(args) else 1


if __name__ == "__main__":
    raise SystemExit(main())
