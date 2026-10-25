"""Pastoral and nomadic peoples: subsistence modes, herds, raids and tribute,
hordes and sedentarization (``chronicler.nomads``, ``--nomads``)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import chronicler.nomads as N
from chronicler import provenance as prov
from chronicler.action_engine import ActionEngine
from chronicler.models import (
    ActionType, Disposition, Event, Federation, Leader, TurnSnapshot, WorldState,
)
from chronicler.nomads_state import (
    AGRO_PASTORAL, NOMADIC, SEDENTARY, Conquest, NomadState, Raid, TributePact,
)
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world

# Template seed 42 (8 regions): the Selurian Republic holds only Ashara Desert
# (3) and is nomadic; Amber Valley (5, Kethani Empire) and Verdant Plains (2,
# Thornwall Confederacy) border it.
DESERT, VERDANT, AMBER, THORNWOOD, FROST, SHORE = 3, 2, 5, 4, 0, 7
ASHKARI, KETHANI, THORNWALL, SELURIAN = 0, 1, 2, 3


def _template(seed: int = 42) -> WorldState:
    world = generate_world(seed=seed)
    N.set_nomads_enabled(world, True)
    return world


def _steppe_template() -> WorldState:
    """Template 42 with Thornwall on the steppe: two nomadic peoples (Thornwall,
    Selurian) side by side, Kethani and Ashkari settled."""
    world = generate_world(seed=42)
    for idx in (VERDANT, THORNWOOD):
        world.regions[idx].terrain = "steppe"
    N.set_nomads_enabled(world, True)
    return world


def _proc(seed: int = 13, regions: int = 48, civs: int = 10) -> WorldState:
    world = generate_world(seed=seed, num_regions=regions, num_civs=civs, worldgen="procedural")
    world.campaigns_enabled = True
    N.set_nomads_enabled(world, True)
    return world


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
    region.occupied_by = None
    civ.regions.append(region.name)
    world.invalidate_trade_route_cache()


def _season(monkeypatch, season: int) -> None:
    import chronicler.resources as res
    monkeypatch.setattr(res, "get_season_id", lambda turn: season)


def _quiet(monkeypatch) -> None:
    """Switch off the per-turn draws a focused test does not exercise."""
    for name, value in (("RAID_MAX", 0.0), ("HORDE_CHANCE", 0.0), ("HORDE_WAVE_CHANCE", 0.0),
                        ("DZUD_CHANCE", 0.0)):
        monkeypatch.setattr(N, name, value)


def _events(result, event_type: str) -> list[Event]:
    return [e for e in result if e.event_type == event_type]


# --- subsistence ---------------------------------------------------------------------------

def test_modes_are_seeded_from_terrain():
    assert N.seed_mode(0.9) == NOMADIC and N.seed_mode(0.5) == AGRO_PASTORAL
    assert N.seed_mode(0.2) == SEDENTARY
    world = _template()
    assert world.nomads.modes == [SEDENTARY, SEDENTARY, SEDENTARY, NOMADIC]
    # Herds start on pastoral land only, at the nomads' share of its pasture.
    herds = world.nomads.herds
    assert herds[DESERT] == round(N.HERD_START[NOMADIC] * N.capacity(world.regions[DESERT]), 4)
    assert all(h == 0.0 for i, h in enumerate(herds) if i != DESERT)
    steppe = _steppe_template()
    assert steppe.nomads.modes[THORNWALL] == NOMADIC
    # A procedural world: the civ on two steppe regions herds, farmers do not.
    proc = _proc(13)
    for ci, civ in enumerate(proc.civilizations):
        terrains = {proc.region_map[n].terrain for n in civ.regions}
        if terrains == {"steppe"}:
            assert proc.nomads.modes[ci] == NOMADIC
        if terrains <= {"forest", "coast", "jungle"}:
            assert proc.nomads.modes[ci] == SEDENTARY


def test_new_polities_are_seeded_at_their_first_tick(monkeypatch):
    _quiet(monkeypatch)
    world = _template()
    parent = world.civilizations[KETHANI]
    newcomer = parent.model_copy(deep=True)
    newcomer.name = "Frost Clans"
    newcomer.regions = []
    world.civilizations.append(newcomer)
    world.invalidate_civ_map()
    _give(world, FROST, len(world.civilizations) - 1)
    landless = parent.model_copy(deep=True)
    landless.name = "Wanderers"
    landless.regions = []
    world.civilizations.append(landless)
    world.invalidate_civ_map()
    N.tick_nomads(world)
    assert world.nomads.modes[4] == NOMADIC       # tundra
    assert world.nomads.modes[5] == SEDENTARY     # landless
    assert len(world.nomads.settle) == len(world.civilizations)


# --- herds ---------------------------------------------------------------------------------

def test_herds_grow_toward_their_pasture(monkeypatch):
    _quiet(monkeypatch)
    _season(monkeypatch, 0)
    world = _template()
    region = world.regions[DESERT]
    world.nomads.herds[DESERT] = 2.0
    k = N.seasonal_capacity(region, 0)
    prev = 2.0
    for _ in range(80):
        N.tick_nomads(world)
        h = world.nomads.herds[DESERT]
        assert h >= prev - 1e-9 and h <= k + 1e-6
        prev = h
    assert prev > 0.9 * k


def test_drought_shrinks_the_pasture_and_kills_the_overshoot(monkeypatch):
    _quiet(monkeypatch)
    _season(monkeypatch, 0)
    world = _template()
    region = world.regions[DESERT]
    world.nomads.herds[DESERT] = N.seasonal_capacity(region, 0)
    full = world.nomads.herds[DESERT]
    region.ecology.water = 0.01          # the wells run dry
    N.tick_nomads(world)
    assert world.nomads.herds[DESERT] < full
    assert world.nomads.counters["herds_lost_pasture"] > 0


def test_dzud_strikes_cold_pasture_in_winter_only(monkeypatch):
    _quiet(monkeypatch)
    world = _steppe_template()
    world.nomads.herds[VERDANT] = 60.0
    world.nomads.herds[THORNWOOD] = 60.0
    monkeypatch.setattr(N, "DZUD_CHANCE", 1.0)
    monkeypatch.setattr(N, "MOBILITY", {AGRO_PASTORAL: 0.0, NOMADIC: 0.0})
    _season(monkeypatch, 1)
    N.tick_nomads(world)
    assert world.nomads.counters["herds_lost_dzud"] == 0
    _season(monkeypatch, 3)
    result = N.tick_nomads(world)
    dzuds = _events(result, "dzud")
    assert world.nomads.counters["herds_lost_dzud"] > 0 and len(dzuds) == 1
    assert dzuds[0].actors == ["Thornwall Confederacy"] and dzuds[0].region in ("Verdant Plains", "Thornwood")
    # A dzud is the herd loss that raids answer.
    assert prov.recall(world, prov.key("herd_loss", "Thornwall Confederacy")) == dzuds[0].event_id


def test_transhumance_follows_the_seasonal_pasture_and_conserves_herds(monkeypatch):
    _quiet(monkeypatch)
    for name in ("HERD_GROWTH", "HERD_INFLOW", "HERD_DIEOFF"):
        monkeypatch.setattr(N, name, 0.0)
    world = _template()
    _give(world, FROST, SELURIAN)        # tundra summer pasture, desert winter pasture
    world.nomads.herds[DESERT] = 30.0
    world.nomads.herds[FROST] = 30.0
    _season(monkeypatch, 1)
    for _ in range(6):
        N.tick_nomads(world)
    summer = (world.nomads.herds[FROST], world.nomads.herds[DESERT])
    assert abs(sum(summer) - 60.0) < 1e-3
    assert summer[0] > summer[1]           # up to the tundra for the summer
    _season(monkeypatch, 3)
    for _ in range(6):
        N.tick_nomads(world)
    winter = (world.nomads.herds[FROST], world.nomads.herds[DESERT])
    assert abs(sum(winter) - 60.0) < 1e-3
    assert winter[1] > winter[0]           # down to the desert for the winter


def test_mobility_spares_nomads_the_winter_die_off(monkeypatch):
    _quiet(monkeypatch)
    losses = {}
    for mode in (NOMADIC, AGRO_PASTORAL):
        world = _template()
        _give(world, FROST, SELURIAN)
        world.nomads.modes[SELURIAN] = mode
        world.nomads.herds[DESERT] = 20.0
        world.nomads.herds[FROST] = 40.0
        _season(monkeypatch, 3)
        for _ in range(3):
            N.tick_nomads(world)
        losses[mode] = world.nomads.counters["herds_lost_pasture"]
    assert losses[NOMADIC] < losses[AGRO_PASTORAL]


def test_herds_on_settled_land_are_slaughtered_away(monkeypatch):
    _quiet(monkeypatch)
    world = _template()
    world.nomads.herds[DESERT] = 40.0
    _give(world, DESERT, KETHANI)        # the desert passes to farmers
    for _ in range(25):
        N.tick_nomads(world)
    assert world.nomads.herds[DESERT] == 0.0


# --- the food hook --------------------------------------------------------------------------

def test_food_hook_is_the_identity_when_off_or_settled():
    from chronicler.climate import get_climate_phase
    from chronicler.ecology import compute_resource_yields
    world = generate_world(seed=42)
    region = world.regions[DESERT]
    yields = [0.5, 0.2, 0.0]
    assert N.food_yields(world, region, yields, 0) is yields
    N.set_nomads_enabled(world, True)
    amber = world.regions[AMBER]
    assert N.food_yields(world, amber, yields, 0) is yields      # settled land
    phase = get_climate_phase(world.turn, world.climate_config)
    off = generate_world(seed=42)
    assert (compute_resource_yields(off.regions[AMBER], 1, phase, 0, off, deplete_reserves=False)
            == compute_resource_yields(amber, 1, phase, 0, world, deplete_reserves=False))


def test_herders_farm_less_and_eat_from_their_herds():
    from chronicler.models import ResourceType
    world = _template()
    _give(world, AMBER, SELURIAN)        # grain land under nomads
    world.nomads.herds[AMBER] = 50.0
    region = world.regions[AMBER]
    assert region.resource_types[0] == ResourceType.GRAIN
    out = N.food_yields(world, region, [0.8, 0.0, 0.0], 1)
    herd = N.HERD_FOOD * 0.5 * N.HERD_FOOD_SHARE[NOMADIC] * N.HERD_FOOD_SEASON[1]
    assert out[0] == pytest.approx(0.8 * N.CROP_SHARE[NOMADIC] + herd)
    world.nomads.modes[SELURIAN] = AGRO_PASTORAL
    out = N.food_yields(world, region, [0.8, 0.0, 0.0], 3)
    herd = N.HERD_FOOD * 0.5 * N.HERD_FOOD_SHARE[AGRO_PASTORAL] * N.HERD_FOOD_SEASON[3]
    assert out[0] == pytest.approx(0.8 * N.CROP_SHARE[AGRO_PASTORAL] + herd)


def test_herd_food_reaches_the_famine_check_and_the_goods_economy():
    from chronicler.climate import get_climate_phase
    from chronicler.ecology import check_food_yield, compute_resource_yields, refresh_resource_yields
    from chronicler.experimental.fisheries import economy_yield
    world = _template()
    region = world.regions[DESERT]
    phase = get_climate_phase(world.turn, world.climate_config)
    world.nomads.herds[DESERT] = 0.0
    bare = compute_resource_yields(region, 3, phase, 0, world, deplete_reserves=False)
    world.nomads.herds[DESERT] = 60.0
    fed = compute_resource_yields(region, 3, phase, 0, world, deplete_reserves=False)
    assert fed[0] > bare[0]
    assert check_food_yield(region, bare, phase) and not check_food_yield(region, fed, phase)
    refresh_resource_yields(world, phase)
    with_herds = economy_yield(world, region, 0)
    assert with_herds > 0
    world.nomads.herds[DESERT] = 0.0
    refresh_resource_yields(world, phase)
    assert with_herds > economy_yield(world, region, 0)


# --- raids -------------------------------------------------------------------------------------

def _raiding(monkeypatch, world: WorldState, *, strong: bool = True) -> None:
    _quiet(monkeypatch)
    monkeypatch.setattr(N, "raid_chance", lambda w, ci: 1.0)
    raider, k, t = world.civilizations[SELURIAN], world.civilizations[KETHANI], world.civilizations[THORNWALL]
    raider.military = 100 if strong else 0
    for victim in (k, t):
        victim.military = 0 if strong else 100
        world.relationships[raider.name][victim.name].disposition = Disposition.NEUTRAL
        world.relationships[victim.name][raider.name].disposition = Disposition.NEUTRAL


def test_raid_plunders_a_settled_neighbour(monkeypatch):
    world = _template()
    _raiding(monkeypatch, world)
    raider = world.civilizations[SELURIAN]
    before = {c.name: (c.treasury, c.stability) for c in world.civilizations}
    pops = [r.population for r in world.regions]
    result = N.tick_nomads(world)
    raids = _events(result, "raid")
    assert len(raids) == 1
    raid = world.nomads.raids[-1]
    assert raid.success and raid.raider == SELURIAN and raid.region in (AMBER, VERDANT)
    victim = world.civilizations[raid.target]
    assert raid.loot > 0
    assert raider.treasury == before[raider.name][0] + raid.loot
    assert victim.treasury == before[victim.name][0] - raid.loot
    assert victim.stability < before[victim.name][1]
    assert world.regions[raid.region].population == pops[raid.region] - raid.killed > 0 or raid.killed
    assert raids[0].event_id == raid.event_id and raids[0].region == world.regions[raid.region].name
    rel = world.relationships[victim.name][raider.name]
    assert rel.disposition in (Disposition.SUSPICIOUS, Disposition.HOSTILE)
    assert world.nomads.counters["raids"] == 1 and world.nomads.counters["plunder"] == raid.loot


def test_repulsed_raid_costs_the_raiders(monkeypatch):
    world = _template()
    _raiding(monkeypatch, world, strong=False)
    raider = world.civilizations[SELURIAN]
    pop = world.regions[DESERT].population
    result = N.tick_nomads(world)
    assert len(_events(result, "raid_repulsed")) == 1
    assert not world.nomads.raids[-1].success
    assert world.regions[DESERT].population < pop
    assert world.nomads.counters["raids_repulsed"] == 1 and raider.treasury == 35


@pytest.mark.parametrize("guard", ["friendly", "allied_back", "federation", "tribute", "war", "vassal", "truce"])
def test_no_raids_on_friends_federations_tributaries_or_enemies_at_war(monkeypatch, guard):
    from chronicler.models import TreatyRecord, VassalRelation
    world = _template()
    _raiding(monkeypatch, world)
    raider = world.civilizations[SELURIAN]
    for ti in (KETHANI, THORNWALL):
        target = world.civilizations[ti]
        if guard == "friendly":
            world.relationships[raider.name][target.name].disposition = Disposition.FRIENDLY
        elif guard == "allied_back":
            world.relationships[target.name][raider.name].disposition = Disposition.ALLIED
        elif guard == "tribute":
            world.nomads.tributes.append(TributePact(pact_id=ti, payer=ti, recipient=SELURIAN,
                                                     amount=2, start_turn=0))
        elif guard == "war":
            world.active_wars.append((raider.name, target.name))
        elif guard == "vassal":
            world.vassal_relations.append(VassalRelation(overlord=target.name, vassal=raider.name))
        elif guard == "truce":
            world.war_state.treaties.append(TreatyRecord(turn=0, name="t", war_key="k",
                                                         parties=[raider.name, target.name], kind="negotiated"))
    if guard == "federation":
        world.federations.append(Federation(name="The Pact", founded_turn=0,
                                            members=[raider.name, "Kethani Empire", "Thornwall Confederacy"]))
    t = N._Tick(world, None, None)
    assert N._raid_targets(t, SELURIAN) == []


def test_raids_leave_one_border_grievance_each(monkeypatch):
    import chronicler.diplomacy as dp
    from chronicler.diplomacy_state import BORDER
    world = _template()
    dp.set_diplomacy_enabled(world, True)
    _raiding(monkeypatch, world)
    N.tick_nomads(world)
    raid = world.nomads.raids[-1]
    victim, raider = world.civilizations[raid.target].name, world.civilizations[raid.raider].name
    dp._nomad_inputs(world)
    assert dp.grievance(world, victim, raider, (BORDER,)) == dp.GRIEVANCE_RAID
    # Next turn, without a raid, the old raid is not counted again.
    world.turn += 1
    dp._nomad_inputs(world)
    assert dp.grievance(world, victim, raider, (BORDER,)) == dp.GRIEVANCE_RAID


def test_a_war_between_the_pair_cites_the_raid(monkeypatch):
    world = _template()
    _raiding(monkeypatch, world)
    N.tick_nomads(world)
    raid = world.nomads.raids[-1]
    names = [world.civilizations[raid.target].name, world.civilizations[raid.raider].name]
    war = Event(turn=world.turn, event_type="war_declared", actors=names, description="war")
    prov.observe_now(world, war)
    assert raid.event_id in war.causes


def test_repeated_raids_buy_a_tribute_that_is_paid_and_spares_the_payer(monkeypatch):
    world = _template()
    _raiding(monkeypatch, world)
    monkeypatch.setattr(N, "TRIBUTE_CHANCE", 1.0)
    monkeypatch.setattr(N, "TRIBUTE_CHANCE_CAUTIOUS", 1.0)
    monkeypatch.setattr(N, "TRIBUTE_CHANCE_BOLD", 1.0)
    monkeypatch.setattr(N, "TRIBUTE_POWER", 99.0)
    # Only Amber Valley is in reach: Thornwall is a friend.
    world.relationships["Selurian Republic"]["Thornwall Confederacy"].disposition = Disposition.FRIENDLY
    agreed = []
    for _ in range(4):
        agreed += _events(N.tick_nomads(world), "tribute_agreed")
        world.turn += 1
        if agreed:
            break
    assert len(agreed) == 1
    pact = world.nomads.active_tributes()[0]
    assert (pact.payer, pact.recipient) == (KETHANI, SELURIAN)
    raids = [r.event_id for r in world.nomads.raids if r.target == KETHANI]
    assert set(agreed[0].causes) <= set(raids) and agreed[0].causes
    payer, recipient = world.civilizations[KETHANI], world.civilizations[SELURIAN]
    p0, r0 = payer.treasury, recipient.treasury
    count = world.nomads.counters["raids"]
    N.tick_nomads(world)
    assert payer.treasury == p0 - pact.amount and recipient.treasury == r0 + pact.amount
    assert pact.paid == pact.amount
    assert world.nomads.counters["raids"] == count     # the payer is spared


def test_a_payer_grown_strong_repudiates_the_tribute(monkeypatch):
    import chronicler.diplomacy as dp
    from chronicler.diplomacy_state import TREATY
    world = _template()
    dp.set_diplomacy_enabled(world, True)
    _quiet(monkeypatch)
    monkeypatch.setattr(N, "TRIBUTE_REPUDIATE_CHANCE", 1.0)
    pact = TributePact(pact_id=1, payer=KETHANI, recipient=SELURIAN, amount=3, start_turn=0,
                       event_id="0:tribute_agreed:0")
    world.nomads.tributes.append(pact)
    world.turn = 3
    world.civilizations[KETHANI].military = 100
    world.civilizations[SELURIAN].military = 0
    result = N.tick_nomads(world)
    ended = _events(result, "tribute_ended")
    assert pact.status == "repudiated" and len(ended) == 1
    assert "0:tribute_agreed:0" in ended[0].causes
    dp._nomad_inputs(world)
    assert dp.grievance(world, "Selurian Republic", "Kethani Empire", (TREATY,)) == dp.GRIEVANCE_TRIBUTE_REPUDIATED


# --- hordes ------------------------------------------------------------------------------------

def _horde_world(monkeypatch) -> WorldState:
    world = _steppe_template()
    _quiet(monkeypatch)
    monkeypatch.setattr(N, "HORDE_CHANCE", 1.0)
    monkeypatch.setattr(N, "SUBMIT_BASE", 1.0)
    khan = world.civilizations[THORNWALL]
    khan.asabiya, khan.stability, khan.military = 0.9, 60, 90
    world.civilizations[SELURIAN].military = 10
    world.turn = 5
    return world


def test_a_strong_khan_unites_the_clans_into_a_horde_federation(monkeypatch):
    world = _horde_world(monkeypatch)
    result = N.tick_nomads(world)
    formed = _events(result, "horde_formed")
    assert len(formed) == 1
    horde = world.nomads.active_hordes()[0]
    assert horde.khan == THORNWALL and horde.members == [THORNWALL, SELURIAN]
    assert horde.khan_leader == world.civilizations[THORNWALL].leader.name
    fed = [f for f in world.federations if f.name == horde.name]
    assert fed and fed[0].members == ["Thornwall Confederacy", "Selurian Republic"]
    for a, b in (("Thornwall Confederacy", "Selurian Republic"), ("Selurian Republic", "Thornwall Confederacy")):
        assert world.relationships[a][b].disposition == Disposition.ALLIED
    assert formed[0].event_id == horde.event_id
    # A second tick keeps it (the khan reigns) and does not form another.
    N.tick_nomads(world)
    assert len(world.nomads.hordes) == 1 and horde.status == "active"
    # The federation code now holds it together: a member it sheds leaves the horde.
    assert N._horde_of(world.nomads, SELURIAN) is horde


def test_a_dominant_nomad_takes_command_of_his_federation(monkeypatch):
    world = _horde_world(monkeypatch)
    formed_fed = Event(turn=world.turn, event_type="federation_formed",
                       actors=["Thornwall Confederacy", "Kethani Empire"], description="Formation")
    prov.observe_now(world, formed_fed)
    world.federations.append(Federation(name="The Iron Pact", founded_turn=1,
                                        members=["Thornwall Confederacy", "Kethani Empire"]))
    world.civilizations[KETHANI].military = 10
    result = N.tick_nomads(world)
    formed = _events(result, "horde_formed")
    assert len(formed) == 1 and "The Iron Pact" in formed[0].description
    horde = world.nomads.active_hordes()[0]
    assert horde.khan == THORNWALL and horde.members == [THORNWALL, KETHANI]
    # The federation itself becomes the horde (renamed); no second federation.
    assert [f.name for f in world.federations] == [horde.name]
    assert world.federations[0].members == ["Thornwall Confederacy", "Kethani Empire"]
    assert formed_fed.event_id in formed[0].causes
    # The khan's death breaks the federation he had taken over.
    world.civilizations[THORNWALL].leader = Leader(name="Elder Heir", trait="cautious", reign_start=world.turn)
    world.turn += 1
    N.tick_nomads(world)
    assert horde.status == "fragmented" and world.federations == []


def test_an_outranked_nomad_does_not_take_command(monkeypatch):
    world = _horde_world(monkeypatch)
    world.federations.append(Federation(name="The Iron Pact", founded_turn=1,
                                        members=["Thornwall Confederacy", "Kethani Empire"]))
    kethani = world.civilizations[KETHANI]
    kethani.military, kethani.stability, kethani.population = 100, 100, 400
    assert N._power(kethani) > N._power(world.civilizations[THORNWALL])
    N.tick_nomads(world)
    assert world.nomads.hordes == [] and [f.name for f in world.federations] == ["The Iron Pact"]


def test_the_horde_breaks_apart_when_the_khan_dies(monkeypatch):
    world = _horde_world(monkeypatch)
    N.tick_nomads(world)
    horde = world.nomads.active_hordes()[0]
    khan = world.civilizations[THORNWALL]
    death = Event(turn=world.turn, event_type="leader_death", actors=[khan.name], description="died")
    prov.observe_now(world, death)
    khan.leader = Leader(name="Chieftain Heir", trait="cautious", reign_start=world.turn)
    asabiya = world.regions[VERDANT].asabiya_state.asabiya
    stability = khan.stability
    world.turn += 1
    result = N.tick_nomads(world)
    broken = _events(result, "horde_fragmented")
    assert len(broken) == 1 and horde.status == "fragmented" and horde.end_turn == world.turn
    assert death.event_id in broken[0].causes and horde.event_id in broken[0].causes
    assert not any(f.name == horde.name for f in world.federations)
    for a, b in (("Thornwall Confederacy", "Selurian Republic"), ("Selurian Republic", "Thornwall Confederacy")):
        assert world.relationships[a][b].disposition == Disposition.SUSPICIOUS
    assert khan.stability == stability - N.FRAGMENT_STABILITY
    assert world.regions[VERDANT].asabiya_state.asabiya < asabiya
    # A secession or collapse of the khan's people soon after cites the break.
    secession = Event(turn=world.turn, event_type="secession", actors=[khan.name, "Rebels"],
                      description="secession")
    prov.observe_now(world, secession)
    assert broken[0].event_id in secession.causes


def test_the_horde_dissolves_when_the_federation_sheds_its_clans(monkeypatch):
    world = _horde_world(monkeypatch)
    N.tick_nomads(world)
    horde = world.nomads.active_hordes()[0]
    fed = next(f for f in world.federations if f.name == horde.name)
    fed.members.remove("Selurian Republic")   # the federation dissolution rule ejected it
    world.turn += 1
    result = N.tick_nomads(world)
    assert horde.status == "dissolved" and len(_events(result, "horde_dissolved")) == 1
    assert not any(f.name == horde.name for f in world.federations)


def test_the_horde_rides_to_war_through_the_campaign_path(monkeypatch):
    from chronicler.war.peace import war_key
    world = _horde_world(monkeypatch)
    world.campaigns_enabled = True
    # Kethani is the only settled neighbour (it takes the Ashkari shore).
    _give(world, SHORE, KETHANI)
    N.tick_nomads(world)
    horde = world.nomads.active_hordes()[0]
    monkeypatch.setattr(N, "HORDE_WAVE_CHANCE", 1.0)
    monkeypatch.setattr(N, "HORDE_RIDE_CHANCE", 1.0)
    world.turn += 1
    result = N.tick_nomads(world)
    rides = _events(result, "horde_rides")
    assert ("Thornwall Confederacy", "Kethani Empire") in world.active_wars
    war = next(w for w in world.war_state.wars if w.war_key == war_key("Thornwall Confederacy", "Kethani Empire"))
    assert war.aim == "conquest"               # a horde seeks conquest, not tribute
    declared = prov.recall(world, prov.war_key("Thornwall Confederacy", "Kethani Empire"))
    assert rides and declared in rides[0].causes and horde.event_id in rides[0].causes
    # Selurian borders Kethani at Amber Valley: it rides with the khan.
    assert ("Selurian Republic", "Kethani Empire") in world.active_wars
    assert any(e.actors[:2] == ["Selurian Republic", "Thornwall Confederacy"] for e in rides)
    assert horde.wars == 2 and world.nomads.counters["horde_rides"] == 1


def test_horde_conquest_aim_only_against_settled_peoples(monkeypatch):
    world = _horde_world(monkeypatch)
    N.tick_nomads(world)
    civs = world.civilizations
    assert N.horde_conquest(world, civs[THORNWALL], civs[KETHANI])
    assert not N.horde_conquest(world, civs[KETHANI], civs[THORNWALL])
    assert not N.horde_conquest(world, civs[THORNWALL], civs[SELURIAN])


# --- conquest and sedentarization ------------------------------------------------------------------

def test_conquests_by_herders_are_recorded_with_their_cause(monkeypatch):
    _quiet(monkeypatch)
    world = _template()
    annex = Event(turn=world.turn, event_type="annexation", actors=["Selurian Republic", "Kethani Empire"],
                  description="annexed", region="Amber Valley")
    prov.observe_now(world, annex)
    _give(world, AMBER, SELURIAN)
    N.tick_nomads(world)
    conquest = world.nomads.conquests[-1]
    assert (conquest.region, conquest.civ, conquest.from_civ) == (AMBER, SELURIAN, KETHANI)
    assert conquest.event_id == annex.event_id
    assert world.nomads.counters["nomad_conquests"] == 1
    # Land settled peoples take is not a nomad conquest.
    _give(world, VERDANT, KETHANI)
    N.tick_nomads(world)
    assert world.nomads.counters["nomad_conquests"] == 1


def test_conquerors_settle_after_a_generation_and_lose_asabiya(monkeypatch):
    _quiet(monkeypatch)
    world = _template()
    world.regions[DESERT].population = 10
    world.nomads.conquests.append(Conquest(turn=0, region=AMBER, civ=SELURIAN, from_civ=KETHANI,
                                           event_id="0:annexation:0"))
    _give(world, AMBER, SELURIAN)
    _give(world, VERDANT, SELURIAN)
    world.nomads.controllers = N._controllers(world)
    assert N.pastoral_share(world, world.civilizations[SELURIAN]) < N.NOMADIC_FLOOR
    asabiya = world.regions[AMBER].asabiya_state.asabiya
    settled = []
    for _ in range(N.GENERATION):
        settled += _events(N.tick_nomads(world), "sedentarization")
    assert len(settled) == 1 and world.nomads.modes[SELURIAN] == AGRO_PASTORAL
    assert "0:annexation:0" in settled[0].causes
    assert world.nomads.mode_event[SELURIAN] == settled[0].event_id
    assert world.regions[AMBER].asabiya_state.asabiya < asabiya
    # Above the agro-pastoral floor, the herders keep their herds.
    for _ in range(N.GENERATION):
        N.tick_nomads(world)
    assert world.nomads.modes[SELURIAN] == AGRO_PASTORAL


def test_a_people_back_on_the_steppe_resets_the_settling_clock(monkeypatch):
    _quiet(monkeypatch)
    world = _template()
    world.nomads.settle[SELURIAN] = N.GENERATION - 1
    N.tick_nomads(world)                      # all desert: above the floor
    assert world.nomads.settle[SELURIAN] == N.GENERATION - 1 - N.SETTLE_RECOVERY
    assert world.nomads.modes[SELURIAN] == NOMADIC


def test_nomads_move_on_from_empty_pasture(monkeypatch):
    _quiet(monkeypatch)
    world = _template()
    _give(world, SHORE, SELURIAN)              # an outlying coast whose grass is gone
    world.regions[SHORE].population = 3
    world.regions[SHORE].infrastructure = []
    world.regions[SHORE].capacity_modifier = 0.0
    for _ in range(N.LOOSE_TURNS + 1):
        world.nomads.herds[SHORE] = 0.0
        result = N.tick_nomads(world)
        if _events(result, "pasture_abandoned"):
            break
    assert world.regions[SHORE].controller is None
    assert "Obsidian Shore" not in world.civilizations[SELURIAN].regions
    assert world.nomads.counters["pastures_abandoned"] == 1


# --- action weights and expansion ------------------------------------------------------------------

def test_weight_bucket_leans_raiders_to_war_within_its_ceiling(monkeypatch):
    world = _template()
    raider = world.civilizations[SELURIAN]
    for other in ("Kethani Empire", "Thornwall Confederacy", "Ashkari Nomads"):
        world.relationships[raider.name][other].disposition = Disposition.NEUTRAL
    assert N.weight_modifiers(raider, world) == {}
    world.relationships[raider.name]["Kethani Empire"].disposition = Disposition.HOSTILE
    assert N.weight_modifiers(raider, world) == {ActionType.WAR: N.NOMAD_WAR_WEIGHT}
    monkeypatch.setattr(N, "HORDE_WAR_WEIGHT", 9.0)
    world.nomads.hordes.append(N.Horde(horde_id=1, name="h", khan=SELURIAN, khan_leader="x",
                                       founded_turn=0, members=[SELURIAN]))
    assert N.weight_modifiers(raider, world) == {ActionType.WAR: N.WEIGHT_CEILING}
    assert N.weight_modifiers(world.civilizations[KETHANI], world) == {}


def test_herders_expand_into_desert_and_tundra_in_any_era():
    from chronicler.action_engine import HARSH_TERRAINS
    world = _template()
    assert N.harsh_terrains(world, world.civilizations[SELURIAN], HARSH_TERRAINS) == frozenset()
    assert N.harsh_terrains(world, world.civilizations[KETHANI], HARSH_TERRAINS) == HARSH_TERRAINS


# --- switch, persistence and identity ----------------------------------------------------------------

def test_switch_off_is_dormant_and_omitted():
    world = generate_world(seed=42)
    assert world.nomads is None
    assert "nomads" not in json.loads(world.model_dump_json())
    N.set_nomads_enabled(world, True)
    assert "nomads" in json.loads(world.model_dump_json())
    N.set_nomads_enabled(world, False)
    assert world.nomads is None and "nomads" not in json.loads(world.model_dump_json())
    snap = TurnSnapshot(turn=0, civ_stats={}, region_control={}, relationships={})
    assert "nomads" not in json.loads(snap.model_dump_json())


def test_old_save_without_nomads_loads(tmp_path):
    world = generate_world(seed=7, num_regions=24, num_civs=6, worldgen="procedural")
    data = json.loads(world.model_dump_json())
    assert "nomads" not in data
    path = tmp_path / "old.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = WorldState.load(path)
    assert loaded.nomads is None and loaded.model_dump_json() == world.model_dump_json()


def test_feature_off_never_runs_nomad_code(monkeypatch):
    import chronicler.diplomacy as dp

    def boom(*a, **k):
        raise AssertionError("nomad code ran with the switch off")
    for name in ("tick_nomads", "seed_state", "weight_modifiers", "harsh_terrains", "horde_conquest",
                 "snapshot_summary", "capacity", "pastoral_share"):
        monkeypatch.setattr(N, name, boom)
    monkeypatch.setattr(dp, "_nomad_inputs", boom)
    real = N.food_yields
    calls = []

    def identity(world, region, yields, season_id):
        out = real(world, region, yields, season_id)
        assert out is yields
        calls.append(1)
        return out
    monkeypatch.setattr(N, "food_yields", identity)
    world = generate_world(seed=7, num_regions=24, num_civs=6, worldgen="procedural")
    world.campaigns_enabled = True
    dp.set_diplomacy_enabled(world, True)
    _advance(world, 30)
    assert world.nomads is None and calls


def test_state_round_trips_and_the_cache_never_affects_equality():
    world = _advance(_proc(13), 25)
    N._region_index(world)                     # warm the cache
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.nomads == world.nomads
    assert dumped.model_dump_json() == world.model_dump_json()


def test_nomad_runs_are_deterministic():
    a = _advance(_proc(13), 60)
    b = _advance(_proc(13), 60)
    assert a.model_dump_json() == b.model_dump_json()
    assert a.nomads.counters["raids"] + a.nomads.counters["raids_repulsed"] > 0


def _live_save_point(monkeypatch) -> WorldState:
    """Procedural seed 13 with an eager horde: the first turn from 12 on where
    herds graze, a horde rides and a raid has happened."""
    monkeypatch.setattr(N, "HORDE_CHANCE", 1.0)
    monkeypatch.setattr(N, "HORDE_STABILITY", 0)
    world = _advance(_proc(13), 12)
    while not (world.nomads.active_hordes() and sum(world.nomads.herds) > 0 and world.nomads.raids):
        assert world.turn < 80, "no turn with a live horde, herds and raids"
        _advance(world, 1)
    return world


def test_save_load_resume_identity_with_live_herds_and_hordes(tmp_path, monkeypatch):
    first = _live_save_point(monkeypatch)
    save_turn = first.turn
    straight = _advance(_proc(13), save_turn)
    assert straight.model_dump_json() == first.model_dump_json()
    _advance(straight, 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.nomads == first.nomads and resumed.nomads.active_hordes()
    _advance(resumed, 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_enabling_on_a_resumed_world_seeds_from_its_current_land():
    world = _advance(generate_world(seed=42), 10)
    N.set_nomads_enabled(world, True)
    state = world.nomads
    assert len(state.modes) == len(world.civilizations) and len(state.herds) == len(world.regions)
    assert state.controllers == N._controllers(world)
    assert all(t == world.turn for t in state.mode_turn)


def test_cli_flag_gate_forwarding_snapshot_analytics_and_report(tmp_path):
    import argparse
    import importlib.util
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    assert parser.parse_args([]).nomads is None
    assert parser.parse_args(["--nomads"]).nomads is True
    assert parser.parse_args(["--no-nomads"]).nomads is False
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("m53b", root / "scripts" / "m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._nomads_args(argparse.Namespace(nomads=True)) == ["--nomads"]
    assert m53b._nomads_args(argparse.Namespace(nomads=False)) == ["--no-nomads"]
    assert m53b._nomads_args(argparse.Namespace(nomads=None)) == []
    out = tmp_path / "run"
    args = parser.parse_args(["--seed", "13", "--turns", "20", "--regions", "48", "--civs", "10",
                              "--worldgen", "procedural", "--simulate-only", "--nomads",
                              "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    execute_run(args)
    state = json.loads((out / "state.json").read_text())
    assert "nomads" in state
    bundle = json.loads((out / "chronicle_bundle.json").read_text())
    assert all("nomads" in h for h in bundle["history"])
    metrics = N.extract_nomad_metrics([bundle])
    assert metrics["runs"][0]["pastoral_civs_peak"] >= 1
    spec = importlib.util.spec_from_file_location("nomads_report", root / "scripts" / "nomads_report.py")
    rep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rep)
    row = rep.run_metrics(out / "state.json")
    assert row["nomads"] and row["raids"] == int(state["nomads"]["counters"]["raids"])
    assert row["pastoral_civs"] >= 1
    # --no-nomads leaves them out; a flag-off run reports zeros and its polities.
    out2 = tmp_path / "off"
    args = parser.parse_args(["--seed", "13", "--turns", "3", "--regions", "48", "--civs", "10",
                              "--worldgen", "procedural", "--simulate-only", "--no-nomads",
                              "--output", str(out2 / "chronicle.md"), "--state", str(out2 / "state.json")])
    execute_run(args)
    assert "nomads" not in json.loads((out2 / "state.json").read_text())
    row = rep.run_metrics(out2 / "state.json")
    assert not row["nomads"] and row["raids"] == 0 and row["polities_alive"] > 0
    # Analytics reports nomads only for the run that carries them.
    from chronicler.analytics import generate_report
    assert len(generate_report(tmp_path)["nomads"]["runs"]) == 1


def test_new_worlds_default_on_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import _build_parser, execute_run
    assert N.DEFAULT_ENABLED_FOR_NEW_WORLDS is True
    parser = _build_parser()

    def args(out, *extra, turns=3):
        return parser.parse_args(["--seed", "13", "--turns", str(turns), "--regions", "48", "--civs", "10",
                                  "--worldgen", "procedural", "--simulate-only", *extra,
                                  "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    fresh = tmp_path / "fresh"
    execute_run(args(fresh))
    assert "nomads" in json.loads((fresh / "state.json").read_text())
    off = tmp_path / "off"
    execute_run(args(off, "--no-nomads"))
    assert "nomads" not in json.loads((off / "state.json").read_text())
    for run, kept in ((off, False), (fresh, True)):
        resumed = args(run, turns=5)
        resumed.resume = str(run / "state.json")
        resumed.state = str(run / "resumed.json")
        execute_run(resumed)
        assert ("nomads" in json.loads((run / "resumed.json").read_text())) is kept


def test_raid_records_are_pruned_and_counters_kept(monkeypatch):
    _quiet(monkeypatch)
    world = _template()
    world.nomads.raids.append(Raid(turn=0, raider=SELURIAN, target=KETHANI, region=AMBER,
                                   raiders=3, success=True))
    world.turn = N.RAID_MEMORY + 1
    N.tick_nomads(world)
    assert world.nomads.raids == []


def test_hybrid_native_run_with_nomads_is_deterministic(tmp_path):
    pytest.importorskip("chronicler_agents")
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    outs = []
    for side in ("a", "b"):
        out = tmp_path / side
        args = parser.parse_args(["--seed", "13", "--turns", "15", "--regions", "48", "--civs", "10",
                                  "--worldgen", "procedural", "--agents", "hybrid", "--simulate-only",
                                  "--nomads", "--output", str(out / "chronicle.md"),
                                  "--state", str(out / "state.json")])
        execute_run(args)
        outs.append((out / "state.json").read_text())
    assert outs[0] == outs[1] and json.loads(outs[0])["nomads"]["modes"]


def test_abandonment_flag_is_cleared_by_the_turn_and_nothing_transient_is_left(monkeypatch):
    """The only transient a tick sets (the region's controller-changed flag)
    is consumed and reset by the turn, and a tick leaves no state off the
    persisted model."""
    _quiet(monkeypatch)
    monkeypatch.setattr(N, "LOOSE_TURNS", 1)
    monkeypatch.setattr(N, "LOOSE_POP", 1000)   # the turn's growth refills the coast
    world = _template()
    _give(world, SHORE, SELURIAN)
    world.regions[SHORE].population = 3
    world.regions[SHORE].infrastructure = []
    real_capacity = N.capacity
    monkeypatch.setattr(N, "capacity", lambda r: 0.0 if r.name == "Obsidian Shore" else real_capacity(r))
    seen = []
    real = N.tick_nomads

    def watch(w, acc=None, agent_bridge=None):
        out = real(w, acc=acc, agent_bridge=agent_bridge)
        seen.append(any(e.event_type == "pasture_abandoned" for e in out)
                    and w.regions[SHORE]._controller_changed_this_turn)
        return out
    monkeypatch.setattr(N, "tick_nomads", watch)
    _advance(world, 3)
    assert any(seen) and world.regions[SHORE].controller is None
    assert not world.regions[SHORE]._controller_changed_this_turn
    # A tick adds nothing to the world outside the persisted nomad state.
    before = set(vars(world))
    private = dict(world.__pydantic_private__ or {})
    real(world)
    assert set(vars(world)) == before
    assert set(world.__pydantic_private__ or {}) == set(private)
    assert world.nomads._cache == N.NomadState()._cache
