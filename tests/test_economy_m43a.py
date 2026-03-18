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
