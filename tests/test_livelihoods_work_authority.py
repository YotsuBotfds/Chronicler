"""Adversarial checks of the livelihoods work authority and its lifecycle.

Offline (no native extension): a stand-in simulator supplies the native
contracts of ``workshop_work.rs`` and ``wealth_transfer.rs`` with per-site
crews; the L1 workshop and L6a payroll code is the real code. Derived from
the stated contracts in ``docs/integration/workshops.md`` and
``docs/integration/workshop-finance.md``, not from the authors' examples.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import workshop_payroll as P
from chronicler import workshops as W
from chronicler.cities_state import City, CityState
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.workshop_payroll_state import OwedWage, WorkshopFirm, WorkshopPayrollState
from chronicler.workshops_state import WorkshopReceipt, WorkshopSite, WorkshopState

MAX_WEALTH = 100.0


class Sim:
    """Native stand-in: per-site crews, a work registry, paid work and transfers."""

    def __init__(self, crews: dict[int, list[int]], wealth: float = 10.0, income: float = 0.3):
        self.crews = {site: list(ids) for site, ids in crews.items()}
        self.wealth = {aid: wealth for ids in crews.values() for aid in ids}
        self.dead: set[int] = set()
        self.income = income
        self.registry: list[tuple[int, int, int, float]] = []    # (turn, id, category, fraction)
        self.paid = self.receipt = None
        self.keys: list[tuple[int, int, int]] = []
        self.plan_calls: list[tuple[list, int | None]] = []

    # workshop_work.rs
    def plan_workshop_crews(self, requests, enlisted, turn=None):
        self.plan_calls.append((list(requests), turn))
        held = {aid for t, aid, _c, _f in self.registry if t == turn} if turn is not None else set()
        rows, reserve = [], []
        for site, region, settlement, fraction, cap in requests:
            crew = [a for a in self.crews.get(site, []) if a not in self.dead
                    and a not in enlisted and a not in held][:cap]
            rows.append((site, region, settlement, len(crew), 0, 0, 0, len(crew), crew,
                         [30] * len(crew), len(crew) * fraction))
            reserve.extend((aid, fraction) for aid in crew)
        if turn is not None:
            self.reserve_work(turn, 0, reserve)
        return rows

    def reserve_work(self, turn, category, rows):
        held = {aid for t, aid, _c, _f in self.registry if t == turn}
        if any(aid in held or aid in self.dead for aid, _ in rows):
            raise ValueError("agent already holds work this turn")
        self.registry = [r for r in self.registry if r[0] == turn]
        self.registry.extend((turn, aid, category, fraction) for aid, fraction in rows)

    def work_reservations(self, turn):
        return [(aid, c, f) for t, aid, c, f in self.registry if t == turn]

    def take_craft_inputs(self):
        return None

    # wealth_transfer.rs
    def install_paid_work(self, turn, rows):
        if self.paid is not None:
            raise ValueError("paid work share already pending")
        for aid, share in rows:
            reserved = sum(f for t, a, _c, f in self.registry if t == turn and a == aid)
            if share > reserved + 1e-6:
                raise ValueError("paid work exceeds the agent's work reservation this turn")
        self.paid = (turn, list(rows))

    def cancel_paid_work(self):
        had, self.paid = self.paid is not None, None
        return had

    def wealth_phase(self):
        """The native tick's wealth phase consumes the arming; the registry clears."""
        if self.paid is not None:
            turn, rows = self.paid
            out = []
            for aid, share in rows:
                if aid in self.dead:
                    continue
                out.append((aid, share, self.income, self.income * share))
                self.wealth[aid] += self.income * (1 - share)
            self.receipt, self.paid = (turn, out), None
        self.registry = []

    def take_paid_work_receipt(self):
        out, self.receipt = self.receipt, None
        return out

    def get_snapshot(self):
        return pa.record_batch({"id": pa.array(sorted(a for a in self.wealth if a not in self.dead), pa.uint32())})

    def transfer_wealth(self, turn, purpose, batch, rows):
        if any(p == purpose and b == batch and t >= turn for t, p, b in self.keys):
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        self.keys.append((turn, purpose, batch))
        out = []
        for aid, amount in rows:
            if aid in self.dead or aid not in self.wealth:
                out.append((aid, amount, 0, amount, 2))
                continue
            w = self.wealth[aid]
            applied = min(amount, math.floor((MAX_WEALTH - w) * 1000)) if amount >= 0 \
                else -min(-amount, math.floor(w * 1000))
            self.wealth[aid] = w + applied / 1000
            out.append((aid, amount, applied, amount - applied, 0 if applied == amount else 1))
        return out


def _region(i):
    return SimpleNamespace(name=f"R{i}", controller="Civ0", stockpile=SimpleNamespace(goods={"crafts": 0.0}))


def _world(mode="no_customer", turn=30):
    civs = [SimpleNamespace(name="Civ0", treasury=1000)]
    world = SimpleNamespace(
        turn=turn, agent_mode="hybrid", civilizations=civs, regions=[_region(i) for i in range(4)],
        cities=CityState(cities=[City(settlement_id=2, region=2, name="C2", founded_turn=1,
                                      founder=0, rank=2, size=10.0)]),
        livelihoods=LivelihoodsState(), war_state=SimpleNamespace(armies=[]), scholarship=None)
    world.livelihoods.workshops = WorkshopState(mode="operate")
    world.livelihoods.workshop_payroll = WorkshopPayrollState(mode=mode)
    return world


def _firm(site, region, settlement, cash, owed=(), diverted=0.3):
    firm = WorkshopFirm(site=site, region=region, settlement_id=settlement, city_name=f"C{settlement}",
                        opened_turn=1, cash=cash, diverted=diverted,
                        owed=[OwedWage(agent_id=a, amount=m, since_turn=1) for a, m in owed])
    firm.totals["sales"] = cash
    return firm


def _receipt(world, site, region, settlement, crew, share):
    return WorkshopReceipt(turn=world.turn, site=site, region=region, settlement_id=settlement, rank=2,
                           diverted_fraction=share, resident_adult_farmers=len(crew), excluded_trip=0,
                           excluded_army=0, excluded_assigned=0, eligible=len(crew), crew=list(crew),
                           crew_ages=[30] * len(crew), work_available=share * len(crew),
                           allocated=share * len(crew), region_craft_output=0.0)


def test_phase10_wages_split_scarce_cash_among_survivors_of_the_tick_after_a_phase2_liquidation():
    """Contract (workshop-finance.md, Death): dead workers' claims lapse before
    cash is shared, so scarce cash is split among the living only; the living
    set is read from the native snapshot after the tick.

    Adversarial order: another firm is liquidated in Phase 2 (its city fell)
    and pays its owed wages then, before the tick. A worker of the operating
    firm dies in this turn's tick. His Phase 10 claim must lapse first, and
    the survivor must receive the firm's whole scarce cash.
    """
    world = _world(mode="no_customer")
    ws, pay = world.livelihoods.workshops, world.livelihoods.workshop_payroll
    share = 0.3
    wage = P._wage(share)                                   # 150 milli-units
    # Site 0's city fell this turn: the L1 site is closed, its firm still open.
    ws.closed = [WorkshopSite(site=0, region=1, settlement_id=1, city_name="C1", selected_turn=1,
                              status="closed", closed_turn=world.turn, closed_reason="city_fell")]
    ws.sites = [WorkshopSite(site=1, region=2, settlement_id=2, city_name="C2", selected_turn=1, asset="open")]
    ws.frame = [_receipt(world, 1, 2, 2, [10, 20], share)]
    ws.frame_turn = world.turn
    pay.firms = [_firm(0, 1, 1, cash=1000, owed=[(5, 100)]), _firm(1, 2, 2, cash=wage)]
    sim = Sim({1: [10, 20]})
    sim.wealth[5] = 10.0
    sim.reserve_work(world.turn, 0, [(10, share), (20, share)])
    bridge = SimpleNamespace(_sim=sim)

    P.finish_phase2(world, None, bridge, None)            # liquidates firm 0, paying worker 5
    assert [f.site for f in pay.firms] == [1] and pay.closed[0].closed_reason == "city_fell"
    sim.dead.add(20)                                       # dies in this turn's native tick
    sim.wealth_phase()
    P.after_agent_tick(world, bridge)
    P.phase10(world, None, None, bridge)

    firm = pay.firms[0]
    paid = {m.payee[1]: m.applied for m in pay.money if m.kind == "wage" and m.payer == ("workshop_cash", 1)}
    assert 20 not in paid, "a worker who died in the tick shared the scarce cash"
    assert paid == {10: wage}
    assert firm.cash == 0 and firm.owed == []
    row = next(r for r in pay.frame if r.site == 1)
    assert row.owed_lapsed == wage


def test_phase10_reads_the_living_once_after_the_tick_without_a_phase2_liquidation():
    """Control for the above: no Phase 2 liquidation, the same death."""
    world = _world(mode="no_customer")
    ws, pay = world.livelihoods.workshops, world.livelihoods.workshop_payroll
    share = 0.3
    wage = P._wage(share)
    ws.sites = [WorkshopSite(site=1, region=2, settlement_id=2, city_name="C2", selected_turn=1, asset="open")]
    ws.frame = [_receipt(world, 1, 2, 2, [10, 20], share)]
    ws.frame_turn = world.turn
    pay.firms = [_firm(1, 2, 2, cash=wage)]
    sim = Sim({1: [10, 20]})
    sim.reserve_work(world.turn, 0, [(10, share), (20, share)])
    bridge = SimpleNamespace(_sim=sim)
    P.finish_phase2(world, None, bridge, None)
    sim.dead.add(20)
    sim.wealth_phase()
    P.after_agent_tick(world, bridge)
    P.phase10(world, None, None, bridge)
    paid = {m.payee[1]: m.applied for m in pay.money if m.kind == "wage"}
    assert paid == {10: wage} and pay.firms[0].owed == []


def test_paid_work_is_armed_only_for_reserved_crew_and_a_rollback_disarms_it():
    """Contract: paid time is always reserved time; a failed Phase 2 leaves no arming."""
    world = _world(mode="paid")
    ws, pay = world.livelihoods.workshops, world.livelihoods.workshop_payroll
    ws.sites = [WorkshopSite(site=1, region=2, settlement_id=2, city_name="C2", selected_turn=1, asset="open")]
    ws.frame = [_receipt(world, 1, 2, 2, [10, 20], 0.3)]
    ws.frame_turn = world.turn
    pay.firms = [_firm(1, 2, 2, cash=0)]
    sim = Sim({1: [10, 20]})
    bridge = SimpleNamespace(_sim=sim)
    sim.reserve_work(world.turn, 0, [(10, 0.3)])           # 20 holds no reservation
    with pytest.raises(ValueError, match="reservation"):
        P.finish_phase2(world, None, bridge, None)
    assert sim.paid is None and pay._turn is None
    sim.reserve_work(world.turn, 0, [(20, 0.3)])
    P.finish_phase2(world, None, bridge, None)
    assert sim.paid == (world.turn, [(10, 0.3), (20, 0.3)])
    P.rollback_phase2(world)
    assert sim.paid is None and pay._turn is None


def test_wages_never_stack_on_the_replaced_income_share_and_lapse_for_the_dead():
    """No double-paid time: for every paid person-turn the native wealth phase
    removed exactly the share that the wage pays for; a worker who died before
    the wealth phase is neither deducted nor paid."""
    world = _world(mode="paid")
    ws, pay = world.livelihoods.workshops, world.livelihoods.workshop_payroll
    share = 0.3
    ws.sites = [WorkshopSite(site=1, region=2, settlement_id=2, city_name="C2", selected_turn=1, asset="open")]
    ws.frame = [_receipt(world, 1, 2, 2, [10, 20, 30], share)]
    ws.frame_turn = world.turn
    pay.firms = [_firm(1, 2, 2, cash=5000)]
    sim = Sim({1: [10, 20, 30]})
    sim.reserve_work(world.turn, 0, [(10, share), (20, share), (30, share)])
    bridge = SimpleNamespace(_sim=sim)
    P.finish_phase2(world, None, bridge, None)
    sim.dead.add(30)                                        # a catastrophe death before the wealth phase
    sim.wealth_phase()
    P.after_agent_tick(world, bridge)
    P.phase10(world, None, None, bridge)
    paid = {m.payee[1]: m.applied for m in pay.money if m.kind == "wage"}
    assert set(paid) == {10, 20} and pay._turn is None
    row = pay.frame[0]
    assert row.income_replaced == pytest.approx(2 * sim.income * share)
    assert row.owed_lapsed == P._wage(share)


def test_a_failed_agent_tick_disarms_the_paid_work_share():
    """Contract (failed-tick rollback): when the agent tick raises, pending
    work commitments are released. The paid-work share armed in Phase 2 for
    the crew must not stay armed natively after the failed tick."""
    from chronicler.livelihoods import wrap_agent_tick
    world = _world(mode="paid")
    ws, pay = world.livelihoods.workshops, world.livelihoods.workshop_payroll
    ws.sites = [WorkshopSite(site=1, region=2, settlement_id=2, city_name="C2", selected_turn=1, asset="open")]
    ws.frame = [_receipt(world, 1, 2, 2, [10, 20], 0.3)]
    ws.frame_turn = world.turn
    pay.firms = [_firm(1, 2, 2, cash=0)]
    sim = Sim({1: [10, 20]})
    sim.reserve_work(world.turn, 0, [(10, 0.3), (20, 0.3)])
    bridge = SimpleNamespace(_sim=sim)
    P.finish_phase2(world, None, bridge, None)
    assert sim.paid is not None

    def failing_tick(*args, **kwargs):
        raise RuntimeError("injected agent tick failure")

    tick = wrap_agent_tick(world, bridge, failing_tick, None)
    with pytest.raises(RuntimeError, match="injected"):
        tick(world)
    assert sim.paid is None, "the paid-work share stayed armed after a failed agent tick"
