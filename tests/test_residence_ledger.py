"""X1 residence ledger (``--residence-ledger``): offline contract (no native extension).

A small fake stands in for the post-tick native pool (snapshot, trips,
relationships) on the war fixtures' five-region world (Avalon 0, Brook 1,
Crag 2, Dun 3, Edge 4); each constructed turn applies moves and deaths as the
native tick would, records the migration events with their drivers, and runs
the livelihoods Phase 10 hook. Every state here is constructed. Native hybrid
runs: ``tests/test_residence_ledger_native.py``; the read guard:
``tests/test_residence_ledger_guard.py``.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import pytest

from chronicler import livelihoods as LV
from chronicler import residence_ledger as RL
from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
from chronicler.feature_catalog import REQUIREMENTS
from chronicler.ffi_constants import BOND_FRIEND, BOND_MARRIAGE
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState
from chronicler.main import _build_parser
from chronicler.models import MIGRATION_DRIVER_NAMES, NO_MIGRATION_DRIVER, AgentEventRecord
from chronicler.residence_ledger_state import (
    ANCHOR_TURNS, ANCHORS, CLOSURES, COUNTERS, REGION_KEYS, REHOME_TURNS, TOTAL_KEYS, ResidenceLedgerState,
)
from tests.war_fixtures import place_army, war_world

ROOT = Path(__file__).resolve().parents[1]
AVALON, BROOK, CRAG, DUN, EDGE = range(5)


def parse(*argv):
    return _build_parser().parse_args(list(argv))


class Column:
    def __init__(self, values):
        self.values = values

    def to_pylist(self):
        return list(self.values)


class Batch:
    def __init__(self, rows, columns):
        self.rows, self.columns = rows, columns

    def column(self, name):
        assert name in self.columns, name
        return Column([r[name] for r in self.rows])


_SNAPSHOT = ("id", "region", "origin_region", "displacement_turn", "age", "parent_id_0", "parent_id_1")


class FakeSim:
    """People (id -> region, birth region, age, parents), trips and bonds."""

    def __init__(self, *, relationships_allowed=True):
        self.people: dict[int, dict] = {}
        self.trips: set[int] = set()
        self.bonds: list[tuple[int, int, int]] = []
        self.relationships_allowed = relationships_allowed
        self.relationship_reads = 0

    def add(self, aid, region, *, origin=None, age=30, parents=(0, 0)):
        self.people[aid] = {"id": aid, "region": region, "origin_region": region if origin is None else origin,
                            "displacement_turn": 0, "age": age, "parent_id_0": parents[0], "parent_id_1": parents[1]}

    def get_snapshot(self):
        return Batch([dict(self.people[i]) for i in sorted(self.people)], _SNAPSHOT)

    def trip_agent_ids(self):
        return sorted(i for i in self.trips if i in self.people)

    def get_all_relationships(self):
        if not self.relationships_allowed:
            raise AssertionError("the writer must not read relationships (separation is on demand)")
        self.relationship_reads += 1
        rows = [{"agent_id": a, "target_id": b, "bond_type": k, "sentiment": 50} for a, b, k in self.bonds] + \
               [{"agent_id": b, "target_id": a, "bond_type": k, "sentiment": 50} for a, b, k in self.bonds]
        return Batch(rows, ("agent_id", "target_id", "bond_type", "sentiment"))


class FakeBridge:
    def __init__(self, sim):
        self._sim = sim


def _code(driver):
    return NO_MIGRATION_DRIVER if driver is None else MIGRATION_DRIVER_NAMES.index(driver)


def _world(*extra, turn=1):
    world = war_world()
    world.agent_mode = "hybrid"
    world.turn = turn
    LV.configure_livelihoods(world, parse("--residence-ledger", *extra), agent_mode="hybrid")
    return world


def _state(world) -> ResidenceLedgerState:
    return world.livelihoods.residence_ledger


def step(world, sim, moves=(), deaths=(), before=None, *, advance=True):
    """One constructed turn: moves (id, from, to, driver name or None) and
    deaths as the native tick applies them, then the Phase 10 hook."""
    for aid, frm, to, driver in moves:
        assert sim.people[aid]["region"] == frm, (aid, sim.people[aid]["region"], frm)
        sim.people[aid]["region"] = to
        sim.people[aid]["displacement_turn"] = 5
        world.agent_events_raw.append(AgentEventRecord(world.turn, aid, "migration", frm, to, 0, 0,
                                                       migration_driver=_code(driver)))
    for aid in deaths:
        sim.people.pop(aid)
        world.agent_events_raw.append(AgentEventRecord(world.turn, aid, "death", 0, 0, 0, 0))
    if before is not None:
        before()
    LV.phase10(world, agent_bridge=FakeBridge(sim))
    frame = _state(world).frame
    if advance:
        world.turn += 1
        for p in sim.people.values():
            p["displacement_turn"] = max(0, p["displacement_turn"] - 1)
    return frame


def _row(world, aid):
    return _state(world).rows.get(aid)


def _region(frame, region):
    return next((r for r in frame["regions"] if r["region"] == region), None)


def _events(world, kind=None):
    return [e for e in _state(world).events or [] if kind is None or e["kind"] == kind]


def _population(sim, n=6, region=AVALON):
    for aid in range(1, n + 1):
        sim.add(aid, region)


# --- registry and switch ---------------------------------------------------------------

def test_the_switch_sits_after_a3_before_d2_with_cli_catalog_and_manifest_keys():
    i = LIVELIHOODS_SWITCHES.index("residence_ledger")
    assert LIVELIHOODS_SWITCHES[i + 1:] == ("attribution_records", "wealth_accounting")
    assert LIVELIHOODS_SWITCHES.index("workshop_economics") < i
    keys = LV.LIVELIHOODS_ARG_KEYS
    assert keys[keys.index("residence_ledger") + 1:] == ("attribution_records", "wealth_accounting")
    assert "residence_ledger" not in LV.LIVELIHOODS_CHOICES                 # no modes: record only
    assert REQUIREMENTS["residence_ledger"] == ({"agents": ["hybrid"]},)
    assert "residence_ledger" in SIMULATION_ARG_KEYS
    default = parse()
    assert default.residence_ledger is None
    assert "residence_ledger" not in simulation_config(default)           # feature-off manifests keep their bytes
    assert simulation_config(parse("--residence-ledger"))["residence_ledger"] is True
    assert simulation_config(parse("--no-residence-ledger"))["residence_ledger"] is False
    assert LV.livelihoods_arguments(parse("--residence-ledger")) == ["--residence-ledger"]
    assert LV.livelihoods_arguments(parse("--no-residence-ledger")) == ["--no-residence-ledger"]
    assert "residence_ledger" in LivelihoodsState.model_fields


@pytest.mark.parametrize("mode", ["off", "demographics-only", "shadow"])
def test_the_switch_requires_hybrid_also_when_saved(mode):
    world = war_world()
    world.agent_mode = mode
    with pytest.raises(ValueError, match="--residence-ledger requires --agents hybrid"):
        LV.configure_livelihoods(world, parse("--residence-ledger"), agent_mode=mode)
    saved = _world()
    saved.agent_mode = mode
    with pytest.raises(ValueError, match="pass --no-residence-ledger to end it"):
        LV.configure_livelihoods(saved, parse(), agent_mode=mode)
    LV.configure_livelihoods(saved, parse("--no-residence-ledger"), agent_mode="hybrid")
    assert not RL.residence_ledger_active(saved) and _state(saved).counters["switched_off"] == 1


def test_off_worlds_have_no_state_and_no_key():
    world = war_world()
    world.agent_mode = "hybrid"
    LV.configure_livelihoods(world, parse("--food-allocation"), agent_mode="hybrid")
    assert world.livelihoods.residence_ledger is None
    assert "residence_ledger" not in world.livelihoods.model_dump(mode="json")
    assert "residence_ledger" not in LV.livelihoods_feature_flags(world)
    assert "residence_ledger" not in LV.livelihoods_snapshot_fields(world).get("livelihoods", {})


def test_driver_sets_are_c1bs_and_the_declared_constants():
    from chronicler.quarantine_rules import FLIGHT_DRIVERS, HUNGER_DRIVERS
    assert RL._FLIGHT == frozenset(FLIGHT_DRIVERS) and RL._HUNGER == frozenset(HUNGER_DRIVERS)
    assert (REHOME_TURNS, ANCHOR_TURNS) == (20, 5)
    assert ANCHORS == ("war", "famine", "persecution", "none")
    assert CLOSURES == ("returned", "resettled", "died", "pool_reset", "unobserved_gap")
    # The famine onset value the anchor reads is the one ecology sets.
    ecology = (ROOT / "src" / "chronicler" / "ecology.py").read_text(encoding="utf-8")
    assert f"region.famine_cooldown = {RL.FAMINE_ONSET_COOLDOWN}\n" in ecology


# --- definitions (audit 11.1) ------------------------------------------------------------

def test_first_observation_sets_home_to_residence_and_a_newborn_to_its_birth_region():
    world, sim = _world(), FakeSim()
    _population(sim, 3)
    sim.add(4, CRAG)
    frame = step(world, sim)
    assert {aid: (r.home, r.res, r.first_seen) for aid, r in _state(world).rows.items()} == {
        1: (AVALON, AVALON, 1), 2: (AVALON, AVALON, 1), 3: (AVALON, AVALON, 1), 4: (CRAG, CRAG, 1)}
    assert frame["observed_from"] == 1 and frame["totals"]["new_rows"] == 4 and frame["totals"]["newborn_rows"] == 0
    sim.add(10, DUN, origin=DUN, age=0)                     # born in Dun in this turn's tick
    frame = step(world, sim)
    row = _row(world, 10)
    assert (row.home, row.res, row.home_since, row.first_seen) == (DUN, DUN, 2, 2)
    assert frame["totals"]["newborn_rows"] == 1


def test_a_flight_or_hunger_move_from_home_opens_a_spell_and_a_voluntary_one_rehomes():
    world, sim = _world(), FakeSim()
    _population(sim, 4)
    step(world, sim)
    frame = step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory"), (2, AVALON, BROOK, "opp_food"),
                                    (3, AVALON, BROOK, "wage"), (4, AVALON, CRAG, "opp_satisfaction")])
    s1, s2 = _row(world, 1).spell, _row(world, 2).spell
    assert (s1.cause, s1.origin, s1.start, s1.moves) == ("flight", AVALON, 2, 1)
    assert (s2.cause, s2.origin) == ("hunger", AVALON)
    assert _row(world, 1).home == AVALON and _row(world, 1).res == BROOK
    for aid, region in ((3, BROOK), (4, CRAG)):                          # voluntary and unclassified: migrants
        row = _row(world, aid)
        assert row.spell is None and row.home == region and row.home_since == 2 and row.res == region
    t = frame["totals"]
    assert (t["moves"], t["moves_flight"], t["moves_hunger"], t["moves_voluntary"], t["moves_other"]) == (4, 1, 1, 1, 1)
    assert (t["opened"], t["rehomed"], t["displaced"], t["displaced_flight"], t["displaced_hunger"]) == (2, 2, 2, 1, 1)
    av, br = _region(frame, AVALON), _region(frame, BROOK)
    assert (av["departures"], av["departures_flight"], av["opened"], av["displaced_from"]) == (4, 1, 2, 2)
    assert (br["arrivals"], br["arrivals_displaced"], br["displaced"], br["residents"]) == (3, 2, 2, 3)
    assert [e["id"] for e in _events(world, "opened")] == [1, 2]


def test_a_follower_carries_the_leads_driver_and_is_displaced_with_it():
    """Natively a household follower's event carries its lead's driver; the
    ledger reads the event's driver, so the follower opens the same spell."""
    world, sim = _world(), FakeSim()
    _population(sim, 2)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "persecution"), (2, AVALON, BROOK, "persecution")])
    assert _row(world, 1).spell.cause == _row(world, 2).spell.cause == "flight"


def test_return_closes_onward_flight_keeps_and_a_voluntary_onward_move_resettles():
    world, sim = _world(), FakeSim()
    _population(sim, 3)
    step(world, sim)
    step(world, sim, moves=[(a, AVALON, BROOK, "famine_memory") for a in (1, 2, 3)])
    frame = step(world, sim, moves=[(1, BROOK, AVALON, "opp_satisfaction"), (2, BROOK, CRAG, "safety_need"),
                                    (3, BROOK, DUN, "wage")])
    assert _row(world, 1).spell is None and _row(world, 1).home == AVALON            # returned home
    assert _row(world, 2).spell.moves == 2 and _row(world, 2).home == AVALON           # still displaced
    assert _row(world, 3).spell is None and _row(world, 3).home == DUN                 # resettled where it chose
    assert {(e["id"], e["kind"], e.get("by")) for e in _events(world) if e["kind"] != "opened"} == {
        (1, "returned", None), (3, "resettled", "move")}
    t = frame["totals"]
    assert (t["returned"], t["resettled"], t["resettled_by_move"], t["displaced"]) == (1, 1, 1, 1)
    assert _region(frame, AVALON)["returned"] == 1 and _region(frame, DUN)["resettled"] == 1
    returned = _events(world, "returned")[0]
    assert (returned["start"], returned["length"], returned["origin"]) == (2, 1, AVALON)


def test_a_spell_resettles_after_rehome_turns_at_one_residence():
    world, sim = _world(), FakeSim()
    _population(sim, 1)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "conquest_memory")])                     # turn 2
    for _ in range(REHOME_TURNS - 1):
        step(world, sim)
    assert world.turn == 2 + REHOME_TURNS and _row(world, 1).spell is not None           # 19 turns there
    frame = step(world, sim)
    row = _row(world, 1)
    assert row.spell is None and row.home == BROOK and row.home_since == 2 + REHOME_TURNS
    assert _events(world, "resettled")[0]["by"] == "rehome_turns" and frame["totals"]["resettled_by_move"] == 0
    assert _events(world, "resettled")[0]["length"] == REHOME_TURNS


def test_a_death_closes_the_spell_and_drops_the_row():
    world, sim = _world(), FakeSim()
    _population(sim, 2)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, CRAG, "battle_memory")])
    frame = step(world, sim, deaths=[1, 2])
    assert not _state(world).rows
    assert (frame["totals"]["died"], frame["totals"]["deaths"]) == (1, 2)
    assert _region(frame, CRAG)["died_displaced"] == 1 and _region(frame, AVALON)["deaths"] == 1
    assert _state(world).counters["closed_died"] == 1


# --- anchors -------------------------------------------------------------------------------

def _depart(world, sim, aid, region, before=None):
    step(world, sim, moves=[(aid, region, BROOK if region != BROOK else AVALON, "safety_need")], before=before)
    return _row(world, aid).spell


def test_pre_tick_war_and_famine_anchor_the_same_turn():
    world, sim = _world(), FakeSim()
    for aid, region in ((1, CRAG), (2, DUN), (3, EDGE)):
        sim.add(aid, region)
    for _ in range(ANCHOR_TURNS):
        step(world, sim)
    turn = world.turn

    def events():
        world.regions[CRAG].last_conquered_turn = turn        # Phase 5 conquest
        world.regions[DUN].famine_cooldown = RL.FAMINE_ONSET_COOLDOWN   # Phase 9 famine onset
        world.regions[EDGE].occupied_by = "A"

    step(world, sim, moves=[(1, CRAG, BROOK, "conquest_memory"), (2, DUN, CRAG, "famine_memory"),
                            (3, EDGE, DUN, "battle_memory")], before=events)
    assert (_row(world, 1).spell.anchor, _row(world, 2).spell.anchor, _row(world, 3).spell.anchor) == (
        "war", "famine", "war")
    assert not any(_row(world, a).spell.anchor_partial for a in (1, 2, 3))


def test_persecution_and_a_controller_change_anchor_only_from_the_next_turn():
    world, sim = _world(), FakeSim()
    for aid, region in ((1, CRAG), (2, CRAG), (3, DUN), (4, DUN)):
        sim.add(aid, region)
    for _ in range(ANCHOR_TURNS):
        step(world, sim)

    def phase10_events():
        world.regions[CRAG].persecution_intensity = 0.4       # computed in Phase 10
        world.regions[DUN].controller = "A"                   # a secession: no conquest

    step(world, sim, moves=[(1, CRAG, BROOK, "persecution"), (3, DUN, EDGE, "safety_need")], before=phase10_events)
    assert _row(world, 1).spell.anchor == "none" and _row(world, 3).spell.anchor == "none"
    world.regions[CRAG].persecution_intensity = 0.0
    step(world, sim, moves=[(2, CRAG, BROOK, "persecution"), (4, DUN, EDGE, "safety_need")])
    assert _row(world, 2).spell.anchor == "persecution" and _row(world, 4).spell.anchor == "war"


def test_the_anchor_window_is_anchor_turns_and_keeps_every_kind_present():
    world, sim = _world(), FakeSim()
    for aid in (1, 2, 3):
        sim.add(aid, CRAG)
    step(world, sim)                                                    # turn 1 (watch starts)
    world.regions[CRAG].famine_cooldown = RL.FAMINE_ONSET_COOLDOWN
    world.regions[CRAG].persecution_intensity = 0.3
    step(world, sim)                                                    # turn 2: famine onset, persecution
    world.regions[CRAG].famine_cooldown = 4
    world.regions[CRAG].persecution_intensity = 0.0
    for _ in range(ANCHOR_TURNS - 1):
        step(world, sim)
    assert world.turn == 2 + ANCHOR_TURNS
    spell = _depart(world, sim, 1, CRAG)                                # turn 7: 2 >= 7 - 5
    assert (spell.anchor, spell.anchor_kinds, spell.anchor_partial) == ("famine", ["famine", "persecution"], False)
    spell = _depart(world, sim, 2, CRAG)                                # turn 8: outside the window
    assert (spell.anchor, spell.anchor_kinds) == ("none", [])


def test_an_anchor_window_before_the_watch_began_is_partial():
    world, sim = _world(), FakeSim()
    sim.add(1, CRAG)
    step(world, sim)
    spell = _depart(world, sim, 1, CRAG)
    assert spell.anchor == "none" and spell.anchor_partial
    assert _state(world).frame["totals"]["anchor_partial"] == 1


# --- attachment, trips, relocations ------------------------------------------------------

def test_enlistment_never_rehomes_and_attachment_is_counted_by_home_region():
    world, sim = _world(), FakeSim()
    for aid in (1, 2, 3):
        sim.add(aid, AVALON)
    step(world, sim)
    place_army(world, "A", "Crag", 2, "A|B", roster=[(1, AVALON), (2, AVALON)])
    place_army(world, "A", "Avalon", 1, "A|B", roster=[(3, AVALON)])
    frame = step(world, sim)
    assert (_row(world, 1).army, _row(world, 1).army_region, _row(world, 1).home) == ("army-1", CRAG, AVALON)
    av = _region(frame, AVALON)
    assert (av["attached"], av["attached_away"], frame["totals"]["attached_away"]) == (3, 2, 2)
    world.war_state.armies.clear()                                      # dissolved: seen at the next write
    step(world, sim)
    assert _row(world, 1).army is None and _row(world, 1).home == AVALON


def test_a_traveller_keeps_its_residence_and_one_first_seen_on_a_trip_waits_for_its_end():
    world, sim = _world(), FakeSim()
    sim.add(1, AVALON)
    sim.add(2, BROOK)
    sim.trips = {2}
    frame = step(world, sim)
    assert 2 not in _state(world).rows and _state(world).deferred == [2] and frame["totals"]["deferred"] == 1
    sim.trips = {1}
    sim.people[1]["region"] = CRAG                                      # in transit
    sim.people[2]["region"] = DUN                                       # back home after the trip
    frame = step(world, sim)
    assert _row(world, 1).res == AVALON and _region(frame, AVALON)["in_transit"] == 1
    assert (_row(world, 2).home, _row(world, 2).res) == (DUN, DUN) and frame["totals"]["newborn_rows"] == 0
    sim.trips = set()
    sim.people[1]["region"] = AVALON                                    # home at the trip's end
    frame = step(world, sim)
    assert frame["totals"]["trip_relocations"] == frame["totals"]["unexplained_relocations"] == 0


def test_a_trip_that_ends_away_from_home_is_an_unclassified_relocation():
    """A native unwind on conquest leaves the traveller where it was."""
    world, sim = _world(), FakeSim()
    sim.add(1, AVALON)
    sim.add(2, AVALON)
    sim.add(3, BROOK)
    step(world, sim)
    step(world, sim, moves=[(2, AVALON, CRAG, "battle_memory")])
    sim.trips = {1, 2}
    sim.people[1]["region"] = EDGE
    sim.people[2]["region"] = DUN
    step(world, sim)
    sim.trips = set()
    frame = step(world, sim)                                            # both stay where the trip stopped
    assert (_row(world, 1).home, _row(world, 1).res, _row(world, 1).spell) == (EDGE, EDGE, None)
    assert (_row(world, 2).home, _row(world, 2).res, _row(world, 2).spell) == (DUN, DUN, None)   # resettled
    assert [(e["id"], e["kind"], e["by"], e["relocation"]) for e in _events(world)] == [(2, "resettled", "move", True)]
    assert frame["totals"]["trip_relocations"] == 2 and frame["totals"]["unexplained_relocations"] == 0
    assert frame["totals"]["moves"] == 0                                # not applied migrations
    sim.people[3]["region"] = CRAG                                      # no trip, no event
    frame = step(world, sim)
    assert frame["totals"]["unexplained_relocations"] == 1 and _row(world, 3).res == CRAG


# --- lifecycle: pool reset, gaps, switch off ----------------------------------------------

def test_a_rebuilt_pool_closes_spells_and_restarts_observation_rebuilding_nothing():
    world, sim = _world(), FakeSim()
    _population(sim, 3)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory")])
    RL.on_pool_reset(world)                                            # Phase 2 of turn 3
    assert not _state(world).rows and _state(world).observed_from is None
    frame = step(world, sim)
    assert frame["observed_from"] == 3 and frame["totals"]["pool_reset"] == 1
    assert frame["totals"]["newborn_rows"] == 0 and frame["totals"]["displaced"] == 0
    assert [e["kind"] for e in _events(world)] == ["pool_reset"]
    assert _row(world, 1).home == BROOK                                 # history before is unknown
    assert _state(world).counters["closed_pool_reset"] == 1
    fresh = _world()
    RL.on_pool_reset(fresh)                                             # a fresh run: no-op, no log
    assert not _state(fresh).log[1:] and _state(fresh).pending is None


def test_a_gap_closes_spells_as_unobserved():
    world, sim = _world(), FakeSim()
    _population(sim, 2)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory")])
    world.turn += 2                                                     # two turns not observed
    frame = step(world, sim)
    assert frame["totals"]["unobserved_gap"] == 1 and frame["observed_from"] == world.turn - 1
    assert _state(world).counters["gaps"] == 1


def test_switching_off_closes_and_drops_and_switching_on_restarts():
    world, sim = _world(), FakeSim()
    _population(sim, 2)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory")])
    LV.configure_livelihoods(world, parse("--no-residence-ledger"), agent_mode="hybrid")
    state = _state(world)
    assert not state.rows and state.frame is None and state.counters["closed_unobserved_gap"] == 1
    assert "residence_ledger" not in LV.livelihoods_snapshot_fields(world).get("livelihoods", {})
    LV.phase10(world, agent_bridge=FakeBridge(sim))                     # inactive: no hook runs
    assert state.frame is None
    world.turn += 1
    LV.configure_livelihoods(world, parse("--residence-ledger"), agent_mode="hybrid")
    frame = step(world, sim)
    assert frame["observed_from"] == world.turn - 1 and state.counters["switched_on"] == 2


def test_the_writer_runs_once_a_turn_and_an_unobserved_turn_has_no_frame():
    world, sim = _world(), FakeSim()
    _population(sim, 1)
    step(world, sim, advance=False)
    with pytest.raises(RuntimeError, match="written twice"):
        LV.phase10(world, agent_bridge=FakeBridge(sim))
    world.turn += 1
    LV.phase10(world, agent_bridge=None)
    assert _state(world).frame is None and _state(world).frame_turn == world.turn
    assert _state(world).counters["turns_unobserved"] == 1


def test_the_writer_never_reads_relationships():
    world, sim = _world(), FakeSim(relationships_allowed=False)
    _population(sim, 3)
    sim.bonds = [(1, 2, BOND_MARRIAGE)]
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory")])
    assert sim.relationship_reads == 0


# --- readers (audit 11.4): T's frame at T+1, never the same turn ---------------------------

def test_readers_give_t_to_t_plus_1_and_refuse_a_same_turn_or_other_turn_read():
    world, sim = _world(), FakeSim()
    _population(sim, 2)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory")], advance=False)   # T = 2 written
    T = world.turn
    for read in (lambda: RL.read_frame(world, consumer_turn=T), lambda: RL.own_row(world, 1, consumer_turn=T),
                 lambda: RL.separation(world, FakeBridge(sim), consumer_turn=T)):
        with pytest.raises(RL.LedgerReadRefused, match="same-turn read refused"):
            read()
    world.turn += 1                                                     # the consumer's turn T+1
    with pytest.raises(RL.LedgerReadRefused, match="at its own turn"):
        RL.read_frame(world, consumer_turn=T + 2)                       # a future consumer
    with pytest.raises(RL.LedgerReadRefused, match="at its own turn"):
        RL.read_frame(world, consumer_turn=T)
    with pytest.raises(TypeError):
        RL.read_frame(world, consumer_turn=True)
    frame = RL.read_frame(world, consumer_turn=T + 1)
    assert frame["turn"] == T and frame["totals"]["displaced"] == 1
    row = RL.own_row(world, 1, consumer_turn=T + 1)
    assert row["source_turn"] == T and row["spell"]["cause"] == "flight" and row["res"] == BROOK
    assert row["res_since"] == T and row["move_from"] == AVALON
    assert set(row) == {"id", "source_turn", "home", "home_since", "res", "res_since", "first_seen", "move_turn",
                        "move_from", "move_driver", "spell", "army", "army_region"}
    assert RL.own_row(world, 2, consumer_turn=T + 1)["spell"] is None           # every key, None included
    assert RL.own_row(world, 99, consumer_turn=T + 1) is None
    frame["totals"]["displaced"] = 99                                   # a copy
    assert _state(world).frame["totals"]["displaced"] == 1
    world.turn += 1                                                     # T+2: T's frame is stale
    assert RL.read_frame(world, consumer_turn=T + 2) is None
    assert RL.own_row(world, 1, consumer_turn=T + 2) is None


def test_the_aggregate_frame_names_no_person():
    world, sim = _world(), FakeSim()
    _population(sim, 3)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory")])
    frame = RL.read_frame(world, consumer_turn=world.turn)
    assert set(frame) == {"turn", "observed_from", "totals", "regions"}
    assert set(frame["totals"]) == set(TOTAL_KEYS)
    assert all(set(r) == set(REGION_KEYS) for r in frame["regions"])


def test_a_reader_gets_none_when_off_or_unobserved():
    world, sim = _world(), FakeSim()
    _population(sim, 1)
    assert RL.read_frame(world, consumer_turn=world.turn) is None       # nothing written yet
    step(world, sim)
    LV.phase10(world, agent_bridge=None)                                # an unobserved turn
    world.turn += 1
    assert RL.read_frame(world, consumer_turn=world.turn) is None
    world.agent_mode = "shadow"
    assert RL.read_frame(world, consumer_turn=world.turn) is None


def test_separation_is_computed_on_demand_with_its_causes():
    world, sim = _world(), FakeSim()
    for aid in range(1, 11):
        sim.add(aid, AVALON)
    sim.add(11, AVALON, age=5, parents=(9, 10))
    sim.bonds = [(1, 2, BOND_MARRIAGE), (3, 4, BOND_MARRIAGE), (5, 6, BOND_MARRIAGE), (7, 8, BOND_MARRIAGE),
                 (1, 3, BOND_FRIEND)]
    step(world, sim)
    place_army(world, "A", "Crag", 1, "A|B", roster=[(5, AVALON)])
    step(world, sim, moves=[(3, AVALON, BROOK, "battle_memory"), (7, AVALON, DUN, "wage"),
                            (10, AVALON, EDGE, "wage")])
    sim.trips = {1}
    sim.people[1]["region"] = CRAG
    step(world, sim, advance=False)
    world.turn += 1
    out = RL.separation(world, FakeBridge(sim), consumer_turn=world.turn)
    got = {(s["a"], s["b"], s["relation"], s["cause"]) for s in out["separated"]}
    assert got == {(1, 2, "spouse", "trip"), (3, 4, "spouse", "displaced"), (5, 6, "spouse", "attached"),
                   (7, 8, "spouse", "migrated"), (11, 10, "parent", "migrated")}
    assert out["pairs"] == 6 and out["by_cause"] == {"trip": 1, "attached": 1, "displaced": 1, "migrated": 2}
    assert out["by_relation"] == {"spouse": 4, "parent": 1} and out["source_turn"] == world.turn - 1
    assert "separation" not in json.dumps(_state(world).model_dump(mode="json"))       # never stored


# --- records -------------------------------------------------------------------------------

@pytest.mark.parametrize("case", ["absent", "malformed", "unobserved", "recorded_zero", "recorded"])
def test_reader_states_are_distinct(case):
    world, sim = _world(), FakeSim()
    _population(sim, 2)
    step(world, sim)
    moves = [(1, AVALON, BROOK, "battle_memory")] if case == "recorded" else []
    step(world, sim, moves=moves)
    snapshot = LV.livelihoods_snapshot_fields(world)
    record = snapshot["livelihoods"]["residence_ledger"]
    assert record["stage"] == "X1" and record["source_turn"] == world.turn - 1
    assert json.loads(json.dumps(snapshot)) == snapshot
    if case == "absent":
        snapshot = {"livelihoods": {"schema_version": 1}}
    elif case == "malformed":
        record["frame"]["totals"].pop("displaced")
    elif case == "unobserved":
        world.turn += 1
        snapshot = LV.livelihoods_snapshot_fields(world)
    status, frame = RL.record_status(snapshot)
    assert status == case
    assert (frame is None) == (case in ("absent", "malformed", "unobserved"))


def test_the_snapshot_never_aliases_the_state_and_carries_its_parameters():
    world, sim = _world(), FakeSim()
    _population(sim, 2)
    step(world, sim)
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory")])
    record = LV.livelihoods_snapshot_fields(world)["livelihoods"]["residence_ledger"]
    record["frame"]["regions"].clear()
    record["events"].clear()
    assert _state(world).frame["regions"] and _state(world).events
    p = record["parameters"]
    assert (p["rehome_turns"], p["anchor_turns"], p["closures"]) == (20, 5, list(CLOSURES))
    assert record["events_dropped"] == 0 and set(record["counters"]) <= set(COUNTERS)


def test_the_state_round_trips_json_and_pickle():
    world, sim = _world(), FakeSim()
    _population(sim, 3)
    step(world, sim)
    place_army(world, "A", "Crag", 1, "A|B", roster=[(3, AVALON)])
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory")])
    state = _state(world)
    back = LivelihoodsState.model_validate_json(world.livelihoods.model_dump_json())
    assert back.residence_ledger == state and list(back.residence_ledger.rows) == [1, 2, 3]
    assert pickle.loads(pickle.dumps(world.livelihoods)).residence_ledger == state
    dumped = json.loads(world.livelihoods.model_dump_json())["residence_ledger"]["rows"]["2"]
    assert set(dumped) == {"home", "home_since", "res", "res_since", "first_seen"}      # empty fields omitted


def test_rows_and_events_are_bounded(monkeypatch):
    monkeypatch.setattr(RL, "MAX_ROWS", 3)
    monkeypatch.setattr(RL, "MAX_EVENTS", 1)
    world, sim = _world(), FakeSim()
    _population(sim, 5)
    frame = step(world, sim)
    assert frame["totals"]["observed"] == 3 and _state(world).counters["rows_refused"] == 2
    step(world, sim, moves=[(1, AVALON, BROOK, "battle_memory"), (2, AVALON, BROOK, "battle_memory")])
    assert len(_state(world).events) == 1 and _state(world).events_dropped == 1
    assert _state(world).counters["events_dropped"] == 1


def test_counters_and_log_kinds_are_declared():
    state = ResidenceLedgerState()
    with pytest.raises(KeyError):
        RL._bump(state, "made_up")
    with pytest.raises(KeyError):
        RL._log(state, 1, "made_up")


def test_with_the_ledger_on_everything_but_its_record_equals_off():
    def scenario(*extra):
        world = war_world()
        world.agent_mode = "hybrid"
        world.turn = 1
        LV.configure_livelihoods(world, parse(*extra), agent_mode="hybrid")
        sim = FakeSim()
        _population(sim, 4)
        sim.trips = {4}
        place_army(world, "A", "Crag", 1, "A|B", roster=[(3, AVALON)])
        LV.phase10(world, agent_bridge=FakeBridge(sim))
        world.turn += 1
        world.agent_events_raw.append(AgentEventRecord(world.turn, 1, "migration", AVALON, BROOK, 0, 0,
                                                       migration_driver=_code("battle_memory")))
        sim.people[1]["region"] = BROOK
        world.regions[CRAG].persecution_intensity = 0.2
        LV.phase10(world, agent_bridge=FakeBridge(sim))
        world.turn += 1
        return world, sim

    on, sim_on = scenario("--residence-ledger")
    off, sim_off = scenario()
    dump_on, dump_off = on.model_dump(mode="json"), off.model_dump(mode="json")
    record = dump_on["livelihoods"].pop("residence_ledger")
    assert dump_on.pop("livelihoods") == {"schema_version": 1} and "livelihoods" not in dump_off
    assert record["frame"]["turn"] == 2 and dump_on == dump_off
    assert sim_on.people == sim_off.people and sim_on.trips == sim_off.trips
    assert on.agent_events_raw == off.agent_events_raw


# --- the report script -----------------------------------------------------------------------

def test_the_report_summarizes_shares_and_closures():
    import importlib.util
    spec = importlib.util.spec_from_file_location("residence_ledger_report", ROOT / "scripts" / "residence_ledger_report.py")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    world, sim = _world(), FakeSim()
    _population(sim, 4)
    history = []
    for moves in ([], [(1, AVALON, BROOK, "battle_memory")], [(1, BROOK, AVALON, None)], [], []):
        step(world, sim, moves=moves)
        history.append({"turn": world.turn, **LV.livelihoods_snapshot_fields(world)})
    history.append({"turn": world.turn + 1, "livelihoods": {"schema_version": 1}})
    out = report.summarize(history)
    assert out["turns"] == 5 and out["readings"] == {"recorded_zero": 3, "recorded": 2, "absent": 1}
    assert out["opened"] == 1 and out["closed"]["returned"] == 1 and out["median_length"]["returned"] == 1
    # The last three quarters (turns 2-5) of 4 people: one displaced at turn 2.
    assert out["shares_last_three_quarters"]["open_spell"] == 0.0625
    assert out["shares_last_three_quarters"]["native_cooldown"] == 0.25        # moved in the last 5 turns
    assert out["alive_range"] == [4, 4]
