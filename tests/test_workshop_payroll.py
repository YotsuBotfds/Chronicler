"""L6a workshop payroll without the native extension.

A stand-in simulator supplies crews, craft inputs, the paid-work share the
wealth phase consumes and stable-id wealth transfers with the native limits.
Everything else is the real L1 workshop and L6a payroll code.
"""
from __future__ import annotations

import math
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import workshop_payroll as P
from chronicler import workshops as W
from chronicler.cities_state import City, CityState
from chronicler.economy import FIXED_GOODS
from chronicler.learning_services_state import AcademyMaterialInventory, AcademyProcurementReceipt
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.workshop_payroll_state import WorkshopPayrollState
from chronicler.workshops_state import WorkshopState

MAX_WEALTH = 100.0
SITE_REGION = 2


class FakeSim:
    """Native stand-in with the contracts of ``wealth_transfer.rs``."""

    def __init__(self, crew=(10, 20), wealth=10.0, income=0.3):
        self.crew = list(crew)
        self.wealth = {aid: wealth for aid in crew}
        self.dead: set[int] = set()
        self.income, self.inputs = income, None
        self.paid = self.receipt = None
        self.keys: list[tuple[int, int, int]] = []
        self.requests: list[list] = []
        self.cancelled = 0
        self.refuse_install = False

    def plan_workshop_crews(self, requests, enlisted, turn=None):
        self.requests.append(list(requests))
        rows = []
        for site, region, settlement, fraction, cap in requests:
            crew = [a for a in self.crew if a not in self.dead][:cap]
            rows.append((site, region, settlement, len(crew), 0, 0, 0, len(crew), crew, [30] * len(crew),
                         len(crew) * fraction))
        return rows

    def take_craft_inputs(self):
        out, self.inputs = self.inputs, None
        return out

    def get_stockpile_commitments(self):
        n = self._regions
        return pa.record_batch({
            "region_id": pa.array([r for r in range(n) for _ in FIXED_GOODS], pa.uint16()),
            "good_slot": pa.array([g for _ in range(n) for g in range(len(FIXED_GOODS))], pa.uint8()),
            "reserved": pa.array([0.0] * n * len(FIXED_GOODS), pa.float32()),
            "pending_departure": pa.array([0.0] * n * len(FIXED_GOODS), pa.float32()),
        })

    def install_paid_work(self, turn, rows):
        if self.refuse_install:
            raise ValueError("paid work exceeds the agent's work reservation this turn")
        if self.paid is not None:
            raise ValueError("paid work share already pending")
        self.paid = (turn, list(rows))

    def cancel_paid_work(self):
        had = self.paid is not None
        self.paid = None
        self.cancelled += had
        return had

    def wealth_phase(self):
        if self.paid is None:
            return
        turn, rows = self.paid
        out = []
        for aid, share in rows:
            if aid in self.dead:
                continue
            out.append((aid, share, self.income, self.income * share))
            self.wealth[aid] = self.wealth[aid] + self.income * (1 - share)
        self.receipt, self.paid = (turn, out), None

    def take_paid_work_receipt(self):
        out, self.receipt = self.receipt, None
        return out

    def transfer_wealth(self, turn, purpose, batch, rows):
        if any(p == purpose and b == batch and t >= turn for t, p, b in self.keys):
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        if len({aid for aid, _ in rows}) != len(rows):
            raise ValueError("duplicate agent in wealth transfer")
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


def _region(i, controller="Civ0"):
    return SimpleNamespace(name=f"R{i}", controller=controller, stockpile=SimpleNamespace(goods={"crafts": 0.0}))


def _world(mode="paid", treasury=(1000, 1000), academy=True, regions=4):
    civs = [SimpleNamespace(name=f"Civ{i}", treasury=t) for i, t in enumerate(treasury)]
    world = SimpleNamespace(
        turn=20, agent_mode="hybrid", civilizations=civs, regions=[_region(i) for i in range(regions)],
        cities=CityState(cities=[City(settlement_id=1, region=SITE_REGION, name="C1", founded_turn=1,
                                      founder=0, rank=2, size=10.0)]),
        livelihoods=LivelihoodsState(), war_state=SimpleNamespace(armies=[]), scholarship=None)
    world.livelihoods.workshops = WorkshopState(mode="operate")
    world.livelihoods.workshop_payroll = WorkshopPayrollState(mode=mode)
    world.academy = academy
    return world


def _academy_procurement(world, lord=0, seat=0, region=1, price=2.0, learners=40, scholars=4):
    """The academy procurement of this turn (a fully informed purchaser)."""
    services = getattr(getattr(world, "scholarship", None), "learning_services", None)
    if services is None:
        asset = AcademyMaterialInventory(seat_id=seat, region=region, founder=lord, founded_turn=1,
                                         seat_name="Seat", held=0.0, purchased_total=0.0, used_total=0.0,
                                         lost_total=0.0)
        services = SimpleNamespace(enabled=True, inventories=[asset], procurement_receipts=[],
                                   last_procurement_turn=None)
        world.scholarship = SimpleNamespace(learning_services=services)
    asset = services.inventories[0]
    services.procurement_receipts = [AcademyProcurementReceipt(
        seat_id=seat, region=region, founder=asset.founder, founded_turn=1, seat_name="Seat", lord=lord,
        source_turn=world.turn, upkeep_source_turn=world.turn, upkeep_due=1, upkeep_amount_paid=1,
        upkeep_satisfied=True, scholar_upper_bound=scholars, learner_upper_bound=learners, craft_price=price,
        market_stock=0.0, market_commitments=0.0, budget_before=world.civilizations[lord].treasury,
        held_before=asset.held, purchased=0.0, paid=0, held_after=asset.held, shortfalls=())]
    services.last_procurement_turn = world.turn
    return asset


def _batch(n=4, ceiling=1.5):
    return pa.record_batch({"region_id": pa.array(range(n), pa.uint16()),
                            "craft_raw_demand": pa.array([ceiling] * n, pa.float32())})


def _turn(world, sim, output=0.0, stock_after=None, lord=0):
    """One whole turn: Phase 2 (workshop + payroll), the agent tick's wealth
    phase, academy procurement and the payroll's Phase 10."""
    sim._regions = len(world.regions)
    bridge = SimpleNamespace(_sim=sim)
    batch = W.prepare_phase2(world, _batch(len(world.regions)), bridge, None, None)
    P.prepare_phase2(world, batch, bridge, None, None)
    goods = [[0.0] * 9 for _ in world.regions]
    for s in world.livelihoods.workshops.sites:
        goods[s.region][3] = output
    sim.inputs = goods
    W.finish_phase2(world, SimpleNamespace(craft_output={r.name: output for r in world.regions}), bridge, None)
    region = world.regions[SITE_REGION]
    region.stockpile.goods["crafts"] += output if stock_after is None else stock_after
    try:
        P.finish_phase2(world, None, bridge, None)
    except Exception:
        W.rollback_phase2(world)
        P.rollback_phase2(world)
        raise
    sim.wealth_phase()
    P.after_agent_tick(world, bridge)
    if world.academy:
        _academy_procurement(world, lord=lord)
    P.phase10(world, None, None, bridge)
    world.turn += 1
    return batch


def _build(world, sim):
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        _turn(world, sim)


def _firm(world):
    return world.livelihoods.workshop_payroll.firms[0]


def _receipt(world):
    return world.livelihoods.workshop_payroll.frame[0]


def test_sales_fund_wages_and_every_account_closes():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    treasury = world.civilizations[0].treasury
    l1_paid = sum(world.livelihoods.workshops.counters.get(k, 0) for k in ("paid_upkeep", "paid_arrears", "paid_repair"))
    for _ in range(6):
        _turn(world, sim, output=1.2)
        P.check_firm(_firm(world))
    firm, r = _firm(world), _receipt(world)
    state = world.livelihoods.workshop_payroll
    # Rank 2: d = 0.3; two crew at full hours.
    assert r.crew == [10, 20] and r.shares == [pytest.approx(0.3)] * 2 and r.operating
    assert r.wages_due == 2 * 150 and r.wages_paid == 2 * 150 and r.owed_after == 0
    assert r.income_replaced == pytest.approx(2 * 0.3 * 0.3)
    # The workshop receipt reports the replaced ordinary income share.
    assert world.livelihoods.workshops.frame[0].affected_ordinary_income_share == pytest.approx(0.3)
    # Typed transfers: buyer treasury -> firm cash, firm -> agents, firm -> academy.
    kinds = {m.kind for m in state.money}
    assert {"sale", "wage"} <= kinds
    sale = next(m for m in state.money if m.kind == "sale")
    assert sale.payer == ("civ_treasury", 0) and sale.payee == ("workshop_cash", firm.site)
    delivery = next(m for m in state.materials if m.kind == "delivery")
    assert delivery.source == ("workshop_inventory", firm.site) and delivery.dest == ("academy_inventory", 0)
    # Totals: buyer paid exactly the firm's sales; the academy holds what was delivered.
    l1_paid = sum(world.livelihoods.workshops.counters.get(k, 0)
                  for k in ("paid_upkeep", "paid_arrears", "paid_repair")) - l1_paid
    paid_by_buyer = treasury - world.civilizations[0].treasury - l1_paid
    assert paid_by_buyer * 1000 == firm.totals["sales"] - firm.totals.get("distributed", 0)
    asset = world.scholarship.learning_services.inventories[0]
    assert asset.held == pytest.approx(firm.totals["delivered"] / 1000)
    assert asset.purchased_total - asset.used_total - asset.lost_total == pytest.approx(asset.held)
    # Cash and inventory close exactly; the crew got their wages by stable id.
    assert firm.cash == firm.totals["sales"] - firm.totals["wages"] - firm.totals.get("distributed", 0)
    assert firm.inventory == firm.totals["titled"] - firm.totals["delivered"] - firm.totals.get("worn", 0)
    assert state.counters["wages_paid"] == firm.totals["wages"]
    # Wares titled never also sit in the region's stock.
    assert world.regions[SITE_REGION].stockpile.goods["crafts"] == pytest.approx(0.0, abs=1e-9)


def test_without_an_order_the_site_stays_a_public_workshop():
    world = _world(academy=False)
    sim = FakeSim()
    _build(world, sim)
    for _ in range(3):
        _turn(world, sim, output=1.0)
    state = world.livelihoods.workshop_payroll
    assert not state.firms and sim.paid is None and sim.keys == []
    assert state.counters["operating_without_order"] == 3
    assert world.livelihoods.workshops.frame[0].affected_ordinary_income_share == 0.0
    # Output stays in the region's shared stock; nothing is titled or charged.
    assert world.regions[SITE_REGION].stockpile.goods["crafts"] == pytest.approx(3.0)
    # An academy order (last turn's procurement) opens the firm.
    world.academy = True
    _turn(world, sim, output=1.0)
    assert not state.firms
    _turn(world, sim, output=1.0)
    assert state.firms and state.firms[0].history[0][1:] == ("opened", 0)


def test_title_is_bounded_by_output_uncommitted_stock_and_the_cap():
    world = _world(mode="no_customer")
    sim = FakeSim()
    _build(world, sim)
    # The region's market used part of the output first: only what is left is titled.
    _turn(world, sim, output=1.0, stock_after=0.4)
    assert _receipt(world).titled == 400 and _receipt(world).title_basis == pytest.approx(0.4)
    assert world.regions[SITE_REGION].stockpile.goods["crafts"] == pytest.approx(0.0, abs=1e-9)
    # Extra older stock never becomes the firm's: at most this turn's output.
    world.regions[SITE_REGION].stockpile.goods["crafts"] = 5.0
    _turn(world, sim, output=1.0, stock_after=0.0)
    assert _receipt(world).titled == 1000
    assert world.regions[SITE_REGION].stockpile.goods["crafts"] == pytest.approx(4.0)
    firm = _firm(world)
    extra = P.INVENTORY_CAP - firm.inventory
    firm.inventory += extra
    firm.totals["titled"] += extra
    P.check_firm(firm)
    _turn(world, sim, output=1.0)
    assert _receipt(world).titled == 0


def test_no_customer_pressure_cuts_hours_then_crew_then_closes_the_firm():
    world = _world(mode="no_customer")
    sim = FakeSim(crew=tuple(range(10, 18)))
    _build(world, sim)
    history = []
    for _ in range(P.CLOSE_AFTER):
        _turn(world, sim, output=1.0)
        r = _receipt(world)
        history.append((r.hours, r.crew_cap, r.insolvent, r.sales))
    assert all(insolvent and sales == 0 for _, _, insolvent, sales in history)
    # Hours fall each insolvent turn; crew cuts start on the second.
    assert [h for h, *_ in history] == [1.0, 0.75, 0.5, 0.25, 0.25, 0.25]
    assert [c for _, c, *_ in history] == [8, 8, 6, 4, 2, 1]
    # The reduced terms reached the crew planner: fraction d x hours, smaller cap.
    assert sim.requests[-1][0][3] == pytest.approx(0.3 * 0.25) and sim.requests[-1][0][4] == 1
    state = world.livelihoods.workshop_payroll
    assert not state.firms and state.closed[0].closed_reason == "insolvent"
    sites = world.livelihoods.workshops
    assert not sites.sites and sites.closed[-1].closed_reason == "insolvent"
    # Owed wages were written off; held wares went back to the region's market.
    assert state.counters["owed_written_off"] > 0 and state.counters.get("wages_paid", 0) == 0
    firm = state.closed[0]
    assert firm.inventory == 0 and firm.totals["returned"] > 0 and firm.owed == []
    P.check_firm(firm)
    assert world.regions[SITE_REGION].stockpile.goods["crafts"] == pytest.approx(firm.totals["returned"] / 1000)
    # The closed city is never readmitted; the region returns to its legacy ceiling.
    batch = _turn(world, sim, output=0.0)
    assert batch.column("craft_raw_demand").to_pylist()[SITE_REGION] == pytest.approx(1.5)


def test_unpaid_labor_replaces_the_income_share_without_a_wage():
    world = _world(mode="unpaid_labor")
    sim = FakeSim()
    _build(world, sim)
    before = dict(sim.wealth)
    owner_before = world.civilizations[0].treasury
    upkeep_before = world.livelihoods.workshops.counters.get("paid_upkeep", 0)
    for _ in range(4):
        _turn(world, sim, output=1.2)
    state = world.livelihoods.workshop_payroll
    assert state.counters.get("wages_due", 0) == 0 and state.counters.get("wages_paid", 0) == 0
    assert state.counters["income_replaced"] == pytest.approx(4 * 2 * 0.3 * 0.3)
    assert state.counters["sales"] > 0
    # The crew earned only 70% of ordinary income: the unpaid job harms them.
    assert all(sim.wealth[a] == pytest.approx(before[a] + 4 * 0.3 * 0.7) for a in before)
    # With no wage bill there is no reserve: sales go back to the owner.
    firm = _firm(world)
    assert firm.cash < 1000 and firm.totals["distributed"] > 0
    upkeep = world.livelihoods.workshops.counters["paid_upkeep"] - upkeep_before
    spent = owner_before - world.civilizations[0].treasury - upkeep
    assert spent * 1000 == firm.totals["sales"] - firm.totals["distributed"]


def test_paid_wages_help_the_crew_relative_to_unpaid_labor():
    paid_world, unpaid_world = _world(), _world(mode="unpaid_labor")
    paid, unpaid = FakeSim(), FakeSim()
    for world, sim in ((paid_world, paid), (unpaid_world, unpaid)):
        _build(world, sim)
        for _ in range(5):
            _turn(world, sim, output=1.2)
    for aid in paid.wealth:
        # +0.15 wage a turn against 0.09 of replaced ordinary income.
        assert paid.wealth[aid] - unpaid.wealth[aid] == pytest.approx(5 * 0.15)


def test_wealth_ceiling_residuals_stay_in_cash_and_dead_workers_claims_lapse():
    world = _world()
    sim = FakeSim(wealth=10.0, income=0.0)
    _build(world, sim)
    sim.wealth[10] = MAX_WEALTH - 0.0625                 # room for 62 whole milli-units
    _turn(world, sim, output=1.2)
    r = _receipt(world)
    assert r.wages_cap_residual == 88 and r.wages_paid == 150 + 62 and r.owed_after == 0
    wage = [m for m in world.livelihoods.workshop_payroll.money if m.kind == "wage" and m.payee[1] == 10][0]
    assert (wage.applied, wage.residual, wage.status) == (62, 88, "limited")
    assert sim.wealth[10] <= MAX_WEALTH
    P.check_firm(_firm(world))
    # A worker who dies before the wealth phase: no deduction, no payment, claim lapses.
    sim.dead.add(20)
    _turn(world, sim, output=1.2)
    r = _receipt(world)
    assert r.crew == [10]                         # the planner no longer resolves the dead
    assert world.livelihoods.workshop_payroll.counters.get("owed_lapsed", 0) == 0
    _firm(world).owed.append(P.OwedWage(agent_id=20, amount=300, since_turn=world.turn - 1))
    _turn(world, sim, output=1.2)
    assert _receipt(world).owed_lapsed == 300 and all(o.agent_id != 20 for o in _firm(world).owed)
    assert _receipt(world).owed_after == 0


def test_partial_fills_owe_the_rest_and_pay_it_first_from_later_cash():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    world.academy = False                      # the order stands, but nobody buys this turn
    _turn(world, sim, output=1.0)
    firm = _firm(world)
    assert _receipt(world).owed_after == 300 and _receipt(world).insolvent
    assert [(o.agent_id, o.amount) for o in firm.owed] == [(10, 150), (20, 150)]
    # Cash arrives (a sale): what is owed and this turn's (shorter) wages are paid.
    world.academy = True
    _turn(world, sim, output=1.5)
    r = _receipt(world)
    assert r.hours == 0.75 and r.wages_due == 2 * P._wage(W._diverted(2) * 0.75)
    assert r.sales > 0 and r.wages_paid == 300 + r.wages_due and r.owed_after == 0 and not r.insolvent
    P.check_firm(firm)
    assert P._pro_rata(5, {1: 3, 2: 3, 3: 3}) == {1: 2, 2: 2, 3: 1}
    assert sum(P._pro_rata(997, {4: 450, 9: 300, 2: 250}).values()) == 997


def test_conquest_moves_the_customer_and_the_owner_but_the_firm_keeps_its_books():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    world.academy = False
    _turn(world, sim, output=1.0)
    owed = _receipt(world).owed_after
    assert owed > 0
    world.regions[SITE_REGION].controller = "Civ1"
    before = [c.treasury for c in world.civilizations]
    # A Civ0 academy no longer buys from the site; a Civ1 academy does.
    world.academy = True
    _turn(world, sim, output=1.0, lord=0)
    assert _receipt(world).sales == 0 and _receipt(world).controller == 1
    assert world.civilizations[0].treasury == before[0]
    _turn(world, sim, output=1.0, lord=1)
    r = _receipt(world)
    assert r.controller == 1 and r.sales > 0
    assert world.civilizations[0].treasury == before[0]
    assert world.civilizations[1].treasury < before[1]
    assert _firm(world).site == world.livelihoods.workshops.sites[0].site


def test_city_fall_liquidates_the_firm_once():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    world.academy = False
    _turn(world, sim, output=1.0)
    firm = _firm(world)
    firm.cash += 2500                          # constructed: a sale's proceeds
    firm.totals["sales"] = firm.totals.get("sales", 0) + 2500
    held = firm.inventory
    owed = sum(o.amount for o in firm.owed)
    fallen = world.cities.cities.pop()
    world.cities.fallen.append(fallen)
    treasury = world.civilizations[0].treasury
    _turn(world, sim)
    state = world.livelihoods.workshop_payroll
    assert not state.firms and state.closed[0].closed_reason == "city_fell"
    closed = state.closed[0]
    assert closed.totals["wages"] >= owed and closed.owed == [] and closed.cash == 0
    assert closed.totals["returned"] == held
    units = (2500 - owed) // 1000
    assert world.civilizations[0].treasury == treasury + units
    assert closed.totals["written_off"] == 2500 - owed - units * 1000
    P.check_firm(closed)


def test_failed_install_moves_nothing_and_rollback_cancels_armed_work():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    sim.refuse_install = True
    with pytest.raises(ValueError, match="reservation"):
        _turn(world, sim, output=1.0)
    state = world.livelihoods.workshop_payroll
    assert state._turn is None and not state.firms
    assert world.regions[SITE_REGION].stockpile.goods["crafts"] == pytest.approx(1.0)
    # A later failure after arming: rollback cancels the native share once.
    sim.refuse_install = False
    world.regions[SITE_REGION].stockpile.goods["crafts"] = 0.0
    bridge = SimpleNamespace(_sim=sim)
    sim._regions = len(world.regions)
    batch = W.prepare_phase2(world, _batch(), bridge, None, None)
    P.prepare_phase2(world, batch, bridge, None, None)
    sim.inputs = [[0.0] * 9 for _ in world.regions]
    W.finish_phase2(world, SimpleNamespace(craft_output={}), bridge, None)
    P.finish_phase2(world, None, bridge, None)
    assert sim.paid is not None
    P.rollback_phase2(world)
    assert sim.paid is None and sim.cancelled == 1 and state._turn is None


def test_each_turn_settles_once_and_survives_an_exact_round_trip():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    for _ in range(3):
        _turn(world, sim, output=1.1)
    bridge = SimpleNamespace(_sim=sim)
    world.turn -= 1
    with pytest.raises(ValueError, match="already settled"):
        P.prepare_phase2(world, None, bridge, None, None)
    world.turn += 1
    # Exact pickle and JSON round trips continue identically.
    restored = _world()
    restored.turn = world.turn
    restored.civilizations[0].treasury = world.civilizations[0].treasury
    restored.livelihoods = pickle.loads(pickle.dumps(world.livelihoods))
    restored.scholarship = pickle.loads(pickle.dumps(world.scholarship))
    restored.regions[SITE_REGION].stockpile.goods["crafts"] = world.regions[SITE_REGION].stockpile.goods["crafts"]
    payroll = world.livelihoods.workshop_payroll
    assert type(payroll).model_validate_json(payroll.model_dump_json()).model_dump() == payroll.model_dump()
    twin = FakeSim()
    twin.wealth = dict(sim.wealth)
    twin.keys = list(sim.keys)
    for _ in range(4):
        _turn(world, sim, output=0.9)
        _turn(restored, twin, output=0.9)
    assert restored.livelihoods.model_dump() == world.livelihoods.model_dump()
    assert twin.wealth == sim.wealth
    assert restored.civilizations[0].treasury == world.civilizations[0].treasury
    # Every wage transfer key was used exactly once.
    assert len(sim.keys) == len(set(sim.keys))


def test_without_payroll_the_workshop_requests_are_unchanged():
    world = _world()
    world.livelihoods.workshop_payroll = None
    sim = FakeSim()
    sim._regions = 4
    W.prepare_phase2(world, _batch(), SimpleNamespace(_sim=sim), None, None)
    assert sim.requests[-1] == [(0, SITE_REGION, 1, W._diverted(2), W.MAX_CREW)]
    W.rollback_phase2(world)
    world.livelihoods.workshop_payroll = WorkshopPayrollState(enabled=False)
    W.prepare_phase2(world, _batch(), SimpleNamespace(_sim=sim), None, None)
    assert sim.requests[-1] == [(0, SITE_REGION, 1, W._diverted(2), W.MAX_CREW)]


def test_snapshot_is_dated_and_unknown_when_stale():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    _turn(world, sim, output=1.0)
    summary = P.snapshot_summary(world)
    assert summary["stage"] == "L6a" and summary["source_turn"] == world.turn - 1
    assert summary["receipts"][0]["crew"] == [10, 20] and summary["transfers"]["money"]
    assert summary["units"]["milli"] == 1000 and summary["parameters"]["wage_per_work"] == P.WAGE_PER_WORK
    world.turn += 1
    stale = P.snapshot_summary(world)
    assert stale["receipts"] is None and stale["transfers"] is None


def test_prerequisites_and_modes():
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=6, num_civs=2)
    world.cities = CityState()
    parse = _build_parser().parse_args
    with pytest.raises(ValueError, match="operate mode"):
        configure_livelihoods(world, parse(["--workshop-payroll"]), agent_mode="hybrid")
    with pytest.raises(ValueError, match="operate mode"):
        configure_livelihoods(world, parse(["--workshops", "--workshop-mode", "cost_only", "--workshop-payroll"]),
                              agent_mode="hybrid")
    assert world.livelihoods is None
    args = parse(["--workshops", "--workshop-payroll", "--workshop-payroll-mode", "unpaid_labor"])
    configure_livelihoods(world, args, agent_mode="hybrid")
    assert world.livelihoods.workshop_payroll.mode == "unpaid_labor"
    assert P.workshop_payroll_active(world)
    configure_livelihoods(world, parse(["--no-workshop-payroll"]), agent_mode="hybrid")
    assert not P.workshop_payroll_active(world) and P.crew_terms(world, 0) == (8, 1.0)
