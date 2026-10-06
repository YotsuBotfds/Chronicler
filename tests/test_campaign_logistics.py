"""Ordinary explicit tables; no worlds, native agents or scientific RNG."""

from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import random
import runpy
import subprocess
import sys

import pytest

from chronicler.campaign_logistics import (
    Condition, Counts, Credit, Draw, Food, MemberReceipt, Order,
    Region, Replenishment, Session, Soldier, Stock, Tick, Topology,
    admit, advance, canonical_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "campaign_logistics_demo.py"
DEMO = runpy.run_path(str(DRIVER))


@pytest.fixture
def policy():
    return DEMO["illustrative_policy"]()


@pytest.fixture
def topology():
    return DEMO["fixture_topology"]()


def session_for(policy, topology, soldiers=(Soldier(10, 1, 8, 800),), stocks=()):
    return admit(policy=policy, topology=topology, campaign_id="unit-table", turn=0,
                 staging=1, target=2, soldiers=soldiers, stocks=stocks)


def tick_for(session, *, orders=(), credits=(), sources=(1,), needs=0, quality=1000, draw=9999):
    active = [s.agent_id for s in session.state.soldiers if s.status in ("active", "arrived")]
    if session.state.phase in ("closed", "cancelled") or any(o.kind == "cancel" for o in orders):
        active = []
    return Tick(session.state.turn + 1, orders, credits,
                tuple(Condition(agent, needs, quality) for agent in active),
                tuple(Draw(agent, draw) for agent in active), sources)


def step(session, policy, topology, **kwargs):
    return advance(session, policy=policy, topology=topology, tick=tick_for(session, **kwargs))


def conserved(result):
    f = result.receipt.food
    assert f.initial + f.credits == f.local + f.carried + f.consumed + f.deserted
    c = result.receipt.counts_after
    assert c.active + c.arrived_active + c.returned + c.deserted == len(result.session.state.original_ids)
    for member in result.receipt.members:
        assert member.ration_before + member.replenished == member.consumed + member.ration_after + member.released
        assert member.region_before == member.region_after or (
            len(member.path) >= 2 and member.region_before == member.path[0]
            and member.region_after == member.path[1])


def test_hand_calculated_three_region_complete_trace(policy, topology):
    session = DEMO["fixture_session"](policy, topology)
    # turn, phase, locations, kits, morale, local stock, consumed food
    expected = [
        (1, "ready", (1, 1), (7, 7), (820, 790), (0, 0, 4), 2),
        (2, "marching", (0, 0), (6, 6), (840, 810), (0, 0, 4), 4),
        (3, "arrived", (2, 2), (5, 5), (830, 800), (0, 0, 4), 6),
        (4, "arrived", (2, 2), (6, 6), (810, 780), (0, 0, 2), 8),
        (5, "returning", (0, 0), (5, 5), (790, 760), (0, 0, 2), 10),
        (6, "closed", (1, 1), (0, 0), (780, 750), (0, 8, 2), 12),
        (7, "closed", (1, 1), (0, 0), (780, 750), (0, 8, 2), 12),
    ]
    for turn, phase, locations, kits, morale, stock, consumed in expected:
        tick = DEMO["fixture_tick"](session, turn)
        result = advance(session, policy=policy, topology=topology, tick=tick)
        state, receipt = result.session.state, result.receipt
        assert (state.turn, state.phase) == (turn, phase)
        assert tuple(s.region for s in state.soldiers) == locations
        assert tuple(s.rations for s in state.soldiers) == kits
        assert tuple(s.morale for s in state.soldiers) == morale
        assert tuple(s.rations for s in state.stocks) == stock
        assert receipt.food == Food(20, 2 if turn >= 4 else 0, sum(stock), sum(kits), consumed, 0)
        assert receipt.counts_after == (
            Counts(2, 0, 0, 0) if turn <= 2 else Counts(0, 2, 0, 0) if turn <= 4
            else Counts(2, 0, 0, 0) if turn == 5 else Counts(0, 0, 2, 0))
        assert receipt.policy_id == policy.version
        assert receipt.topology_id == topology.version
        assert receipt.payload_digest == hashlib.sha256(canonical_bytes(receipt.inputs)).hexdigest()
        assert receipt.state_after_digest == hashlib.sha256(canonical_bytes(state)).hexdigest()
        assert receipt.stocks_before == session.state.stocks
        if turn == 1:
            assert receipt.members == (
                MemberReceipt(101, 1, 1, "active", "active", (1,), 0, 8, 0, 1, 7, 0,
                              800, 820, 0, 0, 0, 0, 9999, False, ("at_objective",)),
                MemberReceipt(202, 0, 1, "active", "active", (0, 1), 1, 8, 0, 1, 7, 0,
                              800, 790, 0, 10, 0, 0, 9999, False, ("rally_move",)),
            )
            assert receipt.reasons == ("rallied_march_next_turn",)
        if turn == 2:
            assert receipt.members == (
                MemberReceipt(101, 1, 0, "active", "active", (1, 0, 2), 0, 7, 0, 1, 6, 0,
                              820, 840, 0, 0, 0, 0, 9999, False, ("march_move",)),
                MemberReceipt(202, 1, 0, "active", "active", (1, 0, 2), 0, 7, 0, 1, 6, 0,
                              790, 810, 0, 0, 0, 0, 9999, False, ("march_move",)),)
        if turn == 3:
            assert receipt.members == (
                MemberReceipt(101, 0, 2, "active", "arrived", (0, 2), 1, 6, 0, 1, 5, 0,
                              840, 830, 0, 10, 0, 0, 9999, False, ("march_move", "arrived")),
                MemberReceipt(202, 0, 2, "active", "arrived", (0, 2), 1, 6, 0, 1, 5, 0,
                              810, 800, 0, 10, 0, 0, 9999, False, ("march_move", "arrived")),)
        if turn == 4:
            assert receipt.replenishments == (
                Replenishment("kit-4", 101, 2, 2, 2, 6, 4, "replenished"),
                Replenishment("kit-4", 202, 2, 2, 2, 4, 2, "replenished"))
            assert receipt.members == (
                MemberReceipt(101, 2, 2, "arrived", "arrived", (2,), 2, 5, 2, 1, 6, 0,
                              830, 810, 0, 20, 0, 0, 9999, False, ("at_objective", "arrival_latched")),
                MemberReceipt(202, 2, 2, "arrived", "arrived", (2,), 2, 5, 2, 1, 6, 0,
                              800, 780, 0, 20, 0, 0, 9999, False, ("at_objective", "arrival_latched")),)
        if turn == 5:
            assert receipt.members == (
                MemberReceipt(101, 2, 0, "arrived", "active", (2, 0, 1), 2, 6, 0, 1, 5, 0,
                              810, 790, 0, 20, 0, 0, 9999, False, ("return_move",)),
                MemberReceipt(202, 2, 0, "arrived", "active", (2, 0, 1), 2, 6, 0, 1, 5, 0,
                              780, 760, 0, 20, 0, 0, 9999, False, ("return_move",)),)
        if turn == 6:
            assert receipt.members == (
                MemberReceipt(101, 0, 1, "active", "returned", (0, 1), 1, 5, 0, 1, 0, 4,
                              790, 780, 0, 10, 0, 0, 9999, False, ("return_move", "returned")),
                MemberReceipt(202, 0, 1, "active", "returned", (0, 1), 1, 5, 0, 1, 0, 4,
                              760, 750, 0, 10, 0, 0, 9999, False, ("return_move", "returned")),)
        if turn == 7:
            assert receipt.reasons == ("terminal_noop",)
            assert receipt.members == (
                MemberReceipt(101, 1, 1, "returned", "returned", (), None, 0, 0, 0, 0, 0,
                              780, 780, 0, 0, 0, 0, None, False, ("terminal_noop",)),
                MemberReceipt(202, 1, 1, "returned", "returned", (), None, 0, 0, 0, 0, 0,
                              750, 750, 0, 0, 0, 0, None, False, ("terminal_noop",)),)
        conserved(result)
        session = result.session


def test_starvation_stall_then_all_deserted_close(policy, topology):
    session = session_for(policy, topology, (Soldier(10, 0, 0, 350),))
    first = step(session, policy, topology, draw=9999)
    assert first.receipt.members == (
        MemberReceipt(10, 0, 0, "active", "active", (0, 1), 1, 0, 0, 0, 0, 0,
                      350, 220, 120, 10, 0, 0, 9999, False, ("ration_shortfall", "logistics_stall")),)
    second = step(first.session, policy, topology, draw=0)
    assert second.receipt.members == (
        MemberReceipt(10, 0, 0, "active", "deserted", (), 1, 0, 0, 0, 0, 0,
                      220, 90, 120, 10, 0, 0, 0, True, ("ration_shortfall", "deserted")),)
    assert second.receipt.phase_after == "closed"
    assert second.receipt.counts_after == Counts(0, 0, 0, 1)
    conserved(second)
    terminal = step(second.session, policy, topology)
    assert terminal.session.state.consumed_food == 0


def test_stress_components_and_deserted_ration_sink(policy, topology):
    session = session_for(policy, topology, (Soldier(10, 2, 4, 270),))
    result = step(session, policy, topology, needs=500, quality=500, draw=4999)
    assert result.receipt.members == (
        MemberReceipt(10, 2, 2, "active", "deserted", (), 2, 4, 0, 1, 0, 3,
                      270, 160, 0, 20, 50, 40, 4999, True, ("deserted",)),)
    assert result.receipt.food == Food(4, 0, 0, 0, 1, 3)
    conserved(result)


@pytest.mark.parametrize("draw,deserted", [(4999, True), (5000, False), (9999, False)])
def test_desertion_draw_boundary_and_threshold(policy, topology, draw, deserted):
    session = session_for(policy, topology, (Soldier(10, 0, 2, 210),))
    result = step(session, policy, topology, draw=draw)
    assert result.receipt.members[0].morale_after == 200
    assert result.receipt.members[0].deserted is deserted
    conserved(result)


def test_hold_replenishment_local_allocation_and_credit(policy, topology):
    session = session_for(policy, topology, (Soldier(20, 0, 0, 800), Soldier(10, 1, 0, 800)),
                          (Stock(0, 1), Stock(1, 0)))
    result = step(session, policy, topology,
                  orders=(Order("hold", 1, "hold"), Order("replenish", 1, "replenish", (20, 10), 3)),
                  credits=(Credit("one-local", 1, 1, 2),))
    assert result.receipt.replenishments == (
        Replenishment("replenish", 10, 1, 3, 2, 2, 0, "local_stock_shortfall"),
        Replenishment("replenish", 20, 0, 3, 1, 1, 0, "local_stock_shortfall"))
    assert tuple(s.region for s in result.session.state.soldiers) == (1, 0)
    assert tuple(s.rations for s in result.session.state.soldiers) == (1, 0)
    assert result.receipt.food == Food(1, 2, 0, 1, 2, 0)
    assert result.receipt.members[1].reasons == ("hold",)
    conserved(result)


def test_shared_stock_stable_id_priority_and_capacity(policy, topology):
    session = session_for(policy, topology, (Soldier(20, 1, 0, 800), Soldier(10, 1, 0, 800)),
                          (Stock(1, 3),))
    result = step(session, policy, topology, orders=(Order("kit", 1, "replenish", (20, 10), 2),))
    assert result.receipt.replenishments == (
        Replenishment("kit", 10, 1, 2, 2, 3, 1, "replenished"),
        Replenishment("kit", 20, 1, 2, 1, 1, 0, "local_stock_shortfall"))
    assert tuple(s.rations for s in result.session.state.soldiers) == (1, 0)
    full = session_for(policy, topology, stocks=(Stock(1, 5),))
    limited = step(full, policy, topology, orders=(Order("kit", 1, "replenish", (10,), 2),))
    assert limited.receipt.replenishments[0] == Replenishment("kit", 10, 1, 2, 0, 5, 5, "kit_limit")
    conserved(result)
    conserved(limited)


@pytest.mark.parametrize("order_ids", [("z", "a"), ("a", "z")])
def test_soldier_priority_spans_separate_replenishment_orders(policy, topology, order_ids):
    session = session_for(policy, topology, (Soldier(20, 1, 0, 800), Soldier(10, 1, 0, 800)),
                          (Stock(1, 1),))
    low_order, high_order = order_ids
    tick = tick_for(session, orders=(Order(high_order, 1, "replenish", (20,), 1),
                                    Order(low_order, 1, "replenish", (10,), 1)))
    result = advance(session, policy=policy, topology=topology, tick=tick)
    assert result.receipt.replenishments == (
        Replenishment(low_order, 10, 1, 1, 1, 1, 0, "replenished"),
        Replenishment(high_order, 20, 1, 1, 0, 0, 0, "local_stock_shortfall"))
    assert tuple(m.consumed for m in result.receipt.members) == (1, 0)
    assert tuple(s.morale for s in result.session.state.soldiers) == (820, 680)
    assert tuple(m.region_after for m in result.receipt.members) == (1, 1)
    replay = advance(result.session, policy=policy, topology=topology, tick=tick)
    assert replay.session is result.session and replay.receipt is result.receipt
    reversed_tick = replace(tick, orders=tuple(reversed(tick.orders)))
    assert advance(session, policy=policy, topology=topology, tick=reversed_tick) == result
    conserved(result)


def test_multiple_requests_per_soldier_preserve_global_priority(policy, topology):
    session = session_for(policy, topology, (Soldier(20, 1, 0, 800), Soldier(10, 1, 0, 800)),
                          (Stock(1, 2),))
    result = step(session, policy, topology, orders=(
        Order("a", 1, "replenish", (20,), 1),
        Order("c", 1, "replenish", (10,), 1),
        Order("b", 1, "replenish", (20, 10), 1)))
    assert result.receipt.replenishments == (
        Replenishment("b", 10, 1, 1, 1, 2, 1, "replenished"),
        Replenishment("c", 10, 1, 1, 1, 1, 0, "replenished"),
        Replenishment("a", 20, 1, 1, 0, 0, 0, "local_stock_shortfall"),
        Replenishment("b", 20, 1, 1, 0, 0, 0, "local_stock_shortfall"))
    assert tuple(s.rations for s in result.session.state.soldiers) == (1, 0)
    conserved(result)


@pytest.mark.parametrize("field", ["supply_sources", "agent_ids"])
@pytest.mark.parametrize("invalid", ["", [], None, 0])
def test_tuple_fields_reject_malformed_empty_values_before_publication(policy, topology, field, invalid):
    session = session_for(policy, topology, stocks=(Stock(1, 1),))
    tick = tick_for(session, orders=(Order("hold", 1, "hold"),
                                    Order("kit", 1, "replenish", (10,), 1)),
                    credits=(Credit("local-credit", 1, 1, 2),))
    if field == "supply_sources":
        malformed = replace(tick, supply_sources=invalid)
    else:
        malformed = replace(tick, orders=(replace(tick.orders[0], agent_ids=invalid), tick.orders[1]))
    snapshot = tuple(canonical_bytes(value) for value in (session, policy, topology, malformed))
    with pytest.raises(ValueError):
        advance(session, policy=policy, topology=topology, tick=malformed)
    assert snapshot == tuple(canonical_bytes(value) for value in (session, policy, topology, malformed))


@pytest.mark.parametrize("field", ["supply_sources", "agent_ids"])
def test_malformed_empty_strings_cannot_alias_valid_replay_payload(policy, topology, field):
    session = session_for(policy, topology)
    tick = tick_for(session, orders=(Order("hold", 1, "hold"),), sources=())
    result = advance(session, policy=policy, topology=topology, tick=tick)
    malformed = replace(tick, supply_sources="") if field == "supply_sources" else replace(
        tick, orders=(replace(tick.orders[0], agent_ids=""),))
    saved = canonical_bytes(result.session)
    with pytest.raises(ValueError, match=f"{field} must be a tuple"):
        advance(result.session, policy=policy, topology=topology, tick=malformed)
    assert canonical_bytes(result.session) == saved


def test_rally_never_marches_same_turn_and_hold_is_one_turn(policy, topology):
    session = session_for(policy, topology, (Soldier(10, 2, 8, 800), Soldier(20, 1, 8, 800)))
    held = step(session, policy, topology, orders=(Order("h", 1, "hold"),))
    assert tuple(s.region for s in held.session.state.soldiers) == (2, 1)
    rally = step(held.session, policy, topology, orders=(Order("m2", 2, "march"),))
    assert tuple(s.region for s in rally.session.state.soldiers) == (0, 1)
    rally2 = step(rally.session, policy, topology, orders=(Order("m3", 3, "march"),))
    assert rally2.session.state.phase == "ready"
    assert tuple(s.region for s in rally2.session.state.soldiers) == (1, 1)
    waiting = step(rally2.session, policy, topology)
    assert waiting.session.state.phase == "ready"
    assert all(m.reasons == ("at_objective",) for m in waiting.receipt.members)
    march = step(waiting.session, policy, topology, orders=(Order("m5", 5, "march"),))
    assert tuple(s.region for s in march.session.state.soldiers) == (0, 0)
    assert all(m.path == (1, 0, 2) for m in march.receipt.members)


def test_cohort_stalls_together_until_local_replenishment(policy, topology):
    session = session_for(policy, topology, (Soldier(10, 1, 1, 800), Soldier(20, 1, 8, 800)),
                          (Stock(1, 2),))
    ready = step(session, policy, topology)
    stalled = step(ready.session, policy, topology, orders=(Order("march", 2, "march"),))
    assert tuple(s.region for s in stalled.session.state.soldiers) == (1, 1)
    assert stalled.receipt.members[0].reasons == ("ration_shortfall", "logistics_stall")
    assert stalled.receipt.members[1].reasons == ("cohort_stall",)
    moved = step(stalled.session, policy, topology, orders=(Order("kit", 3, "replenish", (10,), 2),))
    assert tuple(s.region for s in moved.session.state.soldiers) == (0, 0)
    conserved(moved)


def test_return_during_rally_settles_only_members_at_staging(policy, topology):
    session = session_for(policy, topology, (Soldier(10, 1, 8, 800), Soldier(20, 2, 8, 800)))
    result = step(session, policy, topology, orders=(Order("return", 1, "return"),))
    assert result.receipt.counts_after == Counts(1, 0, 1, 0)
    assert result.session.state.stocks[1] == Stock(1, 7)
    assert result.session.state.soldiers[1].region == 0
    final = step(result.session, policy, topology)
    assert final.receipt.food == Food(16, 0, 13, 0, 3, 0)
    assert final.receipt.members[0].draw is None
    assert final.receipt.members[0].consumed == 0
    assert final.receipt.phase_after == "closed"
    conserved(final)


def test_return_can_stall_and_desert(policy, topology):
    session = session_for(policy, topology, (Soldier(10, 2, 0, 340),))
    result = step(session, policy, topology, orders=(Order("return", 1, "return"),))
    assert result.receipt.phase_after == "returning"
    assert result.receipt.members[0].morale_after == 200
    assert result.receipt.members[0].region_after == 2
    final = step(result.session, policy, topology, draw=0)
    assert final.receipt.phase_after == "closed"
    assert final.receipt.members[0].status_after == "deserted"


def test_disconnected_rally_and_supply_reason_coded_stall(policy):
    topology = Topology("disconnected-v1", (Region(0, (1,)), Region(1, (0,)), Region(2, ())))
    session = session_for(policy, topology, (Soldier(10, 2, 8, 800),))
    result = step(session, policy, topology)
    assert result.receipt.members == (
        MemberReceipt(10, 2, 2, "active", "active", (), None, 8, 0, 1, 7, 0,
                      800, 700, 0, 100, 0, 0, 9999, False,
                      ("supply_unreachable", "destination_unreachable")),)
    assert result.receipt.phase_after == "rally"
    conserved(result)


def test_disconnected_target_never_teleports(policy):
    topology = Topology("disconnected-v1", (Region(0, (1,)), Region(1, (0,)), Region(2, ())))
    ready = step(session_for(policy, topology), policy, topology)
    result = step(ready.session, policy, topology, orders=(Order("march", 2, "march"),))
    assert result.receipt.members[0].region_after == 1
    assert result.receipt.members[0].reasons == ("destination_unreachable",)


def test_cancellation_before_movement_retains_local_kits_and_is_terminal(policy, topology):
    session = session_for(policy, topology, (Soldier(10, 2, 8, 800),))
    result = step(session, policy, topology, orders=(Order("cancel", 1, "cancel"),))
    assert result.receipt.phase_after == "cancelled"
    assert result.session.state.soldiers == session.state.soldiers
    assert result.receipt.food == Food(8, 0, 0, 8, 0, 0)
    assert result.receipt.reasons == ("cancelled_before_movement",)
    terminal = step(result.session, policy, topology)
    assert terminal.session.state.soldiers == session.state.soldiers
    conserved(terminal)


def test_exact_replay_conflicts_and_resume(policy, topology):
    initial = DEMO["fixture_session"](policy, topology)
    session, inputs, receipts = initial, [], []
    for turn in range(1, 8):
        tick = DEMO["fixture_tick"](session, turn)
        result = advance(session, policy=policy, topology=topology, tick=tick)
        inputs.append(tick)
        receipts.append(result.receipt)
        session = result.session
        if turn == 3:
            interrupted = Session(session.state, session.cursor)
    for tick, receipt in zip(inputs, receipts):
        replay = advance(session, policy=policy, topology=topology, tick=tick)
        assert replay.session is session
        assert replay.receipt is receipt
    resumed = interrupted
    for tick in inputs[3:]:
        resumed = advance(resumed, policy=policy, topology=topology, tick=tick).session
    assert canonical_bytes(resumed) == canonical_bytes(session)
    saved = canonical_bytes(session)
    with pytest.raises(ValueError, match="contradictory"):
        advance(session, policy=policy, topology=topology,
                tick=replace(inputs[3], credits=(Credit("local-demo-credit-4", 4, 2, 3),)))
    assert canonical_bytes(session) == saved


@pytest.mark.parametrize("bad", [
    lambda t: replace(t, turn=0),
    lambda t: replace(t, turn=3),
    lambda t: replace(t, turn=True),
    lambda t: replace(t, draws=()),
    lambda t: replace(t, draws=(Draw(10, 1), Draw(10, 2))),
    lambda t: replace(t, draws=(Draw(10, -1),)),
    lambda t: replace(t, draws=(Draw(10, 10000),)),
    lambda t: replace(t, draws=(Draw(99, 3),)),
    lambda t: replace(t, conditions=()),
    lambda t: replace(t, conditions=(Condition(10, 0, 1000), Condition(10, 0, 1000))),
    lambda t: replace(t, conditions=(Condition(10, 1001, 0),)),
    lambda t: replace(t, conditions=(Condition(10, 0, -1),)),
    lambda t: replace(t, conditions=(Condition(10, 0, float("nan")),)),
    lambda t: replace(t, orders=(Order("same", 1, "hold"), Order("same", 1, "hold"))),
    lambda t: replace(t, orders=(Order("h", 0, "hold"),)),
    lambda t: replace(t, orders=(Order("h", 2, "hold"),)),
    lambda t: replace(t, orders=(Order("h", 1, "hold"), Order("m", 1, "march"))),
    lambda t: replace(t, orders=(Order("bad", 1, "combat"),)),
    lambda t: replace(t, orders=(Order("bad", 1, "replenish", (99,), 1),)),
    lambda t: replace(t, orders=(Order("bad", 1, "replenish", (10, 10), 1),)),
    lambda t: replace(t, orders=(Order("bad", 1, "replenish", (10,), -1),)),
    lambda t: replace(t, orders=(Order("bad", 1, "replenish", (10,), 0),)),
    lambda t: replace(t, orders=(Order("bad", 1, "hold", (10,), 1),)),
    lambda t: replace(t, credits=(Credit("src", 1, 1, 1), Credit("src", 1, 1, 1))),
    lambda t: replace(t, credits=(Credit("src", 2, 1, 1),)),
    lambda t: replace(t, credits=(Credit("src", 1, 9, 1),)),
    lambda t: replace(t, credits=(Credit("src", 1, 1, -1),)),
    lambda t: replace(t, supply_sources=(9,)),
    lambda t: replace(t, supply_sources=(1, 1)),
    lambda t: replace(t, supply_sources=(True,)),
    lambda t: replace(t, orders=[]),
])
def test_malformed_tick_atomicity(policy, topology, bad):
    session = session_for(policy, topology)
    tick = tick_for(session, orders=(Order("kit", 1, "replenish", (10,), 1),),
                    credits=(Credit("good-src", 1, 1, 4),))
    malformed = bad(tick)
    saved = canonical_bytes(session), canonical_bytes(policy), canonical_bytes(topology)
    with pytest.raises(ValueError):
        advance(session, policy=policy, topology=topology, tick=malformed)
    assert saved == (canonical_bytes(session), canonical_bytes(policy), canonical_bytes(topology))


@pytest.mark.parametrize("kwargs", [
    {"soldiers": ()},
    {"soldiers": (Soldier(10, 1, 2, 500), Soldier(10, 0, 3, 800))},
    {"soldiers": (Soldier(10, 9, 2, 500),)},
    {"soldiers": (Soldier(10, 1, -1, 500),)},
    {"soldiers": (Soldier(10, 1, 9, 500),)},
    {"soldiers": (Soldier(10, 1, "2", 500),)},
    {"soldiers": (Soldier(10, 1, 2.0, 500),)},
    {"soldiers": (Soldier(10, 1, 2, 1001),)},
    {"soldiers": (Soldier(10, 1, 2, 500, role="farmer"),)},
    {"soldiers": (Soldier(10, 1, 2, 500, status="returned"),)},
    {"soldiers": (Soldier(True, 1, 2, 500),)},
    {"stocks": (Stock(1, -1),)},
    {"stocks": (Stock(1, 1), Stock(1, 2))},
    {"stocks": (Stock(9, 1),)},
])
def test_invalid_admission(policy, topology, kwargs):
    with pytest.raises(ValueError):
        session_for(policy, topology, **kwargs)


@pytest.mark.parametrize("change", [
    {"ration_demand": 0}, {"carried_limit": 0}, {"distance_stress": -1},
    {"unreachable_stress": 1001}, {"desertion_chance": 10001},
    {"movement_min_morale": float("inf")}, {"version": ""},
    {"ordering": ("move", "consume")}, {"require_full_rations": 1},
    {"rally_rule": "same-turn"}, {"termination_rule": "combat"},
])
def test_invalid_policy(policy, topology, change):
    with pytest.raises(ValueError):
        session_for(replace(policy, **change), topology)


@pytest.mark.parametrize("regions", [
    (), (Region(0, (1,)), Region(1, ())),
    (Region(0, (9,)),), (Region(0, (0,)),),
    (Region(0, ()), Region(0, ())),
    (Region(0, (1, 1)), Region(1, (0,))),
    (Region(0, [1]), Region(1, (0,))),
])
def test_illegal_topology(policy, regions):
    with pytest.raises(ValueError):
        session_for(policy, Topology("bad", regions))


def test_illegal_identity_dates_and_lifecycle(policy, topology):
    for kwargs in ({"turn": -1}, {"staging": 9}, {"target": 1}, {"campaign_id": ""}):
        params = dict(policy=policy, topology=topology, campaign_id="id", turn=0,
                      staging=1, target=2, soldiers=(Soldier(10, 1, 8, 800),), stocks=())
        params.update(kwargs)
        with pytest.raises(ValueError):
            admit(**params)
    session = session_for(policy, topology)
    first = step(session, policy, topology, orders=(Order("h", 1, "hold"),), credits=(Credit("c", 1, 1, 2),))
    for kwargs in ({"orders": (Order("h", 2, "hold"),)}, {"credits": (Credit("c", 2, 1, 2),)},
                   {"orders": (Order("cancel", 2, "cancel"),)}):
        saved = canonical_bytes(first.session)
        with pytest.raises(ValueError):
            step(first.session, policy, topology, **kwargs)
        assert canonical_bytes(first.session) == saved
    cancelled = step(session, policy, topology, orders=(Order("cancel", 1, "cancel"),))
    with pytest.raises(ValueError):
        step(cancelled.session, policy, topology, credits=(Credit("c", 2, 1, 1),))


def test_resume_rejects_wrong_cursor_state_or_configuration(policy, topology):
    initial = session_for(policy, topology)
    result = step(initial, policy, topology)
    corruptions = [Session(result.session.state, initial.cursor),
                   Session(initial.state, result.session.cursor),
                   replace(result.session, state=replace(result.session.state, consumed_food=0)),
                   replace(result.session, cursor=replace(result.session.cursor, receipts=(
                       replace(result.receipt, reasons=("corrupt",)),)))]
    for corrupted in corruptions:
        with pytest.raises(ValueError):
            step(corrupted, policy, topology)
    with pytest.raises(ValueError, match="identity"):
        step(result.session, replace(policy, hunger_stress=110), topology)
    with pytest.raises(ValueError, match="identity"):
        step(result.session, policy, replace(topology, version="changed"))
    with pytest.raises(FrozenInstanceError):
        result.session.state.turn = 9


def test_permutations_equal_all_states_and_receipts(policy, topology):
    reverse_topology = replace(topology, regions=tuple(
        replace(r, neighbors=tuple(reversed(r.neighbors))) for r in reversed(topology.regions)))
    left = DEMO["fixture_session"](policy, topology)
    right = admit(policy=policy, topology=reverse_topology, campaign_id=left.state.campaign_id,
                  turn=0, staging=1, target=2, soldiers=tuple(reversed(left.state.soldiers)),
                  stocks=tuple(reversed(left.state.stocks)))
    assert left == right
    for turn in range(1, 8):
        tick = DEMO["fixture_tick"](left, turn)
        reverse = replace(tick, orders=tuple(replace(o, agent_ids=tuple(reversed(o.agent_ids)))
                          for o in reversed(tick.orders)), credits=tuple(reversed(tick.credits)),
                          conditions=tuple(reversed(tick.conditions)), draws=tuple(reversed(tick.draws)),
                          supply_sources=tuple(reversed(tick.supply_sources)))
        a = advance(left, policy=policy, topology=topology, tick=tick)
        b = advance(right, policy=policy, topology=reverse_topology, tick=reverse)
        assert canonical_bytes(a) == canonical_bytes(b)
        left, right = a.session, b.session


def test_multiple_credit_order_source_permutations(policy, topology):
    session = session_for(policy, topology, (Soldier(20, 1, 0, 800), Soldier(10, 1, 0, 800)))
    tick = tick_for(session, orders=(Order("b", 1, "replenish", (20,), 2),
                                    Order("a", 1, "replenish", (10,), 2)),
                    credits=(Credit("y", 1, 1, 1), Credit("x", 1, 1, 2)), sources=(2, 1))
    reverse = replace(tick, orders=tuple(reversed(tick.orders)), credits=tuple(reversed(tick.credits)),
                      conditions=tuple(reversed(tick.conditions)), draws=tuple(reversed(tick.draws)),
                      supply_sources=(1, 2))
    left = advance(session, policy=policy, topology=topology, tick=tick)
    right = advance(session, policy=policy, topology=topology, tick=reverse)
    assert left == right
    assert left.receipt.members[0].supply_distance == 0
    conserved(left)


def test_empty_sources_are_explicit_unreachable(policy, topology):
    result = step(session_for(policy, topology), policy, topology, sources=())
    assert result.receipt.members[0].supply_distance is None
    assert result.receipt.members[0].distance_stress == 100
    assert "supply_unreachable" in result.receipt.members[0].reasons


def test_fixed_point_rounding_and_policy_movement_gate(policy, topology):
    policy = replace(policy, ration_demand=3, hunger_stress=100,
                     needs_stress=99, information_stress=79, require_full_rations=False)
    session = session_for(policy, topology, (Soldier(10, 0, 2, 800),))
    result = step(session, policy, topology, needs=333, quality=667)
    # Hunger ceil(100/3)=34; needs floor(99*333/1000)=32;
    # information floor(79*333/1000)=26; distance=10; total=102.
    assert result.receipt.members == (
        MemberReceipt(10, 0, 1, "active", "active", (0, 1), 1, 2, 0, 2, 0, 0,
                      800, 698, 34, 10, 32, 26, 9999, False, ("ration_shortfall", "rally_move")),)
    conserved(result)


def test_arrival_rejects_march_and_settled_member_replenishment(policy, topology):
    session = DEMO["fixture_session"](policy, topology)
    for turn in range(1, 4):
        session = advance(session, policy=policy, topology=topology,
                          tick=DEMO["fixture_tick"](session, turn)).session
    with pytest.raises(ValueError, match="march not legal"):
        step(session, policy, topology, orders=(Order("m4", 4, "march"),))
    dispersed = session_for(policy, topology, (Soldier(10, 1, 8, 800), Soldier(20, 2, 8, 800)))
    returning = step(dispersed, policy, topology, orders=(Order("return", 1, "return"),))
    with pytest.raises(ValueError, match="settled member"):
        step(returning.session, policy, topology, orders=(Order("kit", 2, "replenish", (10,), 2),))


def test_shortest_path_sorted_tie_and_uncapped_length(policy):
    # Plain graph tables exercise BFS, without any WorldState/science fixture.
    topology = Topology("bfs-tie-table", (Region(3, (2, 1)), Region(2, (3, 0)),
                                         Region(1, (3, 0)), Region(0, (2, 1))))
    session = admit(policy=policy, topology=topology, campaign_id="tie", turn=0,
                    staging=0, target=3, soldiers=(Soldier(10, 3, 8, 800),), stocks=())
    result = step(session, policy, topology, sources=(0,))
    assert result.receipt.members[0].path == (3, 1, 0)
    assert result.receipt.members[0].region_after == 1
    line = Topology("bfs-long-table", tuple(Region(i, tuple(j for j in (i - 1, i + 1)
                         if 0 <= j < 12)) for i in range(12)))
    session = admit(policy=policy, topology=line, campaign_id="line", turn=0,
                    staging=0, target=11, soldiers=(Soldier(10, 11, 8, 800),), stocks=())
    result = step(session, policy, line, sources=(0,))
    assert result.receipt.members[0].path == tuple(range(11, -1, -1))
    assert result.receipt.members[0].supply_distance == 11
    assert result.receipt.members[0].distance_stress == 110
    assert result.receipt.members[0].region_after == 10


def test_driver_disabled_exact_noop_and_no_rng(policy, topology, monkeypatch):
    session = session_for(policy, topology)
    tick = tick_for(session)
    saved = canonical_bytes(session), canonical_bytes(tick), random.getstate()
    def forbidden(*args, **kwargs):
        raise AssertionError("hidden RNG used")
    for name in ("random", "randint", "randrange", "choice", "seed", "getrandbits"):
        monkeypatch.setattr(random, name, forbidden)
    unchanged, receipt = DEMO["drive"](session, enabled=False, policy=policy, topology=topology, tick=tick)
    assert unchanged is session
    assert (receipt.reason, receipt.draws_consumed, receipt.food_consumed, receipt.moves) == (
        "experiment_disabled", 0, 0, 0)
    step(session, policy, topology)
    assert saved == (canonical_bytes(session), canonical_bytes(tick), random.getstate())


def test_driver_and_import_in_fresh_processes_hashseed_stable():
    outputs = []
    for seed in ("0", "1", "42", "101"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT / "src"))
        outputs.append(subprocess.check_output([sys.executable, str(DRIVER), "--enable"], env=env))
    assert all(output == outputs[0] for output in outputs)
    assert json.loads(outputs[0])["state"]["phase"] == "closed"
    disabled = json.loads(subprocess.check_output([sys.executable, str(DRIVER)]))
    assert disabled == {"contract": "chronicler-m60a-detached-v1", "reason": "experiment_disabled",
                        "draws_consumed": 0, "food_consumed": 0, "moves": 0}
    probe = '''import sys, random
before = random.getstate()
import chronicler.campaign_logistics
assert random.getstate() == before
assert not any(k in sys.modules for k in ("chronicler.models", "chronicler.simulation", "chronicler.agent_bridge", "numpy"))
'''
    subprocess.run([sys.executable, "-c", probe], check=True,
                   env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))
