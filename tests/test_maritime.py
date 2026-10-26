"""Maritime layer: fleets, sea-zone control, blockade, naval campaigns,
piracy and colonization by sea (``chronicler.maritime``, ``--maritime``)."""
from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest

from chronicler.bundle_codec import load_bundle
import chronicler.maritime as M
from chronicler.action_engine import ActionEngine
from chronicler.maritime_state import CONTESTED, CONTROLLED, UNCONTESTED, Fleet, MaritimeState
from chronicler.models import Army, Event, TurnSnapshot, WarRecord, WorldState
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world

# Procedural seed 7, 48 regions: sea lane (1, 3) lies in zone 4 (the
# Nepyros Bight, ports 1 2 3 4 11); the two ends are not land neighbours.
LANE_A, LANE_B, ZONE = 1, 3, 4


def _proc(seed: int = 7, regions: int = 48, civs: int = 10) -> WorldState:
    world = generate_world(seed=seed, num_regions=regions, num_civs=civs, worldgen="procedural")
    world.campaigns_enabled = True
    M.set_maritime_enabled(world, True)
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


def _war(world: WorldState, a: int, b: int) -> WarRecord:
    from chronicler.war.peace import war_key
    ca, cb = world.civilizations[a].name, world.civilizations[b].name
    world.active_wars.append((ca, cb))
    war = WarRecord(war_key=war_key(ca, cb), attacker=ca, defender=cb, start_turn=world.turn)
    world.war_state.wars.append(war)
    return war


def _befriend(world: WorldState, a: int, b: int) -> None:
    from chronicler.models import Disposition
    ca, cb = world.civilizations[a].name, world.civilizations[b].name
    world.relationships[ca][cb].disposition = Disposition.FRIENDLY
    world.relationships[cb][ca].disposition = Disposition.FRIENDLY
    world.invalidate_trade_route_cache()


def _fleet(world: WorldState, civ: int, zone: int, ships: int, home: int) -> Fleet:
    state = world.maritime
    fleet = Fleet(fleet_id=state.next_fleet_id, name=f"fleet-{state.next_fleet_id}", civ=civ,
                  zone=zone, home_port=home, ships=ships, built_turn=world.turn,
                  event_id=f"0:fleet_commissioned:{state.next_fleet_id}")
    state.next_fleet_id += 1
    state.fleets.append(fleet)
    return fleet


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def _tick(world: WorldState):
    return M.tick_maritime(world)


# --- sea model -------------------------------------------------------------------------

def test_procedural_sea_model_uses_geography_zones_and_lanes():
    world = _proc()
    state = world.maritime
    geo = world.geography
    assert [z.name for z in state.zones] == [z.name for z in geo.sea_zones]
    index = {r.name: i for i, r in enumerate(world.regions)}
    want = sorted(tuple(sorted((index[a], index[b]))) for a, b in geo.sea_lanes)
    assert sorted((a, b) for a, b, _ in state.lanes) == want
    for a, b, z in state.lanes:
        assert 0 <= z < len(state.zones)
        ports = state.zones[z].ports
        # A lane belongs to a zone both ends border whenever one exists.
        if any(a in zz.ports and b in zz.ports for zz in state.zones):
            assert a in ports and b in ports
    assert len(state.landmass) == len(world.regions)
    assert (LANE_A, LANE_B, ZONE) in state.lanes


def test_template_world_derives_one_zone_from_the_coast_clique():
    world = generate_world(seed=42, num_regions=12, num_civs=4)
    M.set_maritime_enabled(world, True)
    state = world.maritime
    assert state.derived
    coasts = [i for i, r in enumerate(world.regions) if r.terrain == "coast"]
    assert len(state.zones) == 1 and state.zones[0].kind == "coast"
    assert state.zones[0].ports == coasts
    assert state.lanes == [(coasts[0], coasts[1], 0)]
    assert state.zones[0].name == "the Obsidian Sea"


def test_template_world_without_a_clique_has_no_sea():
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    M.set_maritime_enabled(world, True)
    assert world.maritime.zones == [] and world.maritime.lanes == []
    assert _tick(world) == []


def test_navigation_level_is_neutral_with_techniques_off():
    world = _proc()
    assert world.techniques is None
    assert M.navigation_level(world, world.civilizations[0]) == 0


def _knowing(world: WorldState, civ: int, keys: list[str]) -> None:
    """Techniques on, with ``civ`` knowing ``keys`` and every other civ nothing."""
    from chronicler.techniques_state import TECHNIQUE_INDEX, TechniqueState
    known = [[] for _ in world.civilizations]
    known[civ] = sorted(TECHNIQUE_INDEX[k] for k in keys)
    world.techniques = TechniqueState(initialized_turn=0, last_tick_turn=0, known=known)


def test_navigation_level_counts_the_known_navigation_techniques():
    world = _proc()
    _knowing(world, 0, ["sailing", "celestial_navigation", "writing", "bronze_working"])
    knows, other = world.civilizations[0], world.civilizations[1]
    assert M.navigation_level(world, knows) == 2  # writing and bronze are other domains
    assert M.navigation_level(world, other) == 0
    _knowing(world, 0, ["sailing", "celestial_navigation", "compass", "ocean_navigation"])
    assert M.navigation_level(world, knows) == 4


def test_navigation_level_reaches_quality_range_ships_and_storms(monkeypatch):
    world = _proc()
    civ = world.civilizations[0]
    base_quality, base_range = M.fleet_quality(world, civ), M._fleet_range(world, civ)
    _knowing(world, 0, ["sailing", "celestial_navigation"])
    assert M.fleet_quality(world, civ) == pytest.approx(base_quality * (1 + 2 * M.NAVIGATION_QUALITY))
    assert M._fleet_range(world, civ) == base_range + 2
    # Storms: two known navigation techniques scale the chance by 0.7, so a
    # roll at 0.8 of the base chance sinks ships only without them.
    zone = world.maritime.zones[ZONE]
    fleet = _fleet(world, 0, ZONE, 10, zone.ports[0])
    civ.active_focus = None
    chance = M.STORM_CHANCE * M.STORM_KIND.get(zone.kind, 1.0)

    class _Rng:
        def random(self):
            return chance * 0.8

        def uniform(self, a, b):
            return a

    monkeypatch.setattr(M, "_rng", lambda *a, **k: _Rng())
    world.turn = 1  # spring: no winter factor
    M._storms(M._Tick(world, None, None))
    assert fleet.ships == 10
    world.techniques = None
    M._storms(M._Tick(world, None, None))
    assert fleet.ships < 10


# --- switch, dormancy, persistence ------------------------------------------------------------

def test_switch_off_is_dormant_and_omitted():
    world = generate_world(seed=7, num_regions=24, num_civs=6, worldgen="procedural")
    assert world.maritime is None
    assert "maritime" not in json.loads(world.model_dump_json())
    M.set_maritime_enabled(world, True)
    assert "maritime" in json.loads(world.model_dump_json())
    M.set_maritime_enabled(world, False)
    assert world.maritime is None
    assert "maritime" not in json.loads(world.model_dump_json())
    snap = TurnSnapshot(turn=0, civ_stats={}, region_control={}, relationships={})
    assert "maritime" not in json.loads(snap.model_dump_json())


def test_old_save_without_maritime_loads(tmp_path):
    world = generate_world(seed=7, num_regions=24, num_civs=6, worldgen="procedural")
    data = json.loads(world.model_dump_json())
    assert "maritime" not in data
    path = tmp_path / "old.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = WorldState.load(path)
    assert loaded.maritime is None
    assert loaded.model_dump_json() == world.model_dump_json()


def test_feature_off_never_runs_maritime_code(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("maritime code ran with the switch off")
    for name in ("tick_maritime", "observe_phase2", "observe_agent_sea_trade", "expansion_candidates",
                 "overseas_zone", "merchant_route_graph", "filter_boundary_batch", "attach_naval_context",
                 "blocked_name_pairs", "landing_factor", "build_sea_model"):
        monkeypatch.setattr(M, name, boom)
    world = generate_world(seed=7, num_regions=24, num_civs=6, worldgen="procedural")
    world.campaigns_enabled = True
    _advance(world, 30)
    assert world.maritime is None


def test_state_round_trips_and_lookups_never_affect_equality():
    world = _advance(_proc(), 20)
    M._lookups(world.maritime)  # warm the cache
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.maritime == world.maritime
    assert dumped.model_dump_json() == world.model_dump_json()


# --- fleet lifecycle ---------------------------------------------------------------------

def test_war_need_commissions_a_fleet_paid_from_the_treasury():
    world = _proc()
    _give(world, LANE_A, 0)
    _give(world, LANE_B, 1)
    _war(world, 0, 1)
    civ = world.civilizations[0]
    civ.treasury = 500
    events = _tick(world)
    mine = [f for f in world.maritime.fleets if f.civ == 0]
    assert len(mine) == 1
    fleet = mine[0]
    assert fleet.ships >= M.MIN_FLEET_SHIPS and fleet.home_port == LANE_A
    assert fleet.mission == "war"
    spent = 500 - civ.treasury
    assert spent >= fleet.ships * M.SHIP_COST  # plus timber bought in coin (no physical stocks)
    commissioned = [e for e in events if e.event_type == "fleet_commissioned" and civ.name in e.actors]
    assert commissioned and fleet.event_id == commissioned[0].event_id
    assert world.maritime.counters["fleets_commissioned"] >= 1


def test_new_squadron_waits_until_it_can_sail_at_strength():
    world = _proc()
    _give(world, LANE_A, 0)
    _give(world, LANE_B, 1)
    _war(world, 0, 1)
    civ = world.civilizations[0]
    # Budget for exactly one ship: no one-ship fleet is commissioned.
    civ.treasury = M.TREASURY_RESERVE + int((M.SHIP_COST + M.SHIP_TIMBER * M.TIMBER_PRICE + 1) / M.BUILD_SHARE)
    _tick(world)
    assert not [f for f in world.maritime.fleets if f.civ == 0]


def test_upkeep_is_charged_and_unpaid_squadrons_lose_ships():
    world = _proc()
    _give(world, LANE_A, 0)
    civ = world.civilizations[0]
    fleet = _fleet(world, 0, ZONE, 10, LANE_A)
    civ.treasury = 100
    M._upkeep(M._Tick(world, None, None))
    assert civ.treasury == 100 - 5 and fleet.ships == 10
    civ.treasury = 0
    M._upkeep(M._Tick(world, None, None))
    assert fleet.ships == 9
    assert world.maritime.counters["ships_lost_upkeep"] == 1


def test_storms_sink_ships_and_small_fleets(monkeypatch):
    world = _proc()
    _give(world, LANE_A, 0)
    big = _fleet(world, 0, ZONE, 20, LANE_A)
    small = _fleet(world, 0, ZONE, 2, LANE_A)
    monkeypatch.setattr(M, "STORM_CHANCE", 1.0)
    monkeypatch.setitem(M.STORM_KIND, "ocean", 1.0)
    t = M._Tick(world, None, None)
    M._storms(t)
    assert 20 - 20 * M.STORM_LOSS[1] - 1 <= big.ships < 20
    assert small not in world.maritime.fleets
    kinds = [e.event_type for e in t.events]
    assert kinds.count("fleet_storm") == 2
    assert all(e.causes for e in t.events)


def test_naval_battle_losses_retreat_war_score_and_provenance():
    world = _proc()
    _give(world, LANE_A, 0)
    _give(world, LANE_B, 1)
    war = _war(world, 0, 1)
    strong = _fleet(world, 0, ZONE, 20, LANE_A)
    weak = _fleet(world, 1, ZONE, 6, LANE_B)
    t = M._Tick(world, None, None)
    M._naval_battles(t)
    battle = world.maritime.battles[-1]
    assert battle.winner == 0 and battle.attacker_losses < battle.defender_losses
    assert strong.ships == 20 - battle.attacker_losses
    assert war.battle_points > 0 and war.last_combat_turn == world.turn
    ev = [e for e in t.events if e.event_type == "naval_battle"][0]
    assert strong.event_id in ev.causes and weak.event_id in ev.causes
    if weak in world.maritime.fleets:
        assert weak.refit_until == world.turn + M.REFIT_TURNS
    assert any(ne.name.startswith("The Battle of") for ne in world.named_events)


def test_battle_outcomes_are_deterministic():
    def run():
        world = _proc()
        _give(world, LANE_A, 0)
        _give(world, LANE_B, 1)
        _war(world, 0, 1)
        _fleet(world, 0, ZONE, 9, LANE_A)
        _fleet(world, 1, ZONE, 8, LANE_B)
        M._naval_battles(M._Tick(world, None, None))
        return world.maritime.model_dump_json()
    assert run() == run()


# --- zone control --------------------------------------------------------------------------

def _control(world):
    t = M._Tick(world, None, None)
    M._update_control(t)
    return world.maritime.zones[ZONE], t.events


def test_zone_control_states():
    world = _proc()
    _give(world, LANE_A, 0)
    _give(world, LANE_B, 1)
    zone, _ = _control(world)
    assert zone.status == UNCONTESTED and zone.controller is None
    a = _fleet(world, 0, ZONE, 6, LANE_A)
    zone, events = _control(world)
    assert (zone.status, zone.controller) == (CONTROLLED, 0)
    # A peacetime patrol takes command silently; its fleet stands as the cause.
    assert events == [] and zone.status_event_id == a.event_id
    # A neutral fleet does not contest; a hostile one does.
    b = _fleet(world, 1, ZONE, 5, LANE_B)
    zone, _ = _control(world)
    assert (zone.status, zone.controller) == (CONTROLLED, 0)
    _war(world, 0, 1)
    zone, events = _control(world)
    assert zone.status == CONTESTED and zone.controller is None
    assert events[0].event_type == "sea_contested"
    # Twice the hostile strength commands the zone again (news: out of a contest).
    b.ships = 3
    zone, events = _control(world)
    assert (zone.status, zone.controller) == (CONTROLLED, 0)
    assert events[0].event_type == "sea_control" and a.event_id in events[0].causes
    # Fewer than MIN_CONTROL_SHIPS cannot command a zone.
    a.ships, b.ships = 2, 0
    world.maritime.fleets.remove(b)
    zone, _ = _control(world)
    assert zone.status == UNCONTESTED


# --- blockade ------------------------------------------------------------------------------

def _blockade_world():
    """Civ 0 commands zone 4 at war with civ 1, which holds port 3; civ 2
    holds the other end of lane (1, 3) and trades with civ 1."""
    world = _proc()
    _give(world, LANE_B, 1)
    _give(world, LANE_A, 2)
    _give(world, 2, 0)  # another port of zone 4 for the blockader
    _befriend(world, 1, 2)
    _war(world, 0, 1)
    _fleet(world, 0, ZONE, 8, 2)
    t = M._Tick(world, None, None)
    M._update_control(t)
    M._update_blockades(t)
    return world, t


def test_blockade_closes_the_enemys_lanes_with_provenance():
    world, t = _blockade_world()
    state = world.maritime
    active = state.active_blockades()
    assert [(b.zone, b.blockader, b.target) for b in active] == [(ZONE, 0, 1)]
    assert (LANE_A, LANE_B) in state.blocked
    assert all(LANE_B in lane for lane in state.blocked)
    ev = [e for e in t.events if e.event_type == "blockade"][0]
    assert state.zones[ZONE].status_event_id in ev.causes
    # Lifted when the war ends.
    world.active_wars.clear()
    t2 = M._Tick(world, None, None)
    M._update_control(t2)
    M._update_blockades(t2)
    assert not state.active_blockades() and state.blocked == []
    lifted = [e for e in t2.events if e.event_type == "blockade_lifted"]
    assert lifted and lifted[0].causes == [ev.event_id]


def test_blockade_cuts_trade_routes_ledger_flows_and_goods_batches():
    from chronicler.contact_ledger import off_mode_trade_rows
    from chronicler.resources import get_active_trade_routes
    world, _ = _blockade_world()
    c1, c2 = world.civilizations[1].name, world.civilizations[2].name
    pair = tuple(sorted((c1, c2)))
    # Civ 1 and civ 2 touch only across the blockaded lane.
    assert pair not in get_active_trade_routes(world)
    saved = list(world.maritime.blocked)
    world.maritime.blocked = []
    world.invalidate_trade_route_cache()
    assert pair in get_active_trade_routes(world)
    rows = off_mode_trade_rows(world, get_active_trade_routes(world))
    assert (LANE_A, LANE_B) in {(a, b) for a, b, _ in rows}
    world.maritime.blocked = saved
    adjust = M.ledger_trade_adjuster(world)
    assert adjust(LANE_A, LANE_B, 1.0) == 0.0 and adjust(LANE_B, LANE_A, 1.0) == 0.0
    batch = pa.record_batch({"origin_region_id": pa.array([LANE_A, 0], type=pa.uint16()),
                             "dest_region_id": pa.array([LANE_B, 5], type=pa.uint16())})
    kept = M.filter_boundary_batch(world, batch, "origin_region_id", "dest_region_id")
    assert kept.column("origin_region_id").to_pylist() == [0]


def test_merchant_graph_drops_blocked_lanes_and_carries_raid_risk():
    world, _ = _blockade_world()
    world.maritime.zones[0].pirates = 1.0
    lane0 = next((a, b) for a, b, z in world.maritime.lanes if z == 0)
    batch = pa.record_batch({
        "from_region": pa.array([LANE_A, lane0[0], 0], type=pa.uint16()),
        "to_region": pa.array([LANE_B, lane0[1], 5], type=pa.uint16()),
        "is_river": pa.array([False] * 3),
        "transport_cost": pa.array([1.0] * 3, type=pa.float32()),
    })
    out = M.merchant_route_graph(world, batch)
    assert out.column("from_region").to_pylist() == [lane0[0], 0]
    risk = out.column("sea_raid_risk").to_pylist()
    assert risk[0] == pytest.approx(M.PIRACY_MAX_SKIM)
    assert risk[1] == -1.0


def test_enemy_command_cuts_sea_supply():
    from chronicler.war.common import build_context
    world, _ = _blockade_world()
    ctx = build_context(world)
    c1 = world.civilizations[1].name
    supply = ctx.naval.supply_graph(c1)
    assert LANE_A not in supply[LANE_B] and LANE_A in ctx.graph[LANE_B]
    # The blockader's own supply still runs through its zone.
    assert LANE_A in ctx.naval.supply_graph(world.civilizations[0].name)[LANE_B]


# --- naval campaigns ------------------------------------------------------------------------

def _crossing_world(fleet_ships: int | None, *, control: bool = False):
    """Civ 0's army at port 1 marches on civ 1's region 3 across lane (1, 3)."""
    from chronicler.war.common import build_context
    world = _proc()
    _give(world, LANE_A, 0)
    _give(world, LANE_B, 1)
    war = _war(world, 0, 1)
    army = Army(army_id="army-1", name="The First Host", civ=world.civilizations[0].name,
                war_key=war.war_key, region=world.regions[LANE_A].name,
                home_region=world.regions[LANE_A].name, objective=world.regions[LANE_B].name,
                phase="marching", soldiers=30, raised=30, morale=700, rations=100)
    world.war_state.armies.append(army)
    if fleet_ships:
        _fleet(world, 0, ZONE, fleet_ships, LANE_A)
    if control:
        world.maritime.zones[ZONE].status = CONTROLLED
        world.maritime.zones[ZONE].controller = 0
    return world, build_context(world), army


def _march(world, army, turns: int = 2):
    """Run ``move_armies`` for ``turns`` ticks (region 3 is tundra: two
    turns of marching); returns the last tick's context."""
    from chronicler.war.common import build_context
    from chronicler.war.logistics import move_armies
    ctx = None
    for _ in range(turns):
        ctx = build_context(world)
        move_armies(ctx, [army])
    return ctx


def test_army_waits_on_the_shore_without_escort_and_requests_one():
    from chronicler.war.logistics import move_armies
    world, ctx, army = _crossing_world(None)
    move_armies(ctx, [army])
    assert army.region == world.regions[LANE_A].name
    reqs = world.maritime.escort_requests
    assert [(r.civ, r.zone, r.ships) for r in reqs] == [(0, ZONE, 2)]


def test_escorted_crossing_lands_through_the_battle_code():
    from chronicler.war.runtime import _sieges_and_liberation
    world, _, army = _crossing_world(2)
    ctx = _march(world, army)
    assert army.region == world.regions[LANE_B].name
    state = world.maritime
    assert state.landings == {"army-1": world.turn}
    assert state.counters["overseas_campaigns"] == 1 and state.counters["landings"] == 1
    landing = [e for e in ctx.events if e.event_type == "amphibious_landing"]
    assert landing and landing[0].causes[0] == state.fleets[0].event_id
    assert M.landing_factor(world, army) == M.LANDING_POWER
    # The landed army fights the garrison through the ordinary campaign code,
    # and that fight cites the landing.
    before = len(world.war_state.battles)
    _sieges_and_liberation(ctx)
    assert len(world.war_state.battles) == before + 1
    fight = [e for e in ctx.events if e.event_type == "war"][-1]
    assert landing[0].event_id in fight.causes


def test_escort_capacity_is_limited_per_turn():
    world, _, army = _crossing_world(1)  # one ship lifts 20 soldiers; the army has 30
    _march(world, army)
    assert army.region == world.regions[LANE_A].name
    assert world.maritime.escort_requests


def test_own_command_of_the_zone_allows_crossing_and_enemy_command_forbids_it():
    world, _, army = _crossing_world(None, control=True)
    _march(world, army)
    assert army.region == world.regions[LANE_B].name
    world2, ctx2, army2 = _crossing_world(5)
    world2.maritime.zones[ZONE].status = CONTROLLED
    world2.maritime.zones[ZONE].controller = 1
    from chronicler.war.common import build_context
    ctx2 = build_context(world2)
    allowed, _ = ctx2.naval.crossing(army2, LANE_A, LANE_B)
    assert not allowed


def test_landing_penalty_lasts_one_turn():
    world, ctx, army = _crossing_world(2)
    world.maritime.landings[army.army_id] = world.turn
    assert M.landing_factor(world, army) == M.LANDING_POWER
    world.turn += 1
    assert M.landing_factor(world, army) == 1.0
    _tick(world)
    assert army.army_id not in world.maritime.landings


def test_objectives_ignore_lanes_the_civ_cannot_cross():
    from chronicler.war.common import build_context
    world, ctx, army = _crossing_world(None)
    c0 = world.civilizations[0].name
    # Civ 0 has a port in the zone, so it can plan across it.
    assert world.regions[LANE_B].name in ctx.naval.distances(c0, world.regions[LANE_A].name)
    # Enemy command of the zone removes the lane from planning.
    world.maritime.zones[ZONE].status = CONTROLLED
    world.maritime.zones[ZONE].controller = 1
    ctx = build_context(world)
    assert LANE_B not in ctx.naval.planning_graph(c0)[LANE_A]


# --- piracy --------------------------------------------------------------------------------------

def _trading_world():
    world = _proc()
    _give(world, LANE_A, 0)
    _give(world, LANE_B, 1)
    _befriend(world, 0, 1)
    return world


def test_pirates_skim_sea_trade_and_cost_treasury():
    from chronicler.resources import get_active_trade_routes
    world = _trading_world()
    state = world.maritime
    state.zones[ZONE].pirates = 1.0
    routes = get_active_trade_routes(world)
    M.observe_phase2(world, routes)
    assert state.pending_sea_trade[ZONE] > 0
    assert state.pending_piracy[ZONE] == pytest.approx(state.pending_sea_trade[ZONE] * M.PIRACY_MAX_SKIM, rel=1e-4)
    victims = sorted(state.pending_piracy_civ)
    assert victims == [0, 1]
    # Losses are charged to the cargo owners' treasuries (whole coins plus a
    # deterministic chance of one more for the fraction).
    state.pending_piracy_civ = {0: 3.0, 1: 0.0}
    before = [c.treasury for c in world.civilizations[:2]]
    t = M._Tick(world, None, None)
    traffic = M._consume_measurements(t)
    assert traffic[ZONE] > 0
    assert world.civilizations[0].treasury == before[0] - int(3.0 * M.PIRACY_TREASURY_PER_UNIT)
    assert world.civilizations[1].treasury == before[1]
    # Consumed once: the pending measurement is reset (multi-turn reset check).
    assert state.pending_sea_trade[ZONE] == 0 and state.pending_piracy_civ == {}
    traffic2 = M._consume_measurements(M._Tick(world, None, None))
    assert traffic2[ZONE] == 0
    assert state.counters["piracy_losses"] > 0 and state.counters["sea_trade"] > 0


def test_piracy_reports_fold_into_a_chronic_episode():
    from chronicler import provenance
    world = _trading_world()
    state = world.maritime
    state.zones[ZONE].pirates = 1.0
    state.zones[ZONE].status_event_id = "0:sea_contested:0"
    state.pending_piracy[ZONE] = 2.0
    events = M._consume_measurements(M._Tick(world, None, None)) and None
    t = M._Tick(world, None, None)
    state.pending_piracy[ZONE] = 2.0
    M._consume_measurements(t)
    ev = [e for e in t.events if e.event_type == "piracy"][0]
    assert ev.region == world.regions[state.zones[ZONE].ports[0]].name
    assert ev.causes == ["0:sea_contested:0"]
    assert "piracy" in provenance.CHRONIC
    del events


def test_patrol_commission_cites_the_raid_it_answers():
    from chronicler import provenance
    world = _trading_world()
    state = world.maritime
    zone = state.zones[ZONE]
    zone.pirates = 0.5
    state.last_sea_trade[ZONE] = 2.0
    anchor = world.regions[zone.ports[0]].name
    raid = Event(turn=world.turn, event_type="piracy", actors=[], description="raid", region=anchor)
    provenance.observe(world, [raid])
    civ = world.civilizations[0]
    civ.treasury = 500
    t = M._Tick(world, None, None)
    needs = {0: M._naval_needs(t, 0)}
    assert needs[0][ZONE] == (M.PATROL_SHIPS, "patrol")
    M._build_ships(t, needs)
    commissioned = [e for e in t.events if e.event_type == "fleet_commissioned"]
    assert commissioned and commissioned[0].causes == [raid.event_id]


def test_controlled_zone_has_no_piracy_and_suppresses_pirates():
    world = _trading_world()
    zone = world.maritime.zones[ZONE]
    zone.pirates = 0.8
    zone.status, zone.controller = CONTROLLED, 0
    assert M.skim_rate(world, ZONE) == 0.0
    M._update_pirates(M._Tick(world, None, None), [10.0] * len(world.maritime.zones))
    assert zone.pirates == pytest.approx(0.8 * (1 - M.PIRATE_SUPPRESSION))
    zone.status, zone.controller = UNCONTESTED, None
    p = zone.pirates
    M._update_pirates(M._Tick(world, None, None), [10.0] * len(world.maritime.zones))
    assert zone.pirates > p
    p = zone.pirates
    M._update_pirates(M._Tick(world, None, None), [0.0] * len(world.maritime.zones))
    assert zone.pirates < p


def test_ledger_proxy_is_skimmed_by_pirates():
    world = _trading_world()
    world.maritime.zones[ZONE].pirates = 1.0
    adjust = M.ledger_trade_adjuster(world)
    assert adjust(LANE_A, LANE_B, 2.0) == pytest.approx(2.0 * (1 - M.PIRACY_MAX_SKIM))
    assert adjust(0, 5, 2.0) == 2.0  # land edges untouched


class _StubSim:
    def __init__(self, rows):
        self.rows = rows

    def get_sea_trade_log(self):
        cols = list(zip(*self.rows)) if self.rows else [[]] * 7
        return pa.record_batch({
            "from_region": pa.array(cols[0], type=pa.uint16()),
            "to_region": pa.array(cols[1], type=pa.uint16()),
            "origin_region": pa.array(cols[2], type=pa.uint16()),
            "dest_region": pa.array(cols[3], type=pa.uint16()),
            "good_slot": pa.array(cols[4], type=pa.uint8()),
            "qty": pa.array(cols[5], type=pa.float32()),
            "raided": pa.array(cols[6], type=pa.bool_()),
        })


class _StubBridge:
    def __init__(self, rows):
        self._sim = _StubSim(rows)


def test_native_sea_log_feeds_sea_trade_and_raids():
    world = _trading_world()
    rows = [(LANE_A, LANE_B, LANE_A, LANE_B, 0, 1.0, False),
            (LANE_B, LANE_A, LANE_B, LANE_A, 1, 0.5, True),
            (0, 5, 0, 5, 0, 1.0, False)]  # a land hop is ignored
    M.observe_agent_sea_trade(world, _StubBridge(rows))
    state = world.maritime
    assert state.pending_sea_trade[ZONE] == pytest.approx(1.5)
    assert state.pending_piracy[ZONE] == pytest.approx(0.5)
    assert state.pending_piracy_civ == {1: pytest.approx(0.5)}
    M.observe_agent_sea_trade(world, _StubBridge([]))
    assert state.pending_sea_trade[ZONE] == pytest.approx(1.5)


def test_native_extension_accepts_the_sea_column_and_logs_nothing_without_it():
    agents = pytest.importorskip("chronicler_agents")
    sim = agents.AgentSimulator(num_regions=4, seed=1)
    assert sim.get_sea_trade_log().num_rows == 0
    batch = pa.record_batch({
        "from_region": pa.array([0, 1], type=pa.uint16()),
        "to_region": pa.array([1, 0], type=pa.uint16()),
        "is_river": pa.array([False, False]),
        "transport_cost": pa.array([1.0, 1.0], type=pa.float32()),
        "sea_raid_risk": pa.array([0.1, 0.1], type=pa.float32()),
    })
    sim.set_merchant_route_graph(batch)
    assert sim.get_sea_trade_log().schema.names == [
        "from_region", "to_region", "origin_region", "dest_region", "good_slot", "qty", "raided"]


# --- colonization ------------------------------------------------------------------------------

def _colony_world():
    """Civ 0 holds port 1; port 3 is unclaimed and walled off by civ 1's land."""
    world = _proc()
    _give(world, LANE_A, 0)
    land = M._land_graph(world)
    for nb in land[LANE_B]:
        if world.regions[nb].controller is None:
            _give(world, nb, 1)
    for nb in land[LANE_A]:
        if world.regions[nb].controller is None:
            _give(world, nb, 1)
    assert LANE_B not in M.land_reachable(world, world.civilizations[0].name)
    return world


def test_overseas_coast_needs_a_fleet_in_its_zone():
    world = _colony_world()
    civ = world.civilizations[0]
    unclaimed = [r for r in world.regions if r.controller is None]
    names = {r.name for r in M.expansion_candidates(world, civ, unclaimed)}
    assert world.regions[LANE_B].name not in names
    _fleet(world, 0, ZONE, 3, LANE_A)
    names = {r.name for r in M.expansion_candidates(world, civ, unclaimed)}
    assert world.regions[LANE_B].name in names
    # Only coasts are gated: inland targets keep the base EXPAND reach.
    ports = {i for z in world.maritime.zones for i in z.ports}
    inland = {r.name for i, r in enumerate(world.regions) if r.controller is None and i not in ports}
    assert inland <= names
    world.maritime.fleets.clear()
    names = {r.name for r in M.expansion_candidates(world, civ, unclaimed)}
    walkable = M.land_reachable(world, civ.name)
    assert names == {r.name for i, r in enumerate(world.regions)
                     if r.controller is None and (i not in ports or i in walkable)}


def test_settlers_follow_a_colony_fleet():
    world = _colony_world()
    civ = world.civilizations[0]
    unclaimed = [r for r in world.regions if r.controller is None]
    fleet = _fleet(world, 0, ZONE, 3, LANE_A)
    assert len(M.expansion_candidates(world, civ, unclaimed)) > 1
    fleet.mission = "colony"
    targets = M.expansion_candidates(world, civ, unclaimed)
    walkable = M.land_reachable(world, civ.name)
    assert world.regions[LANE_B] in targets
    assert all(world.regions.index(r) in world.maritime.zones[ZONE].ports
               and world.regions.index(r) not in walkable for r in targets)


def test_sealess_world_keeps_the_base_expand_reach():
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    M.set_maritime_enabled(world, True)
    civ = world.civilizations[0]
    unclaimed = [r for r in world.regions if r.controller is None]
    assert M.expansion_candidates(world, civ, unclaimed) == unclaimed


def test_expand_by_sea_records_a_colony_citing_the_fleet(monkeypatch):
    from chronicler import action_engine
    from chronicler.models import TechEra
    world = _colony_world()
    civ = world.civilizations[0]
    civ.military = 80
    civ.tech_era = TechEra.IRON  # the target coast is tundra
    fleet = _fleet(world, 0, ZONE, 3, LANE_A)
    target = world.regions[LANE_B]
    monkeypatch.setattr(M, "expansion_candidates", lambda w, c, u: [target])
    ev = action_engine._resolve_expand(civ, world)
    assert target.controller == civ.name
    state = world.maritime
    assert [(c.region, c.civ, c.zone) for c in state.colonies] == [(LANE_B, 0, ZONE)]
    assert fleet.event_id in ev.causes and state.colonies[0].event_id == ev.event_id
    assert "across" in ev.description and state.counters["colonies"] == 1


def test_expand_over_land_is_not_a_colony():
    from chronicler import action_engine
    world = _proc()
    _give(world, LANE_A, 0)
    civ = world.civilizations[0]
    civ.military = 80
    ev = action_engine._resolve_expand(civ, world)
    assert ev.event_type == "expand"
    assert world.maritime.colonies == []


def test_colony_need_builds_a_colony_fleet():
    world = _colony_world()
    civ = world.civilizations[0]
    civ.military = 80
    civ.treasury = 500
    # No walkable land left for civ 0.
    for i in M.land_reachable(world, civ.name):
        _give(world, i, 1)
    needs = M._naval_needs(M._Tick(world, None, None), 0)
    assert needs.get(ZONE, (0, ""))[1] == "colony"


# --- runs ---------------------------------------------------------------------------------------

def test_maritime_runs_build_fleets_and_are_deterministic():
    a = _advance(_proc(seed=7, regions=48, civs=10), 60)
    b = _advance(_proc(seed=7, regions=48, civs=10), 60)
    assert a.model_dump_json() == b.model_dump_json()
    assert a.maritime.counters["fleets_commissioned"] > 0
    assert a.maritime.counters["ships_built"] > 0


def test_save_load_resume_identity_with_fleets_at_sea(tmp_path):
    straight = _advance(_proc(seed=7, regions=48, civs=10), 45)
    first = _advance(_proc(seed=7, regions=48, civs=10), 30)
    assert first.maritime.fleets, "the save point must carry fleets at sea"
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.maritime.fleets == first.maritime.fleets
    _advance(resumed, 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_escort_requests_and_pending_trade_are_consumed_each_tick():
    world = _advance(_proc(), 5)
    state = world.maritime
    state.escort_requests.append(M.EscortRequest(civ=0, zone=ZONE, ships=2))
    state.pending_sea_trade[ZONE] = 3.0
    _tick(world)
    assert state.escort_requests == []
    assert state.pending_sea_trade[ZONE] == 0.0 and state.last_sea_trade[ZONE] == 3.0
    _tick(world)
    assert state.last_sea_trade[ZONE] == 0.0


def test_cli_flag_gate_forwarding_and_snapshot(tmp_path):
    import importlib.util
    import argparse
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    assert parser.parse_args([]).maritime is None
    assert parser.parse_args(["--maritime"]).maritime is True
    spec = importlib.util.spec_from_file_location(
        "m53b", Path(__file__).resolve().parents[1] / "scripts" / "m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._maritime_args(argparse.Namespace(maritime=True)) == ["--maritime"]
    assert m53b._maritime_args(argparse.Namespace(maritime=False)) == ["--no-maritime"]
    assert m53b._maritime_args(argparse.Namespace(maritime=None)) == []
    out = tmp_path / "run"
    args = parser.parse_args(["--seed", "7", "--turns", "12", "--regions", "24", "--civs", "6",
                              "--worldgen", "procedural", "--simulate-only", "--maritime",
                              "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    execute_run(args)
    state = json.loads((out / "state.json").read_text())
    assert "maritime" in state
    bundle = load_bundle(out / "chronicle_bundle.json")
    assert all("maritime" in h for h in bundle["history"])
    assert M.extract_maritime_metrics([bundle])["runs"][0]["zones"] == len(state["maritime"]["zones"])
    spec = importlib.util.spec_from_file_location(
        "maritime_report", Path(__file__).resolve().parents[1] / "scripts" / "maritime_report.py")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    row = report.run_metrics(out / "state.json")
    assert row["maritime"] and row["zones"] == len(state["maritime"]["zones"])
    assert row["fleets"] == int(state["maritime"]["counters"]["fleets_commissioned"])
    # --no-maritime leaves the layer out.
    out2 = tmp_path / "off"
    args = parser.parse_args(["--seed", "7", "--turns", "3", "--regions", "24", "--civs", "6",
                              "--worldgen", "procedural", "--simulate-only", "--no-maritime",
                              "--output", str(out2 / "chronicle.md"), "--state", str(out2 / "state.json")])
    execute_run(args)
    assert "maritime" not in json.loads((out2 / "state.json").read_text())
    # A flag-off run is measured with a sea model derived from its saved world.
    row = report.run_metrics(out2 / "state.json")
    assert not row["maritime"] and row["zones"] == len(state["maritime"]["zones"]) and row["fleets"] == 0


def test_new_worlds_default_on_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import _build_parser, execute_run
    assert M.DEFAULT_ENABLED_FOR_NEW_WORLDS is True
    parser = _build_parser()

    def args(out, *extra, turns=3):
        return parser.parse_args(["--seed", "7", "--turns", str(turns), "--regions", "24", "--civs", "6",
                                  "--worldgen", "procedural", "--simulate-only", *extra,
                                  "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    fresh = tmp_path / "fresh"
    execute_run(args(fresh))
    assert "maritime" in json.loads((fresh / "state.json").read_text())
    off = tmp_path / "off"
    execute_run(args(off, "--no-maritime"))
    assert "maritime" not in json.loads((off / "state.json").read_text())
    for run, kept in ((off, False), (fresh, True)):
        resumed = args(run, turns=5)
        resumed.resume = str(run / "state.json")
        resumed.state = str(run / "resumed.json")
        execute_run(resumed)
        assert ("maritime" in json.loads((run / "resumed.json").read_text())) is kept


def test_naval_battles_and_blockades_feed_diplomatic_memory():
    import chronicler.diplomacy as dp
    from chronicler.diplomacy_state import EMBARGO, WAR
    world, _ = _blockade_world()
    dp.set_diplomacy_enabled(world, True)
    _fleet(world, 1, ZONE, 3, LANE_B)
    M._naval_battles(M._Tick(world, None, None))
    assert world.maritime.battles and world.maritime.active_blockades()
    dp._naval_inputs(world)
    c0, c1 = world.civilizations[0].name, world.civilizations[1].name
    loser_memory = world.relationships[c1][c0].memory
    assert loser_memory.grievance[WAR] > dp.GRIEVANCE_BATTLE_LOST
    assert loser_memory.grievance[EMBARGO] == dp.GRIEVANCE_EMBARGO_TURN


def test_hybrid_merchants_cross_sea_lanes_and_are_raided_deterministically(tmp_path, monkeypatch):
    """Real native merchants: the sea column reaches Rust, crossings are
    logged, pirates seize cargo, and the run repeats exactly."""
    pytest.importorskip("chronicler_agents")
    from chronicler.main import _build_parser, execute_run
    # Every sea starts infested so raids happen within a short run.
    for kind in ("ocean", "sea", "coast"):
        monkeypatch.setitem(M.PIRATE_START, kind, 1.0)
    states = []
    # Seed 8, 40 turns: about 110 crossings and 9 cargo lost to pirates with
    # the needs calibration (seed 7 then crosses 3 times and loses none).
    # Sea trade changes with each correction of the agent tick and the food
    # economy.
    for label in ("a", "b"):
        out = tmp_path / label
        args = _build_parser().parse_args([
            "--seed", "8", "--turns", "40", "--regions", "48", "--civs", "10",
            "--worldgen", "procedural", "--agents", "hybrid", "--simulate-only", "--maritime",
            "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
        execute_run(args)
        states.append((out / "state.json").read_text())
    assert states[0] == states[1]
    counters = json.loads(states[0])["maritime"]["counters"]
    assert counters["crossings"] > 0 and counters["sea_trade"] > 0
    assert counters["piracy_losses"] > 0
