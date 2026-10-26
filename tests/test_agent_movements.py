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
import math
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler.bundle_codec import load_bundle
import chronicler.agent_movements as M
from chronicler.action_engine import ActionEngine
from chronicler.agent_movements_state import (
    COMMONS, CRUSHED, DISSOLVED, ENDED, FADED, FISCAL, GATHERING, HOME_RULE, INQUISITION, LAPSED,
    LIBERTY, NEGLECT, OPPOSITION, PRESSING, RELIEF, RISING, RULER, SATISFIED, SCHISM, SECEDED,
    SECT, SUPPRESSED, TOLERATION, WON, Movement, MovementState,
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
        self.reforms: list = []
        self.leaders: list = []
        self.foundings: list = []

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

    def set_movement_reforms(self, batch):
        self.reforms.append(batch.to_pydict())

    def queue_movement_leaders(self, ids, roles):
        self.leaders.extend(zip(ids, roles))

    def seed_movement_members(self, batch):
        self.seeds.append(batch.to_pydict())

    def found_movement(self, movement_id, creed, target, region, founder_id, settlement):
        """As ``movements::seed_founding``: the founder, then 15% of the
        region's adults (at least 3) from its aggrieved of the creed."""
        self.foundings.append((movement_id, creed, target, region, founder_id, settlement))
        aggrieved = self.aggrieved.get(region, (0, 0, 0))[creed] if creed < 3 else self.adults
        n = min(aggrieved, max(3, math.ceil(0.15 * self.adults))) + (1 if founder_id else 0)
        return ([region], [n]) if n else ([], [])


def _bridge(world, aggrieved=None, rebels=None, adults=30):
    sim = _Sim(len(world.regions), aggrieved, adults)
    return SimpleNamespace(_sim=sim, last_tick_unrest_by_region=lambda: (rebels or {}, {}))


def _rows(world, members: dict[tuple[int, int], int], adults: int = 30, belief: int | None = None,
          occupation: int = 0):
    """Phase 10 rows: ``adults`` per held region; ``members[(movement index,
    region)]`` of them belong to that movement, boldest first by id. Their
    civ affinity is the region's controller."""
    cols = {k: [] for k in ("id", "region", "age", "movement_id", "boldness", "belief",
                            "civ_affinity", "occupation")}
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
            cols["civ_affinity"].append(world.civilizations.index(civ))
            cols["occupation"].append(occupation)
            next_id += 1
    batch = pa.record_batch({
        "id": pa.array(cols["id"], type=pa.uint32()), "region": pa.array(cols["region"], type=pa.uint16()),
        "age": pa.array(cols["age"], type=pa.uint16()),
        "movement_id": pa.array(cols["movement_id"], type=pa.uint16()),
        "boldness": pa.array(cols["boldness"], type=pa.float32()),
        "belief": pa.array(cols["belief"], type=pa.uint8()),
        "civ_affinity": pa.array(cols["civ_affinity"], type=pa.uint8()),
        "occupation": pa.array(cols["occupation"], type=pa.uint8()),
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
    # generate_world worlds stay off; the CLI, batch and live entry points
    # turn movements on for the worlds they create.
    assert M.DEFAULT_ENABLED_FOR_NEW_WORLDS is True


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
    _tick(world, members={(0, THORNWOOD): 4, (1, VERDANT): 4}, bridge=bridge)
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
    # The founder and the most aggrieved (15% of 30 adults, 5) are enrolled
    # at founding, so the next tick has no founding one-shot.
    assert m.members == 6 and m.member_regions == [[THORNWOOD, 6]] and m.peak_members == 6
    assert m.stronghold == THORNWOOD and m.strength == pytest.approx(6 / 60)
    world.turn += 1
    table = M.movement_table(world).to_pydict()
    assert table["found_region"] == [M.NO_REGION] and table["founder_id"] == [0]
    assert table["appeal"][0] == pytest.approx(M.APPEAL_LEADER * M.IDEA_APPEAL)


class _OldSim(_Sim):
    """A simulator without ``found_movement`` (founders seeded by the next tick)."""

    def __getattribute__(self, name):
        if name == "found_movement":
            raise AttributeError(name)
        return super().__getattribute__(name)


def test_founders_join_at_founding_or_on_the_next_tick_without_the_native_call(monkeypatch):
    monkeypatch.setattr(M, "EMERGE_CHANCE", 1.0)
    monkeypatch.setattr(M, "EMERGE_CHANCE_CAP", 1.0)
    world = _world()
    bridge = _bridge(world, aggrieved={THORNWOOD: (12, 0, 0)})
    events = _tick(world, members={}, bridge=bridge)
    m = world.agent_movements.movements[0]
    assert bridge._sim.foundings == [(1, COMMONS, THORNWALL, THORNWOOD, 0, 0)]
    assert "12 of 30 people there" in events[0].description and m.members == 5
    assert M.snapshot_summary(world)["living"][0]["members"] == 5
    world.turn += 1
    # Resumed on the next turn: the saved founders are re-seeded.
    assert M.movement_seeds(world).to_pydict()["count"] == [5]
    # Nobody free to join: no founding, no event, no counter.
    world2 = _world()
    bridge2 = _bridge(world2, aggrieved={THORNWOOD: (12, 0, 0)})
    bridge2._sim.found_movement = lambda *a: ([], [])
    assert _tick(world2, members={}, bridge=bridge2) == []
    assert world2.agent_movements.movements == []
    assert world2.agent_movements.counters.get("founded", 0) == 0
    # Without the call the table seeds them on the next tick, and resume
    # seeds leave them to it.
    world3 = _world()
    sim3 = _OldSim(len(world3.regions), {THORNWOOD: (12, 0, 0)})
    bridge3 = SimpleNamespace(_sim=sim3, last_tick_unrest_by_region=lambda: ({}, {}))
    _tick(world3, members={}, bridge=bridge3)
    m3 = world3.agent_movements.movements[0]
    assert m3.members == 0 and m3.peak_members == 0
    world3.turn += 1
    assert M.movement_table(world3).to_pydict()["found_region"] == [THORNWOOD]
    assert M.movement_seeds(world3).num_rows == 0
    with pytest.raises(RuntimeError, match="rebuild it"):
        M.send_to_native(world3, SimpleNamespace(_sim=sim3))


def test_a_movement_with_no_member_left_ends_at_once():
    world = _world()
    m = _place(world, member_regions=[[THORNWOOD, 4]], members=4)
    sat = _place(world, creed=SECT, stage=SATISFIED, member_regions=[[VERDANT, 2]], members=2)
    events = _tick(world, members={})
    assert [e.description for e in events] == [
        "the Test 0 fades away", "the Test 2 disbands, its demand met"]
    assert m.stage == ENDED and m.end == FADED and sat.end == WON
    # The founding turn itself is never ended, nor a world without agent rows.
    fresh = _world()
    young = _place(fresh, founded_turn=fresh.turn)
    old = _place(fresh, creed=SECT)
    _tick(fresh, members={})
    assert young.stage != ENDED and old.stage == ENDED
    off = _world()
    kept = _place(off, members=0)
    assert _tick(off) == [] and kept.stage != ENDED


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


def _full_registry_world():
    """Template world whose 16-faith registry is full; faiths 4-8 and 10-15
    have no believer and no temple (9 keeps a temple)."""
    from chronicler.models import Belief
    world = _world()
    faith = world.civilizations[THORNWALL].civ_majority_faith
    used = {b.faith_id for b in world.belief_registry}
    for fid in range(16):
        if fid not in used:
            world.belief_registry.append(Belief(faith_id=fid, name=f"Old Faith {fid}", civ_origin=0,
                                                doctrines=[0, 0, 0, 0, 0]))
    world.regions[AMBER].infrastructure.append(
        Infrastructure(type="temples", builder_civ="Kethani Empire", built_turn=1, faith_id=9))
    for r in world.regions:
        r.majority_belief = faith if r.controller else 0xFF
    return world


def test_a_recycled_faith_slot_never_carries_an_old_reform_or_movement():
    """A toleration in force (or remembered for restoration) and a living
    movement keep their faith's registry slot: a schism never hands their
    number, which the native reform table matches believers by, to an
    unrelated church."""
    from chronicler.agent_movements_state import Reform
    world = _full_registry_world()
    state = world.agent_movements
    m = _restless(world, creed=SECT, stability=60)
    m.grievance = 0.25
    # Faith 4: an old toleration still in force in Kethani.
    state.reforms.append(Reform(kind=TOLERATION, civ=KETHANI, enacted_turn=3, faith=4))
    # Faith 5: a toleration repealed 10 turns ago, which a movement may seek to restore.
    state.reforms.append(Reform(kind=TOLERATION, civ=KETHANI, enacted_turn=3, faith=5,
                                repeal=RULER, repealed_turn=world.turn - 10))
    # Faith 6: a living movement whose members last held it.
    _place(world, target=KETHANI, home=AMBER, faith=6)
    # Faith 7: a toleration lapsed long ago, and an ended movement: free.
    state.reforms.append(Reform(kind=TOLERATION, civ=KETHANI, enacted_turn=1, faith=7,
                                repeal=LAPSED, repealed_turn=5))
    _place(world, target=KETHANI, home=AMBER, faith=7, stage=ENDED, end=FADED)
    events = _tick(world, members={(0, THORNWOOD): 8})
    assert "Schism" in _types(events) and m.end == SCHISM
    assert m.schism_to == 7
    assert M.reform_table(world).to_pydict()["faith"] == [4]


def test_a_faith_referenced_only_by_reforms_is_not_free():
    from chronicler.agent_movements_state import Reform
    world = _full_registry_world()
    free = [4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15]
    world.agent_movements.reforms.extend(
        Reform(kind=TOLERATION, civ=KETHANI, enacted_turn=3, faith=f) for f in free)
    m = _restless(world, creed=SECT, stability=60)
    m.grievance = 0.25
    assert _types(_tick(world, members={(0, THORNWOOD): 8})) == ["movement_rising"]
    assert len(world.belief_registry) == 16


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


# --- lasting reforms -----------------------------------------------------------------

def _governed(world):
    from chronicler.governance_runtime import set_governance_enabled
    from chronicler.governance_state import CivGovernance
    set_governance_enabled(world, True)
    for civ in world.civilizations:
        civ.governance = CivGovernance()
    return world


def _grant(world, monkeypatch, creed=COMMONS, members=9, rows=None, **fields):
    """A movement against Thornwall whose demand is granted this tick."""
    monkeypatch.setattr(M, "grant_chance", lambda t, m, civ: 1.0)
    m = _place(world, creed=creed, **fields)
    i = len(world.agent_movements.movements) - 1
    return m, _tick(world, members={(i, THORNWOOD): members}, **(rows or {}))


def test_a_grant_enacts_a_lasting_reform_and_its_institution(monkeypatch):
    world = _governed(_world())
    civ = world.civilizations[THORNWALL]
    m, events = _grant(world, monkeypatch)
    state = world.agent_movements
    assert m.reform == 0 and len(state.reforms) == 1
    r = state.reforms[0]
    assert (r.kind, r.civ, r.regions, r.movement) == (RELIEF, THORNWALL, [], 0)
    assert (r.institution, r.founded_institution) == ("commons_management", True)
    grant = next(e for e in events if e.event_type == "movement_reform")
    assert r.event_id == grant.event_id and "poor relief becomes law under Commons Management" in grant.description
    gov = civ.governance
    assert [i.institution_type for i in gov.institutions] == ["commons_management"]
    assert gov.institutions[0].enacted_turn == world.turn and gov.institutions[0].opposing_faction == "cultural"
    assert gov.institutions[0].enforcement_cost == pytest.approx(0.75 * len(civ.regions))
    assert gov.institution_log[-1] == [world.turn, "commons_management", "enacted"]
    assert M.reform_table(world).to_pydict() == {
        "creed": [COMMONS], "civ": [THORNWALL], "region": [M.NO_REGION], "faith": [M.NO_FAITH]}
    # Another commons grant against the same ruler extends the reform in force.
    m2 = _place(world)
    world.turn += 1
    _tick(world, members={(1, THORNWOOD): 9})
    assert m2.stage == SATISFIED and m2.reform == 0 and len(state.reforms) == 1
    assert state.counters["enacted"] == 1 and state.counters["extended"] == 1


def test_the_reform_institution_runs_in_the_governance_runtime(monkeypatch):
    world = _governed(_world())
    _grant(world, monkeypatch)
    monkeypatch.setattr(M, "REPEAL_RULER_HARSH", 0.0)   # a succession falls in these turns
    monkeypatch.setattr(M, "REPEAL_RULER", 0.0)
    world.turn += 1   # the tick ran in turn 30's Phase 10; the run goes on with turn 31
    _advance(world, 3)
    gov = world.civilizations[THORNWALL].governance
    assert "commons_management" in {i.institution_type for i in gov.institutions}
    assert gov.last_institution_enforcement_cost == pytest.approx(0.75 * 2)
    assert world.agent_movements.reforms[0].repeal == 0


def test_a_reform_falls_with_its_institution(monkeypatch):
    for kind, why in (("collapsed", NEGLECT), ("repealed", OPPOSITION)):
        world = _governed(_world())
        _grant(world, monkeypatch)
        gov = world.civilizations[THORNWALL].governance
        world.turn += 1
        gov.institutions = []
        gov.institution_log.append([world.turn, "commons_management", kind])
        events = _tick(world, members={})
        r = world.agent_movements.reforms[0]
        assert r.repeal == why and r.repealed_turn == world.turn
        repeal = next(e for e in events if e.event_type == "reform_repealed")
        assert repeal.causes == [r.event_id] and r.repeal_event_id == repeal.event_id
        assert M.reform_table(world).num_rows == 0 and world.agent_movements.counters["repealed"] == 1


def test_a_new_ruler_may_repeal_once_per_reign(monkeypatch):
    world = _governed(_world())
    _grant(world, monkeypatch)
    civ = world.civilizations[THORNWALL]
    r = world.agent_movements.reforms[0]
    monkeypatch.setattr(M, "REPEAL_RULER", 0.0)
    world.turn += 1
    civ.leader.name, civ.leader.reign_start, civ.leader.trait = "King Mild", world.turn, "cautious"
    _tick(world, members={})
    assert r.repeal == 0 and r.ruler == "King Mild"
    monkeypatch.setattr(M, "REPEAL_RULER", 1.0)
    world.turn += 1
    _tick(world, members={})
    assert r.repeal == 0      # judged once per reign
    monkeypatch.setattr(M, "REPEAL_RULER_HARSH", 1.0)
    world.turn += 1
    civ.leader.name, civ.leader.reign_start, civ.leader.trait = "King Harsh", world.turn, "zealous"
    events = _tick(world, members={})
    assert r.repeal == RULER
    assert "King Harsh of Thornwall Confederacy repeals the poor relief" in [e.description for e in events]
    # The institution the grant enacted goes with it.
    assert civ.governance.institutions == []
    assert civ.governance.institution_log[-1] == [world.turn, "commons_management", "repealed"]


def test_relief_without_an_institution_pays_upkeep_until_the_treasury_fails(monkeypatch):
    world = _world()
    _grant(world, monkeypatch)
    civ = world.civilizations[THORNWALL]
    r = world.agent_movements.reforms[0]
    assert r.institution == "" and not r.founded_institution
    world.turn += 1
    before = civ.treasury
    _tick(world, members={})
    due = math.ceil(M.RELIEF_UPKEEP * len(civ.regions))
    assert civ.treasury == before - due and world.agent_movements.counters["upkeep"] == due
    civ.treasury = 0
    for _ in range(M.ARREARS_TURNS):
        world.turn += 1
        events = _tick(world, members={})
    assert r.repeal == FISCAL and "reform_repealed" in _types(events)
    # Opposition: a dominant merchant faction has it repealed.
    other = _world()
    _grant(other, monkeypatch)
    monkeypatch.setattr(M, "REPEAL_FACTION", 1.0)
    other.civilizations[THORNWALL].factions.influence[FactionType.MERCHANT] = 0.7
    other.turn += 1
    events = _tick(other, members={})
    assert other.agent_movements.reforms[0].repeal == OPPOSITION
    assert any("merchant faction" in e.description for e in events)


def test_home_rule_charters_the_city_and_lapses_with_the_region(monkeypatch):
    from chronicler.cities_state import MARKET_RIGHTS, NO_CHARTER, City, CityState
    world = _world()
    world.cities = CityState(cities=[City(settlement_id=7, region=THORNWOOD, name="Thorncross",
                                          founded_turn=1, founder=THORNWALL, lord=THORNWALL)])
    m, events = _grant(world, monkeypatch, creed=LIBERTY)
    r = world.agent_movements.reforms[0]
    city = world.cities.cities[0]
    assert (r.kind, r.regions, r.cities, city.charter) == (HOME_RULE, [THORNWOOD], [7], MARKET_RIGHTS)
    charter = next(e for e in events if e.event_type == "city_charter")
    assert charter.causes == [r.event_id] and city.history[-1][1] == "charter"
    assert M.reform_table(world).to_pydict() == {
        "creed": [LIBERTY], "civ": [THORNWALL], "region": [THORNWOOD], "faith": [M.NO_FAITH]}
    # The military faction has it repealed; the charter goes with it.
    monkeypatch.setattr(M, "REPEAL_FACTION", 1.0)
    world.civilizations[THORNWALL].factions.influence[FactionType.MILITARY] = 0.7
    world.turn += 1
    _tick(world, members={})
    assert r.repeal == OPPOSITION and city.charter == NO_CHARTER
    # Home rule lapses (no grievance) when the realm loses the region.
    other = _world()
    _grant(other, monkeypatch, creed=LIBERTY)
    other.regions[THORNWOOD].controller = "Kethani Empire"
    other.turn += 1
    events = M.tick_agent_movements(other, [], phase10=None)
    assert other.agent_movements.reforms[0].repeal == LAPSED and "reform_lapsed" in _types(events)
    assert other.agent_movements.counters["lapsed"] == 1 and other.agent_movements.counters["repealed"] == 0


def test_toleration_ends_the_inquisition_and_falls_to_a_new_one(monkeypatch):
    from chronicler.governance_state import GovernanceInstitution

    def inquisition(turn):
        return GovernanceInstitution(institution_type="holy_inquisition", enacted_turn=turn,
                                     opposing_faction="cultural")

    world = _governed(_world())
    gov = world.civilizations[THORNWALL].governance
    gov.institutions.append(inquisition(world.turn - 5))
    m, events = _grant(world, monkeypatch, creed=SECT, rows={"belief": 0})
    r = world.agent_movements.reforms[0]
    assert (r.kind, r.faith, r.institution) == (TOLERATION, 0, "")
    grant = next(e for e in events if e.event_type == "movement_reform")
    assert grant.description.endswith("is tolerated in the realm and the Holy Inquisition is abolished")
    assert gov.institutions == [] and gov.institution_log[-1] == [world.turn, "holy_inquisition", "repealed"]
    assert M.reform_table(world).to_pydict() == {
        "creed": [SECT], "civ": [THORNWALL], "region": [M.NO_REGION], "faith": [0]}
    assert not r.church and M.reform_name(world, r).startswith("the toleration of the ")
    world.turn += 1
    _tick(world, members={})
    assert r.repeal == 0
    # A sect of the ruler's own faith wins the reform of its church.
    church = _world()
    m3, events = _grant(church, monkeypatch, creed=SECT)
    r3 = church.agent_movements.reforms[0]
    faith = church.civilizations[THORNWALL].civ_majority_faith
    assert r3.church and r3.faith == faith
    assert M.reform_name(church, r3) == f"the reform of the {M._faith_name(church, faith)}"
    assert M.snapshot_summary(church)["reforms"][0]["church"] is True
    # The clergy enact it again: the toleration ends.
    world.turn += 1
    gov.institutions.append(inquisition(world.turn - 1))
    events = _tick(world, members={})
    assert r.repeal == INQUISITION and any("Holy Inquisition" in e.description for e in events)


def test_a_repeal_raises_a_movement_for_its_restoration(monkeypatch):
    world = _world()
    m, _ = _grant(world, monkeypatch)
    state = world.agent_movements
    m.stage, m.end, m.ended_turn = ENDED, WON, world.turn
    monkeypatch.setattr(M, "REPEAL_RULER_HARSH", 1.0)
    monkeypatch.setattr(M, "EMERGE_CHANCE_CAP", 1.0)
    monkeypatch.setattr(M, "EMERGE_CHANCE", 1.0)
    world.turn += 1
    civ = world.civilizations[THORNWALL]
    civ.leader.name, civ.leader.reign_start, civ.leader.trait = "King Harsh", world.turn, "zealous"
    bridge = _bridge(world, aggrieved={THORNWOOD: (12, 0, 0)})
    events = _tick(world, members={}, bridge=bridge)
    r = state.reforms[0]
    assert r.repeal == RULER
    founded = next(e for e in events if e.event_type == "movement_founded")
    new = state.movements[-1]
    assert new.restores == 0 and new.home_region == THORNWOOD   # the creed cooldown is waived
    assert "the restoration of the poor relief" in founded.description
    assert r.repeal_event_id in founded.causes
    # Without a repeal the cooldown holds.
    calm = _world()
    m2, _ = _grant(calm, monkeypatch)
    m2.stage, m2.end, m2.ended_turn = ENDED, WON, calm.turn
    calm.turn += 1
    events = _tick(calm, members={}, bridge=_bridge(calm, aggrieved={THORNWOOD: (12, 0, 0)}))
    assert "movement_founded" not in _types(events)
    # Its grant restores the reform.
    new.founded_turn = world.turn - 10
    world.turn += 1
    events = _tick(world, members={(1, THORNWOOD): 9})
    grant = next(e for e in events if e.event_type == "movement_reform")
    assert "the poor relief is restored" in grant.description and r.repeal_event_id in grant.causes
    assert state.reforms[1].restores == 0 and state.counters["restored"] == 1
    assert M._restoration(world, state, THORNWALL, COMMONS, THORNWOOD, world.regions[THORNWOOD]) == -1


# --- leaders ---------------------------------------------------------------------------

def test_a_pressing_movement_raises_its_boldest_member_to_lead(monkeypatch):
    world = _world()
    civ = world.civilizations[THORNWALL]
    m = _place(world, creed=SECT, demands=1, last_demand=world.turn, stage=PRESSING)
    bridge = _bridge(world)
    _tick(world, members={(0, THORNWOOD): 9}, bridge=bridge)
    first = 91   # the first agent of Thornwood in the rows, the boldest member there
    assert bridge._sim.leaders == [(first, M.LEADER_ROLE_PROPHET)] and m.leader_candidate == first
    world.turn += 1
    _tick(world, members={(0, THORNWOOD): 9}, bridge=bridge)
    assert len(bridge._sim.leaders) == 1          # waiting for the promotion
    gp = GreatPerson(name="Brother Aldo", role="prophet", trait="zealous", civilization=civ.name,
                     origin_civilization=civ.name, born_turn=world.turn, source="agent", agent_id=first)
    civ.great_persons.append(gp)
    world.turn += 1
    events = _tick(world, members={(0, THORNWOOD): 9}, bridge=bridge)
    assert m.leader == "Brother Aldo" and m.leader_agent == first and m.leader_candidate == 0
    lead = next(e for e in events if e.event_type == "movement_leader")
    assert lead.description == "Brother Aldo rises to lead the Test 2 in Thornwood"
    assert gp.region == "Thornwood" and gp.deeds[-1].text == "Rose to lead the Test 2"
    assert M.movement_table(world).to_pydict()["appeal"][0] == pytest.approx(
        M.appeal(m, True), rel=1e-6)
    assert M.snapshot_summary(world)["living"][0]["leader"] == "Brother Aldo"
    # A soldier of a commons movement is raised as a general; small movements raise no one.
    other = _world()
    _place(other, demands=1, last_demand=other.turn, stage=PRESSING)
    b2 = _bridge(other)
    _tick(other, members={(0, THORNWOOD): 9}, bridge=b2, occupation=1)
    assert b2._sim.leaders == [(first, M.LEADER_ROLE_GENERAL)]
    small = _world()
    _place(small, demands=1, last_demand=small.turn, stage=PRESSING)
    b3 = _bridge(small)
    _tick(small, members={(0, THORNWOOD): 5}, bridge=b3)
    assert b3._sim.leaders == []


def test_a_secession_crowns_its_leader():
    world = _world()
    civ = world.civilizations[THORNWALL]
    civ.stability = 20
    gp = GreatPerson(name="Captain Varo", role="general", trait="bold", civilization=civ.name,
                     origin_civilization=civ.name, born_turn=world.turn, base_name="Varo")
    civ.great_persons.append(gp)
    m = _place(world, creed=LIBERTY, grievance=0.5, demands=2, stage=PRESSING, leader="Captain Varo")
    _tick(world, members={(0, THORNWOOD): 12})
    world.turn += 1
    n = len(world.civilizations)
    events = _tick(world, members={(0, THORNWOOD): 12}, bridge=_bridge(world, rebels={THORNWOOD: 6}))
    new = world.civilizations[n]
    assert new.leader.throne_name == "Varo" and new.leader.name.endswith(" Varo")
    assert new.leader.trait == "bold" and gp.fate == "ascended" and not gp.active
    assert gp not in civ.great_persons and gp in world.retired_persons
    secession = next(e for e in events if e.event_type == "secession")
    assert f"Captain Varo takes its throne as {new.leader.name}" in secession.description


def _death_bridge(*persons):
    """An agent bridge holding only the named-character registry."""
    import sys
    from unittest.mock import MagicMock
    from chronicler.dynasties import Dynasty, DynastyRegistry
    stub = "chronicler_agents" not in sys.modules
    if stub:
        sys.modules["chronicler_agents"] = MagicMock()
    try:
        from chronicler.agent_bridge import AgentBridge
    finally:
        if stub:
            sys.modules.pop("chronicler_agents", None)
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {gp.agent_id: gp.name for gp in persons}
    bridge.gp_by_agent_id = {gp.agent_id: gp for gp in persons}
    bridge.dynasty_registry = DynastyRegistry()
    founder = persons[0]
    bridge.dynasty_registry.dynasties.append(Dynasty(
        dynasty_id=1, founder_id=founder.agent_id, founder_name=founder.name,
        civ_id=founder.civilization, members=[gp.agent_id for gp in persons]))
    return bridge


def _native_death(agent_id: int, turn: int, region: int):
    from chronicler.models import AgentEventRecord
    return AgentEventRecord(turn=turn, agent_id=agent_id, event_type="death", region=region,
                            target_region=region, civ_affinity=0, occupation=1)


def test_a_crowned_founder_dies_a_natural_death_later():
    """Ascension is a transition, not a death: the founder who left the civ
    rosters for a throne still dies when their agent dies, and their house
    ends with them."""
    from chronicler.historical_context import AsOf, character_as_of
    world = _world()
    civ = world.civilizations[THORNWALL]
    civ.stability = 20
    gp = GreatPerson(name="Captain Varo", role="general", trait="bold", civilization=civ.name,
                     origin_civilization=civ.name, born_turn=world.turn, base_name="Varo",
                     source="agent", agent_id=4242)
    civ.great_persons.append(gp)
    _place(world, creed=LIBERTY, grievance=0.5, demands=2, stage=PRESSING, leader="Captain Varo")
    _tick(world, members={(0, THORNWOOD): 12})
    world.turn += 1
    _tick(world, members={(0, THORNWOOD): 12}, bridge=_bridge(world, rebels={THORNWOOD: 6}))
    crowned = world.turn
    assert gp.fate == "ascended" and gp.alive and gp in world.retired_persons
    bridge = _death_bridge(gp)
    world.turn += 20
    events = bridge._process_deaths([_native_death(4242, world.turn, THORNWOOD)], world)
    assert (gp.alive, gp.active, gp.death_turn, gp.fate) == (False, False, world.turn, "ascended")
    assert [e.event_type for e in events] == ["character_death", "dynasty_extinct"]
    assert events[0].actors == ["Captain Varo", civ.name]
    assert "died in Thornwood" in events[0].description
    assert bridge.dynasty_registry.dynasties[0].extinct
    assert world.retired_persons.count(gp) == 1
    # The record keeps both: ascended (not active) after the throne, alive
    # until the death.
    reign = character_as_of(gp, AsOf.after(crowned + 5), observed=False)
    assert (reign.status, reign.active, reign.alive) == ("ascended", False, True)
    later = character_as_of(gp, AsOf.after(world.turn), observed=False)
    assert (later.status, later.alive) == ("ascended", False)
    # A second report of the same death changes nothing.
    assert bridge._process_deaths([_native_death(4242, world.turn, THORNWOOD)], world) == []


def test_a_roster_death_is_reported_once_and_unchanged():
    world = _world()
    civ = world.civilizations[THORNWALL]
    gp = GreatPerson(name="Elder Ro", role="general", trait="bold", civilization=civ.name,
                     origin_civilization=civ.name, born_turn=1, source="agent", agent_id=77)
    civ.great_persons.append(gp)
    bridge = _death_bridge(gp)
    events = bridge._process_deaths([_native_death(77, world.turn, THORNWOOD)], world)
    assert gp.fate == "dead" and gp not in civ.great_persons and gp in world.retired_persons
    assert [e.event_type for e in events] == ["character_death", "dynasty_extinct"]
    assert world.retired_persons.count(gp) == 1


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


def test_new_worlds_default_on_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()

    def args(out, *extra, turns=3):
        return parser.parse_args(["--seed", "42", "--turns", str(turns), "--regions", "8", "--civs", "4",
                                  "--agents", "off", "--simulate-only", *extra,
                                  "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    fresh = tmp_path / "fresh"
    execute_run(args(fresh))
    state = json.loads((fresh / "state.json").read_text())
    assert state["agent_movements"]["movements"] == []   # nothing founds without agents
    bundle = load_bundle(fresh / "chronicle_bundle.json")
    assert all("agent_movements" in h for h in bundle["history"])
    off = tmp_path / "off"
    execute_run(args(off, "--no-agent-movements"))
    assert "agent_movements" not in json.loads((off / "state.json").read_text())
    from chronicler.analytics import generate_report
    assert generate_report(tmp_path)["agent_movements"]["runs"] == 1
    # A saved world keeps its setting on resume, either way, with no flag.
    for run, kept in ((fresh, True), (off, False)):
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
def test_native_founders_are_enrolled_at_founding():
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    world = _native_world()
    M.set_agent_movements_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    world.turn = 1
    bridge.tick(world)
    regions, _ = bridge._sim.get_movement_stats()
    batch = pa.record_batch(regions)
    adults = batch.column("adults").to_pylist()
    region = max(range(len(world.regions)), key=lambda r: world.regions[r].population)
    aggrieved = batch.column("aggrieved_commons").to_pylist()[region]
    snap = pa.record_batch(bridge._sim.get_snapshot())
    founder = next(i for i, r in zip(snap.column("id").to_pylist(), snap.column("region").to_pylist())
                   if r == region)
    civ = world.civ_index_map[world.regions[region].controller]
    m = Movement(name="the League", creed=COMMONS, founded_turn=1, home_region=region, target=civ,
                 regions_reached=[region], leader_agent=founder)
    assert M._seed_founders(M._Tick(world, None, bridge, None), 0, m, adults)
    world.agent_movements.movements.append(m)
    # The founder joins whatever their grievance; then the most aggrieved.
    expected = 1 + min(aggrieved, max(3, math.ceil(0.15 * adults[region])))
    assert m.members == expected == _snapshot_members(bridge, 1)
    assert m.member_regions == [[region, expected]] and m.stronghold == region
    assert m.peak_members == expected and m.strength > 0
    # The next tick founds nothing more.
    world.turn = 2
    assert M.movement_table(world).to_pydict()["found_region"] == [M.NO_REGION]
    bridge.tick(world)
    _, movements = bridge._sim.get_movement_stats()
    assert pa.record_batch(movements).column("founded").to_pylist() == [0]
    # Nobody free to join (the founder taken, no one aggrieved): nothing enrolled.
    if aggrieved == 0:
        other = Movement(name="the Other", creed=COMMONS, founded_turn=2, home_region=region,
                         target=civ, regions_reached=[region], leader_agent=founder)
        assert not M._seed_founders(M._Tick(world, None, bridge, None), 1, other, adults)


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
    bundle = load_bundle(out / "chronicle_bundle.json")
    assert any(h.get("agent_movements", {}).get("living") for h in bundle["history"])
