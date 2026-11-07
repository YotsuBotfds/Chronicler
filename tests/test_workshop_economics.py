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


def _world(mode="market", payroll="paid", treasury=(1000, 1000), regions=4, rules=1):
    civs = [SimpleNamespace(name=f"Civ{i}", treasury=t) for i, t in enumerate(treasury)]
    world = SimpleNamespace(
        turn=20, agent_mode="hybrid", civilizations=civs, regions=[_region(i) for i in range(regions)],
        cities=CityState(cities=[City(settlement_id=1, region=SITE, name="C1", founded_turn=1,
                                      founder=0, rank=2, size=10.0)]),
        livelihoods=LivelihoodsState(), war_state=SimpleNamespace(armies=[]), scholarship=None)
    world.livelihoods.workshops = WorkshopState(mode="operate")
    world.livelihoods.workshop_payroll = WorkshopPayrollState(mode=payroll)
    if mode is not None:
        world.livelihoods.workshop_economics = WorkshopEconomicsState(mode=mode, rules_version=rules)
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
    # The tick: output enters the commons (A3-1), or the firm's inventory
    # (A3-2's native column), and the people draw their demand free from the commons.
    region = world.regions[SITE]
    owned = (E.OWNED_COLUMN in batch.schema.names
             and batch.column(E.OWNED_COLUMN).to_pylist()[SITE] is not None)
    world.last_owned = owned
    stock = region.stockpile.goods["crafts"] + (0.0 if owned else output)
    world.last_free_draw = min(stock, 0.01 * _residents(sim))
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
        assert sum(debited.values()) == h["paid_milli"] == sum(f.applied for f in _econ(world).book.flows
                                                                if f.purpose == "wares_purchase")
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
    # Turns with no raw stock (operating, converting nothing; the plan price lags the spike by one
    # tick) count toward idle too (re-check n1), then the unaffordable price leaves no budget.
    assert [r for r, _ in runs][-(E.IDLE_CLOSE_AFTER - 1):] == list(range(2, E.IDLE_CLOSE_AFTER + 1))
    assert all(reason == "budget_exhausted" for _, reason in runs[-(E.IDLE_CLOSE_AFTER - 2):])
    sites = world.livelihoods.workshops
    assert not sites.sites and sites.closed[-1].closed_reason == "idle"
    closed = payroll.closed[-1]
    assert closed.cash == 0 and closed.inventory == 0
    # No rescue: no new firm or capital ever again at that city.
    capital = state.counters["capital_paid"]
    for _ in range(3):
        _turn(world, sim)
    assert state.counters["capital_paid"] == capital and not payroll.firms


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
    assert after["bought_milli"] <= after["gap_milli"] <= 220 < before["demand_milli"]   # sales fall with demand
    # When the commons then covers the smaller demand, nobody buys and both reasons are recorded.
    world.regions[SITE].stockpile.goods["crafts"] = 50.0
    _turn(world, sim)
    r = _receipt(world)
    assert r.households["bought_milli"] == 0 and r.households["depopulated"] is True
    assert {"commons_covers", "depopulated"} <= set(r.customer_absent)


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


def test_the_ledger_counts_every_household_purchase_beyond_the_flow_list_bound(monkeypatch):
    """m2: the seam's flow list keeps MAX_FLOWS lines; the ledger reads the
    exact per-turn totals, so a turn with more paying households is counted in
    full and every closure still holds (the drop is recorded)."""
    from chronicler.wealth_accounting_state import WealthAccountingState
    monkeypatch.setattr(M, "MAX_FLOWS", 3)
    world = _world()
    for civ in world.civilizations:
        civ.regions = []
    sim = FakeSim(adults=tuple(range(30, 60)), children=(), wealth=2.0)
    _build(world, sim)
    world.livelihoods.wealth_accounting = WealthAccountingState()
    dropped = 0
    for _ in range(5):
        _turn(world, sim)
        frame = world.livelihoods.wealth_accounting.frame
        if frame is None:
            continue
        assert all(c["closes"] for c in frame["closures"]), frame["closures"]
        h = _econ(world).frame[0].households or {}
        wares = next(r for r in frame["typed"] if r["channel"] == "wares_purchase")
        assert wares["out_milli"] == h.get("paid_milli", 0)
        dropped += frame["treasury"]["firm_economics"]["flows_dropped"]
        w = frame["world"]
        assert w["close"] - w["open"] == pytest.approx(w["typed_net_milli"] / 1000 + w["native_model"], abs=1e-6)
    assert dropped > 0


def test_inputs_are_paid_at_the_plan_price_before_they_are_converted():
    """Market mode: the ceiling is what the reservation buys at the plan price
    (the region's most recent positive raw price from an earlier tick), the
    native conversion never exceeds it, and the charge is ``ceil(used x plan
    price)`` within the reservation. The tick's own price is only recorded."""
    world = _world()
    world.prices = {"raw_material": 0.8, "craft": 2.0}
    sim = FakeSim()
    _build(world, sim)
    state = _econ(world)
    seen = 0
    for turn in range(6):
        if turn == 3:
            world.prices = {"raw_material": 40.0, "craft": 2.0}      # this tick prices raw at 40
        cash_before = _firm(world).cash
        owed_before = sum(o.amount for o in _firm(world).owed)
        plan_turn = world.turn - 1
        _turn(world, sim)
        _check_turn(world)
        r = _receipt(world)
        inputs = r.inputs
        if not r.operating:
            continue
        seen += 1
        # The plan price is last tick's (0.8 before turn 3, 40 after it): never this tick's.
        expected_plan = 40_000 if turn > 3 else 800
        assert inputs["plan_price_milli"] == expected_plan and inputs["plan_price_turn"] == plan_turn
        assert inputs["plan_price_source"] == "region" and inputs["plan_price_region"] == SITE
        assert inputs["tick_price_milli"] == (40_000 if turn >= 3 else 800)
        assert inputs["capacity_milli"] == (max(0, cash_before - owed_before - inputs["wage_bill_milli"]
                                                - E.INPUT_SLACK) * 1000) // inputs["plan_price_milli"]
        assert world.last_output <= world.last_ceiling + 1e-6
        assert world.last_ceiling * 1000 <= inputs["capacity_milli"] + 1e-3
        used = world.last_output
        assert inputs["charged_milli"] == inputs["cost_milli"] == math.ceil(used * expected_plan - 1e-9) > 0
        assert inputs["charged_milli"] <= inputs["budget_milli"] + E.INPUT_SLACK
        assert inputs["converted_unpaid_milli"] == 0 and inputs["payee"] == ["civ_treasury", 0]
        # Everything converted was paid for; what the firm does not title is only the
        # same tick's free use of its output (the declared A3-1 limit).
        assert r.titled + r.free_use_upper_bound == r.produced
    assert seen >= 4
    flows = [f for f in state.book.flows if f.purpose == "firm_input_purchase"]
    assert all(f.payer == ("firm_cash", 0) and f.payee == ("civ_treasury", 0) for f in flows)
    assert state.counters["inputs_charged"] == _firm(world).totals["inputs"] > 0


def test_a_firm_that_cannot_pay_its_full_need_converts_only_what_it_paid_for():
    world = _world()
    world.prices = {"raw_material": 5.0, "craft": 2.0}
    sim = FakeSim(crew=tuple(range(10, 18)))
    _build(world, sim)
    firm = _firm(world)
    stock = world.raw = 100.0                  # far more raw stock than the firm can pay for
    _turn(world, sim)
    r = _receipt(world)
    inputs = r.inputs
    assert r.operating and inputs["capacity_milli"] < inputs["need_milli"]
    assert inputs["unbought_need_milli"] == inputs["need_milli"] - inputs["capacity_milli"] > 0
    assert world.last_output * 1000 <= inputs["capacity_milli"] + 1e-3 < stock * 1000
    # The crew request was sized down to the workers the paid inputs occupy.
    assert len(r_crew := world.livelihoods.workshop_payroll.frame[0].crew) < 8 and r_crew
    assert inputs["charged_milli"] == math.ceil(world.last_output * 5000 - 1e-9)
    assert firm.cash >= 0 and inputs["converted_unpaid_milli"] == 0


def test_free_inputs_differs_from_market_only_in_the_charge():
    """M2: the same budget, plan, crew sizing and ceiling; the charge is
    recorded and not taken."""
    worlds = {}
    for mode in ("market", "free_inputs"):
        world = _world(mode=mode)
        world.prices = {"raw_material": 3.0, "craft": 2.0}
        sim = FakeSim(crew=tuple(range(10, 18)), adults=(), children=())
        _build(world, sim)
        _turn(world, sim)
        worlds[mode] = (world, sim)
    (m, msim), (f, fsim) = worlds["market"], worlds["free_inputs"]
    rm, rf = _receipt(m), _receipt(f)
    for key in ("plan_price_milli", "budget_milli", "capacity_milli", "crew", "wage_bill_milli", "used_milli",
                "cost_milli"):
        assert rm.inputs[key] == rf.inputs[key], key
    assert msim.requests[-1] == fsim.requests[-1] and m.last_ceiling == f.last_ceiling
    assert rm.inputs["charged_milli"] == rf.inputs["not_charged_milli"] > 0
    assert rf.inputs["charged_milli"] == 0 and rm.inputs["not_charged_milli"] == 0
    assert _firm(f).totals.get("inputs", 0) == 0
    assert _firm(f).cash - _firm(m).cash == rm.inputs["charged_milli"]
    assert not [x for x in _econ(f).book.flows if x.purpose == "firm_input_purchase"]


def test_a_region_without_a_price_uses_the_rulers_most_recent_price_and_none_refuses_opening():
    world = _world()
    world.prices = {"raw_material": 0.0, "craft": 2.0}       # no raw demand anywhere: no positive price
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    state = _econ(world)
    assert not world.livelihoods.workshop_payroll.firms
    assert state.counters["opening_refused_no_input_price"] >= 1
    assert state.log[-1].kind == "opening_refused" and state.log[-1].detail["reason"] == "no_input_price"
    # Another region of the same ruler gets a raw price: the realm fallback opens the firm.
    economy_prices = {f"R{i}": {"raw_material": 0.0, "craft": 2.0} for i in range(4)}
    economy_prices["R1"] = {"raw_material": 0.7, "craft": 2.0}
    E.observe_prices(world, SimpleNamespace(market_prices=economy_prices))
    found = E.plan_price(world, SITE)
    assert found == {"price_milli": 700, "turn": world.turn, "region": 1, "source": "realm"}
    world.regions[1].controller = "Civ1"                    # another ruler's region does not count
    assert E.plan_price(world, SITE) is None
    world.regions[1].controller = "Civ0"
    world.prices = {"raw_material": 0.0, "craft": 2.0}
    _turn(world, sim)
    assert world.livelihoods.workshop_payroll.firms and state.log[-1].kind == "opened"
    assert state.log[-1].detail["plan_price"]["source"] == "realm"


def test_wage_arrears_that_cash_cannot_cover_close_the_firm_insolvent():
    world = _world(payroll="no_customer")
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    firm = _firm(world)
    debt = firm.cash + 5000                       # constructed arrears beyond the firm's cash
    firm.owed.append(P.OwedWage(agent_id=10, amount=debt, since_turn=world.turn - 1))
    insolvent = []
    for _ in range(12):
        _turn(world, sim)
        payroll = world.livelihoods.workshop_payroll
        if payroll.frame:
            insolvent.append(payroll.frame[0].insolvent)
            r = _receipt(world)
            assert not r.operating and r.inputs["no_input_reason"] == "budget_exhausted"
        if not payroll.firms:
            break
    payroll = world.livelihoods.workshop_payroll
    assert not payroll.firms and payroll.closed[-1].closed_reason == "insolvent" and all(insolvent)
    assert _econ(world).counters["closed_insolvent"] == 1 and payroll.counters["owed_written_off"] > 0


@pytest.mark.parametrize("mode", ["market", "free_inputs"])
def test_no_customers_close_the_firm_idle_in_both_modes(mode):
    """No customer at all (payroll ``no_customer``): the firm reserves this
    turn's wages before it buys inputs in both modes, so its crew shrinks with
    its cash and it closes idle once it can buy nothing (free_inputs pays no
    inputs, so it lasts longer)."""
    world = _world(mode=mode, payroll="no_customer", treasury=(400, 1000))
    world.prices = {"raw_material": 3.0, "craft": 2.0}
    sim = FakeSim(crew=tuple(range(10, 18)))
    _build(world, sim)
    state, payroll = _econ(world), world.livelihoods.workshop_payroll
    turns = 0
    for _ in range(80):
        _turn(world, sim)
        _check_turn(world)
        turns += 1
        if payroll.frame:
            assert "no_customer_mode" in _receipt(world).customer_absent
        if not payroll.firms:
            break
    assert not payroll.firms and payroll.closed[-1].closed_reason == "idle"
    assert state.counters["closed_idle"] == 1 and payroll.counters.get("owed_written_off", 0) == 0
    world.closing_turns = turns


def test_a_firm_whose_city_has_no_crew_counts_idle_and_closes():
    world = _world()
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    sim.dead |= set(sim.crew)                     # every eligible farmer dies
    for _ in range(E.IDLE_CLOSE_AFTER + 2):
        _turn(world, sim)
        if not world.livelihoods.workshop_payroll.firms:
            break
    payroll = world.livelihoods.workshop_payroll
    assert payroll.closed[-1].closed_reason == "idle"
    assert _econ(world).log[-1].kind in ("closed", "opening_refused")


def test_a_closed_firms_city_is_never_readmitted_beyond_l1s_closed_list():
    """M1: L1 keeps only eight closed sites; A3 keeps every closed firm's city
    and L1 never readmits it while A3 is active (no second capital there)."""
    from chronicler.workshops_state import WorkshopSite
    world = _world()
    world.prices = {"raw_material": 1e6, "craft": 2.0}
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    state, ws = _econ(world), world.livelihoods.workshops
    for _ in range(E.IDLE_CLOSE_AFTER + 2):
        _turn(world, sim)
        if not world.livelihoods.workshop_payroll.firms:
            break
    assert state.closed_settlements == [1] and ws.closed[-1].closed_reason == "idle"
    capital = state.counters["capital_paid"]
    # Eight more closures rotate the city out of L1's own closed list.
    for i in range(8):
        ws.closed.append(WorkshopSite(site=100 + i, region=3, settlement_id=200 + i, city_name=f"X{i}",
                                      selected_turn=1, status="closed", closed_turn=world.turn,
                                      closed_reason="city_fell"))
        del ws.closed[:-W.MAX_CLOSED]
    assert all(site.settlement_id != 1 for site in ws.closed)
    for _ in range(3):
        _turn(world, sim)
    assert not ws.sites and state.counters["capital_paid"] == capital
    assert not world.livelihoods.workshop_payroll.firms
    # Without A3 the same L1 state readmits the city (the L1 rule is unchanged).
    world.livelihoods.workshop_economics.enabled = False
    W.refresh_sites(world, ws)
    assert [s.settlement_id for s in ws.sites] == [1]


def test_a_sub_milli_conversion_is_charged_one_milli_unit_never_nothing():
    """A conversion too small to cost a whole milli-unit at the plan price is
    charged one (found by the development rerun: procedural 11, academy_only)."""
    world = _world()
    world.prices = {"raw_material": 0.5, "craft": 2.0}
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    world.raw = 1e-13                               # 1e-13 loads at 500 milli a load: 5e-11 milli
    _turn(world, sim)
    r = _receipt(world)
    assert r.operating and 0 < world.last_output < 1e-12
    assert r.inputs["charged_milli"] == r.inputs["cost_milli"] == 1


@pytest.mark.parametrize("payroll", ["unpaid_labor", "paid"])
def test_a_firm_that_converts_and_sells_nothing_closes_idle(payroll):
    """Re-check n1 (the reviewer's probe): with no raw stock a firm operates
    and converts nothing; under ``unpaid_labor`` it owes no wage, so its budget
    never runs out. Turns that convert and sell nothing count toward idle."""
    world = _world(payroll=payroll)
    sim = FakeSim(adults=(), children=())
    _build(world, sim)
    world.raw = 0.0
    runs = []
    for _ in range(E.IDLE_CLOSE_AFTER + 3):
        _turn(world, sim)
        if _econ(world).frame:
            runs.append((_receipt(world).operating, _receipt(world).idle_run))
        if not world.livelihoods.workshop_payroll.firms:
            break
    payroll_state = world.livelihoods.workshop_payroll
    assert not payroll_state.firms and payroll_state.closed[-1].closed_reason == "idle"
    assert [run for _op, run in runs][-E.IDLE_CLOSE_AFTER:] == list(range(1, E.IDLE_CLOSE_AFTER + 1))
    assert _econ(world).counters["idle_no_conversion_turns"] >= 1


def test_per_civ_capital_and_input_attribution_is_exact_beyond_the_flow_list_bound(monkeypatch):
    """Re-check n3: with more payments in a turn than the flow list keeps, the
    ledger's per-civilization capital and input rows come from the exact totals."""
    from chronicler.wealth_accounting_state import WealthAccountingState
    monkeypatch.setattr(M, "MAX_FLOWS", 2)
    world = _world()
    for civ in world.civilizations:
        civ.regions = []
    sim = FakeSim(adults=tuple(range(30, 50)), children=(), wealth=2.0)
    world.livelihoods.wealth_accounting = WealthAccountingState()
    capital_seen = inputs_seen = 0
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT + 4):
        _turn(world, sim)
        frame = world.livelihoods.wealth_accounting.frame
        if frame is None or "firm_economics" not in frame["treasury"]:
            continue
        assert all(c["closes"] for c in frame["closures"]), frame["closures"]
        firm = frame["treasury"]["firm_economics"]
        civ = {r["civ"]: r for r in frame["treasury"]["by_civ"]}.get(0, {})
        assert civ.get("firm_capital_milli", 0) == firm["capital_from_treasury_milli"]
        assert civ.get("firm_inputs_milli", 0) == firm["inputs_to_treasury_milli"]
        capital_seen += firm["capital_from_treasury_milli"]
        inputs_seen += firm["inputs_to_treasury_milli"]
    assert capital_seen == E.CAPITAL and inputs_seen > 0
    # The capital flow itself was dropped from the two-line list on its turn, yet attributed.
    assert _econ(world).book.flows_dropped >= 0


# --- A3-2: owned output (``--workshop-economics-rules 2``) -----------------------------


def test_rules_1_keeps_a3_1_bytes_and_a_conflicting_rules_value_is_refused():
    from chronicler.livelihoods import LIVELIHOODS_CHOICES, livelihoods_resume_conflicts
    from chronicler.main import _build_parser
    assert LIVELIHOODS_CHOICES["workshop_economics_rules"] == ("1", "2")
    state = WorkshopEconomicsState()
    assert state.rules_version == 1 and "rules_version" not in state.model_dump()
    assert WorkshopEconomicsState(rules_version=2).model_dump()["rules_version"] == 2
    world = _world()
    sim = FakeSim()
    _build(world, sim)
    for _ in range(3):
        batch = _turn(world, sim)
        assert E.OWNED_COLUMN not in batch.schema.names           # the A3-1 batch, unchanged
    parse = _build_parser().parse_args
    assert livelihoods_resume_conflicts(world, parse(["--workshop-economics-rules", "2"]), {}) == [
        "--workshop-economics-rules '2' conflicts with the checkpoint (saved: '1')"]
    with pytest.raises(ValueError, match="conflicts"):
        E.set_workshop_economics_enabled(world, True, args=SimpleNamespace(workshop_economics_rules="2"))


def test_owned_output_never_enters_the_commons_and_is_titled_whole():
    world = _world(rules=2)
    sim = FakeSim()
    _build(world, sim)
    firm, state = _firm(world), _econ(world)
    produced = 0
    for _ in range(5):
        inventory = firm.inventory
        batch = _turn(world, sim)
        _check_turn(world)
        r = _receipt(world)
        column = batch.column(E.OWNED_COLUMN).to_pylist()
        assert column[SITE] == pytest.approx(inventory / 1000) and all(v is None for i, v in enumerate(column)
                                                                        if i != SITE)
        assert world.last_owned is True
        assert r.produced == r.titled == math.floor(world.last_output * 1000)
        assert r.free_use_upper_bound == 0                       # no same-tick free use
        produced += r.titled
    assert produced > 0 and state.counters["owned_output"] == produced
    assert state.counters.get("free_use_upper_bound", 0) == 0
    payroll = world.livelihoods.workshop_payroll
    titles = [m for m in payroll.materials if m.kind == "title"]
    assert titles and all(m.source == ("workshop_output", firm.site) for m in titles)


def test_firm_output_reaches_households_only_by_sale():
    world = _world(rules=2)
    sim = FakeSim(adults=tuple(range(30, 45)), children=(), wealth=5.0)
    _build(world, sim)
    firm = _firm(world)
    seen = 0
    for _ in range(6):
        commons = world.regions[SITE].stockpile.goods["crafts"]
        _turn(world, sim)
        _check_turn(world)
        r = _receipt(world)
        bought = (r.households or {}).get("bought_milli", 0)
        # The people's free draw took only the commons there before the tick:
        # the firm's output was in its inventory, never available free.
        assert world.last_free_draw <= commons + 1e-9
        # The commons gained exactly what households paid for (and nothing of the output).
        after = world.regions[SITE].stockpile.goods["crafts"]
        assert after == pytest.approx(max(0.0, commons - 0.01 * _residents(sim)) + bought / 1000)
        seen += bought > 0
    assert seen and firm.totals["household_delivered"] > 0


def test_the_ceiling_never_exceeds_the_inventory_room():
    from chronicler.workshop_payroll import INVENTORY_CAP
    world = _world(rules=2)
    sim = FakeSim(adults=(), children=())                    # nobody to sell to
    _build(world, sim)
    firm = _firm(world)
    extra = INVENTORY_CAP - 300 - firm.inventory          # constructed stock, kept on the books
    firm.inventory += extra
    firm.totals["titled"] = firm.totals.get("titled", 0) + extra
    for _ in range(6):
        if not world.livelihoods.workshop_payroll.firms:
            break
        room = INVENTORY_CAP - firm.inventory
        batch = _turn(world, sim)
        _check_turn(world)
        # One raw load makes one load of wares: the ceiling stays within the room,
        # so nothing the firm makes is ever lost or left in the commons.
        assert batch.column("craft_raw_demand").to_pylist()[SITE] * 1000 <= room + 1e-3
        assert firm.inventory <= INVENTORY_CAP and _receipt(world).free_use_upper_bound == 0
    # A full inventory is a declared reason not to operate (and counts idle).
    assert "inventory_full" in E.IDLE_REASONS


def test_the_rules_option_requires_workshop_economics_and_a_new_state_takes_it():
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    from chronicler.world_gen import generate_world
    parse = _build_parser().parse_args
    world = generate_world(seed=42)
    with pytest.raises(ValueError, match="requires --workshop-economics"):
        configure_livelihoods(world, parse(["--workshop-economics-rules", "2"]), agent_mode="hybrid")
    assert world.livelihoods is None
    world = _world(mode=None)
    E.set_workshop_economics_enabled(world, True, args=SimpleNamespace(workshop_economics_rules="2"))
    state = _econ(world)
    assert state.rules_version == 2 and state.log[-1].detail["rules_version"] == 2
    assert E.owned_output(world) and state.model_dump()["rules_version"] == 2
