"""Seats of learning (``chronicler.scholarship``, ``--scholarship``).

Mechanics run on the template world (seed 42) with ticks called directly
(``acc=None``, aggregate mode) and Phase 10 agent rows built as the native
snapshot carries them. Native tests run the real extension.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pyarrow as pa
import pytest

import chronicler.cities as C
import chronicler.scholarship as S
from chronicler import provenance as prov
from chronicler.action_engine import ActionEngine
from chronicler.cities_state import City
from chronicler.models import Event, Infrastructure, InfrastructureType, TurnSnapshot, WorldState
from chronicler.scholarship_state import (
    ACADEMY, COUNTER_KEYS, FALL_CAUSES, FAMINE, HISTORY_KINDS, KIND_NAMES, LEVEL_NAMES, LIBRARY,
    PATRONAGE, PERSECUTION, SACK, TEMPLE_SCHOOL, Seat,
)
from chronicler.simulation import run_turn
from chronicler.turn_artifacts import AgentRows, Phase10Inputs, Stamp
from chronicler.world_gen import generate_world

ROOT = Path(__file__).resolve().parents[1]
# Template seed 42: Ashkari Nomads (civ 0) hold Obsidian Shore (7, capital);
# Kethani Empire (1) Amber Valley (5, capital) and Frostholm Tundra (0);
# Thornwall Confederacy (2) Verdant Plains (2, capital) and Thornwood (4);
# Selurian Republic (3) Ashara Desert (3, capital; values Knowledge).
FROST, VERDANT, ASHARA, THORNWOOD, AMBER, OBSIDIAN = 0, 2, 3, 4, 5, 7
ASHKARI, KETHANI, THORNWALL, SELURIAN = 0, 1, 2, 3


def _world(**kw) -> WorldState:
    world = generate_world(seed=42)
    S.set_scholarship_enabled(world, True)
    world.turn = 40
    for civ in world.civilizations:
        civ.treasury, civ.culture, civ.stability = 200, 60, 60
    for k, v in kw.items():
        setattr(world, k, v)
    return world


def _seat(world, region=VERDANT, kind=ACADEMY, level=1, *, faith=0xFF, city=0, scholars=0.0,
          founded=None) -> tuple[int, Seat]:
    ctrl = world.regions[region].controller
    lord = world.civ_index_map[ctrl] if ctrl else -1
    seat = Seat(region=region, kind=kind, name=f"the {KIND_NAMES[kind].title()} of {world.regions[region].name}",
                founded_turn=world.turn - 30 if founded is None else founded, founder=lord, lord=lord,
                faith=faith, city=city, level=level, peak_level=level, scholars=scholars,
                level_turn=world.turn - 30)
    world.scholarship.seats.append(seat)
    return len(world.scholarship.seats) - 1, seat


def _rows(world, scholars: dict[int, int], others: int = 10):
    """Phase 10 rows: per held region ``others`` farmers and the given scholars."""
    cols = {k: [] for k in ("id", "region", "occupation", "age", "settlement_id", "satisfaction")}
    next_id = 1
    for ri, region in enumerate(world.regions):
        n_sch = scholars.get(ri, 0)
        for k in range(others + n_sch):
            cols["id"].append(next_id)
            cols["region"].append(ri)
            cols["occupation"].append(3 if k < n_sch else 0)
            cols["age"].append(30)
            cols["settlement_id"].append(0)
            cols["satisfaction"].append(0.5)
            next_id += 1
    types = {"id": pa.uint32(), "region": pa.uint16(), "occupation": pa.uint8(), "age": pa.uint16(),
             "settlement_id": pa.uint16(), "satisfaction": pa.float32()}
    batch = pa.record_batch({k: pa.array(v, type=types[k]) for k, v in cols.items()})
    return Phase10Inputs(source_turn=world.turn,
                         agents=AgentRows(stamp=Stamp(world.turn, "phase10_entry"), batch=batch),
                         named_agents=None, economy=None, deaths=())


def _tick(world, events=(), phase10=None):
    out = S.tick_scholarship(world, list(events), acc=None, phase10=phase10)
    world.events_timeline.extend(out)
    return out


def _types(events) -> list[str]:
    return [e.event_type for e in events]


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def _no_draw(monkeypatch, value: float = 0.0):
    """Every scholarship draw returns ``value`` (0: every chance passes)."""
    class _R:
        def random(self):
            return value
    monkeypatch.setattr(S, "_rng", lambda *a, **k: _R())


def _temple(region, faith: int, prestige: int = 50) -> Infrastructure:
    infra = Infrastructure(type=InfrastructureType.TEMPLES, builder_civ=region.controller or "",
                           built_turn=0, faith_id=faith, temple_prestige=prestige)
    region.infrastructure.append(infra)
    return infra


# --- the switch ----------------------------------------------------------------------

def test_switch_dormancy_and_old_saves(tmp_path):
    assert S.DEFAULT_ENABLED_FOR_NEW_WORLDS is False
    world = generate_world(seed=42)
    assert world.scholarship is None and not S.scholarship_enabled(world)
    assert "scholarship" not in json.loads(world.model_dump_json())
    assert S.tick_scholarship(world, []) == []
    assert S.region_pulls(world) == ([0.0] * 8, [False] * 8)
    assert S.learning_factors(world) is None
    assert S.research_factor(world, world.civilizations[0]) == 1.0
    assert S.archive_copies(world, 0, 0) == 0
    path = tmp_path / "state.json"
    world.save(path)
    assert "scholarship" not in json.loads(path.read_text())
    assert WorldState.load(path).scholarship is None
    S.set_scholarship_enabled(world, True)
    assert S.scholarship_enabled(world)
    _seat(world)
    world.save(path)
    loaded = WorldState.load(path)
    assert loaded.scholarship == world.scholarship
    S.set_scholarship_enabled(world, False)
    assert world.scholarship is None
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "scholarship" not in json.loads(snap.model_dump_json())


def test_append_only_orders():
    assert KIND_NAMES[:3] == ("academy", "temple school", "library")
    assert LEVEL_NAMES[:4] == ("fallen", "modest", "renowned", "great")
    assert FALL_CAUSES[:4] == ("sack", "famine", "persecution", "patronage")
    assert HISTORY_KINDS[:10] == ("founded", "rose", "declined", "patron", "unpaid", "struck",
                                  "refugees", "fled", "fell", "master")
    assert COUNTER_KEYS[:3] == ("founded", "academies", "temple_schools")
    from chronicler.models import MIGRATION_DRIVER_NAMES, VOLUNTARY_MIGRATION_DRIVERS
    from chronicler.techniques_state import CHANNELS, CH_SCHOLARS
    assert MIGRATION_DRIVER_NAMES[19] == "learning" and "learning" in VOLUNTARY_MIGRATION_DRIVERS
    assert CHANNELS[CH_SCHOLARS] == "scholars" and CH_SCHOLARS == 7


def test_cli_flag_gate_forwarding_live_default_and_benchmark_pin():
    from chronicler.main import _build_parser
    parser = _build_parser()
    assert parser.parse_args([]).scholarship is None
    assert parser.parse_args(["--scholarship"]).scholarship is True
    assert parser.parse_args(["--no-scholarship"]).scholarship is False
    spec = importlib.util.spec_from_file_location("m53b", ROOT / "scripts" / "m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._scholarship_args(argparse.Namespace(scholarship=True)) == ["--scholarship"]
    assert m53b._scholarship_args(argparse.Namespace(scholarship=False)) == ["--no-scholarship"]
    assert m53b._scholarship_args(argparse.Namespace(scholarship=None)) == []
    assert "set_scholarship_enabled" in (ROOT / "src" / "chronicler" / "live.py").read_text()
    assert "scholarship=False" in (ROOT / "scripts" / "benchmark_headless.py").read_text()


def test_new_worlds_follow_the_default_and_resume_keeps_the_saved_setting(tmp_path):
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()

    def args(out, *extra, turns=3):
        return parser.parse_args(["--seed", "42", "--turns", str(turns), "--regions", "8", "--civs", "4",
                                  "--agents", "off", "--simulate-only", *extra,
                                  "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    fresh, on = tmp_path / "fresh", tmp_path / "on"
    execute_run(args(fresh))
    assert "scholarship" not in json.loads((fresh / "state.json").read_text())
    execute_run(args(on, "--scholarship"))
    assert "scholarship" in json.loads((on / "state.json").read_text())
    for run, kept in ((fresh, False), (on, True)):
        resumed = args(run, turns=5)
        resumed.resume = str(run / "state.json")
        resumed.state = str(run / "resumed.json")
        execute_run(resumed)
        assert ("scholarship" in json.loads((run / "resumed.json").read_text())) is kept


def test_feature_off_never_runs_scholarship_code(monkeypatch):
    import chronicler.contact_ledger as cl
    import chronicler.techniques as T
    from chronicler import historiography as H

    def boom(*a, **k):
        raise AssertionError("scholarship code ran with the switch off")

    for name in ("tick_scholarship", "region_pulls", "research_factor", "learning_factors",
                 "apply_carries", "archive_copies", "snapshot_summary", "living_seats"):
        monkeypatch.setattr(S, name, boom)
    world = generate_world(seed=42)
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, True)
    T.set_techniques_enabled(world, True)
    C.set_cities_enabled(world, True)
    H.set_historiography_enabled(world, True)
    _advance(world, 25)
    for _ in range(3):
        H.observe_turn(world)
    from chronicler.agent_bridge import build_region_batch
    names = build_region_batch(world).schema.names
    assert "seat_pull" not in names and "seat_flight" not in names
    assert world.scholarship is None


# --- foundings -----------------------------------------------------------------------

def test_a_ruler_at_peace_founds_an_academy_at_its_capital(monkeypatch):
    _no_draw(monkeypatch)
    world = _world()
    thornwall = world.civilizations[THORNWALL]
    events = _tick(world)
    seats = world.scholarship.seats
    academies = [s for s in seats if s.kind == ACADEMY]
    assert {s.region for s in academies} == {OBSIDIAN, AMBER, VERDANT, ASHARA}
    verdant = next(s for s in academies if s.region == VERDANT)
    assert verdant.lord == THORNWALL and verdant.level == 1 and verdant.name == "the Academy of Verdant Plains"
    assert thornwall.treasury == 200 - S.ACADEMY_FEE
    assert "seat_founded" in _types(events)
    assert verdant.history[0][1] == "founded"
    # One academy per ruler: no second one next turn.
    world.turn += 1
    _tick(world)
    assert sum(1 for s in world.scholarship.seats if s.kind == ACADEMY) == 4


def test_no_academy_at_war_poor_or_starving(monkeypatch):
    _no_draw(monkeypatch)
    world = _world()
    a, b, c, d = world.civilizations
    world.active_wars = [(a.name, b.name)]
    c.treasury = S.ACADEMY_TREASURY - 1
    world.regions[ASHARA].famine_cooldown = 3
    _tick(world)
    assert world.scholarship.seats == []


def test_learned_rulers_found_more_readily(monkeypatch):
    world = _world()
    selurian, kethani = world.civilizations[SELURIAN], world.civilizations[KETHANI]
    assert S._learned(selurian) and not S._learned(kethani)
    _no_draw(monkeypatch, S.ACADEMY_CHANCE * 1.5)   # between the plain and the learned chance
    _tick(world)
    assert [s.region for s in world.scholarship.seats] == [ASHARA]


def test_a_prestigious_temple_founds_a_school_paid_in_prestige(monkeypatch):
    _no_draw(monkeypatch)
    world = _world()
    for civ in world.civilizations:
        civ.treasury = 0   # no academies
    temple = _temple(world.regions[THORNWOOD], 2, prestige=S.SCHOOL_PRESTIGE + S.SCHOOL_COST)
    _temple(world.regions[FROST], 1, prestige=S.SCHOOL_PRESTIGE)   # not enough
    events = _tick(world)
    [seat] = world.scholarship.seats
    assert (seat.kind, seat.region, seat.faith) == (TEMPLE_SCHOOL, THORNWOOD, 2)
    assert temple.temple_prestige == S.SCHOOL_PRESTIGE
    assert "the Faith of Thornwall open the Temple School of Thornwood" in events[0].description


def test_no_school_at_a_temple_of_another_faith_than_the_realms(monkeypatch):
    _no_draw(monkeypatch)
    world = _world()
    for civ in world.civilizations:
        civ.treasury = 0
    _temple(world.regions[THORNWOOD], 1, prestige=100)   # Kethani faith under Thornwall
    _tick(world)
    assert world.scholarship.seats == []


def test_a_rich_city_founds_a_library_from_its_purse(monkeypatch):
    _no_draw(monkeypatch)
    world = _world()
    for civ in world.civilizations:
        civ.treasury = 0
    C.set_cities_enabled(world, True)
    city = City(settlement_id=3, region=THORNWOOD, name="Thornwood Settlement 1", founded_turn=1,
                founder=THORNWALL, lord=THORNWALL, rank=2, residents=30, size=30.0, wealth=50.0)
    world.cities.cities.append(city)
    small = City(settlement_id=4, region=FROST, name="Frost Settlement 1", founded_turn=1, founder=KETHANI,
                 lord=KETHANI, rank=1, residents=12, size=12.0, wealth=50.0)
    world.cities.cities.append(small)
    _tick(world)
    [seat] = world.scholarship.seats
    assert (seat.kind, seat.city, seat.region) == (LIBRARY, 3, THORNWOOD)
    assert city.wealth == pytest.approx(50.0 - S.LIBRARY_FEE)
    assert small.wealth == 50.0


# --- upkeep, scholars and rises ---------------------------------------------------------

def test_upkeep_is_paid_as_keep_treasury_with_the_fraction_carried(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    _si, seat = _seat(world, VERDANT, level=2)
    thornwall = world.civilizations[THORNWALL]
    paid = []
    for turn in range(5):
        world.turn += 1
        before = thornwall.treasury
        _tick(world)
        paid.append(before - thornwall.treasury)
    assert paid == [0, 1, 0, 1, 1]   # 0.6 a turn
    assert seat.unpaid == 0 and world.scholarship.counters["upkeep"] == 3


def test_unpaid_upkeep_costs_a_level_then_the_seat(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    si, seat = _seat(world, VERDANT, level=2)
    world.civilizations[THORNWALL].treasury = 0
    kinds = []
    for _ in range(40):
        world.turn += 1
        kinds += _types(_tick(world))
        if seat.fallen_turn is not None:
            break
    assert kinds.count("seat_declined") == 1 and kinds[-1] in ("seat_fell", "scholars_fled")
    assert seat.fall_cause == PATRONAGE and seat.level == 0
    assert "no longer pays its masters" in world.events_timeline[-1].description \
        or "no longer pays its masters" in next(e.description for e in world.events_timeline
                                                if e.event_type == "seat_fell")


def test_scholars_rise_a_seat_when_its_patron_pays_the_fee(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    _si, seat = _seat(world, VERDANT, level=1)
    k = C.scale(world)
    need = int(S.RISE_SCHOLARS[2] * k) + 1
    events = _tick(world, phase10=_rows(world, {VERDANT: need}))
    assert seat.level == 2 and "seat_rose" in _types(events)
    assert seat.scholars == pytest.approx(need / k, abs=1e-3)
    assert world.civilizations[THORNWALL].treasury == 200 - int(S.RISE_FEE[2])
    # Not again before RISE_INTERVAL turns.
    world.turn += 1
    _tick(world, phase10=_rows(world, {VERDANT: 50}))
    assert seat.level == 2


def test_great_scholars_teach_at_their_rulers_seat(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    from chronicler.models import GreatPerson
    world = _world()
    _si, seat = _seat(world, VERDANT, level=1)
    thornwall = world.civilizations[THORNWALL]
    thornwall.great_persons.append(GreatPerson(name="Sage Ilm", role="scientist", trait="bold",
                                               civilization=thornwall.name,
                                               origin_civilization=thornwall.name, born_turn=1))
    events = _tick(world)
    assert seat.masters == 1 and seat.teachers == ["Sage Ilm"]
    assert "Sage Ilm teaches at the Academy of Verdant Plains" in events[0].description
    world.turn += 1
    assert "seat_master" not in _types(_tick(world))   # once per scholar
    assert seat.scholars >= S.MASTER_SCHOLARS


def test_agents_off_scholars_are_a_share_of_the_people():
    world = _world()
    _si, seat = _seat(world, AMBER, level=1)
    _tick(world)
    region = world.regions[AMBER]
    assert seat.scholars == pytest.approx(region.population * S.OFF_SCHOLAR_SHARE / C.scale(world), abs=1e-3)


# --- strikes, falls and flight ----------------------------------------------------------

def _occupy(world, region_i: int, by: str) -> Event:
    region = world.regions[region_i]
    region.occupied_by = by
    ev = Event(turn=world.turn, event_type="occupation", actors=[by, region.controller],
               description=f"{by} occupies {region.name}", importance=7, region=region.name)
    prov.remember(world, prov.key("occupation", region.name), ev)
    world.events_timeline.append(ev)
    return ev


def test_a_sack_burns_a_modest_seat_and_its_scholars_flee_to_a_rivals_seat(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    import chronicler.techniques as T
    world = _world()
    T.set_techniques_enabled(world, True)
    si, seat = _seat(world, VERDANT, level=1, scholars=8.0)
    own, own_seat = _seat(world, THORNWOOD, level=1)        # the same ruler's, next door
    rival, rival_seat = _seat(world, ASHARA, level=2)       # Selurian, next door
    occupation = _occupy(world, VERDANT, "Selurian Republic")
    events = _tick(world)
    assert _types(events)[:2] == ["seat_fell", "scholars_fled"]
    fell, fled = events[0], events[1]
    assert "is burned when Selurian Republic take Verdant Plains" in fell.description
    assert occupation.event_id in fell.causes and fell.event_id in fled.causes
    assert seat.fall_cause == SACK and seat.refuge == rival
    # The refuge counts them in its own update later in the tick (one decay).
    assert rival_seat.refugees == pytest.approx(S.FLIGHT_SHARE * 8.0 * (1 - S.REFUGEE_DECAY))
    assert world.scholarship.carries == [(VERDANT, ASHARA, THORNWALL, si)]
    assert "refugees" in [k for _t, k, _e in rival_seat.history]


def test_a_sack_costs_a_greater_seat_a_level_when_it_survives(monkeypatch):
    world = _world()
    _si, seat = _seat(world, VERDANT, level=3)
    _no_draw(monkeypatch, 0.999)    # survives the SACK_FALL draw
    _occupy(world, VERDANT, "Selurian Republic")
    events = _tick(world)
    assert seat.level == 2 and seat.fallen_turn is None and "seat_declined" in _types(events)
    world.turn += 1
    _occupy(world, VERDANT, "Selurian Republic")
    _tick(world)
    assert seat.level == 2, "one strike in STRIKE_COOLDOWN turns"


def test_famine_costs_a_level_and_closes_a_modest_seat(monkeypatch):
    _no_draw(monkeypatch)
    world = _world()
    _si, great = _seat(world, VERDANT, level=2)
    _sj, modest = _seat(world, AMBER, level=1)
    famines = [Event(turn=world.turn, event_type="famine", actors=[world.regions[r].controller],
                     description="Famine strikes", importance=6, region=world.regions[r].name,
                     episode="tick", event_id=f"{world.turn}:famine:{r}") for r in (VERDANT, AMBER)]
    events = _tick(world, famines)
    assert great.level == 1 and great.fallen_turn is None
    assert modest.fall_cause == FAMINE
    fell = next(e for e in events if e.event_type == "seat_fell")
    assert famines[1].event_id in fell.causes and "closes as famine empties Amber Valley" in fell.description
    # A dearth does not strike.
    _sk, other = _seat(world, OBSIDIAN, level=1)
    world.turn += 20
    dearth = Event(turn=world.turn, event_type="dearth", actors=[], description="Dearth", importance=4,
                   region=world.regions[OBSIDIAN].name)
    _tick(world, [dearth])
    assert other.fallen_turn is None


def test_persecution_of_the_scholars_faith_closes_the_seat(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    _si, seat = _seat(world, VERDANT, level=2, faith=3)
    region = world.regions[VERDANT]
    region.persecution_intensity, region.persecuting_faith = 0.6, 2
    for turn in range(S.PERSECUTION_TURNS - 1):
        world.turn += 1
        _tick(world)
        assert seat.fallen_turn is None
    world.turn += 1
    events = _tick(world)
    assert seat.fall_cause == PERSECUTION
    assert "its scholars of the Faith of Selurian are persecuted in Verdant Plains" in events[0].description
    # Its own faith is not persecuted.
    _sj, own = _seat(world, THORNWOOD, level=1, faith=2)
    world.regions[THORNWOOD].persecution_intensity, world.regions[THORNWOOD].persecuting_faith = 0.6, 2
    for _ in range(S.PERSECUTION_TURNS + 1):
        world.turn += 1
        _tick(world)
    assert own.fallen_turn is None


def test_a_temple_school_falls_with_its_temple_and_a_library_with_its_city(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    C.set_cities_enabled(world, True)
    temple = _temple(world.regions[THORNWOOD], 2)
    _si, school = _seat(world, THORNWOOD, TEMPLE_SCHOOL, faith=2)
    _sj, library = _seat(world, AMBER, LIBRARY, city=9)
    _tick(world)
    assert school.fallen_turn is None and library.fall_cause == PATRONAGE
    temple.active = False
    world.turn += 1
    _tick(world)
    assert school.fall_cause == PATRONAGE


def test_a_temple_school_is_kept_by_its_temples_offerings(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    temple = _temple(world.regions[THORNWOOD], 2, prestige=10)
    _si, school = _seat(world, THORNWOOD, TEMPLE_SCHOOL, level=3, faith=2)
    for _ in range(4):
        world.turn += 1
        _tick(world)
    assert temple.temple_prestige == 10 - 4   # 1.0 a turn at level 3


def test_a_lord_change_in_peace_hands_the_academy_to_the_new_ruler(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    _si, seat = _seat(world, THORNWOOD, level=1)
    world.regions[THORNWOOD].controller = "Kethani Empire"
    events = _tick(world)
    assert seat.lord == KETHANI and seat.fallen_turn is None
    assert "Kethani Empire takes the Academy of Thornwood in Thornwood under its patronage" in events[0].description


def test_no_refuge_out_of_reach_and_a_carry_only_with_techniques(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    _si, seat = _seat(world, VERDANT, level=1)
    _occupy(world, VERDANT, "Selurian Republic")
    events = _tick(world)
    assert _types(events) == ["seat_fell"] and seat.refuge == -1
    assert world.scholarship.carries == []   # techniques are off


# --- effects --------------------------------------------------------------------------

def test_research_factor_counts_the_levels_of_a_rulers_seats():
    world = _world()
    thornwall = world.civilizations[THORNWALL]
    assert S.research_factor(world, thornwall) == 1.0
    _seat(world, VERDANT, level=2)
    _seat(world, THORNWOOD, level=3)
    assert S.research_factor(world, thornwall) == pytest.approx(
        1.0 + S.RESEARCH_PER_LEVEL * S.RESEARCH_LEVELS)
    import chronicler.techniques as T
    T.set_techniques_enabled(world, True)
    base = T._research_multiplier(world, world.civilizations[KETHANI], {})
    assert T._research_multiplier(world, thornwall, {}) == pytest.approx(base * 1.6)


def test_learning_factors_near_a_seat():
    world = _world()
    _seat(world, VERDANT, level=2)
    hazard, forget = S.learning_factors(world)
    assert hazard[VERDANT] == pytest.approx(1.0 + 2 * S.LEARN_HAZARD)
    assert forget[VERDANT] == pytest.approx(1.0 - 2 * S.LEARN_KEEP)
    for name in world.regions[VERDANT].adjacencies:
        j = next(i for i, r in enumerate(world.regions) if r.name == name)
        assert hazard[j] == pytest.approx(1.0 + 2 * S.LEARN_NEAR) and j not in forget
    assert AMBER not in hazard


def test_a_seat_speeds_adoption_and_keeps_practice_in_its_region():
    import chronicler.techniques as T
    from chronicler.techniques_state import CH_SEEDED, TECHNIQUE_INDEX
    world = generate_world(seed=42)
    T.set_techniques_enabled(world, True)
    _advance(world, 1)
    st = world.techniques
    writing, masonry = TECHNIQUE_INDEX["writing"], TECHNIQUE_INDEX["masonry"]
    # Writing practised in Verdant Plains and barely in Thornwood next door
    # (one ruler); masonry in Thornwood itself and in Amber Valley, far off.
    st.rows = sorted([(VERDANT, writing, 0.8, -1, CH_SEEDED, THORNWALL),
                      (THORNWOOD, writing, 0.05, -1, CH_SEEDED, THORNWALL),
                      (THORNWOOD, masonry, 0.5, -1, CH_SEEDED, THORNWALL),
                      (AMBER, masonry, 0.5, -1, CH_SEEDED, KETHANI)])
    st.invalidate()
    ctrl = T._controllers(world, T._civ_indices(world))
    links = T._contacts(world, ctrl)
    suit = T._suitability(world, ctrl, links)
    plain, _ = T._update_practice(world, st, ctrl, links, suit)
    S.set_scholarship_enabled(world, True)
    _seat(world, THORNWOOD, level=3)
    learned, _ = T._update_practice(world, st, ctrl, links, suit, S.learning_factors(world))
    # Adoption from Verdant Plains quickens; masonry is kept longer.
    assert learned[(THORNWOOD, writing)] > plain[(THORNWOOD, writing)]
    assert learned[(THORNWOOD, masonry)] > plain[(THORNWOOD, masonry)]
    # Far from the seat nothing changes.
    assert learned[(AMBER, masonry)] == plain[(AMBER, masonry)]
    assert learned[(VERDANT, writing)] >= plain[(VERDANT, writing)]


def test_carried_techniques_start_in_the_refuge_and_part_is_lost_where_it_fell():
    from chronicler.techniques_state import CH_SCHOLARS, TECHNIQUE_INDEX
    import chronicler.techniques as T
    world = _world()
    T.set_techniques_enabled(world, True)
    K = TECHNIQUE_INDEX
    practice = {(VERDANT, K["writing"]): 0.9, (VERDANT, K["masonry"]): 0.8,
                (VERDANT, K["coinage"]): 0.6, (VERDANT, K["roads"]): 0.5,
                (VERDANT, K["law_codes"]): 0.4,
                (ASHARA, K["writing"]): 0.5, (ASHARA, K["masonry"]): 0.3}
    meta = {key: (key[0], 0, -1) for key in practice}
    suit = [[True] * len(T.TECHNIQUES) for _ in world.regions]
    world.scholarship.carries = [(VERDANT, ASHARA, THORNWALL, 0)]
    S.apply_carries(world, practice, meta, suit, T._PREREQS, CH_SCHOLARS)
    # law_codes needs coinage (not practised in the refuge): not carried;
    # coinage and roads are (their prerequisites are), highest tier first.
    assert practice[(ASHARA, K["coinage"])] == S.CARRY_LEVEL
    assert practice[(ASHARA, K["roads"])] == S.CARRY_LEVEL
    assert (ASHARA, K["law_codes"]) not in practice
    assert meta[(ASHARA, K["coinage"])] == (VERDANT, CH_SCHOLARS, THORNWALL)
    # Where it fell: tier >= 2 lose FALL_LOSS, tier 1 is kept.
    assert practice[(VERDANT, K["coinage"])] == pytest.approx(0.6 * (1 - S.FALL_LOSS))
    assert practice[(VERDANT, K["law_codes"])] == pytest.approx(0.4 * (1 - S.FALL_LOSS))
    assert practice[(VERDANT, K["writing"])] == 0.9
    assert world.scholarship.carries == []
    assert world.scholarship.counters["carried"] == 2


def test_a_refuge_civ_learns_a_technique_from_the_fleeing_scholars():
    import chronicler.techniques as T
    from chronicler.techniques_state import TECHNIQUE_INDEX
    world = generate_world(seed=42)
    T.set_techniques_enabled(world, True)
    S.set_scholarship_enabled(world, True)
    _advance(world, 2)
    st = world.techniques
    k = TECHNIQUE_INDEX["coinage"]
    rows = {(r, kk): (p, src, ch, sc) for r, kk, p, src, ch, sc in st.rows}
    rows[(VERDANT, k)] = (0.8, VERDANT, 5, THORNWALL)
    for q in T._PREREQS[k]:
        rows[(ASHARA, q)] = (0.9, ASHARA, 5, SELURIAN)
        rows[(VERDANT, q)] = (0.9, VERDANT, 5, THORNWALL)
    rows.pop((ASHARA, k), None)
    st.rows = [(r, kk, *v) for (r, kk), v in sorted(rows.items())]
    st.invalidate()
    if k in st.known[SELURIAN]:
        st.known[SELURIAN] = [x for x in st.known[SELURIAN] if x != k]
    flight = Event(turn=world.turn, event_type="scholars_fled", actors=[], description="x", importance=4,
                   region=world.regions[VERDANT].name)
    prov.remember(world, prov.key("seat_flight", world.regions[VERDANT].name), flight)
    world.scholarship.carries = [(VERDANT, ASHARA, THORNWALL, 0)]
    events = T.tick_techniques(world)
    adopted = [e for e in events if e.event_type == "technique_adopted" and e.actors == ["Selurian Republic"]
               and "coinage" in e.description]
    assert adopted, [e.description for e in events]
    assert "learned coinage from scholars fleeing Verdant Plains" in adopted[0].description
    assert flight.event_id in adopted[0].causes
    assert st.counts.get("gained:scholars", 0) >= 1


def test_seats_keep_archive_copies():
    world = _world()
    assert S.archive_copies(world, THORNWALL, VERDANT) == 0
    _seat(world, VERDANT, level=2)
    assert S.archive_copies(world, THORNWALL, VERDANT) == 2
    _seat(world, THORNWOOD, level=1)
    assert S.archive_copies(world, THORNWALL, VERDANT) == 3
    assert S.archive_copies(world, KETHANI, AMBER) == 0
    _seat(world, AMBER, level=3)
    assert S.archive_copies(world, KETHANI, AMBER) == S.SEAT_COPIES_CAP


# --- the bridge signals -----------------------------------------------------------------

def test_seat_pull_and_flight_come_from_persisted_seats_and_reset():
    from chronicler.agent_bridge import build_region_batch
    world = _world()
    si, seat = _seat(world, VERDANT, level=2)
    seat.pull = S.LEVEL_PULL[2]
    batch = build_region_batch(world)
    assert batch.column("seat_pull").to_pylist()[VERDANT] == pytest.approx(S.LEVEL_PULL[2])
    assert not any(batch.column("seat_flight").to_pylist())
    # It falls: flight for FLIGHT_TURNS turns, then nothing.
    seat.fallen_turn, seat.level, seat.pull = world.turn, 0, 0.0
    flags = []
    for _ in range(S.FLIGHT_TURNS + 3):
        world.turn += 1
        cols = build_region_batch(world).to_pydict()
        assert cols["seat_pull"][VERDANT] == 0.0
        flags.append(cols["seat_flight"][VERDANT])
    assert flags == [True] * S.FLIGHT_TURNS + [False] * 3
    # A new seat in the region ends the flight at once.
    seat.fallen_turn = world.turn
    _seat(world, VERDANT, level=1)[1].pull = 0.4
    cols = build_region_batch(world).to_pydict()
    assert cols["seat_flight"][VERDANT] is False and cols["seat_pull"][VERDANT] == pytest.approx(0.4)


def test_a_seat_tick_sets_its_pull_read_by_the_next_batch(monkeypatch):
    _no_draw(monkeypatch, 0.999)
    world = _world()
    _si, seat = _seat(world, VERDANT, level=2)
    _tick(world)
    assert seat.pull == S.LEVEL_PULL[2]
    world.regions[VERDANT].occupied_by = "Selurian Republic"
    world.turn += S.STRIKE_COOLDOWN
    _tick(world)
    assert seat.pull == 0.0, "an occupied seat draws no one"


# --- narration, history, snapshot -------------------------------------------------------

def test_snapshot_history_metrics_and_standing_state(monkeypatch):
    _no_draw(monkeypatch)
    from chronicler.narration_context import standing_state_lines
    world = _world()
    _tick(world)
    snap = S.snapshot_summary(world)
    assert {r["region"] for r in snap["seats"]} == {"Obsidian Shore", "Amber Valley", "Verdant Plains",
                                                    "Ashara Desert"}
    row = next(r for r in snap["seats"] if r["region"] == "Verdant Plains")
    assert row["kind"] == "academy" and row["lord"] == "Thornwall Confederacy" and row["level"] == 1
    assert snap["fallen"] == 0 and snap["counters"]["academies"] == 4
    lines = S.seat_history(world, 0)
    assert "founded turn 40" in lines[0] and "founds the" in lines[1]
    bundle = {"history": [{"turn": 1, "scholarship": snap}]}
    metrics = S.extract_scholarship_metrics([bundle])
    assert metrics["runs"] == 1 and metrics["per_run"]["founded"] == 4 and metrics["peak_seats_mean"] == 4
    assert S.extract_scholarship_metrics([{"history": [{"turn": 1}]}]) == {"runs": 0}
    ev = Event(turn=world.turn, event_type="war", actors=["Thornwall Confederacy"], description="x",
               importance=7, region="Verdant Plains")
    snapshot = TurnSnapshot(turn=world.turn + 1, civ_stats={}, region_control={}, relationships={},
                            scholarship=snap)
    out = standing_state_lines(snapshot, [ev], world)
    seat_line = [line for line in out if line.startswith("Seat of learning")]
    assert seat_line and "The Academy of Verdant Plains (modest academy in Verdant Plains" in seat_line[0]
    assert "kept by its ruler" in seat_line[0]


def test_the_scholars_chronicle_their_seat_and_carry_their_archive(monkeypatch):
    from chronicler import historiography as H
    _no_draw(monkeypatch, 0.999)
    world = _world()
    H.set_historiography_enabled(world, True)
    si, seat = _seat(world, VERDANT, level=1)
    rival, rival_seat = _seat(world, ASHARA, level=2)
    founding = Event(turn=world.turn, event_type="seat_founded", actors=["Thornwall Confederacy"],
                     description="Thornwall founds the Academy of Verdant Plains", importance=5,
                     region="Verdant Plains")
    prov.ensure_id(world, founding)
    world.events_timeline.append(founding)
    seat.history.append((world.turn, "founded", founding.event_id))
    world.turn += 1
    H.observe_turn(world)
    st = H.state_of(world)
    chron = next(c for c in st.chroniclers if c.chronicler_id == f"seat:{si}")
    assert chron.kind == "seat" and chron.name == "the scholars of the Academy of Verdant Plains"
    archive = next(a for a in st.archives if a.owner == chron.chronicler_id)
    assert archive.region == VERDANT and archive.copies == 2
    acc = next(a for a in st.accounts if a.chronicler == chron.chronicler_id)
    assert acc.event_id == founding.event_id and acc.stance == "glory" and not acc.transforms
    # The court tells it too (glory, from SEAT_MIN_IMPORTANCE).
    assert any(a.chronicler == f"court:{THORNWALL}" and a.event_id == founding.event_id for a in st.accounts)
    # The seat falls; its scholars flee with the archive.
    _occupy(world, VERDANT, "Selurian Republic")
    _tick(world)
    world.turn += 1
    H.observe_turn(world)
    assert not chron.active
    assert any(a.chronicler == chron.chronicler_id and a.stance == "disaster" for a in st.accounts)
    assert archive.region == ASHARA and archive.copies == 1
    assert any(loss.cause in ("flight", "sack") for loss in archive.losses)
    exported = H.export(world)
    row = next(c for c in exported["chroniclers"] if c["id"] == chron.chronicler_id)
    assert row["seat"] == si and row["kind"] == "seat"
    assert all("seat" not in c for c in exported["chroniclers"] if c["kind"] != "seat")


def test_seat_events_are_readable_and_weighted():
    from chronicler.narration_context import ROUTINE_TYPES, event_text
    assert "seat_master" in ROUTINE_TYPES and "seat_patron" in ROUTINE_TYPES
    for t in ("seat_founded", "seat_rose", "seat_declined", "seat_fell", "scholars_fled"):
        assert t not in ROUTINE_TYPES
    ev = Event(turn=3, event_type="seat_fell", actors=["X"], importance=6,
               description="The Academy of Y in Y is burned when Z take Y.", region="Y")
    assert event_text(ev) == "The Academy of Y in Y is burned when Z take Y"


# --- runs -----------------------------------------------------------------------------

def test_off_mode_run_founds_seats_and_repeats():
    import chronicler.techniques as T
    from chronicler import historiography as H

    def run():
        world = generate_world(seed=42)
        world.campaigns_enabled = True
        T.set_techniques_enabled(world, True)
        H.set_historiography_enabled(world, True)
        S.set_scholarship_enabled(world, True)
        for _ in range(60):
            _advance(world, 1)
            H.observe_turn(world)
        return world
    a, b = run(), run()
    assert a.model_dump_json() == b.model_dump_json()
    assert a.scholarship.counters["founded"] >= 1
    assert H.state_of(a) == H.state_of(b)


def test_cli_run_writes_the_field_and_analytics_reads_it(tmp_path):
    from chronicler.analytics import generate_report
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    out = tmp_path / "on"
    execute_run(parser.parse_args(["--seed", "42", "--turns", "80", "--civs", "4", "--regions", "8",
                                   "--simulate-only", "--scholarship", "--output", str(out / "chronicle.md"),
                                   "--state", str(out / "state.json")]))
    state = json.loads((out / "state.json").read_text())
    assert "scholarship" in state
    bundle = load_bundle(out / "chronicle_bundle.json")
    assert all("scholarship" in h for h in bundle["history"])
    off = tmp_path / "off"
    execute_run(parser.parse_args(["--seed", "42", "--turns", "3", "--civs", "4", "--regions", "8",
                                   "--simulate-only", "--output", str(off / "chronicle.md"),
                                   "--state", str(off / "state.json")]))
    assert "scholarship" not in json.loads((off / "state.json").read_text())
    assert generate_report(tmp_path)["scholarship"]["runs"] == 1


def test_identity_script_strips_only_the_scholarship_fields(tmp_path):
    spec = importlib.util.spec_from_file_location("scholarship_identity",
                                                  ROOT / "scripts" / "scholarship_identity.py")
    ident = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ident)
    base, new = tmp_path / "base", tmp_path / "new"
    for d in (base, new):
        d.mkdir()
    (base / "state.json").write_text(json.dumps({"turn": 3}))
    (new / "state.json").write_text(json.dumps({"turn": 3, "scholarship": {"seats": []}}))
    assert ident.compare(base, new, inert=True) == (1, [])
    assert len(ident.compare(base, new)[1]) == 1


# --- native hybrid ----------------------------------------------------------------------

def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


@pytest.mark.native
def test_native_seat_pull_signal_is_consumed_and_reset_each_turn(make_world):
    """The region batch carries seat_pull while a seat draws; Rust reads it
    every tick and returns to 0 when the column is absent."""
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    world = make_world(num_civs=2)
    world.agent_mode = "hybrid"
    home, seat_region = world.regions
    home.carrying_capacity = seat_region.carrying_capacity = 60
    home.population, seat_region.population = 40, 20
    home.adjacencies = [seat_region.name]
    seat_region.adjacencies = [home.name]
    civ0, civ1 = world.civilizations
    seat_region.controller = civ0.name
    civ0.regions, civ1.regions = [home.name, seat_region.name], []
    civ0.population, civ1.population = 60, 0
    S.set_scholarship_enabled(world, True)
    world.scholarship.seats.append(Seat(region=1, kind=ACADEMY, name="the Academy", founded_turn=0,
                                        founder=0, lord=0, level=3, pull=1.0))
    bridge = AgentBridge(world, mode="hybrid")
    gates = []
    for turn in range(1, 7):
        world.turn = turn
        if turn == 4:
            S.set_scholarship_enabled(world, False)   # the column disappears
        bridge.tick(world)
        gates.append(bridge._sim.get_migration_driver_stats()["gate_learning"])
    assert all(g > 0 for g in gates[:3]), gates
    assert gates[3:] == [0, 0, 0], gates


@pytest.mark.native
def test_native_hybrid_run_founds_seats(tmp_path):
    _require_native()
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    out = tmp_path / "hyb"
    execute_run(parser.parse_args(["--seed", "42", "--turns", "120", "--civs", "4", "--regions", "8",
                                   "--agents", "hybrid", "--simulate-only", "--scholarship",
                                   "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")]))
    world = WorldState.load(out / "state.json")
    assert world.scholarship.counters["founded"] >= 1
    assert any(s.scholars > 0 for s in world.scholarship.seats)
    bundle = load_bundle(out / "chronicle_bundle.json")
    assert any(h.get("scholarship", {}).get("seats") for h in bundle["history"])
