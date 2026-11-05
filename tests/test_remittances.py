"""RS4 diaspora ledger and remittances: offline contract (no native extension).

A small fake stands in for the post-tick native pool (snapshot, trips,
relationships) and for ``wealth_transfer::remit`` with its rules; the
real-native path is in ``test_remittances_native.py``. Every state here is
constructed.
"""
from __future__ import annotations

import json
import math
import pickle

import pytest

from chronicler import remittances as RM
from chronicler.ffi_constants import BOND_FRIEND, BOND_KIN, BOND_MARRIAGE
from chronicler.livelihoods import (
    configure_livelihoods, livelihoods_feature_flags, livelihoods_snapshot_fields, wrap_agent_tick,
)
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.main import _build_parser
from chronicler.models import AgentEventRecord
from chronicler.remittances_state import (
    CLOSE_REASONS, COUNTERS, MODES, MOVE_KINDS, RECEIPT_STATUSES, SENDER_REASONS, UNLINKED_REASONS,
    RemittancesState,
)
from chronicler.world_gen import generate_world

MAX_WEALTH = 100.0


class Column:
    def __init__(self, values):
        self.values = values

    def to_pylist(self):
        return list(self.values)


class Snapshot:
    def __init__(self, rows):
        self.rows = rows

    def column(self, name):
        return Column([r[name] for r in self.rows])


class FakeSim:
    """People (id -> region, age, displacement, wealth), bonds and the remit rules."""

    def __init__(self):
        self.people: dict[int, dict] = {}
        self.bonds: dict[int, list[tuple[int, int, int, int]]] = {}
        self.trips: set[int] = set()
        self.keys: set[tuple[int, int]] = set()
        self.calls: list = []
        self.vanish_before_remit: set[int] = set()

    def add(self, aid, region, *, age=30, wealth=5.0, displacement=0):
        self.people[aid] = {"id": aid, "region": region, "age": age, "displacement_turn": displacement,
                            "wealth": wealth}

    def bond(self, a, b, kind, sentiment):
        self.bonds.setdefault(a, []).append((b, sentiment, kind, 0))
        self.bonds.setdefault(b, []).append((a, sentiment, kind, 0))

    def kill(self, aid):
        self.people.pop(aid, None)
        self.bonds.pop(aid, None)
        for rows in self.bonds.values():
            rows[:] = [r for r in rows if r[0] != aid]

    def get_snapshot(self):
        return Snapshot([dict(self.people[i]) for i in sorted(self.people)])

    def trip_agent_ids(self):
        return sorted(i for i in self.trips if i in self.people)

    def get_agent_relationships(self, aid):
        return list(self.bonds.get(aid, [])) if aid in self.people else None

    def remit_wealth(self, turn, batch, rows):
        assert (turn, batch) not in self.keys and all(t < turn or b != batch for t, b in self.keys)
        assert len({r[0] for r in rows}) == len(rows)
        self.keys.add((turn, batch))
        self.calls.append((turn, list(rows)))
        for aid in self.vanish_before_remit:
            self.kill(aid)
        out = []
        for s, r, amount, fee in rows:
            if s not in self.people or r not in self.people or s in self.trips or r in self.trips:
                out.append((s, r, 0, 0, 0, 0, 2))
                continue
            asked = amount + fee
            have = math.floor(self.people[s]["wealth"] * 1000)
            sent = min(asked, have)
            fee_paid = fee if sent == asked else sent * fee // asked
            carried = sent - fee_paid
            credited = min(carried, math.floor((MAX_WEALTH - self.people[r]["wealth"]) * 1000))
            refunded = carried - credited
            self.people[s]["wealth"] -= (sent - refunded) / 1000
            self.people[r]["wealth"] += credited / 1000
            out.append((s, r, sent, fee_paid, credited, refunded, 0 if sent == asked and not refunded else 1))
        return out


class FakeBridge:
    def __init__(self, sim):
        self._sim = sim


def _world(mode="send", regions=4):
    world = generate_world(seed=42, num_regions=regions, num_civs=2)
    world.agent_mode = "hybrid"
    configure_livelihoods(world, _build_parser().parse_args(["--remittances", "--remittance-mode", mode]),
                          agent_mode="hybrid")
    return world


def step(world, sim, moves=(), deaths=(), between=None):
    """One constructed tick: apply moves (displacement 5) and deaths, count
    displacement down as the native tick does, record the events, then run
    the after-tick hook and close the turn."""
    for aid, frm, to in moves:
        assert sim.people[aid]["region"] == frm
        sim.people[aid]["region"] = to
        sim.people[aid]["displacement_turn"] = 5
        world.agent_events_raw.append(AgentEventRecord(world.turn, aid, "migration", frm, to, 0, 0))
    for aid in deaths:
        sim.kill(aid)
        world.agent_events_raw.append(AgentEventRecord(world.turn, aid, "death", 0, 0, 0, 0))
    for p in sim.people.values():
        if p["displacement_turn"] > 0:
            p["displacement_turn"] -= 1
    if between is not None:
        between()
    RM.after_agent_tick(world, FakeBridge(sim))
    world.turn += 1
    return world.livelihoods.remittances


def settle(world, sim, turns):
    for _ in range(turns):
        state = step(world, sim)
    return state


def family():
    """Migrant 10 (0 -> 1) with a spouse 20 and kin 21, 22 at home in region 0."""
    sim = FakeSim()
    sim.add(10, 0, wealth=7.0)
    sim.add(20, 0, wealth=1.0)
    sim.add(21, 0, wealth=1.0)
    sim.add(22, 0, wealth=1.0)
    sim.bond(10, 20, BOND_MARRIAGE, 30)
    sim.bond(10, 21, BOND_KIN, 90)
    sim.bond(10, 22, BOND_KIN, 90)
    return sim


# --- Wiring, observation, feature off ------------------------------------------


def test_switch_requires_hybrid_and_is_absent_when_never_enabled():
    world = generate_world(seed=42, num_regions=4, num_civs=2)
    with pytest.raises(ValueError, match="hybrid"):
        configure_livelihoods(world, _build_parser().parse_args(["--remittances"]), agent_mode="shadow")
    assert world.livelihoods is None and livelihoods_snapshot_fields(world) == {}
    configure_livelihoods(world, _build_parser().parse_args(["--no-remittances"]), agent_mode="hybrid")
    assert world.livelihoods is None
    world = _world("record_only")
    assert MODES == ("send", "record_only") and world.livelihoods.remittances.mode == "record_only"
    assert livelihoods_feature_flags(world) == {"remittances": True}
    world.agent_mode = "shadow"
    assert not RM.remittances_active(world)


def test_an_unobserved_turn_is_unknown_not_zero():
    world = _world()
    fields = livelihoods_snapshot_fields(world)["livelihoods"]["remittances"]
    assert fields["stage"] == "RS4" and fields["source_turn"] == world.turn - 1
    for key in ("funnel", "totals", "regions", "moves", "closures", "receipts", "unmet"):
        assert fields[key] is None, key
    assert fields["counters"] == {} and fields["last_pool_reset"] is None


# --- The ledger ------------------------------------------------------------------


def test_the_ledger_records_departure_onward_return_and_death_separately_per_region():
    world, sim = _world(), FakeSim()
    for aid in (1, 2, 3):
        sim.add(aid, 0)
    state = step(world, sim, moves=[(1, 0, 1), (2, 0, 1), (3, 0, 2)])
    assert [(e.id, e.origin, e.destination, e.departure_turn, e.arrival_turn) for e in state.entries] == \
        [(1, 0, 1, 0, 0), (2, 0, 1, 0, 0), (3, 0, 2, 0, 0)]
    regions = {r.region: r for r in state.regions}
    assert (regions[0].departures, regions[0].arrivals, regions[0].diaspora_out) == (3, 0, 3)
    assert (regions[1].arrivals, regions[1].departures, regions[1].diaspora_in) == (2, 0, 2)
    assert [m.kind for m in state.moves] == ["departure"] * 3
    # Onward: 2 moves on to region 3; the origin is kept.
    state = step(world, sim, moves=[(2, 1, 3)])
    e2 = next(e for e in state.entries if e.id == 2)
    assert (e2.origin, e2.destination, e2.arrival_turn, e2.moves) == (0, 3, 1, 2)
    regions = {r.region: r for r in state.regions}
    assert (regions[1].departures, regions[3].arrivals, regions[1].diaspora_in, regions[3].diaspora_in) == (1, 1, 1, 1)
    assert state.moves[0].kind == "onward"
    # Return: 1 goes home and its entry closes; 3 dies in the tick.
    state = step(world, sim, moves=[(1, 1, 0)], deaths=[3])
    assert [e.id for e in state.entries] == [2]
    assert [(c.id, c.reason, c.closed_turn) for c in state.closures] == [(1, "return", 2), (3, "death", 2)]
    regions = {r.region: r for r in state.regions}
    assert (regions[0].arrivals, regions[0].returns_home, regions[1].departures) == (1, 1, 1)
    assert regions[0].diaspora_out == 1 and regions[3].diaspora_in == 1 and 2 not in regions
    c = state.counters
    assert (c["departures"], c["onward_moves"], c["returns"], c["deaths"], c["moves_seen"]) == (3, 1, 1, 1, 5)
    # A return is a closure, so a later move from home opens a fresh entry.
    state = step(world, sim, moves=[(1, 0, 2)])
    e1 = next(e for e in state.entries if e.id == 1)
    assert (e1.origin, e1.departure_turn, e1.moves) == (0, 3, 1)


def test_the_ledger_is_bounded_and_refuses_new_departures_when_full(monkeypatch):
    monkeypatch.setattr(RM, "MAX_ENTRIES", 2)
    world, sim = _world(), FakeSim()
    for aid in (1, 2, 3):
        sim.add(aid, 0)
    state = step(world, sim, moves=[(1, 0, 1), (2, 0, 1), (3, 0, 1)])
    assert [e.id for e in state.entries] == [1, 2]
    assert state.moves[2].kind == "unrecorded" and state.counters["entries_refused"] == 1
    # Region flows still count every applied move.
    assert {r.region: r.arrivals for r in state.regions}[1] == 3


def test_knowledge_flow_counts_qualified_movers_at_both_ends(monkeypatch):
    import chronicler.apprenticeship as A
    assert A.qualified_ids(None, 0) == []           # the RS0 stub until RS1 lands
    world, sim = _world(), FakeSim()
    for aid in (1, 2):
        sim.add(aid, 0)
    monkeypatch.setattr(A, "qualified_ids", lambda w, region: [1] if sim.people[1]["region"] == region else [])
    state = step(world, sim, moves=[(1, 0, 1), (2, 0, 1)])
    regions = {r.region: r for r in state.regions}
    assert (regions[0].qualified_departures, regions[1].qualified_arrivals) == (1, 1)
    assert (regions[0].qualified_out, regions[1].qualified_in) == (1, 1)
    assert [m.qualified for m in state.moves] == [True, False]
    assert state.funnel["ledger_qualified"] == 1
    state = step(world, sim, moves=[(1, 1, 0)])
    assert state.counters["qualified_returns"] == 1 and state.funnel["ledger_qualified"] == 0


def test_pool_reset_closes_every_entry_dated_and_is_silent_when_empty():
    world, sim = _world(), FakeSim()
    RM.on_pool_reset(world)                          # a fresh run binds its pool: nothing to close
    assert world.livelihoods.remittances.counters == {}
    sim.add(1, 0)
    step(world, sim, moves=[(1, 0, 1)])
    RM.on_pool_reset(world)
    state = world.livelihoods.remittances
    assert state.entries == [] and state.counters["pool_resets"] == 1
    assert state.last_pool_reset.model_dump() == {"turn": 1, "entries_closed": 1,
                                                  "reason": "native pool rebuilt: saved stable ids name other people"}


def test_an_unobserved_gap_closes_the_ledger():
    world, sim = _world(), FakeSim()
    sim.add(1, 0)
    step(world, sim, moves=[(1, 0, 1)])
    world.turn += 3                                   # the switch was off for three turns
    state = step(world, sim)
    assert state.entries == [] and [(c.id, c.reason) for c in state.closures] == [(1, "unobserved_gap")]
    assert state.counters["gap_closures"] == 1


# --- Remittances -------------------------------------------------------------------


def test_a_settled_migrant_sends_to_the_spouse_first_with_a_courier_fee():
    world, sim = _world(), family()
    state = step(world, sim, moves=[(10, 0, 1)])
    assert state.receipts == [] and state.funnel["unsettled"] == 1
    for _ in range(RM.SETTLED_TURNS - 1):
        state = step(world, sim)
        assert state.receipts == [], world.turn
    state = step(world, sim)
    r = state.receipts[0]
    # 7.0 wealth: 10% of 5.0 above the reserve = 500, fee 75, amount 425.
    assert (r.sender, r.recipient, r.bond, r.sentiment, r.origin, r.destination) == (10, 20, "marriage", 30, 0, 1)
    assert (r.amount, r.fee_requested, r.sent, r.fee, r.credited, r.refunded, r.status) == \
        (425, 75, 500, 75, 425, 0, "applied")
    assert sim.people[10]["wealth"] == pytest.approx(6.5) and sim.people[20]["wealth"] == pytest.approx(1.425)
    regions = {x.region: x for x in state.regions}
    assert (regions[1].senders, regions[1].outflow_milli, regions[1].fee_milli) == (1, 500, 75)
    assert (regions[0].recipients, regions[0].inflow_milli) == (1, 425)
    t = state.totals
    assert t["debited_milli"] == t["credited_milli"] + t["fee_milli"] == 500 and t["refunded_milli"] == 0
    entry = state.entries[0]
    assert (entry.last_sent_turn, entry.sent_turns, entry.credited_milli) == (RM.SETTLED_TURNS, 1, 425)
    # Without the spouse (death sweeps the bond): the highest sentiment, then the lowest id.
    state = step(world, sim, deaths=[20])
    assert state.receipts[0].recipient == 21 and state.receipts[0].bond == "kin"


def test_recipient_order_is_spouse_then_sentiment_then_id():
    alive = {1: (0, 30, 0, 0), 2: (0, 30, 0, 0), 3: (0, 30, 0, 0), 4: (1, 30, 0, 0)}
    bonds = [(3, 50, BOND_KIN, 0), (2, 50, BOND_KIN, 0), (1, 20, BOND_MARRIAGE, 0), (4, 99, BOND_KIN, 0)]
    assert RM.choose_recipient(bonds, 0, alive, set()) == ((1, "marriage", 20), None)
    assert RM.choose_recipient(bonds[:2], 0, alive, set()) == ((2, "kin", 50), None)
    assert RM.choose_recipient(bonds[:2] + [(1, 60, BOND_KIN, 0)], 0, alive, set())[0][0] == 1
    assert RM.choose_recipient([(1, 19, BOND_MARRIAGE, 0), (2, 99, BOND_FRIEND, 0)], 0, alive, set()) == \
        (None, "no_bond")
    assert RM.choose_recipient([(4, 99, BOND_KIN, 0), (9, 99, BOND_KIN, 0)], 0, alive, set()) == \
        (None, "recipient_away")
    assert RM.choose_recipient(bonds[:3], 0, alive, {1, 2, 3}) == (None, "recipient_on_trip")
    assert RM.choose_recipient(bonds[:3], 0, alive, {1}) == ((2, "kin", 50), None)
    assert RM.choose_recipient(None, 0, alive, set()) == (None, "no_bond")


def test_amounts_follow_the_reserve_share_cap_and_fee():
    assert RM.remittance_amount(2000) == (0, 0)
    assert RM.remittance_amount(1500) == (0, 0)
    assert RM.remittance_amount(3000) == (85, 15)
    assert RM.remittance_amount(7000) == (425, 75)
    assert RM.remittance_amount(12_000) == (850, 150)          # capped at one unit
    assert RM.remittance_amount(100_000) == (850, 150)
    assert RM.remittance_amount(2_009) == (0, 0)               # 0.9 milli rounds to nothing


def test_unmet_and_ineligible_migrants_are_recorded_with_reasons():
    world, sim = _world(), FakeSim()
    sim.add(1, 0, wealth=9.0)                         # no bond at all
    sim.add(2, 0, wealth=9.0)                         # kin moved away too
    sim.add(3, 0, wealth=9.0)                         # spouse on a trip
    sim.add(4, 0, wealth=9.0, age=12)                 # a child migrant
    sim.add(5, 0, wealth=9.0)                         # on a trip itself
    sim.add(6, 0, wealth=1.5)                         # linked, below the reserve
    sim.add(30, 2)                                    # 2's kin lives elsewhere
    sim.add(31, 0)
    sim.add(32, 0)
    sim.add(33, 0)
    sim.bond(2, 30, BOND_KIN, 80)
    sim.bond(3, 31, BOND_MARRIAGE, 80)
    sim.bond(5, 32, BOND_KIN, 80)
    sim.bond(6, 33, BOND_KIN, 80)
    step(world, sim, moves=[(i, 0, 1) for i in (1, 2, 3, 4, 5, 6)])
    sim.trips |= {31, 5}
    state = settle(world, sim, RM.SETTLED_TURNS)
    f = state.funnel
    assert (f["eligible"], f["linked"], f["no_bond"], f["recipient_away"], f["recipient_on_trip"]) == (4, 1, 1, 1, 1)
    assert (f["child"], f["on_trip"], f["no_surplus"], f["rows"]) == (1, 1, 1, 0)
    assert [(u.id, u.reason, u.surplus_milli) for u in state.unmet] == \
        [(1, "no_bond", 7000), (2, "recipient_away", 7000), (3, "recipient_on_trip", 7000)]
    assert state.receipts == [] and sim.calls == []
    assert set(f) >= set(SENDER_REASONS) | set(UNLINKED_REASONS)


def test_record_only_computes_the_same_rows_and_moves_nothing():
    results = {}
    for mode in MODES:
        world, sim = _world(mode), family()
        step(world, sim, moves=[(10, 0, 1)])
        state = settle(world, sim, RM.SETTLED_TURNS)
        results[mode] = (state.model_copy(deep=True), {i: p["wealth"] for i, p in sim.people.items()}, sim)
    sent, control = results["send"][0], results["record_only"][0]
    keys = ("sender", "recipient", "bond", "amount", "fee_requested", "wealth_milli")
    assert [r.model_dump(include=set(keys)) for r in sent.receipts] == \
        [r.model_dump(include=set(keys)) for r in control.receipts]
    r = control.receipts[0]
    assert (r.status, r.sent, r.fee, r.credited, r.refunded) == ("not_sent", 0, 0, 0, 0)
    assert results["record_only"][1] == {10: 7.0, 20: 1.0, 21: 1.0, 22: 1.0}
    assert results["record_only"][2].calls == []
    assert control.totals["not_sent_milli"] == 500 and control.totals["debited_milli"] == 0
    assert control.counters["rows_not_sent"] == 1 and "rows_applied" not in control.counters


def test_a_ceiling_refund_goes_back_to_the_sender_and_balances_exactly():
    world, sim = _world(), FakeSim()
    sim.add(10, 0, wealth=12.0)
    sim.add(20, 0, wealth=99.7)
    sim.bond(10, 20, BOND_KIN, 40)
    step(world, sim, moves=[(10, 0, 1)])
    state = settle(world, sim, RM.SETTLED_TURNS)
    r = state.receipts[0]
    assert (r.amount, r.fee_requested, r.sent, r.fee) == (850, 150, 1000, 150)
    assert r.credited == math.floor((MAX_WEALTH - 99.7) * 1000) and r.refunded == 850 - r.credited
    assert r.status == "limited" and r.sent == r.fee + r.credited + r.refunded
    assert sim.people[10]["wealth"] == pytest.approx(12.0 - (r.fee + r.credited) / 1000)
    t = state.totals
    assert t["sent_milli"] == t["debited_milli"] + t["refunded_milli"]
    assert {x.region: x.refunded_milli for x in state.regions}[1] == r.refunded


def test_a_party_gone_before_the_transfer_is_absent_and_nothing_moves():
    world, sim = _world(), family()
    step(world, sim, moves=[(10, 0, 1)])
    settle(world, sim, RM.SETTLED_TURNS - 1)
    sim.vanish_before_remit = {20}
    state = step(world, sim)
    r = state.receipts[0]
    assert (r.status, r.sent, r.credited, r.fee) == ("absent", 0, 0, 0)
    assert sim.people[10]["wealth"] == 7.0
    assert state.counters["rows_absent"] == 1 and state.totals["debited_milli"] == 0
    assert state.entries[0].sent_turns == 0 and state.entries[0].credited_milli == 0


def test_a_returning_or_dead_sender_sends_nothing():
    world, sim = _world(), family()
    step(world, sim, moves=[(10, 0, 1)])
    settle(world, sim, RM.SETTLED_TURNS - 1)
    state = step(world, sim, moves=[(10, 1, 0)])       # home again on the turn it would send
    assert state.receipts == [] and state.entries == [] and state.closures[0].reason == "return"
    world, sim = _world(), family()
    step(world, sim, moves=[(10, 0, 1)])
    settle(world, sim, RM.SETTLED_TURNS - 1)
    state = step(world, sim, deaths=[10])
    assert state.receipts == [] and state.closures[0].reason == "death" and sim.calls == []


def test_settlement_is_once_per_turn_and_resumes_exactly():
    world, sim = _world(), family()
    step(world, sim, moves=[(10, 0, 1)])
    settle(world, sim, RM.SETTLED_TURNS)
    state = world.livelihoods.remittances
    world.turn -= 1                                    # replaying a settled turn is refused
    with pytest.raises(RuntimeError, match="already settled"):
        RM.after_agent_tick(world, FakeBridge(sim))
    world.turn += 1
    assert len(sim.calls) == 1
    # A JSON or pickle round trip (an exact checkpoint) continues identically.
    text = world.livelihoods.model_dump_json()
    back = LivelihoodsState.model_validate_json(text)
    assert back.model_dump_json() == text
    assert pickle.loads(pickle.dumps(state)).model_dump_json() == state.model_dump_json()
    assert RemittancesState.model_validate_json(state.model_dump_json()) == state
    resumed_world, resumed_sim = _world(), pickle.loads(pickle.dumps(sim))
    resumed_world.livelihoods = back
    resumed_world.turn = world.turn
    a = settle(world, sim, 3)
    b = settle(resumed_world, resumed_sim, 3)
    assert a.model_dump_json() == b.model_dump_json()
    assert sim.people == resumed_sim.people and [c[0] for c in sim.calls] == [5, 6, 7, 8]


def test_snapshot_is_a_dated_copy_with_ordered_counters():
    world, sim = _world(), family()
    step(world, sim, moves=[(10, 0, 1)])
    settle(world, sim, RM.SETTLED_TURNS)
    fields = livelihoods_snapshot_fields(world)["livelihoods"]["remittances"]
    json.dumps(fields)
    assert fields["source_turn"] == RM.SETTLED_TURNS and fields["receipts"][0]["recipient"] == 20
    assert list(fields["counters"]) == [k for k in COUNTERS if k in fields["counters"]]
    assert fields["parameters"]["settled_turns"] == RM.SETTLED_TURNS
    fields["receipts"][0]["credited"] = -1                # a copy, never the live state
    assert world.livelihoods.remittances.receipts[0].credited == 425
    world.turn += 1
    later = livelihoods_snapshot_fields(world)["livelihoods"]["remittances"]
    assert later["receipts"] is None and later["regions"] is None and later["funnel"] is None


def test_a_failed_tick_runs_no_after_hook_and_moves_nothing():
    world, sim = _world(), family()
    step(world, sim, moves=[(10, 0, 1)])
    settle(world, sim, RM.SETTLED_TURNS - 1)
    before = world.livelihoods.remittances.model_dump_json()
    bridge = FakeBridge(sim)
    world.livelihoods._pool_sim = id(sim)              # the pool this run already bound

    def failing(*args, **kwargs):
        raise RuntimeError("kernel failed")

    tick = wrap_agent_tick(world, bridge, failing, None)
    with pytest.raises(RuntimeError, match="kernel failed"):
        tick(world)
    assert world.livelihoods.remittances.model_dump_json() == before and sim.calls == []
    assert sim.people[10]["wealth"] == 7.0
    # The same turn then succeeds once.
    tick = wrap_agent_tick(world, bridge, lambda *a, **k: [], None)
    tick(world)
    assert len(sim.calls) == 1


def test_a_stale_native_build_is_refused():
    world = _world()

    class Old:
        def get_snapshot(self):
            return Snapshot([])

    with pytest.raises(RuntimeError, match="fresh native build"):
        RM.after_agent_tick(world, FakeBridge(Old()))


def test_declared_codes_are_append_only_prefixes():
    assert RECEIPT_STATUSES[:4] == ("applied", "limited", "absent", "not_sent")
    assert CLOSE_REASONS[:4] == ("return", "death", "pool_reset", "unobserved_gap")
    assert MOVE_KINDS[:4] == ("departure", "onward", "return", "unrecorded")
    assert SENDER_REASONS[:5] == ("child", "unsettled", "on_trip", "elsewhere", "already_sent")
    assert UNLINKED_REASONS[:3] == ("no_bond", "recipient_away", "recipient_on_trip")
    assert RM.PURPOSE_REMITTANCE == 4
