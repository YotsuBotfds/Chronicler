"""RS3 veteran reintegration without the native extension (constructed state).

A constructed five-region war world (``war_fixtures``: A, civ 0, holds Avalon
0 and Brook 1; B, civ 1, holds Crag 2, Dun 3 and Edge 4) and a constructed
pool standing in for the native snapshot. Each test drives the real campaign
functions and this package's livelihoods hooks in turn order: Phase 2
(``prepare_phase2``/``finish_phase2``), the war phase, then ``phase10``
after a (here, constructed) agent tick. Natural worlds are in the native
tests and the development evidence, not here.
"""
from __future__ import annotations

import json
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import veteran_reintegration as VR
from chronicler.cities_state import CityState
from chronicler.livelihoods import bind_native_pool
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.veteran_reintegration_state import (
    CAUSES, COUNTERS, OUTCOMES, UNMET_REASONS, VeteranReintegrationState,
)
from chronicler.war import params as P
from chronicler.war import runtime as RT
from chronicler.war.armies import disband, rebind_rosters, release_soldiers
from chronicler.war.common import build_context
from chronicler.workshops_state import WorkshopReceipt, WorkshopSite, WorkshopState
from war_fixtures import place_army, start_war, war_world

#: id -> (region, age, occupation, civ_affinity, settlement): civ 0 people in
#: Brook's city (settlement 7) and Avalon, one minor, one civ 1 person.
ROWS = {10: (1, 30, 0, 0, 7), 11: (1, 25, 1, 0, 7), 12: (0, 40, 0, 0, 0), 13: (1, 15, 0, 0, 7),
        14: (1, 33, 0, 0, 7), 15: (1, 28, 0, 0, 7), 16: (1, 50, 0, 0, 7), 30: (2, 30, 0, 1, 0)}


class Pool:
    """A constructed native pool: the snapshot, deaths queue and registry."""

    def __init__(self, rows):
        self.rows = {aid: list(v) for aid, v in rows.items()}
        self.queued: list[int] = []

    def queue_targeted_deaths(self, ids):
        self.queued.extend(ids)

    def work_reservations(self, turn):
        return []


class Bridge:
    def __init__(self, rows=ROWS):
        self._sim = Pool(rows)
        self.named_agents: dict[int, str] = {}

    def get_snapshot(self):
        ids = sorted(self._sim.rows)
        col = [[self._sim.rows[a][i] for a in ids] for i in range(5)]
        return pa.record_batch({
            "id": pa.array(ids, pa.uint32()), "region": pa.array(col[0], pa.uint16()),
            "age": pa.array(col[1], pa.uint16()), "occupation": pa.array(col[2], pa.uint8()),
            "civ_affinity": pa.array(col[3], pa.uint8()), "settlement_id": pa.array(col[4], pa.uint16())})


def _world(mode="priority", *, cities=False):
    world = war_world()
    world.agent_mode = "hybrid"
    world.livelihoods = LivelihoodsState()
    VR.set_veteran_reintegration_enabled(world, True, args=SimpleNamespace(veteran_mode=mode))
    bridge = Bridge()
    world._agent_bridge = bridge
    world.livelihoods._pool_sim = id(bridge._sim)
    if cities:
        world.cities = CityState()
    ctx, war = start_war(world)
    ctx.bridge = bridge
    return world, bridge, ctx, war


def _state(world) -> VeteranReintegrationState:
    return world.livelihoods.veteran_reintegration


def _turn(world, bridge, war_phase=None, *, receipts=None):
    """One turn in hook order; ``receipts`` stand in for the workshops' finish."""
    VR.prepare_phase2(world, None, bridge, bridge.get_snapshot(), None)
    if receipts is not None:
        ws = world.livelihoods.workshops
        ws.frame, ws.frame_turn = receipts, world.turn
    VR.finish_phase2(world, None, bridge, None)
    if war_phase is not None:
        war_phase()
    VR.phase10(world, None, None, bridge)
    world.turn += 1


def _army(world, war, roster, *, civ="A", region="Brook", phase="marching"):
    army = place_army(world, civ, region, len(roster), war.war_key, roster=roster, phase=phase)
    army.raised_turn = world.turn
    return army


def _kinds(record):
    return [(o.turn, o.kind) for o in record.outcomes]


def _record(world, aid):
    state = _state(world)
    found = [r for r in state.records if r.agent_id == aid]
    return found[0] if found else None


# --- Capture --------------------------------------------------------------------------


def test_release_and_disband_capture_the_living_by_cause_and_war():
    world, bridge, ctx, war = _world()
    army = _army(world, war, [(10, 1), (11, 1), (12, 0), (14, 1)])

    def war_phase():
        assert release_soldiers(ctx, army, 2, cause="desertion") == 2
        kept = list(army.roster)
        disband(ctx, army, "demobilized")
        state = _state(world)
        # Buffered only: nothing is recorded before the agent tick succeeded.
        assert state.records == [] and len(state._captures) == 2
        assert set(state._captures[1][7]) == set(kept)

    _turn(world, bridge, war_phase)
    state = _state(world)
    assert sorted(r.agent_id for r in state.records) == [10, 11, 12, 14]
    for r in state.records:
        assert (r.civ, r.army_id, r.war_key, r.war_start, r.released_turn) == (0, army.army_id, war.war_key,
                                                                              war.start_turn, 0)
        assert r.cause in ("desertion", "demobilised") and r.region == ROWS[r.agent_id][0]
        assert r.status == "waiting" and _kinds(r) == [(0, "waiting")]
    frame = state.frame
    assert frame.turn == 0 and frame.captured_by_cause == {"desertion": 2, "demobilised": 2}
    assert {c.agent_id for c in frame.captured} == {10, 11, 12, 14}
    assert state.counters["captured"] == 4 and state.last_settled_turn == 0


def test_destroyed_and_dissolved_armies():
    world, bridge, ctx, war = _world()
    small = _army(world, war, [(10, 1), (14, 1)])
    small.casualties = 3                                   # broken by battle: destroyed
    big = _army(world, war, [(15, 1), (16, 1), (12, 0)])

    def war_phase():
        RT._drop_empty(ctx)                                # survivors scatter, then disband
        assert [item[6] for item in _state(world)._captures] == ["scattered"]
        assert small.roster == []
        # A disband that finds people still enlisted records them as destroyed.
        disband(ctx, big, "destroyed")

    _turn(world, bridge, war_phase)
    causes = {r.agent_id: r.cause for r in _state(world).records}
    assert causes == {10: "scattered", 14: "scattered", 15: "destroyed", 16: "destroyed", 12: "destroyed"}
    # A civilization that is gone: its army is dropped silently, its roster alive.
    world2, bridge2, ctx2, war2 = _world()
    gone = _army(world2, war2, [(10, 1), (14, 1), (15, 1)])
    world2.civ_map["A"].regions = []
    RT._validate_armies(ctx2)
    assert gone not in world2.war_state.armies
    assert [(item[6], item[7]) for item in _state(world2)._captures] == [("dissolved", ((10, 1), (14, 1), (15, 1)))]


def test_end_of_turn_sync_commits_into_the_settled_turn():
    world, bridge, ctx, war = _world()
    army = _army(world, war, [(10, 1), (14, 1), (15, 1)])
    VR.prepare_phase2(world, None, bridge, bridge.get_snapshot(), None)
    VR.finish_phase2(world, None, bridge, None)
    VR.phase10(world, None, None, bridge)
    world.civ_map["A"].regions = []                        # dies after Phase 10
    RT.end_of_turn_sync(world)
    state = _state(world)
    assert army not in world.war_state.armies and state._captures == []
    assert sorted(r.agent_id for r in state.records) == [10, 14, 15]
    assert all(r.cause == "dissolved" and r.status == "ineligible" and r.reason == "unobserved"
               for r in state.records)
    assert state.frame.captured_by_cause == {"dissolved": 3} and state.frame.counts["open"] == 3
    world.turn += 1
    # Next turn: observed alive, in land no longer ruled by the civ they served.
    world.regions[1].controller = "B"
    _turn(world, bridge)
    assert all(r.reason == "control_lost" and _kinds(r)[-1] == (1, "control_lost") for r in state.records)
    assert VR.priority_ids(world, 1) == []


def test_feature_off_hooks_change_nothing_and_draw_no_rng(monkeypatch):
    def leaving(world, ctx, war):
        army = _army(world, war, [(10, 1), (11, 1), (12, 0), (14, 1), (15, 1)])
        release_soldiers(ctx, army, 2, cause="desertion")
        return list(army.roster)

    on_world, _b, on_ctx, on_war = _world()
    kept_on = leaving(on_world, on_ctx, on_war)
    # No livelihoods container: the capture module is never consulted.
    off_world, bridge, ctx, war = _world()
    off_world.livelihoods = None
    monkeypatch.setattr(VR, "capture_release", lambda *a, **k: pytest.fail("consulted while off"))
    assert leaving(off_world, ctx, war) == kept_on
    monkeypatch.undo()
    # Present but disabled, or not in hybrid: nothing buffered.
    for tweak in ("disabled", "shadow"):
        world, bridge, ctx, war = _world()
        if tweak == "disabled":
            VR.set_veteran_reintegration_enabled(world, False)
        else:
            world.agent_mode = "shadow"
        assert leaving(world, ctx, war) == kept_on
        assert _state(world)._captures == [] and _state(world).records == []
    with pytest.raises(ValueError, match="cause"):
        VR.capture_release(on_world, on_world.war_state.armies[0], [(10, 1)], "retired")


def test_war_identity_is_the_key_and_start_turn_of_the_war_served():
    world, bridge, ctx, war = _world()
    first = _army(world, war, [(10, 1), (14, 1), (15, 1)])
    # The war ends; the pair goes to war again later under the same key.
    world.war_state.wars.remove(war)
    war.ended_turn = 5
    world.war_state.ended_wars.append(war)
    from chronicler.models import WarRecord
    again = WarRecord(war_key=war.war_key, attacker="A", defender="B", start_turn=7)
    world.war_state.wars.append(again)
    world.turn = 8
    second = _army(world, again, [(12, 0), (16, 1), (11, 1)])
    assert VR._war_of(world, first) == (war.war_key, 0)
    assert VR._war_of(world, second) == (war.war_key, 7)
    stray = _army(world, again, [(13, 1)])
    stray.war_key = "Nobody:Else"
    assert VR._war_of(world, stray) == (None, None)


# --- Eligibility and priority -------------------------------------------------------


def _released(world, bridge, ctx, war, roster):
    army = _army(world, war, roster)
    _turn(world, bridge, lambda: disband(ctx, army, "demobilized"))
    return army


def test_priority_order_eligibility_and_the_control():
    world, bridge, ctx, war = _world()
    _released(world, bridge, ctx, war, [(14, 1), (10, 1), (13, 1), (12, 0)])      # turn 0
    _released(world, bridge, ctx, war, [(15, 1), (11, 1)])                         # turn 1
    assert world.turn == 2
    # Earliest release first, then id; the minor (13) is not eligible; region 0 apart.
    assert VR.priority_ids(world, 1) == [10, 14, 11, 15]
    assert VR.priority_ids(world, 0) == [12] and VR.priority_ids(world, 2) == []
    assert _record(world, 13).status == "ineligible" and _record(world, 13).reason == "minor"
    # On a roster again: not eligible (and closed as remobilised at the next commit).
    _army(world, war, [(14, 1), (16, 1), (30, 2)])
    assert VR.priority_ids(world, 1) == [10, 11, 15]
    # Another ruler in Brook: nobody there is prioritised.
    world.regions[1].controller = "B"
    assert VR.priority_ids(world, 1) == []
    world.regions[1].controller = "A"
    # The control captures and tracks but never reorders anyone.
    _state(world).mode = "record_only"
    assert VR.priority_ids(world, 1) == []
    _state(world).mode = "priority"
    # The window is checked live too: through turn 0 + ELIGIBLE_TURNS, never after
    # (a run that skipped commits, e.g. a disabled switch, cannot extend it).
    world.turn = VR.ELIGIBLE_TURNS                       # 14 is still enlisted
    assert VR.priority_ids(world, 1) == [10, 11, 15]
    world.turn = VR.ELIGIBLE_TURNS + 1
    assert VR.priority_ids(world, 1) == [11, 15]
    VR.set_veteran_reintegration_enabled(world, False)
    assert VR.priority_ids(world, 1) == []


def test_drafted_and_released_again_within_a_turn_opens_a_second_record():
    world, bridge, ctx, war = _world()
    _released(world, bridge, ctx, war, [(10, 1), (14, 1), (15, 1)])           # turn 0
    state = _state(world)
    first = _record(world, 10)

    def war_phase():
        again = _army(world, war, [(10, 1), (16, 1), (12, 0)])
        release_soldiers(ctx, again, 3, cause="scattered")

    _turn(world, bridge, war_phase)                                          # turn 1
    assert first.status == "closed" and first.closed_reason == "remobilised" and first.closed_turn == 1
    assert first.outcomes[-1].detail == {"army_id": world.war_state.armies[-1].army_id}
    assert [(r.agent_id, r.released_turn, r.cause) for r in state.records if r.agent_id == 10] == [(10, 1, "scattered")]
    assert state.counters["closed_remobilised"] == 1 and state.counters["captured"] == 6


def test_lifecycle_death_migration_control_remobilisation_expiry_and_return():
    world, bridge, ctx, war = _world()
    _released(world, bridge, ctx, war, [(10, 1), (11, 1), (12, 0), (14, 1), (15, 1), (16, 1)])
    rows = bridge._sim.rows
    del rows[11]                                           # dies in the tick
    rows[12][0] = 1                                        # moves Avalon -> Brook (same ruler)
    rows[15][0] = 2                                        # moves into B's Crag
    redraft = _army(world, war, [(16, 1), (30, 2), (13, 1)])
    _turn(world, bridge)                                   # turn 1
    state = _state(world)
    closed = {r.agent_id: r for r in state.archive}
    assert closed[11].closed_reason == "died" and _kinds(closed[11])[-1] == (1, "died")
    assert closed[16].closed_reason == "remobilised" and closed[16].outcomes[-1].detail == {"army_id": redraft.army_id}
    r12, r15 = _record(world, 12), _record(world, 15)
    assert (r12.region, r12.status) == (1, "waiting")
    assert ("migrated" in [k for _, k in _kinds(r12)]) and r12.outcomes[-1].kind == "migrated"
    assert r15.reason == "control_lost" and [k for _, k in _kinds(r15)][-2:] == ["migrated", "control_lost"]
    assert 12 in VR.priority_ids(world, 1) and VR.priority_ids(world, 2) == []
    # Back home: eligible again, dated.
    rows[15][0] = 1
    _turn(world, bridge)                                   # turn 2
    assert r15.status == "waiting" and _kinds(r15)[-1] == (2, "waiting") and r15.reason is None
    # Released again after remobilisation: a new record for the same person.
    _turn(world, bridge, lambda: disband(ctx, redraft, "demobilized"))   # turn 3
    records16 = sorted((r for r in (*state.records, *state.archive) if r.agent_id == 16),
                       key=lambda r: r.record_id)
    assert [(r.released_turn, r.status) for r in records16] == [(0, "closed"), (3, "waiting")]
    # The window ends: expired, dated, and no longer offered.
    while world.turn <= VR.ELIGIBLE_TURNS:
        _turn(world, bridge)
    expired = [r for r in state.archive if r.closed_reason == "expired"]
    assert {r.agent_id for r in expired} == {10, 12, 14, 15}
    assert all(r.closed_turn == VR.ELIGIBLE_TURNS for r in expired)
    assert VR.priority_ids(world, 1) == [16]
    assert state.counters["closed_expired"] == 4 and state.counters["closed_died"] == 1


# --- Placements --------------------------------------------------------------------------


def _site_world(mode="priority"):
    world, bridge, ctx, war = _world(mode, cities=True)
    world.livelihoods.workshops = WorkshopState(mode="operate", sites=[
        WorkshopSite(site=0, region=1, settlement_id=7, city_name="Brook Town", selected_turn=0, asset="open")])
    return world, bridge, ctx, war


def _receipt(turn, crew, *, eligible, allocated=1.0):
    return [WorkshopReceipt(turn=turn, site=0, region=1, settlement_id=7, rank=1, diverted_fraction=0.25,
                            resident_adult_farmers=eligible, excluded_trip=0, excluded_army=0,
                            excluded_assigned=0, eligible=eligible, crew=crew, crew_ages=[30] * len(crew),
                            work_available=0.25 * len(crew), allocated=allocated)]


@pytest.mark.parametrize("mode", ["priority", "record_only"])
def test_crew_placements_and_why_others_waited(mode):
    world, bridge, ctx, war = _site_world(mode)
    _released(world, bridge, ctx, war, [(10, 1), (11, 1), (12, 0), (14, 1)])      # turn 0
    state = _state(world)
    # Turn 1: 10 is crewed; 14 is a resident farmer the cap left out; 11 is no
    # farmer; 12 lives where there is no site.
    _turn(world, bridge, receipts=_receipt(1, [10, 3, 4], eligible=4))
    frame = state.frame
    assert frame.offered == [(1, [10, 11, 14])] and frame.priority_applied is (mode == "priority")
    assert [(p.agent_id, p.kind, p.site, p.prioritised, p.new_spell) for p in frame.placed] == \
        [(10, "placed:crew", 0, mode == "priority", True)]
    assert {w.agent_id: w.reason for w in frame.waiting} == {11: "not_crew_eligible", 14: "crew_full",
                                                             12: "no_site"}
    assert _record(world, 10).status == "placed" and _kinds(_record(world, 10))[-1] == (1, "placed:crew")
    assert state.counters["offered" if mode == "priority" else "would_offer"] == 3
    # Turn 2: same crew (one spell); turn 3: the site is idle (no work); turn 4: back.
    _turn(world, bridge, receipts=_receipt(2, [10, 14, 3], eligible=4))
    _turn(world, bridge, receipts=_receipt(3, [10, 14, 3], eligible=4, allocated=0.0))
    assert {w.agent_id: w.reason for w in state.frame.waiting}[10] == "site_idle"
    assert _record(world, 10).status == "waiting" and _kinds(_record(world, 10))[-1] == (3, "waiting")
    _turn(world, bridge, receipts=_receipt(4, [10], eligible=1))
    r10, r14 = _record(world, 10), _record(world, 14)
    assert [(s.start_turn, s.last_turn, s.turns) for s in r10.spells] == [(1, 2, 2), (4, 4, 1)]
    assert (r10.placements, r10.placed_turns, r14.placements, r14.placed_turns) == (2, 3, 1, 1)
    assert state.counters["placements"] == 3 and state.counters["placement_turns"] == 4
    assert state.counters["people_placed"] == 2 and state.ever_placed == [10, 14]
    assert state.counters.get("placed_prioritised", 0) == (3 if mode == "priority" else 0)
    assert set(state.counters) <= set(COUNTERS)
    assert all(w.reason in UNMET_REASONS for w in state.frame.waiting)


def test_reported_placements_are_staged_dated_and_counted_once():
    world, bridge, ctx, war = _world()
    with pytest.raises(ValueError, match="unknown veteran outcome"):
        VR.note_outcome(world, 10, "placed:army", turn=0)
    _released(world, bridge, ctx, war, [(10, 1), (14, 1), (15, 1)])
    state = _state(world)
    with pytest.raises(TypeError):
        VR.note_outcome(world, 10, "placed:repair", turn=1, detail={"site": [1]})
    assert VR.note_outcome(world, 999, "placed:repair", turn=1) is None and state._noted == []
    VR.note_outcome(world, 10, "placed:apprentice", turn=1, detail={"site": 0, "region": 1})
    VR.note_outcome(world, 10, "placed:apprentice", turn=1, detail={"site": 0, "region": 1})   # twice
    VR.note_outcome(world, 14, "placed:repair", turn=0, detail={"site": 2})                     # stale
    assert state.records and _record(world, 10).spells == []                                    # staged only
    _turn(world, bridge)
    r10 = _record(world, 10)
    assert r10.placements == 1 and r10.placed_turns == 1 and r10.status == "placed"
    assert r10.spells[0].prioritised is True                # eligible at this turn's Phase 2
    assert state.counters["notes_discarded"] == 1 and _record(world, 14).placements == 0
    VR.note_outcome(world, 10, "placed:apprentice", turn=2, detail={"site": 0})
    VR.note_outcome(world, 15, "died", turn=2)              # another lane saw the death first
    _turn(world, bridge)
    assert [(s.start_turn, s.last_turn) for s in r10.spells] == [(1, 2)]
    assert [r.closed_reason for r in state.archive] == ["died"]
    # Remobilised, released again, placed again: two placements, one person.
    redraft = _army(world, war, [(10, 1), (12, 0), (16, 1)])
    _turn(world, bridge)
    _turn(world, bridge, lambda: disband(ctx, redraft, "demobilized"))
    VR.note_outcome(world, 10, "placed:repair", turn=world.turn, detail={"site": 1})
    _turn(world, bridge)
    assert [r.placements for r in (*state.archive, *state.records) if r.agent_id == 10] == [1, 1]
    assert state.counters["placements"] == 2 and state.counters["people_placed"] == 1


# --- Exactly once, failures, pool reset -------------------------------------------------


def test_a_failed_turn_commits_nothing_and_a_turn_settles_once():
    world, bridge, ctx, war = _site_world()
    _released(world, bridge, ctx, war, [(10, 1), (14, 1), (15, 1)])
    state = _state(world)
    army = _army(world, war, [(16, 1), (12, 0), (11, 1)])
    # Turn 1 fails after the war phase (the agent tick raised): no commit.
    VR.prepare_phase2(world, None, bridge, bridge.get_snapshot(), None)
    ws = world.livelihoods.workshops
    ws.frame, ws.frame_turn = _receipt(1, [10], eligible=1), 1
    VR.finish_phase2(world, None, bridge, None)
    disband(ctx, army, "demobilized")
    VR.note_outcome(world, 14, "placed:repair", turn=1)
    before = state.model_dump_json()
    assert state._captures and state._noted and state._phase2 is not None
    world.turn += 1                                        # the run went on regardless
    VR.prepare_phase2(world, None, bridge, bridge.get_snapshot(), None)
    assert state.counters["captures_discarded"] == 3 and state.counters["notes_discarded"] == 1
    assert state._captures == [] and _record(world, 16) is None
    VR.rollback_phase2(world)
    assert state._phase2 is None
    after = json.loads(state.model_dump_json())
    for key in ("captures_discarded", "notes_discarded"):
        after["counters"].pop(key)
    assert after == json.loads(before)
    # The agent-tick rollback clears everything staged.
    VR.prepare_phase2(world, None, bridge, bridge.get_snapshot(), None)
    VR.rollback_agent_tick(world, bridge)
    assert (state._captures, state._noted, state._phase2) == ([], [], None)
    VR.phase10(world, None, None, bridge)
    with pytest.raises(RuntimeError, match="already settled"):
        VR.phase10(world, None, None, bridge)
    assert all(r.placements == 0 for r in state.records)


def test_pool_reset_closes_records_and_a_redraft_makes_no_veteran():
    world, bridge, ctx, war = _world()
    army = _army(world, war, [(15, 1), (16, 1), (11, 1)])
    _released(world, bridge, ctx, war, [(10, 1), (14, 1)])
    VR.note_outcome(world, 10, "placed:repair", turn=world.turn)
    _turn(world, bridge)
    state = _state(world)
    assert state.ever_placed == [10] and len(state.records) == 2
    old_pool = id(bridge._sim)
    state._captures.append((world.turn, old_pool, "army-x", 0, None, None, "desertion", ((12, 0),)))
    # A rebuilt pool: different people under small ids.
    fresh = Bridge({100: (1, 30, 1, 0, 7), 101: (1, 31, 1, 0, 7), 102: (1, 32, 1, 0, 7), 103: (0, 40, 1, 0, 0)})
    bind_native_pool(world, fresh)
    assert state.records == [] and state._captures == [] and state.ever_placed == []
    assert [(r.agent_id, r.closed_reason, _kinds(r)[-1]) for r in state.archive[-2:]] == \
        [(10, "pool_reset", (world.turn, "pool_reset")), (14, "pool_reset", (world.turn, "pool_reset"))]
    assert state.counters["pool_resets"] == 1 and state.counters["people_placed"] == 1
    assert state.counters["captures_discarded"] == 1
    # The roster is redrafted from the new pool; nobody is released by it.
    ctx.bridge = fresh
    world._agent_bridge = fresh
    rebind_rosters(ctx)
    assert {aid for aid, _ in army.roster} <= {100, 101, 102, 103} and len(army.roster) == 3
    assert state._captures == [] and state.pool_reset_turn == world.turn
    VR.prepare_phase2(world, None, fresh, fresh.get_snapshot(), None)
    # The redrafted army demobilises: its people served only by the redraft.
    disband(ctx, army, "demobilized")
    assert state._captures == [] and state.counters["captures_untrusted"] == 3
    VR.phase10(world, None, None, fresh)
    assert state.records == [] and state.frame.captured_total == 0
    assert [o.kind for o in state.frame.outcomes] == ["pool_reset", "pool_reset"]
    world.turn += 1
    # An army raised after the rebuild is captured as usual.
    later = _army(world, war, [(100, 1), (101, 1), (102, 1)])
    _turn(world, bridge=fresh, war_phase=lambda: disband(ctx, later, "demobilized"))
    assert sorted(r.agent_id for r in state.records) == [100, 101, 102]
    # A fresh run binds with nothing to close: no counter.
    world2, *_ = _world()
    VR.on_pool_reset(world2)
    assert _state(world2).counters == {}


def test_bounds_on_records_and_outcomes(monkeypatch):
    monkeypatch.setattr(VR, "MAX_OPEN", 2)
    monkeypatch.setattr(VR, "MAX_OUTCOMES", 2)
    world, bridge, ctx, war = _world()
    _released(world, bridge, ctx, war, [(10, 1), (14, 1), (15, 1)])
    state = _state(world)
    assert len(state.records) == 2 and state.counters["capture_overflow"] == 1
    assert state.frame.captured_total == 3
    rows = bridge._sim.rows
    for region in (0, 1, 0):
        rows[10][0] = region
        _turn(world, bridge)
    r10 = _record(world, 10)
    assert len(r10.outcomes) == 2 and r10.outcomes_dropped >= 2
    assert state.counters["outcomes_dropped"] == sum(r.outcomes_dropped for r in state.records)


def test_no_money_moves_and_snapshot_is_dated_and_copied():
    class Refuse:
        def __getattr__(self, name):
            raise AssertionError(f"the accumulator was used: {name}")

    world, bridge, ctx, war = _world()
    treasuries = [c.treasury for c in world.civilizations]
    army = _army(world, war, [(10, 1), (14, 1), (15, 1)])
    VR.prepare_phase2(world, None, bridge, bridge.get_snapshot(), Refuse())
    VR.finish_phase2(world, None, bridge, Refuse())
    disband(ctx, army, "demobilized")
    VR.phase10(world, Refuse(), None, bridge)
    world.turn += 1
    assert [c.treasury for c in world.civilizations] == treasuries
    summary = VR.snapshot_summary(world)
    assert summary["stage"] == "RS3" and summary["source_turn"] == 0 and summary["frame"]["turn"] == 0
    assert [v["agent_id"] for v in summary["veterans"]] == [10, 14, 15] and summary["veterans_omitted"] == 0
    assert summary["veterans"][0]["war_key"] == war.war_key and summary["veterans"][0]["cause"] == "demobilised"
    json.dumps(summary)
    summary["veterans"][0]["status"] = "edited"
    assert _record(world, 10).status == "waiting"          # a copy, not the live record
    world.turn += 1                                        # no commit in turn 1: unknown, not zero
    later = VR.snapshot_summary(world)
    assert later["frame"] is None and later["source_turn"] == 1


def test_state_round_trips_and_an_rs0_pickle_restores():
    world, bridge, ctx, war = _world()
    _released(world, bridge, ctx, war, [(10, 1), (14, 1)])
    state = _state(world)
    text = state.model_dump_json()
    back = VeteranReintegrationState.model_validate_json(text)
    assert back.model_dump_json() == text and back.frame.offered == []
    assert pickle.loads(pickle.dumps(state)).model_dump_json() == text
    container = pickle.loads(pickle.dumps(world.livelihoods))
    assert container.veteran_reintegration.model_dump_json() == text
    # A pickle of the RS0 stub (switch, mode and counters only).
    raw = VeteranReintegrationState(mode="record_only").__getstate__()
    raw = {**raw, "__dict__": {k: raw["__dict__"][k] for k in ("schema_version", "enabled", "mode", "counters")},
           "__pydantic_private__": None}
    old = VeteranReintegrationState.__new__(VeteranReintegrationState)
    old.__setstate__(raw)
    assert old.records == [] and old.frame is None and old._captures == [] and old.mode == "record_only"
    assert OUTCOMES[-1] == "pool_reset" and CAUSES[-1] == "dissolved"
    assert P.MIN_ARMY == 3                                 # the destroyed-army case above relies on it
    assert build_context(world).bridge is bridge
