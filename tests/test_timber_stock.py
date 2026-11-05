"""L3 renewable timber stock (``--timber-stock``), offline.

docs/integration/timber-stock.md. A recorded economy stands in for the native
kernel: it produces ``min(potential, cap)`` per timber slot, as the economy's
``timber_harvest_cap_{slot}`` columns specify (null: no cap).
"""
from __future__ import annotations

import json
import math
import pickle
import random

import numpy as np
import pyarrow as pa
import pytest

from chronicler import timber_stock as ts
from chronicler.economy import EconomyResult
from chronicler.livelihoods import configure_livelihoods, finish_phase2, prepare_phase2
from chronicler.main import _build_parser
from chronicler.models import ResourceType, WorldState
from chronicler.timber_stock_state import TimberStockState, TimberTotals
from chronicler.world_gen import generate_world

TIMBER = int(ResourceType.TIMBER)


def _world(*flags, seed=3, overrides=None):
    world = generate_world(seed=seed)
    if overrides:
        world.tuning_overrides = dict(overrides)
    if flags:
        configure_livelihoods(world, _build_parser().parse_args(list(flags)), agent_mode="hybrid")
    return world


def _batch(world):
    """The economy region input's identity columns (the rest is not read)."""
    data = {"region_id": pa.array(range(len(world.regions)), type=pa.uint16())}
    for slot in range(3):
        data[f"resource_type_{slot}"] = pa.array(
            [r.resource_types[slot] for r in world.regions], type=pa.uint8())
    return pa.record_batch(data)


def _tick(world, potential=None):
    """One Phase 2: prepare, a recorded kernel, finish; then the turn ends.

    ``potential``: uncapped timber output per (region, slot) (default 0)."""
    potential = potential or {}
    batch = prepare_phase2(world, _batch(world), None, None)
    result = EconomyResult()
    for rid, region in enumerate(world.regions):
        outputs = []
        for slot in range(3):
            amount = np.float32(potential.get((rid, slot), 0.0))
            name = f"timber_harvest_cap_{slot}"
            cap = batch.column(name)[rid].as_py() if name in batch.schema.names else None
            if cap is not None:
                amount = min(amount, np.float32(cap))
            outputs.append(float(amount))
        result.slot_output[region.name] = tuple(outputs)
    events = finish_phase2(world, result, None)
    world.turn += 1
    return batch, events


def _summary(world):
    return ts.snapshot_summary(world)


def _rows(world):
    return {(r["region_id"], r["slot"]): r for r in _summary(world)["regions"]}


def _assert_closes(row):
    expected = math.fsum([row["opening"], -row["cleared"], -(row["extraction"] - row["overdraft"]),
                          row["regrowth"], -row["removed"]])
    assert expected == pytest.approx(row["stock"], rel=1e-12, abs=1e-9)
    assert 0.0 <= row["stock"] <= row["capacity"] * (1 + 1e-12) or row["removed"] > 0
    if row["cap"] is not None:
        assert row["extraction"] <= row["cap"] <= min(row["opening"], row["capacity"])


def _stocks(world):
    return {(s.region_id, s.slot): s.stock for s in world.livelihoods.timber_stock.stocks}


# --- Enable and capacity ---------------------------------------------------------

def test_enable_initializes_every_timber_slot_at_its_cover_implied_capacity():
    world = _world("--timber-stock")
    slots = ts.timber_slots(world)
    assert slots == [(0, 0), (2, 0)]
    for rid, slot in slots:
        region = world.regions[rid]
        harvest = region.resource_base_yields[slot] * 0.33 * region.carrying_capacity
        assert ts.reference_harvest(region, slot) == pytest.approx(harvest)
        reference = ts.reference_capacity(region, slot)
        assert ts.effective_capacity(region, slot) == pytest.approx(
            reference * region.ecology.forest_cover / 0.9)
        # The reference crew's harvest is the stock's maximum sustained yield.
        best = max(ts.regrowth(reference * x / 1000, reference, True) for x in range(1000))
        assert best == pytest.approx(harvest * ts.REFERENCE_CREWS_AT_MSY, rel=1e-4)
    assert _stocks(world) == {(rid, slot): ts.effective_capacity(world.regions[rid], slot)
                              for rid, slot in slots}
    # A temporary capacity modifier (drought, flood) does not change capacity.
    region = world.regions[0]
    before = ts.effective_capacity(region, 0)
    region.capacity_modifier = 0.5
    assert ts.effective_capacity(region, 0) == before


def test_cap_columns_are_float32_stock_on_timber_slots_null_elsewhere():
    world = _world("--timber-stock")
    state = world.livelihoods.timber_stock
    state.stocks[0].stock = 123.456789012345  # below capacity
    before = world.model_dump_json()
    batch = prepare_phase2(world, _batch(world), None, None)
    assert world.model_dump_json() == before, "prepare charges and mutates nothing"
    for slot in range(3):
        column = batch.column(f"timber_harvest_cap_{slot}")
        assert column.type == pa.float32()
        for rid, region in enumerate(world.regions):
            cap = column[rid].as_py()
            if region.resource_types[slot] != TIMBER:
                assert cap is None
                continue
            stock = _stocks(world)[(rid, slot)]
            limit = min(stock, ts.effective_capacity(region, slot))
            assert cap <= limit and float(np.float32(cap)) == cap
            assert float(np.nextafter(np.float32(cap), np.float32(np.inf))) > limit
    assert batch.column("timber_harvest_cap_0")[0].as_py() == pytest.approx(123.456789012345)
    assert ts.harvest_caps(world) == {(rid, s): batch.column(f"timber_harvest_cap_{s}")[rid].as_py()
                                      for rid, s in ts.timber_slots(world)}


def test_prepare_rejects_misaligned_or_owned_columns():
    world = _world("--timber-stock")
    batch = _batch(world)
    with pytest.raises(ValueError, match="one row per region"):
        ts.prepare_phase2(world, batch.slice(1), None, None, None)
    with pytest.raises(ValueError, match="owned by the timber stock"):
        ts.prepare_phase2(world, ts.prepare_phase2(world, batch, None, None, None), None, None, None)
    swapped = batch.set_column(0, "region_id", pa.array(list(reversed(range(batch.num_rows))), type=pa.uint16()))
    with pytest.raises(ValueError, match="follow world.regions"):
        ts.prepare_phase2(world, swapped, None, None, None)
    retyped = batch.set_column(1, "resource_type_0", pa.array([TIMBER] * batch.num_rows, type=pa.uint8()))
    with pytest.raises(ValueError, match="does not match"):
        ts.prepare_phase2(world, retyped, None, None, None)


# --- Accounting ------------------------------------------------------------------

def test_ledger_closes_and_harvest_never_exceeds_stock_over_many_turns():
    world = _world("--timber-stock")
    rng = random.Random(11)  # local stream: the test's pressure and cover path
    initial = sum(_stocks(world).values())
    capped = 0
    for turn in range(300):
        region = world.regions[0]
        if turn % 37 == 0:
            region.ecology.forest_cover = max(0.0, region.ecology.forest_cover - 0.3)  # wildfire
        region.ecology.forest_cover = min(0.95, max(0.0, region.ecology.forest_cover + rng.uniform(-0.02, 0.015)))
        region.ecology.water = rng.uniform(0.1, 0.9)
        pressure = {(0, 0): rng.uniform(0.0, 80.0), (2, 0): rng.choice([0.0, 5.0, 60.0])}
        _tick(world, pressure)
        record = _summary(world)
        assert record["observed"] and record["source_turn"] == world.turn - 1
        for row in record["regions"]:
            _assert_closes(row)
            if not row["water_gate_open"]:
                assert row["regrowth"] == 0.0
        capped += record["totals"]["capped_slots"]
    totals = world.livelihoods.timber_stock.totals
    assert totals.observed_turns == 300 and totals.capped_slot_turns == capped > 0
    final = sum(_stocks(world).values())
    assert final == pytest.approx(initial + totals.regrowth - totals.extraction - totals.cleared
                                  - totals.removed, rel=1e-9)
    assert totals.overdraft == 0.0 and totals.cleared > 0.0


def test_no_labour_means_no_extraction():
    world = _world("--timber-stock")
    full = _stocks(world)
    for _ in range(5):
        _tick(world, {})
        for row in _summary(world)["regions"]:
            assert row["extraction"] == 0.0 and row["capped"] is False
    assert _stocks(world) == full, "a full stand with no harvest stays at capacity"
    # Harvested down, then idle: only regrowth.
    _tick(world, {(0, 0): 1e9})
    low = _stocks(world)[(0, 0)]
    _tick(world, {})
    row = _rows(world)[(0, 0)]
    assert row["extraction"] == 0.0 and row["regrowth"] > 0.0 and row["stock"] == pytest.approx(low + row["regrowth"])


def test_heavy_harvest_binds_then_the_stock_recovers_when_pressure_falls():
    world = _world("--timber-stock")
    region = world.regions[0]
    capacity = ts.effective_capacity(region, 0)
    msy = ts.reference_harvest(region, 0)
    binding = []
    for _ in range(120):  # three reference crews, about three times the sustained yield
        _tick(world, {(0, 0): 3 * msy})
        binding.append(_rows(world)[(0, 0)]["capped"])
    depleted = _stocks(world)[(0, 0)]
    assert depleted < 0.05 * capacity and binding[-1] is True and binding[0] is False
    path = [depleted]
    for _ in range(200):
        _tick(world, {})
        path.append(_stocks(world)[(0, 0)])
    assert all(b > a for a, b in zip(path, path[1:]))
    turns_to_90 = next(i for i, s in enumerate(path) if s >= 0.9 * capacity)
    assert 120 <= turns_to_90 <= 180, "recovery takes the declared turns, not one"


def test_cover_loss_is_cleared_separately_from_extraction():
    world = _world("--timber-stock")
    region = world.regions[0]
    opening = _stocks(world)[(0, 0)]
    region.ecology.forest_cover -= 0.3  # wildfire (or clearing, succession)
    capacity = ts.effective_capacity(region, 0)
    batch, _ = _tick(world, {(0, 0): 25.0})
    assert batch.column("timber_harvest_cap_0")[0].as_py() <= capacity, "burnt timber is not offered"
    row = _rows(world)[(0, 0)]
    assert row["cleared"] == pytest.approx(opening - capacity)
    assert row["extraction"] == pytest.approx(25.0)
    assert row["stock"] == pytest.approx(capacity - 25.0 + row["regrowth"])
    _assert_closes(row)
    # Dry land: no regrowth (the forest regrowth water gate).
    region.ecology.water = 0.29
    _tick(world, {(0, 0): 10.0})
    row = _rows(world)[(0, 0)]
    assert not row["water_gate_open"] and row["regrowth"] == 0.0 and row["cleared"] == 0.0


def test_ablation_keeps_the_accounting_without_the_cap():
    world = _world("--timber-stock", overrides={ts.K_TIMBER_ENFORCE_CAP: 0.0})
    capacity = ts.effective_capacity(world.regions[0], 0)
    batch, _ = _tick(world, {(0, 0): 2 * capacity})
    for slot in range(3):
        assert batch.column(f"timber_harvest_cap_{slot}").null_count == len(world.regions)
    row = _rows(world)[(0, 0)]
    assert row["cap"] is None and row["capped"] is None
    assert row["extraction"] == pytest.approx(2 * capacity, rel=1e-6)
    assert row["overdraft"] == pytest.approx(row["extraction"] - capacity, rel=1e-6)
    assert row["stock"] == pytest.approx(row["regrowth"]) and row["regrowth"] > 0.0
    _assert_closes(row)
    record = _summary(world)
    assert record["enforce_cap"] is False and record["totals"]["overdraft"] > 0.0


def test_a_kernel_that_ignores_the_cap_is_refused_without_partial_state():
    world = _world("--timber-stock")
    world.livelihoods.timber_stock.stocks[0].stock = 10.0
    before = world.model_dump_json()
    result = EconomyResult()
    for region in world.regions:
        result.slot_output[region.name] = (0.0, 0.0, 0.0)
    result.slot_output[world.regions[0].name] = (10.5, 0.0, 0.0)
    with pytest.raises(RuntimeError, match="timber_harvest_cap_0"):
        finish_phase2(world, result, None)
    assert world.model_dump_json() == before
    with pytest.raises(RuntimeError, match="slot output"):
        finish_phase2(world, EconomyResult(), None)
    assert world.model_dump_json() == before


def test_a_turn_is_settled_once():
    world = _world("--timber-stock")
    result = EconomyResult()
    for region in world.regions:
        result.slot_output[region.name] = (1.0, 0.0, 0.0)
    finish_phase2(world, result, None)
    with pytest.raises(RuntimeError, match="already settled"):
        finish_phase2(world, result, None)


def test_a_slot_that_stops_being_timber_removes_its_stock_and_a_new_one_opens_full():
    world = _world("--timber-stock")
    held = _stocks(world)[(2, 0)]
    world.regions[2].resource_types[0] = int(ResourceType.GRAIN)
    world.regions[5].resource_types[2] = TIMBER
    world.regions[5].resource_base_yields[2] = 1.0
    _tick(world, {(5, 2): 3.0})
    rows = _rows(world)
    assert rows[(2, 0)]["removed"] == held and rows[(2, 0)]["stock"] == 0.0
    assert rows[(5, 2)]["opening"] == pytest.approx(ts.effective_capacity(world.regions[5], 2))
    assert rows[(5, 2)]["opening"] > 3.0
    assert rows[(5, 2)]["extraction"] == pytest.approx(3.0)
    assert set(_stocks(world)) == {(0, 0), (5, 2)}
    for row in rows.values():
        _assert_closes(row)


def test_the_stock_changes_no_other_world_state_and_draws_no_rng():
    world = _world("--timber-stock")
    rng_state = random.getstate()
    np_state = np.random.get_state()[1].copy()
    before = json.loads(world.model_dump_json())
    for _ in range(10):
        _tick(world, {(0, 0): 40.0, (2, 0): 15.0})
    after = json.loads(world.model_dump_json())
    for doc in (before, after):
        doc.pop("livelihoods")
        doc.pop("turn")
    assert after == before, "forest cover and every other field are untouched"
    assert random.getstate() == rng_state and (np.random.get_state()[1] == np_state).all()


# --- Switch identity and persistence ------------------------------------------------

def test_feature_off_worlds_are_identical():
    reference = generate_world(seed=3)
    rng_state = random.getstate()
    for flags in ((), ("--no-timber-stock",)):
        world = _world(*flags)
        assert world.livelihoods is None
        assert world.model_dump_json() == reference.model_dump_json()
        batch = _batch(world)
        assert prepare_phase2(world, batch, None, None) is batch
        assert finish_phase2(world, EconomyResult(), None) == []
        assert world.model_dump_json() == reference.model_dump_json()
    assert random.getstate() == rng_state
    world = generate_world(seed=3)
    ts.set_timber_stock_enabled(world, False)  # direct call on a never-enabled world
    assert world.livelihoods is None


def test_disable_freezes_and_reenable_resumes():
    world = _world("--timber-stock")
    _tick(world, {(0, 0): 50.0})
    frozen = _stocks(world)
    configure_livelihoods(world, _build_parser().parse_args(["--no-timber-stock"]), agent_mode="hybrid")
    assert not ts.timber_stock_active(world)
    batch = _batch(world)
    assert prepare_phase2(world, batch, None, None) is batch
    assert _stocks(world) == frozen
    configure_livelihoods(world, _build_parser().parse_args(["--timber-stock"]), agent_mode="hybrid")
    assert ts.timber_stock_active(world) and _stocks(world) == frozen
    assert _summary(world)["observed"] is True  # the settled turn is the completed one
    world.turn += 1
    assert _summary(world)["observed"] is False


def test_snapshot_reports_unknown_not_zero_and_is_bounded_json():
    world = _world("--timber-stock")
    record = _summary(world)
    assert record["observed"] is False and record["regions"] is None and record["totals"] is None
    assert record["source_turn"] == world.turn - 1 and record["completed_turn"] == world.turn
    _tick(world, {(0, 0): 5.0})
    record = json.loads(json.dumps(_summary(world)))
    assert record["observed"] and record["completed_turn"] == world.turn
    assert len(record["regions"]) == len(ts.timber_slots(world)) <= 3 * len(world.regions)
    assert record["totals"]["extraction"] == pytest.approx(5.0) and record["totals"]["slots"] == 2
    assert set(record["regions"][0]) >= {"region_id", "slot", "stock", "capacity", "extraction",
                                          "regrowth", "cleared", "capped"}


def test_stub_pickles_and_saves_backfill_the_new_fields():
    stub = TimberStockState(enabled=False)
    raw = stub.__getstate__()
    for name in ("stocks", "ledger_turn", "ledger", "totals"):
        raw["__dict__"].pop(name)
    back = TimberStockState.__new__(TimberStockState)
    back.__setstate__(raw)
    assert (back.enabled, back.stocks, back.ledger_turn, back.ledger, back.totals) == (
        False, [], None, [], TimberTotals())
    assert pickle.loads(pickle.dumps(back)).model_dump_json() == stub.model_dump_json()
    assert TimberStockState.model_validate_json('{"schema_version": 1, "enabled": true}') == TimberStockState()


def test_enabled_state_round_trips_exactly():
    world = _world("--timber-stock")
    for turn in range(6):
        _tick(world, {(0, 0): 40.0 + turn / 3, (2, 0): 7.0 / 3})
    restored = pickle.loads(pickle.dumps(world))
    assert restored.model_dump_json() == world.model_dump_json()
    assert restored.livelihoods.timber_stock == world.livelihoods.timber_stock
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert loaded.livelihoods.timber_stock == world.livelihoods.timber_stock
    # The restored world continues exactly as the original.
    for w in (world, restored, loaded):
        _tick(w, {(0, 0): 33.3, (2, 0): 1.0})
    assert restored.model_dump_json() == world.model_dump_json() == loaded.model_dump_json()
