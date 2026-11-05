"""PL3 recovery crews and the RS2 ``no_people`` correction without the native
extension: constructed worlds and a recording simulator stand in for the
native registry, paid-work install, keyed wealth transfers, the agent
snapshot and the storage work channel, whose delivery is limited by the
region's farm labour (farmers x ``farm_labor_factor``) as ``economy.rs`` does."""
from __future__ import annotations

import math
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import grain_storage as S
from chronicler import livelihoods as LV
from chronicler import recovery_crews as RC
from chronicler import repair_projects as RP
from chronicler import veteran_reintegration as VR
from chronicler import workshops as W
from chronicler.cities_state import City, CityState
from chronicler.grain_reserves import _ensure, set_grain_reserves_enabled
from chronicler.grain_storage_state import StorageAsset
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.recovery_crews_state import CivCrewLedger, RecoveryCrewsState
from chronicler.workshops_state import WorkshopSite, WorkshopState
from chronicler.world_gen import generate_world

FARMER, SOLDIER, MERCHANT = 0, 1, 2
CITY = 5          # a rank-1 city of region 1: urban farmers farm 0.8 of their turn


class _Sim:
    """Records the native seams: the registry's all-or-none rule (also against
    rural health work held natively), paid-work install rules, keyed wealth
    transfers with a wealth ceiling, merchant trips and the agent snapshot."""

    CEILING = 100_000

    def __init__(self, people):
        # id -> (region, occupation, age, settlement id)
        self.people = dict(people)
        self.registry: list[tuple[int, int, float, int]] = []
        self.health: set[int] = set()
        self.trips: set[int] = set()
        self.paid = None
        self.paid_turn = None
        self.receipt = None
        self.wealth: dict[int, int] = {}
        self.keys: set = set()
        self.transfers: list = []
        self.cancelled = 0

    def get_snapshot(self):
        ids = sorted(self.people)
        col = lambda i, t: pa.array([self.people[a][i] for a in ids], t)   # noqa: E731
        return pa.record_batch({"id": pa.array(ids, pa.uint32()), "region": col(0, pa.uint16()),
                                "occupation": col(1, pa.uint8()), "age": col(2, pa.uint16()),
                                "settlement_id": col(3, pa.uint16())})

    def trip_agent_ids(self):
        return sorted(self.trips)

    def plan_workshop_crews(self, requests, enlisted, turn=None, *, priority_ids=None):
        rank = {a: i for i, a in enumerate(priority_ids or [])}
        held = {r[0] for r in self.registry if r[3] == turn} | self.health
        out = []
        for site, region, settlement, diverted, most in requests:
            pool = sorted((a for a, (r, occ, age, s) in self.people.items()
                           if (r, occ, s) == (region, FARMER, settlement) and age >= 20 and a not in enlisted
                           and a not in held and a not in self.trips), key=lambda a: (rank.get(a, math.inf), a))
            crew = pool[:most]
            if turn is not None:
                self.reserve_work(turn, 0, [(a, diverted) for a in crew])
                held.update(crew)
            out.append((site, region, settlement, len(pool), 0, 0, 0, len(pool), crew, [30] * len(crew),
                        len(crew) * diverted))
        return out

    def take_craft_inputs(self):
        return None

    def reserve_work(self, turn, category, rows):
        held = {r[0] for r in self.registry if r[3] == turn} | self.health
        if any(a in held for a, _ in rows):
            raise ValueError("agent already holds work this turn")
        if any(a not in self.people for a, _ in rows):
            raise ValueError("work reservation names no living agent")
        if any(not 0.0 < f <= 1.0 for _, f in rows):
            raise ValueError("work reservation fraction must be in (0, 1]")
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
        if len({a for a, _ in rows}) != len(rows):
            raise ValueError("duplicate")
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

    def tick(self, turn):
        """The native agent tick: consume the paid share, clear the registry."""
        if self.paid is not None:
            self.receipt = (turn, [(a, s, 2.0, 2.0 * s) for a, s in sorted(self.paid.items())])
        self.paid = None
        self.registry = []
        return []


class _Bridge:
    def __init__(self, sim):
        self._sim = sim

    def get_snapshot(self):
        return self._sim.get_snapshot()


def _people(extra=None):
    """Region 0: rural adult farmers 1-3, a child farmer 4, a merchant 5.
    Region 1 (city 5): urban farmers 100-105, rural farmers 110-111, a
    merchant 120. Region 2: rural farmers 200-203."""
    people = {1: (0, FARMER, 30, 0), 2: (0, FARMER, 30, 0), 3: (0, FARMER, 30, 0), 4: (0, FARMER, 12, 0),
              5: (0, MERCHANT, 30, 0)}
    people.update({a: (1, FARMER, 30, CITY) for a in range(100, 106)})
    people.update({110: (1, FARMER, 30, 0), 111: (1, FARMER, 30, 0), 120: (1, MERCHANT, 30, 0)})
    people.update({a: (2, FARMER, 30, 0) for a in range(200, 204)})
    people.update(extra or {})
    return people


def _world(*, granary=(0.5, 1.0, 1.0), site=None, treasury=1000, timber=50.0, crews="paid", repair_mode=None):
    w = generate_world(seed=42, num_regions=3, num_civs=2)
    w.agent_mode = "hybrid"
    w.turn = 5
    civ = w.civilizations[0]
    civ.regions = [r.name for r in w.regions]
    civ.treasury = treasury
    other = w.civilizations[1]
    other.regions = []
    other.treasury = treasury
    for r in w.regions:
        r.controller = civ.name
        r.stockpile.goods = {"timber": timber, "grain": 10.0}
    set_grain_reserves_enabled(w, True)
    state = _ensure(w)
    for g in state.granaries:
        g.owner, g.grain = 0, 20.0
    storage = S.enable_storage(w)
    storage.assets = [StorageAsset(capacity=100.0, condition=c, owner=0) for c in granary]
    for rid in range(3):
        S.set_storage_policy(w, rid, "maintain", 4.0)
    w.cities = CityState(cities=[City(settlement_id=CITY, region=1, name="C5", founded_turn=0, founder=0,
                                      rank=1, size=10.0)])
    w.livelihoods = LivelihoodsState()
    if site is not None:
        ws = w.livelihoods.workshops = WorkshopState(mode="operate")
        ws.sites = [WorkshopSite(site=0, region=1, settlement_id=CITY, city_name="C5", selected_turn=0,
                                 asset="open", construction_paid=W.CONSTRUCTION_COST, condition=site)]
        ws.next_site = 1
    RP.set_repair_projects_enabled(w, True, args=SimpleNamespace(repair_mode=repair_mode))
    if crews is not None:
        RC.set_recovery_crews_enabled(w, True, args=SimpleNamespace(recovery_crew_mode=crews))
    return w


@pytest.fixture(autouse=True)
def _no_commitments(monkeypatch):
    monkeypatch.setattr(RP, "_commitments", lambda world, sim: {})


def _factor(world, sim):
    """The cities' farm_labor_factor of the people: each urban farmer farms 0.8."""
    out = []
    for rid in range(len(world.regions)):
        farmers = [a for a, (r, occ, _age, _s) in sim.people.items() if r == rid and occ == FARMER]
        urban = sum(1 for a in farmers if sim.people[a][3] == CITY and rid == 1)
        out.append(1.0 - 0.2 * urban / len(farmers) if farmers else 1.0)
    return out


def _labour(world, sim, factor):
    return [sum(1 for (r, occ, _age, _s) in sim.people.values() if r == rid and occ == FARMER) * f
            for rid, f in enumerate(factor)]


def _batch(world, sim, plan):
    n = len(world.regions)
    return pa.record_batch({
        "region_id": pa.array(range(n), pa.uint16()),
        "craft_raw_demand": pa.array([1.0] * n, pa.float32()),
        "stockpile_timber": pa.array([r.stockpile.goods.get("timber", 0.0) for r in world.regions], pa.float32()),
        "farm_labor_factor": pa.array(_factor(world, sim), pa.float32()),
        "granary_work_requested": pa.array(plan.requests, pa.float32()),
    })


def _turn(world, sim, *, fail_economy=False, fail_agent=False, extra=()):
    """One turn in the simulation's order through the livelihoods fan-out:
    storage plan, Phase 2 hooks, a native economy whose storage channel
    delivers at most the farm labour, settlement, the wrapped agent tick and
    Phase 10."""
    bridge = _Bridge(sim)
    snapshot = sim.get_snapshot()
    plan = S.prepare_storage_work(world, [10.0] * len(world.regions), commitments={})
    batch = _batch(world, sim, plan)
    try:
        batch = LV.prepare_phase2(world, batch, bridge, snapshot)
        if fail_economy:
            raise RuntimeError("native economy failed")
        requested = batch.column("granary_work_requested").to_pylist()
        labour = _labour(world, sim, batch.column("farm_labor_factor").to_pylist())
        delivered = {rid: (min(r, labour[rid]) if r > 0 else 0.0) for rid, r in enumerate(requested)}
        for rid, value in enumerate(batch.column("stockpile_timber").to_pylist()):
            world.regions[rid].stockpile.goods["timber"] = value
        econ = SimpleNamespace(granary_work_delivered=delivered, craft_output={})
        S.finish_storage_work(world, plan, [delivered[r] for r in range(len(world.regions))])
        LV.finish_phase2(world, econ, bridge)
    except BaseException:
        if plan.status == "pending":
            S.rollback_storage_work(world, plan)
        LV.rollback_phase2(world)
        raise

    def tick():
        if fail_agent:
            raise RuntimeError("agent tick failed")
        return sim.tick(world.turn)

    LV.wrap_agent_tick(world, bridge, tick, econ)()
    for fn in extra:
        fn(world)
    LV.phase10_before_reserves(world, economy_result=econ, agent_bridge=bridge)
    LV.phase10(world, economy_result=econ, agent_bridge=bridge)
    world.turn += 1
    return batch, econ


def _rs2(world):
    return world.livelihoods.repair_projects


def _rc(world) -> RecoveryCrewsState:
    return world.livelihoods.recovery_crews


def _open(world, sim):
    RP.phase10_before_reserves(world, None, None, _Bridge(sim))


# ---------------------------------------------------------------------------
# Granary crews
# ---------------------------------------------------------------------------

def test_granary_crew_is_named_reserved_withheld_and_paid_the_granary_coins():
    world = _world()
    sim = _Sim(_people())
    _open(world, sim)
    (p,) = _rs2(world).projects
    treasury = world.civilizations[0].treasury
    registry = []
    original = sim.reserve_work
    sim.reserve_work = lambda turn, cat, rows: (registry.append((cat, list(rows))), original(turn, cat, rows))
    batch, econ = _turn(world, sim)
    # Three free adult farmers farm 3 work: the child and the merchant never join,
    # and the request shrinks from the planned 4 to the crew (no_labor).
    assert registry == [(RP.CATEGORY_REPAIR, [(1, 1.0), (2, 1.0), (3, 1.0)])]
    assert batch.column("granary_work_requested").to_pylist()[0] == 3.0
    assert econ.granary_work_delivered[0] == 3.0
    (r,) = _rc(world).receipts
    assert (r.kind, r.pid, r.region, r.payer, r.eligible) == ("granary", p.pid, 0, 0, 3)
    assert (r.planned, r.capacity, r.requested, r.delivered) == (4.0, 3.0, 3.0, 3.0)
    assert [(m.agent_id, m.origin, m.share, m.worked, m.farm_time) for m in r.members] == \
           [(a, "rural_farmer", 1.0, 1.0, 1.0) for a in (1, 2, 3)]
    # Paid mode: the 2 coins per delivered work go to the crew by stable id.
    (turn, purpose, wage_batch, rows) = sim.transfers[0]
    assert (purpose, wage_batch, rows) == (RP.PURPOSE_REPAIR_WAGE, RC.GRANARY_WAGE_BATCH,
                                           [(1, 2000), (2, 2000), (3, 2000)])
    assert sim.wealth == {1: 2000, 2: 2000, 3: 2000}
    assert (r.coin_cost_milli, r.wages_due_milli, r.wages_milli, r.sunk_milli) == (6000, 6000, 6000, 0)
    assert [m.income_replaced for m in r.members] == [2.0, 2.0, 2.0]
    # RS2's own books are unchanged: one charge of the coin cost, anonymous receipt.
    (rr,) = _rs2(world).receipts
    assert rr.crew == [] and rr.wages_due_milli == 0 and rr.reasons == ["no_labor"]
    (ledger,) = _rs2(world).ledger
    assert (ledger.charged, ledger.coin_cost_milli) == (6, 6000)
    assert treasury - world.civilizations[0].treasury == 6
    (crew_ledger,) = _rc(world).ledger
    assert crew_ledger == CivCrewLedger(turn=5, civ=0, coin_cost_milli=6000, wages_due_milli=6000,
                                        wages_milli=6000, wage_residual_milli=0, sunk_milli=0)
    assert _rc(world).counters["granary_crew_short"] == 1


def test_crew_covers_the_planned_work_with_urban_farm_shares():
    """Urban farmers of the rank-1 city farm 0.8 of their turn (the city has
    the rest): five of them cover 4 work; the last share is the remainder."""
    world = _world(granary=(1.0, 0.5, 1.0))
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    (r,) = _rc(world).receipts
    assert r.requested == pytest.approx(4.0) and r.delivered == pytest.approx(4.0)
    assert [m.agent_id for m in r.members] == [100, 101, 102, 103, 104]
    assert {m.origin for m in r.members} == {"urban_farmer"}
    assert [m.share for m in r.members] == pytest.approx([0.8] * 5)
    assert sum(m.wage_milli for m in r.members) == r.coin_cost_milli == 8000


def test_unpaid_keeps_the_crews_charge_withholding_and_sink():
    paid, unpaid = _world(), _world(crews="unpaid")
    sims = {}
    for w in (paid, unpaid):
        sims[id(w)] = sim = _Sim(_people())
        _open(w, sim)
        _turn(w, sim)
        _turn(w, sim)
    a, b = _rc(paid), _rc(unpaid)
    assert [m.model_dump(exclude={"wage_due_milli", "wage_milli"}) for r in a.receipts for m in r.members] == \
           [m.model_dump(exclude={"wage_due_milli", "wage_milli"}) for r in b.receipts for m in r.members]
    assert paid.civilizations[0].treasury == unpaid.civilizations[0].treasury
    assert _rs2(paid).ledger == _rs2(unpaid).ledger
    assert sims[id(unpaid)].transfers == [] and sims[id(unpaid)].wealth == {}
    assert sims[id(paid)].paid_turn == sims[id(unpaid)].paid_turn
    # The wages paid are exactly the coins the control sinks.
    assert a.counters["granary_wages_milli"] == b.counters["granary_sunk_milli"] == 12000
    assert a.counters["granary_sunk_milli"] == 0 and b.counters["granary_wages_milli"] == 0
    assert sum(sims[id(paid)].wealth.values()) == a.counters["granary_wages_milli"]


def test_a_wage_the_ceiling_refuses_stays_a_sink_and_the_charge_is_unchanged():
    world = _world()
    sim = _Sim(_people())
    sim.CEILING = 500
    _open(world, sim)
    treasury = world.civilizations[0].treasury
    _turn(world, sim)
    (r,) = _rc(world).receipts
    assert (r.wages_due_milli, r.wages_milli, r.wage_residual_milli, r.sunk_milli) == (6000, 1500, 4500, 4500)
    assert treasury - world.civilizations[0].treasury == 6
    RC.check_ledger(_rc(world).ledger[0])


def test_no_free_adult_farmer_stalls_the_granary_without_holding_timber_or_coins():
    world = _world()
    people = {a: v for a, v in _people().items() if a not in (1, 2, 3)}       # only the child farmer
    sim = _Sim(people)
    _open(world, sim)
    timber = world.regions[0].stockpile.goods["timber"]
    _turn(world, sim)
    (rr,) = _rs2(world).receipts
    assert rr.status == "stalled" and rr.requested == 0.0 and rr.reasons == ["no_labor"]
    assert rr.timber_held == 0.0 and world.regions[0].stockpile.goods["timber"] == timber
    (r,) = _rc(world).receipts
    assert r.members == [] and r.planned == 4.0 and r.requested == 0.0
    assert sim.transfers == [] and _rc(world).counters["granary_no_crew"] == 1


def test_registry_holders_health_work_trips_and_the_enlisted_never_join(monkeypatch):
    world = _world()
    sim = _Sim(_people({6: (0, FARMER, 30, 0), 7: (0, FARMER, 30, 0)}))
    sim.registry = [(1, 1, 0.5, world.turn)]                 # an L5 learner this turn
    sim.trips = {2}
    sim.health = {3}
    world.health_care = SimpleNamespace(_prepared=[(3, 0, 6, 0.3)])       # patient 3, carer 6
    monkeypatch.setattr(W, "_enlisted", lambda w: [7])
    _open(world, sim)
    _turn(world, sim)
    (r,) = _rc(world).receipts
    assert r.members == [] and r.eligible == 0


def test_veteran_priority_on_a_granary_crew_and_the_placement_is_noted(monkeypatch):
    world = _world()
    VR.set_veteran_reintegration_enabled(world, True, args=None)
    for hook in ("prepare_phase2", "finish_phase2", "rollback_phase2", "rollback_agent_tick", "phase10",
                 "on_pool_reset", "after_agent_tick"):
        monkeypatch.delattr(VR, hook, raising=False)
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: [3, 5] if region == 0 else [])
    monkeypatch.setattr(VR, "open_record_ids", lambda w: frozenset({3, 5}))
    noted = []
    monkeypatch.setattr(VR, "note_outcome", lambda w, aid, kind, *, turn, detail=None:
                        noted.append((aid, kind, detail)))
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    (r,) = _rc(world).receipts
    # The veteran farmer first; the veteran merchant is no farmer and stays off.
    assert [m.agent_id for m in r.members] == [3, 1, 2]
    assert [m.veteran for m in r.members] == [True, False, False]
    assert noted == [(3, "placed:repair", {"site": None, "region": 0})]
    assert _rc(world).counters["veterans_placed"] == 1


def test_death_migration_and_enlistment_leave_next_turns_crew(monkeypatch):
    world = _world()
    sim = _Sim(_people({6: (0, FARMER, 30, 0), 7: (0, FARMER, 30, 0)}))
    _open(world, sim)
    _turn(world, sim)
    assert [m.agent_id for m in _rc(world).receipts[0].members] == [1, 2, 3, 6]
    del sim.people[1]                                   # died in the tick
    sim.people[2] = (2, FARMER, 30, 0)                  # moved to region 2
    monkeypatch.setattr(W, "_enlisted", lambda w: [3])  # drafted in Phase 5
    _turn(world, sim)
    (r,) = _rc(world).receipts
    assert [m.agent_id for m in r.members] == [6, 7]
    assert r.requested == 2.0 and r.delivered == 2.0
    assert sim.wealth[1] == 2000 and 1 not in [a for a, _c, _f in sim.work_reservations(world.turn - 1)]


def test_a_new_controller_pays_the_inherited_crew():
    world = _world()
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    winner = world.civilizations[1]
    winner.regions = [r.name for r in world.regions]
    for r in world.regions:
        r.controller = winner.name
    world.civilizations[0].regions = []
    before = (world.civilizations[0].treasury, winner.treasury)
    _turn(world, sim)
    (r,) = _rc(world).receipts
    assert r.payer == 1 and [m.agent_id for m in r.members] == [1, 2, 3]
    assert world.civilizations[0].treasury == before[0]
    assert [(row.civ, row.charged) for row in _rs2(world).ledger] == [(1, 6)]
    assert [(row.civ, row.wages_milli) for row in _rc(world).ledger] == [(1, 6000)]


def test_a_failed_economy_tick_records_nothing_and_a_failed_agent_tick_drops_the_frame():
    world = _world()
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    frame = _rc(world).model_dump_json()
    with pytest.raises(RuntimeError, match="economy failed"):
        _turn(world, sim, fail_economy=True)
    assert _rc(world)._turn is None and _rc(world).model_dump_json() == frame
    assert sim.transfers[-1][0] == world.turn - 1                  # nothing paid for the failed turn
    # A failed native turn is abandoned; the retry below starts from a fresh registry.
    sim.registry = []
    with pytest.raises(RuntimeError, match="agent tick failed"):
        _turn(world, sim, fail_agent=True)
    assert _rc(world)._turn is None and _rc(world).model_dump_json() == frame
    assert sim.cancelled >= 1 and sim.paid is None
    # The run goes on: the next turn settles normally.
    world.turn += 1
    _turn(world, sim)
    assert _rc(world).last_settled_turn == world.turn - 1


def test_duplicate_settlement_and_stale_receipts_are_refused():
    world = _world()
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    with pytest.raises(ValueError, match="already applied"):
        sim.transfer_wealth(world.turn - 1, RP.PURPOSE_REPAIR_WAGE, RC.GRANARY_WAGE_BATCH, [(1, 1)])
    world.turn -= 1
    with pytest.raises(RuntimeError, match="already settled"):
        RC._begin(world, sim)
    world.turn += 1
    # A paid-work receipt of another turn is refused.
    sim.receipt = (world.turn - 7, [(1, 1.0, 2.0, 2.0)])
    world.livelihoods._paid_receipt = None
    with pytest.raises(RuntimeError, match="another turn"):
        LV.paid_work_receipt(world, sim)
    # A turn left staged by a failed run is discarded (counted) at the next turn.
    world.turn += 1
    RC._begin(world, sim)
    world.turn += 1
    RC._begin(world, sim)
    assert _rc(world).counters["turns_discarded"] == 1


def test_pool_reset_clears_the_frame_and_an_exact_rebind_keeps_it():
    world = _world()
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    keep = pickle.loads(pickle.dumps(world.livelihoods))
    world.livelihoods._pool_sim = id(sim)
    LV.bind_native_pool(world, _Bridge(_Sim(_people())))        # a rebuilt pool: ids name strangers
    assert _rc(world).receipts is None and _rc(world).counters["pool_resets"] == 1
    rebound = SimpleNamespace(livelihoods=keep)
    LV.bind_native_pool(rebound, _Bridge(sim), reset=False)
    assert rebound.livelihoods.recovery_crews.receipts is not None


def test_state_pickles_exactly_and_drops_the_turn_in_flight():
    world = _world()
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    state = _rc(world)
    RC._begin(world, sim)
    assert state._turn is not None
    back = pickle.loads(pickle.dumps(state))
    assert back.model_dump() == state.model_dump() and back._turn is None
    assert back.model_dump_json() == state.model_dump_json()
    assert RecoveryCrewsState.model_validate_json(state.model_dump_json()).model_dump() == state.model_dump()
    # A state pickled before a field existed restores its defaults.
    raw = state.__getstate__()
    raw["__dict__"] = {k: v for k, v in raw["__dict__"].items() if k not in ("rows_dropped", "ledger")}
    old = RecoveryCrewsState.__new__(RecoveryCrewsState)
    old.__setstate__(raw)
    assert old.rows_dropped == 0 and old.ledger is None


def test_snapshot_is_dated_and_unknown_without_a_settled_phase2():
    world = _world()
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    snap = LV.livelihoods_snapshot_fields(world)["livelihoods"]["recovery_crews"]
    assert snap["stage"] == "PL3" and snap["source_turn"] == world.turn - 1 and snap["mode"] == "paid"
    assert len(snap["receipts"]) == 1 and snap["ledger"][0]["wages_milli"] == 6000
    world.turn += 1
    snap = LV.livelihoods_snapshot_fields(world)["livelihoods"]["recovery_crews"]
    assert snap["receipts"] is None and snap["ledger"] is None


# ---------------------------------------------------------------------------
# Workshop repair crews: the wider pool
# ---------------------------------------------------------------------------

def _vets(monkeypatch, world, *, eligible, priority):
    VR.set_veteran_reintegration_enabled(world, True, args=None)
    for hook in ("prepare_phase2", "finish_phase2", "rollback_phase2", "rollback_agent_tick", "phase10",
                 "on_pool_reset", "after_agent_tick"):
        monkeypatch.delattr(VR, hook, raising=False)
    monkeypatch.setattr(VR, "_eligible_ids", lambda w, s: set(eligible))
    monkeypatch.setattr(VR, "_ordered", lambda s, region, ids: [a for a in eligible if a in ids])
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: list(priority))
    monkeypatch.setattr(VR, "open_record_ids", lambda w: frozenset(eligible))
    noted = []
    monkeypatch.setattr(VR, "note_outcome", lambda w, aid, kind, *, turn, detail=None: noted.append((aid, kind)))
    return noted


def test_without_the_switch_the_workshop_crew_is_the_site_citys():
    world = _world(granary=(1.0, 1.0, 1.0), site=0.4, crews=None)
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    (r,) = _rs2(world).receipts
    assert r.crew == [100, 101, 102, 103]
    assert world.livelihoods.recovery_crews is None


def test_the_workshop_pool_widens_to_the_region_and_admits_veterans_first(monkeypatch):
    world = _world(granary=(1.0, 1.0, 1.0), site=0.4)
    noted = _vets(monkeypatch, world, eligible=[120], priority=[120])
    people = {a: v for a, v in _people().items() if a not in (102, 103, 104, 105)}   # two city farmers left
    sim = _Sim(people)
    _open(world, sim)
    batch, _econ = _turn(world, sim)
    (r,) = _rs2(world).receipts
    # The veteran merchant first (RS3 priority), then the city and rural farmers by id.
    assert r.crew == [120, 100, 101, 110] and r.veterans == [120]
    d = 1.0 - 0.8
    assert r.share == pytest.approx(d) and r.wages_due_milli == 4 * 100
    (c,) = _rc(world).receipts
    assert (c.kind, c.eligible, c.eligible_site_city) == ("workshop", 5, 2)
    assert [(m.agent_id, m.origin) for m in c.members] == [(120, "veteran"), (100, "site_city"),
                                                           (101, "site_city"), (110, "rural_farmer")]
    # The rural farmer's repair share leaves the region's farm labour (4 farmers).
    assert [m.farm_time for m in c.members] == pytest.approx([0.0, 0.0, 0.0, d])
    factor = batch.column("farm_labor_factor").to_pylist()[1]
    assert factor == pytest.approx(1.0 - 0.2 * 2 / 4 - d / 4, rel=1e-6)
    assert c.farm_time_removed == pytest.approx(d)
    # Every member's paid share is withheld (the wage replaces it).
    assert r.income_replaced == pytest.approx(4 * 2.0 * d)
    assert noted == [(120, "placed:repair")]
    assert _rc(world).counters["workshop_members_veteran"] == 1


def test_record_only_admits_the_same_veterans_without_putting_them_first(monkeypatch):
    world = _world(granary=(1.0, 1.0, 1.0), site=0.4)
    _vets(monkeypatch, world, eligible=[120], priority=[])
    people = {a: v for a, v in _people().items() if a not in (101, 102, 103, 104, 105)}
    sim = _Sim(people)
    _open(world, sim)
    _turn(world, sim)
    (r,) = _rs2(world).receipts
    assert r.crew == [100, 110, 111, 120] and r.veterans == [120]


def test_eligible_ids_api_for_woodcutting(monkeypatch):
    world = _world(granary=(1.0, 1.0, 1.0))
    _vets(monkeypatch, world, eligible=[120], priority=[120])
    sim = _Sim(_people())
    sim.registry = [(100, 0, 0.2, world.turn)]
    assert RC.eligible_ids(world, 1, "woodcut", sim=sim) == [120, 101, 102, 103, 104, 105, 110, 111]
    assert RC.eligible_ids(world, 1, "granary", sim=sim) == [101, 102, 103, 104, 105, 110, 111]
    assert RC.eligible_ids(world, 0, "woodcut", sim=sim, priority=[3]) == [3, 1, 2]
    with pytest.raises(ValueError, match="unknown recovery crew kind"):
        RC.eligible_ids(world, 0, "mining", sim=sim)
    # Without --recovery-crews veterans of other occupations are not admitted.
    RC.set_recovery_crews_enabled(world, False)
    assert 120 not in RC.eligible_ids(world, 1, "woodcut", sim=sim)


# ---------------------------------------------------------------------------
# RS2 correction: no granary project without farm labour (``no_people``)
# ---------------------------------------------------------------------------

def test_no_granary_project_opens_in_a_region_without_farm_labour():
    """Regression (D3): RS2 opened and kept granary projects where the native
    farm labour was 0, so they stalled ``no_labor`` forever. Correction: no
    project opens there (unmet ``no_people``); it opens once farmers live there."""
    world = _world(granary=(1.0, 1.0, 0.5), crews=None)
    people = {a: v for a, v in _people().items() if v[0] != 2}            # region 2 is empty
    sim = _Sim(people)
    _open(world, sim)
    assert _rs2(world).projects == []
    assert [(u.kind, u.asset, u.reason) for u in _rs2(world).unmet] == [("granary", 2, "no_people")]
    assert _rs2(world).counters["unmet_no_people"] == 1
    sim.people[200] = (2, FARMER, 12, 0)                                   # a child farmer is farm labour
    _open(world, sim)
    (p,) = _rs2(world).projects
    assert (p.kind, p.region) == ("granary", 2)


def test_an_open_granary_project_is_suspended_without_farm_labour_and_resumes():
    world = _world(granary=(1.0, 1.0, 0.5), crews=None)
    sim = _Sim(_people())
    _open(world, sim)
    (p,) = _rs2(world).projects
    gone = {a: sim.people.pop(a) for a in list(sim.people) if sim.people[a][0] == 2}
    treasury = world.civilizations[0].treasury
    timber = world.regions[2].stockpile.goods["timber"]
    batch, _econ = _turn(world, sim)
    (r,) = _rs2(world).receipts
    assert (r.status, r.reasons, r.requested, r.timber_held) == ("stalled", ["no_people"], 0.0, 0.0)
    assert batch.column("granary_work_requested").to_pylist()[2] == 0.0
    assert world.civilizations[0].treasury == treasury and world.regions[2].stockpile.goods["timber"] == timber
    assert _rs2(world).projects[0].stalls == {"no_people": 1}
    assert [h[1] for h in _rs2(world).projects[0].history][-1] == "suspended_no_people"
    # Its storage request stays suspended, and the L9 proposal asks nothing for it.
    obs = SimpleNamespace(economy=object(), turn=world.turn - 1, held={})
    world.turn -= 1
    assert RP.budget_proposal(world, 0, obs) == []
    world.turn += 1
    _turn(world, sim)                                                        # still empty: one note only
    assert [h[1] for h in _rs2(world).projects[0].history].count("suspended_no_people") == 1
    assert _rs2(world).counters["suspensions"] == 1 and _rs2(world).counters["stalled_no_people"] == 2
    sim.people.update(gone)
    _turn(world, sim)
    (r,) = _rs2(world).receipts
    assert r.status == "progress" and r.delivered == 4.0
    assert [h[1] for h in _rs2(world).projects[0].history][-1] == "resumed"
    assert _rs2(world).counters["resumptions"] == 1


def test_the_correction_needs_a_snapshot_and_otherwise_keeps_the_legacy_rule():
    world = _world(granary=(1.0, 1.0, 0.5), crews=None)
    RP.phase10_before_reserves(world, None, None, None)                    # no snapshot: unknown
    (p,) = _rs2(world).projects
    assert p.region == 2


# ---------------------------------------------------------------------------
# Switch, prerequisites, feature off
# ---------------------------------------------------------------------------

def _parse(*argv):
    from chronicler.main import _build_parser
    return _build_parser().parse_args(list(argv))


def test_prerequisites_and_modes():
    world = _world(crews=None)
    LV.configure_livelihoods(world, _parse("--recovery-crews", "--recovery-crew-mode", "unpaid"),
                             agent_mode="hybrid")
    assert _rc(world).mode == "unpaid" and RC.recovery_crews_active(world)
    LV.configure_livelihoods(world, _parse("--recovery-crews", "--recovery-crew-mode", "paid"), agent_mode="hybrid")
    assert _rc(world).mode == "paid"
    bare = generate_world(seed=42, num_regions=3, num_civs=2)
    bare.agent_mode = "hybrid"
    with pytest.raises(ValueError, match="--recovery-crews requires"):
        LV.configure_livelihoods(bare, _parse("--recovery-crews"), agent_mode="hybrid")
    with pytest.raises(ValueError, match="--recovery-crews requires"):
        LV.configure_livelihoods(_world(crews=None), _parse("--recovery-crews"), agent_mode="shadow")
    assert LV.livelihoods_arguments(_parse("--recovery-crews", "--recovery-crew-mode", "unpaid")) == \
        ["--recovery-crews", "--recovery-crew-mode=unpaid"]
    RP.set_repair_projects_enabled(world, False)
    assert not RC.recovery_crews_active(world)


def test_feature_off_has_no_state_and_rs2_keeps_its_anonymous_channel():
    a, b = _world(crews=None), _world(crews=None)
    LV.configure_livelihoods(b, _parse("--no-recovery-crews"), agent_mode="hybrid")
    assert b.livelihoods.recovery_crews is None
    for w in (a, b):
        sim = _Sim(_people())
        _open(w, sim)
        batch, _ = _turn(w, sim)
        # The anonymous channel: 4 work from 4 farmers (the child among them).
        assert batch.column("granary_work_requested").to_pylist()[0] == 4.0
    assert _rs2(a).model_dump_json() == _rs2(b).model_dump_json()
    assert "recovery_crews" not in LV.livelihoods_snapshot_fields(a)["livelihoods"]
    assert "recovery_crews" not in a.livelihoods.model_dump()
    assert "recovery_crews" not in LV.livelihoods_feature_flags(a)


def test_switching_off_mid_run_stops_naming_crews():
    world = _world()
    sim = _Sim(_people())
    _open(world, sim)
    _turn(world, sim)
    RC.set_recovery_crews_enabled(world, False)
    batch, _ = _turn(world, sim)
    assert batch.column("granary_work_requested").to_pylist()[0] == 4.0
    assert "recovery_crews" not in LV.livelihoods_snapshot_fields(world)["livelihoods"]
