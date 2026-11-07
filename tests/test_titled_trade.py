"""A4 titled trade (``--titled-trade``) without the native extension.

The household-retail stand-in (``tests/test_household_retail.py``: the PL4 FFI
contract with simple Python rules) is extended with the native seams titled
trade uses: the work registry (``reserve_work`` with the ``trade`` category),
the shared paid-work share and its receipt (a merchant's ordinary income of
``MERCHANT_INCOME`` a turn, withheld whole while it carries), the trip list
and the pairwise ``settle_pairs`` with the native limits. Everything else is
the real livelihoods hooks, household retail, titled trade, the payment seam
and the A1 ledger's Python snapshot/typed-receipt interface. Its two ledger
unit tests explicitly leave A1-2 native stages unavailable; compiled stage and
closure evidence belongs to the native contract/accounting suites.
Template seed 42: Verdant Plains (2) and Thornwood (4) are
Thornwall's and adjacent; Frostholm Tundra (0, Kethani) and Obsidian Shore (7,
Ashkari) are adjacent across a border.
"""
from __future__ import annotations

import copy
import json
import math
import pickle
from fractions import Fraction
from itertools import product
from types import SimpleNamespace as NS

import pytest

from chronicler import household_retail as HR
from chronicler import livelihoods as LV
from chronicler import money as M
from chronicler import titled_trade as TT
from chronicler.household_retail_state import RETAIL_GOODS
from chronicler.livelihoods import configure_livelihoods, livelihoods_snapshot_fields
from chronicler.main import _build_parser
from chronicler.titled_trade_state import COUNTERS, OUTCOMES, Shipment, TitledTradeState
from chronicler.world_gen import generate_world
from tests.test_household_retail import MAX_WEALTH, FakeBridge, FakeSim, Harness

FROST, VERDANT, THORNWOOD, OBSIDIAN = 0, 2, 4, 7
MERCHANT_INCOME = 0.2
MERCHANT = 2


class TradeSim(FakeSim):
    """The retail stand-in plus the work registry, paid work and pairs."""

    def __init__(self):
        super().__init__()
        self.reservations: list[tuple[int, int, int, float]] = []    # (turn, id, category, fraction)
        self.paid = None
        self.paid_receipt = None
        self.on_trip: set[int] = set()
        self.pair_calls: list = []
        self.extend_calls: list = []

    def get_snapshot(self):
        """A real Arrow batch (the A1 ledger reads columns with Arrow)."""
        import pyarrow as pa
        ids = sorted(self.people)
        col = lambda k, t: pa.array([self.people[a][k] for a in ids], t)  # noqa: E731
        return pa.record_batch({
            "id": pa.array(ids, pa.uint32()), "region": col("region", pa.uint16()),
            "origin_region": col("origin_region", pa.uint16()), "occupation": col("occupation", pa.uint8()),
            "age": col("age", pa.uint16()), "settlement_id": col("settlement_id", pa.uint16()),
            "parent_id_0": col("parent_id_0", pa.uint32()), "parent_id_1": col("parent_id_1", pa.uint32()),
            "wealth": col("wealth", pa.float32()), "displacement_turn": col("displacement_turn", pa.uint16())})

    def work_reservation_categories(self):
        return ["workshop", "learning", "apprentice", "repair", "trade"]

    def wealth_transfer_purposes(self):
        return list(M.NATIVE_PURPOSES)

    def trip_agent_ids(self):
        return sorted(a for a in self.on_trip if a in self.people)

    def reserve_work(self, turn, category, rows):
        if category >= 5:
            raise ValueError("unknown work reservation category")
        held = {a for t, a, _c, _f in self.reservations if t == turn}
        for aid, fraction in rows:
            if aid not in self.people:
                raise ValueError("work reservation names no living agent")
            if aid in held:
                raise ValueError("agent already holds work this turn")
        self.reservations = [r for r in self.reservations if r[0] == turn]
        self.reservations.extend((turn, aid, category, f) for aid, f in rows)

    def work_reservations(self, turn):
        return [(a, c, f) for t, a, c, f in self.reservations if t == turn]

    def extend_paid_work(self, turn, rows):
        self.extend_calls.append((turn, list(rows)))
        if self.paid is not None and self.paid[0] != turn:
            raise ValueError("paid work share pending for another turn")
        for aid, share in rows:
            reserved = sum(f for t, a, _c, f in self.reservations if t == turn and a == aid)
            if aid not in self.people or share > reserved + 1e-6:
                raise ValueError("paid work exceeds the agent's work reservation this turn")
        plan = dict(self.paid[1]) if self.paid is not None else {}
        for aid, share in rows:
            if aid in plan:
                raise ValueError("agent already has a paid work share this turn")
            plan[aid] = share
        self.paid = (turn, plan)

    def cancel_paid_work(self):
        had, self.paid = self.paid is not None, None
        return had

    def take_paid_work_receipt(self):
        out, self.paid_receipt = self.paid_receipt, None
        return out

    def settle_pairs(self, turn, purpose, batch, rows):
        self.pair_calls.append((turn, purpose, batch, list(rows)))
        if purpose not in (8, 9):
            raise ValueError("not a pairwise wealth transfer purpose")
        if any(p == purpose and b == batch and t >= turn for t, p, b in self.keys):
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        payers, payees = {r[0] for r in rows}, {r[1] for r in rows}
        if payers & payees or len({(r[0], r[1]) for r in rows}) != len(rows) or any(r[2] <= 0 for r in rows):
            raise ValueError("invalid pairwise rows")
        self.keys.add((turn, purpose, batch))
        left, room, out = {}, {}, []
        for payer, payee, amount in rows:
            if payer not in self.people or payee not in self.people:
                out.append((payer, payee, amount, 0, 0, 0, 2))
                continue
            left.setdefault(payer, math.floor(self.people[payer]["wealth"] * 1000))
            room.setdefault(payee, math.floor((MAX_WEALTH - self.people[payee]["wealth"]) * 1000))
            sent = min(amount, left[payer])
            credited = min(sent, room[payee])
            left[payer] -= credited
            room[payee] -= credited
            self.people[payer]["wealth"] -= credited / 1000
            self.people[payee]["wealth"] += credited / 1000
            out.append((payer, payee, amount, sent, credited, sent - credited,
                        0 if sent == amount and sent == credited else 1))
        return out

    def tick(self, world, **kwargs):
        # The wealth phase: merchants' ordinary income, less any paid share.
        paid, self.paid = self.paid, None
        rows = []
        for aid in sorted(self.people):
            p = self.people[aid]
            share = paid[1].get(aid, 0.0) if paid is not None and paid[0] == world.turn else 0.0
            if p["occupation"] != MERCHANT:
                if share:                                # a paid share on no merchant income
                    rows.append((aid, share, 0.0, 0.0))
                continue
            if share:
                rows.append((aid, share, MERCHANT_INCOME, MERCHANT_INCOME * share))
            p["wealth"] = min(MAX_WEALTH, p["wealth"] + MERCHANT_INCOME * (1.0 - share))
        if paid is not None:
            self.paid_receipt = (world.turn, rows)
        out = super().tick(world, **kwargs)
        self.reservations = []
        return out


class TradeHarness(Harness):
    def __init__(self, *flags, trade=True, boundary="all"):
        extra = ["--household-retail-boundary", boundary, *(["--titled-trade"] if trade else []), *flags]
        super().__init__(*extra)
        self.sim = TradeSim()
        self.bridge = FakeBridge(self.sim)

    @property
    def tt(self) -> TitledTradeState:
        return self.world.livelihoods.titled_trade


def _farmers(h, rid, ids, wealth=5.0):
    for aid in ids:
        h.sim.add(aid, rid, occupation=0, wealth=wealth)


def _merchant(h, aid, rid, wealth=20.0):
    h.sim.add(aid, rid, occupation=MERCHANT, wealth=wealth)


def _market(h, owners=(1, 2, 3), buyers=(51, 52, 53, 54, 55, 56), merchant=90, origin=VERDANT,
            dest=THORNWOOD, merchant_wealth=20.0, buyer_wealth=8.0):
    """Owners farm at the origin, buyers live short of food at the destination."""
    _farmers(h, origin, owners)
    for aid in buyers:
        h.sim.add(aid, dest, occupation=3, wealth=buyer_wealth)
    if merchant is not None:
        _merchant(h, merchant, origin, merchant_wealth)


def _goods_total(h):
    """Every unit of retail food: commons, owned pools and cargo aboard."""
    world = h.world
    commons = sum(round(float(r.stockpile.goods.get(g, 0.0)) * 1000) for r in world.regions for g in RETAIL_GOODS)
    owned = sum(sum(reg.goods) for reg in h.state.regions)
    cargo = sum(s.total() for s in h.tt.shipments) if h.world.livelihoods.titled_trade is not None else 0
    return commons, owned, cargo


def _run_until_dispatch(h, production=None, limit=4):
    production = production or {VERDANT: {"grain": 30.0}}
    for _ in range(limit):
        h.turn(production)
        if h.tt.shipments or h.tt.closed:
            return
    raise AssertionError("no shipment was dispatched")


# --- registry, switch, prerequisites -------------------------------------------------

def test_switch_registry_cli_catalog_and_manifest_keys():
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
    from chronicler.feature_catalog import REQUIREMENTS
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    order = LIVELIHOODS_SWITCHES
    assert order.index("titled_trade") == order.index("workshop_economics") + 1
    # Infrastructure and canopy records close before C2. The late care/guard
    # consumers share the final retail factor after all reservations.
    assert order[order.index("titled_trade") + 1:order.index("epidemic_care")] == ("infrastructure_condition", "harvest_cover")
    # Every acting consumer (including A6's own prior-row observations) runs
    # before the sole X1 writer, then D2 and the closing wealth observer.
    assert order[order.index("epidemic_care") + 1:order.index("residence_ledger")] == (
        "guild_leagues", "war_requisition", "war_consequences", "adaptive_livelihoods", "public_health", "movement_branches")
    assert order.index("residence_ledger") == order.index("attribution_records") - 1
    assert order[-1] == "wealth_accounting"
    assert order.index("household_retail") < order.index("titled_trade")
    assert REQUIREMENTS["titled_trade"] == (
        {"agents": ["hybrid"]}, {"feature": "household_retail"},
        {"choice": "household_retail_mode", "values": ["retail", "no_relief"]},
        {"choice": "household_retail_rules", "values": ["2"]})
    assert "titled_trade" in SIMULATION_ARG_KEYS and "titled_trade" not in LV.LIVELIHOODS_CHOICES
    parse = _build_parser().parse_args
    assert "titled_trade" not in simulation_config(parse([]))
    assert simulation_config(parse(["--titled-trade"]))["titled_trade"] is True
    assert LV.livelihoods_arguments(parse(["--no-titled-trade"])) == ["--no-titled-trade"]
    for fn in ("set_titled_trade_enabled", "titled_trade_active", "snapshot_summary", "reserve_first",
               "finish_phase2", "after_agent_tick", "phase10", "on_pool_reset"):
        assert callable(getattr(TT, fn))
    # No Phase 2 planner or pre-tick hook: purchases and movement run in Phase 10.
    assert not hasattr(TT, "prepare_phase2") and not hasattr(TT, "before_agent_tick")


@pytest.mark.parametrize("argv, agents, match", [
    (["--titled-trade"], "hybrid", "household-retail"),
    (["--food-allocation", "--titled-trade"], "hybrid", "household-retail"),
    (["--food-allocation", "--household-retail", "--household-retail-mode", "free_exchange", "--titled-trade"],
     "hybrid", "retail or no_relief"),
    (["--food-allocation", "--household-retail", "--household-retail-mode", "record_only", "--titled-trade"],
     "hybrid", "retail or no_relief"),
    (["--food-allocation", "--household-retail", "--household-retail-rules", "1", "--titled-trade"],
     "hybrid", "rules version 2"),
    (["--titled-trade"], "shadow", "hybrid"),
])
def test_invalid_combinations_are_refused_before_any_change(argv, agents, match):
    world = generate_world(seed=42)
    with pytest.raises(ValueError, match=match):
        configure_livelihoods(world, _build_parser().parse_args(argv), agent_mode=agents)
    assert world.livelihoods is None


def test_a_saved_world_refuses_a_resume_that_ends_retail_until_the_switch_is_ended():
    h = TradeHarness()
    parse = _build_parser().parse_args
    with pytest.raises(LV.LivelihoodsRefusal, match="no-titled-trade"):
        configure_livelihoods(h.world, parse(["--no-household-retail"]), agent_mode="hybrid")
    with pytest.raises(LV.LivelihoodsRefusal, match="no-titled-trade"):
        configure_livelihoods(h.world, parse(["--household-retail-mode", "record_only", "--household-retail"]),
                              agent_mode="hybrid")
    configure_livelihoods(h.world, parse(["--no-titled-trade", "--no-household-retail"]), agent_mode="hybrid")
    assert h.tt.enabled is False and not TT.titled_trade_active(h.world)
    # An exact resume refuses toggling it (generic seam).
    h2 = TradeHarness()
    assert LV.livelihoods_resume_conflicts(h2.world, parse(["--no-titled-trade"]), {}) == [
        "--titled-trade False conflicts with the checkpoint (saved: True)"]


def test_feature_off_has_no_state_no_flows_and_no_snapshot_key():
    h = TradeHarness(trade=False)
    _market(h)
    for _ in range(3):
        h.turn({VERDANT: {"grain": 30.0}})
    assert h.world.livelihoods.titled_trade is None
    assert "titled_trade" not in json.loads(h.world.model_dump_json())["livelihoods"]
    assert "titled_trade" not in livelihoods_snapshot_fields(h.world)["livelihoods"]
    assert not h.sim.pair_calls and not h.sim.reservations and not h.sim.extend_calls
    for f in h.state.frame:
        assert not set(f.flows) & {"sold_merchant", "consigned_in", "returned_in"}


# --- purchase ---------------------------------------------------------------------

def test_merchants_buy_only_surplus_above_the_reserve_pro_rata_at_the_local_price():
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    d = h.tt.frame["dispatched"][0]
    assert (ship.holder, ship.carrier, ship.origin, ship.dest, ship.path) == (90, 90, VERDANT, THORNWOOD,
                                                                            [VERDANT, THORNWOOD])
    rows = d["seller_rows"]
    taken = {r[0]: r[1] for r in rows}
    reg = h.state.region(VERDANT)
    # Each owner kept at least its reserve; the takes are pro rata to the surplus above it.
    before = {o: reg.claims.get(o, 0) + t for o, t in taken.items()}
    assert all(reg.claims.get(o, 0) >= TT.OWNER_KEEP for o in taken)
    surplus = {o: c - TT.OWNER_KEEP for o, c in before.items() if c > TT.OWNER_KEEP}
    assert taken == HR.largest_remainder(d["milli"], surplus.items())
    assert sum(taken.values()) == d["milli"] == sum(ship.cargo_open)
    # Each owner is paid ceil(milli x local price / ration), by id, at the origin's retail price.
    ration_milli = HR._ration(h.world) * 1000
    assert d["price_milli"] == HR.price_milli(h.world, h.results[-1], VERDANT)
    for _owner, take, requested, applied in rows:
        assert requested == math.ceil(take * d["price_milli"] / ration_milli) == applied
    assert d["paid"] == sum(r[3] for r in rows) == ship.cost_milli
    flows = [f for f in h.tt.book.flows if f.purpose == "cargo_purchase"]
    assert {(f.payer, f.payee, f.applied) for f in flows} == {(("agent_wealth", 90), ("agent_wealth", o), a)
                                                             for o, _t, _r, a in rows}
    assert h.sim.pair_calls[-1][1:3] == (8, ship.id)
    frame_flows = next(f for f in h.state.frame if f.region == VERDANT).flows
    assert frame_flows["sold_merchant"] == d["milli"]


def test_the_quantity_stops_where_the_last_unit_no_longer_earns_the_margin():
    origin = (10.0, 20.0)                               # demand 10, supply 20: price 0.5
    dest = (10.0, 4.0)                                   # price 2.5
    q = TT._plan_quantity(origin, dest, 0.05, 50_000)
    gap = lambda x: TT._price(dest, x / 1000) * 0.95 - TT._price(origin, -x / 1000)  # noqa: E731
    assert gap(q) >= TT.LOAD_MARGIN > gap(q + 1)
    assert TT._plan_quantity(origin, dest, 0.05, 100) == 100          # capped below the margin's end
    assert TT._plan_quantity(origin, (10.0, 20.0), 0.05, 50_000) == 0  # no gap, no trip
    assert TT._plan_quantity(origin, dest, 0.05, TT.MIN_CARGO - 1) == 0


def test_no_surplus_no_cash_or_no_destination_plans_no_trip():
    h = TradeHarness()
    _market(h, merchant_wealth=0.5)                     # cannot keep its reserve
    for _ in range(3):
        h.turn({VERDANT: {"grain": 30.0}})
    assert not h.tt.shipments and not h.tt.closed and h.tt.counters.get("plans_no_cash", 0) > 0
    h2 = TradeHarness()
    _market(h2)
    h2.turn({VERDANT: {"grain": 3.0}})                   # every claim within the owners' reserve
    claims = h2.state.region(VERDANT).claims
    assert claims and max(claims.values()) <= TT.OWNER_KEEP
    assert not h2.tt.shipments and h2.tt.counters.get("plans_no_offer", 0) == 1


# --- title and custody, exactly once -----------------------------------------------

def test_title_and_custody_pass_exactly_once_through_purchase_transit_delivery_and_sale():
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    sid, opened = ship.id, sum(ship.cargo_open)
    # Purchase turn: the cargo left the origin pool and is aboard, in no pool.
    assert ship.total() == opened and ship.cursor == 0
    h.turn({VERDANT: {"grain": 30.0}})                  # moves one edge and arrives (one hop)
    closed = next(s for s in h.tt.closed if s.id == sid)
    assert closed.outcome == "delivered" and closed.status == "closed" and closed.closed_turn == h.world.turn - 1
    decay = closed.losses.get("transit_decay", 0)
    assert decay == sum(math.floor(v * r) for v, r in zip(closed.cargo_open, TT.TRANSIT_DECAY))
    assert closed.delivered == opened - decay and closed.returned == closed.deposited == 0
    assert sum(closed.cargo_open) == decay + closed.delivered
    dest_frame = next(f for f in h.state.frame if f.region == THORNWOOD)
    assert dest_frame.flows["consigned_in"] == closed.delivered
    assert h.state.region(THORNWOOD).claims.get(90, 0) == closed.delivered
    assert h.tt.lots[0].holder == 90 and h.tt.lots[0].milli == closed.delivered
    assert sum(1 for s in h.tt.closed if s.id == sid) == 1 and h.tt.shipment(sid) is None
    # The next tick sells the holder's claim to the destination's buyers, paid to the holder by id.
    wealth = h.sim.people[90]["wealth"]
    h.turn({VERDANT: {"grain": 30.0}})
    sales = h.tt.frame["sales"]
    assert sales and sales[0]["holder"] == 90 and sales[0]["region"] == THORNWOOD and sales[0]["cargo_sold"] > 0
    assert sales[0]["exact"] is True and sales[0]["credited"] > 0
    assert h.tt.counters["cargo_sales_credited_milli"] == sum(s["credited"] for s in sales)
    assert h.sim.people[90]["wealth"] > wealth          # sales credits arrived (net of any new purchase)


def test_goods_close_across_pools_cargo_commons_and_declared_losses_every_turn(monkeypatch):
    """Every titled-trade step conserves commons + owned pools + cargo, less
    the declared losses (transit decay, sea loss) of that step."""
    h = TradeHarness()
    _market(h)
    checked = []

    def total():
        commons, owned, cargo = _goods_total(h)
        return commons + owned + cargo

    def wrap(name):
        real = getattr(TT, name)

        def step(world, *args):
            lost0 = h.tt.counters.get("transit_decay_milli", 0) + h.tt.counters.get("sea_loss_milli", 0)
            start = total()
            out = real(world, *args)
            lost = h.tt.counters.get("transit_decay_milli", 0) + h.tt.counters.get("sea_loss_milli", 0) - lost0
            assert abs(total() - (start - lost)) <= 3, (name, start, total(), lost)    # milli rounding of the commons
            checked.append(name)
            return out
        monkeypatch.setattr(TT, name, step)
    wrap("retail_phase10")
    wrap("after_agent_tick")
    for _ in range(6):
        cargo0 = _goods_total(h)[2]
        h.turn({VERDANT: {"grain": 30.0}})
        cargo1 = _goods_total(h)[2]
        flows = {}
        for f in h.state.frame:
            for k, v in f.flows.items():
                flows[k] = flows.get(k, 0) + v
        lost = sum(e.get("losses", {}).get("transit_decay", 0) for e in h.tt.frame["events"]
                   if e["event"] in OUTCOMES)
        moved = flows.get("sold_merchant", 0) - flows.get("consigned_in", 0) - flows.get("returned_in", 0)
        assert cargo1 - cargo0 == moved - lost
    assert checked.count("retail_phase10") == 6 and checked.count("after_agent_tick") == 6
    for ship in h.tt.closed:
        assert sum(ship.cargo_open) == sum(ship.losses.values()) + ship.delivered + ship.returned + ship.deposited


def test_the_carriers_model_income_is_withheld_exactly_while_it_carries():
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    h.turn({VERDANT: {"grain": 30.0}})                  # the carrier's travel turn
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    assert closed.withheld_turns == 1 and closed.withheld == pytest.approx(MERCHANT_INCOME)
    rows = [r for r in h.tt.frame["withheld"] if r["shipment"] == ship.id]
    assert rows == [{"shipment": ship.id, "carrier": 90, "share": 1.0, "ordinary": MERCHANT_INCOME,
                     "deducted": MERCHANT_INCOME}]
    # Reserved under the trade category for the travel turn only, extended at share 1.0.
    turns = [t for t, rows_ in h.sim.extend_calls if (90, 1.0) in rows_]
    assert turns == [h.world.turn - 1]
    assert h.tt.counters["income_withheld_micro"] == round(MERCHANT_INCOME * 1_000_000)


# --- declared outcomes, each exactly once ------------------------------------------

def test_a_conquest_of_the_destination_returns_the_shipment_to_its_origin_once():
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    cargo, opened = list(ship.cargo), sum(ship.cargo_open)
    h.world.regions[THORNWOOD].controller = "Kethani Empire"      # conquered since dispatch
    claim = h.state.region(VERDANT).claims.get(90, 0)
    h.turn({VERDANT: {"grain": 30.0}})
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    assert (closed.outcome, closed.cause) == ("returned", "destination_conquered")
    assert closed.returned == opened and not closed.losses and closed.closed_region == VERDANT
    assert h.state.region(VERDANT).claims.get(90, 0) >= claim + sum(cargo) - 0   # the holder's claim at home
    frame = next(f for f in h.state.frame if f.region == VERDANT)
    assert frame.flows["returned_in"] == opened
    assert h.tt.counters["returned_destination_conquered"] == 1
    assert sum(1 for e in h.tt.frame["events"] if e["shipment"] == ship.id and e["event"] == "returned") == 1


def _commons(h, rid):
    return [float(h.world.regions[rid].stockpile.goods.get(g, 0.0)) for g in RETAIL_GOODS]


def test_the_holders_death_escheats_the_cargo_to_the_commons_where_it_stands():
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    cargo = list(ship.cargo)
    seen = {}
    h.sim.die_after.add(90)                              # dies in the tick
    h.turn({VERDANT: {"grain": 30.0}}, between=lambda: seen.update(commons=_commons(h, VERDANT)))
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    assert closed.outcome == "escheated" and closed.deposit_reason == "holder_died"
    assert closed.deposited == sum(cargo) and closed.closed_region == VERDANT and closed.cursor == 0
    assert h.tt.counters["escheated"] == 1 and h.tt.counters.get("delivered", 0) == 0
    # Exactly the cargo reached the origin commons after the tick (nothing else touches them then).
    assert _commons(h, VERDANT) == pytest.approx([c + v / 1000 for c, v in zip(seen["commons"], cargo)], abs=1e-9)


def test_a_pool_reset_inside_phase_2_puts_the_cargo_into_that_turns_economy_batch():
    """Review M1: a deposit made while Phase 2 is prepared (after the batch was
    built) must reach the economy: retail patches the batch with it."""
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    rid, cargo = ship.region(), list(ship.cargo)
    before = _commons(h, rid)
    owned = list(h.state.region(rid).goods)               # retail's own reset sends these to the commons too
    h.world.livelihoods._pool_sim = -1                    # the next turn binds another pool: a reset
    h.turn({VERDANT: {"grain": 30.0}})
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    assert closed.outcome == "pool_reset" and closed.deposited == sum(cargo)
    batch = h.region_inputs[-1]
    got = [batch.column(f"stockpile_{g}").to_pylist()[rid] for g in RETAIL_GOODS]
    assert got == pytest.approx([b + (o + v) / 1000 for b, o, v in zip(before, owned, cargo)], abs=1e-4)


def test_a_death_seen_at_reserve_first_puts_the_cargo_into_that_turns_economy_batch(monkeypatch):
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    rid, cargo = ship.region(), list(ship.cargo)
    before = _commons(h, rid)
    real = TT._people
    monkeypatch.setattr(TT, "_people", lambda snap: {k: v for k, v in real(snap).items() if k != 90})
    h.turn({VERDANT: {"grain": 30.0}})
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    assert closed.outcome == "escheated" and closed.closed_turn == h.world.turn - 1
    batch = h.region_inputs[-1]
    got = [batch.column(f"stockpile_{g}").to_pylist()[rid] for g in RETAIL_GOODS]
    assert got == pytest.approx([b + v / 1000 for b, v in zip(before, cargo)], abs=1e-4)


def test_a_quarantine_closure_of_the_route_returns_the_shipment(monkeypatch):
    h = TradeHarness()
    _market(h, origin=FROST, dest=OBSIDIAN, owners=(11, 12, 13), buyers=(61, 62, 63, 64, 65), merchant=91)
    _run_until_dispatch(h, production={FROST: {"grain": 30.0}})
    ship = h.tt.shipments[0]
    assert (ship.origin, ship.dest) == (FROST, OBSIDIAN)
    import chronicler.quarantine_rules as Q
    pair = tuple(sorted((h.world.regions[FROST].controller, h.world.regions[OBSIDIAN].controller)))
    monkeypatch.setattr(Q, "closed_pairs", lambda world: {pair})
    h.turn({FROST: {"grain": 30.0}})
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    assert (closed.outcome, closed.cause) == ("returned", "quarantine_closure")
    assert closed.returned == sum(closed.cargo_open)
    assert h.tt.counters["returned_quarantine_closure"] == 1


def test_routes_take_the_lowest_shortest_path_and_the_narrowest_legs_capacity():
    edges = {(0, 1): (False, -1.0), (1, 2): (False, -1.0), (0, 3): (False, -1.0), (3, 2): (False, -1.0)}
    assert TT._bfs(edges, 0)[2] == [0, 1, 2]             # ties to the lower region
    assert TT._capacity(edges, [0, 1, 2]) == TT.LAND_CAP
    assert TT._capacity({(0, 1): (True, -1.0)}, [0, 1]) == TT.RIVER_CAP
    assert TT._capacity({(0, 1): (False, 0.1)}, [0, 1]) == TT.SEA_CAP


def _released(h, ship):
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    assert closed.outcome == "released_returned" and closed.holder == 90 and closed.cursor == 0
    assert closed.returned == sum(closed.cargo_open) and not closed.losses and closed.delivered == 0
    assert not any(e[1] == "moved" for e in closed.history)               # it never moved unattended
    assert h.tt.counters["released_returned"] == 1
    return closed


def test_a_migrated_carrier_returns_its_shipment_to_the_origin_at_once_with_title_kept():
    """Lead decision M3: no cargo travels without a reserved carrier, and the
    holder's new income never stacks with a margin."""
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    claim = h.state.region(VERDANT).claims.get(90, 0)
    h.sim.people[90]["region"] = FROST                   # migrated before Phase 2
    h.turn({VERDANT: {"grain": 30.0}})
    closed = _released(h, ship)
    assert closed.released == "migrated" and closed.cause == "migrated" and closed.closed_turn == h.world.turn - 1
    # The holder's claim at the origin took the whole cargo (then the turn's decay fell on it).
    assert next(f for f in h.state.frame if f.region == VERDANT).flows["returned_in"] == closed.returned
    assert claim < h.state.region(VERDANT).claims.get(90, 0) <= claim + closed.returned
    assert h.tt.counters["released_returned_migrated"] == 1
    # Never reserved nor withheld once released, and no other shipment is live for it.
    assert not [r for r in h.tt.frame["withheld"] if r["shipment"] == ship.id]
    assert not any((90, 1.0) in rows for t, rows in h.sim.extend_calls if t == h.world.turn - 1)


def test_a_carrier_changing_occupation_in_the_tick_returns_its_shipment_instead_of_moving():
    h = TradeHarness()
    _market(h, origin=FROST, dest=OBSIDIAN, owners=(11, 12, 13), buyers=(61, 62, 63, 64, 65), merchant=90)
    _run_until_dispatch(h, production={FROST: {"grain": 30.0}})
    ship = h.tt.shipments[0]

    def switch():                                        # after Phase 2: the change lands in the tick
        h.sim.people[90]["occupation"] = 0
    h.turn({FROST: {"grain": 30.0}}, between=switch)
    closed = _released(h, ship)
    assert closed.released == "occupation" and closed.closed_region == FROST
    # It was reserved for the turn (withheld once), then returned at Phase 10 instead of moving.
    assert [r["shipment"] for r in h.tt.frame["withheld"]] == [ship.id]


def test_a_pool_reset_and_the_switch_off_end_live_shipments_in_the_commons():
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    TT.on_pool_reset(h.world)
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    assert closed.outcome == "pool_reset" and closed.deposited == sum(closed.cargo_open) and not h.tt.shipments
    h2 = TradeHarness()
    _market(h2)
    _run_until_dispatch(h2)
    ship2 = h2.tt.shipments[0]
    configure_livelihoods(h2.world, _build_parser().parse_args(["--no-titled-trade"]), agent_mode="hybrid")
    closed2 = next(s for s in h2.tt.closed if s.id == ship2.id)
    assert closed2.outcome == "switched_off" and closed2.deposit_reason == "switched_off"
    assert h2.tt.log[-1].kind == "switched_off"


def test_every_shipment_has_exactly_one_outcome_and_ids_are_never_reused():
    h = TradeHarness()
    _market(h)
    for _ in range(8):
        h.turn({VERDANT: {"grain": 30.0}})
    ids = [s.id for s in h.tt.closed] + [s.id for s in h.tt.shipments]
    assert ids and len(ids) == len(set(ids)) and max(ids) < h.tt.next_shipment
    assert all(s.outcome in OUTCOMES and s.status == "closed" for s in h.tt.closed)
    assert sum(h.tt.counters.get(k, 0) for k in OUTCOMES) == len(h.tt.closed)
    assert set(h.tt.counters) <= set(COUNTERS)


def test_a_repeated_phase10_or_settlement_is_refused():
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    h.world.turn -= 1
    with pytest.raises(RuntimeError, match="already"):
        TT.retail_phase10(h.world, None, h.results[-1], h.bridge)
    with pytest.raises(RuntimeError, match="already"):
        TT.after_agent_tick(h.world, h.bridge)
    h.world.turn += 1
    # The payment seam refuses the same shipment's key again.
    sid = h.tt.closed[-1].id if h.tt.closed else h.tt.shipments[-1].id
    bill = M.Bill(purpose="cargo_purchase", batch=sid, phase="phase10", payer=M.agent(90),
                  lines=((M.agent(1), 1),))
    assert M.quote(h.world, bill, turn=h.tt.book.settled[-1][0], book=h.tt.book, sim=h.sim).reason == "already_settled"


# --- ledger -------------------------------------------------------------------------

@pytest.fixture
def python_ledger_only(monkeypatch):
    """Use only A1's offline snapshot/receipt interface in these two unit tests.

    TradeSim has no native wealth observer. Do not invent native stage rows or
    closure: the resulting frame must explicitly retain native=None. The
    production before-tick guard and compiled accounting tests stay unchanged.
    """
    from chronicler import wealth_accounting as WA

    def python_receipts_only(world, bridge, economy_result):
        assert isinstance(bridge._sim, TradeSim)
        assert not hasattr(bridge._sim, "set_wealth_observation")
        assert not hasattr(bridge._sim, "take_wealth_observation")
        assert world.livelihoods.wealth_accounting.mode == "observe"

    monkeypatch.setattr(WA, "before_agent_tick", python_receipts_only)


def test_the_wealth_ledger_records_the_purchases_and_the_withheld_income_and_its_identity_holds(python_ledger_only):
    h = TradeHarness("--wealth-accounting")
    _market(h)
    seen_purchase = seen_withheld = False
    for _ in range(6):
        h.turn({VERDANT: {"grain": 30.0}})
        frame = h.world.livelihoods.wealth_accounting.frame
        assert frame is not None
        assert frame["native"] is None                 # unavailable, not a fake native closure
        assert all(c["closes"] for c in frame["closures"]), [c for c in frame["closures"] if not c["closes"]]
        typed = {r["channel"]: r for r in frame["typed"]}
        cargo = typed["cargo_purchase"]
        assert cargo["in_milli"] == cargo["out_milli"] == sum(d["paid"] for d in h.tt.frame["dispatched"])
        assert cargo["unlocated_in_milli"] == cargo["unlocated_out_milli"] == 0
        seen_purchase |= cargo["in_milli"] > 0
        wh = {r["package"]: r for r in frame["withheld"]["packages"]}
        assert wh["titled_trade"]["deducted"] == pytest.approx(h.tt.frame["withheld_total"])
        assert wh["titled_trade"]["matches"] is True
        seen_withheld |= wh["titled_trade"]["rows"] > 0
        assert frame["withheld"]["unattributed_rows"] == 0
        world = frame["world"]
        regions = sum(r["native_model"] for r in frame["regions"])
        assert world["native_model"] == pytest.approx(regions, abs=1e-6)
    assert seen_purchase and seen_withheld
    life = h.world.livelihoods.wealth_accounting.lifetime
    assert life["cargo_purchase_in_milli"] == life["cargo_purchase_out_milli"] == h.tt.counters["paid_milli"]


def test_with_the_ledger_on_and_trade_off_the_ledger_has_no_a4_rows(python_ledger_only):
    h = TradeHarness("--wealth-accounting", trade=False)
    _market(h)
    h.turn({VERDANT: {"grain": 30.0}})
    frame = h.world.livelihoods.wealth_accounting.frame
    assert frame["native"] is None                     # unavailable, not observed zero
    assert "cargo_purchase" not in {r["channel"] for r in frame["typed"]}
    packages = (frame["withheld"] or {}).get("packages") or []
    assert "titled_trade" not in {r["package"] for r in packages}
    assert not any(k.startswith("cargo_purchase") or k == "withheld_titled_trade"
                   for k in h.world.livelihoods.wealth_accounting.lifetime)


def test_trade_unit_stand_in_still_fails_the_production_native_observer_guard():
    from chronicler import wealth_accounting as WA
    h = TradeHarness("--wealth-accounting")
    with pytest.raises(ValueError, match="requires the A1-2 native wealth observer"):
        WA.before_agent_tick(h.world, h.bridge, None)


# --- persistence and records ----------------------------------------------------------

def test_exact_pickle_and_json_round_trip_with_a_shipment_in_transit_continue_identically():
    from chronicler.models import WorldState
    h = TradeHarness()
    _market(h, origin=FROST, dest=OBSIDIAN, owners=(11, 12, 13), buyers=(61, 62, 63, 64, 65), merchant=91)
    _run_until_dispatch(h, production={FROST: {"grain": 30.0}})
    assert h.tt.shipments and h.tt._turn is None
    back = pickle.loads(pickle.dumps(h.world))
    assert back.model_dump_json() == h.world.model_dump_json()
    loaded = WorldState.model_validate_json(h.world.model_dump_json())
    assert loaded.livelihoods.titled_trade == h.tt
    assert isinstance(loaded.livelihoods.titled_trade.shipments[0], Shipment)
    # An older pickle without later fields still loads.
    raw = h.tt.__getstate__()
    raw["__dict__"] = {k: v for k, v in raw["__dict__"].items() if k in ("schema_version", "enabled")}
    old = TitledTradeState.__new__(TitledTradeState)
    old.__setstate__(raw)
    assert old.shipments == [] and old.next_shipment == 0
    twin = copy.deepcopy(h)
    LV.bind_native_pool(twin.world, twin.bridge, reset=False)
    for _ in range(3):
        h.turn({FROST: {"grain": 30.0}})
        twin.turn({FROST: {"grain": 30.0}})
    assert twin.world.model_dump_json() == h.world.model_dump_json()
    assert twin.sim.people == h.sim.people


def test_the_snapshot_is_dated_and_unknown_when_stale():
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    summary = livelihoods_snapshot_fields(h.world)["livelihoods"]["titled_trade"]
    assert summary["stage"] == "A4" and summary["source_turn"] == h.world.turn - 1
    assert summary["frame"]["turn"] == summary["source_turn"] and summary["shipments"]
    assert summary["flows"] and all(f["purpose"] == "cargo_purchase" for f in summary["flows"])
    h.world.turn += 1
    stale = livelihoods_snapshot_fields(h.world)["livelihoods"]["titled_trade"]
    assert stale["frame"] is None and stale["flows"] is None


def test_a_sea_lane_loses_its_expected_raid_share_and_a_refused_claim_goes_to_the_commons(monkeypatch):
    h = TradeHarness()
    _market(h)
    _run_until_dispatch(h)
    ship = h.tt.shipments[0]
    cargo = list(ship.cargo)
    real = TT._graph

    def sea(world):
        edges, closed = real(world)
        return {**edges, (VERDANT, THORNWOOD): (False, 0.1)}, closed
    monkeypatch.setattr(TT, "_graph", sea)
    # Every claim slot is taken: the holder's delivery cannot become a claim.
    monkeypatch.setattr(HR, "MAX_CLAIMS", h.state.claims_count())
    commons = h.world.regions[THORNWOOD].stockpile.goods.get("grain", 0.0)
    h.turn({VERDANT: {"grain": 30.0}})
    closed = next(s for s in h.tt.closed if s.id == ship.id)
    sea_loss = [math.floor(v * 0.1) for v in cargo]
    assert closed.losses["sea_loss"] == sum(sea_loss)
    after_sea = [v - x for v, x in zip(cargo, sea_loss)]
    decay = [math.floor(v * r) for v, r in zip(after_sea, TT.TRANSIT_DECAY)]
    assert closed.losses["transit_decay"] == sum(decay)
    assert closed.outcome == "delivered" and closed.delivered == 0
    assert closed.deposited == sum(after_sea) - sum(decay) and closed.deposit_reason == "claims_refused"
    assert 90 not in h.state.region(THORNWOOD).claims
    assert h.world.regions[THORNWOOD].stockpile.goods.get("grain", 0.0) >= commons


def test_a_later_carrier_may_buy_the_surplus_an_earlier_carrier_cannot_buy_from_itself():
    """Review m7: a carrier's own claim is off its own offer, not off the next carrier's."""
    h = TradeHarness()
    _market(h)                                           # merchant 90 at the origin
    _merchant(h, 91, VERDANT)

    def own_claim():                                     # merchant 90 holds the origin's only surplus
        HR.consign(h.world, VERDANT, 90, [5000, 0, 0, 0, 0], "returned_in")
    h.turn({VERDANT: {"grain": 3.0}}, between=own_claim)
    assert h.tt.counters.get("plans_no_offer", 0) >= 1    # 90 could not buy its own food
    ship = next(s for s in h.tt.shipments + h.tt.closed if s.holder == 91)
    d = next(x for x in h.tt.frame["dispatched"] if x["shipment"] == ship.id)
    assert {r[0] for r in d["seller_rows"]} == {90}       # 91 bought 90's surplus above its reserve


def _dispatch_floor_case(monkeypatch, carriers=(90,)):
    """Direct dispatch with real Arrow people and isolated market/price inputs."""
    from chronicler.household_retail_state import RetailRegion
    h = TradeHarness()
    _market(h, owners=(1, 2), buyers=(51,), merchant=None)
    for aid in carriers:
        _merchant(h, aid, VERDANT, 100.0)
    claims = {1: 101_000, 2: 101_000}
    h.state.regions = [RetailRegion(region=VERDANT, opened_turn=9, reason="opened",
                                    claims=claims, goods=[sum(claims.values()), 0, 0, 0, 0]),
                       RetailRegion(region=THORNWOOD, opened_turn=9, reason="opened")]
    values = {"ration": .35, "price": 100}
    monkeypatch.setattr(HR, "_ration", lambda _: values["ration"])
    monkeypatch.setattr(HR, "price_milli", lambda *_: values["price"])
    monkeypatch.setattr(TT, "_capacity", lambda *_: 2**100)
    edges = {(VERDANT, THORNWOOD): (False, -1.0)}
    return h, values, edges


def test_dispatch_floor_quantities_match_exact_fraction_oracle_at_boundaries(monkeypatch):
    h, values, edges = _dispatch_floor_case(monkeypatch)
    seen = []
    monkeypatch.setattr(TT, "_plan_quantity", lambda _o, _d, _decay, q: seen.append(q) or 0)
    big_intermediate = False
    # Binary-float rations retain their complete exact ratios.  Wealth is read
    # back through the real float32 Arrow columns before computing the oracle.
    for ration, price, owner_wealth, carrier_wealth in product(
            (.35, .6, 1 / 3, math.nextafter(.35, 0.0), math.nextafter(.6, math.inf)),
            (1, 7, 333, 1000, 3333), (0.0, 50.0, 99.0, 99.99, 99.999, 100.0),
            (0.0, 6.0, 20.0, 100.0)):
        values.update(ration=ration, price=price)
        for aid in (1, 2):
            h.sim.people[aid]["wealth"] = owner_wealth
        h.sim.people[90]["wealth"] = carrier_wealth
        people = TT._people(h.sim.get_snapshot())
        exact = Fraction(ration) * TT.MILLI
        offer = {}
        for owner, claim in h.state.region(VERDANT).claims.items():
            room = max(0, math.floor((TT.MAX_WEALTH - people[owner][3]) * TT.MILLI))
            most = int(room * exact // price)
            big_intermediate |= room * exact.numerator > 2**64
            if (surplus := min(claim - TT.OWNER_KEEP, most)) > 0:
                offer[owner] = surplus
        cash = math.floor(people[90][3] * TT.MILLI) - TT.RESERVE_RATIONS * price - len(offer)
        q_cash = int(max(0, cash) * exact // price)
        expected = [min(sum(offer.values()), q_cash)] if sum(offer.values()) >= TT.MIN_CARGO and q_cash >= TT.MIN_CARGO else []
        seen.clear()
        TT._dispatch(h.world, h.tt, TT._Turn(h.world.turn), h.sim, edges, NS(), None)
        assert seen == expected, (ration, price, owner_wealth, carrier_wealth)
        assert not h.tt.shipments and not h.sim.pair_calls
    assert big_intermediate
    assert h.state.region(VERDANT).claims == {1: 101_000, 2: 101_000}


def test_dispatch_no_margin_candidates_avoid_fraction_multiplication_per_owner(monkeypatch):
    h, _values, edges = _dispatch_floor_case(monkeypatch, carriers=range(90, 130))
    monkeypatch.setattr(TT, "_plan_quantity", lambda *_: 0)
    calls = []
    original = Fraction.__rmul__

    def multiply(self, other):
        calls.append(1)
        return original(self, other)

    monkeypatch.setattr(Fraction, "__rmul__", multiply)
    before = copy.deepcopy(h.sim.people)
    TT._dispatch(h.world, h.tt, TT._Turn(h.world.turn), h.sim, edges, NS(), None)
    assert not h.tt.shipments and not h.sim.pair_calls
    assert h.sim.people == before
    assert h.state.region(VERDANT).claims == {1: 101_000, 2: 101_000}
    assert h.tt.counters["plans_no_margin"] == 40
    # The old correct arithmetic allocated 120 intermediate Fractions for this
    # unchanged refused market; the measured stress case made millions.
    assert calls == []


def test_dispatch_ceiling_and_claim_changes_after_buy_are_read_by_next_carrier(monkeypatch):
    h, _values, edges = _dispatch_floor_case(monkeypatch, carriers=(90, 91))
    reg = h.state.region(VERDANT)
    reg.claims = {1: 101_000}
    reg.goods = [101_000, 0, 0, 0, 0]
    bought = []
    monkeypatch.setattr(TT, "_plan_quantity", lambda _o, _d, _decay, q: min(10, q))

    def buy(world, state, t, sim, acc, aid, origin, dest, path, q, offer, price, ratio, people):
        bought.append((aid, dict(offer)))
        # _buy updates this same mutable people map after the actual transfer;
        # exercise both a newly binding ceiling and a changed physical claim.
        people[1] = (*people[1][:3], TT.MAX_WEALTH)
        reg.claims[1] -= q

    monkeypatch.setattr(TT, "_buy", buy)
    TT._dispatch(h.world, h.tt, TT._Turn(h.world.turn), h.sim, edges, NS(), None)
    assert len(bought) == 1 and bought[0][0] == 90
    assert h.tt.counters["plans_no_offer"] == 1
    assert reg.claims == {1: 100_990}
