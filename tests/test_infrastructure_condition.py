"""B3 infrastructure condition and repair (``--infrastructure-condition``) without
the native extension: constructed worlds, RS2's recording simulator and a
labour-limited stand-in for the native storage-work column (no simulation run)."""
from __future__ import annotations

import ast
import copy
import json
import pickle
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import grain_storage as S
from chronicler import infrastructure_condition as IC
from chronicler import repair_projects as RP
from chronicler.grain_reserves import _ensure, set_grain_reserves_enabled
from chronicler.grain_storage_state import StorageAsset
from chronicler.infrastructure_condition_state import COUNTERS, InfrastructureConditionState
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.local_budgets_state import Commitment, LocalBudgetState
from chronicler.models import Event, Infrastructure, InfrastructureType
from chronicler.world_gen import generate_world

from tests.test_repair_projects import _Sim

ROOT = Path(__file__).resolve().parents[1]
IRR, ROADS = InfrastructureType.IRRIGATION, InfrastructureType.ROADS


@pytest.fixture(autouse=True)
def _no_commitments(monkeypatch):
    monkeypatch.setattr(RP, "_commitments", lambda world, sim: getattr(sim, "commitments", {}))


def _world(*, mode="repair", treasury=200, timber=50.0, policy="neglect", granary=1.0, rs2=True,
           infrastructure=((0, IRR), (1, IRR), (1, ROADS), (2, ROADS)), switch=True):
    w = generate_world(seed=42, num_regions=3, num_civs=2)
    w.agent_mode = "hybrid"
    w.turn = 5
    civ = w.civilizations[0]
    civ.regions = [r.name for r in w.regions]
    civ.treasury = treasury
    w.civilizations[1].regions = []
    for r in w.regions:
        r.controller = civ.name
        r.stockpile.goods = {"timber": timber, "grain": 10.0}
        r.infrastructure = []
        r.pending_build = None
    for rid, kind in infrastructure:
        w.regions[rid].infrastructure.append(Infrastructure(type=kind, builder_civ=civ.name, built_turn=1))
    set_grain_reserves_enabled(w, True)
    for g in _ensure(w).granaries:
        g.owner, g.grain = 0, 20.0
    storage = S.enable_storage(w)
    storage.assets = [StorageAsset(capacity=100.0, condition=granary if i == 0 else 1.0, owner=0) for i in range(3)]
    for rid in range(3):
        S.set_storage_policy(w, rid, policy, 4.0 if policy != "neglect" else 0.0)
    w.livelihoods = LivelihoodsState()
    if rs2:
        RP.set_repair_projects_enabled(w, True, args=SimpleNamespace(repair_mode=None))
    if switch:
        IC.set_infrastructure_condition_enabled(w, True, args=SimpleNamespace(infrastructure_condition_mode=mode))
    return w


def _batch(world, plan):
    n = len(world.regions)
    cols = {"region_id": pa.array(range(n), pa.uint16()),
            "stockpile_timber": pa.array([r.stockpile.goods.get("timber", 0.0) for r in world.regions], pa.float32())}
    if plan is not None:
        cols["granary_work_requested"] = pa.array(plan.requests, pa.float32())
    return pa.record_batch(cols)


def _turn(world, sim, *, labor=100.0, fail_economy=False, stop_after_phase2=False):
    """One turn in the simulation's order (storage plan, RS2's Phase 2 with
    the works inside it, a labour-limited native column, settlement, Phase 10)."""
    bridge = SimpleNamespace(_sim=sim)
    plan = S.prepare_storage_work(world, [10.0] * len(world.regions), commitments={})
    batch = _batch(world, plan)
    rs2 = RP.repair_projects_active(world) if world.livelihoods.repair_projects is not None else False
    try:
        if rs2:
            batch = RP.prepare_phase2(world, batch, bridge, None, None)
        if fail_economy:
            raise RuntimeError("native economy failed")
        requested = batch.column("granary_work_requested").to_pylist()
        delivered = {rid: min(r, labor) for rid, r in enumerate(requested)}
        for rid, value in enumerate(batch.column("stockpile_timber").to_pylist()):
            world.regions[rid].stockpile.goods["timber"] = value
        econ = SimpleNamespace(granary_work_delivered=delivered, craft_output={}, food_ledger={})
        S.finish_storage_work(world, plan, [delivered[r] for r in range(len(world.regions))])
        if rs2:
            RP.finish_phase2(world, econ, bridge, None)
    except BaseException:
        if plan.status == "pending":
            S.rollback_storage_work(world, plan)
        if rs2:
            RP.rollback_phase2(world)
        IC.rollback_phase2(world)
        raise
    if stop_after_phase2:
        return econ, bridge
    sim.tick(world.turn)
    if rs2:
        RP.after_agent_tick(world, bridge)
        RP.phase10_before_reserves(world, None, econ, bridge)
    if world.livelihoods.infrastructure_condition is not None and IC.infrastructure_condition_active(world):
        IC.phase10_before_reserves(world, None, econ, bridge)
    if rs2:
        RP.phase10(world, None, econ, bridge)
    if world.livelihoods.infrastructure_condition is not None and IC.infrastructure_condition_active(world):
        IC.phase10(world, None, econ, bridge)
    world.turn += 1
    return batch, plan


def _state(world) -> InfrastructureConditionState:
    return world.livelihoods.infrastructure_condition


def _p10(world):
    IC.phase10_before_reserves(world, None, None, None)


def _asset(world, region, kind):
    return next(a for a in _state(world).assets if a.region == region and a.kind == kind)


# ---------------------------------------------------------------------------
# Registry: identity and lifecycle
# ---------------------------------------------------------------------------

def test_active_records_get_stable_ids_matched_each_turn():
    world = _world(mode="record_only", rs2=False)
    IC.reconcile(world)
    state = _state(world)
    assert [(a.aid, a.region, a.kind, a.record_index) for a in state.assets] == [
        (0, 0, "irrigation", 0), (1, 1, "irrigation", 0), (2, 1, "roads", 1), (3, 2, "roads", 0)]
    assert all(a.condition == 1.0 and a.status == "serving" and a.responsible == 0 for a in state.assets)
    before = [a.model_dump() for a in state.assets]
    IC.reconcile(world)
    IC.reconcile(world)
    assert [a.model_dump() for a in state.assets] == before and state.next_aid == 4
    # Fortifications, temples and other types are not assets.
    world.regions[0].infrastructure.append(Infrastructure(type=InfrastructureType.TEMPLES,
                                                          builder_civ="x", built_turn=2))
    IC.reconcile(world)
    assert state.next_aid == 4


@pytest.mark.parametrize("cause", ["scorch", "earthquake", "depopulation", "unknown"])
def test_a_deactivated_record_makes_its_asset_inactive_with_the_dated_cause(cause):
    world = _world(mode="wear_only", rs2=False)
    IC.reconcile(world)
    region = world.regions[1]
    for rec in region.infrastructure:
        rec.active = False
    if cause == "scorch":
        world.events_timeline.append(Event(turn=world.turn, event_type="scorched_earth", actors=["x"],
                                           description=f"x scorched {region.name} during retreat", importance=6))
    elif cause == "earthquake":
        world.events_timeline.append(Event(turn=world.turn, event_type="earthquake", region=region.name,
                                           actors=["nature"], description="Earthquake", importance=7))
    elif cause == "depopulation":
        region.depopulated_since = world.turn
    IC.reconcile(world)
    state = _state(world)
    ended = [a for a in state.terminal if a.region == 1]
    assert [(a.kind, a.status, a.cause, a.status_turn) for a in ended] == [
        ("irrigation", "inactive", cause, 5), ("roads", "inactive", cause, 5)]
    assert {a.region for a in state.assets} == {0, 2}
    assert state.counters[f"inactive_{cause}"] == 2
    assert IC.service(world, 1, "irrigation") == 1.0         # no serving asset: consumers read the record


def test_mid_turn_damage_skips_a_record_ended_earlier_in_the_turn_and_phase10_dates_the_cause():
    world = _world(mode="repair")
    _p10(world)
    world.turn += 1
    region = world.regions[1]
    region.infrastructure[0].active = False                  # an earthquake in Phase 1
    RP.region_conquered(world, region, "x", world.civilizations[0].name)          # Phase 5
    state = _state(world)
    assert [d.aid for d in state.damages] == [2]               # only the road, still active
    assert _asset(world, 1, "irrigation").status == "serving"  # not ended before Phase 10
    world.events_timeline.append(Event(turn=world.turn, event_type="earthquake", region=region.name,
                                       actors=["nature"], description="Earthquake", importance=7))
    _p10(world)
    (ended,) = state.terminal
    assert (ended.aid, ended.status, ended.cause) == (1, "inactive", "earthquake")


def test_a_removed_record_list_destroys_and_a_rebuild_gets_a_new_id():
    world = _world(mode="wear_only", rs2=False)
    IC.reconcile(world)
    region = world.regions[0]
    region.infrastructure = []                               # the supervolcano
    IC.reconcile(world)
    state = _state(world)
    (gone,) = [a for a in state.terminal if a.aid == 0]
    assert (gone.status, gone.cause) == ("destroyed", "record_removed")
    world.turn = 9
    region.infrastructure.append(Infrastructure(type=IRR, builder_civ=world.civilizations[0].name, built_turn=9))
    IC.reconcile(world)
    rebuilt = _asset(world, 0, "irrigation")
    assert rebuilt.aid == 4 and rebuilt.record_index == 0 and rebuilt.opened_turn == 9
    assert state.next_aid == 5 and len({a.aid for a in state.assets + state.terminal}) == 5


def test_conquest_keeps_the_asset_moves_responsibility_and_damages_it_once_a_turn():
    world = _world(mode="repair")
    _p10(world)
    state = _state(world)
    other = world.civilizations[1]
    other.regions = [world.regions[1].name]
    world.regions[1].controller = other.name
    RP.region_conquered(world, world.regions[1], other.name, world.civilizations[0].name)
    RP.city_sacked(world, 0, 1, other.name, world.civilizations[0].name)        # same turn: no second record
    irrigation = _asset(world, 1, "irrigation")
    assert irrigation.condition == pytest.approx(0.99 - 0.25) and irrigation.aid == 1
    assert [(d.aid, d.event) for d in state.damages] == [(1, "conquest"), (2, "conquest")]
    world.turn += 1
    _p10(world)
    assert irrigation.responsible == 1 and any(e[1] == "responsibility" and e[2] == 1 for e in irrigation.history)
    (work,) = [w for w in state.works if w.aid == 1]
    assert work.cause == "war" and work.controller == 1 and work.damages == [0]
    assert work.scope == pytest.approx((1.0 - irrigation.condition) * IC.WORK_PER_CONDITION["irrigation"])
    # The record never changed hands and was never rebuilt.
    assert world.regions[1].infrastructure[0].builder_civ == world.civilizations[0].name


# ---------------------------------------------------------------------------
# Wear, service, failure
# ---------------------------------------------------------------------------

def test_declared_wear_service_and_failure_keep_the_record_active():
    world = _world(mode="wear_only", rs2=False)
    _p10(world)
    irrigation, road = _asset(world, 0, "irrigation"), _asset(world, 1, "roads")
    assert irrigation.condition == pytest.approx(0.99) and road.condition == pytest.approx(0.995)
    _p10(world)                                              # the same turn: wear once
    assert irrigation.condition == pytest.approx(0.99)
    irrigation.condition = 0.3
    assert IC.service(world, 0, "irrigation") == pytest.approx(0.6)
    assert IC.serves(world, world.regions[0], "irrigation")
    irrigation.condition = 0.2
    assert not IC.serves(world, world.regions[0], "irrigation")
    irrigation.condition = 0.005
    world.turn += 1
    _p10(world)
    assert (irrigation.status, irrigation.condition, irrigation.failed_turn) == ("failed", 0.0, 6)
    assert world.regions[0].infrastructure[0].active and IC.service(world, 0, "irrigation") == 0.0
    from chronicler.infrastructure import valid_build_types
    assert IRR not in valid_build_types(world.regions[0])      # failed is not rebuilt
    world.turn += 1
    _p10(world)
    assert irrigation.condition == 0.0 and _state(world).counters["assets_failed"] == 1


def test_consumers_read_exactly_one_when_off_and_service_when_on():
    from chronicler.agent_bridge import build_region_batch
    from chronicler.economy import arable_capacity
    from chronicler.techniques import extend_trade_routes
    off = _world(switch=False)
    record = _world(mode="record_only", rs2=False)
    wear = _world(mode="wear_only", rs2=False)
    for w in (record, wear):
        IC.reconcile(w)
        for a in _state(w).assets:
            a.condition = 0.2                                 # service 0.4 < the gate
    base = [arable_capacity(off, r).hex() for r in off.regions]
    assert [arable_capacity(record, r).hex() for r in record.regions] == base
    assert IC.service(off, 0, "irrigation") == 1.0 and IC.service(record, 0, "irrigation") == 1.0

    def flags(w):
        return build_region_batch(w).column("has_irrigation").to_pylist()

    assert flags(off) == flags(record) == [True, True, False]
    assert flags(wear) == [False, False, False]
    worn = [arable_capacity(wear, r) for r in wear.regions]
    assert worn[0] < arable_capacity(off, off.regions[0]) and worn[2] == arable_capacity(off, off.regions[2])
    # Bit-identical arithmetic: 0.10 x 1.0 == 0.10.
    assert 0.10 * 1.0 == 0.10
    # Roads: the two-hop range rule needs the road's service.
    assert IC.serves(off, 1, "roads") and IC.serves(record, 1, "roads") and not IC.serves(wear, 1, "roads")
    assert callable(extend_trade_routes)


def test_service_fails_closed_for_an_unknown_region():
    world = _world(mode="wear_only", rs2=False)
    IC.reconcile(world)
    _asset(world, 0, "irrigation").condition = 0.2
    copy_of_region = world.regions[0].model_copy()            # a copy is the same region by its name
    assert IC.service(world, copy_of_region, "irrigation") == pytest.approx(0.4)
    stranger = world.regions[0].model_copy(update={"name": "Nowhere"})
    with pytest.raises(ValueError, match="unknown region"):
        IC.service(world, stranger, "irrigation")
    with pytest.raises(ValueError, match="unknown region index"):
        IC.service(world, 99, "roads")


def test_the_watershed_and_python_ecology_read_irrigation_through_the_gate():
    from chronicler import watershed
    from chronicler.ecology import _tick_water
    from chronicler.models import ClimatePhase
    losses = {}
    for label, mode, condition in (("off", None, None), ("record", "record_only", 0.1),
                                   ("serving", "wear_only", 0.9), ("failed", "wear_only", 0.1)):
        world = _world(mode=mode or "wear_only", rs2=False, switch=mode is not None)
        if mode is not None:
            IC.reconcile(world)
            _asset(world, 0, "irrigation").condition = condition
        region = world.regions[0]
        assert watershed._irrigated(world, region, gate=True) == (label != "failed")
        assert watershed._irrigated(world, region, gate=False)          # flow mode: every active work
        region.ecology.water = 0.5
        _tick_water(region, world.civilizations[0], ClimatePhase.DROUGHT, world)
        losses[label] = 0.5 - region.ecology.water
    assert losses["off"] == losses["record"] == losses["serving"] > losses["failed"]   # irrigation's x1.5 drought loss


def test_road_range_rules_are_gated_by_service():
    from chronicler import resources
    source = (ROOT / "src/chronicler/techniques.py").read_text(encoding="utf-8")
    assert 'serves(world, mid, "roads")' in source
    world = _world(mode="wear_only", rs2=False)
    IC.reconcile(world)
    assert resources._roads_serve(world, world.regions[1])
    _asset(world, 1, "roads").condition = 0.1
    assert not resources._roads_serve(world, world.regions[1])
    off = _world(switch=False)
    assert resources._roads_serve(off, off.regions[1])


# ---------------------------------------------------------------------------
# Works: labour, timber, coins through RS2's turn
# ---------------------------------------------------------------------------

def _worn(world, condition=0.5, kinds=("irrigation", "roads")):
    IC.reconcile(world)
    for a in _state(world).assets:
        if a.kind in kinds:
            a.condition = condition
    _p10(world)


def test_a_work_moves_real_labour_timber_and_coins_once():
    world = _world(mode="repair")
    _worn(world, kinds=("irrigation",))
    state = _state(world)
    works = sorted((w.kind, w.region) for w in state.works)
    assert works == [("irrigation", 0), ("irrigation", 1)]
    w0 = next(w for w in state.works if w.region == 0)
    assert w0.scope == pytest.approx((1 - 0.49) * 20)
    treasury, timber = world.civilizations[0].treasury, world.regions[0].stockpile.goods["timber"]
    batch, plan = _turn(world, _Sim())
    assert plan.requests == [0.0, 0.0, 0.0]                    # storage asked nothing (neglect) ...
    assert plan.suspended == frozenset({0, 1})                  # ... so the works claimed those regions
    assert batch.column("granary_work_requested").to_pylist() == [4.0, 4.0, 0.0]
    r0 = next(r for r in state.receipts if r.region == 0)
    assert (r0.status, r0.requested, r0.delivered, r0.credited, r0.shared) == ("progress", 4.0, 4.0, 4.0, False)
    assert r0.timber_used == pytest.approx(1.0) and r0.coin_cost_milli == 2400     # 0.6 coin per work
    a0 = _asset(world, 0, "irrigation")
    assert a0.condition == pytest.approx(0.49 + 4 / 20)       # this turn's wear came before the credit
    assert world.regions[0].stockpile.goods["timber"] == pytest.approx(timber - 1.0)
    (ledger,) = state.ledger
    assert (ledger.charged, ledger.coin_cost_milli, ledger.prepaid_after_milli) == (5, 4800, 200)
    assert treasury - world.civilizations[0].treasury == 5
    assert state.book.sinks == {"public_works": 5000}
    assert [(k[1], k[2]) for k in state.book.settled] == [("infrastructure_repair", 0)]
    # Storage itself did nothing in the claimed regions.
    assert all(r.delivered == 0.0 for r in world.grain_reserves.storage.receipts)


@pytest.mark.parametrize("kind,rebuild", [("irrigation", 12), ("roads", 10)])
def test_a_whole_repair_costs_no_more_coins_than_a_rebuild(kind, rebuild):
    from chronicler.infrastructure import BUILD_SPECS
    spec = BUILD_SPECS[IRR if kind == "irrigation" else ROADS]
    assert spec.cost == rebuild
    assert IC._coin_milli(IC.WORK_PER_CONDITION[kind], kind) == rebuild * 1000


def test_settlement_happens_once_and_a_failed_tick_returns_every_hold():
    world = _world(mode="repair")
    _worn(world, kinds=("irrigation",))
    timber = [r.stockpile.goods["timber"] for r in world.regions]
    treasury = world.civilizations[0].treasury
    with pytest.raises(RuntimeError, match="native economy failed"):
        _turn(world, _Sim(), fail_economy=True)
    assert [r.stockpile.goods["timber"] for r in world.regions] == timber
    assert world.civilizations[0].treasury == treasury and _state(world)._turn is None
    assert _state(world).book.settled == []
    world.turn += 1
    _turn(world, _Sim())
    assert _state(world).last_settled_turn == world.turn - 1
    # A settled turn cannot settle again.
    world.turn -= 1
    with pytest.raises(RuntimeError, match="already settled"):
        IC._begin(world, _state(world))


def test_a_refused_charge_raises_before_anything_is_credited(monkeypatch):
    world = _world(mode="repair", infrastructure=((0, IRR),))
    _worn(world)
    asset = _asset(world, 0, "irrigation")
    before = asset.condition
    from chronicler import money
    monkeypatch.setattr(money, "quote", lambda *a, **k: money.Quote(False, "payer_short", 1, 0))
    with pytest.raises(RuntimeError, match="charge refused at settlement"):
        _turn(world, _Sim())
    assert asset.condition == before and _state(world).works[0].delivered == 0.0
    assert _state(world).book.settled == []


def test_granary_first_in_a_shared_column_then_irrigation_then_roads():
    world = _world(mode="repair", granary=0.5, infrastructure=((0, IRR), (0, ROADS)))
    RP.phase10_before_reserves(world, None, None, None)          # RS2's granary project in region 0
    _worn(world)
    batch, plan = _turn(world, _Sim(), labor=6.0)
    rs2 = world.livelihoods.repair_projects
    (granary,) = rs2.receipts
    assert granary.requested == 4.0 and granary.delivered == 4.0            # the granary first
    assert rs2.suspended == [0]                                             # RS2's record: its own region only
    state = _state(world)
    irr = next(r for r in state.receipts if r.kind == "irrigation")
    road = next(r for r in state.receipts if r.kind == "roads")
    assert batch.column("granary_work_requested").to_pylist()[0] == 12.0
    assert (irr.delivered, road.delivered) == (2.0, 0.0)                    # then irrigation, then roads
    assert irr.shared and irr.granary_request == 4.0 and "no_labor" in irr.reasons
    assert road.status == "stalled" and road.reasons == ["no_labor"]
    assert state.shared == [0]
    # Timber: the unused holds came back.
    assert road.timber_returned == pytest.approx(road.timber_held)


def test_granary_first_follows_storages_actual_request():
    # Maintain below full condition: storage asks for work in region 0 (the
    # granary's), nothing in region 1 (condition 1.0): the works claim region 1.
    world = _world(mode="repair", policy="maintain", granary=0.6, infrastructure=((0, IRR), (1, IRR)))
    _worn(world)
    _batch_, plan = _turn(world, _Sim())
    state = _state(world)
    r0 = next(r for r in state.receipts if r.region == 0)
    r1 = next(r for r in state.receipts if r.region == 1)
    assert plan.requests[0] > 0 and 0 not in plan.suspended
    assert (r0.status, r0.reasons) == ("stalled", ["granary_first"])
    assert r1.status == "progress" and 1 in plan.suspended
    # The same maintain policy with a zero work budget: storage's actual
    # request is 0, so the works may use the column there.
    world = _world(mode="repair", policy="maintain", granary=0.6, infrastructure=((0, IRR),))
    S.set_storage_policy(world, 0, "maintain", 0.0)
    _worn(world)
    _batch_, plan = _turn(world, _Sim())
    (r0,) = _state(world).receipts
    assert plan.requests[0] == 0.0 and 0 in plan.suspended
    assert r0.status == "progress" and r0.delivered == pytest.approx(4.0)


@pytest.mark.parametrize("case,reason", [
    ("timber", "no_timber"), ("coins", "no_coins"), ("labour", "no_labor"), ("envelope", "no_envelope")])
def test_stalls_record_their_cause(case, reason):
    world = _world(mode="repair", timber=0.0 if case == "timber" else 50.0,
                   treasury=0 if case == "coins" else 200, infrastructure=((0, IRR),))
    if case == "envelope":
        world.livelihoods.local_budgets = LocalBudgetState()
        world.livelihoods.local_budgets.enabled = True
    _worn(world)
    _turn(world, _Sim(), labor=0.0 if case == "labour" else 100.0)
    (r,) = _state(world).receipts
    assert r.status == "stalled" and reason in r.reasons
    (work,) = _state(world).works
    assert reason in work.stalls
    assert _state(world).counters[f"stalled_{reason}"] >= 1


def _envelope_row(service, claim, amount, recipients, expected, cid=0):
    return Commitment(cid=cid, civ=0, service=service, pid=cid, decided_turn=4, for_turn=5, recipients=recipients,
                      claims=[claim], amount=amount, unit="work", expected=expected)


def test_the_works_spend_only_their_own_envelope_never_rs2s():
    world = _world(mode="repair", granary=0.5, infrastructure=((1, IRR), (2, IRR), (2, ROADS)))
    lb = world.livelihoods.local_budgets = LocalBudgetState()
    lb.enabled = True
    lb.open = [_envelope_row("repairs", "repairs:0", 11, [0], 4.0),
               _envelope_row(IC.BUDGET_SERVICE, "infrastructure:0", 2, [1, 2], 3.0, cid=1)]
    RP.phase10_before_reserves(world, None, None, None)
    _worn(world)
    treasury = world.civilizations[0].treasury
    _turn(world, _Sim())
    (rs2_row,) = world.livelihoods.repair_projects.ledger
    (row,) = _state(world).ledger
    assert rs2_row.charged == 8 and rs2_row.envelope == 11             # RS2 keeps its own envelope
    assert row.envelope == 2 and row.charged <= 2 and row.rs2_charged == 8
    receipts = {(r.kind, r.region): r for r in _state(world).receipts}
    # 2 coins fund 3.333 irrigation work at 0.6 a unit, in split order.
    assert receipts[("irrigation", 1)].delivered + receipts[("irrigation", 2)].delivered == pytest.approx(10 / 3, abs=1e-5)
    road = receipts[("roads", 2)]
    assert road.status == "stalled" and road.reasons == ["no_envelope"] and road.envelope == 0
    assert treasury - world.civilizations[0].treasury == rs2_row.charged + row.charged


def test_pending_bills_add_the_two_separately_rounded_charges():
    """The reviewer's probe: RS2 plans 500 milli and the works 500 milli; the
    two are charged separately (1 + 1), so later planners must see 2."""
    world = _world(mode="repair", treasury=3, infrastructure=((0, IRR),))
    rs2 = world.livelihoods.repair_projects
    rs2._turn = RP._Turn(world.turn, None)
    rs2._turn.work = {0: SimpleNamespace(payer=0, planned_milli=500)}
    t = _state(world)._turn = IC._Turn(world.turn)
    t.prepared = True
    t.plans = [SimpleNamespace(payer=0, planned_milli=500)]
    assert RP.pending_bills(world) == [2, 0]
    # A tight treasury and PL1 planning after them (timber_supply._budgets):
    # RS2 0.5 unit and the works 1.5 units are charged 1 + 2 = 3, the whole
    # treasury, so nothing is left for expedition wages (one rounding left 1
    # and crashed PL1's settlement check).
    t.plans = [SimpleNamespace(payer=0, planned_milli=1500)]
    from chronicler import timber_supply
    assert RP.pending_bills(world) == [3, 0]
    assert timber_supply._budgets(world, None)[0] == 0


def test_the_works_are_their_own_screened_l9_proposal_with_audited_detail():
    world = _world(mode="repair", policy="maintain", infrastructure=((0, IRR), (1, IRR), (2, IRR), (2, ROADS)))
    lb = world.livelihoods.local_budgets = LocalBudgetState()
    lb.enabled = True
    world.grain_reserves.storage.assets[1].condition = 0.6      # region 1's storage will ask for work
    _worn(world, condition=0.52)
    state = _state(world)
    state._labour = (world.turn, [0, 5, 5])                     # region 0 has no farmer
    obs = SimpleNamespace(economy=SimpleNamespace(food_ledger={0: (0.0, 40.0), 1: (0.0, 40.0), 2: (0.0, 40.0)}),
                          held={}, turn=world.turn)
    (row,) = IC.works_proposal(world, 0, obs)
    assert row["service"] == IC.BUDGET_SERVICE and row["claims"] == ["infrastructure:0"] and row["recipients"] == [2]
    assert row["cost"] == 3 and row["expected"] == pytest.approx(4.0)             # 2.4 coins, its own rounding
    d = row["detail"]
    assert (d["works"], d["cost_milli"], d["screened_no_labor"], d["screened_granary_first"], d["screened_roads"]) \
        == (1, 2400, 1, 1, 1)
    assert row["relief"]["commons"] == pytest.approx(d["food_at_risk_relieved"]) and d["food_at_risk_relieved"] > 0
    # RS2's own proposal never carries the works.
    assert RP._repairs_proposal(world, 0, obs) == []
    # Far from the gate there is no food at risk within the horizon.
    _asset(world, 2, "irrigation").condition = 0.74
    (row,) = IC.works_proposal(world, 0, obs)
    assert "commons" not in row["relief"]
    from chronicler.local_budgets import _providers
    assert IC.BUDGET_PROVIDER in _providers() and IC.BUDGET_PROVIDER.group == "repairs"


def test_the_works_envelope_settles_from_the_works_own_ledger():
    world = _world(mode="repair", granary=0.5, infrastructure=((1, IRR),))
    lb = world.livelihoods.local_budgets = LocalBudgetState()
    lb.enabled = True
    lb.open = [_envelope_row("repairs", "repairs:0", 8, [0], 4.0),
               _envelope_row(IC.BUDGET_SERVICE, "infrastructure:0", 3, [1], 4.0, cid=1)]
    RP.phase10_before_reserves(world, None, None, None)
    _worn(world)
    econ, _bridge = _turn(world, _Sim(), stop_after_phase2=True)
    obs = SimpleNamespace(economy=econ)
    got = IC.works_settlement(world, SimpleNamespace(civ=0, expected=4.0, amount=3), obs)
    assert (got["outcome"], got["spent"], got["delivered"]) == ("kept", 3, pytest.approx(4.0))
    rs2 = RP.budget_settlement(world, SimpleNamespace(civ=0, expected=4.0, amount=8), obs)
    assert rs2["spent"] == 8 and "infrastructure_works" not in rs2["detail"]       # RS2 settles RS2 only


def test_food_at_risk_is_the_arable_ceiling_kept_over_the_horizon():
    world = _world(mode="repair", infrastructure=((0, IRR),))
    IC.reconcile(world)
    from chronicler.ecology import potential_capacity
    from chronicler.economy import FARM_CEILING_IRRIGATION, arable_capacity
    region = world.regions[0]
    got = IC.food_at_risk_relieved(world, 0, 0.5, 4.0, 10.0, 30.0)
    kept = sum(IC.service_of(0.7 - h * 0.01) - IC.service_of(0.5 - h * 0.01) for h in range(1, 11))
    expect = 30.0 * potential_capacity(region) * FARM_CEILING_IRRIGATION * kept / arable_capacity(world, region)
    assert got == pytest.approx(expect) and got > 0
    assert IC.food_at_risk_relieved(world, 0, 0.9, 4.0, 10.0, 30.0) == 0.0


def test_cost_only_pays_the_same_and_credits_nothing():
    a, b = _world(mode="repair", infrastructure=((0, IRR),)), _world(mode="cost_only", infrastructure=((0, IRR),))
    for w in (a, b):
        _worn(w)
        _turn(w, _Sim())
    ra, rb = _state(a).receipts[0], _state(b).receipts[0]
    assert (ra.delivered, ra.coin_cost_milli, ra.timber_used) == (rb.delivered, rb.coin_cost_milli, rb.timber_used)
    assert ra.credited == 4.0 and rb.credited == 0.0
    assert _asset(b, 0, "irrigation").condition == pytest.approx(0.49)
    assert _asset(a, 0, "irrigation").condition == pytest.approx(0.69)


def test_completion_and_a_failed_asset_is_repaired_not_rebuilt():
    world = _world(mode="repair", infrastructure=((0, IRR),))
    IC.reconcile(world)
    asset = _asset(world, 0, "irrigation")
    asset.condition = 0.005
    _p10(world)
    assert asset.status == "failed"
    (work,) = _state(world).works
    assert work.scope == pytest.approx(20.0)
    sim = _Sim()
    for _ in range(8):
        _turn(world, sim)
        if not _state(world).works:
            break
    assert _state(world).closed[-1].status == "completed" and asset.status == "serving"
    assert any(e[1] == "restored" for e in asset.history)
    assert _state(world).counters["assets_restored"] == 1


def test_wear_only_is_the_no_repair_control():
    world = _world(mode="wear_only", infrastructure=((0, IRR),))
    IC.reconcile(world)
    _asset(world, 0, "irrigation").condition = 0.3
    for _ in range(3):
        _turn(world, _Sim())
    state = _state(world)
    assert state.works == [] and state.receipts is None and state.ledger is None
    assert _asset(world, 0, "irrigation").condition == pytest.approx(0.27)
    assert IC.service(world, 0, "irrigation") == pytest.approx(0.54)


def _strip(world):
    w = copy.deepcopy(world)
    w.livelihoods.infrastructure_condition = None
    return w.model_dump(mode="json")


def test_record_only_equals_off_except_the_record():
    on = _world(mode="record_only", granary=0.5)
    off = _world(switch=False, granary=0.5)
    sim_on, sim_off = _Sim(), _Sim()
    for _ in range(4):
        for w, sim in ((on, sim_on), (off, sim_off)):
            RP.phase10_before_reserves(w, None, None, None)
            _turn(w, sim)
    assert _strip(on) == off.model_dump(mode="json")
    state = _state(on)
    assert state.works == [] and state.assets and all(a.wear > 0 for a in state.assets)
    snap = IC.snapshot_summary(on)
    assert all(row["service"] == 1.0 for row in snap["assets"]) and snap["receipts"] is None


def test_exact_resume_at_an_open_work_matches_the_straight_run():
    a = _world(mode="repair", infrastructure=((0, IRR), (1, ROADS)))
    _worn(a, condition=0.2)
    sim_a = _Sim()
    _turn(a, sim_a, labor=2.0)
    b = pickle.loads(pickle.dumps(a))
    assert _state(b)._turn is None and _state(b).works
    b2 = InfrastructureConditionState.model_validate_json(_state(a).model_dump_json())
    assert b2.model_dump() == _state(a).model_dump()
    sim_b = copy.deepcopy(sim_a)
    for _ in range(3):
        _turn(a, sim_a, labor=2.0)
        _turn(b, sim_b, labor=2.0)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
    json.dumps(IC.snapshot_summary(a))


def test_switching_off_abandons_works_and_service_returns_to_one():
    world = _world(mode="repair", infrastructure=((0, IRR),))
    _worn(world, condition=0.2)
    assert IC.service(world, 0, "irrigation") == pytest.approx(0.4 - 0.02)
    world.civilizations[0].treasury = 100
    IC.set_infrastructure_condition_enabled(world, False)
    state = _state(world)
    assert state.works == [] and state.closed[-1].closed_reason == "switched_off"
    assert IC.service(world, 0, "irrigation") == 1.0 and not IC.infrastructure_condition_active(world)


def test_flood_damage_records_its_cause_and_its_only_caller_is_the_flow_onset():
    world = _world(mode="wear_only", rs2=False)
    IC.flood_damage(world, 1, 0.4, ref="flood:1:5")
    state = _state(world)
    assert [(d.event, d.ref, round(d.amount, 9)) for d in state.damages] == [
        ("flood", "flood:1:5", 0.2), ("flood", "flood:1:5", 0.2)]
    IC.flood_damage(world, 1, 0.4)                       # one damage per asset per turn
    assert len(state.damages) == 2
    callers = sorted(p.name for p in (ROOT / "src/chronicler").rglob("*.py")
                     if "flood_damage(" in p.read_text(encoding="utf-8") and p.name != "infrastructure_condition.py")
    assert callers == ["watershed.py"]


# ---------------------------------------------------------------------------
# Watershed flow x condition (both opt-in: only the combined mode changes)
# ---------------------------------------------------------------------------

def _flow_condition_world(monkeypatch, *, condition=0.3, mode="wear_only", watershed_mode="flow"):
    from tests.test_watershed import _flow_world, _headwater_chain
    from tests.test_watershed import _world as _ws_world
    world = _flow_world(monkeypatch) if watershed_mode == "flow" else _ws_world(11)
    state = world.livelihoods.watershed
    up, down = _headwater_chain(state)
    world.regions[down].infrastructure.append(Infrastructure(type=IRR, builder_civ="x", built_turn=0))
    world.regions[down].infrastructure.append(Infrastructure(type=ROADS, builder_civ="x", built_turn=0))
    world.agent_mode = "hybrid"
    if mode is not None:
        world.livelihoods.infrastructure_condition = InfrastructureConditionState(mode=mode)
        IC.reconcile(world)
        for a in _state(world).assets:
            a.condition = condition
    return world, up, down


@pytest.mark.parametrize("watershed_mode,mode,expect", [
    ("flow", "wear_only", 0.6),          # flow x condition: the withdrawal capacity scales with service
    ("flow", None, 1.0),                 # flow alone: main's rule
    ("flow", "record_only", 1.0),        # the condition switch records only
    ("record_only", "wear_only", 1.0),   # the B1 account keeps the >= 0.5 gate (service 0.6 serves)
])
def test_flow_withdrawal_scales_with_service_and_the_account_closes(monkeypatch, watershed_mode, mode, expect):
    from chronicler import watershed as ws
    world, _up, down = _flow_condition_world(monkeypatch, mode=mode, watershed_mode=watershed_mode)
    state = world.livelihoods.watershed
    turn, key, trend, inputs = ws.region_inputs(world, state)
    assert inputs[down].irrigated and inputs[down].irrigation_service == pytest.approx(expect)
    plan = ws.account_step(state.graph, state.storage, state.last_index, turn, key, trend, inputs)  # closure checked
    full = ws.account_step(state.graph, state.storage, state.last_index, turn, key, trend,
                           [i._replace(irrigation_service=1.0) for i in inputs])
    demand = ws.PARAMETERS.irrigation_demand
    t = plan.columns["withdrawal"][down]
    assert t == pytest.approx(min(full.columns["withdrawal"][down], demand * expect))
    assert abs(plan.residual) <= 1e-9 * max(1.0, sum(plan.columns["precipitation"]))
    if expect == 1.0:
        assert plan.columns == full.columns           # 1.0 x demand == demand: bit-identical columns


def test_a_failed_work_withdraws_nothing_under_flow(monkeypatch):
    from chronicler import watershed as ws
    world, _up, down = _flow_condition_world(monkeypatch, condition=0.0)
    state = world.livelihoods.watershed
    IC.phase10_before_reserves(world, None, None, None)           # condition 0 -> failed
    assert _asset(world, down, "irrigation").status == "failed"
    turn, key, trend, inputs = ws.region_inputs(world, state)
    plan = ws.account_step(state.graph, state.storage, state.last_index, turn, key, trend, inputs)
    assert inputs[down].irrigation_service == 0.0 and plan.columns["withdrawal"][down] == 0.0


def _onset(world, up, down):
    from tests.test_watershed import _set_storage, _settle
    from chronicler.watershed import after_ecology, before_ecology
    state = world.livelihoods.watershed
    _settle(world, down)
    _set_storage(state, up, 10.0)
    before_ecology(world, acc=None, native=True)
    return state, before_ecology, after_ecology


def test_a_flood_onset_damages_the_works_once_with_its_event_as_cause(monkeypatch):
    world, up, down = _flow_condition_world(monkeypatch, condition=1.0)
    state, before_ecology, after_ecology = _onset(world, up, down)
    assert down in state._plan.consequences
    b3 = _state(world)
    onset_turn = world.turn
    excess = state._plan.columns["flood_excess"][down]
    damage = [(d.aid, d.event, d.ref, d.turn) for d in b3.damages]
    expected = min(IC.FLOOD_DAMAGE_CAP, IC.FLOOD_DAMAGE_PER_EXCESS * excess)
    assert sorted(damage) == sorted((a.aid, "flood", f"flood:{down}:{onset_turn}", onset_turn) for a in b3.assets)
    assert all(d.amount == pytest.approx(expected) for d in b3.damages)
    after_ecology(world, acc=None)
    IC.phase10_before_reserves(world, None, None, None)
    world.turn += 1
    assert any(e.region == down and e.end_turn is None for e in state.flood_events)    # the event is still open
    from tests.test_watershed import _set_storage
    _set_storage(state, up, 10.0)                                                     # still above the channel
    before_ecology(world, acc=None, native=True)
    assert down not in state._plan.consequences and len(b3.damages) == 2             # never on an ongoing flood
    assert b3.counters["damages_flood"] == 2


def test_a_flood_withheld_by_a_disaster_cooldown_damages_nothing(monkeypatch):
    world, up, down = _flow_condition_world(monkeypatch, condition=1.0)
    world.regions[down].disaster_cooldowns["earthquake"] = 4
    state, _b, _a = _onset(world, up, down)
    assert down in state._plan.withheld and down not in state._plan.consequences
    assert _state(world).damages == []                 # consistent with B2: a withheld flood does nothing


def test_resume_inside_an_open_flood_with_damaged_works_damages_nothing_twice(monkeypatch):
    world, up, down = _flow_condition_world(monkeypatch, condition=1.0)
    state, before_ecology, after_ecology = _onset(world, up, down)
    after_ecology(world, acc=None)
    IC.phase10_before_reserves(world, None, None, None)
    IC.phase10(world, None, None, None)
    world.turn += 1
    resumed = pickle.loads(pickle.dumps(world))
    for w in (world, resumed):
        from tests.test_watershed import _set_storage
        _set_storage(w.livelihoods.watershed, up, 10.0)
        before_ecology(w, acc=None, native=True)
        after_ecology(w, acc=None)
        IC.phase10_before_reserves(w, None, None, None)
        IC.phase10(w, None, None, None)
        w.turn += 1
    assert world.model_dump(mode="json") == resumed.model_dump(mode="json")
    assert _state(resumed).counters["damages_flood"] == 2


# ---------------------------------------------------------------------------
# Switch, prerequisites, records
# ---------------------------------------------------------------------------

def _args(**kw):
    from chronicler.livelihoods import LIVELIHOODS_ARG_KEYS, LIVELIHOODS_PATH_KEYS
    base = {k: None for k in LIVELIHOODS_ARG_KEYS + LIVELIHOODS_PATH_KEYS}
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("agents,kw,message", [
    ("hybrid", dict(infrastructure_condition_mode="wear_only"), "requires --infrastructure-condition"),
    ("hybrid", dict(infrastructure_condition=False, infrastructure_condition_mode="wear_only"),
     "requires --infrastructure-condition"),
    ("off", dict(infrastructure_condition=True, infrastructure_condition_mode="record_only"), "requires --agents hybrid"),
    ("shadow", dict(infrastructure_condition=True, infrastructure_condition_mode="wear_only"), "requires --agents hybrid"),
    ("hybrid", dict(infrastructure_condition=True), "requires --repair-projects"),
    ("hybrid", dict(infrastructure_condition=True, infrastructure_condition_mode="cost_only"), "requires --repair-projects"),
])
def test_invalid_combinations_are_refused(agents, kw, message):
    from chronicler.livelihoods import configure_livelihoods
    world = _world(rs2=False, switch=False)
    world.livelihoods = None
    with pytest.raises(ValueError, match=message):
        configure_livelihoods(world, _args(**kw), agent_mode=agents)
    assert world.livelihoods is None


@pytest.mark.parametrize("mode", ["record_only", "wear_only"])
def test_record_and_wear_modes_need_only_hybrid(mode):
    from chronicler.livelihoods import configure_livelihoods
    world = _world(rs2=False, switch=False)
    world.livelihoods = None
    configure_livelihoods(world, _args(infrastructure_condition=True, infrastructure_condition_mode=mode),
                          agent_mode="hybrid")
    assert _state(world).mode == mode and IC.infrastructure_condition_active(world)


def test_a_saved_record_refuses_a_mode_change_and_a_resume_without_its_prerequisites():
    from chronicler.livelihoods import configure_livelihoods, livelihoods_resume_conflicts
    world = _world(mode="repair")
    with pytest.raises(ValueError, match="mode change on resume is refused"):
        configure_livelihoods(world, _args(infrastructure_condition_mode="wear_only"), agent_mode="hybrid")
    with pytest.raises(ValueError, match="pass --no-infrastructure-condition"):
        configure_livelihoods(world, _args(repair_projects=False), agent_mode="hybrid")
    with pytest.raises(ValueError, match="pass --no-infrastructure-condition"):
        configure_livelihoods(world, _args(), agent_mode="demographics-only")
    assert livelihoods_resume_conflicts(world, _args(infrastructure_condition_mode="cost_only"), {}) == [
        "--infrastructure-condition-mode 'cost_only' conflicts with the checkpoint (saved: 'repair')"]
    configure_livelihoods(world, _args(infrastructure_condition=False), agent_mode="hybrid")
    assert not _state(world).enabled


def test_counters_are_declared_and_the_record_is_dated_and_serializable():
    world = _world(mode="repair", infrastructure=((0, IRR),))
    _worn(world)
    _turn(world, _Sim())
    assert set(_state(world).counters) <= COUNTERS
    snap = IC.snapshot_summary(world)
    assert snap["stage"] == "B3" and snap["source_turn"] == world.turn - 1 and snap["works_enabled"]
    assert snap["receipts"] and snap["ledger"] and snap["unmet"] == []
    json.dumps(snap)
    world.turn += 1                                      # a stale frame: unknown, not zero
    stale = IC.snapshot_summary(world)
    assert stale["receipts"] is None and stale["ledger"] is None and stale["unmet"] is None


def test_the_payment_is_registered_with_the_seam():
    from chronicler import money
    from chronicler.wealth_accounting_state import MONEY_BILLS
    assert MONEY_BILLS[("infrastructure_condition", "_bill")] == ("infrastructure_repair",)
    assert money.PURPOSES["infrastructure_repair"] is None and "public_works" in money.SINKS
    assert "infrastructure_condition" in money.MONEY_BOOKS
    tree = ast.parse((ROOT / "src/chronicler/infrastructure_condition.py").read_text(encoding="utf-8"))
    assert not any(isinstance(n, ast.Attribute) and n.attr == "treasury" and isinstance(n.ctx, ast.Store)
                   for n in ast.walk(tree))           # the treasury moves only through the seam
