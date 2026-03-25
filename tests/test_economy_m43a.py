"""M43a: Transport, perishability & stockpiles tests."""

from chronicler.models import RegionStockpile, Region
from chronicler.economy import (
    FOOD_GOODS,
    ALL_GOODS,
    TRANSIT_DECAY,
    STORAGE_DECAY,
    TERRAIN_COST,
    TRANSPORT_COST_BASE,
    RIVER_DISCOUNT,
    COASTAL_DISCOUNT,
    INFRASTRUCTURE_DISCOUNT,
    WINTER_MODIFIER,
    SALT_PRESERVATION_FACTOR,
    MAX_PRESERVATION,
    PER_CAPITA_FOOD,
    CONQUEST_STOCKPILE_SURVIVAL,
    PER_GOOD_CAP_FACTOR,
    INITIAL_BUFFER,
    map_resource_to_good,
    bootstrap_region_stockpile,
    settle_pending_stockpile_bootstraps,
    compute_transport_cost,
    build_river_route_set,
    allocate_trade_flow,
)


# --- Task 1: RegionStockpile ---

def test_region_stockpile_default():
    s = RegionStockpile()
    assert s.goods == {}


def test_region_stockpile_with_goods():
    s = RegionStockpile(goods={"grain": 50.0, "salt": 10.0})
    assert s.goods["grain"] == 50.0
    assert s.goods["salt"] == 10.0


def test_region_has_stockpile():
    r = Region(name="Test", terrain="plains", carrying_capacity=50, resources="fertile")
    assert isinstance(r.stockpile, RegionStockpile)
    assert r.stockpile.goods == {}


# --- Task 2: Constants ---

def test_food_goods_contains_salt():
    assert "salt" in FOOD_GOODS
    assert "grain" in FOOD_GOODS
    assert "fish" in FOOD_GOODS
    assert "botanicals" in FOOD_GOODS
    assert "exotic" in FOOD_GOODS
    assert "timber" not in FOOD_GOODS


def test_all_goods_has_8_members():
    assert len(ALL_GOODS) == 8
    assert ALL_GOODS == frozenset({
        "grain", "timber", "botanicals", "fish",
        "salt", "ore", "precious", "exotic",
    })


def test_transit_decay_rates():
    assert TRANSIT_DECAY["grain"] == 0.05
    assert TRANSIT_DECAY["fish"] == 0.08
    assert TRANSIT_DECAY["salt"] == 0.0
    assert TRANSIT_DECAY["ore"] == 0.0
    assert TRANSIT_DECAY["precious"] == 0.0


def test_storage_decay_rates():
    assert STORAGE_DECAY["grain"] == 0.03
    assert STORAGE_DECAY["grain"] < TRANSIT_DECAY["grain"]
    assert STORAGE_DECAY["salt"] == 0.0


def test_terrain_cost_all_terrains():
    assert set(TERRAIN_COST.keys()) == {"plains", "forest", "desert", "mountains", "tundra", "coast"}
    assert TERRAIN_COST["plains"] == 1.0
    assert TERRAIN_COST["mountains"] == 2.0
    assert TERRAIN_COST["coast"] == 0.6


def test_per_good_cap_factor_derived():
    assert PER_GOOD_CAP_FACTOR == 5.0 * PER_CAPITA_FOOD
    assert INITIAL_BUFFER == 2.0 * PER_CAPITA_FOOD


# --- Task 3: map_resource_to_good ---

def test_map_resource_to_good_all_types():
    assert map_resource_to_good(0) == "grain"
    assert map_resource_to_good(1) == "timber"
    assert map_resource_to_good(2) == "botanicals"
    assert map_resource_to_good(3) == "fish"
    assert map_resource_to_good(4) == "salt"
    assert map_resource_to_good(5) == "ore"
    assert map_resource_to_good(6) == "precious"
    assert map_resource_to_good(7) == "exotic"


# --- Task 4: Transport cost ---

def test_transport_cost_plains_to_plains():
    cost = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=False)
    assert cost == TRANSPORT_COST_BASE * 1.0


def test_transport_cost_worst_terrain():
    cost = compute_transport_cost("plains", "mountains", is_river=False, is_coastal=False, is_winter=False)
    assert cost == TRANSPORT_COST_BASE * TERRAIN_COST["mountains"]


def test_transport_cost_river_discount():
    base = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=False)
    river = compute_transport_cost("plains", "plains", is_river=True, is_coastal=False, is_winter=False)
    assert river == base * RIVER_DISCOUNT


def test_transport_cost_coastal_discount():
    base = compute_transport_cost("coast", "coast", is_river=False, is_coastal=False, is_winter=False)
    coastal = compute_transport_cost("coast", "coast", is_river=False, is_coastal=True, is_winter=False)
    assert coastal == base * COASTAL_DISCOUNT


def test_transport_cost_river_and_coastal_takes_min():
    river_only = compute_transport_cost("coast", "coast", is_river=True, is_coastal=False, is_winter=False)
    coastal_only = compute_transport_cost("coast", "coast", is_river=False, is_coastal=True, is_winter=False)
    both = compute_transport_cost("coast", "coast", is_river=True, is_coastal=True, is_winter=False)
    assert both == min(river_only, coastal_only)


def test_transport_cost_winter_modifier():
    base = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=False)
    winter = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=True)
    assert winter == base * WINTER_MODIFIER


def test_build_river_route_set():
    from chronicler.models import River
    rivers = [River(name="Nile", path=["A", "B", "C"])]
    result = build_river_route_set(rivers)
    assert frozenset({"A", "B"}) in result
    assert frozenset({"B", "C"}) in result
    assert frozenset({"A", "C"}) not in result


# --- Task 5: Effective margin ---

def test_effective_margin_filters_expensive_routes():
    routes = [("A", "B"), ("A", "C")]
    origin_prices = {"food": 1.0, "raw_material": 1.0, "luxury": 1.0}
    dest_prices = {
        "B": {"food": 1.05, "raw_material": 1.0, "luxury": 1.0},
        "C": {"food": 2.0, "raw_material": 1.0, "luxury": 1.0},
    }
    surplus = {"food": 10.0, "raw_material": 0.0, "luxury": 0.0}
    transport_costs = {("A", "B"): 0.10, ("A", "C"): 0.10}

    flow = allocate_trade_flow(
        routes, origin_prices, dest_prices, surplus,
        merchant_count=5, transport_costs=transport_costs,
    )
    assert flow[("A", "B")]["food"] == 0.0
    assert flow[("A", "C")]["food"] > 0.0


# --- Task 6: Transit decay ---

from chronicler.economy import apply_transit_decay


def test_transit_decay_grain():
    delivered = apply_transit_decay(100.0, "grain")
    assert delivered == 100.0 * (1.0 - TRANSIT_DECAY["grain"])


def test_transit_decay_mineral_no_loss():
    assert apply_transit_decay(100.0, "ore") == 100.0
    assert apply_transit_decay(100.0, "precious") == 100.0


def test_transit_decay_zero_shipped():
    assert apply_transit_decay(0.0, "grain") == 0.0


# --- Task 7: Storage decay with salt preservation ---

from chronicler.economy import apply_storage_decay, STORAGE_DECAY, FOOD_GOODS


def test_storage_decay_grain_no_salt():
    goods = {"grain": 100.0}
    loss = apply_storage_decay(goods)
    assert abs(goods["grain"] - 97.0) < 0.01
    assert abs(loss - 3.0) < 0.01


def test_storage_decay_salt_no_decay():
    goods = {"salt": 100.0}
    loss = apply_storage_decay(goods)
    assert goods["salt"] == 100.0
    assert loss == 0.0


def test_storage_decay_ore_no_decay():
    goods = {"ore": 100.0}
    loss = apply_storage_decay(goods)
    assert goods["ore"] == 100.0
    assert loss == 0.0


def test_storage_decay_salt_preserves_food():
    # 20% salt ratio → hits cap (50% reduction)
    goods = {"grain": 80.0, "salt": 20.0}
    apply_storage_decay(goods)
    expected = 80.0 * (1.0 - 0.03 * 0.5)
    assert abs(goods["grain"] - expected) < 0.01
    assert goods["salt"] == 20.0


def test_storage_decay_partial_salt():
    # salt-to-food ratio = 5/95 ≈ 0.0526 (salt excluded from denominator per spec)
    # preservation = 0.0526 * 2.5 ≈ 0.1316
    goods = {"grain": 95.0, "salt": 5.0}
    apply_storage_decay(goods)
    salt_ratio = 5.0 / 95.0
    preservation = min(salt_ratio * 2.5, 0.5)
    expected = 95.0 * (1.0 - 0.03 * (1.0 - preservation))
    assert abs(goods["grain"] - expected) < 0.01


def test_storage_decay_zero_food_no_division_error():
    goods = {"salt": 10.0}
    apply_storage_decay(goods)
    assert goods["salt"] == 10.0


def test_storage_decay_timber_not_salt_affected():
    goods = {"timber": 100.0, "salt": 50.0}
    apply_storage_decay(goods)
    expected = 100.0 * (1.0 - STORAGE_DECAY["timber"])
    assert abs(goods["timber"] - expected) < 0.01


# --- Task 8: Stockpile accumulation ---

from chronicler.economy import accumulate_stockpile


def test_accumulate_stockpile_basic():
    goods = {"grain": 10.0}
    accumulate_stockpile(goods, production={"grain": 50.0}, exports={"grain": 20.0}, imports={"grain": 5.0})
    assert abs(goods["grain"] - 45.0) < 0.01


def test_accumulate_stockpile_new_good():
    goods = {}
    accumulate_stockpile(goods, production={}, exports={}, imports={"fish": 10.0})
    assert abs(goods["fish"] - 10.0) < 0.01


def test_accumulate_stockpile_export_only():
    goods = {"grain": 5.0}
    accumulate_stockpile(goods, production={"grain": 10.0}, exports={"grain": 15.0}, imports={})
    assert abs(goods["grain"] - 0.0) < 0.01


# --- Task 9: food_sufficiency from stockpile + consumption + cap ---

from chronicler.economy import (
    derive_food_sufficiency_from_stockpile,
    consume_from_stockpile,
    apply_stockpile_cap,
    PER_GOOD_CAP_FACTOR,
)


def test_food_sufficiency_from_stockpile_equilibrium():
    goods = {"grain": 50.0}
    result = derive_food_sufficiency_from_stockpile(goods, 50.0)
    assert abs(result - 1.0) < 0.01


def test_food_sufficiency_from_stockpile_surplus():
    goods = {"grain": 200.0}
    result = derive_food_sufficiency_from_stockpile(goods, 50.0)
    assert result == 2.0


def test_food_sufficiency_from_stockpile_deficit():
    goods = {"grain": 25.0}
    result = derive_food_sufficiency_from_stockpile(goods, 50.0)
    assert abs(result - 0.5) < 0.01


def test_food_sufficiency_empty_stockpile():
    goods = {}
    result = derive_food_sufficiency_from_stockpile(goods, 50.0)
    assert result == 0.0


def test_food_sufficiency_includes_salt():
    goods = {"salt": 50.0}
    result = derive_food_sufficiency_from_stockpile(goods, 50.0)
    assert abs(result - 1.0) < 0.01


def test_consume_from_stockpile_proportional():
    goods = {"grain": 60.0, "fish": 40.0}
    consume_from_stockpile(goods, food_demand=50.0)
    assert abs(goods["grain"] - 30.0) < 0.01
    assert abs(goods["fish"] - 20.0) < 0.01


def test_consume_from_stockpile_clamped():
    goods = {"grain": 10.0}
    consume_from_stockpile(goods, food_demand=50.0)
    assert goods["grain"] == 0.0


def test_consume_from_stockpile_empty():
    goods = {}
    consume_from_stockpile(goods, food_demand=50.0)


def test_stockpile_cap():
    goods = {"grain": 1000.0, "timber": 5.0}
    apply_stockpile_cap(goods, population=10)
    expected_cap = PER_GOOD_CAP_FACTOR * 10
    assert goods["grain"] == expected_cap
    assert goods["timber"] == 5.0


def test_stockpile_cap_zero_population():
    goods = {"grain": 100.0}
    apply_stockpile_cap(goods, population=0)
    assert goods["grain"] == 0.0


# --- Task 10: Stockpile Initialization in world_gen.py ---

def test_stockpile_initialization():
    """generate_world() initializes primary food stockpile for controlled regions."""
    from chronicler.world_gen import generate_world
    from chronicler.economy import map_resource_to_good, INITIAL_BUFFER

    world = generate_world(seed=42, num_regions=8, num_civs=4)
    for region in world.regions:
        if region.controller is not None and region.resource_types[0] != 255:
            good = map_resource_to_good(region.resource_types[0])
            expected = INITIAL_BUFFER * region.population
            assert abs(region.stockpile.goods.get(good, 0.0) - expected) < 0.01, (
                f"Region {region.name}: expected {good}={expected}, "
                f"got {region.stockpile.goods}"
            )


def test_bootstrap_region_stockpile_seeds_primary_good_and_food():
    region = Region(
        name="Hills",
        terrain="mountains",
        carrying_capacity=50,
        population=24,
        resources="mineral",
    )
    region.resource_types[0] = 5  # ore

    bootstrapped = bootstrap_region_stockpile(region)

    assert bootstrapped is True
    assert region.stockpile.goods["ore"] == INITIAL_BUFFER * 24
    assert region.stockpile.goods["grain"] == INITIAL_BUFFER * 24


def test_bootstrap_region_stockpile_preserves_existing_primary_and_adds_missing_food():
    region = Region(
        name="Hills",
        terrain="mountains",
        carrying_capacity=50,
        population=18,
        resources="mineral",
    )
    region.resource_types[0] = 5  # ore
    region.stockpile.goods["ore"] = 7.0

    bootstrapped = bootstrap_region_stockpile(region)

    assert bootstrapped is True
    assert region.stockpile.goods["ore"] == 7.0
    assert region.stockpile.goods["grain"] == INITIAL_BUFFER * 18


def test_settle_pending_stockpile_bootstraps_waits_for_population():
    region = Region(
        name="Frontier",
        terrain="coast",
        carrying_capacity=60,
        population=0,
        resources="maritime",
        controller="Civ A",
    )
    region.resource_types[0] = 3  # fish
    region._stockpile_bootstrap_pending = True

    assert settle_pending_stockpile_bootstraps([region]) == 0
    assert getattr(region, "_stockpile_bootstrap_pending", False) is True
    assert region.stockpile.goods == {}

    region.population = 22
    assert settle_pending_stockpile_bootstraps([region]) == 1
    assert getattr(region, "_stockpile_bootstrap_pending", False) is False
    assert region.stockpile.goods["fish"] == INITIAL_BUFFER * 22


# --- Task 11: Conquest Stockpile Destruction ---

def test_conquest_stockpile_destruction():
    """Conquest destroys 50% of each good in the region's stockpile."""
    from chronicler.models import Region, RegionStockpile
    from chronicler.economy import CONQUEST_STOCKPILE_SURVIVAL

    region = Region(name="Heartland", terrain="plains", carrying_capacity=50, resources="fertile")
    region.stockpile = RegionStockpile(goods={"grain": 100.0, "timber": 40.0, "salt": 20.0})

    for good in region.stockpile.goods:
        region.stockpile.goods[good] *= CONQUEST_STOCKPILE_SURVIVAL

    assert abs(region.stockpile.goods["grain"] - 50.0) < 0.01
    assert abs(region.stockpile.goods["timber"] - 20.0) < 0.01
    assert abs(region.stockpile.goods["salt"] - 10.0) < 0.01


# --- Task 12: Analytics Extractors ---

def test_extract_stockpiles_structure():
    """extract_stockpiles returns per-region per-good time series."""
    from chronicler.analytics import extract_stockpiles

    bundle = {
        "world_state": {
            "regions": [
                {"name": "Valley", "stockpile": {"goods": {"grain": 50.0, "salt": 10.0}}},
                {"name": "Hills", "stockpile": {"goods": {"ore": 30.0}}},
            ],
        },
        "history": [
            {"turn": 10, "world_state": {
                "regions": [
                    {"name": "Valley", "stockpile": {"goods": {"grain": 45.0, "salt": 12.0}}},
                    {"name": "Hills", "stockpile": {"goods": {"ore": 28.0}}},
                ],
            }},
        ],
    }
    result = extract_stockpiles([bundle], checkpoints=[10])
    assert "Valley" in result
    assert "grain" in result["Valley"]
    assert result["Valley"]["grain"][10] == 45.0


# --- Task 13: compute_economy() stockpile integration ---

def test_compute_economy_stockpile_integration():
    """compute_economy() accumulates stockpile and derives food_sufficiency from it."""
    from unittest.mock import MagicMock
    import numpy as np
    import pyarrow as pa
    from chronicler.economy import compute_economy, PER_CAPITA_FOOD
    from chronicler.models import RegionStockpile

    r1 = MagicMock()
    r1.name = "Valley"
    r1.terrain = "plains"
    r1.resource_types = [0, 255, 255]
    r1.resource_effective_yields = [1.0, 0.0, 0.0]
    r1.adjacencies = ["Hills"]
    r1.population = 10
    r1.stockpile = RegionStockpile(goods={"grain": 20.0})

    r2 = MagicMock()
    r2.name = "Hills"
    r2.terrain = "mountains"
    r2.resource_types = [5, 255, 255]
    r2.resource_effective_yields = [0.5, 0.0, 0.0]
    r2.adjacencies = ["Valley"]
    r2.population = 5
    r2.stockpile = RegionStockpile(goods={"ore": 5.0})

    civ = MagicMock()
    civ.name = "Aram"
    civ.regions = ["Valley", "Hills"]

    world = MagicMock()
    world.regions = [r1, r2]
    world.civilizations = [civ]
    world.rivers = []
    world.turn = 10

    n_agents = 15
    regions_arr = np.array([0]*10 + [1]*5, dtype=np.int32)
    occupations_arr = np.array([0]*10 + [1]*5, dtype=np.int32)
    wealth_arr = np.zeros(n_agents, dtype=np.float32)
    civ_arr = np.zeros(n_agents, dtype=np.int32)

    snapshot = pa.RecordBatch.from_pydict({
        "region": pa.array(regions_arr, type=pa.int32()),
        "occupation": pa.array(occupations_arr, type=pa.int32()),
        "wealth": pa.array(wealth_arr, type=pa.float32()),
        "civ_affinity": pa.array(civ_arr, type=pa.int32()),
    })

    region_map = {"Valley": r1, "Hills": r2}
    result = compute_economy(world, snapshot, region_map, agent_mode=True, active_trade_routes=[])

    # Valley should have grain in stockpile (20 initial + 10 farmers × 1.0 yield production - consumption)
    assert r1.stockpile.goods.get("grain", 0.0) > 0.0
    # food_sufficiency should be derived from stockpile
    assert "Valley" in result.food_sufficiency
    assert result.food_sufficiency["Valley"] > 0.0
    # Conservation tracking should have production > 0
    assert result.conservation["production"] > 0.0


# --- Task 14: Conservation Law ---

def test_conservation_law():
    """Global balance: old_stockpile + production = new_stockpile + consumption + transit_loss + storage_loss + cap_overflow."""
    from unittest.mock import MagicMock
    import numpy as np
    import pyarrow as pa
    from chronicler.economy import compute_economy, ALL_GOODS
    from chronicler.models import Region, RegionStockpile

    r1 = Region(name="Breadbasket", terrain="plains", carrying_capacity=50, resources="fertile",
                controller="Alpha", resource_types=[0, 255, 255],
                resource_base_yields=[2.0, 0.0, 0.0],
                resource_effective_yields=[2.0, 0.0, 0.0])
    r1.stockpile = RegionStockpile(goods={"grain": 50.0})
    r1.adjacencies = ["Port"]

    r2 = Region(name="Port", terrain="coast", carrying_capacity=30, resources="maritime",
                controller="Beta", resource_types=[3, 255, 255],
                resource_base_yields=[1.0, 0.0, 0.0],
                resource_effective_yields=[1.0, 0.0, 0.0])
    r2.stockpile = RegionStockpile(goods={"fish": 20.0})
    r2.adjacencies = ["Breadbasket"]

    civ_a = MagicMock()
    civ_a.name = "Alpha"
    civ_a.regions = ["Breadbasket"]
    civ_b = MagicMock()
    civ_b.name = "Beta"
    civ_b.regions = ["Port"]
    world = MagicMock()
    world.regions = [r1, r2]
    world.civilizations = [civ_a, civ_b]
    world.rivers = []
    world.turn = 10

    old_total = sum(amt for r in [r1, r2] for amt in r.stockpile.goods.values())

    n = 35
    regions_arr = np.array([0]*25 + [1]*10, dtype=np.int32)
    occ_arr = np.array([0]*20 + [2]*5 + [0]*10, dtype=np.int32)
    wealth_arr = np.zeros(n, dtype=np.float32)
    civ_arr = np.array([0]*25 + [1]*10, dtype=np.int32)
    snapshot = pa.RecordBatch.from_pydict({
        "region": pa.array(regions_arr, type=pa.int32()),
        "occupation": pa.array(occ_arr, type=pa.int32()),
        "wealth": pa.array(wealth_arr, type=pa.float32()),
        "civ_affinity": pa.array(civ_arr, type=pa.int32()),
    })
    region_map = {"Breadbasket": r1, "Port": r2}

    result = compute_economy(
        world, snapshot, region_map, agent_mode=True,
        active_trade_routes=[("Alpha", "Beta")],
    )

    new_total = sum(amt for r in [r1, r2] for amt in r.stockpile.goods.values())

    c = result.conservation
    inputs = old_total + c["production"]
    outputs = new_total + c["consumption"] + c["transit_loss"] + c["storage_loss"] + c["cap_overflow"] + c["clamp_floor_loss"]
    assert abs(inputs - outputs) < 0.01, (
        f"Conservation violated: inputs={inputs:.2f}, outputs={outputs:.2f}, "
        f"diff={abs(inputs - outputs):.4f}, conservation={c}"
    )
    for r in [r1, r2]:
        for good, amt in r.stockpile.goods.items():
            assert amt >= 0.0, f"Negative stockpile: {r.name}.{good} = {amt}"


# --- Task 15: Backward Compatibility ---

def test_food_sufficiency_backward_compat_full_path():
    """Full compute_economy at equilibrium produces food_sufficiency ~ 1.0 (matches M42)."""
    from unittest.mock import MagicMock
    import numpy as np
    import pyarrow as pa
    from chronicler.economy import compute_economy, PER_CAPITA_FOOD
    from chronicler.models import Region, RegionStockpile

    pop = 20
    food_demand = pop * PER_CAPITA_FOOD
    region = Region(name="Valley", terrain="plains", carrying_capacity=50, resources="fertile",
                    controller="Aram", resource_types=[0, 255, 255],
                    resource_base_yields=[food_demand / pop, 0.0, 0.0],
                    resource_effective_yields=[food_demand / pop, 0.0, 0.0])
    region.stockpile = RegionStockpile(goods={})
    civ = MagicMock()
    civ.name = "Aram"
    civ.regions = ["Valley"]

    world = MagicMock()
    world.regions = [region]
    world.civilizations = [civ]
    world.rivers = []
    world.turn = 10

    regions_arr = np.zeros(pop, dtype=np.int32)
    occ_arr = np.zeros(pop, dtype=np.int32)
    wealth_arr = np.zeros(pop, dtype=np.float32)
    civ_arr = np.zeros(pop, dtype=np.int32)
    snapshot = pa.RecordBatch.from_pydict({
        "region": pa.array(regions_arr, type=pa.int32()),
        "occupation": pa.array(occ_arr, type=pa.int32()),
        "wealth": pa.array(wealth_arr, type=pa.float32()),
        "civ_affinity": pa.array(civ_arr, type=pa.int32()),
    })

    result = compute_economy(world, snapshot, {"Valley": region}, agent_mode=True, active_trade_routes=[])
    assert abs(result.food_sufficiency["Valley"] - 1.0) < 0.01, (
        f"Expected food_sufficiency ~ 1.0, got {result.food_sufficiency['Valley']}"
    )


def test_transport_cost_mountain_vs_river():
    """Mountain routes are more expensive than river routes."""
    from chronicler.economy import compute_transport_cost

    mountain = compute_transport_cost("plains", "mountains", is_river=False, is_coastal=False, is_winter=False)
    river = compute_transport_cost("plains", "plains", is_river=True, is_coastal=False, is_winter=False)
    assert mountain > river * 3, f"Mountain ({mountain}) should be much more than river ({river})"

