"""Epidemiology, finance and diplomacy switched on together.

Each system has its own suite; these tests cover running them in one world:
save/load resume identity, determinism, and every system's state being live.
"""
from __future__ import annotations

import chronicler.contact_ledger as cl
import chronicler.diplomacy as dp
import chronicler.epidemiology as ep
import chronicler.finance as F
from chronicler.action_engine import ActionEngine
from chronicler.models import WorldState
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


def _world(seed: int = 42) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    F.set_finance_enabled(world, True)
    dp.set_diplomacy_enabled(world, True)
    return world


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def test_all_three_systems_run_and_persist_state():
    world = _advance(_world(42), 40)
    assert world.epidemics is not None
    assert world.finance is not None
    assert world.diplomacy is not None
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.epidemics == world.epidemics
    assert dumped.finance == world.finance
    assert dumped.diplomacy == world.diplomacy


def test_save_load_resume_identity_with_all_three_on(tmp_path):
    # Save at the first turn from 30 on where all three systems carry live
    # state (an epidemic has killed, a loan is outstanding, a treaty stands).
    first = _advance(_world(42), 30)
    while not (first.epidemics.deaths_total > 0 and first.finance.loans
               and first.diplomacy.treaties):
        assert first.turn < 80, "no turn with live state in all three systems"
        _advance(first, 1)
    straight = _advance(_world(42), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_all_three_on_is_deterministic():
    a = _advance(_world(7), 30)
    b = _advance(_world(7), 30)
    assert a.model_dump_json() == b.model_dump_json()


# --- Maritime together with epidemiology, finance and diplomacy -------------------------

def _sea_world(seed: int = 11) -> WorldState:
    """A procedural world with sea zones, so fleets, blockades and piracy run."""
    import chronicler.maritime as mt
    world = generate_world(seed=seed, num_regions=32, num_civs=8, worldgen="procedural")
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    F.set_finance_enabled(world, True)
    dp.set_diplomacy_enabled(world, True)
    mt.set_maritime_enabled(world, True)
    return world


def _all_four_live(world: WorldState) -> bool:
    m = world.maritime
    return bool(m.fleets and m.counters["naval_battles"] > 0 and m.counters["sea_trade"] > 0
                and world.epidemics.deaths_total > 0 and world.finance.loans
                and world.diplomacy.treaties)


def _live_save_point() -> WorldState:
    """The first turn from 30 on where every system carries live state:
    fleets at sea after a naval battle, sea trade, an epidemic death, a loan
    and a treaty."""
    world = _advance(_sea_world(), 30)
    while not _all_four_live(world):
        assert world.turn < 90, "no turn with live state in all four systems"
        _advance(world, 1)
    return world


def test_maritime_with_all_three_runs_and_persists_state():
    world = _live_save_point()
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.maritime == world.maritime
    assert dumped.model_dump_json() == world.model_dump_json()


def test_save_load_resume_identity_with_maritime_and_all_three_on(tmp_path):
    first = _live_save_point()
    straight = _advance(_sea_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_maritime_with_all_three_is_deterministic():
    a = _advance(_sea_world(), 30)
    b = _advance(_sea_world(), 30)
    assert a.model_dump_json() == b.model_dump_json()


# --- All five: techniques and maritime with epidemiology, finance and diplomacy --------

def _five_world() -> WorldState:
    import chronicler.techniques as tq
    world = _sea_world()
    tq.set_techniques_enabled(world, True)
    return world


def test_save_load_resume_identity_with_all_five_on(tmp_path):
    first = _advance(_five_world(), 30)
    assert first.techniques is not None and first.maritime.fleets
    assert first.finance.loans and first.diplomacy.treaties
    assert first.epidemics.deaths_total > 0
    straight = _advance(_five_world(), 45)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


# --- Great-person agendas on top of all five --------------------------------------------

def _six_world() -> WorldState:
    """All five systems plus great-person agendas and the governance bucket."""
    import chronicler.gp_agendas as ga
    from chronicler.governance_runtime import set_governance_enabled
    world = _five_world()
    set_governance_enabled(world, True)
    ga.set_gp_agendas_enabled(world, True)
    return world


def test_save_load_resume_identity_with_agendas_and_all_five_on(tmp_path):
    import chronicler.gp_agendas as ga
    first = _advance(_six_world(), 30)
    while not any(ga._is_open(r) for r in first.gp_agendas.records.values()):
        assert first.turn < 90, "no turn with an open great-person agenda"
        _advance(first, 1)
    assert first.techniques is not None and first.maritime.fleets
    assert first.finance.loans and first.diplomacy.treaties
    assert first.gp_agendas.counts["declared"] > 0
    straight = _advance(_six_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.gp_agendas == first.gp_agendas
    _advance(resumed, 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


# --- Nomads with every other system: the ledger, epidemiology, finance, diplomacy,
# --- techniques and maritime ---------------------------------------------------------------

def _all_world() -> WorldState:
    """Seed 11 (32 regions, 8 civs) has a nomadic and two agro-pastoral peoples."""
    import chronicler.nomads as nm
    world = _five_world()
    nm.set_nomads_enabled(world, True)
    return world


def _nomads_live(world: WorldState) -> bool:
    n = world.nomads
    return bool(sum(n.herds) > 0 and n.counters["raids"] + n.counters["raids_repulsed"] > 0
                and any(m != 0 for i, m in enumerate(n.modes) if world.civilizations[i].regions))


def _all_live_save_point() -> WorldState:
    """The first turn from 30 on where herds graze, a raid has happened and
    every other system carries live state."""
    world = _advance(_all_world(), 30)
    while not (_nomads_live(world) and _all_four_live(world) and world.techniques is not None):
        assert world.turn < 120, "no turn with live state in every system"
        _advance(world, 1)
    return world


def test_nomads_with_every_system_run_and_persist_state():
    world = _all_live_save_point()
    assert world.nomads.raids or world.nomads.counters["raids"] > 0
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.nomads == world.nomads
    assert dumped.model_dump_json() == world.model_dump_json()


def test_save_load_resume_identity_with_nomads_and_every_system_on(tmp_path):
    first = _all_live_save_point()
    straight = _advance(_all_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_nomads_with_every_system_is_deterministic():
    a = _advance(_all_world(), 30)
    b = _advance(_all_world(), 30)
    assert a.model_dump_json() == b.model_dump_json()


# --- Everything: nomads and great-person agendas with all five systems -----------------

def _everything_world() -> WorldState:
    import chronicler.gp_agendas as ga
    from chronicler.governance_runtime import set_governance_enabled
    world = _all_world()
    set_governance_enabled(world, True)
    ga.set_gp_agendas_enabled(world, True)
    return world


def test_save_load_resume_identity_with_everything_on(tmp_path):
    first = _advance(_everything_world(), 30)
    while not (_nomads_live(first) and first.gp_agendas.counts["declared"] > 0
               and first.finance.loans and first.diplomacy.treaties):
        assert first.turn < 120, "no turn with live nomads, agendas, loans and treaties"
        _advance(first, 1)
    straight = _advance(_everything_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


# --- Cities on top of everything (settlements as M56a leaves them) --------------------

def _cities_world() -> WorldState:
    """Everything above plus cities. With --agents off nothing detects
    settlements, so the four most populous held regions get one each, as
    M56a records them (its id allocator and names); their cities found,
    trade, owe dues, petition and build from the first tick."""
    import chronicler.cities as ct
    from chronicler.models import Settlement, SettlementStatus
    world = _everything_world()
    ct.set_cities_enabled(world, True)
    held = sorted((i for i, r in enumerate(world.regions) if r.controller),
                  key=lambda i: (-world.regions[i].population, i))[:4]
    for i in held:
        region = world.regions[i]
        seq = world.settlement_naming_counters.get(region.name, 1)
        region.settlements.append(Settlement(
            settlement_id=world.next_settlement_id, name=f"{region.name} Settlement {seq}",
            region_name=region.name, last_seen_turn=0, population_estimate=40,
            peak_population=40, centroid_x=0.5, centroid_y=0.5, footprint_cells=[(5, 5)],
            status=SettlementStatus.ACTIVE, inertia=1,
        ))
        world.next_settlement_id += 1
        world.settlement_naming_counters[region.name] = seq + 1
    return world


def _cities_live(world: WorldState) -> bool:
    c = world.cities
    return bool(c.cities and c.counters["charters"] + c.counters["refusals"] > 0
                and any(o > 0 for o in c.owed) and c.counters["dues"] > 0
                and any(city.wealth > 0 for city in c.cities))


def _market_inputs(world: WorldState):
    """What the city markets read from the world (city-markets.md): the
    economy columns for a fixed set of agent rows (two farmers and a
    merchant in every living city, two rural farmers per region), the
    cut-off cities and the merchant graph after the cities' filter. With
    --agents off nothing calls them; read here, they show that every input
    comes from persisted state."""
    import pyarrow as pa
    import chronicler.cities as ct
    from chronicler.economy import build_merchant_route_graph
    region, occupation, sid = [], [], []
    for city in world.cities.cities:
        region += [city.region] * 3
        occupation += [0, 0, 2]
        sid += [city.settlement_id] * 3
    for r in range(len(world.regions)):
        region += [r, r]
        occupation += [0, 0]
        sid += [0, 0]
    rows = pa.record_batch({"region": pa.array(region, type=pa.uint16()),
                            "occupation": pa.array(occupation, type=pa.uint8()),
                            "settlement_id": pa.array(sid, type=pa.uint16())})
    graph = ct.merchant_route_graph(world, build_merchant_route_graph(world))
    return ct.economy_columns(world, rows), sorted(ct.cut_off_regions(world)), graph.to_pydict()


def test_save_load_resume_identity_with_cities_and_everything_on(tmp_path):
    first = _advance(_cities_world(), 30)
    while not (_cities_live(first) and _nomads_live(first) and first.finance.loans
               and first.diplomacy.treaties):
        assert first.turn < 120, "no turn with live cities, nomads, loans and treaties"
        _advance(first, 1)
    straight = _advance(_cities_world(), first.turn)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.cities == first.cities
    # City markets: every input the economy and the merchant graph would read
    # matches the uninterrupted run, turn by turn.
    for _ in range(15):
        assert _market_inputs(resumed) == _market_inputs(straight)
        _advance(resumed, 1)
        _advance(straight, 1)
    assert _market_inputs(resumed) == _market_inputs(straight)
    assert resumed.model_dump_json() == straight.model_dump_json()
    assert resumed.cities.counters["founded"] >= 4


# --- Agent movements on top of everything (members as a world saves them) -------------

def _movements_world() -> WorldState:
    """Everything above, cities included, plus agent movements. With --agents
    off nothing recruits or founds, so two movements are placed as a saved
    world carries them (members by region, strength, stronghold): their
    demands, the rulers' responses, crackdowns and risings run from the
    persisted state. A lasting reform (relief without an institution) is in
    force from the start: its upkeep, the rulers' judgement of it and any
    repeal run from the persisted state too."""
    import chronicler.agent_movements as am
    from chronicler.agent_movements_state import COMMONS, LIBERTY, RELIEF, Movement, Reform
    world = _cities_world()
    am.set_agent_movements_enabled(world, True)
    held = sorted((i for i, r in enumerate(world.regions) if r.controller),
                  key=lambda i: (-world.regions[i].population, i))
    for creed, ri in ((LIBERTY, held[0]), (COMMONS, held[1])):
        target = world.civ_index_map[world.regions[ri].controller]
        world.agent_movements.movements.append(Movement(
            name=f"movement {ri}", creed=creed, founded_turn=0, home_region=ri, target=target,
            members=12, member_regions=[[ri, 12]], strength=0.3, stronghold=ri,
            stronghold_share=0.4, regions_reached=[ri]))
    civ = world.civilizations[world.civ_index_map[world.regions[held[2]].controller]]
    world.agent_movements.reforms.append(Reform(
        kind=RELIEF, civ=world.civ_index_map[civ.name], enacted_turn=0, ruler=civ.leader.name,
        ruler_start=civ.leader.reign_start))
    return world


def _movements_live(world: WorldState) -> bool:
    c = world.agent_movements.counters
    return c["demands"] >= 2 and c["refusals"] + c["reforms"] + c["crackdowns"] >= 2


def test_save_load_resume_identity_with_movements_and_everything_on(tmp_path):
    first = _advance(_movements_world(), 30)
    while not (_movements_live(first) and _cities_live(first) and first.finance.loans
               and first.diplomacy.treaties):
        assert first.turn < 120, "no turn with live movements, cities, loans and treaties"
        _advance(first, 1)
    straight = _advance(_movements_world(), first.turn)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.agent_movements == first.agent_movements
    import chronicler.agent_movements as am
    for _ in range(15):
        # The native table each tick would read is the same, turn by turn.
        assert am.movement_table(resumed).to_pydict() == am.movement_table(straight).to_pydict()
        assert am.reform_table(resumed).to_pydict() == am.reform_table(straight).to_pydict()
        _advance(resumed, 1)
        _advance(straight, 1)
    assert resumed.model_dump_json() == straight.model_dump_json()
    assert resumed.agent_movements.counters["demands"] >= 2
    assert resumed.agent_movements.reforms and resumed.agent_movements.counters["upkeep"] > 0
