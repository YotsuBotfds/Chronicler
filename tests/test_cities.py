"""Cities as historical actors (``chronicler.cities``, ``--cities``).

Mechanics are exercised on the template world (seed 42) with settlements
placed as M56a records them (its allocator, names and statuses); the tick is
called directly with ``acc=None`` (Phase 10 outside hybrid mode mutates
directly). Native tests run the real extension in hybrid mode.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import chronicler.cities as C
from chronicler import provenance as prov
from chronicler.accumulator import StatAccumulator
from chronicler.action_engine import ActionEngine
from chronicler.cities_state import (
    CITY, FREE_CITY, GREAT_CITY, MARKET_RIGHTS, NO_CHARTER, SELF_GOVERNMENT, TOWN, City, CityState,
)
from chronicler.models import (
    Event, FactionType, InfrastructureType, Settlement, SettlementStatus, TurnSnapshot, WorldState,
)
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world

ROOT = Path(__file__).resolve().parents[1]
# Template seed 42: Thornwall Confederacy (civ 2) holds Verdant Plains (2,
# capital) and Thornwood (4); Kethani Empire (1) holds Amber Valley (5,
# capital) and Frostholm Tundra (0); Iron Peaks (1) is unclaimed.
FROST, IRON, VERDANT, DESERT, THORNWOOD, AMBER = 0, 1, 2, 3, 4, 5
ASHKARI, KETHANI, THORNWALL, SELURIAN = 0, 1, 2, 3


def _world(seed: int = 42) -> WorldState:
    world = generate_world(seed=seed)
    C.set_cities_enabled(world, True)
    return world


def _settle(world: WorldState, region_idx: int, population: int, *,
            status: SettlementStatus = SettlementStatus.ACTIVE) -> Settlement:
    """An M56a settlement record (its id allocator and naming counter)."""
    region = world.regions[region_idx]
    seq = world.settlement_naming_counters.get(region.name, 1)
    s = Settlement(
        settlement_id=world.next_settlement_id, name=f"{region.name} Settlement {seq}",
        region_name=region.name, founding_turn=world.turn, last_seen_turn=world.turn,
        population_estimate=population, peak_population=population, centroid_x=0.55,
        centroid_y=0.55, footprint_cells=[(5, 5)], status=status, inertia=1,
    )
    world.next_settlement_id += 1
    world.settlement_naming_counters[region.name] = seq + 1
    region.settlements.append(s)
    return s


def _tick(world: WorldState, events=(), economy=None, acc=None) -> list[Event]:
    events = C.tick_cities(world, events, acc=acc, economy_result=economy)
    world.events_timeline.extend(events)
    return events


def _economy(food: dict | None = None, routes: dict | None = None):
    return SimpleNamespace(food_sufficiency=food or {}, trade_route_counts=routes or {})


def _city(world: WorldState, sid: int) -> City:
    return next(c for c in world.cities.cities + world.cities.fallen if c.settlement_id == sid)


def _types(events) -> list[str]:
    return [e.event_type for e in events]


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def _give(world: WorldState, region_idx: int, civ_idx: int) -> None:
    region = world.regions[region_idx]
    if region.controller is not None:
        world.civ_map[region.controller].regions.remove(region.name)
    civ = world.civilizations[civ_idx]
    region.controller = civ.name
    civ.regions.append(region.name)


# --- switch and persistence ------------------------------------------------------

def test_default_off_and_dormant_fields_are_omitted():
    assert C.DEFAULT_ENABLED_FOR_NEW_WORLDS is False
    world = generate_world(seed=42)
    assert world.cities is None and not C.cities_enabled(world)
    assert "cities" not in json.loads(world.model_dump_json())
    assert "cities" not in json.loads(TurnSnapshot(turn=1, civ_stats={}, region_control={},
                                                   relationships={}).model_dump_json())
    assert C.tick_cities(world, []) == []
    C.pay_dues(world, StatAccumulator())
    assert C.region_pulls(world) == [0.0] * len(world.regions)
    assert C.credit_factor(world, 0) == 1.0


def test_enable_disable_and_state_round_trip():
    world = _world()
    _settle(world, THORNWOOD, 30)
    _tick(world)
    assert world.cities.cities
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert loaded.cities == world.cities
    C.set_cities_enabled(world, True)   # idempotent: keeps the state
    assert world.cities.cities
    C.set_cities_enabled(world, False)
    assert world.cities is None


def test_old_saves_without_cities_load(tmp_path):
    world = generate_world(seed=7)
    path = tmp_path / "state.json"
    world.save(path)
    data = json.loads(path.read_text())
    assert "cities" not in data
    assert WorldState.load(path).cities is None


# --- founding, ranks, falls --------------------------------------------------------

def test_a_settlement_of_town_size_becomes_a_city_with_its_rank():
    world = _world()
    k = C.scale(world)
    town = _settle(world, VERDANT, round(C.RANK_POP[TOWN] * k) + 1)
    great = _settle(world, THORNWOOD, round(C.RANK_POP[GREAT_CITY] * k) + 1)
    small = _settle(world, AMBER, round(C.RANK_POP[TOWN] * k) - 2)
    _settle(world, FROST, 50, status=SettlementStatus.CANDIDATE)
    _settle(world, IRON, 50, status=SettlementStatus.DISSOLVING)
    events = _tick(world)
    assert _types(events) == ["city_founded", "city_founded"]
    assert {c.settlement_id: c.rank for c in world.cities.cities} == {
        town.settlement_id: TOWN, great.settlement_id: GREAT_CITY}
    founded = _city(world, great.settlement_id)
    assert (founded.region, founded.founder, founded.lord) == (THORNWOOD, THORNWALL, THORNWALL)
    assert great.name in events[1].description and events[1].region == "Thornwood"
    assert founded.history[0][1] == "founded" and founded.history[0][2] == events[1].event_id
    assert small.settlement_id not in {c.settlement_id for c in world.cities.cities}


def test_ranks_follow_the_smoothed_estimate_with_hysteresis():
    world = _world()
    k = C.scale(world)
    s = _settle(world, THORNWOOD, round(C.RANK_POP[TOWN] * k) + 1)
    _tick(world)
    city = _city(world, s.settlement_id)
    s.population_estimate = round(C.RANK_POP[CITY] * k) + 4
    grew = []
    for turn in range(1, 30):
        world.turn = turn
        grew += [e for e in _tick(world) if e.event_type == "city_grew"]
    assert city.rank == CITY and len(grew) == 1
    # A dip below the town threshold but above 0.7 of the city's keeps the rank.
    s.population_estimate = round(C.RANK_POP[CITY] * k * 0.8)
    for turn in range(30, 60):
        world.turn = turn
        _tick(world)
    assert city.rank == CITY
    s.population_estimate = round(C.RANK_POP[TOWN] * k)
    declined = []
    for turn in range(60, 100):
        world.turn = turn
        declined += [e for e in _tick(world) if e.event_type == "city_declined"]
    assert city.rank == TOWN and len(declined) == 1


def test_falls_abandoned_or_deserted_and_a_successor_names_its_predecessor():
    world = _world()
    a = _settle(world, THORNWOOD, 30)
    b = _settle(world, VERDANT, 30)
    _tick(world)
    # M56a dissolves a's settlement: the city is abandoned.
    world.regions[THORNWOOD].settlements.remove(a)
    world.turn = 1
    events = _tick(world)
    assert _types(events) == ["city_fell"] and "abandoned" in events[0].description
    assert _city(world, a.settlement_id).fallen_turn == 1
    # b's people leave: deserted after FALL_TURNS turns below the floor.
    b.population_estimate = 0
    fell = []
    for turn in range(2, 80):
        world.turn = turn
        fell += [e for e in _tick(world) if e.event_type == "city_fell"]
    assert len(fell) == 1 and "deserted" in fell[0].description
    # The same settlement never founds a second city; a new one names its predecessor.
    b.population_estimate = 40
    world.turn = 80
    assert not [e for e in _tick(world) if e.event_type == "city_founded"]
    c = _settle(world, THORNWOOD, 30)
    world.turn = 81
    events = _tick(world)
    assert _types(events) == ["city_founded"] and a.name in events[0].description
    assert _city(world, c.settlement_id).predecessor == a.settlement_id
    assert world.cities.counters["fallen"] == 2


# --- wealth ---------------------------------------------------------------------

def test_commerce_fills_the_purse_and_dues_are_paid_next_turn_as_keep():
    world = _world()
    s = _settle(world, THORNWOOD, 30)
    _tick(world, economy=_economy(routes={"Thornwood": 2}))
    city = _city(world, s.settlement_id)
    base = city.size / C.scale(world) * sum(w * m for w, m in zip(C.COMMERCE_WEIGHTS, city.mix))
    assert city.commerce == pytest.approx(base * (1 + 2 * C.ROUTE_ACCESS), abs=1e-3)
    owed = world.cities.owed[THORNWALL]
    assert owed == pytest.approx(city.commerce * C.DUES[NO_CHARTER], abs=1e-4)
    assert city.wealth == pytest.approx(city.commerce - owed, abs=1e-3)
    # Next Phase 2: whole units as keep treasury; the fraction carries.
    acc = StatAccumulator()
    C.pay_dues(world, acc)
    whole = int(owed)
    keeps = [c for c in acc._changes if c.category == "keep" and c.stat == "treasury"]
    assert sum(c.delta for c in keeps) == whole and all(c.civ_id == THORNWALL for c in keeps)
    assert world.cities.carry[THORNWALL] == pytest.approx(owed - whole, abs=1e-6)
    assert world.cities.owed[THORNWALL] == 0.0
    # Hunger and occupation cut commerce.
    world.turn = 1
    _tick(world, economy=_economy(food={"Thornwood": 0.5}))
    hungry = city.commerce
    world.turn = 2
    _tick(world)
    assert hungry == pytest.approx(city.commerce * 0.5, rel=0.05)


def test_commerce_does_not_grow_with_the_agent_scale():
    small, large = _world(), _world()
    for region in large.regions:
        region.carrying_capacity *= 100
        region.population *= 100
    a = _settle(small, THORNWOOD, 30)
    b = _settle(large, THORNWOOD, 3000)
    _tick(small)
    _tick(large)
    assert _city(small, a.settlement_id).rank == _city(large, b.settlement_id).rank
    assert _city(small, a.settlement_id).commerce == pytest.approx(
        _city(large, b.settlement_id).commerce, rel=0.01)


def test_dues_owed_to_a_dead_lord_are_dropped():
    world = _world()
    world.cities.owed = [0.0, 0.0, 5.5]
    world.cities.carry = [0.0, 0.0, 0.25]
    world.civilizations[THORNWALL].regions = []
    acc = StatAccumulator()
    C.pay_dues(world, acc)
    assert not acc._changes and world.cities.carry[THORNWALL] == 0.0


# --- politics -------------------------------------------------------------------

def test_charter_petitions_are_granted_for_a_fee_or_refused(monkeypatch):
    world = _world()
    s = _settle(world, THORNWOOD, 30)
    _tick(world)
    city = _city(world, s.settlement_id)
    city.wealth = 100.0
    lord = world.civilizations[THORNWALL]
    treasury = lord.treasury
    merchants = lord.factions.influence[FactionType.MERCHANT]
    monkeypatch.setattr(C, "grant_chance", lambda lord, m: 1.0)
    world.turn = 1
    events = _tick(world)
    assert "city_charter" in _types(events) and city.charter == MARKET_RIGHTS
    fee = int(C.CHARTER_FEE[MARKET_RIGHTS])
    assert lord.treasury == treasury + fee
    assert lord.factions.influence[FactionType.MERCHANT] > merchants
    # No new petition before PETITION_INTERVAL turns.
    world.turn = 2
    assert "city_charter" not in _types(_tick(world))
    monkeypatch.setattr(C, "grant_chance", lambda lord, m: 0.0)
    world.turn = 1 + C.PETITION_INTERVAL
    city.wealth = 100.0
    events = _tick(world)
    assert "charter_refused" in _types(events) and city.charter == MARKET_RIGHTS
    assert city.grievance > 0.2


def test_grant_chance_reads_trait_treasury_weakness_and_merchants():
    world = generate_world(seed=42)
    lord = world.civilizations[THORNWALL]
    lord.treasury, lord.stability = 200, 60
    lord.leader.trait = "shrewd"
    seller = C.grant_chance(lord, 0.25)
    lord.leader.trait = "stubborn"
    refuser = C.grant_chance(lord, 0.25)
    assert seller - refuser == pytest.approx(2 * C.GRANT_TRAIT)
    lord.treasury, lord.stability = 5, 10
    assert C.grant_chance(lord, 0.25) == pytest.approx(refuser + C.GRANT_POOR + C.GRANT_WEAK)
    assert C.grant_chance(lord, 0.6) > C.grant_chance(lord, 0.25)
    lord.leader.trait = "shrewd"
    assert C.grant_chance(lord, 1.0) == C.GRANT_MAX


def test_unrest_rises_with_misery_hunger_and_occupation(monkeypatch):
    monkeypatch.setattr(C, "REVOLT_CHANCE", 0.0)
    world = _world()
    s = _settle(world, THORNWOOD, 30)
    _tick(world)
    city = _city(world, s.settlement_id)
    for turn in range(1, 20):
        world.turn = turn
        _tick(world)
    calm = city.unrest
    assert calm == pytest.approx(C.DUES_UNREST[city.charter], abs=0.02)
    city.satisfaction = 0.2
    for turn in range(20, 40):
        world.turn = turn
        _tick(world, economy=_economy(food={"Thornwood": 0.3}))
    target = (C.DUES_UNREST[city.charter] + C.SAT_UNREST * (C.SAT_CALM - 0.2)
              + C.HUNGER_UNREST * (C.HUNGER_FLOOR - 0.3) / C.HUNGER_FLOOR)
    assert city.unrest == pytest.approx(min(1.0, target), abs=0.03) and city.unrest > 0.7
    hungry = city.unrest
    city.satisfaction = 0.45
    world.regions[THORNWOOD].occupied_by = "Kethani Empire"
    world.turn = 40
    before = city.unrest
    _tick(world, economy=_economy(food={"Thornwood": 1.0}))
    occupied = city.unrest
    world.regions[THORNWOOD].occupied_by = None
    city.unrest = before
    world.turn = 41
    _tick(world, economy=_economy(food={"Thornwood": 1.0}))
    assert occupied > city.unrest


def _restless(world: WorldState, *, regions: int = 3, stability: int = 60):
    """A self-governing city of rank 2+ in Thornwood at full unrest; its lord
    Thornwall holds `regions` regions (Iron Peaks added for three)."""
    from chronicler.models import Infrastructure
    if regions >= 3:
        _give(world, IRON, THORNWALL)
    # Walls already stand, so the city spends nothing on them in the test turn.
    world.regions[THORNWOOD].infrastructure.append(Infrastructure(
        type=InfrastructureType.FORTIFICATIONS, builder_civ="Thornwall Confederacy", built_turn=0))
    s = _settle(world, THORNWOOD, 30)
    _tick(world)
    city = _city(world, s.settlement_id)
    city.charter = MARKET_RIGHTS
    city.unrest = 1.0
    city.satisfaction = 0.0
    city.last_petition = world.turn   # no petition in the revolt turn
    world.civilizations[THORNWALL].stability = stability
    return city


def _revolt_turn(world: WorldState, city: City, monkeypatch, *, concede: bool = False):
    monkeypatch.setattr(C, "REVOLT_CHANCE", 1.0)
    monkeypatch.setattr(C, "CONCESSION_CHANCE", 1.0 if concede else 0.0)
    world.turn += 1
    return _tick(world)


def test_a_revolt_against_a_strong_lord_is_put_down(monkeypatch):
    world = _world()
    city = _restless(world, stability=80)
    city.wealth = 40.0
    lord = world.civilizations[THORNWALL]
    treasury = lord.treasury
    events = [e for e in _revolt_turn(world, city, monkeypatch) if e.event_type != "city_walls"]
    assert _types(events) == ["urban_revolt", "revolt_suppressed"]
    assert lord.stability == 80 - C.REVOLT_STABILITY
    fine = world.cities.counters["fines"]
    assert fine >= 9 and lord.treasury == treasury + fine
    assert events[1].causes == [events[0].event_id]
    assert city.charter == MARKET_RIGHTS and city.unrest < 1.0


def test_a_weak_lord_yields_a_charter(monkeypatch):
    # A town without a charter cannot go free; its weak lord concedes one.
    world = _world()
    city = _restless(world, stability=28)
    city.charter = NO_CHARTER
    events = [e for e in _revolt_turn(world, city, monkeypatch) if e.event_type != "city_walls"]
    assert _types(events) == ["urban_revolt", "urban_concession"]
    assert city.charter == MARKET_RIGHTS and city.grievance == 0.0
    # A strong lord concedes only by chance.
    world = _world()
    city = _restless(world, stability=80)
    events = [e for e in _revolt_turn(world, city, monkeypatch, concede=True) if e.event_type != "city_walls"]
    assert _types(events) == ["urban_revolt", "urban_concession"] and city.charter == SELF_GOVERNMENT


def test_a_city_wins_its_freedom_from_a_failing_lord(monkeypatch):
    world = _world()
    city = _restless(world, stability=20)
    lord = world.civilizations[THORNWALL]
    city.wealth = 50.0
    n = len(world.civilizations)
    events = [e for e in _revolt_turn(world, city, monkeypatch) if e.event_type != "city_walls"]
    assert _types(events) == ["urban_revolt", "free_city"]
    assert len(world.civilizations) == n + 1
    free = world.civilizations[n]
    assert free.name == "Free City of Thornwood" and free.regions == ["Thornwood"]
    assert free.capital_region == "Thornwood" and "freedom" in free.values
    assert world.regions[THORNWOOD].controller == free.name
    assert "Thornwood" not in lord.regions
    assert free.treasury > 20 and city.wealth < 30
    assert world.relationships[lord.name][free.name].disposition.value == "hostile"
    assert city.charter == FREE_CITY and city.lord == n
    assert events[1].causes == [events[0].event_id]
    assert events[1].actors == [lord.name, free.name]
    # A free city pays no dues to its old lord; it keeps its share itself.
    C.pay_dues(world, StatAccumulator())
    world.turn = 2
    _tick(world)
    assert world.cities.owed[n] > 0 and world.cities.owed[THORNWALL] == 0.0
    # And it does not revolt against itself.
    city.unrest = 1.0
    world.turn = 3
    assert "urban_revolt" not in _types(_tick(world))


def test_no_free_city_from_a_capital_or_a_small_realm(monkeypatch):
    world = _world()
    city = _restless(world, regions=2, stability=20)
    world.civilizations[THORNWALL].regions.remove("Verdant Plains")   # Thornwood alone
    world.regions[VERDANT].controller = None
    events = _revolt_turn(world, city, monkeypatch)
    assert "free_city" not in _types(events)
    world = _world()
    _give(world, IRON, THORNWALL)
    s = _settle(world, VERDANT, 30)   # the capital
    _tick(world)
    city = _city(world, s.settlement_id)
    city.charter, city.unrest = MARKET_RIGHTS, 1.0
    world.civilizations[THORNWALL].stability = 20
    assert "free_city" not in _types(_revolt_turn(world, city, monkeypatch))


# --- war ------------------------------------------------------------------------

def test_an_occupier_sacks_the_city_once_in_the_cooldown():
    world = _world()
    s = _settle(world, THORNWOOD, 30)
    _tick(world)
    city = _city(world, s.settlement_id)
    city.wealth = 80.0
    occupier = world.civilizations[KETHANI]
    treasury = occupier.treasury
    world.regions[THORNWOOD].occupied_by = occupier.name
    world.turn = 1
    events = _tick(world)
    sacked = [e for e in events if e.event_type == "city_sacked"]
    assert len(sacked) == 1 and sacked[0].actors == [occupier.name, "Thornwall Confederacy"]
    assert occupier.treasury == treasury + 40
    assert city.wealth < 45 and city.grievance > 0
    assert prov.recall(world, prov.key("city_sack", str(s.settlement_id))) == sacked[0].event_id
    world.turn = 2
    assert "city_sacked" not in _types(_tick(world))
    assert city.pull == 0.0   # an occupied city draws no one


def test_a_conqueror_at_war_sacks_and_revokes_a_charter():
    world = _world()
    s = _settle(world, THORNWOOD, 30)
    _tick(world)
    city = _city(world, s.settlement_id)
    city.wealth, city.charter = 60.0, SELF_GOVERNMENT
    world.active_wars.append(("Kethani Empire", "Thornwall Confederacy"))
    _give(world, THORNWOOD, KETHANI)
    world.turn = 1
    events = _tick(world)
    assert "city_sacked" in _types(events)
    assert city.lord == KETHANI and city.charter == MARKET_RIGHTS
    # A peaceful transfer keeps the charter and plunders nothing.
    world.active_wars.clear()
    _give(world, THORNWOOD, THORNWALL)
    world.turn = 30
    events = _tick(world)
    assert "city_sacked" not in _types(events) and "city_lord_changed" in _types(events)
    assert city.charter == MARKET_RIGHTS and city.lord == THORNWALL
    assert city.history[-1][1] == "lord" and city.history[-1][2]


def test_a_rich_city_builds_walls_through_the_infrastructure_pipeline():
    world = _world()
    s = _settle(world, THORNWOOD, 40)
    _tick(world)
    city = _city(world, s.settlement_id)
    city.wealth = C.WALL_COST + 10
    world.turn = 1
    events = _tick(world)
    assert "city_walls" in _types(events)
    build = world.regions[THORNWOOD].pending_build
    assert build.type == InfrastructureType.FORTIFICATIONS and build.builder_civ == "Thornwall Confederacy"
    assert city.wealth < 15
    world.turn = 2
    city.wealth = 100
    assert "city_walls" not in _types(_tick(world))


# --- voice, pull, disease, credit --------------------------------------------------

def test_patricians_raise_the_merchant_faction_within_the_cap():
    world = _world()
    for region in (VERDANT, THORNWOOD):
        _settle(world, region, 45)
    lord = world.civilizations[THORNWALL]
    before = lord.factions.influence[FactionType.MERCHANT]
    _tick(world)
    after = lord.factions.influence[FactionType.MERCHANT]
    assert before < after <= before + C.VOICE_CAP + 1e-9
    assert sum(lord.factions.influence.values()) == pytest.approx(1.0)


def test_city_pull_by_region_and_the_batch_column_only_when_on():
    from chronicler.agent_bridge import build_region_batch
    world = generate_world(seed=42)
    assert "city_pull" not in build_region_batch(world).schema.names
    C.set_cities_enabled(world, True)
    s = _settle(world, THORNWOOD, 45)
    _tick(world)
    city = _city(world, s.settlement_id)
    assert city.pull == pytest.approx(C.RANK_PULL[GREAT_CITY] * (1 - city.unrest), abs=1e-4)
    batch = build_region_batch(world)
    pulls = batch.column("city_pull").to_pylist()
    assert pulls[THORNWOOD] == pytest.approx(city.pull, abs=1e-6)
    assert sum(1 for p in pulls if p) == 1
    # Recomputed every turn from city state: hunger lowers it, a fall removes it.
    world.turn = 1
    _tick(world, economy=_economy(food={"Thornwood": 0.5}))
    assert C.region_pulls(world)[THORNWOOD] == pytest.approx(city.pull) and city.pull < 0.5
    world.regions[THORNWOOD].settlements.clear()
    world.turn = 2
    _tick(world)
    assert C.region_pulls(world) == [0.0] * len(world.regions)


def test_epidemic_susceptibility_and_credit_factors():
    world = _world()
    s = _settle(world, THORNWOOD, 30)
    _tick(world)
    city = _city(world, s.settlement_id)
    region = world.regions[THORNWOOD]
    factors = C.epidemic_susceptibility_factors(world)
    share = min(1.0, city.residents / region.population)
    assert factors[THORNWOOD] == pytest.approx(1 + C.URBAN_SUSCEPTIBILITY * share)
    assert all(f == 1.0 for i, f in enumerate(factors) if i != THORNWOOD)
    assert C.credit_factor(world, THORNWALL) == 1.0
    city.charter = SELF_GOVERNMENT
    assert C.credit_factor(world, THORNWALL) == pytest.approx(1 + 2 * C.CREDIT_PER_CHARTER)


def test_epidemiology_reads_the_urban_factor():
    import chronicler.contact_ledger as cl
    import chronicler.epidemiology as ep
    world = _world()
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    _settle(world, THORNWOOD, 45)
    _tick(world)
    seen = {}
    real = ep._introduce

    def spy(world, state, rows, mods):
        seen["mods"] = list(mods)
        return real(world, state, rows, mods)

    ep._introduce = spy
    try:
        ep.tick_epidemics(world)
    finally:
        ep._introduce = real
    base = ep._modifiers(world.regions[THORNWOOD])[0]
    assert seen["mods"][THORNWOOD][0] == pytest.approx(base * C.epidemic_susceptibility_factors(world)[THORNWOOD])
    assert seen["mods"][AMBER][0] == pytest.approx(ep._modifiers(world.regions[AMBER])[0])


# --- snapshot, history, metrics ------------------------------------------------------

def test_snapshot_history_and_metrics():
    world = _world()
    s = _settle(world, THORNWOOD, 30)
    _tick(world)
    summary = C.snapshot_summary(world)
    row = summary["cities"][0]
    assert row["id"] == s.settlement_id and row["region"] == "Thornwood"
    assert row["lord"] == "Thornwall Confederacy" and row["rank"] >= CITY
    lines = C.city_history(world, s.settlement_id)
    assert lines and lines[0].startswith("0: founded: " + s.name)
    bundle = {"metadata": {"seed": 42}, "history": [{"cities": summary}, {"cities": summary}]}
    run = C.extract_city_metrics([bundle, {"history": [{}]}])["runs"]
    assert len(run) == 1 and run[0]["cities_peak"] == 1 and run[0]["seed"] == 42


def test_city_events_are_named_in_world_for_narration():
    """The languages layer names the settlement and maps its canonical name
    in a city event to the in-world name the narrator is given."""
    from chronicler import languages as L
    world = _world()
    L.set_languages_enabled(world, True)
    s = _settle(world, THORNWOOD, 30)
    L.observe_turn(world)
    world.turn = 1
    events = _tick(world)
    index = L.NameIndex(L.export(world))
    assert ("settlement", s.settlement_id) in index.entities(events)
    view = index.views("settlement", s.settlement_id, world.turn)
    assert view is not None and view["canonical"] == s.name and view["name"]


# --- the switch in a run ---------------------------------------------------------------

def test_feature_off_never_runs_city_code(monkeypatch):
    import chronicler.contact_ledger as cl
    import chronicler.epidemiology as ep
    import chronicler.finance as F

    def boom(*a, **k):
        raise AssertionError("city code ran with the switch off")

    for name in ("tick_cities", "pay_dues", "region_pulls", "epidemic_susceptibility_factors",
                 "credit_factor", "snapshot_summary", "economy_columns", "with_economy_columns",
                 "merchant_route_graph", "cut_off_regions"):
        monkeypatch.setattr(C, name, boom)
    world = generate_world(seed=42)
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    F.set_finance_enabled(world, True)
    _settle(world, THORNWOOD, 30)
    _advance(world, 25)
    from chronicler.agent_bridge import build_region_batch
    assert "city_pull" not in build_region_batch(world).schema.names


def test_off_mode_cities_live_through_a_run_and_repeat():
    def run():
        world = _world()
        world.campaigns_enabled = True
        _settle(world, THORNWOOD, 40)
        _settle(world, AMBER, 25)
        return _advance(world, 40)
    a, b = run(), run()
    assert a.model_dump_json() == b.model_dump_json()
    assert len(a.cities.cities) == 2 and a.cities.counters["dues"] > 0
    assert all(c.wealth > 0 for c in a.cities.cities)


def test_cli_flag_gate_forwarding_and_live_default():
    from chronicler.main import _build_parser
    parser = _build_parser()
    assert parser.parse_args([]).cities is None
    assert parser.parse_args(["--cities"]).cities is True
    assert parser.parse_args(["--no-cities"]).cities is False
    spec = importlib.util.spec_from_file_location("m53b", ROOT / "scripts" / "m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._cities_args(argparse.Namespace(cities=True)) == ["--cities"]
    assert m53b._cities_args(argparse.Namespace(cities=False)) == ["--no-cities"]
    assert m53b._cities_args(argparse.Namespace(cities=None)) == []
    assert "set_cities_enabled" in (ROOT / "src" / "chronicler" / "live.py").read_text()


def test_identity_script_strips_only_the_cities_fields(tmp_path):
    spec = importlib.util.spec_from_file_location("cities_identity", ROOT / "scripts" / "cities_identity.py")
    ident = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ident)
    base, new = tmp_path / "base", tmp_path / "new"
    for d in (base, new):
        d.mkdir()
    (base / "state.json").write_text(json.dumps({"turn": 3}))
    (new / "state.json").write_text(json.dumps({"turn": 3, "cities": {"cities": []}}))
    bundle = {"metadata": {"generated_at": "x"}, "history": [{"turn": 1}], "world_state": {"turn": 3}}
    (base / "chronicle_bundle.json").write_text(json.dumps(bundle))
    bundle["history"][0]["cities"] = {"cities": []}
    bundle["world_state"]["cities"] = {}
    bundle["metadata"]["generated_at"] = "y"
    (new / "chronicle_bundle.json").write_text(json.dumps(bundle))
    assert ident.compare(base, new, inert=True) == (2, [])
    assert len(ident.compare(base, new)[1]) == 2
    (base / "chronicle.md").write_text("a")
    (new / "chronicle.md").write_text("b")
    assert ident.compare(base, new, inert=True)[1][0].startswith("differs: chronicle.md")


def test_cli_run_off_mode_keeps_bytes_and_the_switch_persists(tmp_path):
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    out = tmp_path / "on"
    args = parser.parse_args(["--seed", "42", "--turns", "5", "--civs", "4", "--regions", "8",
                              "--simulate-only", "--cities",
                              "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    execute_run(args)
    state = json.loads((out / "state.json").read_text())
    assert state["cities"]["cities"] == []   # no settlements without agents
    bundle = json.loads((out / "chronicle_bundle.json").read_text())
    assert all("cities" in h for h in bundle["history"])
    off = tmp_path / "off"
    execute_run(parser.parse_args(["--seed", "42", "--turns", "3", "--civs", "4", "--regions", "8",
                                   "--simulate-only", "--output", str(off / "chronicle.md"),
                                   "--state", str(off / "state.json")]))
    assert "cities" not in json.loads((off / "state.json").read_text())
    from chronicler.analytics import generate_report
    assert len(generate_report(tmp_path)["cities"]["runs"]) == 1
    # Resumed without the flag, the world keeps its setting.
    args = parser.parse_args(["--seed", "42", "--turns", "7", "--simulate-only",
                              "--resume", str(out / "state.json"),
                              "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    execute_run(args)
    assert "cities" in json.loads((out / "state.json").read_text())


# --- native hybrid --------------------------------------------------------------------

def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


@pytest.mark.native
def test_native_hybrid_run_founds_cities(tmp_path):
    _require_native()
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    out = tmp_path / "hyb"
    args = parser.parse_args(["--seed", "42", "--turns", "60", "--civs", "4", "--regions", "8",
                              "--agents", "hybrid", "--simulate-only",
                              "--cities", "--output", str(out / "chronicle.md"),
                              "--state", str(out / "state.json")])
    execute_run(args)
    world = WorldState.load(out / "state.json")
    assert world.cities.counters["founded"] >= 1
    city = (world.cities.cities + world.cities.fallen)[0]
    assert city.satisfaction is not None and abs(sum(city.mix) - 1.0) < 0.01
    bundle = json.loads((out / "chronicle_bundle.json").read_text())
    assert any(h.get("cities", {}).get("cities") for h in bundle["history"])


@pytest.mark.native
def test_native_city_pull_signal_is_consumed_and_reset_each_turn(make_world):
    """The region batch carries city_pull while a city draws; Rust reads it
    every tick and returns to 0 when the column is absent."""
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    world = make_world(num_civs=2)
    world.agent_mode = "hybrid"
    home, city_region = world.regions
    home.carrying_capacity = city_region.carrying_capacity = 60
    home.population, city_region.population = 30, 20
    home.adjacencies = [city_region.name]
    city_region.adjacencies = [home.name]
    civ0, civ1 = world.civilizations
    city_region.controller = civ0.name
    civ0.regions, civ1.regions = [home.name, city_region.name], []
    civ0.population, civ1.population = 50, 0
    C.set_cities_enabled(world, True)
    world.cities.cities.append(City(settlement_id=1, region=1, name="Hub", founded_turn=0,
                                    founder=0, lord=0, rank=GREAT_CITY, pull=1.0))
    bridge = AgentBridge(world, mode="hybrid")
    gates = []
    for turn in range(1, 7):
        world.turn = turn
        if turn == 4:
            C.set_cities_enabled(world, False)   # the column disappears
        bridge.tick(world)
        gates.append(bridge._sim.get_migration_driver_stats()["gate_urban"])
    assert all(g > 0 for g in gates[:3]), gates
    assert gates[3:] == [0, 0, 0], gates


@pytest.mark.native
def test_native_budget_reports_the_urban_term(make_world):
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    world = make_world(num_civs=1)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    world.turn = 1
    bridge.tick(world)
    stats = bridge._sim.get_migration_driver_stats()
    for key in ("share_urban", "present_urban", "follow_urban", "open_urban", "gate_urban"):
        assert key in stats


def test_a_free_city_lives_on_with_every_system_on(monkeypatch):
    """A free city is a polity the other systems take up: it runs with the
    ledger, epidemics, finance, diplomacy, techniques, maritime, agendas and
    nomads on, and can be found again after a save/load."""
    import chronicler.contact_ledger as cl
    import chronicler.diplomacy as dp
    import chronicler.epidemiology as ep
    import chronicler.finance as F
    import chronicler.gp_agendas as ga
    import chronicler.maritime as mt
    import chronicler.nomads as nm
    import chronicler.techniques as tq
    world = _world()
    world.campaigns_enabled = True
    for setter in (cl.set_contact_ledger_enabled, ep.set_epidemiology_enabled, F.set_finance_enabled,
                   dp.set_diplomacy_enabled, tq.set_techniques_enabled, mt.set_maritime_enabled,
                   ga.set_gp_agendas_enabled, nm.set_nomads_enabled):
        setter(world, True)
    _advance(world, 3)
    city = _restless(world, stability=20)
    events = _revolt_turn(world, city, monkeypatch)
    assert "free_city" in _types(events)
    free = world.civilizations[-1]
    monkeypatch.setattr(C, "REVOLT_CHANCE", 0.0)
    _advance(world, 8)
    assert free.regions == ["Thornwood"] or world.regions[THORNWOOD].controller != free.name
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert loaded.model_dump_json() == world.model_dump_json()
