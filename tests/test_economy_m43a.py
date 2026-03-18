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
