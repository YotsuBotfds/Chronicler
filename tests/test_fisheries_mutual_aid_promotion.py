"""Promotion of the fishery stock and adjacent mutual aid to production switches.

Covers the CLI/new-world defaults and saved-setting semantics, the narrated
fishery collapse/recovery transitions, mutual aid's off-mode dormancy, and the
hybrid save/resume boundary of the fishery's persisted Phase 2 inputs.
See docs/integration/fisheries-mutual-aid-promotion.md.
"""
from __future__ import annotations

import argparse
import json

import pyarrow as pa
import pytest

from chronicler.ecology import tick_ecology
from chronicler.economy import EconomyResult
from chronicler.experimental import fisheries
from chronicler.experimental.fisheries import (
    COLLAPSE_STOCK, NEW_WORLD_REFERENCE_WORKERS, RECOVERED_STOCK, FisheryConfig,
    fishery_stock_events, set_fisheries_enabled,
)
from chronicler.models import ActionType, ClimatePhase, EMPTY_SLOT, ResourceType, WorldState
from chronicler import mutual_aid
from chronicler.mutual_aid import dispatch_mutual_aid, mutual_aid_active, observe_mutual_aid


@pytest.fixture
def fish_world(make_world):
    world = make_world(num_civs=1)
    region = world.regions[0]
    region.terrain = "coast"
    region.population = 2000
    region.carrying_capacity = 3000
    region.resource_types = [ResourceType.FISH, ResourceType.ORE, EMPTY_SLOT]
    region.resource_base_yields = [1.0, 0.5, 0.0]
    region.resource_effective_yields = [1.0, 0.5, 0.0]
    region.resource_current_yields = [1.0, 0.5, 0.0]
    world.civilizations[0].population = region.population
    return world


def _cli_args(tmp_path, *, turns=2, agents="off", **switches):
    return argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8, output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents=agents,
        **switches,
    )


# --- switches, defaults and saved settings ----------------------------------------------------

def test_cli_switches_are_tristate():
    from chronicler.main import _build_parser
    parser = _build_parser()
    assert parser.parse_args([]).fisheries is None
    assert parser.parse_args(["--fisheries"]).fisheries is True
    assert parser.parse_args(["--no-fisheries"]).fisheries is False
    assert parser.parse_args([]).mutual_aid is None


def test_new_worlds_follow_the_defaults(tmp_path):
    from chronicler.main import execute_run
    execute_run(_cli_args(tmp_path))
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["fishery_experiment"]["enabled"] is fisheries.DEFAULT_ENABLED_FOR_NEW_WORLDS
    assert state["mutual_aid_enabled"] is mutual_aid.DEFAULT_ENABLED_FOR_NEW_WORLDS


def test_explicit_off_keeps_the_dormant_config_bytes(tmp_path):
    from chronicler.main import execute_run
    execute_run(_cli_args(tmp_path, fisheries=False, mutual_aid=False))
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["fishery_experiment"] == FisheryConfig().model_dump()
    assert state["mutual_aid_enabled"] is False
    assert all("fishery_collapsed" not in region for region in state["regions"])


def test_new_world_gets_living_world_calibration_and_resume_keeps_it(tmp_path):
    from chronicler.main import execute_run
    on = tmp_path / "on"
    execute_run(_cli_args(on, fisheries=True))
    saved = json.loads((on / "state.json").read_text())["fishery_experiment"]
    assert saved["enabled"] is True
    assert saved["reference_workers"] == NEW_WORLD_REFERENCE_WORKERS
    resumed = _cli_args(on, turns=4)
    resumed.resume = str(on / "state.json")
    resumed.state = str(on / "resumed.json")
    execute_run(resumed)
    assert json.loads((on / "resumed.json").read_text())["fishery_experiment"] == saved
    # An explicit switch on resume flips only ``enabled``; memory stays frozen.
    disabled = _cli_args(on, turns=5, fisheries=False)
    disabled.resume = str(on / "resumed.json")
    disabled.state = str(on / "disabled.json")
    execute_run(disabled)
    after = json.loads((on / "disabled.json").read_text())["fishery_experiment"]
    assert after == {**saved, "enabled": False}


def test_resumed_legacy_world_keeps_its_parameters_when_enabled(fish_world):
    set_fisheries_enabled(fish_world, True)  # not a new world
    assert fish_world.fishery_experiment == FisheryConfig(enabled=True)
    set_fisheries_enabled(fish_world, False)
    assert fish_world.fishery_experiment == FisheryConfig()


def test_live_new_worlds_follow_the_defaults():
    import inspect
    from chronicler import live
    source = inspect.getsource(live)
    assert "set_fisheries_enabled(world" in source and "_AID_DEFAULT" in source


def test_gate_runner_forwards_explicit_switches():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "m53b_run_validation.py"
    spec = importlib.util.spec_from_file_location("m53b_run_validation_promo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    forward = module._fishery_aid_args
    assert forward(argparse.Namespace(fisheries=None, mutual_aid=None)) == []
    assert forward(argparse.Namespace(fisheries=True, mutual_aid=False)) == ["--fisheries", "--no-mutual-aid"]
    # The CLI rejects an explicit --mutual-aid with --agents off; aid is dormant there.
    assert forward(argparse.Namespace(fisheries=False, mutual_aid=True), "off") == ["--no-fisheries"]
    assert forward(argparse.Namespace(fisheries=None, mutual_aid=True), "hybrid") == ["--mutual-aid"]


# --- fishery collapse / recovery narration ----------------------------------------------------

def test_collapse_and_recovery_are_narrated_once_with_hysteresis(fish_world):
    fish_world.fishery_experiment.enabled = True
    region = fish_world.regions[0]
    trace = []
    for stock in (0.5, 0.3, COLLAPSE_STOCK - 0.01, 0.1, 0.4, RECOVERED_STOCK - 0.01,
                  RECOVERED_STOCK, 0.7, COLLAPSE_STOCK - 0.05):
        region.fishery_stocks[0] = stock
        fish_world.turn += 1
        trace.append([e.event_type for e in fishery_stock_events(fish_world)])
    assert trace == [[], [], ["fishery_collapse"], [], [], [], ["fishery_recovery"], [],
                     ["fishery_collapse"]]
    assert region.fishery_collapsed == [0]
    events = fishery_stock_events(fish_world)
    assert events == []
    fish_world.turn += 1
    region.fishery_stocks[0] = 0.9
    (recovery,) = fishery_stock_events(fish_world)
    assert recovery.actors == [region.controller] and recovery.importance == 6
    assert region.name in recovery.description and region.fishery_collapsed is None


def test_removed_fish_slot_forgets_collapse_silently(fish_world):
    fish_world.fishery_experiment.enabled = True
    region = fish_world.regions[0]
    region.fishery_stocks[0] = 0.1
    assert [e.event_type for e in fishery_stock_events(fish_world)] == ["fishery_collapse"]
    region.resource_types[0] = ResourceType.GRAIN
    assert fishery_stock_events(fish_world) == []
    assert region.fishery_collapsed is None


def test_disabled_fishery_neither_reads_nor_writes_collapse_memory(fish_world):
    region = fish_world.regions[0]
    region.fishery_stocks[0] = 0.05
    region.fishery_collapsed = [0]
    before = fish_world.model_dump()
    assert fishery_stock_events(fish_world) == []
    assert fish_world.model_dump() == before


def test_collapse_memory_round_trips_and_is_omitted_while_none(fish_world, tmp_path):
    region = fish_world.regions[0]
    assert "fishery_collapsed" not in json.loads(region.model_dump_json())
    region.fishery_collapsed = [0]
    path = tmp_path / "state.json"
    fish_world.save(path)
    assert WorldState.load(path).regions[0].fishery_collapsed == [0]


def test_ecology_tick_returns_the_collapse_event(fish_world):
    fish_world.fishery_experiment.enabled = True
    fish_world.regions[0].fishery_stocks[0] = COLLAPSE_STOCK + 0.02  # 400 proxy workers overfish
    kinds = []
    for turn in range(3):
        fish_world.turn = turn
        kinds += [e.event_type for e in tick_ecology(fish_world, ClimatePhase.TEMPERATE)]
    assert kinds.count("fishery_collapse") == 1
    assert fish_world.regions[0].fishery_stocks[0] < COLLAPSE_STOCK


def test_new_world_calibration_lets_a_dense_coast_overfish():
    """About 40 fishers on one base-yield slot: sustainable at 200, overfished at 100."""
    from chronicler.experimental.fisheries import step_fishery
    stocks = {}
    for reference in (200, NEW_WORLD_REFERENCE_WORKERS):
        config = FisheryConfig(enabled=True, reference_workers=reference)
        stock = 1.0
        for _ in range(400):
            stock = step_fishery(stock, 1.0, 1.0, 40, config).stock
        stocks[reference] = stock
    assert stocks[200] > 0.3
    assert stocks[NEW_WORLD_REFERENCE_WORKERS] < COLLAPSE_STOCK


# --- mutual aid dormancy in aggregate mode ----------------------------------------------------

def test_explicit_mutual_aid_with_agents_off_is_rejected(tmp_path):
    from chronicler.main import execute_run
    with pytest.raises(ValueError, match="agent-backed"):
        execute_run(_cli_args(tmp_path, mutual_aid=True))


def test_saved_mutual_aid_is_dormant_in_aggregate_mode(tmp_path):
    from chronicler.main import execute_run
    first = tmp_path / "first"
    execute_run(_cli_args(first, mutual_aid=False))
    state = json.loads((first / "state.json").read_text())
    state["mutual_aid_enabled"] = True
    (first / "enabled.json").write_text(json.dumps(state))
    resumed = _cli_args(first, turns=4)
    resumed.resume = str(first / "enabled.json")
    resumed.state = str(first / "resumed.json")
    execute_run(resumed)  # no error: dormant
    after = json.loads((first / "resumed.json").read_text())
    assert after["mutual_aid_enabled"] is True
    assert after["mutual_aid_state"] == {} and after["mutual_aid_last_transfers"] == []
    assert not any(e["event_type"] == "mutual_aid" for e in after["events_timeline"])


def _aid_world(make_world):
    from chronicler.models import Region
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    world.mutual_aid_enabled = True
    donor = world.regions[0]
    donor.name = "Granary"
    donor.population = 20
    donor.adjacencies = ["Mine"]
    donor.stockpile.goods = {"grain": 100.0}
    mine = Region(name="Mine", terrain="hills", carrying_capacity=60, population=20,
                  resources="mineral", controller=civ.name, adjacencies=["Granary"],
                  resource_types=[5, 255, 255], resource_effective_yields=[0.5, 0, 0])
    world.regions.append(mine)
    civ.regions = ["Granary", "Mine"]
    world.invalidate_region_map()
    ids = [0] * 20 + [1] * 20
    snap = pa.record_batch({"region": pa.array(ids, type=pa.uint16()),
                            "occupation": pa.array([0] * 40, type=pa.uint8())})
    return world, snap


@pytest.mark.parametrize("mode", [None, "off"])
def test_aggregate_mode_aid_is_a_strict_noop(make_world, mode):
    world, snap = _aid_world(make_world)
    world.agent_mode = mode
    assert not mutual_aid_active(world)
    before = world.model_dump_json()
    for turn in range(4):
        world.turn = turn
        observe_mutual_aid(world, EconomyResult(food_sufficiency={"Granary": 1.5, "Mine": 0.1}), snap)
        assert dispatch_mutual_aid(world, snap) == []
    world.turn = 0
    assert world.model_dump_json() == before


def test_relief_convoy_event_is_narratable(make_world):
    world, snap = _aid_world(make_world)
    world.agent_mode = "demographics-only"
    assert mutual_aid_active(world)
    for turn in range(3):
        world.turn = turn
        observe_mutual_aid(world, EconomyResult(food_sufficiency={"Granary": 1.5, "Mine": 0.1}), snap)
    world.turn = 3
    (event,) = dispatch_mutual_aid(world, snap)
    assert event.event_type == "mutual_aid" and event.actors == [world.civilizations[0].name]
    assert "relief convoy" in event.description and "Granary" in event.description
    assert "Mine" in event.description


# --- hybrid save/resume boundary ----------------------------------------------------------------

def _hybrid_fish_world(fish_world):
    pytest.importorskip("chronicler_agents")
    world = fish_world.model_copy(deep=True)
    world.agent_mode = "hybrid"
    set_fisheries_enabled(world, True, new_world=True)
    world.mutual_aid_enabled = True
    region = world.regions[0]
    region.population = 120
    region.carrying_capacity = 200
    world.civilizations[0].population = 120
    region.fishery_stocks[0] = 0.3
    return world


def _capture_fish_inputs(monkeypatch):
    """Record each world's packed fish-slot economy input (yield, catch credit)."""
    from chronicler import economy
    original = economy.build_economy_region_input_batch
    seen: dict[int, list] = {}

    def wrapped(world, *args, **kwargs):
        batch = original(world, *args, **kwargs)
        row = batch.to_pylist()[0]
        seen.setdefault(id(world), []).append((row["resource_yield_0"], row["fishery_catch_budget_0"]))
        return batch

    monkeypatch.setattr(economy, "build_economy_region_input_batch", wrapped)
    return seen


@pytest.mark.native
def test_hybrid_resume_continues_the_fishery_from_its_saved_state(fish_world, tmp_path, monkeypatch):
    """The agent pool is rebuilt on resume (as for every system), but the
    fishery's persisted Phase 2 inputs at the boundary turn are exactly those
    of the uninterrupted run, and the saved catch credit still caps the catch."""
    from chronicler.agent_bridge import AgentBridge
    from chronicler.simulation import run_turn
    world = _hybrid_fish_world(fish_world)
    bridge = AgentBridge(world, mode="hybrid")
    for turn in range(4):
        run_turn(world, lambda *_: ActionType.DEVELOP, lambda *_: "", seed=42 + turn, agent_bridge=bridge)
    path = tmp_path / "state.json"
    world.save(path)
    resumed = WorldState.load(path)
    for field in ("fishery_stocks", "fishery_yield_ratios", "fishery_catch_budgets", "fishery_collapsed"):
        assert getattr(resumed.regions[0], field) == getattr(world.regions[0], field)
    assert resumed.fishery_experiment == world.fishery_experiment
    assert resumed.mutual_aid_state == world.mutual_aid_state
    saved_stock = world.regions[0].fishery_stocks[0]
    saved_budget = world.regions[0].fishery_catch_budgets[0]
    assert saved_budget is not None and saved_budget > 0

    seen = _capture_fish_inputs(monkeypatch)
    resumed_bridge = AgentBridge(resumed, mode="hybrid")
    for offset in range(3):
        seed = 46 + offset
        run_turn(world, lambda *_: ActionType.DEVELOP, lambda *_: "", seed=seed, agent_bridge=bridge)
        run_turn(resumed, lambda *_: ActionType.DEVELOP, lambda *_: "", seed=seed, agent_bridge=resumed_bridge)
        for w in (world, resumed):
            assert 0.0 <= w.regions[0].fishery_stocks[0] <= 1.0
    straight_inputs, resumed_inputs = seen[id(world)], seen[id(resumed)]
    assert len(straight_inputs) == len(resumed_inputs) == 3
    # Boundary turn: identical fish yield (lagged ratio) and catch credit.
    assert resumed_inputs[0] == straight_inputs[0]
    assert resumed_inputs[0][1] == pytest.approx(saved_budget, rel=1e-6)
    # The stock keeps evolving from the saved value (no reset to full stock).
    later = resumed.regions[0].fishery_stocks[0]
    assert abs(later - saved_stock) < 0.1 and later < 1.0
