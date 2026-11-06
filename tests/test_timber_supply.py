"""PL1 timber supply without the native extension: a constructed three-region
world (home 0 - forest 1 - region 2, in a line) with RS2, the L3 stock and a
recording simulator that stands in for the native registry, paid-work
install, wealth transfers, the agent snapshot and the economy's woodcut
columns (no simulation run)."""
from __future__ import annotations

import math
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import grain_storage as S
from chronicler import livelihoods as LV
from chronicler import repair_projects as RP
from chronicler import timber_stock as TS
from chronicler import timber_supply as TSU
from chronicler import veteran_reintegration as VR
from chronicler.cities_state import City, CityState
from chronicler.grain_reserves import _ensure, set_grain_reserves_enabled
from chronicler.grain_storage_state import StorageAsset
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.timber_supply_state import TimberSupplyState, WageLedger
from chronicler.world_gen import generate_world

#: Stand-in economy: residents of a timber slot harvest RESIDENT a turn; each
#: crew member adds CREW_YIELD (constant returns), the total under the L3 cap.
RESIDENT = 1.0
CREW_YIELD = 2.0


class _Sim:
    """The native seams PL1 and RS2 use: the registry's all-or-none rule,
    paid-work install rules, keyed transfers with a wealth ceiling, merchant
    trips, the agent snapshot and the agent tick."""

    CEILING = 100_000

    def __init__(self, people):
        # id -> [region, occupation, age, settlement]
        self.people = {a: list(v) for a, v in people.items()}
        self.registry: list[tuple[int, int, float, int]] = []
        self.paid: dict[int, float] | None = None
        self.paid_turn = None
        self.receipt = None
        self.wealth: dict[int, int] = {}
        self.keys: set = set()
        self.transfers: list = []
        self.trips: set[int] = set()
        self.held_elsewhere: set[int] = set()     # health or teaching work this turn
        self.cancelled = 0

    def snapshot(self):
        ids = sorted(self.people)
        cols = {"id": pa.array(ids, pa.uint32())}
        for k, name in enumerate(("region", "occupation", "age", "settlement_id")):
            cols[name] = pa.array([self.people[a][k] for a in ids], pa.uint16() if k != 1 else pa.uint8())
        return pa.record_batch(cols)

    def farmers(self, region):
        return sum(1 for v in self.people.values() if v[0] == region and v[1] == 0)

    def reserve_work(self, turn, category, rows):
        held = {r[0] for r in self.registry if r[3] == turn} | self.held_elsewhere
        if any(a not in self.people for a, _ in rows):
            raise ValueError("work reservation names no living agent")
        if any(a in held for a, _ in rows):
            raise ValueError("agent already holds work this turn")
        self.registry = [r for r in self.registry if r[3] == turn]
        self.registry.extend((a, category, f, turn) for a, f in rows)

    def work_reservations(self, turn):
        return [(a, c, f) for a, c, f, t in self.registry if t == turn]

    def extend_paid_work(self, turn, rows):
        held = {a: f for a, _c, f, t in self.registry if t == turn}
        if self.paid is not None and self.paid_turn != turn:
            raise ValueError("pending install of another turn")
        paid = dict(self.paid or {})
        for a, share in rows:
            if a in paid:
                raise ValueError("already has a pending share")
            if share > held.get(a, 0.0) + 1e-9:
                raise ValueError("share above reservation")
            paid[a] = share
        self.paid, self.paid_turn = paid, turn

    def cancel_paid_work(self):
        had = self.paid is not None
        self.paid = None
        self.cancelled += 1
        return had

    def take_paid_work_receipt(self):
        out, self.receipt = self.receipt, None
        return out

    def transfer_wealth(self, turn, purpose, batch, rows):
        key = (turn, purpose, batch)
        if key in self.keys:
            raise ValueError("already applied")
        self.keys.add(key)
        out = []
        for aid, amount in rows:
            if aid not in self.people:
                out.append((aid, amount, 0, amount, 2))
                continue
            room = self.CEILING - self.wealth.get(aid, 0)
            got = min(amount, room)
            self.wealth[aid] = self.wealth.get(aid, 0) + got
            out.append((aid, amount, got, amount - got, 0 if got == amount else 1))
        self.transfers.append((turn, purpose, batch, list(rows)))
        return out

    def trip_agent_ids(self):
        return sorted(self.trips)

    def tick(self, turn):
        if self.paid is not None:
            self.receipt = (turn, [(a, s, 3.0, 3.0 * s) for a, s in sorted(self.paid.items())])
        self.paid = None
        self.registry = []


def _people(**extra):
    people = {a: [0, 0, 30, 0] for a in range(1, 7)}          # six adult farmers at home
    people.update({7: [0, 1, 30, 0],                           # a soldier
                   8: [0, 0, 10, 0],                           # a child
                   9: [0, 2, 40, 0],                           # a merchant
                   20: [1, 0, 30, 0], 21: [1, 0, 30, 0]})      # the forest's own farmers
    people.update(extra)
    return people


def _world(*, treasury=1000, granary=0.5, mode=None, forest_hops=1, timber=0.0):
    w = generate_world(seed=42, num_regions=3, num_civs=2)
    w.agent_mode = "hybrid"
    w.turn = 5
    w.cities = None
    civ, other = w.civilizations
    civ.regions = [r.name for r in w.regions]
    civ.treasury = treasury
    other.regions = []
    names = [r.name for r in w.regions]
    for r in w.regions:
        r.controller = civ.name
        r.stockpile.goods = {"timber": timber, "grain": 10.0}
        r.carrying_capacity = 60
        r.ecology.forest_cover = 0.9
    w.regions[0].adjacencies = [names[1]]
    w.regions[1].adjacencies = [names[0], names[2]]
    w.regions[2].adjacencies = [names[1]]
    for r in w.regions:
        r.resource_types = [0, 255, 255]
        r.resource_base_yields = [1.0, 0.0, 0.0]
    forest = {0: 0, 1: 1, 2: 2}[forest_hops] if forest_hops is not None else None
    if forest is not None:
        w.regions[forest].resource_types = [0, 1, 255]
        w.regions[forest].resource_base_yields = [1.0, 2.0, 0.0]
    set_grain_reserves_enabled(w, True)
    state = _ensure(w)
    for g in state.granaries:
        g.owner, g.grain = 0, 20.0
    storage = S.enable_storage(w)
    storage.assets = [StorageAsset(capacity=100.0, condition=granary if i == 0 else 1.0, owner=0) for i in range(3)]
    for rid in range(3):
        S.set_storage_policy(w, rid, "maintain", 4.0)
    w.livelihoods = LivelihoodsState()
    TS.set_timber_stock_enabled(w, True)
    RP.set_repair_projects_enabled(w, True)
    TSU.set_timber_supply_enabled(w, True, args=SimpleNamespace(timber_supply_mode=mode))
    return w


@pytest.fixture(autouse=True)
def _no_commitments(monkeypatch):
    monkeypatch.setattr(RP, "_commitments", lambda world, sim: getattr(sim, "commitments", {}))


def _batch(world, plan):
    n = len(world.regions)
    cols = {"region_id": pa.array(range(n), pa.uint16())}
    for slot in range(3):
        cols[f"resource_type_{slot}"] = pa.array([r.resource_types[slot] for r in world.regions], pa.uint8())
        cols[f"resource_yield_{slot}"] = pa.array([r.resource_base_yields[slot] for r in world.regions],
                                                  pa.float32())
    cols["stockpile_timber"] = pa.array([r.stockpile.goods.get("timber", 0.0) for r in world.regions], pa.float32())
    cols["granary_work_requested"] = pa.array(plan.requests, pa.float32())
    return pa.record_batch(cols)


def _economy(world, batch, sim):
    """The stand-in native economy: labour-limited granary work after the crews
    left, the residents' and crews' timber under the L3 cap, stock write-back."""
    names = batch.schema.names
    n = len(world.regions)
    col = {name: batch.column(name).to_pylist() for name in names}
    away = col.get("woodcut_labor_away", [0.0] * n)
    labor = col.get("woodcut_labor", [0.0] * n)
    away_out, cut_out, slot_output, granary = {}, {}, {}, {}
    for rid, region in enumerate(world.regions):
        farmers = float(sim.farmers(rid))
        gone = min(away[rid], farmers)
        away_out[rid] = gone
        granary[rid] = min(col["granary_work_requested"][rid], farmers - gone)
        outs = [0.0, 0.0, 0.0]
        cut_out[rid] = 0.0
        for slot in range(3):
            if region.resource_types[slot] != 1:
                continue
            cap = col[f"timber_harvest_cap_{slot}"][rid]
            cap = math.inf if cap is None else cap
            resident = min(RESIDENT if farmers - gone > 0 else 0.0, cap)
            total = resident
            if labor[rid] > 0 and TSU._timber_slot(region) == slot:
                total = min(RESIDENT * (farmers - gone > 0) + CREW_YIELD * labor[rid], cap)
                cut_out[rid] = max(0.0, total - resident)
            outs[slot] = total
        slot_output[region.name] = tuple(outs)
        world.regions[rid].stockpile.goods["timber"] = col["stockpile_timber"][rid]   # native write-back
    econ = SimpleNamespace(granary_work_delivered=granary, craft_output={}, slot_output=slot_output,
                           forage_output={})
    if "woodcut_labor" in names:
        econ.woodcut_labor_away_delivered, econ.woodcut_output = away_out, cut_out
    return econ


def _turn(world, sim, *, fail_economy=False, fail_agent=False, between=None, econ_hook=None):
    """One turn in the simulation's order through the livelihoods dispatch."""
    bridge = SimpleNamespace(_sim=sim, get_snapshot=sim.snapshot)
    plan = S.prepare_storage_work(world, [10.0] * len(world.regions), commitments={})
    batch = _batch(world, plan)
    try:
        batch = LV.prepare_phase2(world, batch, bridge, sim.snapshot(), acc=None)
        if fail_economy:
            raise RuntimeError("native economy failed")
        econ = _economy(world, batch, sim)
        if econ_hook is not None:
            econ_hook(econ)
        S.finish_storage_work(world, plan, [econ.granary_work_delivered[r] for r in range(len(world.regions))])
        LV.finish_phase2(world, econ, bridge, acc=None)
    except BaseException:
        if plan.status == "pending":
            S.rollback_storage_work(world, plan)
        LV.rollback_phase2(world)
        raise

    def tick(*_a, **_k):
        if fail_agent:
            raise RuntimeError("agent tick failed")
        sim.tick(world.turn)
        if between is not None:
            between(sim)
        return []

    LV.wrap_agent_tick(world, bridge, tick, econ)()
    LV.phase10_before_reserves(world, acc=None, economy_result=econ, agent_bridge=bridge)
    LV.phase10(world, acc=None, economy_result=econ, agent_bridge=bridge)
    world.turn += 1
    return batch, econ


def _phase10(world, sim):
    bridge = SimpleNamespace(_sim=sim, get_snapshot=sim.snapshot)
    LV.phase10_before_reserves(world, acc=None, economy_result=None, agent_bridge=bridge)
    LV.phase10(world, acc=None, economy_result=None, agent_bridge=bridge)


def _ts(world) -> TimberSupplyState:
    return world.livelihoods.timber_supply


def _launch(world, sim):
    """Open the RS2 project and launch at this Phase 10 (no Phase 2 yet)."""
    _phase10(world, sim)
    world.turn += 1


# ---------------------------------------------------------------------------
# Switch, prerequisites and feature-off identity
# ---------------------------------------------------------------------------

def test_feature_off_means_no_state_no_columns_and_rs2_unchanged():
    world = _world()
    world.livelihoods.timber_supply = None
    sim = _Sim(_people())
    _phase10(world, sim)
    world.turn += 1
    batch, econ = _turn(world, sim)
    assert "woodcut_labor" not in batch.schema.names and "woodcut_labor_away" not in batch.schema.names
    assert "timber_supply" not in LV.livelihoods_snapshot_fields(world)["livelihoods"]
    assert "timber_supply" not in LV.livelihoods_feature_flags(world)
    assert "timber_supply" not in world.livelihoods.model_dump()
    assert RP._store(world, 0) == 0.0
    # RS2's free timber is the old expression exactly.
    world.regions[0].stockpile.goods["timber"] = 3.25
    assert RP._free_timber(world, 0, {}, 1.0) == max(0.0, 3.25 - 0.0 - 1.0)


def test_prerequisites_and_modes():
    from argparse import Namespace
    world = generate_world(seed=42, num_regions=3, num_civs=2)
    args = Namespace(**{k: None for k in LV.LIVELIHOODS_ARG_KEYS})
    args.timber_supply = True
    with pytest.raises(ValueError, match="--timber-supply requires --agents hybrid, --repair-projects and --timber-stock"):
        LV.configure_livelihoods(world, args, agent_mode="hybrid")
    assert LV.LIVELIHOODS_CHOICES["timber_supply_mode"] == ("supply", "cost_only")
    assert LV.livelihoods_arguments(Namespace(timber_supply=True, timber_supply_mode="cost_only")) == \
        ["--timber-supply", "--timber-supply-mode=cost_only"]
    w = _world(mode="cost_only")
    assert _ts(w).mode == "cost_only" and TSU.timber_supply_active(w)
    w.livelihoods.timber_stock.enabled = False
    assert not TSU.timber_supply_active(w)


# ---------------------------------------------------------------------------
# Planning and crews
# ---------------------------------------------------------------------------

def test_need_launches_a_named_crew_of_eligible_residents():
    world = _world()
    sim = _Sim(_people())
    _phase10(world, sim)
    state = _ts(world)
    (row,) = state.needs
    assert (row.region, row.want, row.free, row.in_transit, row.gap, row.status) == (0, 4.0, 0.0, 0.0, 4.0, "launched")
    (exp,) = state.expeditions
    # Adults of the home region, not the soldier or the child: ascending id, capped.
    assert exp.crew == [1, 2, 3, 4] and exp.launched_crew == [1, 2, 3, 4]
    assert (exp.home, exp.forest, exp.slot, exp.hops, exp.stage, exp.civ) == (0, 1, 1, 1, "outbound", 0)
    assert exp.need == 4.0 and state.counters["launched"] == 1
    # One live expedition per home region: the next turn records it, launches nothing.
    world.turn += 1
    _phase10(world, sim)
    assert [r.status for r in _ts(world).needs] == ["expedition"] and len(_ts(world).expeditions) == 1


def test_veterans_come_first_and_are_noted(monkeypatch):
    world = _world()
    VR.set_veteran_reintegration_enabled(world, True, args=None)
    for hook in ("prepare_phase2", "finish_phase2", "rollback_phase2", "rollback_agent_tick", "phase10",
                 "on_pool_reset"):
        monkeypatch.delattr(VR, hook)
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: [9, 6, 99] if region == 0 else [])
    monkeypatch.setattr(VR, "open_record_ids", lambda w: frozenset({9, 6, 7}))
    noted = []
    monkeypatch.setattr(VR, "note_outcome", lambda w, aid, kind, *, turn, detail=None: noted.append((aid, kind, turn)))
    sim = _Sim(_people())
    _launch(world, sim)
    (exp,) = _ts(world).expeditions
    # Listed eligible veterans first (99 is nobody, 7 a soldier), then by id.
    assert exp.crew == [9, 6, 1, 2] and exp.veterans == [9, 6]
    _turn(world, sim)
    assert noted == [(9, "placed:repair", 6), (6, "placed:repair", 6)]
    assert _ts(world).receipts[0].veterans == [9, 6]


@pytest.mark.parametrize("case, reason", [
    ("no_forest", "no_forest"), ("too_far", "too_far"), ("depleted", "forest_depleted"),
    ("other_civ", "no_forest"), ("unreachable", "no_forest"), ("no_crew", "no_crew"), ("no_coins", "no_coins"),
])
def test_refusals(case, reason, monkeypatch):
    world = _world(forest_hops=None if case == "no_forest" else 2 if case in ("too_far", "unreachable") else 1,
                   treasury=5 if case == "no_coins" else 1000)
    people = _people()
    if case == "too_far":
        monkeypatch.setattr(TSU, "MAX_HOPS", 1)              # the forest is two hops away
    if case == "unreachable":
        world.regions[1].adjacencies = [world.regions[0].name]
        world.regions[2].adjacencies = []
    if case == "depleted":
        for row in world.livelihoods.timber_stock.stocks:
            if (row.region_id, row.slot) == (1, 1):
                row.stock = 0.4 * TS.effective_capacity(world.regions[1], 1)
    if case == "other_civ":
        world.regions[1].controller = world.civilizations[1].name
        world.civilizations[1].regions = [world.regions[1].name]
        world.civilizations[0].regions = [world.regions[0].name, world.regions[2].name]
    if case == "no_crew":
        people = {a: v for a, v in people.items() if v[0] != 0 or v[1] == 1 or v[2] < 20}
    _phase10(world, _Sim(people))
    state = _ts(world)
    (row,) = state.needs
    assert (row.status, row.reason) == ("refused", reason)
    assert state.expeditions == [] and state.counters[f"refused_{reason}"] == 1


def test_an_uncontrolled_forest_is_eligible():
    world = _world()
    world.regions[1].controller = None
    world.civilizations[0].regions = [world.regions[0].name, world.regions[2].name]
    _phase10(world, _Sim(_people()))
    assert _ts(world).needs[0].status == "launched" and _ts(world).expeditions[0].forest == 1


def test_a_busy_forest_refuses_a_second_home():
    world = _world()
    world.grain_reserves.storage.assets[2].condition = 0.5      # region 2 needs timber too
    people = _people()
    people.update({30: [2, 0, 30, 0], 31: [2, 0, 30, 0]})
    sim = _Sim(people)
    _phase10(world, sim)
    rows = {r.region: r for r in _ts(world).needs}
    assert rows[0].status == "launched"
    assert (rows[2].status, rows[2].reason) == ("refused", "forest_busy")


# ---------------------------------------------------------------------------
# Phase 2: reservation, pay, withholding, home labour, cutting
# ---------------------------------------------------------------------------

def test_crew_is_reserved_paid_by_id_withheld_and_removed_from_home_labour():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    treasury = world.civilizations[0].treasury
    batch, econ = _turn(world, sim)
    # Outbound: reserved for the whole turn under the repair category.
    assert batch.column("woodcut_labor_away").to_pylist() == [4.0, 0.0, 0.0]
    assert batch.column("woodcut_labor").to_pylist() == [0.0, 0.0, 0.0]
    assert sim.transfers == [(6, TSU.PURPOSE_REPAIR_WAGE, TSU.WAGE_BATCH, [(1, 500), (2, 500), (3, 500), (4, 500)])]
    assert [sim.wealth[a] for a in (1, 2, 3, 4)] == [500] * 4
    assert world.civilizations[0].treasury == treasury - 2
    state = _ts(world)
    (r,) = state.receipts
    assert (r.stage, r.crew, r.away_requested, r.away_delivered, r.crew_labor, r.cut) == \
        ("outbound", [1, 2, 3, 4], 4.0, 4.0, 0.0, 0.0)
    assert (r.wages_due_milli, r.wages_milli, r.wage_residual_milli) == (2000, 2000, 0)
    assert r.income_withheld == pytest.approx(12.0)                  # share 1.0 of 3.0 each
    (ledger,) = state.ledger
    assert (ledger.charged, ledger.prepaid_before_milli, ledger.prepaid_after_milli) == (2, 0, 0)
    (exp,) = state.expeditions
    assert (exp.stage, exp.travelled, exp.person_turns, exp.wages_milli) == ("cutting", 1, 4, 2000)
    # Cutting: the crew's headcount on the forest's timber slot, marginal harvest on board.
    batch, econ = _turn(world, sim)
    assert batch.column("woodcut_labor").to_pylist() == [0.0, 4.0, 0.0]
    (r,) = _ts(world).receipts
    assert r.cut == pytest.approx(CREW_YIELD * 4) and r.cargo_after == pytest.approx(8.0)
    assert r.stock_before is not None and r.stock_after == pytest.approx(r.stock_before - 9.0 + _regrowth(world, r))


def _regrowth(world, receipt):
    row = next(x for x in world.livelihoods.timber_stock.ledger if (x.region_id, x.slot) == (1, 1))
    return row.regrowth


def test_a_city_farmer_takes_only_the_city_share_away_and_a_merchant_none():
    world = _world()
    world.cities = CityState(cities=[City(settlement_id=5, region=0, name="C5", founded_turn=0, founder=0,
                                          rank=2, size=10.0)])
    from chronicler.cities import URBAN_FARM_LABOR
    people = {1: [0, 0, 30, 5], 2: [0, 2, 30, 0], 3: [0, 0, 30, 0]}
    sim = _Sim(people)
    _launch(world, sim)
    batch, _ = _turn(world, sim)
    assert batch.column("woodcut_labor_away").to_pylist()[0] == pytest.approx(URBAN_FARM_LABOR[2] + 1.0, rel=1e-6)


def test_full_schedule_carries_decays_and_feeds_rs2_from_the_store_first():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    stages = []
    for _ in range(5):
        _turn(world, sim)
        stages.append(_ts(world).receipts[0].stage if _ts(world).receipts else None)
    assert stages == ["outbound", "cutting", "cutting", "cutting", "returning"]
    state = _ts(world)
    assert state.expeditions == []
    (done,) = state.closed
    keep = 1.0 - 0.01
    assert done.status == "delivered" and done.cut == pytest.approx(24.0)
    assert done.delivered == pytest.approx(24.0 * keep) and done.lost == pytest.approx(24.0 * (1 - keep))
    assert done.cut == pytest.approx(done.delivered + done.lost + done.cargo)
    assert state.store == {0: pytest.approx(24.0 * keep)}
    (row,) = state.stores
    assert row.delivered == pytest.approx(24.0 * keep) and row.closing == pytest.approx(24.0 * keep)
    # RS2 reads the store as free timber ahead of the stockpile, its hold takes the store first.
    world.regions[0].stockpile.goods["timber"] = 1.5
    assert RP._free_timber(world, 0, {}, 0.0) == pytest.approx(1.5 + 24.0 * keep)
    _turn(world, sim)
    rp = world.livelihoods.repair_projects
    (receipt,) = rp.receipts
    assert receipt.timber_used == 4.0 and receipt.status == "progress"
    assert _ts(world).store[0] == pytest.approx(24.0 * keep - 4.0)
    assert world.regions[0].stockpile.goods["timber"] == pytest.approx(1.5)
    (row,) = _ts(world).stores
    assert (row.held, row.returned) == (pytest.approx(4.0), 0.0)


def test_unused_held_timber_returns_to_the_stockpile_first_then_the_store():
    world = _world()
    state = _ts(world)
    state.store[0] = 3.0
    world.regions[0].stockpile.goods["timber"] = 2.0
    _phase10(world, _Sim(_people()))
    world.turn += 1
    # The granary asks 4: 3 from the store, 1 from the stockpile; labour delivers 2.
    sim = _Sim({1: [0, 0, 30, 0], 2: [0, 0, 30, 0]})
    _ts(world).expeditions = []                       # no expedition this turn
    _turn(world, sim)
    rp = world.livelihoods.repair_projects
    (receipt,) = rp.receipts
    assert (receipt.timber_held, receipt.timber_used, receipt.timber_returned) == (4.0, 2.0, 2.0)
    # Store used first: 2 used of the 3 taken, so 1 goes back to it and the stockpile's 1 to the stockpile.
    assert _ts(world).store[0] == pytest.approx(1.0)
    assert world.regions[0].stockpile.goods["timber"] == pytest.approx(1.0 + 1.0)
    (row,) = [r for r in _ts(world).stores if r.region == 0]
    assert (row.opening, row.held, row.returned, row.closing) == (3.0, 3.0, 1.0, pytest.approx(1.0))


def test_store_without_an_open_project_is_released_to_the_stockpile():
    world = _world(granary=1.0)
    state = _ts(world)
    state.store[0] = 5.0
    _phase10(world, _Sim(_people()))
    assert _ts(world).store == {}
    assert world.regions[0].stockpile.goods["timber"] == 5.0
    (row,) = _ts(world).stores
    assert (row.opening, row.released, row.closing) == (5.0, 5.0, 0.0)
    assert _ts(world).counters["released"] == 5.0


def test_cost_only_keeps_crews_wages_and_home_labour_but_cuts_nothing():
    supply, control = _world(), _world(mode="cost_only")
    out = {}
    for name, world in (("supply", supply), ("cost_only", control)):
        sim = _Sim(_people())
        _launch(world, sim)
        rows = []
        for _ in range(5):
            batch, _ = _turn(world, sim)
            rows.append((batch.column("woodcut_labor_away").to_pylist(), batch.column("woodcut_labor").to_pylist()))
        out[name] = (rows, sim.transfers, world.civilizations[0].treasury,
                     [x.extraction for x in world.livelihoods.timber_stock.ledger], _ts(world).closed[0])
    (s_rows, s_t, s_treasury, s_ex, s_exp), (c_rows, c_t, c_treasury, c_ex, c_exp) = out["supply"], out["cost_only"]
    assert [r[0] for r in s_rows] == [r[0] for r in c_rows]
    assert all(r[1] == [0.0, 0.0, 0.0] for r in c_rows) and any(r[1][1] > 0 for r in s_rows)
    assert s_t == c_t and s_treasury == c_treasury
    # Review A: a crew home with nothing is "returned", never a delivery.
    assert c_exp.cut == 0.0 and c_exp.delivered == 0.0 and c_exp.status == "returned"
    assert _ts(control).counters.get("delivered_expeditions", 0) == 0
    assert _ts(control).counters["returned_expeditions"] == 1
    assert s_exp.status == "delivered" and _ts(supply).counters["delivered_expeditions"] == 1
    assert c_exp.person_turns == s_exp.person_turns and c_exp.wages_milli == s_exp.wages_milli
    assert c_ex == [RESIDENT] and s_ex == [RESIDENT]          # the last turn walked home
    assert c_exp.cut_turns == s_exp.cut_turns == TSU.CUT_TURNS
    assert _ts(control).store == {}


def test_the_guard_ends_cutting_when_the_stand_falls_below_half():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _turn(world, sim)                               # outbound
    _turn(world, sim)                               # cutting 1
    stock = world.livelihoods.timber_stock
    for row in stock.stocks:
        if (row.region_id, row.slot) == (1, 1):
            row.stock = 0.3 * TS.effective_capacity(world.regions[1], 1)
    batch, _ = _turn(world, sim)                    # the guard: no cutting, the crew walks home
    assert batch.column("woodcut_labor").to_pylist() == [0.0, 0.0, 0.0]
    (r,) = _ts(world).receipts
    assert (r.stage, r.cut_end, r.cut) == ("returning", "forest_depleted", 0.0)
    (exp,) = _ts(world).closed
    assert exp.status == "delivered" and exp.cut_end == "forest_depleted"
    assert exp.delivered == pytest.approx(8.0 * 0.99)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_death_migration_enlistment_trips_and_other_work_drop_members():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)

    def events(s):
        del s.people[1]                 # died
        s.people[2][0] = 2              # migrated
        s.people[3][1] = 1              # enlisted

    _turn(world, sim, between=events)
    (exp,) = _ts(world).expeditions
    assert exp.crew == [4]
    assert [(a, r) for _t, a, r in exp.drops] == [(1, "died"), (2, "migrated"), (3, "enlisted")]
    sim.held_elsewhere = {4}
    _turn(world, sim)
    (exp,) = _ts(world).closed
    assert exp.status == "abandoned" and exp.end_reason == "crew_lost"
    assert [(a, r) for _t, a, r in exp.drops][-1] == (4, "other_work")
    # A roster member and a trip are dropped too.
    world2 = _world()
    sim2 = _Sim(_people())
    _launch(world2, sim2)
    sim2.trips = {1}
    from chronicler.models import Army   # noqa: F401  (the roster is read through war_state)
    world2.war_state = SimpleNamespace(armies=[SimpleNamespace(roster=[(2, 0)])], wars=[], ended_wars=[],
                                       occupations=[])
    _turn(world2, sim2)
    (exp2,) = _ts(world2).expeditions
    assert {(a, r) for _t, a, r in exp2.drops} == {(1, "on_trip"), (2, "enlisted")}
    assert exp2.crew == [3, 4]


def _wipe(s, ids=(1, 2, 3, 4)):
    for a in ids:
        s.people.pop(a, None)


@pytest.mark.parametrize("stage, turns, cut", [("outbound", 1, 0.0), ("cutting", 4, 16.0), ("returning", 6, 24.0)])
def test_a_crew_that_dies_out_deposits_its_cargo_at_the_forest(stage, turns, cut):
    """The whole crew dies at each stage (forest two hops away): the cargo cut
    so far is deposited in the forest region's stockpile as commons, never lost."""
    world = _world(forest_hops=2)
    sim = _Sim(_people())
    _launch(world, sim)
    for i in range(turns):
        _turn(world, sim, between=_wipe if i == turns - 1 else None)
    (r,) = _ts(world).receipts
    assert r.stage == stage
    (exp,) = _ts(world).closed
    assert (exp.status, exp.end_reason) == ("abandoned", "crew_lost")
    assert exp.cut == pytest.approx(cut) and exp.abandoned == pytest.approx(cut)
    assert exp.lost == 0.0 and exp.cargo == 0.0 and exp.delivered == 0.0
    assert world.regions[2].stockpile.goods["timber"] == pytest.approx(cut)
    state = _ts(world)
    assert state.counters.get("abandoned_cargo", 0.0) == pytest.approx(cut)
    assert state.counters.get("lost", 0.0) == 0.0
    assert state.deposits == ([(world.turn - 1, exp.eid, 2, pytest.approx(cut))] if cut else [])


def test_a_partly_lost_crew_goes_on_and_delivers():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _turn(world, sim)                                       # outbound
    _turn(world, sim, between=lambda s: _wipe(s, (1, 2, 3)))   # cut 8, then three die
    for _ in range(3):
        _turn(world, sim)                                   # cut 2, cut 2, walk home
    (exp,) = _ts(world).closed
    assert exp.status == "delivered" and exp.crew == [4]
    assert exp.cut == pytest.approx(8.0 + 2.0 + 2.0)
    assert exp.delivered == pytest.approx(12.0 * 0.99) and exp.abandoned == 0.0


def test_an_unpayable_turn_recalls_the_crew_home_with_its_cargo():
    """Old rule: the expedition was abandoned ``no_coins`` and its cargo lost."""
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _turn(world, sim)                                       # outbound, paid
    _turn(world, sim)                                       # cutting, cut 8
    world.civilizations[0].treasury = 0
    paid = len(sim.transfers)
    batch, _ = _turn(world, sim)
    # No cutting: the crew walks the hop home unpaid, still away and reserved.
    assert batch.column("woodcut_labor").to_pylist() == [0.0, 0.0, 0.0]
    assert batch.column("woodcut_labor_away").to_pylist() == [4.0, 0.0, 0.0]
    (r,) = _ts(world).receipts
    assert (r.stage, r.recalled, r.unpaid, r.cut_end, r.wages_due_milli, r.wages_milli) == \
        ("returning", True, True, "recalled", 0, 0)
    assert r.income_withheld == pytest.approx(12.0)         # away: ordinary income withheld, no wage
    assert len(sim.transfers) == paid and _ts(world).ledger == []
    (exp,) = _ts(world).closed
    assert exp.status == "delivered" and exp.unpaid_turns == 1 and exp.recalled_turn == 8
    assert exp.cut == pytest.approx(8.0) and exp.delivered == pytest.approx(8.0 * 0.99)
    assert exp.abandoned == 0.0 and exp.lost == pytest.approx(8.0 * 0.01)
    assert _ts(world).store == {0: pytest.approx(8.0 * 0.99)}
    assert _ts(world).counters["recalls"] == 1 and _ts(world).counters["unpaid_turns"] == 1
    assert "abandoned_no_coins" not in _ts(world).counters


def test_a_recall_on_the_way_out_turns_back_and_one_at_a_home_forest_arrives_at_once():
    world = _world(forest_hops=2)
    sim = _Sim(_people())
    _launch(world, sim)
    _turn(world, sim)                                       # one hop out of two
    world.civilizations[0].treasury = 0
    _turn(world, sim)                                       # recalled: one hop back, unpaid
    (exp,) = _ts(world).closed
    assert (exp.status, exp.travelled, exp.return_hops, exp.unpaid_turns, exp.cut) == ("returned", 1, 1, 1, 0.0)
    home = _world(forest_hops=0)
    sim2 = _Sim(_people())
    _launch(home, sim2)
    _turn(home, sim2)                                       # cut at home
    home.civilizations[0].treasury = 0
    paid = len(sim2.transfers)
    batch, _ = _turn(home, sim2)                            # recalled where it stands
    assert "woodcut_labor" not in batch.schema.names and len(sim2.transfers) == paid
    (exp2,) = _ts(home).closed
    assert exp2.status == "delivered" and exp2.delivered == pytest.approx(exp2.cut) and exp2.unpaid_turns == 0


def test_the_asset_completing_mid_expedition_releases_the_delivery():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    for _ in range(3):
        _turn(world, sim)
    rp = world.livelihoods.repair_projects
    p = rp.projects[0]
    p.delivered = p.scope                     # the project completes from another source
    world.grain_reserves.storage.assets[0].condition = 1.0
    RP._close(rp, p, world.turn, "completed", None)
    for _ in range(2):
        _turn(world, sim)
    state = _ts(world)
    (exp,) = state.closed
    assert exp.status == "delivered" and state.store == {}
    released = [r for r in state.stores if r.region == 0][0]
    assert released.released == pytest.approx(exp.delivered) and released.closing == 0.0
    assert world.regions[0].stockpile.goods["timber"] == pytest.approx(exp.delivered)


def test_home_controller_change_abandons_and_forest_loss_turns_the_crew_home():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _turn(world, sim)
    _turn(world, sim)                                       # cutting, cargo 8
    other = world.civilizations[1]
    world.regions[1].controller = other.name               # the forest falls to another civ
    other.regions = [world.regions[1].name]
    batch, _ = _turn(world, sim)
    (r,) = _ts(world).receipts
    assert (r.stage, r.cut_end) == ("returning", "forest_lost")
    (exp,) = _ts(world).closed
    assert exp.status == "delivered" and exp.delivered == pytest.approx(8.0 * 0.99)
    # Home conquered: abandoned, cargo lost, no wages paid that turn.
    world2 = _world()
    sim2 = _Sim(_people())
    _launch(world2, sim2)
    _turn(world2, sim2)
    _turn(world2, sim2)
    other2 = world2.civilizations[1]
    world2.regions[0].controller = other2.name
    other2.regions = [world2.regions[0].name]
    paid = len(sim2.transfers)
    _turn(world2, sim2)
    (exp2,) = [e for e in _ts(world2).closed if e.eid == 0]
    assert (exp2.status, exp2.end_reason, exp2.abandoned, exp2.lost) == ("abandoned", "home_lost",
                                                                        pytest.approx(8.0), 0.0)
    assert world2.regions[1].stockpile.goods["timber"] == pytest.approx(8.0)   # commons at the forest
    assert len(sim2.transfers) == paid


def test_the_forest_lost_before_arrival_abandons():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    world.regions[1].controller = world.civilizations[1].name
    world.civilizations[1].regions = [world.regions[1].name]
    _turn(world, sim)
    (exp,) = _ts(world).closed
    assert (exp.status, exp.end_reason, exp.person_turns) == ("abandoned", "forest_lost", 0)


def test_pool_reset_abandons_live_expeditions_and_keeps_stores():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _turn(world, sim)
    _ts(world).store[0] = 2.0
    _turn(world, _Sim(_people()))            # a rebuilt pool: bind_native_pool resets
    state = _ts(world)
    eids = {e.eid: e for e in state.closed}
    assert eids[0].end_reason == "pool_reset" and state.counters["pool_resets"] == 1


def test_a_pool_rebuild_after_packing_defers_the_deposit_to_phase10():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _turn(world, sim)
    _turn(world, sim)                                       # cargo 8
    # The rebuild is noticed in Phase 2, after the batch packed the stockpiles:
    # a deposit then would be overwritten by the economy's write-back.
    _turn(world, _Sim(_people()))
    state = _ts(world)
    (exp,) = [e for e in state.closed if e.eid == 0]
    assert (exp.end_reason, exp.abandoned, exp.lost) == ("pool_reset", pytest.approx(8.0), 0.0)
    assert state.pending_deposits == {} and world.regions[1].stockpile.goods["timber"] == pytest.approx(8.0)


def test_switching_off_abandons_and_releases_every_store():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _ts(world).store[2] = 3.0
    TSU.set_timber_supply_enabled(world, False)
    state = _ts(world)
    assert state.expeditions == [] and state.closed[0].end_reason == "switched_off"
    assert state.store == {} and world.regions[2].stockpile.goods["timber"] == 3.0
    assert not TSU.timber_supply_active(world) and RP._store(world, 2) == 0.0


# ---------------------------------------------------------------------------
# Failures, duplicates and closure
# ---------------------------------------------------------------------------

def test_a_failed_economy_tick_charges_nothing_and_restores_the_store():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _ts(world).store[0] = 3.0
    before = (_ts(world).model_dump_json(), world.civilizations[0].treasury,
              world.regions[0].stockpile.goods["timber"])
    with pytest.raises(RuntimeError, match="native economy failed"):
        _turn(world, sim, fail_economy=True)
    assert (_ts(world).model_dump_json(), world.civilizations[0].treasury,
            world.regions[0].stockpile.goods["timber"]) == before
    assert _ts(world)._turn is None and sim.transfers == []


def test_a_failed_agent_tick_disarms_the_paid_share():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    with pytest.raises(RuntimeError, match="agent tick failed"):
        _turn(world, sim, fail_agent=True)
    assert sim.paid is None and sim.cancelled >= 1


def test_duplicate_and_stale_receipts_are_refused():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    # Woodcut output where nobody cut (outbound turn) is refused before anything moves.
    with pytest.raises(RuntimeError, match="no crew cut"):
        _turn(world, sim, econ_hook=lambda e: e.woodcut_output.__setitem__(2, 1.0))
    world2 = _world()
    sim2 = _Sim(_people())
    _launch(world2, sim2)
    with pytest.raises(RuntimeError, match="woodcut columns"):
        _turn(world2, sim2, econ_hook=lambda e: e.woodcut_output.clear())
    world3 = _world()
    sim3 = _Sim(_people())
    _launch(world3, sim3)
    _turn(world3, sim3)
    # A turn settles once.
    world3.turn -= 1
    bridge = SimpleNamespace(_sim=sim3, get_snapshot=sim3.snapshot)
    with pytest.raises(RuntimeError, match="already settled"):
        TSU.prepare_phase2(world3, pa.record_batch({"region_id": pa.array(range(3), pa.uint16())}),
                           bridge, sim3.snapshot(), None)
    world3.turn += 1
    # A stale in-flight turn of an earlier turn is replaced, never settled.
    _ts(world3)._turn = TSU._Turn(world3.turn - 5, sim3)
    _turn(world3, sim3)
    assert _ts(world3).last_settled_turn == world3.turn - 1


def test_closure_checks_refuse_unbalanced_books():
    TSU.check_ledger(WageLedger(turn=1, civ=0, expeditions=1, person_turns=3, wages_due_milli=1500,
                                wages_applied_milli=1500, wage_residual_milli=0, charged=2,
                                prepaid_before_milli=0, prepaid_after_milli=500))
    with pytest.raises(RuntimeError, match="do not close"):
        TSU.check_ledger(WageLedger(turn=1, civ=0, expeditions=1, person_turns=3, wages_due_milli=1500,
                                    wages_applied_milli=1500, wage_residual_milli=0, charged=1,
                                    prepaid_before_milli=0, prepaid_after_milli=0))
    from chronicler.timber_supply_state import StoreRow
    with pytest.raises(RuntimeError, match="does not close"):
        TSU.check_store(StoreRow(region=0, opening=2.0, held=1.0, closing=2.0))


def test_odd_crews_prepay_the_half_unit_and_wages_close_every_turn():
    world = _world()
    sim = _Sim({1: [0, 0, 30, 0], 2: [0, 0, 30, 0], 3: [0, 0, 30, 0], 20: [1, 0, 30, 0]})
    _launch(world, sim)
    treasury = world.civilizations[0].treasury
    charges = []
    for _ in range(5):
        _turn(world, sim)
        charges.append(_ts(world).ledger[0].charged)
    assert charges == [2, 1, 2, 1, 2]                       # 1500 milli a turn, the remainder prepaid
    assert world.civilizations[0].treasury == treasury - 8
    assert _ts(world).prepaid == {0: 500}


def test_wage_ceiling_is_not_charged():
    world = _world()
    sim = _Sim(_people())
    sim.wealth = {1: _Sim.CEILING - 100}
    _launch(world, sim)
    _turn(world, sim)
    (r,) = _ts(world).receipts
    assert (r.wages_due_milli, r.wages_milli, r.wage_residual_milli) == (2000, 1600, 400)
    assert _ts(world).ledger[0].charged == 2 and _ts(world).prepaid == {0: 400}


# ---------------------------------------------------------------------------
# Observation and persistence
# ---------------------------------------------------------------------------

def test_snapshot_is_dated_and_unknown_without_a_phase2():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    summary = TSU.snapshot_summary(world)
    assert summary["source_turn"] == world.turn - 1 and summary["receipts"] is None
    assert summary["needs"][0]["status"] == "launched"
    _turn(world, sim)
    summary = LV.livelihoods_snapshot_fields(world)["livelihoods"]["timber_supply"]
    assert summary["stage"] == "PL1" and summary["receipts"][0]["stage"] == "outbound"
    assert summary["ledger"][0]["charged"] == 2 and summary["parameters"]["crew_cap"] == TSU.CREW_CAP
    world.turn += 2
    stale = TSU.snapshot_summary(world)
    assert stale["receipts"] is None and stale["ledger"] is None and stale["needs"] is None


def test_state_round_trips_exactly_and_drops_the_turn_in_flight():
    world = _world()
    sim = _Sim(_people())
    _launch(world, sim)
    _turn(world, sim)
    _turn(world, sim)
    state = _ts(world)
    _ts(world).store[1] = 1.25
    text = state.model_dump_json()
    assert TimberSupplyState.model_validate_json(text).model_dump_json() == text
    state._turn = TSU._Turn(world.turn, object())
    back = pickle.loads(pickle.dumps(state))
    assert back._turn is None and back.model_dump_json() == text
    state._turn = None
    assert back == state
    world_back = pickle.loads(pickle.dumps(world))
    assert world_back.livelihoods.timber_supply.model_dump_json() == text
    # A pickle without the later fields restores with defaults.
    raw = TimberSupplyState(mode="cost_only").__getstate__()
    for name in ("stores", "needs", "needs_dropped"):
        raw["__dict__"].pop(name)
    raw["__pydantic_private__"] = None
    old = TimberSupplyState.__new__(TimberSupplyState)
    old.__setstate__(raw)
    assert old.stores == [] and old._turn is None and old.mode == "cost_only"


def test_continuing_after_a_resume_from_a_pickle_matches_an_uninterrupted_run():
    a, b = _world(), _world()
    sa, sb = _Sim(_people()), _Sim(_people())
    for world, sim in ((a, sa), (b, sb)):
        _launch(world, sim)
        _turn(world, sim)
        _turn(world, sim)
    b = pickle.loads(pickle.dumps(b))
    b.livelihoods._pool_sim = id(sb)                       # an exact load re-binds the same pool
    for _ in range(4):
        _turn(a, sa)
        _turn(b, sb)
    assert a.livelihoods.timber_supply.model_dump_json() == b.livelihoods.timber_supply.model_dump_json()
    assert a.civilizations[0].treasury == b.civilizations[0].treasury


def test_every_repair_wage_payer_has_its_own_transfer_batch():
    """The native transfer key is (turn, purpose, batch) and refuses a repeat,
    so RS2 workshop wages, PL3 granary crews and PL1 expeditions, which can all
    pay ``repair_wage`` in one turn, need distinct batches (integration fix:
    PL1 and PL3 both used batch 1)."""
    import inspect
    import re
    from chronicler import recovery_crews as RC
    from chronicler import repair_projects as RP
    rs2 = re.findall(r"PURPOSE_REPAIR_WAGE, (\w+), wages", inspect.getsource(RP))
    assert rs2 == ["0"]
    assert RP.PURPOSE_REPAIR_WAGE == TSU.PURPOSE_REPAIR_WAGE == 3  # PL3 imports RS2's constant
    assert len({0, RC.GRANARY_WAGE_BATCH, TSU.WAGE_BATCH}) == 3
