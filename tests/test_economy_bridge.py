"""M54b: Dedicated economy FFI builders and reconstruction tests.

Verifies batch shapes, fixed good-slot ordering, stable route ordering,
EconomyResult reconstruction from mock return batches, and same-turn
consumer visibility of reconstructed fields.
"""

from unittest.mock import MagicMock

import numpy as np
import pyarrow as pa
import pytest
from chronicler_agents import AgentSimulator

from chronicler.agent_bridge import build_region_batch, configure_economy_runtime
from chronicler.economy import (
    CATEGORIES,
    EconomyResult,
    FIXED_GOODS,
    build_economy_region_input_batch,
    build_economy_trade_route_batch,
    reconstruct_economy_result,
)
from chronicler.factions import compute_tithe_base
from chronicler.models import Region, RegionStockpile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_two_region_world(trade_routes=None, rivers=None):
    """Minimal two-region world for builder tests."""
    r1 = Region(
        name="Valley", terrain="plains", carrying_capacity=50, resources="fertile",
        controller="Aram", resource_types=[0, 255, 255],
        resource_base_yields=[1.0, 0.0, 0.0],
        resource_effective_yields=[1.5, 0.0, 0.0],
    )
    r1.stockpile = RegionStockpile(goods={"grain": 40.0, "salt": 5.0})
    r1.adjacencies = ["Hills"]

    r2 = Region(
        name="Hills", terrain="mountains", carrying_capacity=30, resources="mineral",
        controller="Babel", resource_types=[5, 255, 255],
        resource_base_yields=[0.5, 0.0, 0.0],
        resource_effective_yields=[0.8, 0.0, 0.0],
    )
    r2.stockpile = RegionStockpile(goods={"ore": 10.0})
    r2.adjacencies = ["Valley"]

    civ_a = MagicMock()
    civ_a.name = "Aram"
    civ_a.regions = ["Valley"]
    civ_b = MagicMock()
    civ_b.name = "Babel"
    civ_b.regions = ["Hills"]

    world = MagicMock()
    world.regions = [r1, r2]
    world.civilizations = [civ_a, civ_b]
    world.rivers = rivers or []
    world.turn = 10

    return world


# ---------------------------------------------------------------------------
# Task 1: EconomyResult.conservation includes clamp_floor_loss
# ---------------------------------------------------------------------------

def test_economy_result_conservation_has_clamp_floor_loss():
    """EconomyResult.conservation default dict includes clamp_floor_loss."""
    er = EconomyResult()
    assert "clamp_floor_loss" in er.conservation
    assert er.conservation["clamp_floor_loss"] == 0.0


def test_economy_result_conservation_has_7_fields():
    """Conservation dict has exactly 7 fields matching the spec (M58b added in_transit_delta)."""
    er = EconomyResult()
    expected = {"production", "transit_loss", "consumption", "storage_loss",
                "cap_overflow", "clamp_floor_loss", "in_transit_delta"}
    assert set(er.conservation.keys()) == expected


def test_accumulate_stockpile_returns_clamp_floor_loss():
    """accumulate_stockpile returns clamp_floor_loss when exports exceed stock + production."""
    from chronicler.economy import accumulate_stockpile
    goods = {"grain": 5.0}
    loss = accumulate_stockpile(goods, production={}, exports={"grain": 10.0}, imports={})
    assert loss == pytest.approx(5.0)
    assert goods["grain"] == 0.0


def test_accumulate_stockpile_no_loss_returns_zero():
    """accumulate_stockpile returns 0.0 when no clamping occurs."""
    from chronicler.economy import accumulate_stockpile
    goods = {"grain": 50.0}
    loss = accumulate_stockpile(goods, production={"grain": 10.0}, exports={"grain": 5.0}, imports={})
    assert loss == 0.0
    assert goods["grain"] == pytest.approx(55.0)


def test_conservation_with_clamp_floor_loss():
    """compute_economy tracks clamp_floor_loss in the conservation dict."""
    import pyarrow as pa
    from chronicler.economy import compute_economy
    world = _make_two_region_world()

    # Make a snapshot with agents
    n = 10
    snapshot = pa.RecordBatch.from_pydict({
        "region": pa.array([0]*5 + [1]*5, type=pa.int32()),
        "occupation": pa.array([0]*5 + [0]*5, type=pa.int32()),
        "wealth": pa.array(np.zeros(n, dtype=np.float32), type=pa.float32()),
        "civ_affinity": pa.array([0]*5 + [1]*5, type=pa.int32()),
    })
    region_map = {r.name: r for r in world.regions}

    result = compute_economy(world, snapshot, region_map, agent_mode=True, active_trade_routes=[])
    # clamp_floor_loss should be present (may be 0 in this scenario)
    assert "clamp_floor_loss" in result.conservation
    assert result.conservation["clamp_floor_loss"] >= 0.0

    # Full conservation law with clamp_floor_loss included
    c = result.conservation
    # production + old_stock = new_stock + consumption + transit_loss + storage_loss + cap_overflow + clamp_floor_loss
    # We just verify the field exists and is non-negative here; full balance test is in test_economy_m43a.py


# ---------------------------------------------------------------------------
# Task 2: build_economy_region_input_batch shape and fixed good-slot ordering
# ---------------------------------------------------------------------------

def test_region_input_batch_column_count():
    """Region input batch has 5 + 8 = 13 columns."""
    world = _make_two_region_world()
    batch = build_economy_region_input_batch(world)
    assert batch.num_columns == 13
    assert batch.num_rows == 2


def test_region_input_batch_column_names():
    """Region input batch has the expected column names in order."""
    world = _make_two_region_world()
    batch = build_economy_region_input_batch(world)
    expected = [
        "region_id", "terrain", "storage_population",
        "resource_type_0", "resource_effective_yield_0",
    ] + [f"stockpile_{g}" for g in FIXED_GOODS]
    assert batch.schema.names == expected


def test_region_input_batch_fixed_good_slot_ordering():
    """Stockpile columns follow FIXED_GOODS ordering."""
    world = _make_two_region_world()
    batch = build_economy_region_input_batch(world)
    stockpile_cols = [name for name in batch.schema.names if name.startswith("stockpile_")]
    assert stockpile_cols == [f"stockpile_{g}" for g in FIXED_GOODS]


def test_region_input_batch_values():
    """Region input batch values match world state."""
    world = _make_two_region_world()
    batch = build_economy_region_input_batch(world)
    # Valley is region 0
    assert batch.column("region_id").to_pylist() == [0, 1]
    assert batch.column("storage_population").to_pylist() == [0, 0]  # default population
    assert batch.column("resource_type_0").to_pylist() == [0, 5]  # grain, ore
    assert batch.column("resource_effective_yield_0").to_pylist()[0] == pytest.approx(1.5)
    # Grain stockpile for Valley
    assert batch.column("stockpile_grain").to_pylist()[0] == pytest.approx(40.0)
    # Salt stockpile for Valley
    assert batch.column("stockpile_salt").to_pylist()[0] == pytest.approx(5.0)
    # Ore stockpile for Hills
    assert batch.column("stockpile_ore").to_pylist()[1] == pytest.approx(10.0)
    # Missing goods default to 0.0
    assert batch.column("stockpile_fish").to_pylist()[0] == pytest.approx(0.0)


def test_region_input_batch_no_agent_counts():
    """Region input batch does NOT include agent population or occupation counts."""
    world = _make_two_region_world()
    batch = build_economy_region_input_batch(world)
    names = set(batch.schema.names)
    for col in ("agent_population", "farmer_count", "soldier_count", "merchant_count",
                "wealthy_count", "scholar_count", "priest_count"):
        assert col not in names, f"Agent-derived column {col} should not be in region input"


# ---------------------------------------------------------------------------
# Task 3: build_economy_trade_route_batch shape and stable ordering
# ---------------------------------------------------------------------------

def test_trade_route_batch_column_names():
    """Trade route batch has the expected column names."""
    world = _make_two_region_world()
    batch = build_economy_trade_route_batch(world, active_trade_routes=[("Aram", "Babel")])
    assert batch.schema.names == ["origin_region_id", "dest_region_id", "is_river"]


def test_trade_route_batch_decomposes_civ_routes():
    """Trade route batch decomposes civ-level route into boundary pairs (both directions)."""
    world = _make_two_region_world()
    batch = build_economy_trade_route_batch(world, active_trade_routes=[("Aram", "Babel")])
    # Valley->Hills and Hills->Valley (both directions)
    assert batch.num_rows == 2
    origins = batch.column("origin_region_id").to_pylist()
    dests = batch.column("dest_region_id").to_pylist()
    assert set(zip(origins, dests)) == {(0, 1), (1, 0)}


def test_trade_route_batch_stable_sort():
    """Trade route batch rows are sorted by (origin_region_id, dest_region_id)."""
    world = _make_two_region_world()
    batch = build_economy_trade_route_batch(world, active_trade_routes=[("Aram", "Babel")])
    origins = batch.column("origin_region_id").to_pylist()
    dests = batch.column("dest_region_id").to_pylist()
    pairs = list(zip(origins, dests))
    assert pairs == sorted(pairs)


def test_trade_route_batch_river_flag():
    """Trade route batch sets is_river from world.rivers."""
    river = MagicMock()
    river.path = ["Valley", "Hills"]
    world = _make_two_region_world(rivers=[river])
    batch = build_economy_trade_route_batch(world, active_trade_routes=[("Aram", "Babel")])
    river_flags = batch.column("is_river").to_pylist()
    assert all(river_flags), "Both directions should be river-connected"


def test_trade_route_batch_empty_routes():
    """Trade route batch handles empty route list."""
    world = _make_two_region_world()
    batch = build_economy_trade_route_batch(world, active_trade_routes=[])
    assert batch.num_rows == 0
    assert batch.schema.names == ["origin_region_id", "dest_region_id", "is_river"]


# ---------------------------------------------------------------------------
# Task 4: reconstruct_economy_result from mock return batches
# ---------------------------------------------------------------------------

def _make_mock_return_batches(world):
    """Create mock Rust return batches matching the spec schema."""
    n_regions = len(world.regions)
    n_civs = len(world.civilizations)

    # Region result batch
    region_result_data = {
        "region_id": pa.array(range(n_regions), type=pa.uint16()),
        "farmer_income_modifier": pa.array([1.2, 0.8], type=pa.float32()),
        "food_sufficiency": pa.array([1.5, 0.3], type=pa.float32()),
        "merchant_margin": pa.array([0.4, 0.1], type=pa.float32()),
        "merchant_trade_income": pa.array([2.5, 0.0], type=pa.float32()),
        "trade_route_count": pa.array([1, 1], type=pa.uint16()),
    }
    for good in FIXED_GOODS:
        if good == "grain":
            region_result_data[f"stockpile_{good}"] = pa.array([35.0, 0.0], type=pa.float32())
        elif good == "ore":
            region_result_data[f"stockpile_{good}"] = pa.array([0.0, 8.0], type=pa.float32())
        else:
            region_result_data[f"stockpile_{good}"] = pa.array([0.0, 0.0], type=pa.float32())
    region_result = pa.record_batch(region_result_data)

    # Civ result batch
    civ_result = pa.record_batch({
        "civ_id": pa.array(range(n_civs), type=pa.uint8()),
        "treasury_tax": pa.array([5.0, 2.0], type=pa.float32()),
        "tithe_base": pa.array([100.0, 40.0], type=pa.float32()),
        "priest_tithe_share": pa.array([10.0, 4.0], type=pa.float32()),
    })

    # Observability batch
    observability = pa.record_batch({
        "region_id": pa.array(range(n_regions), type=pa.uint16()),
        "imports_food": pa.array([0.0, 3.0], type=pa.float32()),
        "imports_raw_material": pa.array([2.0, 0.0], type=pa.float32()),
        "imports_luxury": pa.array([0.0, 0.0], type=pa.float32()),
        "stockpile_food": pa.array([35.0, 0.0], type=pa.float32()),
        "stockpile_raw_material": pa.array([0.0, 8.0], type=pa.float32()),
        "stockpile_luxury": pa.array([0.0, 0.0], type=pa.float32()),
        "import_share": pa.array([0.0, 0.9], type=pa.float32()),
        "trade_dependent": pa.array([False, True], type=pa.bool_()),
    })

    # Upstream sources batch
    upstream_sources = pa.record_batch({
        "dest_region_id": pa.array([1], type=pa.uint16()),
        "source_ordinal": pa.array([0], type=pa.uint16()),
        "source_region_id": pa.array([0], type=pa.uint16()),
    })

    # Conservation batch
    conservation = pa.record_batch({
        "production": pa.array([15.0], type=pa.float64()),
        "transit_loss": pa.array([0.5], type=pa.float64()),
        "consumption": pa.array([8.0], type=pa.float64()),
        "storage_loss": pa.array([1.2], type=pa.float64()),
        "cap_overflow": pa.array([0.0], type=pa.float64()),
        "clamp_floor_loss": pa.array([0.3], type=pa.float64()),
    })

    return region_result, civ_result, observability, upstream_sources, conservation


def test_reconstruct_economy_result_signals():
    """Reconstructed EconomyResult has correct region signals."""
    world = _make_two_region_world()
    batches = _make_mock_return_batches(world)
    result = reconstruct_economy_result(*batches, world)

    assert result.farmer_income_modifiers["Valley"] == pytest.approx(1.2)
    assert result.farmer_income_modifiers["Hills"] == pytest.approx(0.8)
    assert result.food_sufficiency["Valley"] == pytest.approx(1.5)
    assert result.merchant_margins["Valley"] == pytest.approx(0.4)
    assert result.merchant_trade_incomes["Valley"] == pytest.approx(2.5)
    assert result.trade_route_counts["Valley"] == 1


def test_reconstruct_economy_result_stockpile_writeback():
    """Reconstructed result writes stockpiles back to world regions."""
    world = _make_two_region_world()
    batches = _make_mock_return_batches(world)
    reconstruct_economy_result(*batches, world)

    assert world.regions[0].stockpile.goods["grain"] == pytest.approx(35.0)
    assert world.regions[1].stockpile.goods["ore"] == pytest.approx(8.0)


def test_reconstruct_economy_result_fiscal():
    """Reconstructed result has correct civ fiscal outputs."""
    world = _make_two_region_world()
    batches = _make_mock_return_batches(world)
    result = reconstruct_economy_result(*batches, world)

    assert result.treasury_tax[0] == pytest.approx(5.0)
    assert result.tithe_base[0] == pytest.approx(100.0)
    assert result.priest_tithe_shares[0] == pytest.approx(10.0)
    assert result.treasury_tax[1] == pytest.approx(2.0)


def test_tick_economy_emits_zero_tithe_base_for_controlled_zero_agent_civ(sample_world):
    """Controlled civs with zero agents must still get explicit zero fiscal rows."""
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]

    for region in sample_world.regions:
        region.population = 0

    sample_world.regions[0].controller = civ_a.name
    sample_world.regions[0].population = 10
    sample_world.regions[1].controller = civ_b.name
    sample_world.regions[1].population = 0
    civ_a.regions = [sample_world.regions[0].name]
    civ_b.regions = [sample_world.regions[1].name]
    civ_b.last_income = 123
    sample_world.turn = 0

    sim = AgentSimulator(num_regions=len(sample_world.regions), seed=sample_world.seed)
    configure_economy_runtime(sim, sample_world)
    sim.set_region_state(build_region_batch(sample_world))

    region_input = build_economy_region_input_batch(sample_world)
    trade_route_input = build_economy_trade_route_batch(sample_world, active_trade_routes=[])
    rust_return = sim.tick_economy(region_input, trade_route_input, 0, False, 1.0)
    result = reconstruct_economy_result(*rust_return, sample_world)

    assert 1 in result.tithe_base
    assert result.tithe_base[1] == pytest.approx(0.0)
    assert compute_tithe_base(civ_b, economy_result=result, civ_idx=1) == pytest.approx(0.0)

def test_reconstruct_economy_result_observability():
    """Reconstructed result has correct observability fields."""
    world = _make_two_region_world()
    batches = _make_mock_return_batches(world)
    result = reconstruct_economy_result(*batches, world)

    assert result.imports_by_region["Hills"]["food"] == pytest.approx(3.0)
    assert result.stockpile_levels["Valley"]["food"] == pytest.approx(35.0)
    assert result.import_share["Hills"] == pytest.approx(0.9)
    assert result.trade_dependent["Hills"] is True
    assert result.trade_dependent["Valley"] is False


def test_reconstruct_economy_result_inbound_sources():
    """Reconstructed result correctly maps upstream source ids to names."""
    world = _make_two_region_world()
    batches = _make_mock_return_batches(world)
    result = reconstruct_economy_result(*batches, world)

    assert result.inbound_sources["Hills"] == ["Valley"]
    assert "Valley" not in result.inbound_sources  # Valley has no imports


def test_reconstruct_economy_result_conservation():
    """Reconstructed result has correct conservation dict."""
    world = _make_two_region_world()
    batches = _make_mock_return_batches(world)
    result = reconstruct_economy_result(*batches, world)

    assert result.conservation["production"] == pytest.approx(15.0)
    assert result.conservation["transit_loss"] == pytest.approx(0.5)
    assert result.conservation["clamp_floor_loss"] == pytest.approx(0.3)


def test_reconstruct_economy_result_requires_oracle_columns_when_strict():
    """Hybrid strict mode fails fast when oracle shadow columns are missing."""
    world = _make_two_region_world()
    batches = _make_mock_return_batches(world)  # observability lacks oracle_margin/food_suff
    with pytest.raises(ValueError, match="missing required oracle observability columns"):
        reconstruct_economy_result(*batches, world, require_oracle_shadow=True)


# ---------------------------------------------------------------------------
# Task 5: FIXED_GOODS constant
# ---------------------------------------------------------------------------

def test_fixed_goods_has_8_entries():
    """FIXED_GOODS contains all 8 goods in a fixed order."""
    assert len(FIXED_GOODS) == 8
    assert set(FIXED_GOODS) == {"grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic"}


def test_fixed_goods_is_tuple():
    """FIXED_GOODS is a tuple (immutable, ordered)."""
    assert isinstance(FIXED_GOODS, tuple)
