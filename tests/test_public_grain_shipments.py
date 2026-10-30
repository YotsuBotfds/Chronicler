"""Prospective bounded public transport contracts; authored, not yet run.

Direct goods-economy fixtures exercise the real public reserve/payment code.
They need no agent/native simulator. Official fresh-native integration and
cross-source whole-run/raw-output parity remain separate required gates.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import pickle
import random
import struct

import pytest

from chronicler import finance as F, grain_reserves as G
from chronicler import public_grain_shipments as S
from chronicler.accumulator import StatAccumulator
from chronicler.economy import EconomyResult
from chronicler.grain_reserves_state import ARRIVED, BOUGHT, DISPATCHED, GrainReserveState
from chronicler.models import WorldState
from chronicler.public_grain_shipments_state import MAX_PENDING, MAX_ORDER
from chronicler.world_gen import generate_world

ROOT = Path(__file__).resolve().parents[1]
DEST, SOURCE, BUYER, SELLER = 2, 3, 2, 3


def economy(world, sufficiency=1.0):
    result = EconomyResult()
    for region in world.regions:
        result.food_sufficiency[region.name] = sufficiency
        result.market_demand[region.name] = (10.0, 0.0, 0.0, 0.0)
        result.market_supply[region.name] = (10.0 * sufficiency, 0.0, 0.0, 0.0)
        result.slot_output[region.name] = [0.0, 0.0, 0.0]
        result.forage_output[region.name] = 10.0
    return result


@pytest.fixture
def world(monkeypatch):
    world = generate_world(seed=42)
    world.agent_mode = "demographics-only"
    world.turn = 30
    G.set_grain_reserves_enabled(world, True)
    G._ensure(world)
    for civ in world.civilizations:
        civ.treasury = 0
    world.civilizations[BUYER].treasury = 200
    for region in world.regions:
        region.population = 20
        region.stockpile.goods.clear()
    world.regions[SOURCE].stockpile.goods["grain"] = 1000.0
    granary = world.grain_reserves.granaries[DEST]
    granary.owner = BUYER
    granary.observed = 24
    granary.harvest_mean = 0.5
    granary.harvest_sq = 0.5
    granary.target = 40.0
    monkeypatch.setattr(G, "_route_graph", lambda world: {DEST: (SOURCE,)})
    S.set_public_grain_shipments_enabled(world, True)
    G.open_granaries(world, economy(world))
    S.settle_arrivals(world)
    return world


def vectors(world):
    surplus = [0.0] * len(world.regions)
    surplus[SOURCE] = 100.0
    budget = [0] * len(world.civilizations)
    budget[BUYER] = 18
    return surplus, budget, S.inbound_by_destination(world)


def dispatch(world, *, acc=None, amount=2.0, cost=2, values=None):
    surplus, budget, inbound = values or vectors(world)
    return S.dispatch_order(world, buyer=BUYER, seller=SELLER, source=SOURCE,
                            dest=DEST, sent=amount, net=amount * (1-G._transit_loss()),
                            cost=cost, graph={DEST: (SOURCE,)}, surplus=surplus,
                            budget=budget, inbound=inbound, flows=world.grain_reserves.flows,
                            acc=acc)


def witness(world, values, acc=None):
    state = world.grain_reserves.shipments
    result = {"json": world.model_dump_json(), "rng": random.getstate(),
              "containers": tuple(id(v) for v in
                  (world.civilizations, world.regions, state.pending, state.frame,
                   state.counters, world.grain_reserves.counters, world.grain_reserves.flows,
                   world.regions[SOURCE].stockpile.goods, *values)),
              "parties": [(id(c), id(c.__pydantic_fields_set__), set(c.__pydantic_fields_set__))
                          for c in (world.civilizations[BUYER], world.civilizations[SELLER])],
              "vectors": deepcopy(values)}
    if world.finance is not None:
        st = world.finance
        result["finance"] = (id(st), tuple(id(getattr(st,n)) for n in
                              ("civs", "region_output", "region_specie", "region_occupier", "totals")),
                             b"".join(struct.pack("!d", v) for v in st.region_specie),
                             list(st.totals.items()))
    if acc is not None:
        result["acc"] = (id(acc), id(acc._changes), acc._keep_applied_up_to,
                         [(id(c), deepcopy(c)) for c in acc._changes])
    return result


def test_real_kernel_misses_one_opening_then_delivers_and_releases(world, monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    G.open_granaries(world, economy(world))
    before = [c.treasury for c in world.civilizations]
    G.tick_grain_reserves(world, economy_result=economy(world))
    state = world.grain_reserves.shipments
    assert len(state.pending) == 1
    order = state.pending[0]
    assert order.dispatch_turn == 30 and order.due_turn == 31
    assert world.grain_reserves.granaries[DEST].grain == 0.0
    assert world.civilizations[BUYER].treasury == before[BUYER] - order.paid
    assert world.civilizations[SELLER].treasury == before[SELLER] + order.paid
    assert sum(c.treasury for c in world.civilizations) == sum(before)
    # No more procurement: isolate this order's physical availability.
    S.set_public_grain_shipments_enabled(world, False)
    world.civilizations[BUYER].treasury = 0
    world.civilizations[SELLER].treasury = 0
    world.turn += 1
    result = economy(world, 0.2)
    G.open_granaries(world, result)
    assert result.food_sufficiency[world.regions[DEST].name] == 0.2
    G.tick_grain_reserves(world, economy_result=result)
    assert state.pending == [] and state.counters["arrived"] == 1
    assert world.grain_reserves.granaries[DEST].grain == pytest.approx(order.net)
    assert result.food_sufficiency[world.regions[DEST].name] == 0.2
    assert sum(flow.cost for flow in world.grain_reserves.flows if flow.kind == ARRIVED) == 0
    assert S.settle_arrivals(world) == []
    world.turn += 1
    result = economy(world, 0.2)
    G.open_granaries(world, result)
    assert result.food_sufficiency[world.regions[DEST].name] > 0.2
    assert world.grain_reserves.granaries[DEST].grain < order.net


@pytest.mark.parametrize("finance", [False, True])
@pytest.mark.parametrize("accumulator", [False, True])
@pytest.mark.parametrize("fault", ["payer", "payee", "specie", "partial", "nonfinite_post"])
def test_payment_failures_restore_exact_owned_state(world, monkeypatch, finance, accumulator, fault):
    if fault in ("specie", "nonfinite_post") and not finance:
        # Still a meaningful paid-then-fail case when finance is off.
        fault = "payee"
    F.set_finance_enabled(world, finance)
    if finance:
        # _ensure must fill legal empty state; retain custom missing defaults.
        world.finance.totals.clear()
        world.finance.totals["retained"] = 7
    acc = StatAccumulator() if accumulator else None
    if acc is not None:
        acc.add(BUYER, world.civilizations[BUYER], "treasury", 3, "keep")
    # Treasury exists as a default-valued model field but was never explicitly set.
    for ci in (BUYER, SELLER):
        world.civilizations[ci].__pydantic_fields_set__.discard("treasury")
    values = vectors(world)
    before = witness(world, values, acc)
    if fault in ("payer", "payee"):
        original = F._Book.add
        def failing(book, ci, delta):
            result = original(book, ci, delta)
            if (fault == "payer" and ci == BUYER and delta < 0) or (fault == "payee" and ci == SELLER and delta > 0):
                raise RuntimeError("injected payment leg")
            return result
        monkeypatch.setattr(F._Book, "add", failing)
    elif fault == "partial":
        original = F.transfer
        def partial(*args, **kwargs):
            return original(*args, **kwargs) - 1
        monkeypatch.setattr(F, "transfer", partial)
    else:
        original = F._move_specie
        def failing(*args, **kwargs):
            result = original(*args, **kwargs)
            if fault == "nonfinite_post":
                # Affect the actual buyer anchor, not an assumed destination.
                index = F._region_indices(world)
                rid = F._anchor_region(world, world.civilizations[BUYER], index)
                world.finance.region_specie[rid] = float("nan")
                return result
            raise RuntimeError("injected specie write")
        monkeypatch.setattr(F, "_move_specie", failing)
    with pytest.raises((RuntimeError, ValueError)):
        dispatch(world, acc=acc, values=values)
    assert witness(world, values, acc) == before


class FailAppend(list):
    def append(self, value):
        super().append(value)
        if not getattr(self, "failed", False):
            self.failed = True
            raise RuntimeError("injected append")


class FailWrite(dict):
    def __init__(self, values, key):
        super().__init__(values)
        self.key, self.failed = key, False

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == self.key and not self.failed:
            self.failed = True
            raise RuntimeError("injected field write")


@pytest.mark.parametrize("location", ["grain", "state_counter", "reserve_counter", "next_order"])
def test_inventory_counter_and_identity_failures_restore_payment(world, location):
    F.set_finance_enabled(world, True)
    state = world.grain_reserves.shipments
    if location == "grain":
        stock = world.regions[SOURCE].stockpile
        stock.__dict__["goods"] = FailWrite(stock.goods, "grain")
    elif location == "state_counter":
        state.__dict__["counters"] = FailWrite(state.counters, "paid")
    elif location == "reserve_counter":
        reserves = world.grain_reserves
        reserves.__dict__["counters"] = FailWrite(reserves.counters, "paid_foreign")
    else:
        object.__setattr__(state, "__dict__", FailWrite(state.__dict__, "next_order"))
    values = vectors(world)
    before = witness(world, values)
    with pytest.raises(RuntimeError, match="injected field write"):
        dispatch(world, values=values)
    assert witness(world, values) == before


@pytest.mark.parametrize("location", ["finance_civs", "finance_output", "finance_specie", "finance_occupier", "pending", "frame", "flows"])
def test_partial_initialization_and_container_failures_restore_identities(world, location):
    F.set_finance_enabled(world, True)
    state = world.grain_reserves.shipments
    if location.startswith("finance_"):
        key = {"finance_civs": "civs", "finance_output": "region_output",
               "finance_specie": "region_specie", "finance_occupier": "region_occupier"}[location]
        world.finance.__dict__[key] = FailAppend()
    elif location == "flows":
        world.grain_reserves.__dict__["flows"] = FailAppend(world.grain_reserves.flows)
    else:
        state.__dict__[location] = FailAppend(getattr(state, location))
    values = vectors(world)
    before = witness(world, values)
    with pytest.raises(RuntimeError, match="injected append"):
        dispatch(world, values=values)
    assert witness(world, values) == before


def test_shared_anchor_signed_zero_and_existing_finance_prefix_rollback(world, monkeypatch):
    F.set_finance_enabled(world, True)
    F._ensure(world)
    buyer = world.civilizations[BUYER]
    seller = world.civilizations[SELLER]
    seller.regions = list(buyer.regions)
    seller.capital_region = buyer.capital_region
    anchor = F._anchor_region(world, buyer, F._region_indices(world))
    world.finance.region_specie[anchor] = -0.0
    original = F._move_specie
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("shared-anchor failure")
    monkeypatch.setattr(F, "_move_specie", fail)
    values = vectors(world)
    before = witness(world, values)
    with pytest.raises(RuntimeError):
        dispatch(world, values=values)
    assert witness(world, values) == before
    assert struct.pack("!d", world.finance.region_specie[anchor]) == struct.pack("!d", -0.0)


def test_prior_accumulator_flush_watermark_and_unapplied_prefix_survive(world, monkeypatch):
    F.set_finance_enabled(world, True)
    acc = StatAccumulator()
    acc.add(BUYER, world.civilizations[BUYER], "treasury", 3, "keep")
    acc.apply_keep(world)
    acc.add(SELLER, world.civilizations[SELLER], "treasury", 7, "keep")
    assert acc._keep_applied_up_to == 1
    original = F.transfer
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("after transfer")
    monkeypatch.setattr(F, "transfer", fail)
    values = vectors(world)
    before = witness(world, values, acc)
    with pytest.raises(RuntimeError):
        dispatch(world, values=values, acc=acc)
    assert witness(world, values, acc) == before


def test_aligned_short_finance_prefix_survives_interrupted_append_sequence(world):
    F.set_finance_enabled(world, True)
    F._ensure(world)
    st = world.finance
    for name in ("civs", "region_output", "region_specie", "region_occupier"):
        del getattr(st, name)[1:]
    st.__dict__["region_specie"] = FailAppend(st.region_specie)
    values = vectors(world)
    before = witness(world, values)
    with pytest.raises(RuntimeError):
        dispatch(world, values=values)
    assert witness(world, values) == before


def test_finite_payment_overflows_destination_specie_and_rolls_back(world):
    F.set_finance_enabled(world, True)
    F._ensure(world)
    index = F._region_indices(world)
    payer_anchor = F._anchor_region(world, world.civilizations[BUYER], index)
    payee_anchor = F._anchor_region(world, world.civilizations[SELLER], index)
    assert payer_anchor != payee_anchor
    # Synthetic finite-account boundary, not a calibrated market trajectory.
    world.finance.region_specie[payer_anchor] = 1e308
    world.finance.region_specie[payee_anchor] = 1.7976931348623157e308
    world.civilizations[BUYER].treasury = 10**308
    values = vectors(world)
    values[1][BUYER] = 10**307
    before = witness(world, values)
    with pytest.raises(ValueError, match="invalid anchor specie"):
        dispatch(world, values=values, cost=10**307)
    assert witness(world, values) == before


@pytest.mark.parametrize("enabled", [False, True])
def test_farther_foreign_source_has_no_immediate_fallback_when_enabled(world, monkeypatch, enabled):
    if not enabled:
        world.grain_reserves.shipments = None
    own = 4  # Thornwood and destination Verdant are both Thornwall's.
    monkeypatch.setattr(G, "_route_graph", lambda world: {DEST:(own,), own:(SOURCE,)})
    before = world.civilizations[BUYER].treasury
    G.tick_grain_reserves(world, economy_result=economy(world))
    if enabled:
        assert world.grain_reserves.shipments.pending == []
        assert world.grain_reserves.granaries[DEST].grain == 0
        assert world.civilizations[BUYER].treasury == before
    else:
        assert world.grain_reserves.granaries[DEST].grain > 0
        assert world.civilizations[BUYER].treasury < before


@pytest.mark.parametrize("enabled", [False, True])
def test_domestic_one_hop_keeps_immediate_priced_producer_sink(world, enabled):
    if not enabled:
        world.grain_reserves.shipments = None
    buyer = world.civilizations[BUYER]
    world.regions[SOURCE].controller = buyer.name
    buyer.regions.append(world.regions[SOURCE].name)
    G.open_granaries(world, economy(world))
    opening = sum(c.treasury for c in world.civilizations)
    G.tick_grain_reserves(world, economy_result=economy(world))
    flows = [flow for flow in world.grain_reserves.flows if flow.kind == BOUGHT]
    assert len(flows) == 1 and flows[0].seller == flows[0].buyer == BUYER
    assert flows[0].cost > 0 and world.grain_reserves.granaries[DEST].grain > 0
    assert sum(c.treasury for c in world.civilizations) == opening - flows[0].cost
    if enabled:
        assert world.grain_reserves.shipments.pending == []


def test_paid_inbound_prevents_buying_the_same_stock_target_again(world, monkeypatch):
    dispatch(world)
    state = world.grain_reserves.shipments
    world.grain_reserves.granaries[DEST].target = state.pending[0].net
    monkeypatch.setattr(G, "_observe", lambda *args: None)
    before = [c.treasury for c in world.civilizations]
    G.tick_grain_reserves(world, economy_result=economy(world))
    assert len(state.pending) == 1 and state.next_order == 1
    assert [c.treasury for c in world.civilizations] == before


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
@pytest.mark.parametrize("field", ["fineness", "specie"])
def test_nonfinite_or_negative_finance_inputs_refuse_before_payment(world, bad, field):
    F.set_finance_enabled(world, True)
    F._ensure(world)
    if field == "fineness":
        world.finance.civs[BUYER].fineness = bad
    else:
        anchor = F._anchor_region(world, world.civilizations[BUYER], F._region_indices(world))
        world.finance.region_specie[anchor] = bad
    values = vectors(world)
    before = witness(world, values)
    with pytest.raises(ValueError):
        dispatch(world, values=values)
    assert witness(world, values) == before


@pytest.mark.parametrize("reason", ["closed", "wrong_controller", "bad_destination", "aliased_civ", "budget"])
def test_preflight_has_no_payment_or_identity_use(world, reason):
    values = vectors(world)
    if reason == "wrong_controller":
        world.regions[SOURCE].controller = world.civilizations[BUYER].name
    elif reason == "bad_destination":
        world.grain_reserves.granaries[DEST].owner = -1
    elif reason == "aliased_civ":
        world.civilizations[SELLER] = world.civilizations[BUYER]
    elif reason == "budget":
        values[1][BUYER] = 0
    before = witness(world, values)
    if reason == "closed":
        with pytest.raises(ValueError):
            S.dispatch_order(world, buyer=BUYER, seller=SELLER, source=SOURCE, dest=DEST,
                sent=2.0, net=2.0*(1-G._transit_loss()), cost=2, graph={},
                surplus=values[0], budget=values[1], inbound=values[2], flows=world.grain_reserves.flows)
    else:
        with pytest.raises(ValueError):
            dispatch(world, values=values)
    assert witness(world, values) == before


def test_destination_cap_and_identity_exhaustion_skip_before_debit(world):
    dispatch(world)
    dispatch(world)
    values = vectors(world)
    cash = [c.treasury for c in world.civilizations]
    grain = world.regions[SOURCE].stockpile.goods["grain"]
    next_order = world.grain_reserves.shipments.next_order
    assert dispatch(world, values=values) is None
    assert len(world.grain_reserves.shipments.pending) == 2
    assert world.grain_reserves.shipments.next_order == next_order
    assert [c.treasury for c in world.civilizations] == cash
    assert world.regions[SOURCE].stockpile.goods["grain"] == grain
    state = world.grain_reserves.shipments
    state.pending.clear()
    state.next_order = MAX_ORDER
    assert dispatch(world) is None
    assert [c.treasury for c in world.civilizations] == cash


def test_global_cap_refuses_without_eviction_or_fallback(world):
    # Synthetic saved-cargo boundary, not a claimed physical trajectory.
    dispatch(world)
    state = world.grain_reserves.shipments
    row = state.pending[0]
    while len(world.regions) < 33:
        rid = len(world.regions)
        world.regions.append(world.regions[DEST].model_copy(update={"name": f"capacity {rid}"}, deep=True))
    G._ensure(world)
    destinations = [rid for rid in range(33) if rid != SOURCE]
    state.pending[:] = [row.model_copy(update={"order": i, "dest": destinations[i//2],
                                               "dest_name": world.regions[destinations[i//2]].name})
                        for i in range(MAX_PENDING)]
    state.next_order = MAX_PENDING
    state.frame.clear()
    S.validate_shipments(world)
    before = [c.treasury for c in world.civilizations], world.regions[SOURCE].stockpile.goods["grain"]
    assert dispatch(world) is None
    assert len(state.pending) == MAX_PENDING
    assert ([c.treasury for c in world.civilizations], world.regions[SOURCE].stockpile.goods["grain"]) == before


@pytest.mark.parametrize("custody", ["conquest_before_open", "conquest_after_open", "dead_buyer", "unguarded"])
def test_delivery_title_and_existing_keeper_settlement(world, custody):
    dispatch(world)
    order = world.grain_reserves.shipments.pending[0]
    world.turn += 1
    if custody == "conquest_before_open":
        world.regions[DEST].controller = world.civilizations[SELLER].name
    elif custody == "unguarded":
        world.regions[DEST].controller = None
    elif custody == "dead_buyer":
        world.civilizations[BUYER].regions.clear()
    G.open_granaries(world, economy(world))
    if custody == "conquest_after_open":
        world.regions[DEST].controller = world.civilizations[SELLER].name
    cash = [c.treasury for c in world.civilizations]
    S.settle_arrivals(world)
    assert [c.treasury for c in world.civilizations] == cash
    assert world.grain_reserves.shipments.pending == []
    assert world.grain_reserves.granaries[DEST].grain == pytest.approx(order.net)
    transition = world.grain_reserves.shipments.frame[0]
    assert transition.buyer == BUYER and transition.paid == order.paid
    if custody == "conquest_before_open":
        assert transition.keeper == SELLER
    elif custody == "unguarded":
        assert transition.keeper == -1
    else:
        assert transition.keeper == BUYER
    world.turn += 1
    before_market = world.regions[DEST].stockpile.goods.get("grain", 0.0)
    G.open_granaries(world, economy(world))
    if custody == "unguarded":
        assert world.grain_reserves.granaries[DEST].grain == 0
        assert world.regions[DEST].stockpile.goods["grain"] == pytest.approx(before_market + order.net)
    elif custody == "conquest_after_open":
        assert world.grain_reserves.granaries[DEST].owner == SELLER


@pytest.mark.parametrize("mutation", ["removed", "renamed", "future", "duplicate", "nan", "negative", "overflow"])
def test_invalid_saved_orders_refuse_before_arrival_mutation(world, mutation):
    dispatch(world)
    state = world.grain_reserves.shipments
    row = state.pending[0]
    if mutation == "removed":
        world.regions.pop(DEST)
    elif mutation == "renamed":
        world.regions[DEST].name += " changed"
    elif mutation == "future":
        row.dispatch_turn += 10
    elif mutation == "duplicate":
        state.pending.append(row.model_copy())
    elif mutation == "nan":
        row.net = float("nan")
    elif mutation == "negative":
        row.net = -1.0
    else:
        row.sent = row.net = 1e308
        row.loss = 0.0
        state.pending.append(row.model_copy(update={"order": 1}))
        state.next_order = 2
    before = world.model_dump_json()
    with pytest.raises(ValueError):
        S.validate_shipments(world)
    assert world.model_dump_json() == before


def test_disable_drain_dormancy_overdue_and_no_economy(world):
    dispatch(world)
    state = world.grain_reserves.shipments
    with pytest.raises(ValueError, match="paid public grain pending"):
        G.set_grain_reserves_enabled(world, False)
    S.set_public_grain_shipments_enabled(world, False)
    assert not state.accept_orders and state.next_order == 1
    original = state.model_dump_json()
    world.agent_mode = "off"
    assert S.settle_arrivals(world) == []
    assert G.tick_grain_reserves(world, economy_result=economy(world)) == []
    assert state.model_dump_json() == original
    world.agent_mode = "demographics-only"
    world.turn += 4
    G.tick_grain_reserves(world, economy_result=None)
    assert state.model_dump_json() == original
    G.open_granaries(world, economy(world))
    S.settle_arrivals(world)
    assert len(state.frame) == 1 and state.frame[0].turn == world.turn
    assert state.pending == [] and state.next_order == 1
    S.set_public_grain_shipments_enabled(world, True)
    dispatch(world)
    assert state.pending[0].order == 1


@pytest.mark.parametrize("format", ["json", "exact"])
def test_midtransit_roundtrip_resumes_once_without_repayment(world, tmp_path, format):
    """Bare World/manual tick contract only; not Native/live integration."""
    dispatch(world)
    # Real complete-turn boundary: clear the optional diagnostic-only ledger.
    world.grain_reserves._ledger = None
    world.turn += 1
    if format == "json":
        path = tmp_path / "world.json"
        world.save(path)
        restored = WorldState.load(path)
    else:
        from chronicler.run_checkpoint import save_world, load_world
        path = tmp_path / "world.ckpt"
        save_world(path, world)
        restored = load_world(path)
    assert restored.model_dump_json() == world.model_dump_json()
    for candidate in (world, restored):
        G.open_granaries(candidate, economy(candidate))
        cash = [c.treasury for c in candidate.civilizations]
        S.settle_arrivals(candidate)
        assert [c.treasury for c in candidate.civilizations] == cash
        assert S.settle_arrivals(candidate) == []
    assert restored.model_dump_json() == world.model_dump_json()
    assert restored.grain_reserves.shipments.next_order == 1


def test_old_missing_nested_json_and_pickle_default_is_omitted():
    state = GrainReserveState()
    assert "shipments" not in json.loads(state.model_dump_json())
    old_pickle = state.__getstate__()
    old_pickle["__dict__"].pop("shipments", None)
    back = GrainReserveState.__new__(GrainReserveState)
    back.__setstate__(old_pickle)
    assert back.shipments is None
    assert back.model_dump_json() == state.model_dump_json()
    assert pickle.loads(pickle.dumps(back)).model_dump_json() == state.model_dump_json()


def test_source_inverse_is_literal_complete_and_refuses_unrelated_edits():
    witness = json.loads((ROOT / "tests/fixtures/public_grain_shipments_source_inverse.json").read_text())
    assert set(witness) == {"schema_version", "base", "files", "new_files"}
    assert witness["base"] == "d921823f52912d8cba664d9a3e08fc3dcda89de1"
    for path, digest in witness["new_files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    for path, row in witness["files"].items():
        body = (ROOT / path).read_text()
        for patch in reversed(row["patches"]):
            assert set(patch) == {"old", "new"}
            assert body.count(patch["new"]) == 1
            body = body.replace(patch["new"], patch["old"], 1)
        assert hashlib.sha256(body.encode()).hexdigest() == row["sha256"]
        assert hashlib.sha256((body + "\n# unrelated mutation\n").encode()).hexdigest() != row["sha256"]


def test_never_enabled_explicit_off_has_raw_json_rng_and_payment_parity(world):
    # Same-source off variants plus complete old-source inverse above; actual
    # cross-source bundle/native parity is a held independent runtime gate.
    world.grain_reserves.shipments = None
    left, right = deepcopy(world), deepcopy(world)
    before_rng = random.getstate()
    S.set_public_grain_shipments_enabled(right, False)
    G.tick_grain_reserves(left, economy_result=economy(left))
    G.tick_grain_reserves(right, economy_result=economy(right))
    assert left.model_dump_json() == right.model_dump_json()
    assert random.getstate() == before_rng
    assert "shipments" not in json.loads(right.grain_reserves.model_dump_json())


def test_cli_and_manifest_default_contract():
    from chronicler.main import _build_parser
    from chronicler.batch_manifest import simulation_config, SIMULATION_ARG_KEYS
    parser = _build_parser()
    default = parser.parse_args([])
    assert default.public_grain_shipments is None
    assert "public_grain_shipments" not in simulation_config(default)
    assert "public_grain_shipments" in SIMULATION_ARG_KEYS
    assert parser.parse_args(["--public-grain-shipments"]).public_grain_shipments is True
    assert parser.parse_args(["--no-public-grain-shipments"]).public_grain_shipments is False


def test_dispatch_receipt_records_cash_but_no_food_and_delivery_has_no_payment(world):
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.public_purchase_receipts import capture_public_purchases, snapshot_summary
    set_transaction_receipts_enabled(world, True)
    opening = F._projections(world, None)
    dispatch(world)
    demand = [10.0] * len(world.regions)
    capture_public_purchases(world, economy_result=economy(world), opening_treasuries=opening,
                             demand=demand, price=[1.0] * len(world.regions))
    frame = world.transaction_receipts.public_purchases
    assert frame.complete and len(frame.rows) == 1
    row = frame.rows[0]
    assert row.received == 0 and row.buyer_paid == row.foreign_ruler_credited == 2
    assert row.committed_net > 0 and row.shipment_id == "public-grain-shipment:30:0"
    assert row.quantity_basis == "committed_public_grain_dispatch"
    world.turn += 1
    G.open_granaries(world, economy(world))
    S.settle_arrivals(world)
    capture_public_purchases(world, economy_result=economy(world), opening_treasuries=F._projections(world,None),
                             demand=demand, price=[1.0] * len(world.regions),
                             flow_start=len(world.grain_reserves.flows))
    world.turn += 1
    summary = snapshot_summary(world)
    assert summary["observed_purchases"] == 0
    assert summary["deliveries"]["complete"]
    assert len(summary["deliveries"]["rows"]) == 1
    assert summary["deliveries"]["rows"][0]["paid_this_turn"] == 0
    assert summary["deliveries"]["rows"][0]["paid_at_dispatch"] == 2


def test_delivery_observer_cap_reports_incomplete_without_dropping_cargo(world):
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.public_purchase_receipts import capture_public_purchases, snapshot_summary
    set_transaction_receipts_enabled(world, True, max_rows=1)
    dispatch(world)
    dispatch(world)
    world.turn += 1
    G.open_granaries(world, economy(world))
    S.settle_arrivals(world)
    capture_public_purchases(world, economy_result=economy(world),
        opening_treasuries=F._projections(world,None), demand=[10.0]*len(world.regions),
        price=[1.0]*len(world.regions), flow_start=len(world.grain_reserves.flows))
    world.turn += 1
    frame = snapshot_summary(world)["deliveries"]
    assert frame["available"] and not frame["complete"]
    assert frame["observed_deliveries"] == 2 and frame["dropped_rows"] == 1
    assert len(frame["rows"]) == 1
    assert world.grain_reserves.shipments.pending == []
    assert world.grain_reserves.shipments.counters["arrived"] == 2


@pytest.mark.parametrize("fault", ["flow_extend", "arrival_counter"])
def test_arrival_failure_restores_cargo_grain_frame_and_container_identity(world, fault):
    dispatch(world)
    world.turn += 1
    G.open_granaries(world, economy(world))
    state = world.grain_reserves.shipments
    if fault == "arrival_counter":
        state.__dict__["counters"] = FailWrite(state.counters, "delivered")
    else:
        class FailExtend(list):
            def extend(self, values):
                super().extend(values)
                raise RuntimeError("injected arrival extension")
        world.grain_reserves.__dict__["flows"] = FailExtend(world.grain_reserves.flows)
    values = vectors(world)
    before = witness(world, values)
    with pytest.raises(RuntimeError):
        S.settle_arrivals(world)
    assert witness(world, values) == before


def test_forecast_preparedness_separates_committed_and_received_food(world):
    from chronicler import harvest_forecasts as H
    from chronicler.contact_ledger import set_contact_ledger_enabled
    from chronicler.harvest_forecasts_state import HarvestReport
    set_contact_ledger_enabled(world, True)
    H.set_harvest_forecasts_enabled(world, True)
    report = HarvestReport(id="transport-warning", source_region=SOURCE,
        source_region_name=world.regions[SOURCE].name, recipient_region=DEST,
        recipient_region_name=world.regions[DEST].name, owner=BUYER,
        owner_name=world.civilizations[BUYER].name, issued_turn=29, delivery_turn=30,
        expires_turn=34, target_start=30, target_end=32, probability=0.7,
        confidence=1.0, predicted_ratio=0.4, status="delivered", delivered_turn=30,
        delivered_event_id="warning-delivered")
    world.harvest_forecasts.reports.append(report)
    row = {"forecast_id":report.id, "region":DEST, "owner":BUYER,
           "base_target":40.0, "extra_target":0.0,
           "bought_during_warning":0.0, "paid_during_warning":0}
    world.harvest_forecasts.preparedness.append(row)
    dispatch(world)
    H.record_preparedness_purchases(world)
    assert row["committed_during_warning"] > 0
    assert row["paid_for_shipments_during_warning"] == 2
    assert row["arrived_during_warning"] == row["bought_during_warning"] == 0
    assert row["paid_during_warning"] == 0
    assert row["shipment_ids_during_warning"] == ["public-grain-shipment:30:0"]
    cash = [c.treasury for c in world.civilizations]
    world.turn += 1
    # Direct observation fixture retains a warning row; normal opening rebuilds
    # preparedness independently from today's actually delivered reports.
    S.settle_arrivals(world)
    H.record_preparedness_purchases(world)
    assert row["arrived_during_warning"] > 0
    assert row["paid_for_shipments_during_warning"] == 0
    assert [c.treasury for c in world.civilizations] == cash


def test_parent_discard_after_settlement_and_reenable_has_fresh_evidence_id(world):
    dispatch(world)
    first_id = world.grain_reserves.shipments.frame[0].id
    world.turn += 1
    S.settle_arrivals(world)
    assert world.grain_reserves.shipments.pending == []
    G.set_grain_reserves_enabled(world, False)
    G.set_grain_reserves_enabled(world, True)
    G._ensure(world)
    S.set_public_grain_shipments_enabled(world, True)
    G.open_granaries(world, economy(world))
    S.settle_arrivals(world)
    dispatch(world)
    transition = world.grain_reserves.shipments.frame[0]
    assert transition.order == 0 and transition.dispatch_turn == 31
    assert transition.id == "public-grain-shipment:31:0"
    assert transition.id != first_id


def test_enabled_aggregate_arrow_schema_keeps_bought_distinct_from_arrival(world, tmp_path):
    columns = []
    class Sidecar:
        def add_reserve_ledger_rows(self, rows):
            columns.append(rows)
    class Bridge:
        _sidecar = Sidecar()
    bridge = Bridge()
    result = economy(world)
    G.open_granaries(world, result, agent_bridge=bridge)
    G.tick_grain_reserves(world, economy_result=result, agent_bridge=bridge)
    assert columns and set(G.SHIPMENT_LEDGER_COLUMNS) <= set(columns[-1])
    assert sum(columns[-1]["dispatched_net"]) > 0
    assert sum(columns[-1]["bought"]) == sum(columns[-1]["arrived"]) == 0
    path = tmp_path / "reserves.arrow"
    G.write_reserve_ledger(path, columns[-1])
    restored = G.read_reserve_ledger(path)
    assert set(restored) == set(columns[-1])
    for name, values in columns[-1].items():
        for actual, expected in zip(restored[name], values, strict=True):
            if isinstance(expected, float) and math.isnan(expected):
                assert math.isnan(actual)
            else:
                assert actual == pytest.approx(expected)


def test_metrics_keep_edible_grain_separate_from_detached_cargo(world):
    dispatch(world)
    metrics = G.extract_grain_reserve_metrics([{"world_state": world.model_dump(mode="json")}])
    assert metrics["grain_final_mean"] == 0
    assert metrics["shipments"]["runs"] == 1
    assert metrics["shipments"]["pending_net_final_mean"] > 0
    assert metrics["shipments"]["counters_mean"]["paid"] == 2
    world.grain_reserves.shipments = None
    metrics = G.extract_grain_reserve_metrics([{"world_state": world.model_dump(mode="json")}])
    assert "shipments" not in metrics


@pytest.mark.parametrize("mode", ["demographics-only", "hybrid", "shadow"])
@pytest.mark.parametrize("fresh", [True, False])
def test_real_configure_admits_requested_mode_before_native_boundary(tmp_path, monkeypatch, mode, fresh):
    """Actual parser/configure/setter; stop only at Native construction."""
    from chronicler import main, agent_bridge
    candidate = generate_world(seed=42)
    if fresh:
        assert candidate.agent_mode is None
        grain_flags = ["--grain-reserves"]
    else:
        candidate.agent_mode = "off"  # intentionally differs from requested mode
        G.set_grain_reserves_enabled(candidate, True)
        grain_flags = []
    args = main._build_parser().parse_args(["--agents", mode, "--simulate-only",
        "--public-grain-shipments", *grain_flags])
    calls = []
    class ConfiguredBoundary(RuntimeError):
        pass
    class BridgeBoundary:
        def __init__(self, actual_world, **kwargs):
            calls.append((actual_world, kwargs))
            assert actual_world.agent_mode == mode
            assert actual_world.grain_reserves.shipments.accept_orders
            raise ConfiguredBoundary("real configuration reached Native boundary")
    monkeypatch.setattr(agent_bridge, "AgentBridge", BridgeBoundary)
    monkeypatch.setattr(main, "_create_ecology_runtime", lambda world: pytest.fail("unexpected ecology factory"))
    monkeypatch.setattr(main, "_create_politics_runtime", lambda world: pytest.fail("unexpected politics factory"))
    with pytest.raises(ConfiguredBoundary):
        main._configure_run(args, candidate, fresh, tmp_path / "chronicle.md")
    assert len(calls) == 1 and calls[0][0] is candidate and calls[0][1]["mode"] == mode


@pytest.mark.parametrize("saved_mode", ["demographics-only", "hybrid", "shadow"])
def test_real_configure_refuses_requested_off_despite_saved_enabled_mode(tmp_path, monkeypatch, saved_mode):
    from chronicler import main, agent_bridge
    candidate = generate_world(seed=42)
    candidate.agent_mode = saved_mode
    G.set_grain_reserves_enabled(candidate, True)
    S.set_public_grain_shipments_enabled(candidate, True)
    saved = candidate.grain_reserves.shipments.model_dump_json()
    args = main._build_parser().parse_args(["--agents", "off", "--public-grain-shipments"])
    def forbidden(*args, **kwargs):
        pytest.fail("invalid configuration reached a runtime factory")
    monkeypatch.setattr(agent_bridge, "AgentBridge", forbidden)
    monkeypatch.setattr(main, "_create_ecology_runtime", forbidden)
    monkeypatch.setattr(main, "_create_politics_runtime", forbidden)
    with pytest.raises(ValueError, match="agent-backed goods economy"):
        main._configure_run(args, candidate, False, tmp_path / "chronicle.md")
    assert candidate.grain_reserves.shipments.model_dump_json() == saved


@pytest.mark.parametrize("decoder", ["model", "file"])
def test_actual_old_world_json_decodes_absent_shipment_state_and_flow_field(tmp_path, decoder):
    from chronicler.grain_reserves_state import ReserveFlow
    candidate = generate_world(seed=42)
    G.set_grain_reserves_enabled(candidate, True)
    candidate.grain_reserves.flows.append(ReserveFlow(kind=BOUGHT, region=0, amount=2.0))
    original = candidate.model_dump_json()
    old = json.loads(original)
    assert "shipments" not in old["grain_reserves"]
    assert "shipment_order" not in old["grain_reserves"]["flows"][0]
    if decoder == "model":
        loaded = WorldState.model_validate_json(original)
    else:
        path = tmp_path / "old-world.json"
        path.write_text(original, encoding="utf-8")
        loaded = WorldState.load(path)
    assert loaded.grain_reserves.shipments is None
    assert loaded.grain_reserves.flows[0].shipment_order is None
    assert loaded.model_dump_json() == original


def test_actual_old_reserve_flow_pickle_fills_missing_optional_field():
    from chronicler.grain_reserves_state import ReserveFlow
    expected = ReserveFlow(kind=BOUGHT, region=0, amount=2.0).model_dump_json()
    old = ReserveFlow(kind=BOUGHT, region=0, amount=2.0)
    old.__dict__.pop("shipment_order", None)
    old.__pydantic_fields_set__.discard("shipment_order")
    loaded = pickle.loads(pickle.dumps(old))
    assert loaded.shipment_order is None
    assert loaded.model_dump_json() == expected
