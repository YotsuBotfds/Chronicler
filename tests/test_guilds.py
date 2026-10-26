"""Guilds and burghers (``chronicler.guilds``, ``--guilds``).

Mechanics run on the template world (seed 42) with cities placed as the
cities layer records them and Phase 10 agent rows built as the native
snapshot carries them; ticks are called directly with ``acc=None``. Native
tests run the real extension.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pytest

import chronicler.agent_movements as M
import chronicler.cities as C
import chronicler.guilds as G
from chronicler.action_engine import ActionEngine
from chronicler.agent_movements_state import (
    ENDED, GATHERING, GUILD, GUILD_CHARTER, IN_FORCE, LAPSED, PRESSING, RULER, Movement,
)
from chronicler.cities_state import FREE_CITY, MARKET_RIGHTS, NO_CHARTER, SELF_GOVERNMENT, City
from chronicler.factions import (
    FACTION_WEIGHTS, generate_faction_candidates, get_faction_weight_modifier, normalize_influence,
    _event_is_win,
)
from chronicler.guilds_state import CRAFT, MERCHANT, Guild
from chronicler.models import (
    CLASSIC_FACTIONS, ActionType, Event, FactionType, TurnSnapshot, WorldState,
)
from chronicler.simulation import run_turn
from chronicler.turn_artifacts import AgentRows, Phase10Inputs, Stamp
from chronicler.world_gen import generate_world

ROOT = Path(__file__).resolve().parents[1]
# Template seed 42: Thornwall Confederacy (civ 2) holds Verdant Plains (2,
# capital) and Thornwood (4); Kethani Empire (1) holds Amber Valley (5,
# capital) and Frostholm Tundra (0).
FROST, VERDANT, THORNWOOD, AMBER = 0, 2, 4, 5
KETHANI, THORNWALL = 1, 2


def _world(movements: bool = True) -> WorldState:
    world = generate_world(seed=42)
    C.set_cities_enabled(world, True)
    if movements:
        M.set_agent_movements_enabled(world, True)
    G.set_guilds_enabled(world, True)
    world.turn = 30
    return world


def _city(world, region=THORNWOOD, sid=1, *, rank=2, size=30.0, charter=NO_CHARTER, crafts=0.0,
          mix=(0.45, 0.10, 0.25, 0.10, 0.10), satisfaction=0.5) -> City:
    ctrl = world.regions[region].controller
    lord = world.civ_index_map[ctrl] if ctrl else -1
    city = City(settlement_id=sid, region=region, name=f"{world.regions[region].name} Settlement 1",
                founded_turn=world.turn - 5, founder=lord, lord=lord, rank=rank, residents=int(size),
                size=size, mix=list(mix), charter=charter, crafts=crafts, satisfaction=satisfaction)
    world.cities.cities.append(city)
    return city


def _settle(world, region_idx: int, population: int):
    """An M56a settlement record (as tests/test_cities.py places them)."""
    from chronicler.models import Settlement, SettlementStatus
    region = world.regions[region_idx]
    s = Settlement(
        settlement_id=world.next_settlement_id, name=f"{region.name} Settlement 1",
        region_name=region.name, founding_turn=world.turn, last_seen_turn=world.turn,
        population_estimate=population, peak_population=population, centroid_x=0.55,
        centroid_y=0.55, footprint_cells=[(5, 5)], status=SettlementStatus.ACTIVE, inertia=1,
    )
    world.next_settlement_id += 1
    region.settlements.append(s)
    return s


def _rows(world, members=None, adults: int = 30, sid_region: int | None = None, sid: int = 1):
    """Phase 10 rows: ``adults`` per held region (in ``sid_region`` they live in
    settlement ``sid``); ``members[(movement index, region)]`` belong to it."""
    members = members or {}
    cols = {k: [] for k in ("id", "region", "age", "movement_id", "boldness", "belief",
                            "civ_affinity", "occupation", "settlement_id", "satisfaction")}
    next_id = 1
    for ri, region in enumerate(world.regions):
        if region.controller is None:
            continue
        tags = [i + 1 for (i, r), n in sorted(members.items()) if r == ri for _ in range(n)]
        civ = world.civ_index_map[region.controller]
        for k in range(adults):
            cols["id"].append(next_id)
            cols["region"].append(ri)
            cols["age"].append(30)
            cols["movement_id"].append(tags[k] if k < len(tags) else 0)
            cols["boldness"].append(0.9 - 0.01 * k)
            cols["belief"].append(world.civilizations[civ].civ_majority_faith)
            cols["civ_affinity"].append(civ)
            cols["occupation"].append(2 if k % 3 == 0 else 0)
            cols["settlement_id"].append(sid if ri == sid_region else 0)
            cols["satisfaction"].append(0.5)
            next_id += 1
    types = {"id": pa.uint32(), "region": pa.uint16(), "age": pa.uint16(), "movement_id": pa.uint16(),
             "boldness": pa.float32(), "belief": pa.uint8(), "civ_affinity": pa.uint8(),
             "occupation": pa.uint8(), "settlement_id": pa.uint16(), "satisfaction": pa.float32()}
    batch = pa.record_batch({k: pa.array(v, type=types[k]) for k, v in cols.items()})
    return Phase10Inputs(source_turn=world.turn,
                         agents=AgentRows(stamp=Stamp(world.turn, "phase10_entry"), batch=batch),
                         named_agents=None, economy=None, deaths=())


def _tick(world, phase10=None):
    events = G.tick_guilds(world, [], acc=None, phase10=phase10)
    world.events_timeline.extend(events)
    return events


def _types(events) -> list[str]:
    return [e.event_type for e in events]


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


# --- switch and persistence ------------------------------------------------------

def test_off_worlds_omit_the_dormant_fields():
    world = generate_world(seed=42)
    assert world.guilds is None and not G.guilds_enabled(world)
    assert "guilds" not in json.loads(world.model_dump_json())
    assert "guilds" not in json.loads(TurnSnapshot(turn=1, civ_stats={}, region_control={},
                                                   relationships={}).model_dump_json())
    assert G.tick_guilds(world, []) == []
    assert G.movement_news_columns(world) is None
    assert G.guild_index(world) is None
    assert all(FactionType.BURGHER not in c.factions.influence for c in world.civilizations)


def test_enable_disable_round_trip_and_old_saves(tmp_path):
    world = _world()
    _city(world, charter=MARKET_RIGHTS, crafts=0.2)
    _tick(world)
    assert world.guilds.guilds
    thornwall = world.civilizations[THORNWALL]
    assert FactionType.BURGHER in thornwall.factions.influence
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert loaded.guilds == world.guilds
    assert loaded.civilizations[THORNWALL].factions.influence == thornwall.factions.influence
    G.set_guilds_enabled(world, True)   # idempotent
    assert world.guilds.guilds
    G.set_guilds_enabled(world, False)
    assert world.guilds is None
    assert FactionType.BURGHER not in thornwall.factions.influence
    assert sum(thornwall.factions.influence.values()) == pytest.approx(1.0)
    old = generate_world(seed=7)
    path = tmp_path / "state.json"
    old.save(path)
    assert "guilds" not in json.loads(path.read_text())
    assert WorldState.load(path).guilds is None


def test_cli_flag_gate_forwarding_and_live_default():
    from chronicler.main import _build_parser
    parser = _build_parser()
    assert parser.parse_args([]).guilds is None
    assert parser.parse_args(["--guilds"]).guilds is True
    assert parser.parse_args(["--no-guilds"]).guilds is False
    spec = importlib.util.spec_from_file_location("m53b", ROOT / "scripts" / "m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._guilds_args(argparse.Namespace(guilds=True)) == ["--guilds"]
    assert m53b._guilds_args(argparse.Namespace(guilds=False)) == ["--no-guilds"]
    assert m53b._guilds_args(argparse.Namespace(guilds=None)) == []
    assert "set_guilds_enabled" in (ROOT / "src" / "chronicler" / "live.py").read_text()


def test_feature_off_never_runs_guild_code(monkeypatch):
    import chronicler.contact_ledger as cl

    def boom(*a, **k):
        raise AssertionError("guild code ran with the switch off")

    for name in ("tick_guilds", "snapshot_summary", "craft_access", "dues_share", "take",
                 "wall_help", "shift_urban", "urban_influence", "burgher_weights",
                 "movement_appeal", "on_guild_rising", "news_founding_factor"):
        monkeypatch.setattr(G, name, boom)
    monkeypatch.setattr(M, "found_guild_movement", boom)
    world = generate_world(seed=42)
    world.campaigns_enabled = True
    C.set_cities_enabled(world, True)
    M.set_agent_movements_enabled(world, True)
    cl.set_contact_ledger_enabled(world, True)
    _advance(world, 20)
    assert world.guilds is None
    assert "settlement" not in M.movement_table(world).schema.names


def test_new_worlds_default_on_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    assert G.DEFAULT_ENABLED_FOR_NEW_WORLDS is True

    def run(name, *flags):
        out = tmp_path / name
        execute_run(parser.parse_args(["--seed", "42", "--turns", "3", "--regions", "8",
                                       "--civs", "4", "--agents", "off",
                                       "--simulate-only", "--output", str(out / "chronicle.md"),
                                       "--state", str(out / "state.json"), *flags]))
        return WorldState.load(out / "state.json")

    assert run("default").guilds is not None
    assert run("off", "--no-guilds").guilds is None
    # A saved world keeps its setting on resume, either way, with no flag.
    for name, kept in (("default", True), ("off", False)):
        out = tmp_path / name
        resumed = parser.parse_args(["--seed", "42", "--turns", "5", "--regions", "8", "--civs", "4",
                                     "--agents", "off", "--simulate-only",
                                     "--output", str(out / "chronicle.md")])
        resumed.resume = str(out / "state.json")
        resumed.state = str(out / "resumed.json")
        execute_run(resumed)
        assert (WorldState.load(out / "resumed.json").guilds is not None) is kept


# --- formation and privileges ------------------------------------------------------

def test_a_city_that_makes_wares_forms_a_craft_guild_and_a_town_without_does_not():
    world = _world()
    _city(world, crafts=0.2, size=12.0, rank=1)
    _city(world, region=AMBER, sid=2, size=8.0, rank=1, mix=(0.6, 0.2, 0.05, 0.1, 0.05))
    events = _tick(world)
    assert _types(events).count("guild_founded") == 1
    guild = world.guilds.guilds[0]
    assert guild.kind == CRAFT and guild.city == 1 and guild.region == THORNWOOD
    assert guild.name.endswith("Guild of Thornwood Settlement 1") and "Merchant" not in guild.name
    assert not guild.monopoly and not guild.say
    _tick(world)   # one guild per city
    assert len(world.guilds.guilds) == 1


def test_enough_merchants_and_craftworkers_form_a_merchant_guild():
    world = _world()
    city = _city(world, size=40.0)
    k = C.scale(world)
    assert G.masters(city, k) >= G.GUILD_MASTERS
    _tick(world)
    guild = world.guilds.guilds[0]
    assert guild.kind == MERCHANT and guild.name == f"the Merchant Guild of {city.name}"
    expected = 40.0 / k * (0.25 + 0.45 * (1.0 - C.URBAN_FARM_LABOR[2]))
    assert guild.masters == pytest.approx(expected, abs=1e-3)


def test_charters_grant_privileges_and_a_revocation_is_a_threat():
    world = _world(movements=False)
    city = _city(world, crafts=0.2, charter=MARKET_RIGHTS)
    events = _tick(world)
    guild = world.guilds.guilds[0]
    assert guild.monopoly and not guild.say
    assert "guild_privilege" in _types(events)
    world.turn += 1
    city.charter = SELF_GOVERNMENT
    _tick(world)
    assert guild.say
    world.turn += 1
    city.charter = MARKET_RIGHTS   # a conqueror revokes a level
    events = _tick(world)
    assert not guild.say and guild.monopoly
    assert "guild_privilege_lost" in _types(events)
    assert world.guilds.counters["threats"] == 1
    assert [k for _t, k, _e in guild.history][-2:] == ["lost", "threat"]


def test_privileges_shape_commerce_dues_and_the_guilds_take():
    world = _world()
    guild = Guild(city=1, region=THORNWOOD, name="the Test Guild", founded_turn=1)
    assert G.craft_access(guild, 0.3, 1.0) == (0.3, 1.0)
    guild.monopoly = True
    assert G.craft_access(guild, 0.3, 1.0) == pytest.approx((0.45, 1.5))
    assert G.dues_share(world, guild, 0.2) == pytest.approx(0.2)
    guild.say = True
    assert G.dues_share(world, guild, 0.2) == pytest.approx(0.2 * G.SAY_DUES)
    guild.levy_turn = world.turn - 1
    assert G.dues_share(world, guild, 0.2) == pytest.approx(0.2 * G.SAY_DUES + G.LEVY_SHARE)
    guild.levy_turn = world.turn - G.LEVY_TURNS
    assert G.dues_share(world, guild, 0.2) == pytest.approx(0.2 * G.SAY_DUES)
    assert G.take(world.guilds, guild, 10.0) == pytest.approx(10.0 * G.MONOPOLY_TAKE)
    assert guild.wealth == pytest.approx(1.0)
    assert G.wall_help(guild, 35.0, 30.0) == 0.0          # the purse pays alone
    assert G.wall_help(guild, 29.5, 30.0) == pytest.approx(0.5)
    assert G.wall_help(guild, 20.0, 30.0) == 0.0          # not enough between them


def test_a_guild_with_a_say_lowers_the_dues_its_lord_is_owed():
    def dues(with_guild: bool) -> float:
        world = _world(movements=False)
        city = _city(world, charter=SELF_GOVERNMENT, size=30.0)
        if with_guild:
            world.guilds.guilds.append(Guild(city=1, region=THORNWOOD, name="g", founded_turn=1,
                                             say=True, monopoly=True))
        t = C._Tick(world, None, None, None)
        C._commerce(t, city, world.regions[THORNWOOD], 1.0, C.scale(world))
        return world.cities.owed[THORNWALL] / city.commerce
    assert dues(False) == pytest.approx(C.DUES[SELF_GOVERNMENT], rel=1e-3)
    assert dues(True) == pytest.approx(C.DUES[SELF_GOVERNMENT] * G.SAY_DUES, rel=1e-3)


def test_a_falling_city_dissolves_its_guild():
    world = _world()
    _city(world, crafts=0.2)
    _tick(world)
    world.cities.cities.clear()
    world.turn += 1
    events = _tick(world)
    assert "guild_dissolved" in _types(events)
    assert world.guilds.guilds[0].dissolved_turn == world.turn
    assert G.guild_index(world) == {}


# --- levies, threats, guild movements and the guild charter ---------------------

def _threatened_world(monkeypatch):
    monkeypatch.setattr(G, "LEVY_CHANCE", 1.0)
    monkeypatch.setattr(G, "MOVEMENT_CHANCE", 1.0)
    world = _world()
    city = _city(world, size=40.0, charter=MARKET_RIGHTS)
    _tick(world, _rows(world, sid_region=THORNWOOD))
    world.civilizations[THORNWALL].treasury = 10
    world.turn += 1
    return world, city


def test_a_poor_lord_levies_the_city_and_the_guild_rises(monkeypatch):
    world, city = _threatened_world(monkeypatch)
    events = _tick(world, _rows(world, sid_region=THORNWOOD))
    assert "guild_levy" in _types(events) and "movement_founded" in _types(events)
    guild = world.guilds.guilds[0]
    assert guild.levy_turn == world.turn and guild.movement == 0
    m = world.agent_movements.movements[0]
    assert m.creed == GUILD and m.home_region == THORNWOOD and m.target == THORNWALL
    assert m.name == guild.name and m.stage == GATHERING
    founding = next(e for e in events if e.event_type == "movement_founded")
    levy = next(e for e in events if e.event_type == "guild_levy")
    assert levy.event_id in founding.causes
    # The native table carries the guild's city for its row.
    world.turn += 1
    table = M.movement_table(world).to_pydict()
    assert table["creed"] == [GUILD] and table["settlement"] == [1]
    assert table["found_region"] == [THORNWOOD]
    assert G.dues_share(world, guild, 0.2) == pytest.approx(0.2 + G.LEVY_SHARE)
    # A content city does not rise; a guild with its movement alive does not found another.
    _tick(world, _rows(world, sid_region=THORNWOOD))
    assert len(world.agent_movements.movements) == 1


def test_content_townsmen_or_no_agent_rows_raise_no_movement(monkeypatch):
    world, city = _threatened_world(monkeypatch)
    city.satisfaction = 0.8
    _tick(world, _rows(world, sid_region=THORNWOOD))
    assert world.guilds.counters["levies"] == 1 and not world.agent_movements.movements
    world2, _ = _threatened_world(monkeypatch)
    _tick(world2)   # --agents off: no rows, no members to seed
    assert world2.guilds.counters["levies"] == 1 and not world2.agent_movements.movements


def _won_charter(world, monkeypatch):
    """A guild movement presses its demand and the lord grants it."""
    monkeypatch.setattr(M, "grant_chance", lambda t, m, civ: 1.0)
    i = 0
    m = world.agent_movements.movements[i]
    m.founded_turn = world.turn - 10
    rows = _rows(world, {(i, THORNWOOD): 9}, sid_region=THORNWOOD)
    events = M.tick_agent_movements(world, [], acc=None, phase10=rows)
    world.events_timeline.extend(events)
    return events


def test_a_granted_guild_demand_is_a_guild_charter_with_its_privileges(monkeypatch):
    world, city = _threatened_world(monkeypatch)
    _tick(world, _rows(world, sid_region=THORNWOOD))
    world.turn += 6
    military = world.civilizations[THORNWALL].factions.influence[FactionType.MILITARY]
    events = _won_charter(world, monkeypatch)
    assert "movement_reform" in _types(events)
    r = world.agent_movements.reforms[0]
    assert r.kind == GUILD_CHARTER and r.cities == [1] and r.regions == [THORNWOOD]
    assert r.repeal == IN_FORCE
    assert "charter of the" in M.reform_name(world, r)
    assert world.civilizations[THORNWALL].factions.influence[FactionType.MILITARY] < military
    reforms = M.reform_table(world).to_pydict()
    assert reforms == {"creed": [GUILD_CHARTER], "civ": [THORNWALL], "region": [THORNWOOD],
                       "faith": [255]}
    world.turn += 1
    _tick(world, _rows(world, sid_region=THORNWOOD))
    guild = world.guilds.guilds[0]
    assert guild.charter_reform == 0 and guild.monopoly and guild.say and guild.levy_turn is None
    assert G.dues_share(world, guild, 0.2) == pytest.approx(0.2 * G.SAY_DUES * G.CHARTER_DUES)
    # No levy under a guild charter.
    world.civilizations[THORNWALL].treasury = 0
    world.turn += 1
    _tick(world, _rows(world, sid_region=THORNWOOD))
    assert guild.levy_turn is None


def test_a_repealed_guild_charter_raises_a_restoration_and_a_lost_city_lapses_it(monkeypatch):
    world, city = _threatened_world(monkeypatch)
    _tick(world, _rows(world, sid_region=THORNWOOD))
    world.turn += 6
    _won_charter(world, monkeypatch)
    world.turn += 1
    _tick(world, _rows(world, sid_region=THORNWOOD))
    m = world.agent_movements.movements[0]
    m.stage, m.end, m.ended_turn = ENDED, 2, world.turn   # won and disbanded
    monkeypatch.setattr(G, "RESTORE_CHANCE", 1.0)
    world.turn += 1
    r = world.agent_movements.reforms[0]
    r.repeal, r.repealed_turn, r.repeal_event_id = RULER, world.turn, "x"
    events = _tick(world, _rows(world, sid_region=THORNWOOD))
    guild = world.guilds.guilds[0]
    assert guild.charter_reform == -1 and "movement_founded" in _types(events)
    restoration = world.agent_movements.movements[1]
    assert restoration.creed == GUILD and restoration.restores == 0
    assert restoration.name.startswith(guild.name)
    assert "restoration of the charter" in M._demand_text(world, restoration)
    # A guild charter lapses when its city changes hands.
    world2, city2 = _threatened_world(monkeypatch)
    _tick(world2, _rows(world2, sid_region=THORNWOOD))
    world2.turn += 6
    _won_charter(world2, monkeypatch)
    city2.lord = KETHANI
    world2.turn += 1
    M.tick_agent_movements(world2, [], acc=None, phase10=None)
    assert world2.agent_movements.reforms[0].repeal == LAPSED


def test_a_guild_rising_stirs_its_city():
    world = _world()
    city = _city(world)
    world.guilds.guilds.append(Guild(city=1, region=THORNWOOD, name="g", founded_turn=1, movement=0))
    before = city.unrest
    G.on_guild_rising(world, 0)
    assert city.unrest == pytest.approx(min(1.0, before + G.RISING_UNREST))
    assert G.movement_appeal(world, 0) == 1.0
    world.guilds.guilds[0].wealth = G.WEALTH_APPEAL
    assert G.movement_appeal(world, 0) == pytest.approx(1.0 + G.APPEAL_CAP)
    assert G.movement_appeal(world, 1) == 1.0


def test_the_guild_creed_has_its_parameters_and_ally():
    world = _world()
    civ = world.civilizations[THORNWALL]
    assert M._ally_faction(GUILD, civ) is FactionType.MERCHANT
    civ.factions.influence[FactionType.BURGHER] = 0.1
    normalize_influence(civ.factions)
    assert M._ally_faction(GUILD, civ) is FactionType.BURGHER
    assert M._demand_share(GUILD) == M.GUILD_DEMAND_SHARE
    for table in (M.RISE_GRIEVANCE, M.RISE_SHARE, M.RISE_MIN, M.REFORM_INSTITUTIONS,
                  M.REFORM_OPPONENTS, M._NAMES, M._DEMANDS, M._REFORMS):
        assert len(table) == 4


# --- burghers -------------------------------------------------------------------------

def test_burghers_join_with_chartered_cities_and_leave_without():
    world = _world(movements=False)
    city = _city(world, charter=MARKET_RIGHTS)
    civ = world.civilizations[THORNWALL]
    _tick(world)
    inf = civ.factions.influence
    assert FactionType.BURGHER in inf and inf[FactionType.BURGHER] >= 0.08
    assert list(inf)[-1] is FactionType.BURGHER
    assert sum(inf.values()) == pytest.approx(1.0)
    assert G.burgher_weights(world)[THORNWALL] == pytest.approx(
        city.rank * (G.CHARTER_WEIGHT[MARKET_RIGHTS] + G.GUILD_WEIGHT))
    others = [c for i, c in enumerate(world.civilizations) if i != THORNWALL]
    assert all(FactionType.BURGHER not in c.factions.influence for c in others)
    world.cities.cities.clear()
    for _ in range(G.BURGHER_IDLE_TURNS):
        world.turn += 1
        _tick(world)
    assert FactionType.BURGHER not in inf and sum(inf.values()) == pytest.approx(1.0)
    assert world.guilds.counters["burghers_dissolved"] == 1


def test_free_cities_give_the_burghers_weight():
    world = _world(movements=False)
    _city(world, charter=FREE_CITY, rank=2)
    assert G.burgher_weights(world)[THORNWALL] == pytest.approx(2 * G.CHARTER_WEIGHT[FREE_CITY])


def test_burghers_take_the_patricians_voice_and_press_for_charters():
    world = _world(movements=False)
    civ = world.civilizations[THORNWALL]
    merchant = civ.factions.influence[FactionType.MERCHANT]
    base = C._merchant_influence(civ)
    civ.factions.influence[FactionType.BURGHER] = 0.08
    normalize_influence(civ.factions)
    assert C._merchant_influence(civ) == pytest.approx(G.urban_influence(civ))
    assert G.urban_influence(civ) > civ.factions.influence[FactionType.MERCHANT]
    before = civ.factions.influence[FactionType.BURGHER]
    C._shift_merchants(civ, 0.05)
    assert civ.factions.influence[FactionType.BURGHER] > before
    assert base == pytest.approx(merchant)


def test_burgher_weights_stay_within_the_faction_ranges_and_caps():
    top = max(w for ft in CLASSIC_FACTIONS for w in FACTION_WEIGHTS[ft].values())
    low = min(w for ft in CLASSIC_FACTIONS for w in FACTION_WEIGHTS[ft].values())
    assert all(low <= w <= top for w in FACTION_WEIGHTS[FactionType.BURGHER].values())
    world = _world(movements=False)
    civ = world.civilizations[THORNWALL]
    for ft in CLASSIC_FACTIONS:
        civ.factions.influence[ft] = 0.08
    civ.factions.influence[FactionType.BURGHER] = 0.68
    normalize_influence(civ.factions)
    assert max(get_faction_weight_modifier(civ, a) for a in ActionType) <= 1.5
    assert get_faction_weight_modifier(civ, ActionType.TRADE) > 1.0
    assert get_faction_weight_modifier(civ, ActionType.WAR) < 1.0


def test_burghers_stand_for_succession_win_with_charters_and_stay_out_of_the_kernel():
    from chronicler import governance_runtime as gr
    from chronicler.agent_bridge import FACTION_MAP
    world = _world(movements=False)
    civ = world.civilizations[THORNWALL]
    civ.factions.influence[FactionType.BURGHER] = 0.3
    normalize_influence(civ.factions)
    kinds = {c["faction"]: c["type"] for c in generate_faction_candidates(civ, world)}
    assert kinds.get("burgher") == "elected"
    ev = Event(turn=world.turn, event_type="city_charter", actors=[civ.name], description="x")
    assert _event_is_win(ev, civ, FactionType.BURGHER)
    weights = gr._faction_weights(civ)
    assert len(gr._FACTIONS) == 4 and FactionType.BURGHER not in gr._FACTIONS
    assert sum(weights.weight(f) for f in gr.g01.Faction) == pytest.approx(1.0)
    assert FACTION_MAP["burgher"] == 4


def test_burghers_press_for_order_against_commons_and_liberty():
    world = _world()
    civ = world.civilizations[THORNWALL]
    for ft in CLASSIC_FACTIONS:
        civ.factions.influence[ft] = 0.2
    m = Movement(name="x", creed=0, founded_turn=1, home_region=THORNWOOD, target=THORNWALL)
    before = {creed: M.suppress_chance(m.model_copy(update={"creed": creed}), civ) for creed in range(4)}
    civ.factions.influence[FactionType.BURGHER] = 0.2   # the others unchanged
    after = {creed: M.suppress_chance(m.model_copy(update={"creed": creed}), civ) for creed in range(4)}
    for creed in (0, 1):
        assert after[creed] == pytest.approx(before[creed] + G.BURGHER_ORDER * 0.2)
    for creed in (2, GUILD):
        assert after[creed] == before[creed]


# --- movement news ---------------------------------------------------------------------

def test_news_columns_come_from_last_turns_events_and_reset():
    world = _world()
    world.agent_movements.movements.extend([
        Movement(name="a", creed=0, founded_turn=29, home_region=THORNWOOD, target=THORNWALL),
        Movement(name="b", creed=1, founded_turn=10, home_region=AMBER, target=KETHANI,
                 reform_turn=29, crackdown_turn=29, crackdown_region=FROST),
        Movement(name="c", creed=2, founded_turn=29, home_region=AMBER, target=KETHANI),
    ])
    codes, intensity = G.movement_news_columns(world)
    assert codes[THORNWOOD] == 0 * 4 + G.FOUNDING_NEWS and intensity[THORNWOOD] == 120
    assert codes[AMBER] == 1 * 4 + G.REFORM_NEWS and intensity[AMBER] == 220   # the strongest
    assert codes[FROST] == 1 * 4 + G.CRACKDOWN_NEWS
    assert codes[VERDANT] == G.NO_NEWS and intensity[VERDANT] == 0
    world.turn = 31   # nothing happened at turn 30: every region reads no news
    assert set(G.movement_news_columns(world)[0]) == {G.NO_NEWS}
    world.turn = 30
    world.tuning_overrides = {"guilds.movement_news": 0}
    assert G.movement_news_columns(world) is None
    world.tuning_overrides = {}
    from chronicler.agent_bridge import build_region_batch
    names = build_region_batch(world).schema.names
    assert "movement_news" in names and "movement_news_intensity" in names
    off = generate_world(seed=42)
    C.set_cities_enabled(off, True)
    M.set_agent_movements_enabled(off, True)
    assert "movement_news" not in build_region_batch(off).schema.names


def _emerge_with(monkeypatch, world, informed, roll):
    """Run emergence over one candidate (commons, Thornwood, 10 of 30
    aggrieved: chance 0.05) with a fixed roll; returns the foundings."""
    founded = []
    monkeypatch.setattr(M, "_found", lambda t, ri, creed, *a, **k: founded.append((ri, creed)) or True)
    monkeypatch.setattr(M, "_carrier", lambda *a, **k: (None, 1.0))
    monkeypatch.setattr(M, "_rng", lambda *a, **k: SimpleNamespace(random=lambda: roll))
    nreg = len(world.regions)
    aggrieved = [[0, 0, 0] for _ in range(nreg)]
    aggrieved[THORNWOOD] = [10, 0, 0]
    info = None
    if informed is not None:
        info = [[0, 0, 0] for _ in range(nreg)]
        info[THORNWOOD] = [informed, 0, 0]
    M._emerge(M._Tick(world, None, None, None), ([30] * nreg, aggrieved, info))
    return founded


def test_news_raises_the_founding_chance_within_its_bound(monkeypatch):
    assert G.news_founding_factor(10, 0) == 1.0
    assert G.news_founding_factor(10, 2) == pytest.approx(1.0 + 0.4 * G.NEWS_FOUND)
    assert G.news_founding_factor(10, 5) == pytest.approx(1.0 + G.NEWS_FOUND)
    assert G.news_founding_factor(10, 50) == pytest.approx(1.0 + G.NEWS_FOUND)
    world = _world()
    assert _emerge_with(monkeypatch, world, None, 0.07) == []      # chance 0.05
    assert _emerge_with(monkeypatch, world, 0, 0.07) == []
    assert _emerge_with(monkeypatch, world, 10, 0.07) == [(THORNWOOD, 0)]   # chance 0.10
    assert world.guilds.counters["news_foundings"] == 1
    assert _emerge_with(monkeypatch, world, 10, 0.11) == []        # bounded at twice
    world.tuning_overrides = {"guilds.movement_news": 0}
    assert _emerge_with(monkeypatch, world, 10, 0.07) == []        # news off: ignored


def test_guild_movements_count_apart_from_the_census_caps(monkeypatch):
    world = _world()
    for k in range(M.MAX_LIVING):
        world.agent_movements.movements.append(Movement(
            name=f"g{k}", creed=GUILD, founded_turn=20, home_region=AMBER, target=KETHANI))
    assert _emerge_with(monkeypatch, world, None, 0.0) == [(THORNWOOD, 0)]


# --- snapshot, history and metrics ---------------------------------------------------

def test_snapshot_history_and_metrics():
    world = _world()
    _city(world, crafts=0.2, charter=MARKET_RIGHTS)
    _tick(world)
    snap = G.snapshot_summary(world)
    assert snap["guilds"][0]["kind"] == "craft" and snap["guilds"][0]["monopoly"] is True
    assert snap["burghers"] == {world.civilizations[THORNWALL].name: pytest.approx(
        world.civilizations[THORNWALL].factions.influence[FactionType.BURGHER], abs=1e-4)}
    assert set(snap["counters"]) == set(G.COUNTER_KEYS)
    lines = G.guild_history(world, 0)
    assert lines[0].startswith(world.guilds.guilds[0].name) and "founded" in lines[1]
    bundles = [{"history": [{"guilds": snap}, {"guilds": snap}]}, {"history": [{}]}]
    metrics = G.extract_guild_metrics(bundles)
    assert metrics["runs"] == 1 and metrics["peak_guilds_mean"] == 1


def test_off_mode_guilds_repeat():
    def run():
        world = generate_world(seed=42)
        world.campaigns_enabled = True
        C.set_cities_enabled(world, True)
        M.set_agent_movements_enabled(world, True)
        G.set_guilds_enabled(world, True)
        _settle(world, THORNWOOD, 40)
        return _advance(world, 30)
    a, b = run(), run()
    assert a.model_dump_json() == b.model_dump_json()
    assert a.guilds.guilds


# --- native ----------------------------------------------------------------------------

def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


@pytest.mark.native
def test_native_news_is_observed_on_the_tick_after_the_event_and_not_again():
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    world = generate_world(seed=42)
    world.agent_mode = "hybrid"
    C.set_cities_enabled(world, True)
    M.set_agent_movements_enabled(world, True)
    G.set_guilds_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    world.turn = 1
    bridge.tick(world)
    assert "created_news" not in bridge._sim.get_knowledge_stats()
    region = max(range(len(world.regions)), key=lambda r: world.regions[r].population)
    civ = world.civ_index_map[world.regions[region].controller]
    world.agent_movements.movements.append(Movement(
        name="the League", creed=0, founded_turn=1, home_region=region, target=civ,
        regions_reached=[region]))
    world.turn = 2
    bridge.tick(world)
    stats = bridge._sim.get_knowledge_stats()
    assert stats.get("created_news", 0) >= 1
    world.turn = 3
    bridge.tick(world)   # no event at turn 2: no new observation
    assert bridge._sim.get_knowledge_stats().get("created_news", 0) == 0


@pytest.mark.native
def test_native_hybrid_run_forms_guilds(tmp_path):
    _require_native()
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    out = tmp_path / "hyb"
    execute_run(parser.parse_args(["--seed", "44", "--turns", "60", "--regions", "8", "--civs", "4",
                                   "--agents", "hybrid", "--simulate-only", "--guilds", "--output",
                                   str(out / "chronicle.md"), "--state", str(out / "state.json")]))
    world = WorldState.load(out / "state.json")
    assert world.guilds.counters["founded"] >= 1
    assert any(FactionType.BURGHER in c.factions.influence for c in world.civilizations)
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(out / "chronicle_bundle.json")
    assert any(h.get("guilds", {}).get("guilds") for h in bundle["history"])
