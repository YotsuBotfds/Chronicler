#!/usr/bin/env python3
"""Registered six-worker mechanical proof; never a natural-world benefit gate."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import resource
import subprocess
import sys
import time
import zlib

SCRIPT = Path(__file__).resolve()
HELPER = SCRIPT.with_name("scientific_publication_native_proof.py")
REGISTRATION = SCRIPT.parents[1] / "docs/experiments/scientific-research-native-composition-2026-10-28.md"
NATIVE = "fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317"
CRATE_TREE = "a4703ef4e9a21b5dbb194d318536a46e6ca8b71c"
FEATURES = ("health_care", "harvest_forecasts", "ritual_gatherings", "scientific_claims", "transaction_receipts")
ARMS = ("finite_direct", "finite_resume", "paused_fork")
POOL_FIELDS = (("agent_bridge", "_sim", "AgentSimulator", "agent"),
               ("ecology_runtime", None, "EcologySimulator", "ecology"),
               ("politics_runtime", None, "PoliticsSimulator", "politics"))


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
    source_root = SCRIPT.parents[1]
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=source_root, text=True):
        raise ValueError("prospective proof requires a clean source worktree")
    crate_tree = subprocess.check_output(["git", "rev-parse", "HEAD:chronicler-agents"], cwd=source_root, text=True).strip()
    if crate_tree != CRATE_TREE:
        raise ValueError("source Rust crate differs from qualified receipt runtime")
    compiled = __import__("chronicler_agents.chronicler_agents", fromlist=["AgentSimulator"])
    origin = importlib.util.find_spec("chronicler_agents.chronicler_agents").origin
    if not origin.endswith(tuple(EXTENSION_SUFFIXES)):
        raise ValueError("native runtime is not an actual compiled extension")
    classes = {}
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(native, name)
        if not isinstance(cls, type) or cls is not getattr(compiled, name):
            raise ValueError("native simulator is not a real class")
        version, fingerprint, schema = cls.checkpoint_schema()
        classes[name] = dict(module=cls.__module__, name=cls.__qualname__, version=version,
            fingerprint=fingerprint, schema_sha256=hashlib.sha256(schema.encode()).hexdigest())
    result = dict(source=source_identity(), native=native_identity(), environment=environment_identity(),
        compiled_origin=origin, available_compiled_classes=classes, crate_tree=crate_tree, runner_sha256=sha(SCRIPT),
        helper_sha256=sha(HELPER), registration_sha256=sha(REGISTRATION))
    if result["native"]["sha256"] != NATIVE:
        raise ValueError("actual native binary differs from registered receipt runtime")
    env = result["environment"]
    required_threads = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
                        "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS", "RAYON_NUM_THREADS")
    if (env["affinity_cpu_count"] != 1 or any(env["thread_env"].get(name) != "1" for name in required_threads)
            or env["thread_env"].get("PYTHON_CPU_COUNT") != "1" or env["thread_env"].get("PYTHONHASHSEED") != "0"):
        raise ValueError("registered proof requires one affinity CPU, one numerical/native thread and hash seed zero")
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
    from chronicler import scientific_claims
    from chronicler.main import _build_parser
    from chronicler.expansion_features import configure_expansion_features, expansion_feature_flags
    from chronicler.grain_reserves import set_grain_reserves_enabled
    from chronicler.contact_ledger import set_contact_ledger_enabled
    from chronicler.scientific_research import validate_state
    from chronicler.techniques_state import TECHNIQUE_INDEX
    from chronicler.resources import get_season_id
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
        context = scientific_claims._context(world, index)
        assert context is not None
        seats.append(dict(seat=index, region=seat.region, owner=owner, birth=seat.model_dump(),
                          practice_rows=rows, initial_context=context.model_dump()))
    assert len(seats) <= 5 and world.turn == 2
    flags = expansion_feature_flags(world)
    assert all(flags[name] for name in (*FEATURES, "scientific_research_agendas"))
    assert world.scientific_claims.publication_rule == "funded-context-v2"
    return dict(seed=seed, actual_academy_count=len(seats), academies=seats, flags=flags,
        host_seal=world.scientific_claims.research_agendas.host_seal, source_turn=2,
        calendar_season=get_season_id(world.turn),
        research=world.scientific_claims.research_agendas.model_dump())


def native_sections(loaded, path, *, retain=None):
    """Hash every saved native section and bind it to its actual restored pool."""
    import chronicler_agents as native
    from chronicler.run_checkpoint import read_header
    header, body = read_header(path)
    assert header == loaded.header
    saved = {}
    for section in header["sections"]:
        name = section["name"]
        if not name.startswith("native."):
            continue
        assert name not in saved
        packed = body[section["offset"]:section["offset"] + section["length"]]
        assert hashlib.sha256(packed).hexdigest() == section["sha256"]
        raw = zlib.decompress(packed)
        assert len(raw) == section["raw_length"]
        saved[name] = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                           packed_sha256=section["sha256"])
        if retain is not None:
            with (Path(retain) / (name + "-final.bin")).open("xb") as stream:
                stream.write(raw)
    pools = {}
    for field, attribute, class_name, kind in POOL_FIELDS:
        runtime = getattr(loaded.state, field)
        if runtime is None:
            continue
        simulator = getattr(runtime, attribute) if attribute else runtime
        assert type(simulator) is getattr(native, class_name)
        blob = simulator.checkpoint_state()
        name = "native." + kind + ".0"
        assert name in saved and saved[name]["sha256"] == hashlib.sha256(blob).hexdigest()
        version, fingerprint, schema = simulator.checkpoint_schema()
        pools[name] = dict(runtime_field=field, class_name=class_name, version=version,
            fingerprint=fingerprint, schema_sha256=hashlib.sha256(schema.encode()).hexdigest())
    assert set(saved) == set(pools), "saved native sections and active pools differ"
    return {name: {**saved[name], **pools[name]} for name in sorted(saved)}


def checkpoint_identity(loaded, path):
    state = loaded.state
    return dict(turn=state.world.turn, exact=loaded.header["exact"], flags=loaded.header["flags"],
        world_sha256=digest(state.world.model_dump(mode="json")),
        history_sha256=digest([row.model_dump(mode="json") for row in state.history]),
        events_sha256=digest([row.model_dump(mode="json") for row in state.world.events_timeline]),
        research=state.world.scientific_claims.research_agendas.model_dump(mode="json"),
        native_sections=native_sections(loaded, path))


def validate_pause_archive(parent, final, receipt):
    """Pause closes admission, while retained work may resolve and disseminate."""
    before, after = parent["science"], final["science"]
    a, b = before["research_agendas"], after["research_agendas"]
    assert a["enabled"] is True and b["enabled"] is False
    assert b["policy_changed_turn"] == 27
    for key in ("schema_version", "rule", "enabled_turn", "host_seal", "next_open_turn", "origin_cursor"):
        assert a[key] == b[key], "pause changed research lineage: " + key
    assert b["academy_births"][:len(a["academy_births"])] == a["academy_births"]
    assert after["seat_ids"][:len(before["seat_ids"])] == before["seat_ids"]
    assert after["claims"] == before["claims"]
    assert len(b["cycles"]) == len(a["cycles"])
    for old, new in zip(a["cycles"], b["cycles"]):
        if old["closed_turn"] is not None:
            assert old == new
        else:
            for key in ("id", "legacy_adopted", "opening_roster_complete", "opened_turn", "origin_seat",
                        "participants", "claims", "trials", "announcement_event_id"):
                assert old[key] == new[key]
            assert new["closed_turn"] == 27 and new["close_reason"] == "research_paused"
    assert len(after["trials"]) == len(before["trials"])
    assert after["trial_spent"] == before["trial_spent"]
    mutable = {"status", "resolved_turn", "observed_control", "observed_treatment", "informative",
               "supports", "reason", "event_id"}
    for old, new in zip(before["trials"], after["trials"]):
        assert new["funded_turn"] < 27
        if old["status"] != "running":
            assert old == new
        else:
            assert {k: v for k, v in old.items() if k not in mutable} == {k: v for k, v in new.items() if k not in mutable}
    for key in ("proposals", "receipts"):
        assert after[key][:len(before[key])] == before[key], "retained archive prefix changed: " + key
    assert final["history"][:len(parent["history"])] == parent["history"]
    assert final["events"][:len(parent["events"])] == parent["events"]
    assert receipt["research_policy"]["before"] == {"mode": a["rule"], **a}
    expected = {**deepcopy(a), "enabled": False, "policy_changed_turn": 27}
    assert receipt["research_policy"]["after"] == {"mode": a["rule"], **expected}
    assert receipt["research_policy"]["requested_enabled"] is False
    return dict(archive_prefix_preserved=True, no_new_trial_funding=True,
        trial_spent_delta=after["trial_spent"] - before["trial_spent"],
        effort_spent_delta=after["effort_spent"] - before["effort_spent"],
        effort_pause_semantics="pause gates new trials; paid adoption has its existing cadence",
        parent_trial_count=len(before["trials"]), final_trial_count=len(after["trials"]))


def worker(args):
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    import numpy as np
    from chronicler_agents import AgentSimulator
    from chronicler import main
    from chronicler.models import ActionType
    from chronicler.run_checkpoint import read_checkpoint
    from chronicler.expansion_experiment import controls_for_state
    from chronicler.bundle_codec import load_bundle, same
    from chronicler.snapshot_pruning import prune_history, PRUNED_CIV_STATS_KEY
    from chronicler.scientific_research import validate_state
    before = assert_frozen(args)
    folder = Path(args.output_root) / f"seed-{args.seed}" / args.arm
    folder.mkdir(parents=True, exist_ok=False)
    started, cpu = time.perf_counter(), time.process_time()
    random.seed(314159)
    np.random.seed(314159)
    main.ActionEngine.select_action = lambda *a, **k: ActionType.DEVELOP
    run_args = main._build_parser().parse_args(cli(folder, args.seed))
    loaded = request = world = parent_at_restore = parent_record = None
    if args.arm == "finite_direct":
        world = controlled(args.seed)
    else:
        parent = folder.parent / "finite_direct/checkpoint_turn_27.ckpt"
        loaded = read_checkpoint(parent)
        assert loaded.exact and loaded.state.world.turn == 27
        validate_state(loaded.state.world)
        parent_at_restore = checkpoint_identity(loaded, parent)
        parent_record = dict(science=loaded.state.world.scientific_claims.model_dump(mode="json"),
            history=[row.model_dump(mode="json") for row in loaded.state.history],
            events=[row.model_dump(mode="json") for row in loaded.state.world.events_timeline],
            run_config=deepcopy(loaded.state.run_config), header=deepcopy(loaded.header),
            path=str(parent.resolve()), sha256=sha(parent))
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
        final_path = folder / "checkpoint_turn_29.ckpt"
        final = read_checkpoint(final_path)
        world, state = final.state.world, final.state.world.scientific_claims
        assert world.turn == 29 and final.state.agent_bridge is not None
        assert isinstance(final.state.agent_bridge._sim, AgentSimulator)
        assert final.header["exact"] is (args.arm != "paused_fork")
        assert final.header["flags"]["scientific_research_agendas"] is (args.arm != "paused_fork")
        validate_state(world)
        pools = native_sections(final, final_path, retain=folder)
        assert "native.agent.0" in pools
        bundle = load_bundle(folder / "chronicle_bundle.json")
        raw_history = [row.model_dump(mode="json") for row in final.state.history]
        pruned_history, pruned_stats = prune_history(raw_history)
        assert same(bundle["history"], pruned_history)
        assert same(bundle[PRUNED_CIV_STATS_KEY], pruned_stats)
        assert [row["turn"] for row in bundle["history"]] == list(range(3, 30))
        assert all(any(isinstance(row.get(name), dict) for row in bundle["history"]) for name in FEATURES)
        expected_resume = parent_record["run_config"].get("resume_info") if parent_record else None
        lineage = deepcopy(parent_record["run_config"].get("lineage", [])) if parent_record else []
        if parent_record:
            lineage.append(dict(resumed_at=27, kind="checkpoint", exact=True))
        receipt = bundle["metadata"].get("expansion_experiment")
        pause_assessment = None
        if args.arm == "paused_fork":
            expected_resume = dict(kind="experiment-fork", exact=False, turn=27)
            previous = parent_record["run_config"].get("resume_info")
            if previous is not None:
                expected_resume["previous"] = previous
            expected_parent = dict(path=parent_record["path"], sha256=parent_record["sha256"], turn=27,
                seed=args.seed, identity=parent_record["header"]["identity"],
                flags=parent_record["header"]["flags"], exact=True)
            assert receipt["parent_checkpoint"] == expected_parent
            assert receipt["registration"] == request["registration"]
            assert receipt["source"] == before["source"] and receipt["native"] == before["native"]
            for key, value in dict(schema_version=1, experiment="native-finite-research-mechanical", cohort="development",
                    feature="scientific_claims", arm="pause", intervention_fork=True, applied_before_turn=27, seed=args.seed).items():
                assert type(receipt[key]) is type(value) and receipt[key] == value
            original_controls = {name: parent_record["science"][name] for name in controls_for_state("scientific_claims", state)}
            assert receipt["controls_before"] == receipt["controls_after"] == original_controls
            assert receipt["previous_experiment"] == parent_record["run_config"].get("expansion_experiment")
            lineage.append(dict(resumed_at=27, kind="experiment-fork", exact=False, experiment=receipt))
            pause_assessment = validate_pause_archive(parent_record,
                dict(science=state.model_dump(mode="json"), history=raw_history,
                     events=[row.model_dump(mode="json") for row in world.events_timeline]), receipt)
        else:
            assert receipt == (parent_record["run_config"].get("expansion_experiment") if parent_record else None)
        assert final.state.run_config["resume_info"] == expected_resume
        assert final.header["lineage"] == final.state.run_config["lineage"] == lineage
        assert bundle["metadata"].get("resume") == expected_resume
        assert ("resume" in bundle["metadata"]) is (expected_resume is not None)
        assert final.state.run_config["simulation_args"]["scientific_research_agendas"] is (args.arm != "paused_fork")
        assert state.publication_rule == "funded-context-v2"
        assert all(final.header["flags"][name] is True for name in FEATURES)
        write(folder / "mechanical-summary.json", dict(seed=args.seed, arm=args.arm,
            first_source_turn=2, final_turn=29, history_turns=[row["turn"] for row in bundle["history"]],
            parent_at_restore=parent_at_restore, final_checkpoint=checkpoint_identity(final, final_path),
            controls=controls_for_state("scientific_claims", state), science=state.model_dump(mode="json"),
            events=dict(Counter(e.event_type for e in world.events_timeline)),
            feature_sections={name: sum(isinstance(row.get(name), dict) for row in bundle["history"]) for name in FEATURES},
            active_native_pools=pools, native_agent_final_sha256=pools["native.agent.0"]["sha256"], rng=rng,
            checkpoint_sections=[row["name"] for row in final.header["sections"]],
            resume_metadata=bundle["metadata"].get("resume"),
            expected_resume_metadata=expected_resume, resume_provenance_validated=True,
            lineage=lineage, pause_assessment=pause_assessment,
            experiment_receipt=bundle["metadata"].get("expansion_experiment"),
            effective_simulation_args=final.state.run_config["simulation_args"]))
    finally:
        after = assert_frozen(args)
        write(folder / "worker-identity.json", dict(before=before, after=after, identities_stable=before == after,
            seconds=time.perf_counter() - started, process_cpu_seconds=time.process_time() - cpu))


def json_differences(left, right, path="$", *, left_present=True, right_present=True):
    from chronicler.bundle_codec import same
    if left_present and right_present and same(left, right):
        return []
    if left_present and right_present and isinstance(left, dict) and isinstance(right, dict):
        order = ([] if list(left) == list(right) else [dict(path=path + ".<key-order>",
            left_present=True, right_present=True, left=list(left), right=list(right))])
        return order + [row for key in sorted(left.keys() | right.keys()) for row in json_differences(
            left.get(key), right.get(key), path + "." + key,
            left_present=key in left, right_present=key in right)]
    if left_present and right_present and isinstance(left, list) and isinstance(right, list):
        return [row for i in range(max(len(left), len(right))) for row in json_differences(
            left[i] if i < len(left) else None, right[i] if i < len(right) else None, path + f"[{i}]",
            left_present=i < len(left), right_present=i < len(right))]
    return [dict(path=path, left_present=left_present, right_present=right_present, left=left, right=right)]


def compare(left, right):
    from chronicler.bundle_codec import load_bundle, same
    a, b = (helper().files(folder, after=27) for folder in (left, right))
    summaries = [json.loads((folder / "mechanical-summary.json").read_text()) for folder in (left, right)]
    comparisons, raw_differences, normalized_differences, provenance_errors = {}, [], [], []
    for name in sorted(a.keys() & b.keys()):
        if name == "chronicle_bundle.json":
            x, y = load_bundle(a[name]), load_bundle(b[name])
            raw_differences = json_differences(x, y)
            for side, bundle, summary in zip(("direct", "resume"), (x, y), summaries):
                try:
                    assert summary["resume_provenance_validated"] is True, "worker provenance was not validated"
                    expected = summary["expected_resume_metadata"]
                    assert same(summary["resume_metadata"], expected) and same(expected, bundle["metadata"].get("resume")), "resume provenance differs"
                    assert ("resume" in bundle["metadata"]) is (expected is not None), "resume key presence differs"
                    generated = bundle["metadata"]["generated_at"]
                    assert isinstance(generated, str) and datetime.fromisoformat(generated).utcoffset() is not None, "invalid generated_at"
                except (AssertionError, KeyError, TypeError, ValueError) as exc:
                    provenance_errors.append(dict(side=side, type=type(exc).__name__, message=str(exc)))
            if not provenance_errors:
                for bundle in (x, y):
                    # Omit only separately validated writer-owned provenance;
                    # every other metadata, world, history and event compares.
                    bundle["metadata"].pop("generated_at")
                    bundle["metadata"].pop("resume", None)
            normalized_differences = json_differences(x, y)
            equal = not provenance_errors and same(x, y)
        else:
            equal = a[name].read_bytes() == b[name].read_bytes()
        comparisons[name] = equal
    x, y = summaries
    return dict(left_files=sorted(a), right_files=sorted(b), file_set_equal=a.keys() == b.keys(),
        files=comparisons, native_agent_equal=x["native_agent_final_sha256"] == y["native_agent_final_sha256"],
        native_sections_equal=x["active_native_pools"] == y["active_native_pools"], rng_equal=x["rng"] == y["rng"],
        provenance_validated=not provenance_errors, provenance_errors=provenance_errors,
        raw_bundle_differences=raw_differences, normalized_bundle_differences=normalized_differences)


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
    comparisons, errors = [], []
    for seed in (42, 7):
        if all(row["status"] == "complete" for row in runs if row["seed"] == seed):
            folder = root / f"seed-{seed}"
            try:
                parent_path = folder / "finite_direct/checkpoint_turn_27.ckpt"
                parent = checkpoint_identity(read_checkpoint(parent_path), parent_path)
                restores = {arm: json.loads((folder / arm / "mechanical-summary.json").read_text())["parent_at_restore"]
                            for arm in ARMS[1:]}
                paused = json.loads((folder / "paused_fork/mechanical-summary.json").read_text())
                comparisons.append(dict(seed=seed, exact_resume=compare(folder / "finite_direct", folder / "finite_resume"),
                    original_parent=parent, actual_restores=restores, shared_parent_equal=all(value == parent for value in restores.values()),
                    pause_assessment=paused["pause_assessment"]))
            except Exception as exc:
                errors.append(dict(seed=seed, type=type(exc).__name__, message=str(exc)))
    after = assert_frozen(args)
    used = resource.getrusage(resource.RUSAGE_CHILDREN)
    execution_complete = len(runs) == 6 and all(row["status"] == "complete" for row in runs)
    qualified = qualification_pass(execution_complete, comparisons, errors, used.ru_utime + used.ru_stime)
    write(root / "report.json", dict(protocol_sha256=sha(REGISTRATION), freeze_sha256=sha(args.freeze),
        source_freeze=before, after=after, identities_stable=before == after,
        execution_complete=execution_complete, qualified=qualified, comparison_errors=errors,
        actual_physics_ticks=62 if execution_complete else None,
        aggregate_child_cpu_seconds=used.ru_utime + used.ru_stime, runs=runs, comparisons=comparisons,
        files={str(path.relative_to(root)): sha(path) for path in sorted(root.rglob("*")) if path.is_file()}))
    return qualified


def qualification_pass(execution_complete, comparisons, errors, cpu_seconds):
    if not execution_complete or errors or cpu_seconds > 60 or [row["seed"] for row in comparisons] != [42, 7]:
        return False
    for row in comparisons:
        exact, pause = row["exact_resume"], row["pause_assessment"]
        if (not row["shared_parent_equal"] or exact["provenance_validated"] is not True
                or not exact["file_set_equal"] or not exact["files"]
                or not all(value is True for value in exact["files"].values())
                or any(exact[key] is not True for key in ("native_agent_equal", "native_sections_equal", "rng_equal"))
                or pause.get("archive_prefix_preserved") is not True
                or pause.get("no_new_trial_funding") is not True or pause.get("trial_spent_delta") != 0):
            return False
    return True


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
