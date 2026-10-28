"""Bounded attendance, explicit costs, calendar identity and intervention arms."""
from __future__ import annotations

import json
import pyarrow as pa
import pytest

from chronicler import ritual_gatherings as R
from chronicler.accumulator import StatAccumulator
from chronicler.contact_ledger import ContactLedgerState, update_contact_ledger
from chronicler.economy import EconomyResult, FIXED_GOODS
from chronicler.ffi_constants import BOND_FRIEND, BOND_GRUDGE, BOND_KIN, BOND_MARRIAGE, BOND_RIVAL
from chronicler.models import AgentEventRecord, FaithRecord, WorldState
from chronicler.ritual_gatherings_state import RitualGatheringState
from chronicler.turn_artifacts import AgentRows, Phase10Inputs, Stamp
from chronicler.world_gen import generate_world

RID = 2  # Verdant Plains, realm 2 in the template


def _snapshot(n=40, *, rid=RID, start=1, beliefs=None, age=30):
    return pa.record_batch({
        "id": pa.array(range(start, start + n), type=pa.uint32()),
        "region": pa.array([rid] * n, type=pa.uint16()),
        "age": pa.array([age] * n, type=pa.uint16()),
        "belief": pa.array(beliefs if beliefs is not None else [255] * n, type=pa.uint8()),
    })


def _edge_batch(edges=()):
    columns = ("agent_id", "target_id", "sentiment", "bond_type", "formed_turn")
    types = (pa.uint32(), pa.uint32(), pa.int8(), pa.uint8(), pa.uint16())
    return pa.record_batch({k: pa.array([e[i] for e in edges], type=t)
                            for i, (k, t) in enumerate(zip(columns, types))})


class Bridge:
    def __init__(self, world, snapshot=None, edges=(), *, committed=0):
        self.snapshot = _snapshot() if snapshot is None else snapshot
        self.edges = _edge_batch(edges)
        self._sim = self
        self.world = world
        self.committed = committed
        self.reads = self.graph_reads = self.commitment_reads = 0
        self.ops = []

    def get_snapshot(self):
        self.reads += 1
        return self.snapshot

    def get_all_relationships(self):
        self.graph_reads += 1
        return self.edges

    def get_stockpile_commitments(self):
        self.commitment_reads += 1
        rows = [(rid, slot, self.committed if rid == RID and g == "grain" else 0, 0)
                for rid in range(len(self.world.regions)) for slot, g in enumerate(FIXED_GOODS)]
        keys = ("region_id", "good_slot", "reserved", "pending_departure")
        types = (pa.uint16(), pa.uint8(), pa.float64(), pa.float64())
        return pa.record_batch({k: pa.array([r[i] for r in rows], type=t)
                                for i, (k, t) in enumerate(zip(keys, types))})

    def apply_relationship_ops(self, ops):
        self.ops.extend(ops)


def _world():
    w = generate_world(seed=42)
    w.agent_mode = "hybrid"
    w.turn = R.SEASON_STEP
    R.set_ritual_gatherings_enabled(w, True)
    w.contact_ledger = ContactLedgerState()
    for c in w.civilizations:
        c.treasury = 100
    for region in w.regions:
        region.stockpile.goods["grain"] = 100.0
    return w


def _economy(w, *, suff=1.0, demand=20.0):
    result = EconomyResult()
    for region in w.regions:
        result.food_sufficiency[region.name] = suff
        result.market_demand[region.name] = (demand, 0.0, 0.0, 0.0)
    return result


def _tick(w, bridge=None, economy=None, acc=None, phase10=None):
    bridge = Bridge(w) if bridge is None else bridge
    events = R.tick_ritual_gatherings(w, acc, phase10=phase10, agent_bridge=bridge,
                                    economy_result=_economy(w) if economy is None else economy)
    return events, bridge


def _outcome(w, rid=RID):
    return next(o for o in w.ritual_gatherings.outcomes if o.region == rid)


def _migration(w, aid=1, source=3, target=RID, turn=None):
    return AgentEventRecord(turn=w.turn if turn is None else turn, agent_id=aid, event_type="migration",
                            region=source, target_region=target, civ_affinity=2, occupation=0)


def test_defaults_old_saves_switch_and_dormancy():
    w = generate_world(seed=42)
    before = w.model_dump_json()
    assert not R.DEFAULT_ENABLED_FOR_NEW_WORLDS
    assert w.ritual_gatherings is None
    assert "ritual_gatherings" not in json.loads(before)
    assert R.tick_ritual_gatherings(w) == []
    assert w.model_dump_json() == before
    R.set_ritual_gatherings_enabled(w, True)
    state = w.ritual_gatherings
    R.set_ritual_gatherings_enabled(w, True)
    assert w.ritual_gatherings is state
    for mode in (None, "off", "shadow", "demographics-only"):
        w.agent_mode = mode
        before = w.model_dump_json()
        assert not R.ritual_gatherings_active(w)
        assert R.tick_ritual_gatherings(w) == []
        assert R.snapshot_summary(w) == {}
        assert w.model_dump_json() == before
    R.set_ritual_gatherings_enabled(w, False)
    assert w.ritual_gatherings is None


def test_real_costs_caps_and_no_stat_or_population_bonus():
    w = _world()
    before = [(c.population, c.stability, c.asabiya, c.culture) for c in w.civilizations]
    region_pop = [r.population for r in w.regions]
    events, bridge = _tick(w)
    out = _outcome(w)
    assert out.status == "held" and out.attendee_ids == list(range(1, 33))
    assert out.food == 1.6 and out.funds == 3
    assert out.grain_before == 100 and out.grain_after == pytest.approx(98.4)
    assert out.funds_before == 100 and out.funds_after == 97
    assert w.civilizations[out.host].treasury == 97
    assert out.bond_ops == len(bridge.ops) == 8
    assert all(op["bond_type"] == BOND_FRIEND and op["op_type"] == 1 for op in bridge.ops)
    assert len({aid for op in bridge.ops for aid in (op["agent_a"], op["agent_b"])}) == 16
    assert out.contact_units == 0 and out.arrivals == []
    assert bridge.reads == bridge.graph_reads == bridge.commitment_reads == 1
    assert [(c.population, c.stability, c.asabiya, c.culture) for c in w.civilizations] == before
    assert [r.population for r in w.regions] == region_pop
    assert [e.event_type for e in events] == ["harvest_gathering_held"]


def test_row_order_does_not_change_selection_cost_or_ops():
    a, b = _world(), _world()
    source = _snapshot(80)
    reverse = source.take(pa.array(list(reversed(range(80))), type=pa.int32()))
    _, ba = _tick(a, Bridge(a, source))
    _, bb = _tick(b, Bridge(b, reverse))
    assert a.ritual_gatherings == b.ritual_gatherings
    assert ba.ops == bb.ops


def test_attendance_is_current_local_alive_adults_no_birth_origin():
    w = _world()
    rows = pa.concat_batches([_snapshot(5, start=1, age=5), _snapshot(4, start=50),
                              _snapshot(5, start=90, rid=3)])
    _, bridge = _tick(w, Bridge(w, rows))
    assert _outcome(w).attendee_ids == [50, 51, 52, 53]
    assert _outcome(w, 3).attendee_ids == [90, 91, 92, 93, 94]
    assert all(op["agent_a"] >= 50 for op in bridge.ops)


@pytest.mark.parametrize("reason", ["shortage", "occupied", "food", "funds", "unmeasured_food", "no_host"])
def test_cancelled_gatherings_have_no_cost_bond_or_extra_contact(reason):
    w = _world()
    e = _economy(w)
    r = w.regions[RID]
    if reason == "shortage":
        e.food_sufficiency[r.name] = 0.8
    elif reason == "occupied":
        r.occupied_by = w.civilizations[0].name
    elif reason == "food":
        r.stockpile.goods["grain"] = 40
    elif reason == "funds":
        w.civilizations[w.civ_index_map[r.controller]].treasury = 2
    elif reason == "unmeasured_food":
        e.market_demand = {}
    elif reason == "no_host":
        r.controller = None
    w.agent_events_raw.append(_migration(w))
    grain = r.stockpile.goods["grain"]
    money = [c.treasury for c in w.civilizations]
    _, bridge = _tick(w, economy=e)
    out = _outcome(w)
    assert out.status == "cancelled" and out.reason == reason
    assert out.food == out.funds == out.contact_units == out.bond_ops == 0
    assert out.attendee_ids == out.arrivals == []
    assert out.grain_before is out.funds_before is None
    assert r.stockpile.goods["grain"] == grain
    assert [c.treasury for c in w.civilizations] == money
    assert bridge.ops == [] and bridge.graph_reads == 0
    assert w._contact_pending is None


def test_merchant_commitments_are_not_available_for_gathering_food():
    w = _world()
    _, _bridge = _tick(w, Bridge(w, committed=60))
    assert _outcome(w).reason == "food"
    assert w.regions[RID].stockpile.goods["grain"] == 100


def test_current_shortfall_overrides_optimistic_sufficiency():
    w = _world()
    w.regions[RID].food_shortfall = 0.1
    _tick(w)
    assert _outcome(w).reason == "shortage"


def test_projected_keep_treasury_prevents_overspending_and_is_applied_once():
    w = _world()
    ci = w.civ_index_map[w.regions[RID].controller]
    acc = StatAccumulator()
    acc.add(ci, w.civilizations[ci], "treasury", -98, "keep")
    _tick(w, acc=acc)
    assert _outcome(w).reason == "funds"
    acc.apply_keep(w)
    assert w.civilizations[ci].treasury == 2
    w = _world()
    acc = StatAccumulator()
    acc.add(ci, w.civilizations[ci], "treasury", -10, "keep")
    _tick(w, acc=acc)
    out = _outcome(w)
    assert out.funds_before == 90 and out.funds_after == 87
    assert w.civilizations[ci].treasury == 100
    acc.apply_keep(w)
    acc.apply_keep(w)
    assert w.civilizations[ci].treasury == 87


def test_regions_of_one_host_share_exact_remaining_treasury():
    w = _world()
    ci = w.civ_index_map[w.regions[RID].controller]
    assert w.regions[4].controller == w.regions[RID].controller
    w.civilizations[ci].treasury = 3
    batch = pa.concat_batches([_snapshot(), _snapshot(rid=4, start=101)])
    _tick(w, Bridge(w, batch))
    assert _outcome(w).status == "held" and _outcome(w, 4).reason == "funds"
    assert w.civilizations[ci].treasury == 0


def test_dated_arrivals_only_contact_capped_and_cleared():
    w = _world()
    w.agent_events_raw.extend([_migration(w, aid=i) for i in range(1, 21)])
    # No exposure from a nonattendee, another year or an ambiguous multi-move.
    w.agent_events_raw.extend([_migration(w, aid=1000), _migration(w, aid=31, turn=7),
                               _migration(w, aid=32), _migration(w, aid=32, source=4)])
    _tick(w)
    out = _outcome(w)
    assert len(out.arrivals) == 20 and out.contact_units == 8
    assert len(w._contact_pending) == 8
    update_contact_ledger(w)
    assert w._contact_pending is None
    # Ordinary migration and extra gathering exposure remain separate channels.
    edge = w.contact_ledger.edge_map()[(3, RID)]
    assert edge[1] >= 20 and edge[3] == 8
    w.turn += 1
    _tick(w)
    assert w.ritual_gatherings.outcomes == []
    update_contact_ledger(w)
    assert w.contact_ledger.last_inflow[3] == 0
    assert w.contact_ledger.edge_map()[(3, RID)][3] == pytest.approx(7.2)


@pytest.mark.parametrize("contact,bonds", [(False, False), (False, True), (True, False), (True, True)])
def test_cost_only_no_contact_and_no_bond_controls(contact, bonds):
    w = _world()
    w.ritual_gatherings.contact_enabled = contact
    w.ritual_gatherings.bonds_enabled = bonds
    w.agent_events_raw.append(_migration(w))
    _events, bridge = _tick(w)
    out = _outcome(w)
    assert out.food == 1.6 and out.funds == 3 and len(out.attendee_ids) == 32
    assert out.arrivals == [(1, 3)]
    assert out.contact_units == (1 if contact else 0)
    assert out.bond_ops == (8 if bonds else 0)
    assert len(bridge.ops) == out.bond_ops
    assert bridge.graph_reads == int(bonds)


def test_contact_off_does_not_disable_ordinary_migration_contact():
    w = _world()
    w.ritual_gatherings.contact_enabled = False
    w.agent_events_raw.append(_migration(w))
    _tick(w)
    update_contact_ledger(w)
    assert w.contact_ledger.last_inflow == [0, 1, 0, 0]


def test_contact_ledger_off_never_queues_fictional_exposure():
    w = _world()
    w.contact_ledger = None
    w.agent_events_raw.append(_migration(w))
    _tick(w)
    assert _outcome(w).contact_units == 0 and w._contact_pending is None


def test_eligible_bonds_skip_hostility_full_endpoints_and_strengthen_only():
    attendees = [(k, 255) for k in range(1, 13)]
    edges = {i: [] for i, _ in attendees}
    edges[1] = [(2, 10, BOND_RIVAL, 1)]
    edges[3] = [(4, 1, BOND_GRUDGE, 1)]
    edges[5] = [(6, -5, BOND_FRIEND, 1)]
    edges[7] = [(100 + i, 30, BOND_KIN if i % 2 else BOND_MARRIAGE, 1) for i in range(8)]
    edges[9] = [(10, 60, BOND_FRIEND, 1)]
    edges[10] = [(9, 45, BOND_FRIEND, 1)]
    ops = R._bond_ops(attendees, edges, 8)
    assert [(o["agent_a"], o["agent_b"]) for o in ops] == [(9, 10), (11, 12)]
    assert ops[0]["sentiment"] == 60 and ops[1]["sentiment"] == 20
    assert R._bond_ops(attendees, edges, 65536) == []


def test_same_turn_reentry_and_conquest_cannot_repeat_calendar():
    w = _world()
    _, bridge = _tick(w)
    before = w.model_dump_json()
    assert R.tick_ritual_gatherings(w, agent_bridge=bridge, economy_result=_economy(w)) == []
    assert w.model_dump_json() == before
    old = next(s for s in w.ritual_gatherings.schedules if s.region == RID)
    identity = old.gathering_id
    new = w.civilizations[0]
    oldhost = w.civilizations[w.civ_index_map[w.regions[RID].controller]]
    oldhost.regions.remove(w.regions[RID].name)
    new.regions.append(w.regions[RID].name)
    w.regions[RID].controller = new.name
    w.turn = 9
    _tick(w, bridge)
    assert old.next_turn == 20 and old.gathering_id == identity and old.last_turn == 8
    assert w.ritual_gatherings.outcomes == []
    w.turn = 20
    events, _ = _tick(w, bridge)
    assert _outcome(w).host == 0 and _outcome(w).gathering_id == identity
    assert old.last_turn == 20 and old.next_turn == 32
    assert any(e.event_type == "harvest_gathering_held" for e in events)


def test_occurrences_use_resource_calendar_not_every_simulation_turn():
    w = _world()
    w.turn = 0
    bridge = Bridge(w)
    for turn in range(25):
        w.turn = turn
        _tick(w, bridge)
        if turn not in (8, 20):
            assert w.ritual_gatherings.outcomes == []
    assert bridge.reads == 2
    assert w.ritual_gatherings.counters["held"] == 2


def test_routine_held_and_unchanged_cancellation_do_not_spam_narration():
    w = _world()
    events, bridge = _tick(w)
    assert len(events) == 1
    w.turn = 20
    assert _tick(w, bridge)[0] == []
    w.turn = 32
    bad = _economy(w, suff=0.5)
    assert len(_tick(w, bridge, bad)[0]) == 1
    w.turn = 44
    assert _tick(w, bridge, bad)[0] == []
    w.turn = 56
    assert len(_tick(w, bridge)[0]) == 1


def test_summary_is_completed_turn_only_and_freezes_recorded_names():
    w = _world()
    _tick(w)
    host_name = _outcome(w).host_name
    w.turn = 9
    summary = R.snapshot_summary(w)
    assert summary["source_turn"] == 8 and len(summary["outcomes"]) == len(w.regions)
    w.regions[RID].controller = "a later conqueror"
    assert next(o for o in R.snapshot_summary(w)["outcomes"] if o["region"] == RID)["host_name"] == host_name
    w.turn = 10
    assert R.snapshot_summary(w)["outcomes"] == []
    assert summary["outcomes"] != []  # detached historical receipt


def test_save_resume_preserves_calendar_controls_and_no_pending_replay():
    w = _world()
    w.ritual_gatherings.contact_enabled = False
    w.agent_events_raw.append(_migration(w))
    _tick(w)
    w.turn += 1
    restored = WorldState.model_validate_json(w.model_dump_json())
    assert restored.ritual_gatherings == w.ritual_gatherings
    assert restored._contact_pending is None
    for turn in range(9, 22):
        w.turn = restored.turn = turn
        ea, ba = _tick(w)
        eb, bb = _tick(restored)
        assert ea == eb and ba.ops == bb.ops
        assert restored.ritual_gatherings == w.ritual_gatherings
        assert [r.stockpile.goods for r in restored.regions] == [r.stockpile.goods for r in w.regions]
        assert [c.treasury for c in restored.civilizations] == [c.treasury for c in w.civilizations]


def test_faith_slot_reuse_is_dated_without_resetting_regional_schedule():
    w = _world()
    w.faiths = [FaithRecord(name="Old harvest church", slot=0, founded_turn=0)]
    _tick(w, Bridge(w, _snapshot(8, beliefs=[0] * 8)))
    first = _outcome(w).model_copy(deep=True)
    schedule = next(s for s in w.ritual_gatherings.schedules if s.region == RID)
    assert first.faith == 0 and first.faith_name == "Old harvest church"
    w.faiths[0].released_turn = 15
    w.faiths.append(FaithRecord(name="New church in recycled slot", slot=0, founded_turn=15))
    w.turn = 20
    _tick(w, Bridge(w, _snapshot(8, beliefs=[0] * 8)))
    later = _outcome(w)
    assert later.faith == 1 and later.faith_name == "New church in recycled slot"
    assert later.gathering_id == first.gathering_id == schedule.gathering_id
    assert schedule.next_turn == 32 and first.faith_name == "Old harvest church"


def test_faith_plurality_ties_use_permanent_identity_order():
    w = _world()
    w.faiths = [FaithRecord(name="First", slot=1), FaithRecord(name="Second", slot=0)]
    _tick(w, Bridge(w, _snapshot(4, beliefs=[0, 1, 0, 1])))
    assert _outcome(w).faith == 0 and _outcome(w).faith_name == "First"


def test_cancelled_occurrence_retains_calendar_and_does_not_catch_up():
    w = _world()
    _tick(w, economy=_economy(w, suff=0.5))
    schedule = next(s for s in w.ritual_gatherings.schedules if s.region == RID)
    assert schedule.next_turn == 20
    w.turn = 9
    _tick(w)
    assert w.ritual_gatherings.outcomes == []
    assert w.regions[RID].stockpile.goods["grain"] == 100
    w.turn = 44  # missed turn 20/32 does not replay two expenses
    _tick(w)
    assert _outcome(w).food == 1.6 and w.ritual_gatherings.counters["held"] == 1
    assert schedule.next_turn == 56


def test_presence_uses_current_bridge_instead_of_stale_phase10_capture():
    w = _world()
    old = _snapshot(2, start=1)
    economy = _economy(w)
    phase = Phase10Inputs(source_turn=w.turn,
                          agents=AgentRows(Stamp(w.turn, "phase10_entry"), old),
                          named_agents={}, economy=economy, deaths=())
    _tick(w, Bridge(w, _snapshot(2, start=11)), economy=economy, phase10=phase)
    assert _outcome(w).attendee_ids == [11, 12]


def test_input_stamp_rejected_before_costs_or_state_mutation():
    w = _world()
    batch = _snapshot()
    phase = Phase10Inputs(source_turn=7, agents=AgentRows(Stamp(7, "phase10_entry"), batch),
                          named_agents={}, economy=None, deaths=())
    before = w.model_dump_json()
    with pytest.raises(ValueError, match="source turn"):
        _tick(w, phase10=phase)
    assert w.model_dump_json() == before


@pytest.mark.parametrize("bad", ["missing", "duplicate", "null"])
def test_malformed_snapshot_cannot_charge_a_gathering(bad):
    w = _world()
    batch = _snapshot(2)
    if bad == "missing":
        batch = batch.drop_columns(["age"])
    elif bad == "duplicate":
        batch = batch.set_column(0, "id", pa.array([1, 1], type=pa.uint32()))
    else:
        batch = batch.set_column(0, "id", pa.array([None, 2], type=pa.uint32()))
    grain = w.regions[RID].stockpile.goods["grain"]
    with pytest.raises(ValueError, match="snapshot"):
        _tick(w, Bridge(w, batch))
    assert w.regions[RID].stockpile.goods["grain"] == grain
    assert all(c.treasury == 100 for c in w.civilizations)
