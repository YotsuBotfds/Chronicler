"""C2 bounded epidemic care capacity (``--epidemic-care``) without the native
extension: constructed worlds and a recording simulator stand in for the
native work registry, paid-work install, keyed wealth transfers (with a
wealth ceiling) and the agent snapshot. Covers the dated capacity, the one
floor with practised medicine, the carers' selection and exclusions, the
payment seam's prepaid treasury rule, the L9 provider, configuration and
refusals, the snapshot record and the C3 invariants."""
from __future__ import annotations

import ast
import math
import pickle
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import epidemic_care as EC
from chronicler import epidemiology as EP
from chronicler import labour_reservations as LR
from chronicler import livelihoods as LV
from chronicler import local_budgets as LB
from chronicler import money
from chronicler import recovery_crews as RC
from chronicler.cities_state import City, CityState
from chronicler.contact_ledger import set_contact_ledger_enabled
from chronicler.epidemic_care_state import COUNTERS, CareCapacity, EpidemicCareState
from chronicler.epidemiology import EpidemicState, RegionInfection, set_epidemiology_enabled
from chronicler.grain_reserves import set_grain_reserves_enabled
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.local_budgets_state import Commitment
from chronicler.world_gen import generate_world

SRC = Path(EC.__file__).resolve().parent
FARMER, SOLDIER, MERCHANT = 0, 1, 2
CITY = 5          # a rank-1 city of region 1: urban farmers farm 0.8 of their turn


class _Sim:
    """The native seams C2 uses: the registry's all-or-none rule (also against
    rural health work held natively), paid-work install, keyed wealth
    transfers with a wealth ceiling (milli-units), trips and the snapshot."""

    CEILING = 100_000

    def __init__(self, people):
        self.people = dict(people)          # id -> (region, occupation, age, settlement id)
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
                                "settlement_id": col(3, pa.uint16()),
                                "wealth": pa.array([self.wealth.get(a, 0) / 1000 for a in ids], pa.float32())})

    def trip_agent_ids(self):
        return sorted(self.trips)

    def reserve_work(self, turn, category, rows):
        held = {r[0] for r in self.registry if r[3] == turn} | self.health
        if any(a in held for a, _ in rows):
            raise ValueError("agent already holds work this turn")
        if any(a not in self.people for a, _ in rows):
            raise ValueError("work reservation names no living agent")
        if category not in (0, 1, 2, 3):
            raise ValueError("unknown work reservation category")
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
            if a in paid or share > held.get(a, 0.0) + 1e-9:
                raise ValueError("bad paid share")
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

    @staticmethod
    def wealth_transfer_purposes():
        return list(money.NATIVE_PURPOSES)

    def transfer_wealth(self, turn, purpose, batch, rows):
        key = (turn, purpose, batch)
        if key in self.keys:
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        self.keys.add(key)
        out = []
        for aid, amount in rows:
            if aid not in self.people:
                out.append((aid, amount, 0, amount, 2))
                continue
            got = min(amount, self.CEILING - self.wealth.get(aid, 0))
            self.wealth[aid] = self.wealth.get(aid, 0) + got
            out.append((aid, amount, got, amount - got, 0 if got == amount else 1))
        self.transfers.append((turn, purpose, batch, list(rows)))
        return out

    def tick(self, turn):
        if self.paid is not None:
            self.receipt = (turn, [(a, s, 0.3, 0.3 * s) for a, s in sorted(self.paid.items())])
        self.paid = None
        self.registry = []


class _Bridge:
    def __init__(self, sim):
        self._sim = sim


def _people(extra=None):
    """Region 0: rural adult farmers 1-6, a child farmer 7, a merchant 8, a
    soldier 9. Region 1 (city 5): urban farmers 100-103, rural farmers
    110-111. Region 2: rural farmers 200-201."""
    people = {a: (0, FARMER, 30, 0) for a in range(1, 7)}
    people.update({7: (0, FARMER, 12, 0), 8: (0, MERCHANT, 30, 0), 9: (0, SOLDIER, 30, 0)})
    people.update({a: (1, FARMER, 30, CITY) for a in range(100, 104)})
    people.update({110: (1, FARMER, 30, 0), 111: (1, FARMER, 30, 0)})
    people.update({200: (2, FARMER, 30, 0), 201: (2, FARMER, 30, 0)})
    people.update(extra or {})
    return people


def _world(*, mode="care", treasury=100, techniques=False):
    w = generate_world(seed=42, num_regions=3, num_civs=2)
    w.agent_mode = "hybrid"
    w.turn = 5
    civ, other = w.civilizations[0], w.civilizations[1]
    civ.regions = [r.name for r in w.regions[:2]]
    other.regions = [w.regions[2].name]
    civ.treasury = other.treasury = treasury
    for r in w.regions[:2]:
        r.controller = civ.name
    w.regions[2].controller = other.name
    for r in w.regions:
        r.population = 200
    set_grain_reserves_enabled(w, True)
    set_epidemiology_enabled(w, True)
    set_contact_ledger_enabled(w, True)
    if not techniques:
        w.techniques = None
    w.cities = CityState(cities=[City(settlement_id=CITY, region=1, name="C5", founded_turn=0, founder=0,
                                      rank=1, size=10.0)])
    w.livelihoods = LivelihoodsState()
    LB.set_local_budgets_enabled(w, True, args=SimpleNamespace(local_budget_mode=None))
    EC.set_epidemic_care_enabled(w, True, args=SimpleNamespace(epidemic_care_mode=mode))
    return w


def _outbreak(w, region, *, n=200, burden=0.05, pathogen=1, reported=True, i=0.04, s=0.8):
    w.epidemics.rows.append(RegionInfection(region=region, pathogen=pathogen, n=n, s=s, e=0.02, i=i,
                                            r=1.0 - s - 0.02 - i, burden=burden, cases=12.0, reported=reported))
    w.epidemics.rows.sort(key=lambda r: (r.region, r.pathogen))


def _envelope(w, region, amount, *, civ=0, cid=None):
    """One civ's care envelope for this turn (one region or a list of them)."""
    st = w.livelihoods.local_budgets
    cid = st.next_cid if cid is None else cid
    st.next_cid = max(st.next_cid, cid + 1)
    regions = list(region) if isinstance(region, (list, tuple)) else [region]
    st.open.append(Commitment(cid=cid, civ=civ, service=EC.SERVICE, pid=0, decided_turn=w.turn - 1, for_turn=w.turn,
                              recipients=regions, claims=[f"{EC.SERVICE}:{civ}"], amount=amount,
                              unit="care_time", expected=amount / 0.5))
    return cid


def _batch(w, sim):
    n = len(w.regions)
    return pa.record_batch({"region_id": pa.array(range(n), pa.uint16()),
                            "farm_labor_factor": pa.array([1.0] * n, pa.float32())})


def _phase2(w, sim, *, acc=None):
    bridge = _Bridge(sim)
    batch = EC.prepare_phase2(w, _batch(w, sim), bridge, sim.get_snapshot(), acc)
    EC.finish_phase2(w, SimpleNamespace(), bridge, acc)
    return batch


# --- dated capacity and the case-fatality factor ------------------------------------

def test_capacity_dated_last_turn_applies_once_and_any_other_date_is_refused():
    w = _world()
    _outbreak(w, 0, burden=0.05)          # 10 infectious people
    _outbreak(w, 1, burden=0.10)          # 20
    st = w.livelihoods.epidemic_care
    st.capacity = [CareCapacity(region=0, source_turn=4, carers=1, care_time=1.0, patients=5.0),
                   CareCapacity(region=1, source_turn=4, carers=6, care_time=6.0, patients=30.0),
                   CareCapacity(region=2, source_turn=3, carers=1, care_time=1.0, patients=5.0),   # stale
                   CareCapacity(region=2, source_turn=5, carers=1, care_time=1.0, patients=5.0)]   # future
    factors = EC.care_factors(w, w.epidemics.rows)
    assert factors == pytest.approx([1.0 - 0.3 * 0.5, 1.0 - 0.3, 1.0])
    by = {a.region: a for a in st.applied}
    assert by[0].coverage == pytest.approx(0.5) and by[1].coverage == 1.0
    assert by[0].infectious == pytest.approx(10.0) and by[0].source_turn == 4
    assert sorted((r.region, r.source_turn, r.reason) for r in st.refused) == [(2, 3, "stale"), (2, 5, "future")]
    assert st.capacity == [] and st.tick_turn == 5
    assert st.counters["capacity_stale"] == 1 and st.counters["capacity_future"] == 1
    # Consumed: the next tick has nothing to apply.
    w.turn = 6
    assert EC.care_factors(w, w.epidemics.rows) is None and st.applied == [] and st.refused == []


def test_cost_only_applies_no_factor_and_records_the_one_it_would_apply():
    w = _world(mode="cost_only")
    _outbreak(w, 0, burden=0.05)
    st = w.livelihoods.epidemic_care
    st.capacity = [CareCapacity(region=0, source_turn=4, carers=2, care_time=2.0, patients=10.0)]
    assert EC.care_factors(w, w.epidemics.rows) is None
    (a,) = st.applied
    assert a.care_factor == 1.0 and a.would_be == pytest.approx(0.7) and a.combined_factor == 1.0


def test_no_infectious_people_means_no_coverage():
    w = _world()
    st = w.livelihoods.epidemic_care
    st.capacity = [CareCapacity(region=0, source_turn=4, carers=1, care_time=1.0, patients=5.0)]
    assert EC.care_factors(w, []) is None
    assert st.applied[0].coverage == 0.0 and st.applied[0].care_factor == 1.0


def test_one_combined_floor_with_practised_medicine():
    from chronicler.techniques import CFR_FLOOR
    assert EC.combine_one(0.6, 0.7) == CFR_FLOOR                      # 0.42 floored at 0.5
    assert EC.combine_one(0.9, 0.7) == pytest.approx(0.63)
    assert EC.combine_one(None, 0.7) == pytest.approx(0.7)
    assert EC.combine_one(0.83, 1.0) == 0.83                           # exactly the techniques factor
    assert EC.combine([0.6, 0.9, 0.5], [1.0, 0.7, 0.7]) == [0.6, pytest.approx(0.63), CFR_FLOOR]
    assert EC.combine_one(None, 1.0 - EC.CARE_CFR_REDUCTION) >= CFR_FLOOR   # care alone never reaches the floor


def _tick_expected(w, monkeypatch):
    got = {}
    real = EP._apply_deaths

    def capture(world, state, rows, expected, acc):
        got.update(expected)
        return real(world, state, rows, expected, acc)

    monkeypatch.setattr(EP, "_apply_deaths", capture)
    EP.tick_epidemics(w)
    return got


@pytest.mark.parametrize("techniques", [False, True])
def test_the_tick_scales_expected_deaths_by_the_combined_factor_only(monkeypatch, techniques):
    """Deaths are linear in case fatality (``_step``), so with capacity the
    expected death share is the cost-only share times the combined factor;
    the epidemic model still draws them in ``_apply_deaths``."""
    shares = {}
    for mode in ("care", "cost_only"):
        w = _world(mode=mode, techniques=techniques)
        w.epidemics.initialized_turn = 0
        _outbreak(w, 0, burden=0.05, i=0.05, s=0.7)
        w.livelihoods.epidemic_care.capacity = [
            CareCapacity(region=0, source_turn=4, carers=1, care_time=1.0, patients=5.0)]
        shares[mode] = _tick_expected(w, monkeypatch)[(0, 1)]
        applied = w.livelihoods.epidemic_care.applied[0]
    factor = 1.0 - 0.3 * 0.5
    tech = applied.techniques_factor
    combined = EC.combine_one(tech, factor)
    expected_ratio = combined / (tech if tech is not None else 1.0)
    assert shares["care"] == pytest.approx(shares["cost_only"] * expected_ratio, rel=1e-9)
    assert shares["care"] < shares["cost_only"]


def test_feature_off_tick_is_unchanged(monkeypatch):
    """A world without the switch, and one with it but no capacity, tick the
    same rows to the same values as a world that never imported C2."""
    rows = {}
    for label in ("absent", "no_capacity"):
        w = _world()
        if label == "absent":
            w.livelihoods.epidemic_care = None
        w.epidemics.initialized_turn = 0
        _outbreak(w, 0, burden=0.05, i=0.05, s=0.7)
        EP.tick_epidemics(w)
        rows[label] = [r.model_dump() for r in w.epidemics.rows]
    assert rows["absent"] == rows["no_capacity"]
    w = _world()
    w.livelihoods = None
    assert EC.care_factors(w, []) is None


# --- Phase 2: carers, exclusions, farm time, wages ----------------------------------

def test_carers_are_named_in_id_order_cover_the_need_and_leave_farm_labour():
    w = _world()
    _outbreak(w, 0, burden=0.07)           # 14 infectious: 2.8 worker-turns of care
    _envelope(w, 0, 5)
    sim = _Sim(_people())
    batch = _phase2(w, sim)
    st = w.livelihoods.epidemic_care
    (r,) = st.frame
    assert [x.agent_id for x in r.carers] == [1, 2, 3]
    assert [x.share for x in r.carers] == pytest.approx([1.0, 1.0, 0.8], abs=1e-6)
    assert r.need == pytest.approx(2.8) and r.limit == "need_met" and r.eligible == 6
    assert r.patients == pytest.approx(14.0, abs=1e-5)
    # Farm labour: 7 farmers in region 0 (the child counts natively), factor 1 - 2.8 / 7.
    assert batch.column("farm_labor_factor").to_pylist()[0] == pytest.approx(1.0 - 2.8 / 7, abs=1e-6)
    assert sorted(a for a, *_ in sim.work_reservations(5)) == [1, 2, 3]
    assert all(c == EC.CATEGORY_REPAIR for _a, c, _f in sim.work_reservations(5))
    # Withheld income share = care time; wages by stable id, once.
    assert sim.paid == pytest.approx({1: 1.0, 2: 1.0, 3: 0.8}, abs=1e-6)
    assert [x.wage_due_milli for x in r.carers] == [500, 500, 400]
    assert sim.wealth == {1: 500, 2: 500, 3: 400}
    assert sim.transfers[0][1:3] == (money.PURPOSES["care_wage"], EC.CARE_WAGE_BATCH + 0)
    (row,) = st.ledger
    assert (row.due_milli, row.paid_milli, row.treasury_units, row.carry_before, row.carry_after) == (1400, 1400, 2, 0, 600)
    assert w.civilizations[0].treasury == 98
    assert st.capacity == [CareCapacity(region=0, source_turn=5, carers=3, care_time=r.care_time, patients=r.patients)]


def test_the_prepaid_carry_is_spent_first_next_turn():
    w = _world()
    _outbreak(w, 0, burden=0.025)          # 5 infectious: 1 worker-turn, 500 milli
    _envelope(w, 0, 1)
    sim = _Sim(_people())
    _phase2(w, sim)
    st = w.livelihoods.epidemic_care
    assert w.civilizations[0].treasury == 99 and st.book.carry == {"0:care_wage": 500}
    sim.tick(5)
    EC.after_agent_tick(w, _Bridge(sim))
    assert st.frame[0].carers[0].income_withheld == pytest.approx(0.3)
    EC.phase10(w, None, None, _Bridge(sim))
    w.turn = 6
    _envelope(w, 0, 1)
    _phase2(w, sim)
    assert w.civilizations[0].treasury == 99 and st.book.carry == {}     # paid from the carry
    assert st.ledger[0].treasury_units == 0 and st.ledger[0].carry_before == 500


def test_carers_exclude_everyone_already_booked_this_turn():
    w = _world()
    _outbreak(w, 0, burden=0.2)            # 40 infectious: 8 worker-turns, more than region 0 has
    _envelope(w, 0, 10)
    sim = _Sim(_people())
    sim.reserve_work(5, 3, [(1, 1.0)])                       # a repair crew member
    sim.trips = {2}                                          # away on a merchant trip
    w.health_care = SimpleNamespace(_prepared=[(3, 0, 4, 0.2)])  # 3 a patient, 4 their caregiver
    _phase2(w, sim)
    (r,) = w.livelihoods.epidemic_care.frame
    assert [x.agent_id for x in r.carers] == [5, 6]          # children, merchants, soldiers never
    assert r.limit == "labour" and r.eligible == 2
    booked = LR.booked(w, sim, 5)
    assert booked[3] == "health_patient" and booked[4] == "health_caregiver"
    assert booked[2] == "trip"
    # The carers are now registry holders: nobody else can book them this turn.
    assert {5, 6} <= {a for a, *_ in sim.work_reservations(5)}


def test_the_shared_query_agrees_with_the_recovery_crews_exclusion():
    w = _world()
    sim = _Sim(_people())
    sim.reserve_work(5, 0, [(100, 0.2)])
    sim.reserve_work(5, 3, [(110, 1.0)])
    sim.trips = {2, 200}
    w.health_care = SimpleNamespace(_prepared=[(3, 0, 4, 0.2), (5, 0, 0, 0.0)])
    assert set(LR.booked(w, sim, 5)) == RC._excluded(w, sim, 5)


def test_envelope_and_treasury_limit_the_carers():
    w = _world(treasury=21)
    _outbreak(w, 0, burden=0.2)
    _envelope(w, 0, 1)                     # 1000 milli: two whole carers
    sim = _Sim(_people())
    _phase2(w, sim)
    (r,) = w.livelihoods.epidemic_care.frame
    assert r.limit == "envelope" and r.wages_due_milli <= 1000 and len(r.carers) == 2
    w2 = _world(treasury=0)
    _outbreak(w2, 0, burden=0.2)
    _envelope(w2, 0, 3)
    _phase2(w2, _Sim(_people()))
    (r2,) = w2.livelihoods.epidemic_care.frame
    assert r2.limit == "treasury" and r2.carers == [] and w2.livelihoods.epidemic_care.capacity == []


def test_no_patients_and_a_lost_region_name_nobody():
    w = _world()
    _envelope(w, 0, 2)                     # no outbreak row
    w.regions[1].controller = w.civilizations[1].name
    _outbreak(w, 1, burden=0.1)
    _envelope(w, 1, 2)
    sim = _Sim(_people())
    _phase2(w, sim)
    limits = {r.region: r.limit for r in w.livelihoods.epidemic_care.frame}
    assert limits == {0: "no_patients", 1: "recipient_lost"}
    assert sim.work_reservations(5) == [] and sim.transfers == []


def test_a_duplicate_payment_and_a_stale_settlement_are_refused():
    w = _world()
    _outbreak(w, 0, burden=0.025)
    _envelope(w, 0, 1)
    sim = _Sim(_people())
    bridge = _Bridge(sim)
    EC.prepare_phase2(w, _batch(w, sim), bridge, sim.get_snapshot(), None)
    EC.finish_phase2(w, SimpleNamespace(), bridge, None)
    with pytest.raises(RuntimeError, match="already settled"):
        EC.finish_phase2(w, SimpleNamespace(), bridge, None)
    with pytest.raises(RuntimeError, match="already planned"):
        EC.prepare_phase2(w, _batch(w, sim), bridge, sim.get_snapshot(), None)
    # The same keyed bill again is refused by the seam's book, before any move.
    st = w.livelihoods.epidemic_care
    bill = money.Bill(purpose="care_wage", batch=EC.CARE_WAGE_BATCH, phase="phase2",
                      lines=((money.agent(1), 500),), payer=money.treasury(0))
    got = money.pay(w, bill, turn=5, book=st.book, sim=sim)
    assert not got.ok and got.reason == "already_settled" and sim.wealth == {1: 500}
    # A plan of another turn is never settled.
    EC.phase10(w, None, None, bridge)
    st._turn = EC._Turn(4, sim)
    st._turn.prepared = True
    w.turn = 6
    with pytest.raises(RuntimeError, match="plan missing"):
        EC.finish_phase2(w, SimpleNamespace(), bridge, None)


def test_a_failed_phase2_records_nothing_and_a_failed_tick_releases_the_paid_share():
    w = _world()
    _outbreak(w, 0, burden=0.025)
    _envelope(w, 0, 1)
    sim = _Sim(_people())
    bridge = _Bridge(sim)
    EC.prepare_phase2(w, _batch(w, sim), bridge, sim.get_snapshot(), None)
    EC.rollback_phase2(w)
    st = w.livelihoods.epidemic_care
    assert st._turn is None and st.frame is None and st.capacity == [] and sim.transfers == []
    w.turn = 6
    _envelope(w, 0, 1)
    EC.prepare_phase2(w, _batch(w, sim), bridge, sim.get_snapshot(), None)
    EC.finish_phase2(w, SimpleNamespace(), bridge, None)
    EC.rollback_agent_tick(w, bridge)
    assert sim.paid is None and sim.cancelled == 1


def test_a_carer_absent_at_payment_is_not_paid_and_the_treasury_keeps_it():
    w = _world()
    _outbreak(w, 0, burden=0.05)           # 2 worker-turns: carers 1 and 2
    _envelope(w, 0, 2)
    sim = _Sim(_people())
    bridge = _Bridge(sim)
    EC.prepare_phase2(w, _batch(w, sim), bridge, sim.get_snapshot(), None)
    del sim.people[2]                      # died before settlement
    EC.finish_phase2(w, SimpleNamespace(), bridge, None)
    st = w.livelihoods.epidemic_care
    row = st.ledger[0]
    assert (row.due_milli, row.paid_milli, row.residual_milli) == (1000, 500, 500)
    assert (row.treasury_units, row.carry_after) == (1, 500)
    assert st.frame[0].carers[1].wage_residual_milli == 500


# --- the payment seam: treasury -> agents ---------------------------------------------

def test_a_treasury_pays_agents_only_for_a_declared_purpose():
    w = _world()
    book = money.MoneyBook()
    with pytest.raises(money.MoneyError, match="not supported"):
        money.quote(w, money.Bill(purpose="wares_purchase", batch=0, phase="x", lines=((money.agent(1), 1000),),
                                  payer=money.treasury(0)), turn=5, book=book)
    with pytest.raises(money.MoneyError, match="not supported"):
        money.quote(w, money.Bill(purpose="care_wage", batch=0, phase="x", lines=((money.agent(1), 500),),
                                  payer=money.treasury(0), residual="sink:credit_refused"), turn=5, book=book)
    short = money.Bill(purpose="care_wage", batch=1, phase="x", lines=((money.agent(1), 500), (money.agent(2), 500)),
                       payer=money.treasury(0))
    w.civilizations[0].treasury = 0
    sim = _Sim(_people())
    got = money.pay(w, short, turn=5, book=book, sim=sim)
    assert not got.ok and got.reason == "payer_short" and sim.transfers == []      # whole bill or nothing


def test_a_ceiling_refused_credit_returns_to_the_prepaid_carry():
    w = _world()
    book = money.MoneyBook()
    sim = _Sim(_people())
    sim.wealth[1] = _Sim.CEILING - 200
    bill = money.Bill(purpose="care_wage", batch=7, phase="x", lines=((money.agent(1), 500), (money.agent(2), 700)),
                      payer=money.treasury(0))
    got = money.pay(w, bill, turn=5, book=book, sim=sim)
    assert got.ok and got.applied == 900 and got.residual == 300 and got.treasury_units == -1
    assert book.carry == {"0:care_wage": 100} and w.civilizations[0].treasury == 99
    money.check_book(book)
    total = book.totals[0]
    assert total.applied == 900 and total.treasury_units == -1 and total.carry_change == 100


def test_the_native_code_check_accepts_the_alias_only_at_its_native_name():
    sim = _Sim({})
    assert money._native_code(sim, "care_wage") == money.NATIVE_PURPOSES.index("repair_wage")

    class Other(_Sim):
        @staticmethod
        def wealth_transfer_purposes():
            return ["workshop_wage", "relocation_fare", "apprentice_stipend", "care_wage"]

    with pytest.raises(money.MoneyError, match="rebuild"):
        money._native_code(Other({}), "care_wage")


# --- L9 provider ----------------------------------------------------------------------

def _obs(w):
    return SimpleNamespace(turn=w.turn, economy=object(), pcf=0.5, trace={})


def test_proposals_come_from_reported_outbreaks_of_the_civs_regions():
    w = _world()
    _outbreak(w, 0, burden=0.05, pathogen=1)                 # reported, civ 0
    _outbreak(w, 1, burden=0.05, reported=False)             # smoulder: not known to the ruler
    _outbreak(w, 2, burden=0.05)                             # another civ's region
    (p,) = EC.BUDGET_PROVIDER.proposals(w, 0, _obs(w))
    assert p["recipients"] == [0] and p["claims"] == ["epidemic_care:0"] and p["divisible"] is True
    assert p["expected"] == pytest.approx(2.0) and p["cost"] == 1
    pox = EP.PATHOGENS[1]
    deaths = 10.0 * EP.SUBSTEPS * pox.recovery * pox.cfr
    assert p["relief"]["commons"] == pytest.approx(0.3 * deaths * 10.0 * 0.5, abs=1e-5)
    w.livelihoods.epidemic_care.enabled = False
    assert EC.BUDGET_PROVIDER.proposals(w, 0, _obs(w)) == []


def test_settlement_reads_the_turns_frame():
    w = _world()
    _outbreak(w, 0, burden=0.07)
    cid = _envelope(w, 0, 5)
    sim = _Sim(_people())
    _phase2(w, sim)
    c = next(c for c in w.livelihoods.local_budgets.open if c.cid == cid)
    got = EC.BUDGET_PROVIDER.settle(w, c, _obs(w))
    assert got["outcome"] == "kept" and got["delivered"] == pytest.approx(2.8, abs=1e-5) and got["spent"] == 1
    assert got["spent"] <= c.amount
    w.livelihoods.epidemic_care.frame_turn = 4
    assert EC.BUDGET_PROVIDER.settle(w, c, _obs(w))["reason"] == "service_off"


def test_the_provider_is_appended_and_inactive_without_the_switch():
    # Appended after every earlier provider; B3's works proposal (landed later) follows it.
    assert LB.PROVIDERS[-2:] == ("chronicler.epidemic_care:BUDGET_PROVIDER",
                                 "chronicler.infrastructure_condition:BUDGET_PROVIDER")
    assert LB.PROVIDERS[:-2] == (
        "chronicler.local_budgets:RELIEF", "chronicler.local_budgets:GRANARY", "chronicler.local_budgets:WORKSHOP",
        "chronicler.local_budgets:TEACHING", "chronicler.local_budgets:WARDENS", "chronicler.local_budgets:RELOCATION",
        "chronicler.clearing_protection:BUDGET_PROVIDER", "chronicler.local_budgets:REPAIRS",
        "chronicler.maintenance_obligation:BUDGET_PROVIDER")
    w = _world()
    w.livelihoods.epidemic_care = None
    assert not EC.BUDGET_PROVIDER.active(w) and EC.BUDGET_PROVIDER.group == "relief"


# --- configuration, refusals, records ----------------------------------------------

def _args(**kw):
    return SimpleNamespace(**kw)


def _plain_world():
    w = generate_world(seed=42, num_regions=3, num_civs=2)
    set_grain_reserves_enabled(w, True)
    set_epidemiology_enabled(w, True)
    set_contact_ledger_enabled(w, True)
    return w


@pytest.mark.parametrize("args, agent_mode, message", [
    (dict(epidemic_care=True, local_budgets=True), "shadow", "requires --agents hybrid"),
    (dict(epidemic_care=True), "hybrid", "requires --local-budgets"),
    (dict(epidemic_care_mode="cost_only", local_budgets=True), "hybrid", "requires --epidemic-care"),
])
def test_invalid_requests_are_refused(args, agent_mode, message):
    w = _plain_world()
    with pytest.raises(ValueError, match=message):
        LV.configure_livelihoods(w, _args(**args), agent_mode=agent_mode)


def test_epidemiology_off_is_refused():
    w = _plain_world()
    set_epidemiology_enabled(w, False)
    with pytest.raises(ValueError, match="epidemiology with the contact ledger"):
        LV.configure_livelihoods(w, _args(epidemic_care=True, local_budgets=True), agent_mode="hybrid")


def test_a_saved_world_outside_hybrid_is_refused_with_the_way_to_end_it():
    w = _plain_world()
    LV.configure_livelihoods(w, _args(epidemic_care=True, epidemic_care_mode="cost_only", local_budgets=True),
                             agent_mode="hybrid")
    assert w.livelihoods.epidemic_care.mode == "cost_only"
    with pytest.raises(LV.LivelihoodsRefusal, match="pass --no-epidemic-care to end it") as refused:
        LV.configure_livelihoods(w, _args(), agent_mode="off")
    assert refused.value.code.startswith("Error: --epidemic-care requires --agents hybrid")   # no traceback at the CLI
    w.livelihoods.epidemic_care.tick_turn = 3
    with pytest.raises(ValueError, match="keeps its epidemic care mode"):
        LV.configure_livelihoods(w, _args(epidemic_care_mode="care"), agent_mode="hybrid")
    LV.configure_livelihoods(w, _args(epidemic_care=False), agent_mode="off")      # ending it is allowed
    assert w.livelihoods.epidemic_care.enabled is False and w.livelihoods.epidemic_care.capacity == []


def test_exact_resume_conflicts_name_the_saved_mode():
    w = _plain_world()
    LV.configure_livelihoods(w, _args(epidemic_care=True, local_budgets=True), agent_mode="hybrid")
    conflicts = LV.livelihoods_resume_conflicts(w, _args(epidemic_care_mode="cost_only"), {})
    assert conflicts == ["--epidemic-care-mode 'cost_only' conflicts with the checkpoint (saved: 'care')"]


def test_feature_off_worlds_carry_no_key_and_the_state_pickles_without_its_turn():
    w = _plain_world()
    w.livelihoods = LivelihoodsState()
    assert "epidemic_care" not in w.livelihoods.model_dump()
    st = EpidemicCareState()
    st._turn = object()
    back = pickle.loads(pickle.dumps(st))
    assert back._turn is None and "frame" not in st.model_dump()
    with pytest.raises(Exception):
        EpidemicCareState.model_validate({"schema_version": 2})           # an unknown version is refused


def test_snapshot_is_dated_and_unobserved_turns_are_none():
    w = _world()
    _outbreak(w, 0, burden=0.025)
    _envelope(w, 0, 1)
    sim = _Sim(_people())
    _phase2(w, sim)
    w.turn = 6                              # the snapshot of the completed turn 5
    snap = EC.snapshot_summary(w)
    assert snap["schema_version"] == 1 and snap["stage"] == "C2" and snap["source_turn"] == 5
    assert snap["frame"][0]["carers"][0]["agent_id"] == 1 and snap["capacity"][0]["source_turn"] == 5
    assert snap["tick"] is None             # no tick observed at turn 5 in this construction
    assert set(snap["counters"]) <= set(COUNTERS)
    w.turn = 8
    later = EC.snapshot_summary(w)
    assert later["frame"] is None and later["ledger"] is None


def test_a_rebuilt_pool_drops_the_ids_and_keeps_the_dated_capacity():
    w = _world()
    _outbreak(w, 0, burden=0.025)
    _envelope(w, 0, 1)
    _phase2(w, _Sim(_people()))
    st = w.livelihoods.epidemic_care
    EC.on_pool_reset(w)
    assert st.frame is None and st.ledger is None and len(st.capacity) == 1 and st.counters["pool_resets"] == 1


def test_cli_parser_forwarding_and_manifest():
    from chronicler.batch_manifest import simulation_config
    from chronicler.main import _build_parser
    parser = _build_parser()
    default = parser.parse_args([])
    assert default.epidemic_care is None and default.epidemic_care_mode is None
    assert "epidemic_care" not in simulation_config(default)
    args = parser.parse_args(["--epidemic-care", "--epidemic-care-mode", "cost_only"])
    assert LV.livelihoods_arguments(args)[-2:] == ["--epidemic-care", "--epidemic-care-mode=cost_only"]
    assert simulation_config(args)["epidemic_care_mode"] == "cost_only"


def test_the_catalog_declares_the_exclusion_on_both_sides():
    from chronicler import feature_catalog as fc
    assert fc.exclusion_problems() == []
    surface = {"agents": "hybrid", "values": {}, "settings": {"epidemiology": True}}
    assert fc.validate_features({"grain_reserves": True, "local_budgets": True, "epidemic_care": True}, surface) is None
    refusal = fc.validate_features({"grain_reserves": True, "local_budgets": True, "epidemic_care": True,
                                    "wealth_accounting": True}, surface)
    assert refusal == "'epidemic_care' (--epidemic-care) requires --wealth-accounting off"
    assert fc.validate_features({"epidemic_care": True}, {"agents": "hybrid", "values": {},
                                "settings": {"epidemiology": False}}).endswith("requires --local-budgets")


# --- C3 invariants --------------------------------------------------------------------

def _names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.alias):
            out.add(node.name.split(".")[-1])
    return out


def test_care_never_kills_and_never_touches_injury_episodes():
    """Care changes a parameter (case fatality), never deaths directly: no
    population drain, staged catastrophe death or injury episode in C2."""
    names = _names(SRC / "epidemic_care.py") | _names(SRC / "epidemic_care_state.py") | _names(SRC / "labour_reservations.py")
    forbidden = {"drain_region_pop", "stage_region_catastrophe_deaths", "sync_civ_population", "_apply_deaths",
                 "InjuryEpisode", "episodes", "set_health_care_enabled", "finish_health_care", "prepare_health_care",
                 "endemic_severity", "population"}
    assert not (names & forbidden)


def test_epidemic_code_never_creates_injury_episodes_and_health_care_never_reads_epidemics():
    epi = _names(SRC / "epidemiology.py")
    assert "InjuryEpisode" not in epi and "health_care" not in epi
    for module in ("health_care.py", "health_care_state.py"):
        names = _names(SRC / module)
        assert not ({"epidemics", "epidemiology", "EpidemicState", "RegionInfection", "cfr", "epidemic_care"} & names)


def test_carers_are_not_injury_caregivers_in_the_same_turn():
    w = _world()
    _outbreak(w, 0, burden=0.2)
    _envelope(w, 0, 10)
    sim = _Sim(_people())
    w.health_care = SimpleNamespace(_prepared=[(1, 0, 2, 0.2), (3, 0, 0, 0.0)])
    sim.health = {1, 2}                       # held natively as rural health work too
    _phase2(w, sim)
    carers = {x.agent_id for x in w.livelihoods.epidemic_care.frame[0].carers}
    assert carers and not carers & {1, 2, 3}


def test_endemic_mortality_inputs_are_untouched():
    """M35b endemic severity is read by the native mortality from the bridge;
    C2 changes no region's ecology, severity or population."""
    w = _world()
    before = [(r.endemic_severity, r.population) for r in w.regions]
    _outbreak(w, 0, burden=0.2)
    _envelope(w, 0, 10)
    _phase2(w, _Sim(_people()))
    w.turn = 6
    EC.care_factors(w, w.epidemics.rows)
    assert [(r.endemic_severity, r.population) for r in w.regions] == before


def test_counters_and_parameters_are_declared():
    assert EC.parameters()["care_cfr_reduction"] == 0.3 and EC.parameters()["patients_per_carer"] == 5.0
    st = EpidemicCareState()
    with pytest.raises(KeyError):
        EC._bump(st, "undeclared")
    assert math.isclose(EC.PATIENTS_PER_CARER, 1.0 / 0.2)
    from chronicler.health_care_state import HealthCareState
    assert HealthCareState().care_fraction == 0.2


# --- review of 3e5ee44d: per-civ envelopes, payment refusal, labels, order ------------------

def test_one_proposal_per_civ_covers_its_outbreak_regions_and_rounds_up_once():
    w = _world()
    _outbreak(w, 0, burden=0.05)           # 10 infectious: 2 worker-turns, 1000 milli
    _outbreak(w, 1, burden=0.01)           # 2 infectious: 0.4 worker-turns, 200 milli
    (p,) = EC.BUDGET_PROVIDER.proposals(w, 0, _obs(w))
    assert p["recipients"] == [0, 1] and p["claims"] == ["epidemic_care:0"]
    assert p["detail"]["wages_milli"] == 1200 and p["cost"] == 2          # not one coin per region (3)
    assert p["expected"] == pytest.approx(2.4)


def test_one_envelope_serves_its_regions_most_infectious_first_within_the_award():
    w = _world()
    _outbreak(w, 0, burden=0.01)           # 2 infectious: 0.4 worker-turns
    _outbreak(w, 1, burden=0.05)           # 10 infectious: 2 worker-turns
    _envelope(w, [0, 1], 1)                # 1000 milli: region 1 first takes all of it
    _phase2(w, _Sim(_people()))
    by = {r.region: r for r in w.livelihoods.epidemic_care.frame}
    assert by[1].care_time == pytest.approx(2.0, abs=1e-6) and by[1].limit == "need_met"
    assert by[0].carers == [] and by[0].limit == "envelope"
    assert sum(r.wages_due_milli for r in by.values()) <= 1000
    (row,) = w.livelihoods.epidemic_care.ledger
    assert row.envelope_coins == 1 and row.status == "paid"


def test_a_bill_refused_at_payment_withholds_nothing_pays_nobody_and_gives_no_capacity():
    """Other packages charge the treasury in Phase 2 before C2 pays: the bill is
    quoted again at payment, before any income is withheld."""
    w = _world(treasury=5)
    _outbreak(w, 0, burden=0.05)
    cid = _envelope(w, 0, 2)
    sim = _Sim(_people())
    bridge = _Bridge(sim)
    EC.prepare_phase2(w, _batch(w, sim), bridge, sim.get_snapshot(), None)
    assert w.livelihoods.epidemic_care._turn.receipts[0].carers          # booked at prepare
    w.civilizations[0].treasury = 0                                      # another package's charge
    EC.finish_phase2(w, SimpleNamespace(), bridge, None)
    st = w.livelihoods.epidemic_care
    (r,) = st.frame
    assert r.unpaid_reason == "payer_short" and not r.paid and r.wages_paid_milli == 0
    assert sim.paid is None and sim.transfers == []                      # nothing withheld, nothing moved
    assert st.capacity == []
    (row,) = st.ledger
    assert row.status == "refused:payer_short" and row.due_milli == 1000 and row.paid_milli == 0
    assert st.counters["unpaid_bills"] == 1 and st.counters["farm_time_unpaid"] == pytest.approx(2.0, abs=1e-6)
    c = next(c for c in w.livelihoods.local_budgets.open if c.cid == cid)
    assert EC.BUDGET_PROVIDER.settle(w, c, _obs(w))["reason"] == "treasury_shortfall"


def test_an_envelope_without_patients_leaves_a_nothing_due_ledger_row():
    w = _world()
    _envelope(w, 0, 1)
    _phase2(w, _Sim(_people()))
    (row,) = w.livelihoods.epidemic_care.ledger
    assert (row.status, row.envelope_coins, row.due_milli) == ("nothing_due", 1, 0)
    assert w.livelihoods.epidemic_care.counters["envelope_coins"] == 1


def test_an_envelope_that_ran_out_as_the_need_grew_settles_as_a_cost_that_rose():
    w = _world()
    _outbreak(w, 0, burden=0.2)            # 8 worker-turns needed
    cid = _envelope(w, 0, 1)
    c = next(c for c in w.livelihoods.local_budgets.open if c.cid == cid)
    c.expected = 8.0                       # the full need was promised; the award was 1 coin
    _phase2(w, _Sim(_people()))
    assert w.livelihoods.epidemic_care.frame[0].limit == "envelope"
    assert EC.BUDGET_PROVIDER.settle(w, c, _obs(w))["reason"] == "cost_rose"


def test_the_shared_query_labels_carers_as_care():
    w = _world()
    _outbreak(w, 0, burden=0.025)
    _envelope(w, 0, 1)
    sim = _Sim(_people())
    EC.prepare_phase2(w, _batch(w, sim), _Bridge(sim), sim.get_snapshot(), None)
    booked = LR.booked(w, sim, 5)
    assert booked[1] == "registry_care" and all(c == 3 for _a, c, _f in sim.work_reservations(5))
    assert "registry_care" in LR.REASONS


def test_the_shared_query_names_every_native_registry_category():
    """The registry categories follow ``workshop_work.rs`` (A4 appended ``trade``),
    so an A4 carrier is booked as ``registry_trade``, not ``registry_other``."""
    import re
    root = Path(__file__).resolve().parents[1]
    source = (root / "chronicler-agents" / "src" / "workshop_work.rs").read_text(encoding="utf-8")
    native = re.search(r"RESERVATION_CATEGORIES: \[&str; \d+\] = \[([^\]]*)\]", source).group(1)
    assert LR.REGISTRY_CATEGORIES == tuple(re.findall(r'"([a-z_]+)"', native))
    from chronicler import titled_trade as TT
    assert LR.REGISTRY_CATEGORIES[TT.CATEGORY_TRADE] == "trade" and "registry_trade" in LR.REASONS

    class Sim:
        def work_reservations(self, turn):
            return [(7, TT.CATEGORY_TRADE, 1.0), (8, 9, 1.0)]

    w = _world()
    booked = LR.booked(w, Sim(), 5)
    assert booked[7] == "registry_trade" and booked[8] == "registry_other"


def test_the_tick_record_reads_every_infected_region_after_the_tick(monkeypatch):
    w = _world()
    w.epidemics.initialized_turn = 0
    _outbreak(w, 0, burden=0.05, i=0.05, s=0.7)
    _outbreak(w, 2, burden=0.02, i=0.02, s=0.7)
    w.livelihoods.epidemic_care.capacity = [CareCapacity(region=0, source_turn=4, carers=1, care_time=1.0,
                                                         patients=5.0)]
    EP.tick_epidemics(w)
    EC._observe_tick(w, w.livelihoods.epidemic_care)
    regions = {r.region: r for r in w.livelihoods.epidemic_care.regions}
    assert set(regions) == {r.region for r in w.epidemics.rows} | {j for j, _k, _d in w.epidemics.last_deaths}
    assert sum(r.deaths for r in regions.values()) == sum(d for _j, _k, d in w.epidemics.last_deaths)
    burden = {row.region: row.burden * row.n for row in w.epidemics.rows}
    assert all(regions[j].infectious_pt == pytest.approx(v) for j, v in burden.items())
    assert w.livelihoods.epidemic_care.applied[0].infectious_after == pytest.approx(burden[0])
    for j, r in regions.items():           # the per-pathogen split sums to the region's totals
        assert sum(d for _k, d, _i in r.pathogens) == r.deaths
        assert sum(i for _k, _d, i in r.pathogens) == pytest.approx(r.infectious_pt)
    assert {k for k, _d, _i in regions[0].pathogens} == {1}


def test_a_share_whose_wage_rounds_to_zero_names_nobody(monkeypatch):
    """The rounding boundary: a share below the wage's resolution books nobody (a
    zero wage would book farm time and date no capacity)."""
    assert EC._wage(0.0009999) == 0 and EC._wage(0.002) == 1
    w = _world()
    _outbreak(w, 0, burden=0.03)           # 6 infectious: 1.2 worker-turns
    _envelope(w, 0, 1)
    real = EC._wage
    monkeypatch.setattr(EC, "_wage", lambda share: 0 if share < 0.5 else real(share))
    sim = _Sim(_people())
    _phase2(w, sim)
    (r,) = w.livelihoods.epidemic_care.frame
    assert [x.agent_id for x in r.carers] == [1] and r.limit == "labour"
    assert [a for a, *_ in sim.work_reservations(5)] == [1] and r.paid


def test_a_capacity_row_naming_no_region_and_one_left_unconsumed_are_counted():
    w = _world()
    st = w.livelihoods.epidemic_care
    st.capacity = [CareCapacity(region=99, source_turn=4, carers=1, care_time=1.0, patients=5.0)]
    EC.care_factors(w, [])
    assert [(r.region, r.reason) for r in st.refused] == [(99, "out_of_range")]
    assert st.counters["capacity_out_of_range"] == 1
    st.capacity = [CareCapacity(region=0, source_turn=4, carers=1, care_time=1.0, patients=5.0)]
    _phase2(w, _Sim(_people()))
    assert st.counters["capacity_unconsumed"] == 1 and st.capacity == []


def test_carers_are_booked_after_every_other_work_consumer():
    """C2 names its carers after every other package's Phase 2 planning: no
    switch after it in the hook order plans work, apart from the observers
    (and D1b's guild leagues, which move purses and book no work)."""
    from importlib import import_module
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    later = LIVELIHOODS_SWITCHES[LIVELIHOODS_SWITCHES.index("epidemic_care") + 1:]
    # D1b moves purses; X1 is record-only. Neither books labour.
    assert later == ("guild_leagues", "residence_ledger", "attribution_records", "wealth_accounting")
    for name in later:
        module = import_module("chronicler." + name)
        assert not hasattr(module, "reserve_first")
        assert not hasattr(module, "reserve_work")
    # The observers' Phase 2 hooks reserve nobody: no registry write in their source.
    for name in later:
        assert "reserve_work" not in (SRC / f"{name}.py").read_text(encoding="utf-8")


def test_prepaid_units_are_split_over_the_regions_of_the_bill():
    w = _world()
    book = money.MoneyBook()
    sim = _Sim(_people())
    bill = money.Bill(purpose="care_wage", batch=3, phase="x",
                      lines=((money.agent(1), 1500), (money.agent(200), 1500)), payer=money.treasury(0),
                      regions=(0, 2))
    got = money.pay(w, bill, turn=5, book=book, sim=sim)
    assert got.treasury_units == -3
    by_region = {t.region: t.treasury_units for t in book.totals}
    assert by_region == {0: -2, 2: -1} and sum(by_region.values()) == -3
