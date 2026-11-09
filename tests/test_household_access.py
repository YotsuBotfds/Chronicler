"""DEP-7 household access metrics (observation only, default off).

Pure Python: the frames L2 (food allocation) and L6b (household retail)
settle are written by hand here, so no native extension is needed. The
package's registration as ``--household-access`` (livelihoods switch, catalog
requirement, manifest key) is not part of this module's surface yet.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from chronicler import household_access as HA
from chronicler.food_allocation_state import FoodAllocationState
from chronicler.household_access_state import COUNTERS, HouseholdAccessState

L2_TOTALS = {
    "alive": 100.0, "rations_available": 90.0, "relief_available": 0.0, "allocated": 80.0, "unallocated": 10.0,
    "relief_to_targeted": 0.0, "shortfall": 20.0, "below_floor": 10.0, "people_poorer_half": 50.0,
    "shortfall_poorer_half": 15.0, "people_richer_half": 50.0, "shortfall_richer_half": 5.0,
    "children": 30.0, "shortfall_children": 8.0, "scarce_regions": 1.0, "relief_unknown_regions": 0,
}
L2_REGION = {
    "region": 1, "scarce": 1, "phase2_alive": 40, "alive": 40, "households": 12, "sufficiency": 0.6,
    "rations_available": 30.0, "relief_available": 0.0, "allocated": 24.0, "unallocated": 6.0,
    "relief_to_targeted": 0.0, "shortfall": 16.0, "below_floor": 10, "fully_fed": 8, "min_ration": 0.2,
    "max_ration": 1.0, "people_poorer_half": 20, "shortfall_poorer_half": 12.0, "people_richer_half": 20,
    "shortfall_richer_half": 4.0, "children": 10, "shortfall_children": 5.0,
}
RETAIL_ROW = {"region": 2.0, "persons": 20.0, "rations": 15.0, "priced_out_persons": 4.0,
              "priced_out_deficit": 2.5, "offer_short_persons": 1.0, "children": 6.0, "deficit": 3.0}


def _world(turn=5, *, l2=True, retail=None):
    alloc = FoodAllocationState()
    if l2:
        alloc.frame_turn = turn
        alloc.totals = dict(L2_TOTALS)
        alloc.regions = [dict(L2_REGION)]
    books = {rid: SimpleNamespace(provisioning=row) for rid, row in (retail or {}).items()}
    retail_state = None if retail is None else SimpleNamespace(_turn=SimpleNamespace(turn=turn, books=books))
    world = SimpleNamespace(turn=turn, agent_mode="hybrid", regions=[None] * 4,
                            livelihoods=SimpleNamespace(food_allocation=alloc, household_retail=retail_state,
                                                        household_access=None))
    HA.set_household_access_enabled(world, True)
    return world


def test_l2_only_frame_definitions():
    frame = HA.compute_frame(L2_TOTALS, [L2_REGION], None)
    world = frame["world"]
    assert world["alive"] == 100 and world["allocation_alive"] == 100 and world["retail_alive"] == 0
    assert world["calories_met_share"] == 0.8 and world["shortfall_depth"] == 0.2
    assert world["below_floor_share"] == 0.1
    assert (world["poorer_half_shortfall_depth"], world["richer_half_shortfall_depth"]) == (0.3, 0.1)
    assert world["poorer_richer_ratio"] == 3.0 and world["child_shortfall_share"] == 0.4
    # Without a retail frame, pricing is unobserved (None), not zero.
    assert world["priced_out_persons"] is None and world["priced_out_share"] is None
    assert world["priced_out_deficit"] is None
    [row] = frame["regions"]
    assert row["region"] == 1 and row["source"] == "allocation" and row["alive"] == 40
    assert (row["calories_met_share"], row["shortfall_depth"], row["below_floor_share"]) == (0.6, 0.4, 0.25)
    assert row["poorer_richer_ratio"] == 3.0 and row["child_shortfall_share"] == 0.3125
    assert row["priced_out_persons"] is None


def test_retail_rows_join_the_world_aggregates():
    frame = HA.compute_frame(L2_TOTALS, [L2_REGION], {2: RETAIL_ROW})
    world = frame["world"]
    assert world["alive"] == 120 and world["retail_alive"] == 20 and world["retail_regions"] == 1
    assert world["calories_met_share"] == round(95 / 120, 6)
    assert world["shortfall_depth"] == round(25 / 120, 6)
    # The L2-only metrics stay over L2's people.
    assert world["below_floor_share"] == 0.1 and world["poorer_richer_ratio"] == 3.0
    assert world["priced_out_persons"] == 4 and world["priced_out_share"] == 0.2
    assert world["priced_out_deficit"] == 2.5
    assert [r["region"] for r in frame["regions"]] == [1, 2]
    retail = frame["regions"][1]
    assert retail["source"] == "retail" and retail["alive"] == 20
    assert (retail["calories_met_share"], retail["shortfall_depth"]) == (0.75, 0.25)
    assert retail["below_floor_share"] is None and retail["poorer_richer_ratio"] is None
    assert (retail["priced_out_persons"], retail["priced_out_deficit"]) == (4, 2.5)


def test_unobserved_is_none_never_zero():
    assert HA.compute_frame(None, (), None) is None
    assert HA.compute_frame(None, (), {}) is None
    retail_only = HA.compute_frame(None, (), {2: RETAIL_ROW})
    assert retail_only["world"] is None and [r["region"] for r in retail_only["regions"]] == [2]
    empty = HA.compute_frame({key: 0.0 for key in L2_TOTALS}, [], None)["world"]
    for key in ("calories_met_share", "shortfall_depth", "below_floor_share", "poorer_half_shortfall_depth",
                "richer_half_shortfall_depth", "poorer_richer_ratio", "child_shortfall_share"):
        assert empty[key] is None, key
    no_richer_shortfall = HA.compute_frame({**L2_TOTALS, "shortfall_richer_half": 0.0}, [], None)["world"]
    assert no_richer_shortfall["richer_half_shortfall_depth"] == 0.0
    assert no_richer_shortfall["poorer_richer_ratio"] is None


def test_hook_observes_without_changing_the_frames_it_reads():
    world = _world(retail={2: dict(RETAIL_ROW)})
    before = (copy.deepcopy(world.livelihoods.food_allocation.model_dump()),
              copy.deepcopy(world.livelihoods.household_retail._turn.books[2].provisioning))
    assert HA.after_agent_tick(world, agent_bridge=None) == []
    after = (world.livelihoods.food_allocation.model_dump(),
             world.livelihoods.household_retail._turn.books[2].provisioning)
    assert after == before
    state = world.livelihoods.household_access
    assert state.frame_turn == 5 and state.frame["world"]["alive"] == 120


def test_counters_accumulate_and_snapshot_is_dated_by_source_turn():
    world = _world(turn=5, retail={2: dict(RETAIL_ROW)})
    HA.after_agent_tick(world, None)
    world.turn = 6
    snap = HA.snapshot_summary(world)
    assert snap["schema_version"] == 1 and snap["stage"] == "DEP-7" and snap["source_turn"] == 5
    assert snap["world"]["alive"] == 120 and [r["region"] for r in snap["regions"]] == [1, 2]
    # Turn 6: the allocation frame is still turn 5's (not observed this turn).
    HA.after_agent_tick(world, None)
    world.turn = 7
    snap = HA.snapshot_summary(world)
    assert snap["source_turn"] == 6 and snap["world"] is None and snap["regions"] is None
    counters = snap["counters"]
    assert list(counters) == [k for k in COUNTERS if k in counters]
    assert counters["turns_observed"] == 1 and counters["turns_unobserved"] == 1
    assert counters["person_turns"] == 120 and counters["allocation_person_turns"] == 100
    assert counters["retail_person_turns"] == 20 and counters["shortfall"] == 25
    assert counters["priced_out_person_turns"] == 4 and counters["priced_out_deficit"] == 2.5
    # Turn 7 observed again: cumulative.
    alloc = world.livelihoods.food_allocation
    alloc.frame_turn = 7
    world.livelihoods.household_retail._turn.turn = 7
    HA.after_agent_tick(world, None)
    world.turn = 8
    snap = HA.snapshot_summary(world)
    assert snap["source_turn"] == 7 and snap["world"]["alive"] == 120
    assert snap["counters"]["priced_out_person_turns"] == 8 and snap["counters"]["turns_observed"] == 2
    assert snap["primaries"] == {"P1_poorer_half_shortfall_per_1000": 300.0,
                                 "P2_priced_out_per_1000": round(1000 * 8 / 240, 6)}


def test_retail_frame_of_another_turn_is_not_read():
    world = _world(turn=5, retail={2: dict(RETAIL_ROW)})
    world.livelihoods.household_retail._turn.turn = 4
    HA.after_agent_tick(world, None)
    state = world.livelihoods.household_access
    assert state.frame["world"]["retail_alive"] == 0 and "retail_person_turns" not in state.counters


def test_provisioning_rows_copies_settled_rows_only():
    from chronicler.household_retail import provisioning_rows
    row = dict(RETAIL_ROW)
    books = {3: SimpleNamespace(provisioning=None), 2: SimpleNamespace(provisioning=row)}
    world = SimpleNamespace(turn=5, livelihoods=SimpleNamespace(
        household_retail=SimpleNamespace(_turn=SimpleNamespace(turn=5, books=books))))
    out = provisioning_rows(world)
    assert out == {2: row} and out[2] is not row
    books[2].provisioning = None
    assert provisioning_rows(world) is None
    world.livelihoods.household_retail._turn = None
    assert provisioning_rows(world) is None


def test_switch_state_and_activity():
    world = _world()
    state = world.livelihoods.household_access
    assert HA.household_access_active(world)
    world.agent_mode = "off"
    assert not HA.household_access_active(world)
    world.agent_mode = "hybrid"
    HA.after_agent_tick(world, None)
    HA.set_household_access_enabled(world, False)
    assert not HA.household_access_active(world) and state.frame is None and state.frame_turn is None
    assert state.counters["turns_observed"] == 1          # lifetime counters are kept


def test_state_round_trips_through_serialization():
    world = _world(retail={2: dict(RETAIL_ROW)})
    HA.after_agent_tick(world, None)
    state = world.livelihoods.household_access
    restored = HouseholdAccessState.model_validate(json.loads(state.model_dump_json()))
    assert restored == state


def _bundle(seed, parts):
    history = [{"turn": t + 1, "livelihoods": {"schema_version": 1, "household_access": part}}
               for t, part in enumerate(parts)]
    return {"metadata": {"seed": seed}, "history": history}


def test_extractor_is_empty_without_the_part():
    assert HA.extract_household_access_metrics([{"history": [{"turn": 1}]}, {"history": []}]) == {}
    assert HA.extract_household_access_metrics([{"history": [{"livelihoods": {"food_allocation": {}}}]}]) == {}


def test_extractor_pools_observed_turns_and_final_primaries():
    world = _world(retail={2: dict(RETAIL_ROW)})
    HA.after_agent_tick(world, None)
    world.turn = 6
    observed = HA.snapshot_summary(world)
    unobserved = {**observed, "world": None, "regions": None}
    out = HA.extract_household_access_metrics([_bundle(1, [observed, unobserved]), _bundle(2, [unobserved])])
    assert out["runs"] == 2
    assert out["calories_met_share"] == {"min": round(95 / 120, 6), "p50": round(95 / 120, 6),
                                         "p90": round(95 / 120, 6), "max": round(95 / 120, 6)}
    assert out["priced_out_share"]["max"] == 0.2
    assert out["P1_poorer_half_shortfall_per_1000"]["max"] == 300.0


@pytest.fixture
def fixed_clock(monkeypatch):
    import datetime as real

    class _Fixed(real.datetime):
        @classmethod
        def now(cls, tz=None):
            return real.datetime(2026, 1, 1)

    monkeypatch.setattr("chronicler.analytics.datetime", _Fixed)


def test_default_report_bytes_are_unchanged(tmp_path, monkeypatch, fixed_clock):
    from chronicler.analytics import generate_report
    from tests.test_analytics import _write_batch
    batch_dir = _write_batch(tmp_path, num_runs=3)
    report = json.dumps(generate_report(batch_dir), sort_keys=False, default=str)
    assert "household_access" not in json.loads(report)
    # The same report with the extractor removed (the pre-DEP-7 report).
    monkeypatch.setattr(HA, "extract_household_access_metrics", lambda bundles: {})
    assert json.dumps(generate_report(batch_dir), sort_keys=False, default=str) == report


def test_report_has_the_section_when_bundles_carry_it(tmp_path, fixed_clock):
    from chronicler.analytics import generate_report
    from tests.test_analytics import _make_bundle
    world = _world(retail={2: dict(RETAIL_ROW)})
    HA.after_agent_tick(world, None)
    world.turn = 6
    part = HA.snapshot_summary(world)
    batch_dir = tmp_path / "batch_1"
    for seed in (1, 2):
        bundle = _make_bundle(seed=seed)
        for snap in bundle["history"]:
            snap["livelihoods"] = {"schema_version": 1, "household_access": part}
        run_dir = batch_dir / f"seed_{seed}"
        run_dir.mkdir(parents=True)
        (run_dir / "chronicle_bundle.json").write_text(json.dumps(bundle))
    report = generate_report(batch_dir)
    assert report["household_access"]["runs"] == 2
    assert report["household_access"]["P2_priced_out_per_1000"]["max"] == round(1000 * 4 / 120, 6)
