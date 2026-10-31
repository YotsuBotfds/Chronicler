"""Population conservation on the Python-owned population paths.

Corrections described in docs/integration/population-entities.md. Where
Python owns population (``--agents off`` and shadow), a region's population
changes only by births, deaths and migration: arrivals never remove the
residents of a crowded region, famine refugees never outnumber the people
who fled, and migrants who find no room are counted as deaths.
"""
from __future__ import annotations

import pytest

from chronicler.ecology import _check_famine_yield, effective_capacity
from chronicler.models import (
    EMPTY_SLOT, Civilization, ClimatePhase, Leader, Region, RegionEcology, ResourceType, WorldState,
)
from chronicler.tuning import K_FAMINE_POP_LOSS
from chronicler.utils import add_region_pop, distribute_pop_loss


def _region(name: str, pop: int, cap: int = 100, controller: str | None = None,
            adjacencies: tuple[str, ...] = ()) -> Region:
    return Region(
        name=name, terrain="plains", carrying_capacity=cap, resources="fertile",
        population=pop, controller=controller, adjacencies=list(adjacencies),
        ecology=RegionEcology(soil=1.0, water=1.0, forest_cover=0.3),
    )


def _civ(name: str, regions: list[str], pop: int) -> Civilization:
    return Civilization(
        name=name, population=pop, military=30, economy=40, culture=30, stability=50,
        leader=Leader(name=f"Ruler of {name}", trait="cautious", reign_start=0), regions=regions,
    )


def _total(world: WorldState) -> int:
    return sum(r.population for r in world.regions)


# --- add_region_pop -----------------------------------------------------------------

def test_arrivals_never_remove_the_residents_of_a_crowded_region():
    crowded = _region("Crowded", 100, cap=48)
    assert effective_capacity(crowded) == 48
    assert add_region_pop(crowded, 1) == 0
    assert crowded.population == 100


def test_arrivals_fill_the_headroom_and_report_what_was_accepted():
    region = _region("Room", 40, cap=48)
    assert add_region_pop(region, 20) == 8
    assert region.population == 48
    explicit = _region("Explicit", 10, cap=100)
    assert add_region_pop(explicit, 5, cap=12) == 2
    assert explicit.population == 12


def test_population_loss_never_grows_a_region_after_rounding_overdraw():
    regions = [_region(f"R{index}", 100) for index in range(39)]
    regions.append(_region("Last", 1))
    before = [region.population for region in regions]

    drains = distribute_pop_loss(regions, 20)

    assert sum(drains) == 20
    assert all(drain >= 0 for drain in drains)
    assert [region.population for region in regions] == [
        population - drain for population, drain in zip(before, drains)
    ]
    assert all(region.population <= population for region, population in zip(regions, before))


@pytest.mark.parametrize("pop, amount, accepted", [
    (0, 0, 0), (0, 1, 1), (0, 3, 2), (1, 1, 1), (1, 5, 1), (2, 1, 0), (2, 0, 0),
    (0, -1, 0), (2, -3, 0),
])
def test_tiny_populations_against_a_capacity_of_two(pop, amount, accepted):
    region = _region("Tiny", pop, cap=2)
    assert add_region_pop(region, amount) == accepted
    assert region.population == pop + accepted


# --- famine refugees ------------------------------------------------------------------

def _famine_world(source_pop: int, neighbours: list[tuple[int, int]]) -> WorldState:
    """A famine in Src (civ A) whose neighbours N0.. belong to other civs.

    ``neighbours`` are (population, capacity); the adjacency order is the
    reverse of the region order, so the remainder rule's region-index order
    is observable.
    """
    names = [f"N{k}" for k in range(len(neighbours))]
    src = _region("Src", source_pop, controller="A", adjacencies=tuple(reversed(names)))
    src.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    src.resource_base_yields = [0.10, 0.0, 0.0]
    regions = [src]
    civs = [_civ("A", ["Src"], source_pop)]
    for k, (pop, cap) in enumerate(neighbours):
        neighbour = _region(names[k], pop, cap=cap, controller=f"C{k}", adjacencies=("Src",))
        neighbour.famine_cooldown = 1   # the famine is Src's alone
        regions.append(neighbour)
        civs.append(_civ(f"C{k}", [names[k]], pop))
    world = WorldState(name="T", seed=42, regions=regions, civilizations=civs)
    # A toll larger than the source population drains all of it.
    world.tuning_overrides = {K_FAMINE_POP_LOSS: 100.0}
    return world


def _famine(world: WorldState):
    return _check_famine_yield(world, {"Src": [0.0012, 0.0, 0.0]}, ClimatePhase.TEMPERATE,
                               0.12, 0.15, None)


def test_one_refugee_among_three_neighbours_is_one_person():
    world = _famine_world(1, [(10, 100)] * 3)
    assert _total(world) == 31
    events = _famine(world)
    assert [e.event_type for e in events] == ["famine"]
    assert _total(world) == 31
    # The remainder goes to the lowest region index first.
    assert [r.population for r in world.regions] == [0, 11, 10, 10]


def test_refugees_split_with_the_remainder_in_region_order():
    world = _famine_world(5, [(10, 100)] * 3)
    _famine(world)
    assert [r.population for r in world.regions] == [0, 12, 12, 11]
    assert _total(world) == 35


@pytest.mark.parametrize("source_pop", [1, 2])
def test_tiny_famines_conserve_population(source_pop):
    world = _famine_world(source_pop, [(0, 100), (1, 100), (2, 100)])
    before = _total(world)
    _famine(world)
    assert _total(world) == before
    assert world.regions[0].population == 0


def test_an_empty_region_has_no_famine_and_no_refugees():
    world = _famine_world(0, [(10, 100)] * 2)
    assert _famine(world) == []
    assert [r.population for r in world.regions] == [0, 10, 10]


def test_refugees_who_find_no_room_die_and_residents_stay():
    # N0 is crowded (100 people on room for 48), N1 has room for 2.
    world = _famine_world(6, [(100, 48), (46, 48)])
    before = _total(world)
    _famine(world)
    assert world.regions[1].population == 100      # residents stay
    assert world.regions[2].population == 48       # 2 of its 3 refugees settle
    assert _total(world) == before - 6 + 2         # 4 refugees die


def test_only_neighbours_offered_refugees_feel_them():
    world = _famine_world(1, [(10, 100)] * 3)
    _famine(world)
    stability = [c.stability for c in world.civilizations[1:]]
    assert stability[0] < 50 and stability[1:] == [50, 50]


# --- overflow migration and growth ----------------------------------------------------

def test_overflow_migrants_who_find_no_room_die_and_residents_stay():
    from chronicler.climate import process_migration
    src = _region("Src", 100, cap=40, controller="A", adjacencies=("N0", "N1"))
    full = _region("N0", 90, cap=48, controller="B", adjacencies=("Src",))   # above capacity
    room = _region("N1", 10, cap=100, controller="B", adjacencies=("Src",))
    world = WorldState(name="T", seed=42, regions=[src, full, room],
                       civilizations=[_civ("A", ["Src"], 100), _civ("B", ["N0", "N1"], 100)])
    before = _total(world)
    events = process_migration(world)
    assert [e.event_type for e in events] == ["migration"]
    # 60 leave Src, 30 for each neighbour: N0 has no room, N1 takes its 30.
    assert [r.population for r in world.regions] == [40, 90, 40]
    assert _total(world) == before - 30


def test_growth_never_trims_a_region_above_its_capacity():
    from chronicler.simulation import phase_production
    over = _region("Over", 60, cap=48, controller="A")
    room = _region("Room", 10, cap=100, controller="A")
    empty = _region("Empty", 0, cap=100, controller="A")
    world = WorldState(name="T", seed=42, regions=[over, room, empty],
                       civilizations=[_civ("A", ["Over", "Room", "Empty"], 70)])
    phase_production(world)
    # Growth: 5 per region, refused where there is no room (the empty
    # region, settled by it, needs no repopulation).
    assert [r.population for r in world.regions] == [60, 15, 5]
    assert world.civilizations[0].population == 80


# --- the debug ledger -------------------------------------------------------------------

def _advance(world: WorldState, turns: int) -> None:
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)


def test_aggregate_turns_conserve_population_flow_by_flow(monkeypatch):
    from chronicler.utils import POPULATION_CHECK_ENV
    from chronicler.world_gen import generate_world
    monkeypatch.setenv(POPULATION_CHECK_ENV, "1")
    for seed in (42, 7):
        world = generate_world(seed=seed)
        world.agent_mode = "off"
        _advance(world, 40)
        assert world.turn == 40


def test_the_ledger_catches_people_made_from_nothing(monkeypatch):
    import chronicler.simulation as sim
    from chronicler.utils import POPULATION_CHECK_ENV
    monkeypatch.setenv(POPULATION_CHECK_ENV, "1")
    real = sim.phase_production

    def production_with_a_stray_birth(world, acc=None):
        real(world, acc=acc)
        world.regions[0].population += 1    # not through a recorded helper

    monkeypatch.setattr(sim, "phase_production", production_with_a_stray_birth)
    world = generate_world(seed=42)
    with pytest.raises(AssertionError, match="population not conserved"):
        _advance(world, 1)


def test_the_ledger_catches_refugees_who_outnumber_the_fled(monkeypatch):
    from chronicler import utils
    world = _famine_world(1, [(10, 100)] * 3)
    ledger = utils.start_population_ledger()
    try:
        before = _total(world)
        monkeypatch.setattr("chronicler.ecology.refugee_shares",
                            lambda w, eligible, n: [max(1, n // len(eligible))] * len(eligible))
        _famine(world)
    finally:
        utils.stop_population_ledger()
    assert (ledger.emigrated, ledger.immigrated) == (1, 3)
    with pytest.raises(AssertionError, match="population not conserved"):
        ledger.check(before, _total(world))


def test_the_ledger_is_off_by_default_and_outside_the_aggregate_model(monkeypatch):
    from chronicler import utils
    from chronicler.simulation import _start_population_check
    monkeypatch.delenv(utils.POPULATION_CHECK_ENV, raising=False)
    world = _famine_world(1, [(10, 100)])
    assert _start_population_check(world) is None and utils._population_ledger is None
    monkeypatch.setenv(utils.POPULATION_CHECK_ENV, "1")
    world.agent_mode = "hybrid"
    assert _start_population_check(world) is None and utils._population_ledger is None
    world.agent_mode = "off"
    ledger, total = _start_population_check(world)
    utils.stop_population_ledger()
    assert total == 11 and ledger.net() == 0


# --- modes -------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["hybrid", "demographics-only"])
def test_agent_owned_populations_have_no_python_famine_drain_or_refugees(mode):
    from chronicler.economy import EconomyResult
    world = _famine_world(5, [(10, 100)] * 3)
    world.agent_mode = mode
    before = [r.population for r in world.regions]
    events = _check_famine_yield(world, {}, ClimatePhase.TEMPERATE, 0.12, 0.15, None,
                                 economy_result=EconomyResult(food_sufficiency={"Src": 0.2}))
    assert [e.event_type for e in events] in (["famine"], ["dearth"])
    assert [r.population for r in world.regions] == before


def test_shadow_mode_keeps_the_conserving_python_drain():
    from chronicler.economy import EconomyResult
    world = _famine_world(5, [(10, 100)] * 3)
    world.agent_mode = "shadow"
    world.regions[0].food_severe_turns = 10   # a famine, not a dearth
    before = _total(world)
    _check_famine_yield(world, {}, ClimatePhase.TEMPERATE, 0.12, 0.15, None,
                        economy_result=EconomyResult(food_sufficiency={"Src": 0.0}))
    assert world.regions[0].population < 5
    assert _total(world) == before
