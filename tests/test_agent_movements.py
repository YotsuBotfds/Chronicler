"""Movements grounded in people (``chronicler.agent_movements``, ``--agent-movements``).

Decisions are exercised on the template world (seed 42) with Phase 10 agent
rows built as the native snapshot carries them (``movement_id`` and the
columns the layer reads) and a stand-in for the native census, so they run
without the extension; the tick is called directly with ``acc=None``.
Native tests run the real extension.
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
from chronicler.action_engine import ActionEngine
from chronicler.agent_movements_state import (
    COMMONS, CRUSHED, DISSOLVED, ENDED, FADED, GATHERING, LIBERTY, PRESSING, RISING, SATISFIED,
    SCHISM, SECEDED, SECT, SUPPRESSED, WON, Movement, MovementState,
)
from chronicler.models import FactionType, GreatPerson, Infrastructure, TurnSnapshot, WorldState
from chronicler.simulation import run_turn
from chronicler.turn_artifacts import AgentRows, Phase10Inputs, Stamp
from chronicler.world_gen import generate_world

ROOT = Path(__file__).resolve().parents[1]
# Template seed 42: Thornwall Confederacy (civ 2) holds Verdant Plains (2,
# capital) and Thornwood (4); Kethani Empire (1) holds Amber Valley (5,
# capital) and Frostholm Tundra (0).
FROST, VERDANT, DESERT, THORNWOOD, AMBER = 0, 2, 3, 4, 5
KETHANI, THORNWALL = 1, 2


def _world() -> WorldState:
    world = generate_world(seed=42)
    M.set_agent_movements_enabled(world, True)
    world.turn = 30
    return world


class _Sim:
    """Stand-in for the native simulator's movement surface."""

    def __init__(self, nreg: int, aggrieved: dict | None = None, adults: int = 30) -> None:
        self.nreg = nreg
        self.aggrieved = aggrieved or {}
        self.adults = adults
        self.deaths: list[int] = []
        self.tables: list = []
        self.seeds: list = []

    def get_movement_stats(self):
        rows = {"region_id": [], "adults": [], "aggrieved_commons": [], "aggrieved_liberty": [],
                "aggrieved_sect": []}
        for r in range(self.nreg):
            g = self.aggrieved.get(r, (0, 0, 0))
            rows["region_id"].append(r)
            rows["adults"].append(self.adults)
            for k, v in zip(("aggrieved_commons", "aggrieved_liberty", "aggrieved_sect"), g):
                rows[k].append(v)
        movements = pa.record_batch({"movement_id": pa.array([], type=pa.uint16())})
        return pa.record_batch({k: pa.array(v, type=pa.uint32() if k != "region_id" else pa.uint16())
                                for k, v in rows.items()}), movements

    def queue_targeted_deaths(self, ids):
        self.deaths.extend(ids)

    def set_movement_table(self, batch):
        self.tables.append(batch.to_pydict())

    def seed_movement_members(self, batch):
        self.seeds.append(batch.to_pydict())


def _bridge(world, aggrieved=None, rebels=None, adults=30):
    sim = _Sim(len(world.regions), aggrieved, adults)
    return SimpleNamespace(_sim=sim, last_tick_unrest_by_region=lambda: (rebels or {}, {}))


def _rows(world, members: dict[tuple[int, int], int], adults: int = 30, belief: int | None = None):
    """Phase 10 rows: ``adults`` per held region; ``members[(movement index,
    region)]`` of them belong to that movement, boldest first by id."""
    cols = {k: [] for k in ("id", "region", "age", "movement_id", "boldness", "belief")}
    next_id = 1
    for ri, region in enumerate(world.regions):
        if region.controller is None:
            continue
        joined = [(i, n) for (i, r), n in sorted(members.items()) if r == ri]
        tags = [i + 1 for i, n in joined for _ in range(n)]
        civ = world.civ_map[region.controller]
        for k in range(adults):
            cols["id"].append(next_id)
            cols["region"].append(ri)
            cols["age"].append(30)
            cols["movement_id"].append(tags[k] if k < len(tags) else 0)
            cols["boldness"].append(0.9 - 0.01 * k)
            cols["belief"].append(civ.civ_majority_faith if belief is None else belief)
            next_id += 1
    batch = pa.record_batch({
        "id": pa.array(cols["id"], type=pa.uint32()), "region": pa.array(cols["region"], type=pa.uint16()),
        "age": pa.array(cols["age"], type=pa.uint16()),
        "movement_id": pa.array(cols["movement_id"], type=pa.uint16()),
        "boldness": pa.array(cols["boldness"], type=pa.float32()),
        "belief": pa.array(cols["belief"], type=pa.uint8()),
    })
    return Phase10Inputs(source_turn=world.turn,
                         agents=AgentRows(stamp=Stamp(world.turn, "phase10_entry"), batch=batch),
                         named_agents=None, economy=None, deaths=())


def _tick(world, members=None, bridge=None, **kw):
    phase10 = _rows(world, members, **kw) if members is not None else None
    events = M.tick_agent_movements(world, [], acc=None, phase10=phase10, agent_bridge=bridge)
    world.events_timeline.extend(events)
    return events


def _types(events) -> list[str]:
    return [e.event_type for e in events]


def _place(world, creed=COMMONS, target=THORNWALL, home=THORNWOOD, **fields) -> Movement:
    fields.setdefault("founded_turn", world.turn - 10)
    fields.setdefault("stage_turn", world.turn - 10)
    m = Movement(name=f"the Test {creed}", creed=creed, home_region=home, target=target,
                 regions_reached=[home], **fields)
    world.agent_movements.movements.append(m)
    return m


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


# --- switch and persistence ------------------------------------------------------

def test_off_worlds_omit_the_dormant_fields():
    world = generate_world(seed=42)
    assert world.agent_movements is None and not M.agent_movements_enabled(world)
    assert "agent_movements" not in json.loads(world.model_dump_json())
    assert "agent_movements" not in json.loads(TurnSnapshot(
        turn=1, civ_stats={}, region_control={}, relationships={}).model_dump_json())
    assert M.tick_agent_movements(world, []) == []
    assert M.movement_table(world).num_rows == 0
    M.send_to_native(world, None)   # nothing to send, nothing touched
    assert M.DEFAULT_ENABLED_FOR_NEW_WORLDS is False


def test_enable_disable_and_state_round_trip():
    world = _world()
    _place(world, members=7, member_regions=[[THORNWOOD, 7]])
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert loaded.agent_movements == world.agent_movements
    M.set_agent_movements_enabled(world, True)   # idempotent
    assert world.agent_movements.movements
    M.set_agent_movements_enabled(world, False)
    assert world.agent_movements is None


def test_old_saves_without_movements_load(tmp_path):
    world = generate_world(seed=7)
    path = tmp_path / "state.json"
    world.save(path)
    assert "agent_movements" not in json.loads(path.read_text())
    assert WorldState.load(path).agent_movements is None


# --- emergence ---------------------------------------------------------------------

def test_a_movement_is_founded_where_grievances_cluster(monkeypatch):
    world = _world()
    monkeypatch.setattr(M, "EMERGE_CHANCE", 1.0)
    monkeypatch.setattr(M, "EMERGE_CHANCE_CAP", 1.0)
    bridge = _bridge(world, aggrieved={THORNWOOD: (12, 0, 0)})
    events = _tick(world, members={}, bridge=bridge)
    assert _types(events) == ["movement_founded"]
    m = world.agent_movements.movements[0]
    assert (m.creed, m.target, m.home_region, m.stage) == (COMMONS, THORNWALL, THORNWOOD, GATHERING)
    assert "12 of 30" in events[0].description and events[0].region == "Thornwood"
    assert world.agent_movements.counters["founded"] == 1
    # The ruler faces one commons movement at a time, and not again at once.
    world.turn += 1
    assert "movement_founded" not in _types(_tick(world, members={(0, THORNWOOD): 5}, bridge=bridge))
    # Too few aggrieved, or too early in the run: no founding.
    quiet = _world()
    assert _tick(quiet, members={}, bridge=_bridge(quiet, aggrieved={THORNWOOD: (4, 0, 0)})) == []
    early = _world()
    early.turn = 5
    assert _tick(early, members={}, bridge=_bridge(early, aggrieved={THORNWOOD: (12, 0, 0)})) == []


def test_caps_per_ruler_and_the_creed_cooldown(monkeypatch):
    world = _world()
    monkeypatch.setattr(M, "EMERGE_CHANCE", 1.0)
    monkeypatch.setattr(M, "EMERGE_CHANCE_CAP", 1.0)
    _place(world, creed=COMMONS)
    _place(world, creed=SECT)
    bridge = _bridge(world, aggrieved={THORNWOOD: (0, 12, 0), AMBER: (0, 0, 12)})
    _tick(world, members={}, bridge=bridge)
    new = world.agent_movements.movements[2:]
    assert [(m.creed, m.target) for m in new] == [(SECT, KETHANI)]   # Thornwall is at its cap
    # An ended movement of the creed blocks the creed against that ruler for a while.
    world2 = _world()
    _place(world2, creed=LIBERTY, stage=ENDED, end=FADED, ended_turn=world2.turn - 5)
    _tick(world2, members={}, bridge=_bridge(world2, aggrieved={THORNWOOD: (0, 12, 0)}))
    assert len(world2.agent_movements.movements) == 1


def test_a_great_person_carries_and_leads_and_an_idea_is_carried(monkeypatch):
    from chronicler.models import Movement as Idea
    world = _world()
    monkeypatch.setattr(M, "EMERGE_CHANCE", 1.0)
    monkeypatch.setattr(M, "EMERGE_CHANCE_CAP", 1.0)
    civ = world.civilizations[THORNWALL]
    gp = GreatPerson(name="Brother Ansel", role="prophet", trait="zealous", civilization=civ.name,
                     origin_civilization=civ.name, born_turn=1, region="Thornwood", agent_id=77)
    civ.great_persons.append(gp)
    world.movements.append(Idea(id="movement_0", origin_civ=civ.name, origin_turn=1,
                                value_affinity="faith", adherents={civ.name: 0}))
    events = _tick(world, members={}, bridge=_bridge(world, aggrieved={THORNWOOD: (0, 0, 9)}))
    m = world.agent_movements.movements[0]
    assert m.creed == SECT and m.leader == "Brother Ansel" and m.leader_agent == 77
    assert m.idea == "movement_0" and "Brother Ansel founds" in events[0].description
    world.turn += 1
    table = M.movement_table(world).to_pydict()
    assert table["found_region"] == [THORNWOOD] and table["founder_id"] == [77]
    assert table["appeal"][0] == pytest.approx(M.APPEAL_LEADER * M.IDEA_APPEAL)
    world.turn += 1
    assert M.movement_table(world).to_pydict()["found_region"] == [M.NO_REGION]


# --- observation, pressure, demands ---------------------------------------------

def test_members_strength_stronghold_and_spread_from_the_rows():
    world = _world()
    m = _place(world)
    events = _tick(world, members={(0, THORNWOOD): 9, (0, VERDANT): 3})
    assert m.members == 12 and m.member_regions == [[VERDANT, 3], [THORNWOOD, 9]]
    assert m.strength == pytest.approx(12 / 60) and m.stronghold == THORNWOOD
    assert m.stronghold_share == pytest.approx(0.3)
    assert "movement_spread" in _types(events) and VERDANT in m.regions_reached


def test_pressure_raises_the_creeds_ally_faction():
    world = _world()
    civ = world.civilizations[THORNWALL]
    before = civ.factions.influence[FactionType.CULTURAL]
    _place(world, demands=1, last_demand=world.turn)
    _tick(world, members={(0, THORNWOOD): 6})
    assert civ.factions.influence[FactionType.CULTURAL] > before


def test_a_granted_demand_is_a_reform_with_relief_on_the_next_ticks(monkeypatch):
    world = _world()
    monkeypatch.setattr(M, "grant_chance", lambda t, m, civ: 1.0)
    civ = world.civilizations[THORNWALL]
    treasury = civ.treasury
    m = _place(world)
    events = _tick(world, members={(0, THORNWOOD): 9})
    assert _types(events) == ["movement_demand", "movement_reform"]
    assert m.stage == SATISFIED and m.reform_turn == world.turn and m.grievance == 0.0
    assert civ.treasury == treasury - int(M.REFORM_TREASURY + M.REFORM_TREASURY_PER_STRENGTH * m.strength)
    assert events[1].causes == [events[0].event_id]
    world.turn += 1
    assert M.movement_table(world).to_pydict()["relief_age"] == [1]
    world.turn += M.RELIEF_TURNS
    assert M.movement_table(world).to_pydict()["relief_age"] == [M.NO_RELIEF]
    # No demand before the movement has gathered for a while.
    young = _world()
    _place(young, founded_turn=young.turn - 2)
    assert "movement_demand" not in _types(_tick(young, members={(0, THORNWOOD): 9}))


def test_grant_chance_reads_trait_weakness_strength_factions_and_legitimacy():
    world = _world()
    civ = world.civilizations[THORNWALL]
    m = _place(world, strength=0.1)
    t = M._Tick(world, None, None, None)
    civ.leader.trait = "stubborn"
    harsh = M.grant_chance(t, m, civ)
    civ.leader.trait = "cautious"
    mild = M.grant_chance(t, m, civ)
    assert mild == pytest.approx(harsh + 2 * M.GRANT_TRAIT)
    civ.stability = 10
    assert M.grant_chance(t, m, civ) == pytest.approx(mild + M.GRANT_WEAK)
    m.strength = 0.3
    assert M.grant_chance(t, m, civ) > mild + M.GRANT_WEAK
    civ.factions.influence[FactionType.MILITARY] = 0.6
    assert M.suppress_chance(m, civ) > M.SUPPRESS_BASE


def test_a_refusal_raises_the_grievance(monkeypatch):
    world = _world()
    monkeypatch.setattr(M, "grant_chance", lambda t, m, civ: 0.0)
    monkeypatch.setattr(M, "suppress_chance", lambda m, civ: 0.0)
    civ = world.civilizations[THORNWALL]
    stability = civ.stability
    m = _place(world)
    assert _types(_tick(world, members={(0, THORNWOOD): 9})) == ["movement_demand", "movement_refused"]
    assert m.grievance == M.REFUSAL_GRIEVANCE and m.stage == PRESSING
    assert civ.stability == stability - M.REFUSAL_STABILITY


def test_a_crackdown_kills_the_boldest_and_reuses_persecution_and_martyrdom(monkeypatch):
    world = _world()
    monkeypatch.setattr(M, "grant_chance", lambda t, m, civ: 0.0)
    monkeypatch.setattr(M, "suppress_chance", lambda m, civ: 1.0)
    bridge = _bridge(world)
    m = _place(world, creed=SECT)
    events = _tick(world, members={(0, THORNWOOD): 20}, bridge=bridge)
    assert _types(events) == ["movement_demand", "movement_crackdown"]
    # Thornwood's rows are ids 91-120 (held regions in index order), boldest first.
    assert bridge._sim.deaths == [91, 92]
    assert m.martyrs == 2 and m.stage == SUPPRESSED and m.crackdown_region == THORNWOOD
    assert world.regions[THORNWOOD].martyrdom_boost > 0
    assert world.regions[THORNWOOD].persecution_intensity == 0.0   # the builder's field is untouched
    world.turn += 1
    table = M.movement_table(world).to_pydict()
    assert table["crackdown_region"] == [THORNWOOD] and table["stage"] == [SUPPRESSED]
    world.turn += 1
    assert M.movement_table(world).to_pydict()["crackdown_region"] == [M.NO_REGION]
    # Suppressed movements make no demand until they recover.
    assert "movement_demand" not in _types(_tick(world, members={(0, THORNWOOD): 18}, bridge=bridge))


# --- risings, secession, schism -------------------------------------------------

def _restless(world, creed=LIBERTY, stability=20):
    civ = world.civilizations[THORNWALL]
    civ.stability = stability
    return _place(world, creed=creed, grievance=0.5, demands=2, stage=PRESSING)


def test_a_rising_then_secession_for_a_liberty_movement():
    from chronicler.governance_runtime import set_governance_enabled
    world = _world()
    set_governance_enabled(world, True)
    from chronicler.governance_state import CivGovernance
    civ = world.civilizations[THORNWALL]
    civ.governance = CivGovernance()
    m = _restless(world)
    events = _tick(world, members={(0, THORNWOOD): 12})
    assert _types(events) == ["movement_rising"]
    assert m.stage == RISING and m.rising_region == THORNWOOD and m.rising_members == 12
    assert civ.governance.defeat_turns == [world.turn]
    world.turn += 1
    assert M.movement_table(world).to_pydict()["rising_region"] == [THORNWOOD]
    n = len(world.civilizations)
    events = _tick(world, members={(0, THORNWOOD): 12}, bridge=_bridge(world, rebels={THORNWOOD: 6}))
    assert "secession" in _types(events)
    new = world.civilizations[n]
    assert new.name == "Free Thornwood" and new.regions == ["Thornwood"]
    assert world.regions[THORNWOOD].controller == new.name and "Thornwood" not in civ.regions
    assert world.relationships[civ.name][new.name].disposition.value == "hostile"
    assert m.stage == ENDED and m.end == SECEDED and m.successor == n
    secession = next(e for e in events if e.event_type == "secession")
    assert secession.actors == [civ.name, new.name]
    assert world.agent_movements.counters["secessions"] == 1


def test_a_rising_against_a_strong_ruler_is_crushed_or_wins_a_concession(monkeypatch):
    for chance, outcome in ((0.0, "movement_crushed"), (1.0, "movement_concession")):
        world = _world()
        monkeypatch.setattr(M, "CONCESSION_CHANCE", chance)
        m = _restless(world, stability=80)
        _tick(world, members={(0, THORNWOOD): 12})
        world.turn += 1
        bridge = _bridge(world, rebels={THORNWOOD: 2})
        events = _tick(world, members={(0, THORNWOOD): 12}, bridge=bridge)
        assert outcome in _types(events)
        if chance == 0.0:
            assert m.stage == SUPPRESSED and len(bridge._sim.deaths) == 2   # twice the share
        else:
            assert m.stage == SATISFIED
        assert world.regions[THORNWOOD].controller == "Thornwall Confederacy"


def test_a_sect_of_the_rulers_faith_breaks_away_through_the_religion_path():
    world = _world()
    civ = world.civilizations[THORNWALL]
    faith = civ.civ_majority_faith
    m = _restless(world, creed=SECT, stability=60)
    m.grievance = 0.25
    faiths = len(world.belief_registry)
    events = _tick(world, members={(0, THORNWOOD): 8})
    assert _types(events)[:1] == ["Schism"] and "movement_end" in _types(events)
    assert len(world.belief_registry) == faiths + 1
    new = world.belief_registry[-1]
    assert m.end == SCHISM and m.successor == new.faith_id and m.schism_from == faith
    region = world.regions[THORNWOOD]
    assert (region.schism_convert_from, region.schism_convert_to) == (faith, new.faith_id)
    world.turn += 1
    table = M.movement_table(world).to_pydict()
    assert table["convert_from"] == [faith] and table["convert_to"] == [new.faith_id]
    assert table["stage"] == [SATISFIED]
    world.turn += 1
    assert M.movement_table(world).num_rows == 0
    # A sect of another faith rises instead.
    other = _world()
    other.belief_registry = list(world.belief_registry)
    m2 = _restless(other, creed=SECT, stability=60)
    m2.grievance = 0.25
    assert _types(_tick(other, members={(0, THORNWOOD): 8}, belief=0)) == ["movement_rising"]


def test_narration_gets_the_recorded_chain_of_a_rising(monkeypatch):
    """The narrator's "because" chain for a rising runs back through the
    refusal to the demand: every movement event carries its causes."""
    from chronicler.curator import CauseGraph, build_causal_chain
    world = _world()
    monkeypatch.setattr(M, "grant_chance", lambda t, m, civ: 0.0)
    monkeypatch.setattr(M, "suppress_chance", lambda m, civ: 0.0)
    m = _place(world, creed=LIBERTY, grievance=0.25)
    world.civilizations[THORNWALL].stability = 60
    _tick(world, members={(0, THORNWOOD): 12})
    world.turn += M.DEMAND_INTERVAL
    events = _tick(world, members={(0, THORNWOOD): 12})
    assert m.stage == RISING and _types(events) == ["movement_rising"]
    graph = CauseGraph(world.events_timeline)
    j = next(k for k, e in enumerate(world.events_timeline) if e.event_type == "movement_rising")
    chain = [step.event_type for step in build_causal_chain(graph, j).steps]
    assert chain == ["movement_demand", "movement_refused", "movement_rising"]


def test_a_schism_in_a_full_registry_takes_the_place_of_a_vanished_faith():
    from chronicler.models import Belief
    world = _world()
    civ = world.civilizations[THORNWALL]
    faith = civ.civ_majority_faith
    used = {b.faith_id for b in world.belief_registry}
    for fid in range(16):
        if fid not in used:
            world.belief_registry.append(Belief(faith_id=fid, name=f"Old Faith {fid}", civ_origin=0,
                                                doctrines=[0, 0, 0, 0, 0]))
    # Faith 9 still has a temple; faiths 4-8 and 10-15 have no one. The sect
    # takes the lowest free id's place.
    world.regions[AMBER].infrastructure.append(
        Infrastructure(type="temples", builder_civ="Kethani Empire", built_turn=1, faith_id=9))
    for r in world.regions:
        r.majority_belief = faith if r.controller else 0xFF
    m = _restless(world, creed=SECT, stability=60)
    m.grievance = 0.25
    position = next(k for k, b in enumerate(world.belief_registry) if b.faith_id == 4)
    events = _tick(world, members={(0, THORNWOOD): 8})
    assert "Schism" in _types(events) and m.end == SCHISM
    assert len(world.belief_registry) == 16 and m.schism_to == 4
    assert world.belief_registry[position].faith_id == 4
    assert world.belief_registry[position].name.endswith("(Reformed)")
    assert "Old Faith 4" in next(e for e in events if e.event_type == "Schism").description
    # With every faith held or referenced, the sect rises instead.
    full = _world()
    full.belief_registry = [b.model_copy() for b in world.belief_registry]
    for k, region in enumerate(full.regions):
        region.infrastructure.append(
            Infrastructure(type="temples", builder_civ="x", built_turn=1, faith_id=4 + k))
    for k, c in enumerate(full.civilizations):
        c.previous_majority_faith = 12 + k
    m2 = _restless(full, creed=SECT, stability=60)
    m2.grievance = 0.25
    assert _types(_tick(full, members={(0, THORNWOOD): 8})) == ["movement_rising"]


# --- decay -------------------------------------------------------------------------

def test_movements_fade_win_or_dissolve():
    world = _world()
    faded = _place(world)
    won = _place(world, stage=SATISFIED, reform_turn=world.turn - 5)
    for _ in range(M.FADE_TURNS):
        _tick(world, members={(0, THORNWOOD): 2, (1, VERDANT): 1})
        world.turn += 1
    assert (faded.stage, faded.end) == (ENDED, FADED)
    assert (won.end, world.agent_movements.counters["won"]) == (WON, 1)
    gone = _world()
    m = _place(gone, target=KETHANI, home=AMBER)
    gone.civilizations[KETHANI].regions = []
    _tick(gone, members={})
    assert m.end == DISSOLVED
    crushed = _world()
    c = _place(crushed, stage=SUPPRESSED, stage_turn=crushed.turn)
    for _ in range(M.FADE_TURNS):
        _tick(crushed, members={(0, THORNWOOD): 1})
        crushed.turn += 1
    assert c.end == CRUSHED and crushed.agent_movements.counters["broken"] == 1


def test_a_dead_leader_becomes_a_martyr_once():
    world = _world()
    civ = world.civilizations[THORNWALL]
    gp = GreatPerson(name="Elder Ro", role="general", trait="bold", civilization=civ.name,
                     origin_civilization=civ.name, born_turn=1, region="Thornwood")
    civ.great_persons.append(gp)
    m = _place(world, leader="Elder Ro")
    assert M.appeal(m, M._leader_alive(world, m)) == pytest.approx(M.APPEAL_LEADER)
    gp.alive = False
    assert "movement_martyr" in _types(_tick(world, members={(0, THORNWOOD): 6}))
    world.turn += 1
    assert "movement_martyr" not in _types(_tick(world, members={(0, THORNWOOD): 6}))
    assert m.martyrs == 1


# --- native table, seeds, reports ---------------------------------------------

def test_the_table_and_seeds_come_from_persisted_state():
    world = _world()
    _place(world, member_regions=[[THORNWOOD, 7]])
    _place(world, stage=ENDED, end=FADED, member_regions=[[VERDANT, 2]])
    _place(world, founded_turn=world.turn - 1, member_regions=[[VERDANT, 4]])
    table = M.movement_table(world)
    assert table.schema.field("movement_id").type == pa.uint16()
    assert table.to_pydict()["movement_id"] == [1, 3]
    seeds = M.movement_seeds(world).to_pydict()
    assert seeds == {"movement_id": [1], "region": [THORNWOOD], "count": [7]}
    bridge = _bridge(world)
    M.send_to_native(world, bridge)
    M.send_to_native(world, bridge)
    assert len(bridge._sim.seeds) == 1 and len(bridge._sim.tables) == 2


def test_snapshot_history_and_metrics(monkeypatch):
    world = _world()
    monkeypatch.setattr(M, "grant_chance", lambda t, m, civ: 1.0)
    _place(world)
    _tick(world, members={(0, THORNWOOD): 9})
    summary = M.snapshot_summary(world)
    assert summary["living"][0]["stage"] == "satisfied" and summary["counters"]["reforms"] == 1
    lines = M.movement_history(world, 0)
    assert lines[0].startswith("the Test 0 (commons)") and any("reform:" in x for x in lines)
    bundles = [{"history": [{"turn": 1, "agent_movements": summary}]}, {"history": [{"turn": 1}]}]
    metrics = M.extract_movement_metrics(bundles)
    assert metrics["runs"] == 1 and metrics["per_run"]["reforms"] == 1


# --- the switch in a run ---------------------------------------------------------------

def test_feature_off_never_runs_movement_code(monkeypatch):
    import chronicler.contact_ledger as cl

    def boom(*a, **k):
        raise AssertionError("movement code ran with the switch off")

    for name in ("tick_agent_movements", "send_to_native", "movement_table", "snapshot_summary",
                 "movement_seeds"):
        monkeypatch.setattr(M, name, boom)
    world = generate_world(seed=42)
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, True)
    _advance(world, 20)


def test_off_mode_movements_keep_their_politics_and_repeat():
    """Without agents nothing recruits; a world that carries a movement (a
    resumed or forked world) keeps its saved members and its politics run."""
    def run():
        world = generate_world(seed=42)
        world.campaigns_enabled = True
        M.set_agent_movements_enabled(world, True)
        world.agent_movements.movements.append(Movement(
            name="the Sons of Thornwood", creed=LIBERTY, founded_turn=0, home_region=THORNWOOD,
            target=THORNWALL, members=9, member_regions=[[THORNWOOD, 9]], strength=0.25,
            stronghold=THORNWOOD, stronghold_share=0.3, regions_reached=[THORNWOOD]))
        return _advance(world, 40)
    a, b = run(), run()
    assert a.model_dump_json() == b.model_dump_json()
    m = a.agent_movements.movements[0]
    assert m.demands >= 1 and m.history[0][1] == "demand"


def test_cli_flag_gate_forwarding_and_live_default():
    from chronicler.main import _build_parser
    parser = _build_parser()
    assert parser.parse_args([]).agent_movements is None
    assert parser.parse_args(["--agent-movements"]).agent_movements is True
    assert parser.parse_args(["--no-agent-movements"]).agent_movements is False
    spec = importlib.util.spec_from_file_location("m53b", ROOT / "scripts" / "m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._agent_movements_args(argparse.Namespace(agent_movements=True)) == ["--agent-movements"]
    assert m53b._agent_movements_args(argparse.Namespace(agent_movements=False)) == ["--no-agent-movements"]
    assert m53b._agent_movements_args(argparse.Namespace(agent_movements=None)) == []
    assert "set_agent_movements_enabled" in (ROOT / "src" / "chronicler" / "live.py").read_text()


def test_new_worlds_default_off_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()

    def args(out, *extra, turns=3):
        return parser.parse_args(["--seed", "42", "--turns", str(turns), "--regions", "8", "--civs", "4",
                                  "--agents", "off", "--simulate-only", *extra,
                                  "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    fresh = tmp_path / "fresh"
    execute_run(args(fresh))
    assert "agent_movements" not in json.loads((fresh / "state.json").read_text())
    on = tmp_path / "on"
    execute_run(args(on, "--agent-movements"))
    state = json.loads((on / "state.json").read_text())
    assert state["agent_movements"]["movements"] == []   # nothing founds without agents
    bundle = json.loads((on / "chronicle_bundle.json").read_text())
    assert all("agent_movements" in h for h in bundle["history"])
    from chronicler.analytics import generate_report
    assert generate_report(tmp_path)["agent_movements"]["runs"] == 1
    for run, kept in ((fresh, False), (on, True)):
        resumed = args(run, turns=5)
        resumed.resume = str(run / "state.json")
        resumed.state = str(run / "resumed.json")
        execute_run(resumed)
        assert ("agent_movements" in json.loads((run / "resumed.json").read_text())) is kept


def test_identity_script_strips_only_the_movement_fields(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "agent_movements_identity", ROOT / "scripts" / "agent_movements_identity.py")
    ident = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ident)
    base, new = tmp_path / "base", tmp_path / "new"
    for d in (base, new):
        d.mkdir()
    (base / "state.json").write_text(json.dumps({"turn": 3}))
    (new / "state.json").write_text(json.dumps({"turn": 3, "agent_movements": {"movements": []}}))
    bundle = {"metadata": {"generated_at": "x"}, "history": [{"turn": 1}], "world_state": {"turn": 3}}
    (base / "chronicle_bundle.json").write_text(json.dumps(bundle))
    bundle["history"][0]["agent_movements"] = {"living": []}
    bundle["world_state"]["agent_movements"] = {}
    bundle["metadata"]["generated_at"] = "y"
    (new / "chronicle_bundle.json").write_text(json.dumps(bundle))
    assert ident.compare(base, new, inert=True) == (2, [])
    assert len(ident.compare(base, new)[1]) == 2


# --- native ----------------------------------------------------------------------------

def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


def _native_world():
    world = generate_world(seed=42)
    world.agent_mode = "hybrid"
    return world


def _snapshot_members(bridge, movement_id: int) -> int:
    snap = pa.record_batch(bridge._sim.get_snapshot())
    return sum(1 for v in snap.column("movement_id").to_pylist() if v == movement_id)


@pytest.mark.native
def test_native_switch_off_sends_nothing_and_the_snapshot_column_is_zero():
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    from chronicler.bridge_contract import validate_snapshot_schema
    world = _native_world()
    bridge = AgentBridge(world, mode="hybrid")
    for turn in range(1, 4):
        world.turn = turn
        bridge.tick(world)
    snap = pa.record_batch(bridge._sim.get_snapshot())
    validate_snapshot_schema(snap.schema)
    assert set(snap.column("movement_id").to_pylist()) == {0}
    assert bridge._sim.movements_enabled() is False


@pytest.mark.native
def test_native_founding_seeds_members_and_an_ended_movement_releases_them():
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    world = _native_world()
    M.set_agent_movements_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    world.turn = 1
    bridge.tick(world)
    region = max(range(len(world.regions)), key=lambda r: world.regions[r].population)
    civ = world.civ_index_map[world.regions[region].controller]
    world.agent_movements.movements.append(Movement(
        name="the Seekers", creed=SECT, founded_turn=1, home_region=region, target=civ,
        regions_reached=[region]))
    regions, _ = bridge._sim.get_movement_stats()
    aggrieved = pa.record_batch(regions).column("aggrieved_sect").to_pylist()[region]
    world.turn = 2
    bridge.tick(world)
    founded = _snapshot_members(bridge, 1)
    assert founded >= min(3, aggrieved), (founded, aggrieved)
    _, movements = bridge._sim.get_movement_stats()
    assert pa.record_batch(movements).column("founded").to_pylist() == [founded]
    world.turn = 3
    bridge.tick(world)   # the founding is not repeated
    _, movements = bridge._sim.get_movement_stats()
    assert pa.record_batch(movements).column("founded").to_pylist() == [0]
    m = world.agent_movements.movements[0]
    m.stage, m.end, m.ended_turn = ENDED, FADED, 3
    world.turn = 4
    bridge.tick(world)
    assert _snapshot_members(bridge, 1) == 0


@pytest.mark.native
def test_native_crackdown_memories_are_written_once():
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    world = _native_world()
    M.set_agent_movements_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    world.turn = 1
    bridge.tick(world)
    region = max(range(len(world.regions)), key=lambda r: world.regions[r].population)
    civ = world.civ_index_map[world.regions[region].controller]
    m = Movement(name="the League", creed=COMMONS, founded_turn=0, home_region=region, target=civ,
                 regions_reached=[region], member_regions=[[region, 6]])
    world.agent_movements.movements.append(m)
    bridge._movements_seeded = False   # re-seed the saved members, as after a resume
    world.turn = 2
    bridge.tick(world)
    snap = pa.record_batch(bridge._sim.get_snapshot())
    members = [i for i, v in zip(snap.column("id").to_pylist(), snap.column("movement_id").to_pylist()) if v == 1]
    assert len(members) == 6

    def persecution_memories():
        mem = pa.record_batch(bridge._sim.get_all_memories())
        ids = set(members)
        return sum(1 for a, e, t in zip(mem.column("agent_id").to_pylist(), mem.column("event_type").to_pylist(),
                                        mem.column("turn").to_pylist()) if a in ids and e == 3 and t >= 2)
    before = persecution_memories()
    m.crackdown_turn, m.crackdown_region = 2, region
    world.turn = 3
    bridge.tick(world)
    after = persecution_memories()
    assert after > before
    world.turn = 4
    bridge.tick(world)
    assert persecution_memories() == after


@pytest.mark.native
def test_native_hybrid_run_founds_movements(tmp_path):
    _require_native()
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    out = tmp_path / "hyb"
    args = parser.parse_args(["--seed", "44", "--turns", "80", "--civs", "4", "--regions", "8",
                              "--agents", "hybrid", "--simulate-only", "--agent-movements",
                              "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    execute_run(args)
    world = WorldState.load(out / "state.json")
    assert world.agent_movements.counters["founded"] >= 1
    assert max(m.peak_members for m in world.agent_movements.movements) >= 3
    bundle = json.loads((out / "chronicle_bundle.json").read_text())
    assert any(h.get("agent_movements", {}).get("living") for h in bundle["history"])
