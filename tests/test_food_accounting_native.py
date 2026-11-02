"""Focused real-native Phase 2 food accounting and exact continuation checks."""
import argparse
import json
import random

import pyarrow as pa
import pytest

from chronicler.economy import build_economy_region_input_batch, reconstruct_economy_result
from chronicler.food_accounting import FOOD_LEDGER_FIELDS, capture_food_accounting, public_opening, snapshot_fields
from chronicler.regional_population import capture_food_weights
from chronicler.turn_artifacts import TurnObservation

pytestmark = pytest.mark.native


def _economy(world, bridge):
    routes = pa.record_batch({"origin_region_id": pa.array([], type=pa.uint16()),
        "dest_region_id": pa.array([], type=pa.uint16()), "is_river": pa.array([], type=pa.bool_())})
    inputs = build_economy_region_input_batch(world)
    # Controlled no-forage input: empty resource slots otherwise still forage.
    index = inputs.schema.get_field_index("subsistence_yield")
    inputs = inputs.set_column(index, "subsistence_yield", pa.array([0.0] * inputs.num_rows, type=pa.float32()))
    batches = bridge._sim.tick_economy(inputs, routes, 0, False, 1.0)
    result = reconstruct_economy_result(*batches, world, require_oracle_shadow=True)
    return batches, result


def _empty_yields(world):
    for region in world.regions:
        region.resource_types = [255, 255, 255]
        region.resource_current_yields = [0.0, 0.0, 0.0]
        region.resource_effective_yields = [0.0, 0.0, 0.0]
        region.stockpile.goods = {}


@pytest.mark.parametrize("available", [0.0, 1.0, 1000.0])
def test_real_ffi_food_drawdown_reconstruct_and_balance(make_agent_bridge_world, available):
    world, bridge = make_agent_bridge_world(mode="hybrid")
    _empty_yields(world)
    world.regions[0].stockpile.goods = {"grain": available}
    weights = capture_food_weights(world, bridge.get_snapshot())
    batches, result = _economy(world, bridge)
    names = batches[0].schema.names
    assert all(f"food_{field}" in names for field in FOOD_LEDGER_FIELDS)
    assert all(batches[0].schema.field(f"food_{field}").type == pa.float64() for field in FOOD_LEDGER_FIELDS)
    row = capture_food_accounting(world, result, weights, None).as_dict(1)["regions"][0]
    native = row["native"]
    assert native["opening"] == available
    assert native["produced"] == native["transport_net"] == 0
    assert native["demand"] == weights.counts[0] * 0.5
    assert native["consumed"] == pytest.approx(min(available, native["demand"]))
    assert abs(native["balance_residual"]) <= native["balance_tolerance"]
    for i, field in enumerate(FOOD_LEDGER_FIELDS):
        assert result.food_ledger[0][i] == batches[0].column(f"food_{field}")[0].as_py()
    bridge.close()


def test_real_native_public_release_and_observer_are_distinct_and_read_only(make_agent_bridge_world):
    from chronicler.grain_reserves import _ensure, open_granaries, set_grain_reserves_enabled
    world, bridge = make_agent_bridge_world(mode="hybrid")
    _empty_yields(world)
    region = world.regions[0]
    region.stockpile.goods = {"grain": 1.0}
    weights = capture_food_weights(world, bridge.get_snapshot())
    assert weights.counts[0] > 2
    set_grain_reserves_enabled(world, True)
    reserve = _ensure(world).granaries[0]
    reserve.owner = world.civ_index_map[region.controller]
    reserve.grain = 100.0
    reserve.target = 0.0
    batches, result = _economy(world, bridge)
    opening = public_opening(world)
    native_consumed = result.food_ledger[0][6]
    before_suff = result.food_ledger[0][-1]
    open_granaries(world, result, bridge)
    before_bytes = bytes(bridge._sim.checkpoint_state())
    before_world, rng = world.model_dump_json(), random.getstate()
    captured = capture_food_accounting(world, result, weights, opening)
    obs = TurnObservation(world.turn, world.turn + 1, None, food_accounting=captured)
    first = snapshot_fields(world, obs)
    assert first == snapshot_fields(world, obs)
    row = first["food_accounting"]["regions"][0]
    assert row["native"]["consumed"] == native_consumed == 1.0
    assert row["native"]["sufficiency"] == before_suff
    assert row["public"]["released"] == pytest.approx(row["native"]["demand"] - 1.0)
    assert row["sufficiency_after_relief"] == 1.0
    assert abs(row["public"]["balance_residual"]) < 1e-6
    assert bytes(bridge._sim.checkpoint_state()) == before_bytes
    assert world.model_dump_json() == before_world and random.getstate() == rng
    bridge.close()


def _args(folder, turns, **kwargs):
    values = dict(seed=42, turns=turns, civs=2, regions=5,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="hybrid", tuning_overrides={})
    values.update(kwargs)
    return argparse.Namespace(**values)


def test_actual_checkpoint_resume_preserves_complete_food_history(tmp_path):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import execute_run
    from chronicler.run_checkpoint import read_checkpoint
    straight = tmp_path / "straight"
    execute_run(_args(straight, 8, checkpoint_every=4, checkpoint=str(straight / "c{turn}.ckpt")))
    resumed = tmp_path / "resumed"
    execute_run(_args(resumed, 8), checkpoint_resume=read_checkpoint(straight / "c4.ckpt"))
    a = load_bundle(straight / "chronicle_bundle.json")
    b = load_bundle(resumed / "chronicle_bundle.json")
    a["metadata"].pop("generated_at", None)
    b["metadata"].pop("generated_at", None)
    assert a == b
    assert len(a["history"]) == 8
    for snapshot in a["history"]:
        food = snapshot["food_accounting"]
        assert food["completed_turn"] == food["source_turn"] + 1 == snapshot["turn"]
        assert food["transport"] == "physical_delivery"
        assert all(r["native"] is not None for r in food["regions"])
        for region in food["regions"]:
            ledger = region["native"]
            assert abs(ledger["balance_residual"]) <= ledger["balance_tolerance"]
    assert json.loads((straight / "state.json").read_text()) == json.loads((resumed / "state.json").read_text())


def test_real_merchant_arrival_is_recorded_then_consumed_once():
    # Existing real route graph and mobility fixture; no fabricated delivery buffer.
    from test_transaction_receipts_native import _setup, _tick
    from chronicler.economy import TRANSIT_DECAY
    world, bridge = _setup("hybrid", enabled=False)
    rates = [TRANSIT_DECAY[x] for x in ("grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic", "crafts")]
    for _ in range(25):
        assert bridge._sim.get_pending_arrivals().num_rows == 0
        _tick(world, bridge)
        pending = pa.record_batch(bridge._sim.get_pending_arrivals()).to_pylist()
        food = [r for r in pending if r["good_slot"] in (0, 1, 2, 5, 7)]
        batches, result = _economy(world, bridge)
        if not food:
            continue
        assert bridge._sim.get_pending_arrivals().num_rows == 0
        expected = {}
        for item in food:
            rid = item["dest_region"]
            expected[rid] = expected.get(rid, 0.0) + item["qty"] * (1.0 - rates[item["good_slot"]])
        for rid, qty in expected.items():
            assert result.imports_by_region[world.regions[rid].name]["food"] == pytest.approx(qty, abs=1e-5)
        # With no intervening mobility, the next FFI tick cannot receive them again.
        _, after = _economy(world, bridge)
        for rid in expected:
            assert after.imports_by_region[world.regions[rid].name]["food"] == 0.0
            assert after.food_ledger[rid][2] == 0.0
        break
    else:
        pytest.fail("controlled native mobility fixture produced no food arrivals")
    bridge.close()


def test_zero_merchant_wealth_does_not_gate_region_food_drawdown(make_agent_bridge_world):
    # This tests a real zero-wealth cohort, not individual food allocation:
    # the kernel has only a regional stock drawdown and does not record meals.
    world, bridge = make_agent_bridge_world(mode="hybrid")
    _empty_yields(world)
    totals, counts = bridge._sim.merchant_wealth_by_region()
    rid = next(i for i, n in enumerate(counts) if n > 0)
    bridge._sim.apply_merchant_transfers([rid], [-totals[rid]])
    remaining, _ = bridge._sim.merchant_wealth_by_region()
    assert remaining[rid] == pytest.approx(0, abs=1e-7)
    world.regions[rid].stockpile.goods = {"grain": 1000.0}
    _, result = _economy(world, bridge)
    ledger = result.food_ledger[rid]
    assert ledger[10] > 0
    assert ledger[6] == pytest.approx(ledger[10])
    bridge.close()
