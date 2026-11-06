"""A3 workshop economics (``--workshop-economics``) without the native extension.

A stand-in simulator supplies crews, the paid-work share, stable-id wealth
transfers with the native limits (including the appended ``wares_purchase``
purpose) and a snapshot of residents (id, region, age, parents, wealth). A
small stand-in economy converts raw inputs 1:1 up to the region's craft
ceiling, lets the people draw their 0.01 wares a head free from the commons,
and reports post-trade prices. Everything else is the real L1 workshop, L6a
payroll, A3 economics and payment-seam code.
"""
from __future__ import annotations

import math
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import money as M
from chronicler import workshop_economics as E
from chronicler import workshop_payroll as P
from chronicler import workshops as W
from chronicler.cities_state import City, CityState
from chronicler.economy import FIXED_GOODS
from chronicler.learning_services_state import AcademyMaterialInventory, AcademyProcurementReceipt
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.workshop_economics_state import WorkshopEconomicsState
from chronicler.workshop_payroll_state import WorkshopPayrollState
from chronicler.workshops_state import WorkshopState

MAX_WEALTH = 100.0
SITE = 2
TIMBER = FIXED_GOODS.index("timber")
ORE = FIXED_GOODS.index("ore")


class FakeSim:
    """Native stand-in: crews, paid work, keyed transfers, residents."""

    def __init__(self, crew=(10, 20), adults=(30, 31, 32), children=((40, 30), (41, 99)), wealth=5.0,
                 crew_wealth=10.0, income=0.3):
        self.people: dict[int, dict] = {}
        for aid in crew:
            self.people[aid] = dict(region=SITE, age=30, p0=0, p1=0, wealth=crew_wealth)
        for aid in adults:
            self.people[aid] = dict(region=SITE, age=40, p0=0, p1=0, wealth=wealth)
        for aid, parent in children:
            self.people[aid] = dict(region=SITE, age=8, p0=parent, p1=0, wealth=0.5)
        self.crew = list(crew)
        self.dead: set[int] = set()
        self.income, self.inputs = income, None
        self.paid = self.receipt = None
        self.keys: list[tuple[int, int, int]] = []
        self.transfers: list[tuple[int, int, int, list]] = []
        self.requests: list[list] = []

    @property
    def wealth(self):
        return {a: p["wealth"] for a, p in self.people.items() if a not in self.dead}

    def wealth_transfer_purposes(self):
        return list(M.NATIVE_PURPOSES)

    def plan_workshop_crews(self, requests, enlisted, turn=None):
        self.requests.append(list(requests))
        rows = []
        for site, region, settlement, fraction, cap in requests:
            assert 1 <= cap <= 8
            pool = [a for a in self.crew if a not in self.dead]
            crew = pool[:cap]
            rows.append((site, region, settlement, len(pool), 0, 0, 0, len(pool), crew, [30] * len(crew),
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
        if self.paid is not None:
            raise ValueError("paid work share already pending")
        self.paid = (turn, list(rows))

    def cancel_paid_work(self):
        had = self.paid is not None
        self.paid = None
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
            self.people[aid]["wealth"] += self.income * (1 - share)
        self.receipt, self.paid = (turn, out), None

    def take_paid_work_receipt(self):
        out, self.receipt = self.receipt, None
        return out

    def get_snapshot(self):
        ids = sorted(a for a in self.people if a not in self.dead)
        col = lambda k, t: pa.array([self.people[a][k] for a in ids], t)  # noqa: E731
        return pa.record_batch({"id": pa.array(ids, pa.uint32()), "region": col("region", pa.uint16()),
                                "age": col("age", pa.uint16()), "parent_id_0": col("p0", pa.uint32()),
                                "parent_id_1": col("p1", pa.uint32()), "wealth": col("wealth", pa.float32())})

    def transfer_wealth(self, turn, purpose, batch, rows):
        if any(p == purpose and b == batch and t >= turn for t, p, b in self.keys):
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        if len({aid for aid, _ in rows}) != len(rows):
            raise ValueError("duplicate agent in wealth transfer")
        self.keys.append((turn, purpose, batch))
        self.transfers.append((turn, purpose, batch, list(rows)))
        out = []
        for aid, amount in rows:
            if aid in self.dead or aid not in self.people:
                out.append((aid, amount, 0, amount, 2))
                continue
            w = float(pa.scalar(self.people[aid]["wealth"], pa.float32()).as_py())
            applied = min(amount, math.floor((MAX_WEALTH - w) * 1000)) if amount >= 0 \
                else -min(-amount, math.floor(w * 1000))
            self.people[aid]["wealth"] = w + applied / 1000
            out.append((aid, amount, applied, amount - applied, 0 if applied == amount else 1))
        return out


def _region(i, controller="Civ0"):
    return SimpleNamespace(name=f"R{i}", controller=controller, stockpile=SimpleNamespace(goods={"crafts": 0.0}))


def _world(mode="market", payroll="paid", treasury=(1000, 1000), regions=4):
    civs = [SimpleNamespace(name=f"Civ{i}", treasury=t) for i, t in enumerate(treasury)]
    world = SimpleNamespace(
        turn=20, agent_mode="hybrid", civilizations=civs, regions=[_region(i) for i in range(regions)],
        cities=CityState(cities=[City(settlement_id=1, region=SITE, name="C1", founded_turn=1,
                                      founder=0, rank=2, size=10.0)]),
        livelihoods=LivelihoodsState(), war_state=SimpleNamespace(armies=[]), scholarship=None)
    world.livelihoods.workshops = WorkshopState(mode="operate")
    world.livelihoods.workshop_payroll = WorkshopPayrollState(mode=payroll)
    if mode is not None:
        world.livelihoods.workshop_economics = WorkshopEconomicsState(mode=mode)
    world.academy = False
    world.raw = 100.0                  # raw loads on hand in the site region each turn
    world.prices = {"raw_material": 0.5, "craft": 2.0}
    return world


def _academy_procurement(world, lord=0, price=2.0, learners=40, scholars=4):
    services = getattr(getattr(world, "scholarship", None), "learning_services", None)
    if services is None:
        asset = AcademyMaterialInventory(seat_id=0, region=1, founder=lord, founded_turn=1, seat_name="Seat",
                                         held=0.0, purchased_total=0.0, used_total=0.0, lost_total=0.0)
        services = SimpleNamespace(enabled=True, inventories=[asset], procurement_receipts=[],
                                   last_procurement_turn=None)
        world.scholarship = SimpleNamespace(learning_services=services)
    asset = services.inventories[0]
    services.procurement_receipts = [AcademyProcurementReceipt(
        seat_id=0, region=1, founder=asset.founder, founded_turn=1, seat_name="Seat", lord=lord,
        source_turn=world.turn, upkeep_source_turn=world.turn, upkeep_due=1, upkeep_amount_paid=1,
        upkeep_satisfied=True, scholar_upper_bound=scholars, learner_upper_bound=learners, craft_price=price,
        market_stock=0.0, market_commitments=0.0, budget_before=world.civilizations[lord].treasury,
        held_before=asset.held, purchased=0.0, paid=0, held_after=asset.held, shortfalls=())]
    services.last_procurement_turn = world.turn
    return asset


def _batch(n=4, ceiling=1.5):
    return pa.record_batch({"region_id": pa.array(range(n), pa.uint16()),
                            "craft_raw_demand": pa.array([ceiling] * n, pa.float32())})


def _residents(sim):
    return sum(1 for a, p in sim.people.items() if a not in sim.dead and p["region"] == SITE)


def _turn(world, sim, lord=0):
    """One whole turn: Phase 2 (workshop, payroll and A3 seams), the stand-in
    economy, the wealth phase, academy procurement and Phase 10 (with the A1
    ledger's opening first and closing last when it is on)."""
    sim._regions = len(world.regions)
    bridge = SimpleNamespace(_sim=sim)
    ledger = getattr(world.livelihoods, "wealth_accounting", None) is not None
    if ledger:
        from chronicler import wealth_accounting as WA
        WA.prepare_phase2(world, None, bridge, sim.get_snapshot(), None)
    batch = W.prepare_phase2(world, _batch(len(world.regions)), bridge, None, None)
    P.prepare_phase2(world, batch, bridge, None, None)
    ceiling = float(batch.column("craft_raw_demand").to_pylist()[SITE])
    ws = world.livelihoods.workshops
    output = min(ceiling, world.raw) if any(s.region == SITE for s in ws.sites) else 0.0
    goods = [[0.0] * len(FIXED_GOODS) for _ in world.regions]
    goods[SITE][TIMBER], goods[SITE][ORE] = output * 0.75, output * 0.25
    sim.inputs = goods
    economy = SimpleNamespace(craft_output={r.name: (output if i == SITE else 0.0) for i, r in enumerate(world.regions)},
                              market_prices={r.name: dict(world.prices) for r in world.regions})
    W.finish_phase2(world, economy, bridge, None)
    # The tick: output enters the commons, the people draw their demand free.
    region = world.regions[SITE]
    stock = region.stockpile.goods["crafts"] + output
    region.stockpile.goods["crafts"] = max(0.0, stock - 0.01 * _residents(sim))
    world.last_ceiling, world.last_output = ceiling, output
    try:
        P.finish_phase2(world, economy, bridge, None)
    except Exception:
        W.rollback_phase2(world)
        P.rollback_phase2(world)
        raise
    sim.wealth_phase()
    P.after_agent_tick(world, bridge)
    if world.academy:
        _academy_procurement(world, lord=lord)
    P.phase10(world, None, economy, bridge)
    if ledger:
        WA.phase10(world, None, economy, bridge)
    world.turn += 1
    return batch


def _build(world, sim):
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        _turn(world, sim)


def _econ(world):
    return world.livelihoods.workshop_economics


def _firm(world):
    return world.livelihoods.workshop_payroll.firms[0]


def _receipt(world):
    return _econ(world).frame[0]


def _check_turn(world):
    """Every firm's books close and the receipts' cash and inventory close."""
    payroll = world.livelihoods.workshop_payroll
    for firm in payroll.firms + payroll.closed:
        P.check_firm(firm)
        E.check_firm(world, firm)
    for r in payroll.frame:
        assert r.cash_close == (r.cash_open + (r.capital or 0) + r.sales + (r.household_sales or 0)
                                - (r.inputs or 0) - r.wages_paid - r.distributed - r.written_off
                                - (r.stipends or 0))
        assert r.inventory_close == (r.inventory_open + r.titled - r.sold - (r.household_sold or 0)
                                     - r.worn - r.returned)
    M.check_book(_econ(world).book)


# ---------------------------------------------------------------------------


def test_a_firm_opens_with_capital_once_and_its_books_close_every_turn():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    state, payroll = _econ(world), world.livelihoods.workshop_payroll
    assert state.counters.get("sites_without_firm_turns", 0) > 0
    # Opened in the Phase 10 after construction with the declared capital, paid by the ruler.
    assert len(payroll.firms) == 1
    firm, terms = _firm(world), state.firms[0]
    expected = E.CAPITAL
    assert terms.capital == expected == firm.totals["capital"] and firm.cash == expected
    assert terms.capital_payer == 0
    upkeep_before = world.livelihoods.workshops.counters.get("paid_upkeep", 0)
    assert _receipt(world).capital_in == expected and _receipt(world).event == "opened"
    treasury = world.civilizations[0].treasury
    for _ in range(8):
        _turn(world, sim)
        _check_turn(world)
    # Capital was paid once: one flow, one counter, never again.
    assert state.counters["capital_paid"] == expected and state.counters["firms_opened"] == 1
    assert firm.totals["capital"] == expected
    upkeep = world.livelihoods.workshops.counters["paid_upkeep"] - upkeep_before
    received = state.book.carry.get("0:firm_input_purchase", 0)
    # The owner's treasury: - upkeep (asset subsidy) + input receipts - nothing else (no academies).
    assert (world.civilizations[0].treasury - treasury) * 1000 + received - firm.totals.get("distributed", 0) \
        == firm.totals["inputs"] - upkeep * 1000 + (state.book.carry.get("0:firm_input_purchase", 0) - received)
    assert state.counters["asset_subsidy_firm_units"] == upkeep
    assert _receipt(world).owner_asset_spend == W.UPKEEP


def test_no_free_inputs_in_market_mode():
    world = _world()
    world.prices = {"raw_material": 0.8, "craft": 2.0}
    sim = FakeSim()
    _build(world, sim)
    state = _econ(world)
    for _ in range(6):
        cash_before = _firm(world).cash
        owed_before = sum(o.amount for o in _firm(world).owed)
        _turn(world, sim)
        _check_turn(world)
        r = _receipt(world)
        inputs = r.inputs
        if r.operating:
            # Production never exceeds the ceiling, the ceiling never what the firm could pay for.
            assert world.last_output <= world.last_ceiling + 1e-6
            assert world.last_ceiling * 1000 <= inputs["capacity_milli"] + 1e-3
            assert inputs["capacity_milli"] == (max(0, cash_before - owed_before - inputs["wage_bill_milli"]
                                                    - E.INPUT_SLACK) * 1000) // inputs["plan_price_milli"]
            used = world.last_output
            # Charged at the tick's own post-trade raw price, in full (within the reservation).
            assert inputs["charged_milli"] == inputs["cost_milli"] == math.ceil(used * inputs["price_milli"] - 1e-9) > 0
            assert inputs["payee"] == ["civ_treasury", 0] and inputs["price_milli"] == 800
            assert inputs["unpaid_conversion_milli"] == 0 and inputs["title_cap_milli"] is None
    flows = [f for f in state.book.flows if f.purpose == "firm_input_purchase"]
    assert all(f.payer == ("firm_cash", 0) and f.payee == ("civ_treasury", 0) for f in flows)
    assert state.counters["inputs_charged"] == _firm(world).totals["inputs"] > 0
    assert state.counters.get("inputs_not_charged", 0) == 0


def test_a_site_without_a_firm_produces_nothing():
    # The ruler cannot pay the capital: the site is built and funded but never operates.
    world = _world(treasury=(60 + 19, 1000))
    sim = FakeSim()
    _build(world, sim)
    for _ in range(3):
        batch = _turn(world, sim)
        assert batch.column("craft_raw_demand").to_pylist()[SITE] == 0.0
        assert world.last_output == 0.0
        receipt = world.livelihoods.workshops.frame[0]
        assert receipt.funded and receipt.asset == "open" and not receipt.allocated and receipt.eligible
    state = _econ(world)
    assert not world.livelihoods.workshop_payroll.firms and state.counters["opening_refused_treasury_short"] >= 3
    assert sim.paid is None and not [k for k in sim.keys if k[1] == 0]          # nobody employed or paid
    assert state.log[-1].kind == "opening_refused" and state.log[-1].detail["reason"] == "treasury_short"


def test_free_inputs_control_records_but_does_not_charge():
    world = _world(mode="free_inputs")
    sim = FakeSim()
    _build(world, sim)
    for _ in range(4):
        _turn(world, sim)
        _check_turn(world)
    state, firm = _econ(world), _firm(world)
    r = _receipt(world)
    assert r.operating and r.inputs["charged_milli"] == 0 and r.inputs["not_charged_milli"] > 0
    assert r.inputs["capacity_milli"] is None
    # The ceiling is the full crew's L1 ceiling: K x crew x d.
    assert world.last_ceiling == pytest.approx(W.K_RAW_PER_WORK * 2 * 0.3, rel=1e-6)
    assert firm.totals.get("inputs", 0) == 0 and state.counters["inputs_not_charged"] > 0
    assert not [f for f in state.book.flows if f.purpose == "firm_input_purchase"]


def test_households_buy_by_id_from_adults_and_credit_the_firm():
    world = _world()
    sim = FakeSim(adults=tuple(range(30, 60)), children=((70, 30), (71, 31), (72, 999)), wealth=0.05)
    sim.people[30]["wealth"] = 5.0
    sim.people[31]["wealth"] = 5.0
    _build(world, sim)
    for _ in range(3):
        _turn(world, sim)
    state = _econ(world)
    firm = _firm(world)
    seen = 0
    for _ in range(5):
        before = dict(sim.wealth)
        cash = firm.cash
        stock_before = world.regions[SITE].stockpile.goods["crafts"]
        _turn(world, sim)
        _check_turn(world)
        r = _receipt(world)
        h = r.households
        if not h["paid_milli"]:
            continue
        seen += 1
        rows = [row for t, p, b, got in sim.transfers if (t, p, b) == (world.turn - 1, 7, firm.site) for row in got]
        debited = {a: -amount for a, amount in rows}
        assert all(amount > 0 for amount in debited.values())
        # Only adults (crew included) and the orphan child 72, its own payer, pay; children 70 and 71 do not.
        assert set(debited) <= {10, 20, 72} | set(range(30, 60))
        assert 70 not in debited and 71 not in debited
        for aid, amount in debited.items():
            assert before[aid] * 1000 >= amount          # never more than the payer held
        # The households' debits are the firm's credit.
        assert sum(debited.values()) == h["paid_milli"] == h["paid_milli"]
        assert firm.cash == (cash + h["paid_milli"] + r.academy_sales - r.inputs["charged_milli"] - r.wages_paid
                             - r.distributed)
        flows = [f for f in state.book.flows if f.purpose == "wares_purchase"]
        assert sum(f.applied for f in flows) == h["paid_milli"]
        assert all(f.payee == ("firm_cash", firm.site) and f.region == SITE for f in flows)
        # Paid = charged at the craft price; delivered exactly the paid wares into the commons.
        assert h["price_milli"] == 2000 and h["gap_milli"] == max(0, h["demand_milli"] - h["commons_milli"])
        assert h["bought_milli"] <= h["offered_milli"] <= h["gap_milli"]
        assert h["priced_out_households"] > 0            # most adults hold 0.05: priced out
        assert firm.totals["household_sales"] >= h["paid_milli"]
        # Native keys: one collection per firm and turn (purpose 7, batch = firm).
        assert (world.turn - 1, 7, firm.site) in sim.keys
    assert seen >= 1 and state.counters["household_sales"] == firm.totals["household_sales"]


def test_academy_only_mode_has_no_household_customers():
    world = _world(mode="academy_only")
    sim = FakeSim()
    _build(world, sim)
    world.academy = True
    for _ in range(5):
        _turn(world, sim)
        _check_turn(world)
        assert "academy_only_mode" in _receipt(world).customer_absent
    state, firm = _econ(world), _firm(world)
    assert firm.totals.get("household_sales", 0) == 0 and not [k for k in sim.keys if k[1] == 7]
    assert firm.totals.get("sales", 0) > 0 and state.counters["academy_sales"] == firm.totals["sales"]


def test_commons_covering_demand_sells_nothing_to_households():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    world.regions[SITE].stockpile.goods["crafts"] = 50.0
    for _ in range(3):
        _turn(world, sim)
    assert "commons_covers" in _receipt(world).customer_absent
    assert _receipt(world).households["gap_milli"] == 0 and not [k for k in sim.keys if k[1] == 7]


def test_input_price_spike_leaves_the_firm_idle_then_closes_it_and_the_site_for_good():
    world = _world()
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    world.raw = 0.0                      # nothing to convert: no output, no sale
    _turn(world, sim)
    world.prices = {"raw_material": 1e6, "craft": 2.0}        # inputs now unaffordable
    state, payroll = _econ(world), world.livelihoods.workshop_payroll
    runs = []
    for _ in range(E.IDLE_CLOSE_AFTER + 2):
        _turn(world, sim)
        _check_turn(world)
        if state.frame:
            runs.append((_receipt(world).idle_run, _receipt(world).inputs and _receipt(world).inputs["no_input_reason"]))
        if not payroll.firms:
            break
    assert not payroll.firms and payroll.closed[-1].closed_reason == "idle"
    assert state.closed[-1].closed_reason == "idle" and state.counters["closed_idle"] == 1
    assert [r for r, _ in runs][-E.IDLE_CLOSE_AFTER:] == list(range(1, E.IDLE_CLOSE_AFTER + 1))
    assert all(reason == "budget_exhausted" for _, reason in runs[-E.IDLE_CLOSE_AFTER:])
    sites = world.livelihoods.workshops
    assert not sites.sites and sites.closed[-1].closed_reason == "idle"
    closed = payroll.closed[-1]
    assert closed.cash == 0 and closed.inventory == 0
    # No rescue: no new firm or capital ever again at that city.
    capital = state.counters["capital_paid"]
    for _ in range(3):
        _turn(world, sim)
    assert state.counters["capital_paid"] == capital and not payroll.firms


@pytest.mark.parametrize("mode, reason", [("free_inputs", "insolvent"), ("market", "idle")])
def test_no_customers_close_the_firm_insolvent_or_idle(mode, reason):
    """No customer at all (payroll ``no_customer``). Under ``free_inputs`` the
    full crew is employed whatever the cash: wages run into arrears and the
    firm closes insolvent. Under ``market`` the firm reserves this turn's wages
    before it buys inputs, so its crew shrinks with its cash and it closes idle
    once it can buy nothing."""
    world = _world(mode=mode, payroll="no_customer", treasury=(400, 1000))
    world.prices = {"raw_material": 3.0, "craft": 2.0}
    sim = FakeSim(crew=tuple(range(10, 18)))
    _build(world, sim)
    state, payroll = _econ(world), world.livelihoods.workshop_payroll
    assert payroll.firms
    insolvent = []
    for _ in range(40):
        _turn(world, sim)
        _check_turn(world)
        if payroll.frame:
            insolvent.append(payroll.frame[0].insolvent)
            assert "no_customer_mode" in _receipt(world).customer_absent
        if not payroll.firms:
            break
    assert not payroll.firms and payroll.closed[-1].closed_reason == reason
    assert state.counters[f"closed_{reason}"] == 1
    if reason == "insolvent":
        assert any(insolvent) and payroll.counters["owed_written_off"] > 0
    else:
        assert not any(insolvent) and payroll.counters.get("owed_written_off", 0) == 0


def test_depopulation_collapses_household_demand_and_is_recorded():
    world = _world()
    many = tuple(range(100, 160))
    sim = FakeSim(adults=many, children=(), wealth=5.0)
    _build(world, sim)
    for _ in range(E.DEPOPULATION_WINDOW + 1):
        _turn(world, sim)
    before = _receipt(world).households
    assert before["residents"] == 62 and before["demand_milli"] == 620
    # An epidemic: 40 residents die.
    sim.dead |= set(many[:40])
    for _ in range(3):
        _turn(world, sim)
    after = _receipt(world).households
    assert after["residents"] == 22 and after["demand_milli"] == 220
    assert after["depopulated"] is True
    if not after["bought_milli"]:
        assert "depopulated" in _receipt(world).customer_absent


def test_conquest_moves_the_input_payee_and_city_fall_liquidates_once():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    _turn(world, sim)
    world.regions[SITE].controller = "Civ1"
    _turn(world, sim)
    r = _receipt(world)
    assert r.owner == 1
    if r.operating and r.inputs["charged_milli"]:
        assert r.inputs["payee"] == ["civ_treasury", 1]
    fallen = world.cities.cities.pop()
    world.cities.fallen.append(fallen)
    _turn(world, sim)
    payroll, state = world.livelihoods.workshop_payroll, _econ(world)
    assert not payroll.firms and payroll.closed[-1].closed_reason == "city_fell"
    assert state.closed[-1].closed_reason == "city_fell" and state.counters["closed_other"] == 1
    P.check_firm(payroll.closed[-1])


def test_exact_round_trip_mid_arrears_continues_identically():
    world = _world(payroll="paid")
    sim = FakeSim()
    _build(world, sim)
    for _ in range(3):
        _turn(world, sim)
    firm = _firm(world)
    firm.owed.append(P.OwedWage(agent_id=10, amount=40, since_turn=world.turn - 1))   # constructed arrears
    firm.cash += 40
    firm.totals["sales"] = firm.totals.get("sales", 0) + 40
    restored = _world()
    restored.turn = world.turn
    restored.civilizations[0].treasury = world.civilizations[0].treasury
    restored.livelihoods = pickle.loads(pickle.dumps(world.livelihoods))
    restored.regions[SITE].stockpile.goods["crafts"] = world.regions[SITE].stockpile.goods["crafts"]
    econ = _econ(world)
    assert type(econ).model_validate_json(econ.model_dump_json()).model_dump() == econ.model_dump()
    twin = pickle.loads(pickle.dumps(sim))
    for _ in range(5):
        _turn(world, sim)
        _turn(restored, twin)
    assert restored.livelihoods.model_dump() == world.livelihoods.model_dump()
    assert twin.wealth == sim.wealth and twin.keys == sim.keys
    assert restored.civilizations[0].treasury == world.civilizations[0].treasury
    assert len(sim.keys) == len(set(sim.keys))


def test_feature_off_and_disabled_state_leave_payroll_unchanged():
    on = _world(mode=None)
    sim = FakeSim()
    sim._regions = 4
    W.prepare_phase2(on, _batch(), SimpleNamespace(_sim=sim), None, None)
    assert sim.requests[-1] == [(0, SITE, 1, W._diverted(2), W.MAX_CREW)]
    assert not P._economics(on)
    W.rollback_phase2(on)
    on.livelihoods.workshop_economics = WorkshopEconomicsState(enabled=False)
    W.prepare_phase2(on, _batch(), SimpleNamespace(_sim=sim), None, None)
    assert sim.requests[-1] == [(0, SITE, 1, W._diverted(2), W.MAX_CREW)]
    assert P.crew_terms(on, 0) == (8, 1.0)


def test_snapshot_is_dated_and_unknown_when_stale():
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    _turn(world, sim)
    summary = E.snapshot_summary(world)
    assert summary["stage"] == "A3" and summary["source_turn"] == world.turn - 1 and summary["mode"] == "market"
    assert summary["receipts"] and summary["units"]["milli"] == 1000
    assert summary["parameters"]["capital_milli"] == E.CAPITAL
    world.turn += 1
    stale = E.snapshot_summary(world)
    assert stale["receipts"] is None and stale["flows"] is None


def test_prerequisites_modes_and_resume_refusals():
    from chronicler.livelihoods import configure_livelihoods, livelihoods_resume_conflicts
    from chronicler.main import _build_parser
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=6, num_civs=2)
    world.cities = CityState()
    parse = _build_parser().parse_args
    with pytest.raises(ValueError, match="requires --workshop-payroll"):
        configure_livelihoods(world, parse(["--workshops", "--workshop-economics"]), agent_mode="hybrid")
    with pytest.raises(ValueError, match="requires --agents hybrid"):
        configure_livelihoods(world, parse(["--workshops", "--workshop-payroll", "--workshop-economics"]),
                              agent_mode="off")
    assert world.livelihoods is None
    args = parse(["--workshops", "--workshop-payroll", "--workshop-economics",
                  "--workshop-economics-mode", "free_inputs"])
    configure_livelihoods(world, args, agent_mode="hybrid")
    assert world.livelihoods.workshop_economics.mode == "free_inputs"
    assert E.workshop_economics_active(world)
    # Saved on: ending payroll without ending A3 is refused with a hint.
    with pytest.raises(ValueError, match="pass --no-workshop-economics"):
        configure_livelihoods(world, parse(["--no-workshop-payroll"]), agent_mode="hybrid")
    # An exact resume refuses dropping it or changing its mode.
    assert livelihoods_resume_conflicts(world, parse(["--no-workshop-economics"]), {})
    assert livelihoods_resume_conflicts(world, parse(["--workshop-economics-mode", "market"]), {})
    assert not livelihoods_resume_conflicts(world, parse(["--workshop-economics"]), {})
    configure_livelihoods(world, parse(["--no-workshop-economics"]), agent_mode="hybrid")
    assert not E.workshop_economics_active(world) and world.livelihoods.workshop_economics.log[-1].kind == "switched_off"


def test_an_owner_who_stops_funding_the_asset_leaves_the_firm_idle_until_it_closes():
    # Construction 60, capital 11, then upkeep 3 a turn until the treasury runs dry.
    world = _world(treasury=(60 + 20 + 9, 1000))
    world.prices = {"raw_material": 0.001, "craft": 1e6}      # inputs nearly free; wares priced out
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    payroll, state = world.livelihoods.workshop_payroll, _econ(world)
    assert payroll.firms
    reasons = []
    for _ in range(20):
        _turn(world, sim)
        _check_turn(world)
        if state.frame and state.frame[0].inputs:
            reasons.append(state.frame[0].inputs["no_input_reason"])
        if not payroll.firms:
            break
    assert payroll.closed[-1].closed_reason == "idle" and "not_funded" in reasons
    assert reasons[-E.IDLE_CLOSE_AFTER:] == ["not_funded"] * E.IDLE_CLOSE_AFTER
    # Liquidation returned the firm's cash to the owner: nothing was kept or created.
    closed = payroll.closed[-1]
    assert closed.cash == 0 and closed.totals["distributed"] + closed.totals.get("written_off", 0) > 0


def test_a_tick_price_above_the_reservation_buys_only_the_paid_share_of_the_output():
    """The plan uses the last positive raw price; the tick's own price settles.
    When the tick prices the inputs above what the firm reserved, it pays the
    whole reservation and titles only that share of the output; the rest of the
    conversion stays in the commons it was made from (no free input)."""
    world = _world()
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    _turn(world, sim)                                  # plan price 0.5 observed
    world.prices = {"raw_material": 40.0, "craft": 2.0}     # the tick prices raw at 40 a load
    firm = _firm(world)
    cash = firm.cash
    stock = world.regions[SITE].stockpile.goods["crafts"]
    _turn(world, sim)
    _check_turn(world)
    r = _receipt(world)
    inputs = r.inputs
    assert r.operating and inputs["plan_price_milli"] == 500 and inputs["price_milli"] == 40_000
    assert inputs["cost_milli"] > inputs["budget_milli"] == inputs["charged_milli"] > 0
    cap = (r.produced * inputs["budget_milli"]) // inputs["cost_milli"]
    assert inputs["title_cap_milli"] == cap and r.titled <= cap
    assert inputs["unpaid_conversion_milli"] == r.produced - cap > 0
    # The unpaid share stayed in the commons (the people drew their demand first).
    residents = _residents(sim)
    assert world.regions[SITE].stockpile.goods["crafts"] == pytest.approx(
        max(0.0, stock + world.last_output - 0.01 * residents) - r.titled / 1000)
    assert firm.cash == cash - inputs["charged_milli"] - r.wages_paid - r.distributed + r.academy_sales \
        + (r.households or {}).get("paid_milli", 0)


def test_price_discovery_plans_the_full_ceiling_when_no_positive_price_was_seen():
    world = _world()
    world.prices = {"raw_material": 0.0, "craft": 2.0}      # no raw demand anywhere yet: price 0
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    assert _econ(world).firms                          # capital needs no price
    world.prices = {"raw_material": 0.5, "craft": 2.0}      # the firm's own demand prices raw
    _turn(world, sim)
    _check_turn(world)
    r = _receipt(world)
    assert r.operating and r.inputs["price_discovery"] and r.inputs["plan_price_milli"] is None
    assert world.last_ceiling == pytest.approx(W.K_RAW_PER_WORK * 2 * 0.3, rel=1e-6)
    assert r.inputs["charged_milli"] == math.ceil(world.last_output * 500 - 1e-9)
    # The next plan uses the price just computed.
    assert _econ(world).prices[0].plan_raw_milli == 500
    world.prices = {"raw_material": 0.0, "craft": 2.0}      # a turn without raw use keeps the last positive price
    world.raw = 0.0
    _turn(world, sim)
    assert _econ(world).prices[0].plan_raw_milli == 500 and _econ(world).prices[0].raw_milli is None


def test_the_wealth_ledger_records_the_new_channels_and_its_identity_holds():
    from chronicler.wealth_accounting_state import WealthAccountingState
    world = _world()
    for civ in world.civilizations:
        civ.regions = []
    sim = FakeSim(adults=tuple(range(30, 50)), children=((70, 30), (71, 31)), wealth=2.0)
    _build(world, sim)
    world.livelihoods.wealth_accounting = WealthAccountingState()
    frames = []
    for _ in range(8):
        _turn(world, sim)
        frame = world.livelihoods.wealth_accounting.frame
        if frame is None:
            continue
        frames.append(frame)
        assert all(c["closes"] for c in frame["closures"]), frame["closures"]
        typed = {r["channel"]: r for r in frame["typed"]}
        econ = _econ(world)
        h = econ.frame[0].households or {}
        # Households' purchases leave the household sector and are located in the firm's region.
        assert typed["wares_purchase"]["out_milli"] == h.get("paid_milli", 0)
        assert typed["wares_purchase"]["unlocated_out_milli"] == 0
        firm = frame["treasury"]["firm_economics"]
        assert firm["inputs_to_treasury_milli"] == econ.frame[0].inputs["charged_milli"]
        assert firm["asset_subsidy_firm_units"] == W.UPKEEP
        # The identity: close - open = typed net / 1000 + the native model; the stand-in's only
        # model flow is the crew's ordinary income net of the withheld share (0.3 x 0.7 each).
        w = frame["world"]
        assert w["close"] - w["open"] == pytest.approx(w["typed_net_milli"] / 1000 + w["native_model"], abs=1e-6)
        crew = econ.frame[0].inputs["crew"] if econ.frame[0].operating else 0
        assert w["native_model"] == pytest.approx(crew * 0.3 * 0.7, abs=1e-4)
        assert frame["continuity"]["status"] in ("exact", "unchecked")
    assert any(f["typed"] and any(r["channel"] == "wares_purchase" and r["out_milli"] for r in f["typed"])
               for f in frames)
    life = world.livelihoods.wealth_accounting.lifetime
    assert life["wares_purchase_out_milli"] == sum(
        r["out_milli"] for f in frames for r in f["typed"] if r["channel"] == "wares_purchase")
    assert life["firm_inputs_to_treasury_milli"] > 0 and life["asset_subsidy_units"] >= 8 * W.UPKEEP
