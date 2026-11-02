"""Exact corrected-baseline regression oracles for the snapshot optimization.

Golden data was captured from 423a67c before importing the optimization and is
kept frozen in ``corrected_423a67c.json``. ``corrected_backlog_2026_10.json``
rolled it forward for the 2026-10 deferred-backlog corrections,
``corrected_extinction_2026_10.json`` for the 2026-10 extinction fix,
``corrected_food_balance_2026_10.json`` for the 2026-10 food-balance
corrections, ``corrected_food_logistics_2026_10.json`` for the 2026-10
food-logistics changes (only the locust recalibration moves the off-mode
lane), ``corrected_hunger_2026_10.json`` for the 2026-10 hunger corrections
(the aggregate famine toll scaled by hunger),
``corrected_farmland_2026_10.json`` for the 2026-10 farmland and
regional-climate corrections (food per head against the crowding of the land,
regional harvest shocks), ``corrected_open_items_2026_10.json`` for the
2026-10 procedural open-item corrections (docs/integration/procedural-gates.md),
and the live oracle, ``corrected_population_2026_10.json``, rolls that forward
for the 2026-10 population corrections (arrivals never remove residents,
famine refugees conserved; docs/integration/population-entities.md); each
file's provenance lists only its own corrections and the scoped-difference
proof below pins exactly what each link changed.
The older fixtures and the edf7299 artifacts remain frozen as historical
evidence.
Every turn's pre-existing snapshot/events/narrative and ordered RNG primitives are
checked; only the independently tested version-1 regional observation export is
projected out of these older frozen snapshot witnesses. No approximate float
comparisons or relaxed precision are used.
"""
from copy import deepcopy
import hashlib
from chronicler.turn_artifacts import TurnObservation, TurnResult
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chronicler.intelligence import _get_perceived_stat_with_accuracy, get_perceived_stat
from scripts.benchmark_headless import FixedDateTime, rng_trace, run
from scripts.third_wave_controls import legacy_event_dump


FIXTURES = Path(__file__).parent / "fixtures" / "performance"
BASELINE = json.loads((FIXTURES / "corrected_population_2026_10.json").read_text())
OPEN_ITEMS_BASELINE = json.loads((FIXTURES / "corrected_open_items_2026_10.json").read_text())
FARMLAND_BASELINE = json.loads((FIXTURES / "corrected_farmland_2026_10.json").read_text())
HUNGER_BASELINE = json.loads((FIXTURES / "corrected_hunger_2026_10.json").read_text())
FOOD_LOGISTICS_BASELINE = json.loads((FIXTURES / "corrected_food_logistics_2026_10.json").read_text())
FOOD_BALANCE_BASELINE = json.loads((FIXTURES / "corrected_food_balance_2026_10.json").read_text())
EXTINCTION_BASELINE = json.loads((FIXTURES / "corrected_extinction_2026_10.json").read_text())
BACKLOG_BASELINE = json.loads((FIXTURES / "corrected_backlog_2026_10.json").read_text())
PRIOR_BASELINE = json.loads((FIXTURES / "corrected_423a67c.json").read_text())
# Each roll-forward link: (older oracle, newer oracle declaring its corrections).
ORACLE_CHAIN = {"backlog": (PRIOR_BASELINE, BACKLOG_BASELINE),
                "extinction": (BACKLOG_BASELINE, EXTINCTION_BASELINE),
                "food_balance": (EXTINCTION_BASELINE, FOOD_BALANCE_BASELINE),
                "food_logistics": (FOOD_BALANCE_BASELINE, FOOD_LOGISTICS_BASELINE),
                "hunger": (FOOD_LOGISTICS_BASELINE, HUNGER_BASELINE),
                "farmland": (HUNGER_BASELINE, FARMLAND_BASELINE),
                "open_items": (FARMLAND_BASELINE, OPEN_ITEMS_BASELINE),
                "population": (OPEN_ITEMS_BASELINE, BASELINE)}
PERCEPTIONS = json.loads((FIXTURES / "perception_edf7299.json").read_text())


def _frozen_snapshot(snapshot):
    """Project only the independently tested v1 regional observation export.

    The historical fixtures still pin every pre-existing snapshot field. Refuse
    unknown/malformed additions so a future export contract needs explicit
    review instead of silently disappearing behind this frozen witness.
    """
    fields = snapshot.model_dump(mode="json")
    if "regional_population" not in fields:
        return fields
    value = fields["regional_population"]
    assert type(value) is dict and set(value) == {
        "schema_version", "mode", "source_turn", "completed_turn", "timing",
        "counts", "sources", "agent_counts", "agent_source", "food_weights"}
    assert type(value["schema_version"]) is int and value["schema_version"] == 1
    assert type(value["mode"]) is str and value["mode"] in {"off", "hybrid", "shadow", "demographics-only"}
    assert type(value["source_turn"]) is int and value["source_turn"] >= 0
    assert type(value["completed_turn"]) is int
    assert value["completed_turn"] == value["source_turn"] + 1 == fields["turn"]
    assert value["timing"] == "completed_turn"
    counts = value["counts"]
    assert type(counts) is list
    size = len(counts)

    def valid_counts(values):
        return (type(values) is list and len(values) == size
                and all(type(item) is int and item >= 0 for item in values))

    assert valid_counts(counts)
    sources = value["sources"]
    allowed = ({"demographics_clamped_region_state", "uncontrolled_region_state"}
               if value["mode"] == "demographics-only" else
               {"hybrid_region_state" if value["mode"] == "hybrid" else "python_region_state"})
    assert type(sources) is list and len(sources) == size
    assert all(type(source) is str and source in allowed for source in sources)
    if value["agent_counts"] is None:
        assert value["agent_source"] is None
    else:
        assert value["mode"] != "off"
        assert valid_counts(value["agent_counts"])
        assert value["agent_source"] == "native_region_alive_count"
    food = value["food_weights"]
    if food is not None:
        assert value["mode"] != "off"
        assert type(food) is dict and set(food) == {
            "source", "source_turn", "timing", "counts", "controller_ids"}
        assert food["source"] == "phase2_agent_pool" and food["timing"] == "phase2_entry"
        assert type(food["source_turn"]) is int and food["source_turn"] == value["source_turn"]
        assert valid_counts(food["counts"])
        assert type(food["controller_ids"]) is list and len(food["controller_ids"]) == size
        assert all(item is None or type(item) is int and item >= 0 for item in food["controller_ids"])
    fields.pop("regional_population")
    return fields


def _run_workload(spec, tmp_path, monkeypatch):
    # Fix the lane even in environments where the optional Rust extension exists.
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    # Causal provenance is recorded but the timeline stays provenance-free:
    # the frozen oracle pins every event once the additive fields are removed.
    monkeypatch.setattr("chronicler.provenance.LEGACY_TIMELINE", True)
    turns = []

    def capture(snapshot, text, events, named):
        data = [_frozen_snapshot(snapshot), text,
                [legacy_event_dump(event) for event in events],
                [event.model_dump(mode="json") for event in named]]
        turns.append(hashlib.sha256(json.dumps(data, ensure_ascii=False,
                                              separators=(",", ":")).encode()).hexdigest())

    with rng_trace(tmp_path / "rng.jsonl") as trace:
        run(spec, tmp_path / "artifacts", on_turn=capture)
    return turns, trace


@pytest.mark.parametrize("name", BASELINE["workloads"])
def test_corrected_baseline_all_turns_and_rng(name, tmp_path, monkeypatch):
    expected = BASELINE["workloads"][name]
    turns, trace = _run_workload(expected["spec"], tmp_path, monkeypatch)
    assert turns == expected["turn_sha256"]
    assert trace == expected["rng"]


def _projection_case(make_world):
    from chronicler.models import TurnSnapshot
    from chronicler.regional_population import snapshot_fields

    world = make_world()
    world.agent_mode = "off"
    world.turn = 1
    world.regions[0].population, world.regions[1].population = 11, 17
    snapshot = TurnSnapshot(turn=1, civ_stats={}, region_control={"R0": "Civ0"},
                            relationships={}, ecology={"R0": {"soil": 0.4}},
                            food={"sufficiency": [1.0, None], "aid": []},
                            **snapshot_fields(world, None, TurnObservation(0, 1, None)))
    return snapshot.model_dump(mode="json")


def _snapshot_double(fields):
    return SimpleNamespace(model_dump=lambda **kwargs: deepcopy(fields))


def test_frozen_projection_retains_every_other_snapshot_field(make_world):
    fields = _projection_case(make_world)
    original = deepcopy(fields)
    # This is a real v1 producer observation, not a made-up empty dictionary.
    assert fields["regional_population"]["counts"] == [11, 17]
    assert fields["regional_population"]["sources"] == ["python_region_state"] * 2
    legacy = {key: value for key, value in fields.items() if key != "regional_population"}
    expected = _frozen_snapshot(_snapshot_double(fields))
    assert expected == legacy and fields == original
    assert _frozen_snapshot(_snapshot_double(legacy)) == legacy
    digest = lambda row: hashlib.sha256(json.dumps(row, ensure_ascii=False,
                                                  separators=(",", ":")).encode()).hexdigest()
    for key in legacy:
        changed = deepcopy(fields)
        # Every retained field stays in the exact hash, including empty tables,
        # ordering, numeric values and nested ecology/food observations.
        changed[key] = {"changed_pre_existing_field": changed[key]}
        if key == "turn":
            with pytest.raises(AssertionError):
                _frozen_snapshot(_snapshot_double(changed))
        else:
            assert digest(_frozen_snapshot(_snapshot_double(changed))) != digest(expected), key
    for key, replacement in (("ecology", {"R0": {"soil": 0.4000000000000001}}),
                             ("food", {"sufficiency": [0.99, None], "aid": []})):
        changed = deepcopy(fields); changed[key] = replacement
        assert digest(_frozen_snapshot(_snapshot_double(changed))) != digest(expected)
    changed = deepcopy(fields); changed["future_retained_export"] = 1
    assert digest(_frozen_snapshot(_snapshot_double(changed))) != digest(expected)


@pytest.mark.parametrize("version", [None, False, True, 2, "1", 1.0])
def test_frozen_projection_refuses_unreviewed_regional_versions(make_world, version):
    fields = _projection_case(make_world)
    fields["regional_population"]["schema_version"] = version
    with pytest.raises(AssertionError):
        _frozen_snapshot(_snapshot_double(fields))


@pytest.mark.parametrize("malformation", ["null", "missing_key", "extra_key", "counts_bool",
    "counts_negative", "counts_float", "sources_length", "unknown_source", "unknown_mode",
    "agent_unpaired", "food_shape", "wrong_epoch"])
def test_frozen_projection_refuses_malformed_regional_shape(make_world, malformation):
    fields = _projection_case(make_world)
    value = fields["regional_population"]
    if malformation == "null": fields["regional_population"] = None
    elif malformation == "missing_key": value.pop("counts")
    elif malformation == "extra_key": value["unreviewed"] = 1
    elif malformation == "counts_bool": value["counts"][0] = True
    elif malformation == "counts_negative": value["counts"][0] = -1
    elif malformation == "counts_float": value["counts"][0] = 11.0
    elif malformation == "sources_length": value["sources"].pop()
    elif malformation == "unknown_source": value["sources"][0] = "estimated_from_civ"
    elif malformation == "unknown_mode": value["mode"] = "estimated"
    elif malformation == "agent_unpaired": value["agent_source"] = "native_region_alive_count"
    elif malformation == "food_shape": value["food_weights"] = {}
    elif malformation == "wrong_epoch": value["completed_turn"] = 2
    with pytest.raises(AssertionError):
        _frozen_snapshot(_snapshot_double(fields))


@pytest.mark.parametrize("link", ORACLE_CHAIN)
def test_rolled_forward_oracle_differs_only_where_declared(link):
    """Each declared correction changes only its workloads, from its turn on."""
    prior_oracle, oracle = ORACLE_CHAIN[link]
    first_changed = {}
    for correction in oracle["provenance"]["corrections"]:
        for name, index in correction["workloads"].items():
            first_changed[name] = min(index, first_changed.get(name, index))
    assert set(oracle["workloads"]) == set(prior_oracle["workloads"])
    for name, prior in prior_oracle["workloads"].items():
        current = oracle["workloads"][name]
        assert current["spec"] == prior["spec"]
        if name not in first_changed:
            assert current == prior, name
            continue
        old, new = prior["turn_sha256"], current["turn_sha256"]
        assert len(old) == len(new)
        assert next(i for i, (a, b) in enumerate(zip(old, new)) if a != b) == first_changed[name]


def test_off_mode_tech_regression_removes_era_bonus_immediately(monkeypatch):
    """T1-3: off mode routes tech regression with ``acc=None`` so the era bonus
    is removed at once, not recorded into an already-flushed accumulator.

    This used to be proven by reverting T1-3 and recovering the 423a67c
    ``wide`` oracle. After the 2026-10 extinction fix no golden workload
    regresses (see the fixture notes), so force one regression instead.
    """
    import chronicler.emergence as emergence
    from chronicler import simulation as sim
    from chronicler.models import ActionType, TechEra
    from chronicler.tech import ERA_BONUSES
    from chronicler.world_gen import generate_world

    world = generate_world(seed=77, num_civs=2, num_regions=6)
    world.agent_mode = "off"
    real = emergence.check_tech_regression
    seen = []

    def forced(world, black_swan_fired=False, acc=None):
        civ = world.civilizations[0]
        civ.tech_era = TechEra.IRON
        civ.decline_turns = max(1, civ.decline_turns)
        civ.was_in_twilight = False
        civ.culture = 0  # no culture resistance: the twilight trigger is certain
        civ.economy = 50
        events = real(world, black_swan_fired=black_swan_fired, acc=acc)
        seen.append((acc, civ.tech_era, civ.economy, [e.event_type for e in events]))
        return events

    monkeypatch.setitem(emergence._REGRESSION_TRIGGERS, "entered_twilight", 1.0)
    monkeypatch.setattr(emergence, "check_tech_regression", forced)
    sim.run_turn(world, lambda *a: ActionType.DEVELOP, lambda w, e: "", seed=77)
    assert seen == [(None, TechEra.BRONZE, 50 - ERA_BONUSES[TechEra.IRON]["economy"],
                     ["tech_regression"])]


def test_corrected_oracle_keeps_unaffected_workload_exact():
    # Historical file-level check on the frozen backlog oracle (the extinction
    # fix changes every workload from turn 0; see its provenance).
    historical = json.loads((FIXTURES / "public_edf7299.json").read_text())
    assert BACKLOG_BASELINE["workloads"]["single"] == historical["workloads"]["single"]
    # Real captures first affect snapshot intelligence at these turns. The
    # corresponding lifecycle tests assert the new +0.3 source and its expiry.
    for name, first_changed_index in (("standard", 0), ("wide", 3)):
        old = historical["workloads"][name]["turn_sha256"]
        new = BACKLOG_BASELINE["workloads"][name]["turn_sha256"]
        assert next(i for i, pair in enumerate(zip(old, new)) if pair[0] != pair[1]) == first_changed_index


@pytest.mark.parametrize("case", PERCEPTIONS["cases"])
def test_perception_public_baseline_boundaries(case, monkeypatch):
    observer = SimpleNamespace(name="Observer")
    target = SimpleNamespace(name="Target", military=case["actual"])
    world = SimpleNamespace(seed=42, turn=7)
    monkeypatch.setattr("chronicler.intelligence.compute_accuracy",
                        lambda *args: case["accuracy"])
    # Cover no contact, exact knowledge, integer noise truncation, clipping,
    # negative/high actual values, and caller-specific max_value from old code.
    assert get_perceived_stat(observer, target, "military", world, case["max_value"]) == case["expected"]
    assert _get_perceived_stat_with_accuracy(
        observer, target, "military", world, case["max_value"],
        accuracy=case["accuracy"],
    ) == case["expected"]


def test_ordinary_perception_reads_recompute_after_world_change(monkeypatch):
    observer = SimpleNamespace(name="Observer")
    target = SimpleNamespace(name="Target", military=65)
    world = SimpleNamespace(seed=42, turn=7, accuracy=0.0)
    monkeypatch.setattr("chronicler.intelligence.compute_accuracy", lambda *args: world.accuracy)
    assert get_perceived_stat(observer, target, "military", world) is None
    world.accuracy = 1.0
    assert get_perceived_stat(observer, target, "military", world) == 65


def test_duplicate_names_preserve_discarded_rng_draws(tmp_path, monkeypatch):
    import argparse
    from chronicler.main import execute_run
    from chronicler.models import FactionState, FactionType
    from chronicler.world_gen import generate_world

    expected = json.loads((FIXTURES / "duplicates_edf7299.json").read_text())
    world = generate_world(seed=42, num_civs=3, num_regions=6)
    first, second, target = world.civilizations
    first.name = second.name = "Twin"
    first.factions = FactionState(influence={FactionType.MILITARY: 1.0,
                                           FactionType.MERCHANT: 0.0, FactionType.CULTURAL: 0.0})
    second.factions = FactionState(influence={FactionType.MILITARY: 0.0,
                                            FactionType.MERCHANT: 0.0, FactionType.CULTURAL: 1.0})
    # First observer has exact knowledge; second has noisy knowledge. Reusing the
    # last name-keyed entry for the first would create otherwise absent RNG draws,
    # even though its duplicate output row is later overwritten.
    first.leader.grudges = [{"rival_civ": target.name, "intensity": 0.8} for _ in range(10)]
    world.invalidate_civ_map()
    # Since 2026-10 faction bonuses need contact (docs/integration/procedural-gates.md);
    # the twins and the target are in contact, as the frozen capture assumed.
    monkeypatch.setattr("chronicler.intelligence._ledger_contact", lambda *args: True)

    def tick(world, *args, **kwargs):
        world.turn += 1
        return TurnResult("", TurnObservation(world.turn - 1, world.turn, None))

    monkeypatch.setattr("chronicler.main.run_turn_result", tick)
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.bundle.datetime", FixedDateTime)
    turns = []

    def capture(snapshot, text, events, named):
        data = [_frozen_snapshot(snapshot), text,
                [event.model_dump(mode="json") for event in events],
                [event.model_dump(mode="json") for event in named]]
        turns.append(hashlib.sha256(json.dumps(data, ensure_ascii=False,
                                              separators=(",", ":")).encode()).hexdigest())

    args = argparse.Namespace(seed=42, turns=2, civs=3, regions=6,
                              output=str(tmp_path / "chronicle.md"), state=str(tmp_path / "state.json"),
                              resume=None, reflection_interval=10, llm_actions=False, scenario=None,
                              simulate_only=True, agents="off")
    with rng_trace(tmp_path / "rng.jsonl") as trace:
        execute_run(args, world=world, on_turn=capture)
    assert turns == expected["turn_sha256"]
    assert trace == expected["rng"]


def test_benchmark_comparison_rejects_rng_artifact_and_environment_changes():
    from copy import deepcopy
    from scripts.benchmark_headless import compare

    original = {"environment": {"python": "fixed"}, "workloads": {
        "small": {"workload": {"seed": 42}, "equivalence": {
            "artifacts": {"bundle": "hash"}, "rng": "hash", "turns": ["hash"]},
            "median_seconds": 1.0, "peak_tracemalloc_bytes": 100}}}
    assert compare(original, original)["passed"]
    for change in ("environment", "artifacts", "rng", "turns", "workload"):
        changed = deepcopy(original)
        if change == "environment":
            changed["environment"]["python"] = "different"
        elif change == "workload":
            changed["workloads"]["small"]["workload"]["seed"] = 43
        else:
            changed["workloads"]["small"]["equivalence"][change] = "different"
        assert not compare(original, changed)["passed"]
