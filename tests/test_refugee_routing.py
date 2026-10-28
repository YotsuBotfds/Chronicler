"""Capacity-aware macro routing: actual arrivals, explicit losses, saved opt-in."""
from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
from pathlib import Path

import pytest

from chronicler.climate import process_migration
from chronicler.ecology import _check_famine_yield
from chronicler.models import (
    EMPTY_SLOT, Civilization, ClimatePhase, Disposition, Leader, Region, RegionEcology,
    Relationship, ResourceType, WorldState,
)
from chronicler.refugee_routing import (
    apportion_refugees, capacity_aware_refugees_enabled, set_capacity_aware_refugees_enabled,
)
from chronicler import utils


ROOT = Path(__file__).resolve().parents[1]


def _region(name, population, capacity, owner=None, adjacent=()):
    return Region(name=name, terrain="plains", resources="fertile", population=population,
                  carrying_capacity=capacity, controller=owner, adjacencies=list(adjacent),
                  ecology=RegionEcology(soil=1.0, water=1.0, forest_cover=0.3))


def _world(*destinations, source_population=25, source_capacity=12, mode="off", enabled=True):
    source = _region("Source", source_population, source_capacity, "A",
                     [r.name for r in reversed(destinations)])
    source.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    source.resource_base_yields = [0.1, 0.0, 0.0]
    regions = [source, *destinations]
    names = list(dict.fromkeys(r.controller for r in regions if r.controller))
    civs = [Civilization(name=name, population=sum(r.population for r in regions if r.controller == name),
                         military=20, economy=40, culture=30, stability=50,
                         leader=Leader(name=name, trait="cautious", reign_start=0),
                         regions=[r.name for r in regions if r.controller == name]) for name in names]
    world = WorldState(name="Routing", seed=42, regions=regions, civilizations=civs, agent_mode=mode)
    set_capacity_aware_refugees_enabled(world, enabled)
    for region in destinations:
        region.famine_cooldown = 1
    return world


def _pop(world):
    return [r.population for r in world.regions]


def _flow_check(world, operation):
    before = sum(_pop(world))
    ledger = utils.start_population_ledger()
    try:
        result = operation()
    finally:
        utils.stop_population_ledger()
    ledger.check(before, sum(_pop(world)))
    return result, ledger


def _famine(world):
    from chronicler.economy import EconomyResult
    # A large explicit toll drains all Source residents, in either macro mode.
    from chronicler.tuning import K_FAMINE_POP_LOSS
    world.tuning_overrides[K_FAMINE_POP_LOSS] = 100
    world.regions[0].food_severe_turns = 10
    return _check_famine_yield(world, {"Source": [0.0012, 0.0, 0.0]}, ClimatePhase.TEMPERATE,
                               0.12, 0.15, economy_result=EconomyResult(food_sufficiency={"Source": 0.0}))


def test_thirteen_migrants_bypass_a_full_destination_without_loss():
    world = _world(_region("Full", 10, 10, "B"), _region("Room", 0, 50, "B"))
    events, ledger = _flow_check(world, lambda: process_migration(world))
    assert _pop(world) == [12, 10, 13]
    assert (ledger.emigrated, ledger.immigrated, ledger.removed) == (13, 13, 0)
    assert [event.event_type for event in events] == ["migration"]
    assert world.civ_map["B"].population == 23
    assert world.civ_map["B"].stability == 47  # actual arrival, one destination


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_famine_routes_the_same_source_toll_to_available_room(mode):
    world = _world(_region("Full", 10, 10, "B"), _region("Room", 0, 50, "B"),
                   source_population=13, mode=mode)
    _events, ledger = _flow_check(world, lambda: _famine(world))
    assert _pop(world) == [0, 10, 13]
    assert (ledger.emigrated, ledger.immigrated) == (13, 13)
    assert world.civ_map["B"].stability == 45


def test_water_filling_redistributes_bounded_shares_and_remainders():
    world = _world(_region("Small", 0, 1), _region("Middle", 0, 3), _region("Large", 0, 20))
    plan = apportion_refugees(world, world.regions[1:], 13)
    assert [(r.name, amount) for r, amount in plan] == [("Small", 1), ("Middle", 3), ("Large", 9)]
    room = _world(*(_region(f"R{k}", 0, 100) for k in range(3)))
    assert [amount for _, amount in apportion_refugees(room, room.regions[1:], 13)] == [5, 4, 4]
    uneven = _world(_region("Tiny", 0, 1), _region("A", 0, 100), _region("B", 0, 100))
    assert [amount for _, amount in apportion_refugees(uneven, uneven.regions[1:], 5)] == [1, 2, 2]


def test_zero_and_small_budgets_never_force_one_arrival_per_destination():
    world = _world(*(_region(f"R{k}", 0, 10) for k in range(3)))
    assert apportion_refugees(world, world.regions[1:], 0) == []
    assert apportion_refugees(world, [], 13) == []
    assert [(r.name, n) for r, n in apportion_refugees(world, world.regions[1:], 1)] == [("R0", 1)]


def test_candidate_order_and_duplicates_do_not_change_the_plan_or_population():
    reference = None
    for ordering in itertools.permutations(("R0", "R1", "R2")):
        world = _world(_region("R0", 10, 10, "B"), _region("R1", 2, 5, "B"),
                       _region("R2", 0, 50, "B"))
        world.regions[0].adjacencies = [*ordering, ordering[0]]
        process_migration(world)
        result = (world.model_dump_json(), _pop(world))
        if reference is None:
            reference = result
        else:
            # Adjacency order is user input; outcomes and events remain identical.
            result_world = json.loads(result[0])
            reference_world = json.loads(reference[0])
            result_world["regions"][0]["adjacencies"] = []
            reference_world["regions"][0]["adjacencies"] = []
            assert result_world == reference_world
        assert _pop(world) == [12, 10, 5, 10]


@pytest.mark.parametrize("source_pop, cap, expected", [(25, 12, [12, 10, 2]), (13, 100, [0, 10, 2])])
def test_insufficient_room_keeps_the_full_source_toll(source_pop, cap, expected):
    world = _world(_region("Full", 10, 10, "B"), _region("Tiny", 0, 2, "B"),
                   source_population=source_pop, source_capacity=cap)
    operation = (lambda: process_migration(world)) if cap == 12 else (lambda: _famine(world))
    _, ledger = _flow_check(world, operation)
    assert _pop(world) == expected
    assert (ledger.emigrated, ledger.immigrated) == (13, 2)
    assert ledger.net() == -11


def test_zero_room_still_loses_the_departing_overflow_and_penalizes_no_receiver():
    world = _world(_region("Full", 10, 10, "B"))
    _, ledger = _flow_check(world, lambda: process_migration(world))
    assert _pop(world) == [12, 10]
    assert (ledger.emigrated, ledger.immigrated) == (13, 0)
    assert world.civ_map["B"].stability == 50


def test_without_any_permitted_neighbor_the_existing_starvation_policy_remains():
    world = _world(_region("Hostile", 0, 50, "B"))
    world.relationships = {"A": {"B": Relationship(disposition=Disposition.HOSTILE)}}
    events, ledger = _flow_check(world, lambda: process_migration(world))
    assert _pop(world) == [12, 0]
    assert ledger.removed == 13 and ledger.emigrated == ledger.immigrated == 0
    assert [event.event_type for event in events] == ["famine_starvation"]


def test_plan_never_overfills_or_loses_a_placeable_person_across_tiny_capacity_cases():
    for capacities in itertools.product(range(4), repeat=3):
        world = _world(*(_region(f"R{i}", 0, max(1, capacity)) for i, capacity in enumerate(capacities)))
        for region, capacity in zip(world.regions[1:], capacities):
            region.population = 1 if capacity == 0 else 0
        for budget in (0, 1, 2, 3, 5, 13):
            allocations = {r.name: amount for r, amount in apportion_refugees(world, world.regions[1:], budget)}
            assert sum(allocations.values()) == min(budget, sum(capacities))
            assert all(0 <= allocations.get(f"R{i}", 0) <= capacity for i, capacity in enumerate(capacities))
            unsaturated = [allocations.get(f"R{i}", 0) for i, capacity in enumerate(capacities)
                           if allocations.get(f"R{i}", 0) < capacity]
            assert not unsaturated or max(unsaturated) - min(unsaturated) <= 1


def test_second_source_uses_the_first_sources_remaining_destination_capacity():
    world = _world(_region("Room", 0, 20, "B"))
    other = _region("Other", 25, 12, "A", ("Room",))
    world.regions.insert(1, other)
    world.invalidate_region_map()
    world.civ_map["A"].regions.append("Other")
    _, ledger = _flow_check(world, lambda: process_migration(world))
    assert _pop(world) == [12, 12, 20]
    assert (ledger.emigrated, ledger.immigrated) == (26, 20)


def test_overflow_preserves_hostility_and_uncontrolled_destination_rules():
    world = _world(_region("Hostile", 0, 50, "B"), _region("Unclaimed", 0, 50))
    world.relationships = {"A": {"B": Relationship(disposition=Disposition.HOSTILE)}}
    process_migration(world)
    assert _pop(world) == [12, 0, 13]
    assert world.civ_map["B"].stability == 50


def test_famine_preserves_foreign_controlled_eligibility_including_hostile_neighbors():
    world = _world(_region("Hostile", 0, 50, "B"), _region("Unclaimed", 0, 50),
                   _region("Own", 0, 50, "A"), source_population=13, source_capacity=100)
    world.relationships = {"A": {"B": Relationship(disposition=Disposition.HOSTILE)}}
    _famine(world)
    assert _pop(world) == [0, 13, 0, 0]


@pytest.mark.parametrize("mode", ["hybrid", "demographics-only"])
def test_agent_owned_populations_never_call_the_macro_router(monkeypatch, mode):
    world = _world(_region("Room", 0, 50, "B"), mode=mode)
    before = _pop(world)
    def forbidden(*args, **kwargs):
        raise AssertionError("agent-owned population entered macro routing")
    monkeypatch.setattr("chronicler.refugee_routing.apportion_refugees", forbidden)
    assert process_migration(world) == []
    _famine(world)
    assert _pop(world) == before


def test_feature_off_does_not_call_the_new_router_and_keeps_legacy_losses(monkeypatch):
    world = _world(_region("Full", 10, 10, "B"), _region("Room", 0, 50, "B"), enabled=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("default behavior entered new routing")
    monkeypatch.setattr("chronicler.refugee_routing.apportion_refugees", forbidden)
    process_migration(world)
    assert _pop(world) == [12, 10, 7]  # legacy remainder follows reversed adjacency order
    assert "capacity_aware_refugees" not in json.loads(world.model_dump_json())


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_multiple_sources_use_remaining_room_and_exact_world_checkpoint(tmp_path, mode):
    from chronicler.run_checkpoint import load_world, save_world
    world = _world(_region("Full", 10, 10, "B"), _region("Room", 0, 30, "B"), mode=mode)
    for turn in range(4):
        world.turn = turn
        utils.add_region_pop(world.regions[0], 13, cap=100)
        process_migration(world)
        if turn == 1:
            save_world(tmp_path / "routing.ckpt", world)
            resumed = load_world(tmp_path / "routing.ckpt")
        elif turn > 1:
            resumed.turn = turn
            utils.add_region_pop(resumed.regions[0], 13, cap=100)
            process_migration(resumed)
            assert resumed.model_dump_json() == world.model_dump_json()
    assert world.regions[2].population == 30
    assert capacity_aware_refugees_enabled(resumed)


def _args(folder, turns=5, *extra):
    from chronicler.main import _build_parser
    return _build_parser().parse_args([
        "--seed", "42", "--turns", str(turns), "--regions", "6", "--civs", "3",
        "--agents", "off", "--simulate-only", "--output", str(folder / "chronicle.md"),
        "--state", str(folder / "state.json"), *extra,
    ])


@pytest.fixture
def pure_python(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


def test_cli_live_batch_manifest_and_exact_run_checkpoint(tmp_path, pure_python):
    from chronicler.main import execute_run, _build_parser
    from chronicler.batch import run_batch
    from chronicler.batch_manifest import load_batch_manifest, simulation_config
    from chronicler.run_checkpoint import read_checkpoint
    from chronicler.live import _live_world

    parser = _build_parser()
    assert parser.parse_args([]).capacity_aware_refugees is None
    assert parser.parse_args(["--no-capacity-aware-refugees"]).capacity_aware_refugees is False
    args = _args(tmp_path / "straight", 6, "--capacity-aware-refugees")
    assert simulation_config(args)["capacity_aware_refugees"] is True
    args.checkpoint_every = 3
    args.checkpoint = str(tmp_path / "routing_{turn}.ckpt")
    execute_run(args)
    saved = read_checkpoint(tmp_path / "routing_3.ckpt")
    assert saved.header["flags"]["capacity_aware_refugees"] is True
    assert saved.state.run_config["simulation_args"]["capacity_aware_refugees"] is True
    assert capacity_aware_refugees_enabled(saved.state.world)
    execute_run(_args(tmp_path / "resumed", 6), checkpoint_resume=saved)
    assert (tmp_path / "straight/state.json").read_bytes() == (tmp_path / "resumed/state.json").read_bytes()
    live_world, _ = _live_world(args, {"seed": 42, "regions": 6, "civs": 3})
    assert capacity_aware_refugees_enabled(live_world)
    # Raw live resume keeps the world's saved flag, even when CLI omits it.
    resumed_world, _ = _live_world(_args(tmp_path), {"resume_state": live_world.model_dump()})
    assert capacity_aware_refugees_enabled(resumed_world)
    batch_args = _args(tmp_path / "batch", 2, "--capacity-aware-refugees")
    batch_args.batch = 1
    batch_dir = run_batch(batch_args)
    manifest = load_batch_manifest(batch_dir)
    assert manifest["simulation"]["capacity_aware_refugees"] is True
    assert WorldState.load(batch_dir / "seed_42/state.json").capacity_aware_refugees is True


def test_gate_runner_forwards_the_switch_in_subsets_full_and_determinism(monkeypatch, tmp_path, pure_python):
    from chronicler.main import _build_parser, execute_run
    from chronicler.batch_manifest import load_batch_manifest
    spec = importlib.util.spec_from_file_location("refugee_gate_runner", ROOT / "scripts/m53b_run_validation.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    for enabled, flag in ((True, "--capacity-aware-refugees"), (False, "--no-capacity-aware-refugees")):
        args = argparse.Namespace(capacity_aware_refugees=enabled, profile="subset", seeds=1, turns=2,
                                  seed_start=42, parallel=1, output_root=tmp_path, worldgen="template")
        assert runner._capacity_aware_refugees_args(args) == [flag]
        assert runner._determinism_manifest_args(args, "off").capacity_aware_refugees is enabled
        commands = []
        monkeypatch.setattr(runner, "_run", lambda command, cwd, env: commands.append(command))
        runner.run_subset(args, tmp_path, {})
        runner.run_full(args, tmp_path, {})
        assert all(flag in command for command in commands)
        # Exercise the exact determinism command path without child processes.
        def run_here(command, cwd, env):
            commands.append(command)
            run_args = _build_parser().parse_args(command[3:])
            # main() resolves the template defaults before execute_run.
            run_args.regions = run_args.regions or 8
            run_args.civs = run_args.civs or 4
            execute_run(run_args)
        monkeypatch.setattr(runner, "_run", run_here)
        args.output_root = tmp_path / str(enabled)
        directory = runner.run_determinism(args, tmp_path, {}, "off")
        assert all(flag in command for command in commands)
        assert load_batch_manifest(directory)["simulation"]["capacity_aware_refugees"] is enabled
        for suffix in ("a", "b"):
            assert WorldState.load(directory / f"seed_42_{suffix}/state.json").capacity_aware_refugees is enabled


def test_live_batch_configuration_accepts_only_a_boolean_switch():
    from chronicler.live import LiveServer
    server = LiveServer()
    for value in (None, True, False):
        assert server._validate_batch_config({"capacity_aware_refugees": value}) is None
    for value in ("true", 1, [], {}):
        assert "capacity_aware_refugees" in server._validate_batch_config({"capacity_aware_refugees": value})


def test_old_saves_default_off_and_explicit_off_has_identical_run_files(tmp_path, pure_python):
    from chronicler.main import execute_run
    from chronicler.bundle_codec import load_bundle
    execute_run(_args(tmp_path / "default"))
    execute_run(_args(tmp_path / "off", 5, "--no-capacity-aware-refugees"))
    state = WorldState.load(tmp_path / "default/state.json")
    assert not capacity_aware_refugees_enabled(state)
    assert (tmp_path / "default/state.json").read_bytes() == (tmp_path / "off/state.json").read_bytes()
    left = load_bundle(tmp_path / "default/chronicle_bundle.json")
    right = load_bundle(tmp_path / "off/chronicle_bundle.json")
    left["metadata"].pop("generated_at", None)
    right["metadata"].pop("generated_at", None)
    assert left == right
