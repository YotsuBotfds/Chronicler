"""RS2 repair projects without the native extension: constructed worlds and a
recording simulator stand in for the native registry, paid-work install,
wealth transfers and the storage work channel (no simulation run)."""
from __future__ import annotations

import math
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import apprenticeship as A
from chronicler import grain_storage as S
from chronicler import local_budgets as L
from chronicler import repair_projects as RP
from chronicler import veteran_reintegration as VR
from chronicler import workshops as W
from chronicler.cities_state import City, CityState
from chronicler.grain_reserves import _ensure, set_grain_reserves_enabled
from chronicler.grain_storage_state import StorageAsset
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.local_budgets_state import Commitment, LocalBudgetState
from chronicler.repair_projects_state import CivLedger, RepairProjectsState
from chronicler.workshops_state import WorkshopSite, WorkshopState
from chronicler.world_gen import generate_world


class _Sim:
    """Records the native seams RS2 uses, with the registry's all-or-none
    reservation rule, the paid-work install rules, keyed wealth transfers and
    a wealth ceiling."""

    CEILING = 100_000

    def __init__(self, people=None):
        # id -> settlement id of a living adult urban farmer
        self.people = dict(people or {})
        self.registry: list[tuple[int, int, float, int]] = []    # (id, category, fraction, turn)
        self.paid: dict[int, float] | None = None
        self.paid_turn = None
        self.receipt = None
        self.wealth: dict[int, int] = {}
        self.keys: set = set()
        self.transfers: list = []
        self.crew_calls: list = []
        self.cancelled = 0

    # crew planner: read-only without a turn; with one it reserves category 0
    def plan_workshop_crews(self, requests, enlisted, turn=None, *, priority_ids=None):
        self.crew_calls.append((list(requests), turn, list(priority_ids or [])))
        rank = {a: i for i, a in enumerate(priority_ids or [])}
        assigned = {r[0] for r in self.registry if r[3] == turn} if turn is not None else set()
        out = []
        for site, region, settlement, diverted, most in requests:
            pool = sorted((a for a, s in self.people.items() if s == settlement and a not in enlisted
                           and a not in assigned), key=lambda a: (rank.get(a, math.inf), a))
            crew = pool[:most]
            if turn is not None:
                self.reserve_work(turn, 0, [(a, diverted) for a in crew])
                assigned.update(crew)
            out.append((site, region, settlement, len(pool), 0, 0, 0, len(pool), crew, [30] * len(crew),
                        len(crew) * diverted))
        return out

    def take_craft_inputs(self):
        return None

    def reserve_work(self, turn, category, rows):
        held = {r[0] for r in self.registry if r[3] == turn}
        if any(a in held or a not in self.people for a, _ in rows):
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


# ---------------------------------------------------------------------------
# Constructed worlds
# ---------------------------------------------------------------------------

def _world(*, granary=0.5, site=None, treasury=100, timber=50.0, policy="maintain", capacity=100.0, mode=None):
    w = generate_world(seed=42, num_regions=3, num_civs=2)
    w.agent_mode = "hybrid"
    w.turn = 5
    civ = w.civilizations[0]
    civ.regions = [r.name for r in w.regions]
    civ.treasury = treasury
    other = w.civilizations[1]
    other.regions = []
    for r in w.regions:
        r.controller = civ.name
        r.stockpile.goods = {"timber": timber, "grain": 10.0}
    set_grain_reserves_enabled(w, True)
    state = _ensure(w)
    for g in state.granaries:
        g.owner, g.grain = 0, 20.0
    storage = S.enable_storage(w)
    storage.assets = [StorageAsset(capacity=capacity, condition=granary if i == 0 else 1.0, owner=0)
                      for i in range(3)]
    for rid in range(3):
        S.set_storage_policy(w, rid, policy, 4.0 if policy != "neglect" else 0.0)
    w.livelihoods = LivelihoodsState()
    if site is not None:
        w.cities = CityState(cities=[City(settlement_id=5, region=1, name="C5", founded_turn=0, founder=0,
                                          rank=1, size=10.0)])
        ws = w.livelihoods.workshops = WorkshopState(mode="operate")
        ws.sites = [WorkshopSite(site=0, region=1, settlement_id=5, city_name="C5", selected_turn=0,
                                 asset="open", construction_paid=W.CONSTRUCTION_COST, condition=site)]
        ws.next_site = 1
    RP.set_repair_projects_enabled(w, True, args=SimpleNamespace(repair_mode=mode))
    return w


def _batch(world, plan):
    n = len(world.regions)
    cols = {"region_id": pa.array(range(n), pa.uint16()),
            "craft_raw_demand": pa.array([1.0] * n, pa.float32()),
            "stockpile_timber": pa.array([r.stockpile.goods.get("timber", 0.0) for r in world.regions],
                                         pa.float32())}
    if plan is not None:
        cols["granary_work_requested"] = pa.array(plan.requests, pa.float32())
    return pa.record_batch(cols)


@pytest.fixture(autouse=True)
def _no_commitments(monkeypatch):
    monkeypatch.setattr(RP, "_commitments", lambda world, sim: getattr(sim, "commitments", {}))


def _turn(world, sim, *, labor=100.0, fail_economy=False, fail_agent=False):
    """One turn in the simulation's order: storage plan, Phase 2 prepare, a
    native economy tick (labour-limited storage work, stock write-back), storage
    and package settlement, the agent tick, Phase 10."""
    bridge = SimpleNamespace(_sim=sim)
    plan = S.prepare_storage_work(world, [10.0] * len(world.regions), commitments={})
    batch = _batch(world, plan)
    ws = world.livelihoods.workshops
    try:
        if ws is not None:
            batch = W.prepare_phase2(world, batch, bridge, None, None)
        batch = RP.prepare_phase2(world, batch, bridge, None, None)
        if fail_economy:
            raise RuntimeError("native economy failed")
        requested = batch.column("granary_work_requested").to_pylist()
        delivered = {rid: min(r, labor) for rid, r in enumerate(requested)}
        for rid, value in enumerate(batch.column("stockpile_timber").to_pylist()):
            world.regions[rid].stockpile.goods["timber"] = value      # native write-back
        econ = SimpleNamespace(granary_work_delivered=delivered, craft_output={})
        S.finish_storage_work(world, plan, [delivered[r] for r in range(len(world.regions))])
        if ws is not None:
            W.finish_phase2(world, econ, bridge, None)
        RP.finish_phase2(world, econ, bridge, None)
    except BaseException:
        if plan.status == "pending":
            S.rollback_storage_work(world, plan)
        if ws is not None:
            W.rollback_phase2(world)
        RP.rollback_phase2(world)
        raise
    if fail_agent:
        RP.rollback_agent_tick(world, bridge)
        raise RuntimeError("agent tick failed")
    sim.tick(world.turn)
    RP.after_agent_tick(world, bridge)
    RP.phase10_before_reserves(world, None, econ, bridge)
    RP.phase10(world, None, econ, bridge)
    world.turn += 1
    return batch, plan


def _state(world) -> RepairProjectsState:
    return world.livelihoods.repair_projects


def _open(world):
    RP.phase10_before_reserves(world, None, None, None)


# ---------------------------------------------------------------------------
# Granaries
# ---------------------------------------------------------------------------

def test_granary_project_is_sized_to_the_deficit_and_owns_the_storage_channel():
    world = _world(granary=0.5)
    _open(world)
    (p,) = _state(world).projects
    assert (p.kind, p.asset, p.cause, p.status) == ("granary", 0, "wear", "open")
    assert p.scope == pytest.approx(0.5 * 40) and p.opened_condition == 0.5
    treasury = world.civilizations[0].treasury
    batch, plan = _turn(world, _Sim())
    # The ordinary maintain request of the project region is suspended, the
    # others (at condition 1.0) ask nothing; the project uses the channel.
    assert plan.suspended == frozenset({0}) and plan.requests[0] == 0.0
    assert batch.column("granary_work_requested").to_pylist()[0] == 4.0
    r = _state(world).receipts[0]
    assert (r.status, r.requested, r.delivered, r.credited) == ("progress", 4.0, 4.0, 4.0)
    storage = world.grain_reserves.storage
    assert storage.receipts[0].delivered == 0.0 and storage.receipts[0].requested == 0.0
    # Storage wear then the project's pro-rata credit: 4 work of 40 per unit.
    assert storage.assets[0].condition == pytest.approx(0.5 - 0.01 + 0.1)
    assert world.civilizations[0].treasury == treasury - 8
    assert world.regions[0].stockpile.goods["timber"] == pytest.approx(50.0 - 4.0)
    (ledger,) = _state(world).ledger
    assert (ledger.charged, ledger.coin_cost_milli, ledger.prepaid_after_milli) == (8, 8000, 0)
    assert _state(world).projects[0].delivered == 4.0


def test_no_work_beyond_the_cap_and_completion_closes_the_project():
    world = _world(granary=0.96)
    world.livelihoods.repair_projects.counters.clear()
    RP.OPEN_BELOW, old = 0.97, RP.OPEN_BELOW
    try:
        _open(world)
    finally:
        RP.OPEN_BELOW = old
    (p,) = _state(world).projects
    assert p.scope == pytest.approx(0.04 * 40)
    _turn(world, _Sim())
    r = _state(world).receipts[0]
    assert r.requested == pytest.approx(1.6, rel=1e-6) and r.delivered == r.requested
    assert _state(world).projects == [] and _state(world).closed[-1].status == "completed"
    # Wear was taken first, so the credited deficit lands at most on the cap.
    assert world.grain_reserves.storage.assets[0].condition <= 1.0
    assert "cap_waste" not in _state(world).counters


def test_one_whole_unit_charge_per_civ_and_the_remainder_is_prepaid():
    world = _world(granary=0.5)
    storage = world.grain_reserves.storage
    for a in storage.assets:
        a.condition = 0.5
    _open(world)
    assert len(_state(world).projects) == 3
    sim = _Sim()
    treasury = world.civilizations[0].treasury
    _turn(world, sim, labor=1.3)      # 1.3 work each: 2.6 coins per region
    (ledger,) = _state(world).ledger
    assert ledger.coin_cost_milli == 3 * 2600 and ledger.charged == 8 and ledger.prepaid_after_milli == 200
    assert treasury - world.civilizations[0].treasury == 8         # per region: 3 x ceil(2.6) = 9
    assert all("no_labor" in r.reasons for r in _state(world).receipts)
    RP.check_ledger(ledger)
    assert _state(world).prepaid == {0: 200}
    # The prepaid remainder pays toward the next turn: 7.8 coins cost 7.6 more.
    _turn(world, sim, labor=1.3)
    (ledger,) = _state(world).ledger
    assert (ledger.prepaid_before_milli, ledger.charged, ledger.prepaid_after_milli) == (200, 8, 400)
    assert treasury - world.civilizations[0].treasury == 16
    # Over many turns the charge never exceeds the cost by a whole unit.
    for _ in range(4):
        _turn(world, sim, labor=1.3)
    cost = _state(world).counters["coin_cost_milli"]
    assert cost == 6 * 7800 and _state(world).prepaid == {0: 200}
    assert 0 <= (treasury - world.civilizations[0].treasury) * 1000 - cost < 1000
    # A civ left without regions loses its prepaid remainder (written off).
    world.civilizations[0].regions = []
    RP.phase10_before_reserves(world, None, None, None)
    assert _state(world).prepaid == {} and _state(world).counters["prepaid_written_off_milli"] > 0


def test_zero_capacity_granaries_get_no_project_and_are_unmet():
    world = _world(granary=0.2, capacity=0.0)
    _open(world)
    assert _state(world).projects == []
    assert [(u.kind, u.asset, u.reason) for u in _state(world).unmet] == [("granary", 0, "zero_capacity")]


def test_stalls_record_their_reasons():
    world = _world(granary=0.5, timber=0.0)
    _open(world)
    _turn(world, _Sim())
    r = _state(world).receipts[0]
    assert r.status == "stalled" and r.reasons == ["no_timber"] and r.delivered == 0.0
    assert _state(world).projects[0].stalls == {"no_timber": 1}
    world.regions[0].stockpile.goods["timber"] = 50.0
    world.civilizations[0].treasury = 0
    _turn(world, _Sim())
    r = _state(world).receipts[0]
    assert r.status == "stalled" and r.reasons == ["no_coins"]
    world.civilizations[0].treasury = 100
    _turn(world, _Sim(), labor=0.0)
    r = _state(world).receipts[0]
    assert r.status == "stalled" and r.reasons == ["no_labor"] and r.timber_returned == r.timber_held
    assert world.regions[0].stockpile.goods["timber"] == pytest.approx(50.0)
    assert _state(world).ledger[0].charged == 0


def test_neglect_policy_still_gets_projects_and_maintain_resumes_after_completion():
    world = _world(granary=0.7, policy="neglect")
    _open(world)
    assert _state(world).projects[0].scope == pytest.approx(12.0)
    for _ in range(3):
        _turn(world, _Sim())
    assert _state(world).projects == [] and _state(world).closed[-1].status == "completed"
    S.set_storage_policy(world, 0, "maintain", 4.0)
    _, plan = _turn(world, _Sim())
    assert plan.suspended == frozenset() and plan.requests[0] == 4.0


# ---------------------------------------------------------------------------
# Workshops
# ---------------------------------------------------------------------------

def _people(n=6, settlement=5, first=100):
    return {first + i: settlement for i in range(n)}


def test_workshop_crew_is_reserved_paid_by_id_and_never_also_crew():
    world = _world(granary=1.0, site=0.4)
    assert RP.legacy_workshop_repair_allowed(world) is False
    assert W._bill(world.livelihoods.workshops.sites[0], world) == {"upkeep": W.UPKEEP}
    _open(world)
    (p,) = _state(world).projects
    assert (p.kind, p.asset, p.settlement_id) == ("workshop", 0, 5)
    assert p.scope == pytest.approx(0.6 * RP.WORKSHOP_WORK_PER_CONDITION)
    sim = _Sim(_people())
    treasury = world.civilizations[0].treasury
    _turn(world, sim)
    r = _state(world).receipts[0]
    d = 1.0 - 0.8
    assert r.crew == [100, 101, 102, 103] and r.share == pytest.approx(d) and r.rate == RP.UNQUALIFIED_RATE
    assert "unqualified" in r.reasons
    # The repair crew was reserved before the L1 planner: it took the others.
    crew_rows = world.livelihoods.workshops.frame[0].crew
    assert set(crew_rows).isdisjoint(r.crew) and crew_rows == [104, 105]
    # Wages by stable id under purpose 3, the same share withheld from income.
    (turn, purpose, batch, rows) = sim.transfers[0]
    assert purpose == RP.PURPOSE_REPAIR_WAGE and rows == [(a, 100) for a in r.crew]
    assert r.income_replaced == pytest.approx(sum(2.0 * d for _ in r.crew))
    work = 4 * d * RP.UNQUALIFIED_RATE
    assert r.delivered == pytest.approx(work) and r.timber_used == pytest.approx(work)
    site = world.livelihoods.workshops.sites[0]
    assert site.condition == pytest.approx(0.4 + work / RP.WORKSHOP_WORK_PER_CONDITION)
    (ledger,) = _state(world).ledger
    assert (ledger.wages_applied_milli, ledger.charged, ledger.prepaid_after_milli) == (400, 1, 600)
    assert treasury - world.civilizations[0].treasury == 1 + W.UPKEEP     # repair + L1 upkeep
    # No lump repair was billed and the shut site did not operate.
    receipt = world.livelihoods.workshops.frame[0]
    assert "repair" not in receipt.paid and receipt.allocated == 0.0


@pytest.mark.parametrize("residue", ["1e-8 timber", "a tenth of a worker-turn"])
def test_a_timber_residue_too_small_for_one_turn_hires_nobody(residue):
    """Review C 2026-11-05 (major): a 1e-8 timber stock passed the EPS check, so
    a named repairer was reserved, paid a full wage and taken off the L1 crew
    for 1e-8 work. A worker is hired only for a whole turn the timber supports
    (or the project's whole remaining work)."""
    d = 1.0 - 0.8
    per = d * RP.UNQUALIFIED_RATE
    timber = 1e-8 if residue == "1e-8 timber" else 0.1 * per * RP.WORKSHOP_TIMBER_PER_WORK
    world = _world(granary=1.0, site=0.4, timber=timber)
    _open(world)
    sim = _Sim(_people())
    _turn(world, sim)
    r = _state(world).receipts[0]
    assert r.crew == [] and "no_timber" in r.reasons and r.wages_milli == 0
    assert not sim.transfers and r.delivered == 0.0
    # Nobody was taken off the L1 crew for it.
    crew = world.livelihoods.workshops.frame[0].crew
    assert crew == sorted(crew) and crew[0] == 100
    # The L9 proposal asks for nothing it cannot deliver (no granary needs work here).
    obs = SimpleNamespace(economy=object(), turn=world.turn, held={})
    assert RP.budget_proposal(world, 0, obs) == []


def test_timber_workers_hire_whole_turns_and_a_last_one_only_for_half_a_turn():
    per = 0.1
    assert RP._timber_workers(1.0, 0.25, per) == 3               # two whole turns and a half
    assert RP._timber_workers(1.0, 0.249, per) == 2              # 2.49 turns: the last is under half
    assert RP._timber_workers(0.05, 1.0, per) == 1               # the remaining work alone
    assert RP._timber_workers(1.0, 1e-8, per) == 0 and RP._timber_workers(1.0, 0.04, per) == 0
    assert RP._timber_workers(1.0, 0.05, per) == 1               # exactly half a turn


def test_qualified_people_and_veterans_come_first_and_veterans_are_noted(monkeypatch):
    world = _world(granary=1.0, site=0.4)
    A.set_apprenticeship_enabled(world, True, args=None)
    VR.set_veteran_reintegration_enabled(world, True, args=None)
    # Only the cross-lane seams (qualified_ids, priority_ids, note_outcome) are under
    # test: RS1's and RS3's own hooks need the native registry and snapshot
    # (tests/test_apprenticeship*.py, tests/test_veteran_reintegration*.py).
    monkeypatch.setattr(A, "before_crews", lambda w, s, requests: None)
    monkeypatch.setattr(A, "crew_priority_ids", lambda w: [])
    monkeypatch.setattr(A, "crew_maintenance", lambda w, site, row: 0.0)
    monkeypatch.setattr(A, "operating_wear", lambda w, site: 0.0)
    for module in (A, VR):
        for hook in ("prepare_phase2", "finish_phase2", "rollback_phase2", "after_agent_tick",
                     "rollback_agent_tick", "phase10", "on_pool_reset"):
            if hasattr(module, hook):
                monkeypatch.delattr(module, hook)
    monkeypatch.setattr(A, "qualified_ids", lambda w, region: [104, 105] if region == 1 else [])
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: [103, 105] if region == 1 else [])
    monkeypatch.setattr(VR, "open_record_ids", lambda w: frozenset({103, 105}))
    noted = []
    monkeypatch.setattr(VR, "note_outcome", lambda w, aid, kind, *, turn, detail=None: noted.append((aid, kind, turn)))
    _open(world)
    sim = _Sim(_people())
    _turn(world, sim)
    r = _state(world).receipts[0]
    # Qualified veterans, the qualified, then veterans, then the rest by id.
    assert sim.crew_calls[0][2] == [105, 104, 103]
    assert r.crew[:3] == [105, 104, 103] and r.rate == 1.0 and "unqualified" not in r.reasons
    assert r.qualified == [105, 104] and r.veterans == [105, 103]
    assert noted == [(105, "placed:repair", 5), (103, "placed:repair", 5)]


def test_a_veteran_on_a_repair_crew_is_noted_although_priority_offered_nobody(monkeypatch):
    """Review C 2026-11-05 (major): veterans were noted only from priority_ids,
    which is empty in RS3's record_only control (and for ineligible open
    records), so the control never recorded placed:repair. Every crew member
    holding an open veteran record is noted, in either mode."""
    world = _world(granary=1.0, site=0.4)
    VR.set_veteran_reintegration_enabled(world, True, args=None)
    for module in (VR,):
        for hook in ("prepare_phase2", "finish_phase2", "rollback_phase2", "rollback_agent_tick", "phase10",
                     "on_pool_reset"):
            if hasattr(module, hook):
                monkeypatch.delattr(module, hook)
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: [])            # record_only: nobody offered
    monkeypatch.setattr(VR, "open_record_ids", lambda w: frozenset({101}))
    noted = []
    monkeypatch.setattr(VR, "note_outcome", lambda w, aid, kind, *, turn, detail=None: noted.append((aid, kind)))
    _open(world)
    _turn(world, _Sim(_people()))
    r = _state(world).receipts[0]
    assert 101 in r.crew and r.veterans == [101]
    assert noted == [(101, "placed:repair")] and _state(world).counters["veterans_placed"] == 1


def test_l9_promises_no_crew_work_at_a_site_shut_for_repair():
    """Review C 2026-11-05 (major): with RS2 owning repair, a built site below
    the operating condition is billed upkeep only and puts nobody to work, yet
    L9's workshop proposal still claimed its whole crew work as patrician relief
    (settled kept with nothing delivered, and RS2's repairs proposal claimed the
    same idle work). Its stake is now zero, as in cost-only mode."""
    from chronicler.local_budgets import _Workshop
    world = _world(granary=1.0, site=0.4)
    _open(world)
    _turn(world, _Sim(_people()))
    ws = world.livelihoods.workshops
    receipt = ws.frame[0]
    assert receipt.work_available > 0 and receipt.allocated == 0      # crew present, shut for repair
    (prop,) = _Workshop().proposals(world, 0, SimpleNamespace(turn=ws.frame_turn))
    assert prop["cost"] == W.UPKEEP and prop["expected"] == 0.0 and prop["relief"] == {"patricians": 0.0}


def test_cost_only_reserves_pays_and_uses_timber_identically_without_condition():
    a, b = _world(site=0.4), _world(site=0.4, mode="cost_only")
    for w in (a, b):
        _open(w)
        _turn(w, _Sim(_people()))
    ra, rb = _state(a), _state(b)
    assert [x.model_dump(exclude={"credited", "condition_after"}) for x in ra.receipts] == \
           [x.model_dump(exclude={"credited", "condition_after"}) for x in rb.receipts]
    assert ra.ledger == rb.ledger
    assert a.civilizations[0].treasury == b.civilizations[0].treasury
    assert [r.stockpile.goods for r in a.regions] == [r.stockpile.goods for r in b.regions]
    assert all(x.credited == 0.0 for x in rb.receipts)
    assert b.livelihoods.workshops.sites[0].condition == 0.4
    assert b.grain_reserves.storage.assets[0].condition == pytest.approx(0.49)
    assert a.livelihoods.workshops.sites[0].condition > 0.4


def test_no_crew_when_nobody_is_eligible_and_registry_holders_are_skipped():
    world = _world(granary=1.0, site=0.4)
    _open(world)
    sim = _Sim(_people(3))
    sim.registry = [(100, 2, 0.2, world.turn)]          # an RS1 apprentice seat
    _turn(world, sim)
    assert _state(world).receipts[0].crew == [101, 102]
    sim = _Sim({})
    _turn(world, sim)
    r = _state(world).receipts[0]
    assert r.status == "stalled" and "no_labor" in r.reasons and sim.transfers == []


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_conquest_inherits_and_a_lost_controller_or_asset_abandons():
    world = _world(granary=0.5, site=0.4)
    _open(world)
    assert len(_state(world).projects) == 2
    _turn(world, _Sim(_people()))
    winner = world.civilizations[1]
    winner.regions = [r.name for r in world.regions]
    winner.treasury = 100
    for r in world.regions:
        r.controller = winner.name
    _open(world)
    assert all(p.controller == 1 for p in _state(world).projects)
    assert any(h[1] == "controller" for h in _state(world).projects[0].history)
    _turn(world, _Sim(_people()))
    assert {r.payer for r in _state(world).receipts} == {1}
    assert _state(world).ledger[0].civ == 1
    world.regions[0].controller = None
    _open(world)
    assert [(p.kind, p.closed_reason) for p in _state(world).closed] == [("granary", "no_controller")]
    world.cities.cities = []                               # the city fell
    _turn(world, _Sim(_people()))
    assert _state(world).closed[-1].closed_reason == "asset_closed"
    assert _state(world).projects == []


def test_switching_off_abandons_and_pool_reset_clears_crews():
    world = _world(granary=1.0, site=0.4)
    _open(world)
    _turn(world, _Sim(_people()))
    p = _state(world).projects[0]
    assert p.last_crew == [100, 101, 102, 103]
    RP.on_pool_reset(world)
    assert p.last_crew == [] and p.history[-1][1] == "pool_reset"
    assert _state(world).prepaid == {0: 600}
    RP.set_repair_projects_enabled(world, False, args=None)
    assert _state(world).projects == [] and _state(world).closed[-1].closed_reason == "switched_off"
    assert _state(world).prepaid == {} and _state(world).counters["prepaid_written_off_milli"] == 600
    assert not RP.repair_projects_active(world) and RP.legacy_workshop_repair_allowed(world)
    assert S._repair_suspended(world) == frozenset()


def test_failed_economy_tick_charges_nothing_and_returns_timber():
    world = _world(granary=0.5, site=0.4)
    _open(world)
    before = (world.civilizations[0].treasury, [dict(r.stockpile.goods) for r in world.regions],
              _state(world).model_dump_json())
    sim = _Sim(_people())
    with pytest.raises(RuntimeError, match="native economy failed"):
        _turn(world, sim, fail_economy=True)
    assert world.civilizations[0].treasury == before[0]
    assert [dict(r.stockpile.goods) for r in world.regions] == before[1]
    assert _state(world).model_dump_json() == before[2] and _state(world)._turn is None
    assert sim.transfers == [] and sim.paid is None


def test_failed_agent_tick_disarms_the_paid_share():
    world = _world(granary=1.0, site=0.4)
    _open(world)
    sim = _Sim(_people())
    with pytest.raises(RuntimeError, match="agent tick failed"):
        _turn(world, sim, fail_agent=True)
    assert sim.paid is None and sim.cancelled == 1


def test_a_turn_settles_once():
    world = _world(granary=0.5)
    _open(world)
    sim = _Sim()
    _turn(world, sim)
    world.turn -= 1                                        # replaying the settled turn
    with pytest.raises(RuntimeError, match="already settled"):
        RP.prepare_phase2(world, _batch(world, None), SimpleNamespace(_sim=sim), None, None)
    world.turn += 1
    t = RP._Turn(world.turn, sim)
    t.prepared = t.finished = True
    _state(world)._turn = t
    with pytest.raises(RuntimeError, match="missing"):
        RP.finish_phase2(world, SimpleNamespace(granary_work_delivered={}), SimpleNamespace(_sim=sim), None)


def test_closure_check_refuses_unbalanced_books():
    good = CivLedger(turn=1, civ=0, projects=1, work_delivered=1.0, timber_used=1.0, coin_cost_milli=2000,
                     wages_due_milli=300, wages_applied_milli=200, wage_residual_milli=100, charged=2,
                     prepaid_before_milli=500, prepaid_after_milli=300)
    RP.check_ledger(good)
    for change in ({"charged": 3}, {"prepaid_after_milli": 1300, "charged": 3}, {"wage_residual_milli": 0},
                   {"prepaid_before_milli": 1500, "charged": 1}):
        with pytest.raises(RuntimeError, match="do not close"):
            RP.check_ledger(good.model_copy(update=change))


def test_a_wage_beyond_the_ceiling_is_not_charged():
    world = _world(granary=1.0, site=0.4)
    _open(world)
    sim = _Sim(_people())
    sim.wealth = {100: _Sim.CEILING - 30}
    _turn(world, sim)
    r = _state(world).receipts[0]
    assert r.wages_milli == 330 and r.wage_residual_milli == 70
    (ledger,) = _state(world).ledger
    assert (ledger.wages_applied_milli, ledger.charged, ledger.prepaid_after_milli) == (330, 1, 670)


# ---------------------------------------------------------------------------
# War damage
# ---------------------------------------------------------------------------

def test_war_damage_is_recorded_once_per_asset_and_turn_with_the_war_identity():
    world = _world(granary=1.0, site=1.0)
    attacker, defender = world.civilizations[1].name, world.civilizations[0].name
    from chronicler.politics import war_key
    key = war_key(attacker, defender)
    world.war_start_turns[key] = 3
    RP.region_conquered(world, world.regions[1], attacker, defender)
    RP.city_sacked(world, 5, 1, attacker, defender)          # same turn: no second record
    damages = _state(world).damages
    assert [(d.kind, d.asset, d.event, d.war_key, d.war_start_turn) for d in damages] == [
        ("granary", 1, "conquest", key, 3), ("workshop", 0, "conquest", key, 3)]
    assert world.livelihoods.workshops.sites[0].condition == pytest.approx(1.0 - RP.WAR_DAMAGE)
    assert world.grain_reserves.storage.assets[1].condition == pytest.approx(1.0 - RP.WAR_DAMAGE)
    _open(world)                                           # any deficit with a record: reconstruction
    projects = {(p.kind, p.asset): p for p in _state(world).projects}
    assert projects[("workshop", 0)].cause == "war" and projects[("workshop", 0)].war_key == key
    assert projects[("granary", 1)].damages == [damages[0].did]
    # A later sack extends the open project by the new deficit.
    world.turn += 1
    scope = projects[("workshop", 0)].scope
    RP.city_sacked(world, 5, 1, attacker, defender)
    assert projects[("workshop", 0)].scope == pytest.approx(scope + RP.WAR_DAMAGE * 8)


def test_seizure_damages_the_granary_with_the_occupation_war():
    from chronicler.models import Occupation, WarRecord
    world = _world(granary=1.0)
    region = world.regions[2]
    world.war_state.wars.append(WarRecord(war_key="A:B", attacker="A", defender="B", start_turn=2))
    world.war_state.occupations.append(Occupation(region=region.name, owner="B", occupier="A",
                                                  war_key="A:B", since_turn=4))
    RP.granary_seized(world, region, 1.0)
    (d,) = _state(world).damages
    assert (d.kind, d.asset, d.event, d.war_key, d.war_start_turn) == ("granary", 2, "seizure", "A:B", 2)


def test_a_requisition_that_takes_no_grain_is_no_seizure():
    """Review C 2026-11-05 (major): every siege turn damaged the granary even
    when it held no grain (four turns took an empty granary from 1.0 to 0.0).
    Only a requisition that actually takes grain records seizure damage."""
    from chronicler.war.occupation import _requisition
    world = _world(granary=1.0)
    granaries, assets = world.grain_reserves.granaries, world.grain_reserves.storage.assets
    granaries[0].grain = 0.0
    for _ in range(4):
        _requisition(world.regions[0], 0.75, world)
    assert _state(world).damages == [] and assets[0].condition == 1.0
    _requisition(world.regions[1], 0.75, world)                    # 20 grain: 5 taken
    (d,) = _state(world).damages
    assert (d.asset, d.event) == (1, "seizure") and assets[1].condition == pytest.approx(1.0 - RP.WAR_DAMAGE)


def test_the_ablation_key_scales_or_disables_damage_and_inactive_is_a_no_op():
    world = _world(granary=1.0)
    world.tuning_overrides = {RP.TUNING_WAR_DAMAGE: 0.0}
    RP.granary_seized(world, world.regions[0], 1.0)
    assert _state(world).damages == [] and world.grain_reserves.storage.assets[0].condition == 1.0
    world.tuning_overrides = {RP.TUNING_WAR_DAMAGE: 2.0}
    RP.granary_seized(world, world.regions[0], 1.0)
    assert world.grain_reserves.storage.assets[0].condition == pytest.approx(0.5)
    world.tuning_overrides = {RP.TUNING_WAR_DAMAGE: -1.0}
    with pytest.raises(ValueError):
        RP.granary_seized(world, world.regions[1], 1.0)
    world.tuning_overrides = {}
    RP.set_repair_projects_enabled(world, False, args=None)
    RP.granary_seized(world, world.regions[1], 1.0)
    assert world.grain_reserves.storage.assets[1].condition == 1.0


# ---------------------------------------------------------------------------
# L9 envelope, state, snapshot
# ---------------------------------------------------------------------------

def _budgets(world, amount):
    world.livelihoods.local_budgets = state = LocalBudgetState()
    if amount is not None:
        state.open = [Commitment(cid=0, civ=0, service="repairs", pid=0, decided_turn=world.turn - 1,
                                 for_turn=world.turn, claims=["repairs:0"], amount=amount, unit="work",
                                 expected=4.0)]
    return state


def test_spending_stays_within_the_repairs_envelope():
    world = _world(granary=0.5, site=0.4)
    _open(world)
    _budgets(world, None)
    _turn(world, _Sim(_people()))
    assert all(r.status == "stalled" and "no_envelope" in r.reasons for r in _state(world).receipts)
    assert _state(world).ledger[0].charged == 0
    _budgets(world, 3)
    _turn(world, _Sim(_people()))
    (ledger,) = _state(world).ledger
    assert ledger.envelope == 3 and ledger.charged <= 3
    granary = next(r for r in _state(world).receipts if r.kind == "granary")
    assert "no_envelope" in granary.reasons and granary.delivered > 0


def test_budget_proposal_and_settlement():
    world = _world(granary=0.5)
    _open(world)
    obs = SimpleNamespace(economy=object(), turn=world.turn, held={})
    _turn(world, _Sim())
    world.turn -= 1
    world.grain_reserves.storage.receipt_turn = obs.turn = world.turn
    (prop,) = RP.budget_proposal(world, 0, obs)
    assert prop["service"] == "repairs" and prop["claims"] == ["repairs:0"] and prop["divisible"]
    assert prop["expected"] == pytest.approx(4.0) and prop["cost"] == 8 and prop["relief"]["commons"] > 0
    assert RP.budget_proposal(world, 1, obs) == []
    world.turn += 1
    _budgets(world, 8)
    sim = _Sim()
    bridge = SimpleNamespace(_sim=sim)
    plan = S.prepare_storage_work(world, [10.0] * 3, commitments={})
    batch = RP.prepare_phase2(world, _batch(world, plan), bridge, None, None)
    req = batch.column("granary_work_requested").to_pylist()
    econ = SimpleNamespace(granary_work_delivered={i: v for i, v in enumerate(req)})
    S.finish_storage_work(world, plan, req)
    RP.finish_phase2(world, econ, bridge, None)
    c = world.livelihoods.local_budgets.open[0]
    out = RP.budget_settlement(world, c, SimpleNamespace(economy=econ))
    assert out["outcome"] == "kept" and out["spent"] == 8 and out["spent"] <= c.amount
    RP.rollback_phase2(world)
    assert L.REPAIRS.services == ("repairs",) and "chronicler.local_budgets:REPAIRS" in L.PROVIDERS


def test_granary_under_a_project_takes_no_storage_envelope():
    world = _world(granary=0.5)
    _open(world)
    assert L._repair_regions(world) == frozenset({0})
    RP.set_repair_projects_enabled(world, False, args=None)
    assert L._repair_regions(world) == frozenset()


def test_snapshot_is_dated_and_unknown_without_a_phase2():
    world = _world(granary=0.5, site=0.4)
    _open(world)
    _turn(world, _Sim(_people()))
    snap = RP.snapshot_summary(world)
    assert snap["stage"] == "RS2" and snap["source_turn"] == world.turn - 1
    assert len(snap["receipts"]) == 2 and snap["ledger"] and snap["suspended"] == [0]
    RP.phase10_before_reserves(world, None, None, None)
    RP.phase10(world, None, None, None)                    # a turn without Phase 2
    world.turn += 1
    snap = RP.snapshot_summary(world)
    assert snap["receipts"] is None and snap["ledger"] is None and snap["unmet"] == []
    world.turn += 1
    snap = RP.snapshot_summary(world)
    assert snap["receipts"] is None and snap["unmet"] is None and snap["suspended"] is None


def test_state_round_trips_and_drops_the_turn_in_flight():
    world = _world(granary=0.5, site=0.4)
    _open(world)
    _turn(world, _Sim(_people()))
    state = _state(world)
    text = state.model_dump_json()
    assert RepairProjectsState.model_validate_json(text).model_dump_json() == text
    state._turn = RP._Turn(world.turn, object())
    back = pickle.loads(pickle.dumps(state))
    assert back._turn is None and back.model_dump_json() == text
    # An RS0 pickle (switch, mode and counters only) restores with defaults.
    raw = RepairProjectsState(mode="cost_only", counters={"opened": 2}).__getstate__()
    for name in ("next_pid", "projects", "closed", "damages", "frame_turn", "receipts", "ledger",
                 "unmet", "suspended", "last_settled_turn", "next_did"):
        raw["__dict__"].pop(name)
    raw["__pydantic_private__"] = None
    old = RepairProjectsState.__new__(RepairProjectsState)
    old.__setstate__(raw)
    assert old.projects == [] and old._turn is None and old.mode == "cost_only"


def test_feature_off_storage_planning_is_unchanged():
    a, b = _world(granary=0.5), _world(granary=0.5)
    b.livelihoods.repair_projects = None
    a.livelihoods.repair_projects.enabled = False
    pa_, pb = (S.prepare_storage_work(w, [10.0] * 3, commitments={}) for w in (a, b))
    assert pa_.requests == pb.requests and pa_.suspended == pb.suspended == frozenset()
    assert W._pending_storage_bills(a) == W._pending_storage_bills(b)


def test_workshops_outside_operate_mode_keep_the_lump_and_get_no_projects():
    world = _world(granary=0.5, site=0.4)
    world.livelihoods.workshops.mode = "cost_only"
    assert RP.repair_projects_active(world) and RP.legacy_workshop_repair_allowed(world)
    assert "repair" in W._bill(world.livelihoods.workshops.sites[0], world)
    _open(world)
    assert [(p.kind, p.asset) for p in _state(world).projects] == [("granary", 0)]
    sim = _Sim(_people())
    _turn(world, sim)
    assert all(r.kind == "granary" for r in _state(world).receipts) and sim.transfers == []
    assert world.livelihoods.workshops.sites[0].condition == 1.0       # the L1 lump, as before
