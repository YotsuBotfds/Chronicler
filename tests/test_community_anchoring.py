"""Community anchoring (``--community-anchoring``): the world switch, its
wiring through the CLI, live, the batch manifest, checkpoints and the gate
runner, the fork design of the ablation arms, and the validator's community
component (docs/integration/community-anchoring.md; native behaviour in
tests/test_community_anchoring_native.py and the Rust tests)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chronicler import community_anchoring as ca
from chronicler import validation_ablation as va
from chronicler.validation_io import EVENT_NAME_TO_CODE

MIG = EVENT_NAME_TO_CODE["migration"]
FRIEND, KIN, MARRIAGE, RIVAL, CORELIG = 6, 5, 2, 1, 4


def _ns(**kw):
    return argparse.Namespace(**kw)


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def test_switch_is_off_by_default_dormant_and_omitted():
    from chronicler.models import WorldState

    assert ca.DEFAULT_ENABLED_FOR_NEW_WORLDS is False
    world = WorldState(name="w", seed=1)
    assert not ca.community_anchoring_enabled(world)
    assert "community_anchoring" not in json.loads(world.model_dump_json())
    ca.set_community_anchoring_enabled(world, True)
    assert ca.community_anchoring_enabled(world)
    dumped = json.loads(world.model_dump_json())
    assert dumped["community_anchoring"] is True
    assert WorldState.model_validate_json(world.model_dump_json()).community_anchoring is True
    ca.set_community_anchoring_enabled(world, False)
    assert world.community_anchoring is None
    assert "community_anchoring" not in json.loads(world.model_dump_json())
    # Mocks and other values read as off.
    assert not ca.community_anchoring_enabled(SimpleNamespace(community_anchoring="yes"))
    assert not ca.community_anchoring_enabled(object())


def test_switch_is_sent_to_the_simulator_only_when_on():
    calls = []

    class Sim:
        def set_community_anchoring(self, *args):
            calls.append(args)

    off = SimpleNamespace(community_anchoring=None, tuning_overrides={})
    ca.apply_community_anchoring(Sim(), off)
    assert calls == []
    on = SimpleNamespace(community_anchoring=True, tuning_overrides={})
    ca.apply_community_anchoring(Sim(), on)
    assert calls == [(True,)]
    tuned = SimpleNamespace(community_anchoring=True, tuning_overrides={ca.FULL_ANCHOR_TUNING_KEY: 0.25})
    ca.apply_community_anchoring(Sim(), tuned)
    assert calls[-1] == (True, 0.25)
    with pytest.raises(ValueError, match="finite and not negative"):
        ca.full_anchor_override(SimpleNamespace(tuning_overrides={ca.FULL_ANCHOR_TUNING_KEY: -1}))
    with pytest.raises(RuntimeError, match="predates community anchoring"):
        ca.apply_community_anchoring(object(), on)
    ca.apply_community_anchoring(object(), off)  # off: nothing is sent, even to an old build


def test_cli_parses_the_switch_and_the_manifest_records_it():
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
    from chronicler.main import _build_parser

    parser = _build_parser()
    assert parser.parse_args([]).community_anchoring is None
    assert parser.parse_args(["--community-anchoring"]).community_anchoring is True
    assert parser.parse_args(["--no-community-anchoring"]).community_anchoring is False
    assert "community_anchoring" in SIMULATION_ARG_KEYS
    assert simulation_config(parser.parse_args(["--community-anchoring"]))["community_anchoring"] is True
    args = parser.parse_args(["--decision-ablation", "community_anchor", "--ablation-start-turn", "5"])
    assert args.decision_ablation == "community_anchor"


def test_an_explicit_switch_needs_an_agent_pool(tmp_path):
    from chronicler.main import execute_run

    args = _ns(seed=1, turns=2, civs=2, regions=4, output=str(tmp_path / "chronicle.md"),
               state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
               scenario=None, simulate_only=True, agents="off", tuning_overrides={}, community_anchoring=True)
    with pytest.raises(ValueError, match="Community anchoring requires an agent pool"):
        execute_run(args)


def test_the_community_arm_needs_the_switch():
    from chronicler.main import _check_ablation_term

    _check_ablation_term(None, SimpleNamespace())
    _check_ablation_term(("needs", 5), SimpleNamespace(community_anchoring=None))
    _check_ablation_term(("community_anchor", 5), SimpleNamespace(community_anchoring=True))
    with pytest.raises(ValueError, match="requires community anchoring"):
        _check_ablation_term(("community_anchor", 5), SimpleNamespace(community_anchoring=None))


def test_fork_refuses_the_community_arm_on_a_world_without_the_switch():
    from chronicler.main import _fork_ablation

    class Sim:
        calls = []

        def set_decision_ablation(self, names, start):
            self.calls.append((names, start))

    bridge = argparse.Namespace(_sim=Sim(), decision_ablation=None)
    args = _ns(decision_ablation="community_anchor", ablation_start_turn=101)
    with pytest.raises(ValueError, match="requires community anchoring"):
        _fork_ablation(args, {"agent_mode": "hybrid", "simulation_args": {}}, bridge, 101,
                       world=SimpleNamespace(community_anchoring=None))
    assert Sim.calls == []
    _fork_ablation(args, {"agent_mode": "hybrid", "simulation_args": {}}, bridge, 101,
                   world=SimpleNamespace(community_anchoring=True))
    assert Sim.calls == [(["community_anchor"], 101)]


def test_checkpoints_record_the_switch_and_a_resume_cannot_change_it():
    from chronicler.main import _adopt_checkpoint_args, _build_parser
    from chronicler.models import WorldState
    from chronicler.run_checkpoint import feature_flags

    world = WorldState(name="w", seed=1)
    assert feature_flags(world)["community_anchoring"] is False
    ca.set_community_anchoring_enabled(world, True)
    assert feature_flags(world)["community_anchoring"] is True

    class Loaded:
        def __init__(self, saved):
            self.state = argparse.Namespace(run_config={"simulation_args": saved, "output_args": {}}, seed=42,
                                            num_turns=50, world=SimpleNamespace(turn=10))

    parser = _build_parser()
    args = parser.parse_args(["--resume", "x.ckpt"])
    assert _adopt_checkpoint_args(parser, args, Loaded({"community_anchoring": True})) == []
    assert args.community_anchoring is True
    args = parser.parse_args(["--resume", "x.ckpt", "--no-community-anchoring"])
    conflicts = _adopt_checkpoint_args(parser, args, Loaded({"community_anchoring": True}))
    assert conflicts == ["--community-anchoring False conflicts with the checkpoint (saved: True)"]


# ---------------------------------------------------------------------------
# Gate runner and fork designs
# ---------------------------------------------------------------------------

def _load_runner():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "m53b_run_validation.py"
    spec = importlib.util.spec_from_file_location("m53b_run_validation_community", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def test_gate_runner_forwards_the_switch_and_forks_the_community_arm():
    runner = _load_runner()
    assert runner._community_anchoring_args(_ns(community_anchoring=None)) == []
    assert runner._community_anchoring_args(_ns(community_anchoring=True)) == ["--community-anchoring"]
    assert runner._community_anchoring_args(_ns(community_anchoring=False)) == ["--no-community-anchoring"]
    assert runner.ablation_arms_for(_ns(ablation_arms=None, community_anchoring=None)) == ["needs", "kin_roots"]
    assert runner.ablation_arms_for(_ns(ablation_arms=None, community_anchoring=True)) == [
        "needs", "kin_roots", "community_anchor"]
    assert runner.ablation_arms_for(_ns(ablation_arms="needs,placebo", community_anchoring=True)) == [
        "needs", "placebo"]
    # An aggregate determinism run is not sent the switch, and its manifest says so.
    args = _ns(community_anchoring=True, worldgen=None, regions=None, civs=None, parallel=3)
    assert runner._determinism_manifest_args(args, "off").community_anchoring is None
    assert runner._determinism_manifest_args(args, "hybrid").community_anchoring is True


def test_fork_design_2_tiles_procedural_runs_and_keeps_template_forks():
    from chronicler.ablation_arms import (
        ABLATION_DESIGN, ABLATION_MANIFEST_SCHEMA_VERSION, checkpoint_turns, fork_every, fork_turns,
    )

    assert ABLATION_DESIGN == ABLATION_MANIFEST_SCHEMA_VERSION == 2
    assert fork_every(None) == fork_every("template") == 100
    assert fork_every("procedural") == 20
    assert fork_every("procedural", design=1) == 100
    with pytest.raises(ValueError):
        fork_every(None, design=3)
    assert fork_turns(500) == [100, 200, 300, 400]
    assert fork_turns(300, every=20) == [100, 120, 140, 160, 180, 200, 220, 240, 260]
    assert fork_turns(200, every=20) == [100, 120, 140, 160]
    assert checkpoint_turns(300, every=20)[0] == 101 and checkpoint_turns(300, every=20)[-1] == 261
    # The windows tile turns 101 .. 280 without overlap.
    turns = fork_turns(300, every=20)
    covered = [t for fork in turns for t in range(fork + 1, fork + 21)]
    assert covered == list(range(101, 281))
    runner = _load_runner()
    assert runner._ablation_args(_ns(profile="full", turns=300, ablation_oracles=None, worldgen="procedural")) == [
        "--checkpoint-turns", ",".join(str(t + 1) for t in turns)]
    assert runner._ablation_args(_ns(profile="full", turns=500, ablation_oracles=None, worldgen=None)) == [
        "--checkpoint-turns", "101,201,301,401"]


def test_ablation_methods_follow_the_arms_design():
    from chronicler.validation_io import ablation_methods

    # Design 2 (and no arms) is scored by cohort method 6 (method 5 on the
    # communities of community method 2; docs/integration/spec-communities.md).
    assert ablation_methods(None) == (8, 6)
    assert ablation_methods({"status": "verified"}) == (7, 4)  # a design-1 summary has no design key
    assert ablation_methods({"status": "verified", "design": 2}) == (8, 6)


def test_methods_refuse_arms_of_another_design():
    from chronicler.validation_io import run_cohort_oracle, run_needs_oracle

    arm = {"window": 20, "forks": {}, "design": 1}
    with pytest.raises(ValueError, match="fork design 2, not 1; score them with method 7"):
        run_needs_oracle([{"seed": 1}], ablation=arm)
    with pytest.raises(ValueError, match="fork design 1, not 2; score them with method 8"):
        run_needs_oracle([{"seed": 1}], ablation={**arm, "design": 2}, method_version=7)
    with pytest.raises(ValueError, match="score them with method 4"):
        run_cohort_oracle([{"seed": 1}], ablation=arm)


def _write_events(path: Path, rows):
    import pyarrow as pa
    import pyarrow.ipc as ipc

    table = pa.table({
        "turn": pa.array([r[0] for r in rows], pa.uint32()),
        "agent_id": pa.array([r[1] for r in rows], pa.uint32()),
        "event_type": pa.array([r[2] for r in rows], pa.string()),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    with ipc.new_file(path, table.schema) as writer:
        writer.write_table(table)


def _design2_arms(tmp_path: Path, worldgen: str | None, fork_turns: list[int], schema: int = 2):
    from chronicler.ablation_arms import ABLATION_MANIFEST_FILENAME, ABLATION_MANIFEST_KIND
    from chronicler.batch_manifest import file_sha256

    batch = tmp_path / "batch_42"
    rows = [(t, 1, "migration") for t in range(0, 300, 7)]
    _write_events(batch / "seed_42" / "agent_events.arrow", rows)
    (batch / "batch_manifest.json").write_text(json.dumps({
        "kind": "chronicler-batch", "status": "complete", "turns": 300,
        "simulation": {"worldgen": worldgen}, "runs": [{"seed": 42, "dir": "seed_42"}]}), encoding="utf-8")
    arms = tmp_path / "ablation_42"
    forks = []
    for fork_turn in fork_turns:
        fork = arms / "needs" / "seed_42" / f"fork_{fork_turn}"
        _write_events(fork / "agent_events.arrow", [r for r in rows if r[0] <= fork_turn] + [(fork_turn + 3, 1, "migration")])
        ablation = {"name": "needs", "start_turn": fork_turn + 1, "forked_at": fork_turn + 1}
        (fork / "fork.json").write_text(json.dumps({"decision_ablation": ablation}), encoding="utf-8")
        forks.append({"arm": "needs", "seed": 42, "fork_turn": fork_turn, "dir": f"needs/seed_42/fork_{fork_turn}",
                      "files": {"agent_events.arrow": file_sha256(fork / "agent_events.arrow"),
                                "fork.json": file_sha256(fork / "fork.json")}})
    manifest = {
        "kind": ABLATION_MANIFEST_KIND, "schema_version": schema, "status": "complete",
        "plain_manifest_sha256": file_sha256(batch / "batch_manifest.json"),
        "arms": ["needs"], "window_turns": 20, "fork_turns": fork_turns, "seeds": [42], "forks": forks,
    }
    if schema >= 2:
        manifest["design"] = schema
    (arms / ABLATION_MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    return batch, arms


def test_loader_checks_each_design_against_its_own_rule(tmp_path):
    pytest.importorskip("pyarrow")
    every20 = [100, 120, 140, 160, 180, 200, 220, 240, 260]
    batch, arms = _design2_arms(tmp_path / "p2", "procedural", every20)
    loaded = va.load_ablation_arms(arms, batch)
    assert loaded["design"] == 2 and loaded["summary"]["design"] == 2
    assert loaded["arms"]["needs"]["design"] == 2 and loaded["summary"]["forks"] == 9
    assert loaded["summary"]["fork_rule"].startswith("every 20 turns")
    # A design-1 manifest of the same procedural batch keeps design 1's rule (and no design key).
    batch, arms = _design2_arms(tmp_path / "p1", "procedural", [100, 200], schema=1)
    loaded = va.load_ablation_arms(arms, batch)
    assert loaded["design"] == 1 and "design" not in loaded["summary"]
    # Design 2 in a procedural world refuses design 1's forks; template worlds keep them.
    batch, arms = _design2_arms(tmp_path / "bad", "procedural", [100, 200])
    with pytest.raises(va.AblationInputError, match="not the pre-registered rule"):
        va.load_ablation_arms(arms, batch)
    batch, arms = _design2_arms(tmp_path / "t2", None, [100, 200])
    assert va.load_ablation_arms(arms, batch)["design"] == 2


# ---------------------------------------------------------------------------
# Validator: community ties, spec communities, the community component
# ---------------------------------------------------------------------------

def test_community_ties_mirror_the_native_rule():
    regions = {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 0, 7: 0, 8: 0}
    sigs = {a: [(3, 52, -1)] for a in (1, 2, 3, 5, 6, 7, 8)}
    sigs[4] = [(3, 47, -1)]  # same event type, another 5-turn bucket
    edges = [
        (1, 2, FRIEND, 60),     # tie (non-kin)
        (1, 3, KIN, 80),        # tie (kin)
        (1, 4, FRIEND, 60),     # no shared memory
        (1, 5, FRIEND, 60),     # another region
        (1, 6, RIVAL, 60),      # negative bond
        (1, 7, CORELIG, 19),    # sentiment below 20
        (1, 8, MARRIAGE, 100),  # the spouse
        (3, 1, KIN, 80),        # kin only
        (9, 1, FRIEND, 90),     # 9 is not alive
    ]
    ties = va.community_ties(edges, regions, sigs)
    assert ties == {1: (2, 1, 2), 3: (1, 0, 0)}
    sigs[4] = [(3, 54, -1)]
    assert va.community_ties(edges, regions, sigs)[1] == (3, 2, 3)


def _circle_edges(members, bond=FRIEND, sentiment=60):
    return [(a, b, bond, sentiment) for a in members for b in members if a != b]


def test_spec_communities_need_five_a_non_kin_edge_and_shared_memories():
    regions = {a: 0 for a in range(1, 30)}
    sigs = {a: [(3, 52, -1)] for a in range(1, 30)}
    friends = _circle_edges(range(1, 6))                # five friends: a community
    family = _circle_edges(range(10, 16), bond=KIN)     # six kin only: excluded
    pair = _circle_edges(range(20, 23))                 # three friends: too small
    found = va.detect_spec_communities(friends + family + pair, regions, sigs)
    assert found == [set(range(1, 6))]
    # Rivals and edges across regions do not join anyone.
    split = {**regions, 4: 1, 5: 1}
    assert va.detect_spec_communities(friends + _circle_edges(range(1, 6), bond=RIVAL), split, sigs) == []


def _anchored_world(seeds=6, full_plain=1, full_ablated=2, none_plain=1, none_ablated=1):
    """Agents 0-4 are five friends sharing a memory at the fork (four ties
    each); agents 10-19 have no tie. Plain / ablated migrations per agent."""
    runs, arm = [], {"window": 20, "forks": {}, "design": 2}
    for seed in range(seeds):
        matching = ("civ_affinity", "occupation", "boldness", "ambition", "loyalty_trait")
        needs = ("safety", "material", "social", "spiritual", "autonomy", "purpose")
        cols = {"turn": [], "agent_id": [], "region": [], **{k: [] for k in matching + needs}, "satisfaction": []}
        rel = {k: [] for k in ("turn", "agent_id", "target_id", "bond_type", "sentiment")}
        mem = {k: [] for k in ("turn", "agent_id", "event_type", "memory_turn", "valence_sign")}
        events, ablated = [], {}
        for agent in list(range(5)) + list(range(10, 20)):
            cols["turn"].append(100)
            cols["agent_id"].append(agent)
            cols["region"].append(0)
            for key in matching:
                cols[key].append(0)
            for key in needs:
                cols[key].append(0.9)
            cols["satisfaction"].append(0.6)
            for k, v in zip(mem, (100, agent, 3, 92 if agent < 5 else 40 + agent, -1)):
                mem[k].append(v)
        for a, b, bond, sentiment in _circle_edges(range(5)):
            for k, v in zip(rel, (100, a, b, bond, sentiment)):
                rel[k].append(v)
        for agent in range(5):
            events += [{"turn": 101 + k, "agent_id": agent, "event_type": MIG} for k in range(full_plain)]
            ablated[(agent, MIG)] = [101 + k for k in range(full_ablated)]
        for agent in range(10, 20):
            events += [{"turn": 101 + k, "agent_id": agent, "event_type": MIG} for k in range(none_plain)]
            ablated[(agent, MIG)] = [101 + k for k in range(none_ablated)]
        arm["forks"][seed] = {100: ablated}
        runs.append({"seed": seed, "events": events, "needs_columns": cols, "relationship_columns": rel,
                     "memory_columns": mem, "bundle": {"metadata": {"total_turns": 300}}})
    return runs, arm


def test_community_component_scores_members_and_the_anchors_exposure():
    runs, arm = _anchored_world(full_plain=1, full_ablated=2)
    result = va.community_ablation_result(runs, arm)
    by = result["migration_by_cohort"]
    assert (by["full_ties"]["cohort"], by["full_ties"]["rate_ratio"]) == (30, 0.5)
    assert by["no_ties"]["rate_ratio"] == 1.0 and by["partial_ties"]["cohort"] == 0
    assert by["spec_members"]["cohort"] == 30
    # The oracle's members (label propagation over every edge) are the five friends.
    assert result["members_migration"]["cohort"] == 30 and result["status"] == "PASS"
    restated = result["restated_candidate"]
    # Half the moves is beyond the M53 band (at most 30% fewer); no partial ties: no dose order.
    assert restated["full_ties"]["status"] == "FAIL" and "beyond_band" in restated["full_ties"]["failed_criteria"]
    assert restated["no_ties_within_tolerance"] is True and restated["dose_response"] is False
    assert restated["status"] == "FAIL"
    assert va.community_ablation_result(runs, None)["status"] == "NOT_RUN"


def test_community_component_fails_without_an_anchor():
    runs, arm = _anchored_world(full_plain=2, full_ablated=2)
    result = va.community_ablation_result(runs, arm)
    assert result["status"] == "FAIL" and "members' migration rate ratio" in result["reason"]
    assert result["migration_by_cohort"]["full_ties"]["rate_ratio"] == 1.0


@pytest.mark.parametrize("method_version", [5, 6])
def test_cohort_method_5_reports_the_community_component_without_deciding(method_version):
    from chronicler.validation_gate import adjudicate_validation_report
    from chronicler.validation_io import run_cohort_oracle

    runs, arm = _anchored_world(full_plain=1, full_ablated=2)
    kin = {"window": 20, "forks": {seed: {100: {}} for seed in range(6)}, "design": 2}
    result = run_cohort_oracle(runs, ablation=kin, community=arm, method_version=method_version)
    assert result["method_version"] == method_version
    # Method 6 takes community method 2's members (here the same five
    # friends) and reports method 1's beside them; method 5 PR #62's variant.
    cohorts = set(result["community_ablation"]["migration_by_cohort"])
    extra = {"method_1_members", "method_1_non_members"} if method_version == 6 else {
        "spec_members", "spec_non_members"}
    assert cohorts == {"members", "non_members", "full_ties", "partial_ties", "no_ties"} | extra
    assert result["community_ablation"]["members_migration"]["cohort"] == 30
    assert ("community_method_version" in result["community_ablation"]) is (method_version == 6)
    assert result["community_ablation"]["status"] == "PASS" and result["community_ablation"]["fork_design"] == 2
    assert result["ablation"]["fork_design"] == 2
    assert "community" not in result["required_components"]
    report = {"results": {"needs": {"status": "PASS"}, "community": {"status": "PASS"}, "cohort": result}}
    decision = adjudicate_validation_report("subset", report)
    rows = {row["oracle"]: row for row in decision["causal_evidence"]}
    assert rows["cohort_community"]["decides"] is False
    assert rows["cohort_community"]["status"] == "PASS"
    assert "four ties 0.500" in rows["cohort_community"]["detail"]
    flat_runs, flat_arm = _anchored_world(full_plain=2, full_ablated=2)
    flat = run_cohort_oracle(flat_runs, ablation=kin, community=flat_arm, method_version=method_version)
    decision = adjudicate_validation_report(
        "subset", {"results": {"needs": {"status": "PASS"}, "community": {"status": "PASS"}, "cohort": flat}})
    items = {item["oracle"]: item for item in decision["informational_non_pass"]}
    assert items["cohort_community_ablation"]["status"] == "FAIL"
    # The verdict is method 3's (observational), whatever the community component says.
    assert flat["status"] == run_cohort_oracle(flat_runs, method_version=3)["status"]
    assert result["status"] == run_cohort_oracle(runs, method_version=3)["status"]
