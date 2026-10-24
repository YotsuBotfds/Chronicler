"""Food-logistics corrections (2026-10): goods-economy subsistence.

See docs/integration/food-logistics-2026-10.md.
"""
from __future__ import annotations

import pytest

from chronicler.economy import (
    PER_CAPITA_FOOD,
    compute_allocated_production,
    farm_labor,
    food_first_slot_labor,
)
from chronicler.ecology import goods_per_worker, subsistence_goods_per_worker
from chronicler.models import ClimatePhase, ResourceType
from chronicler.resources import CLIMATE_CLASS_MOD, _CLIMATE_PHASE_INDEX

GRAIN, TIMBER, FISH = int(ResourceType.GRAIN), int(ResourceType.TIMBER), int(ResourceType.FISH)
ORE, PRECIOUS = int(ResourceType.ORE), int(ResourceType.PRECIOUS)
EMPTY = 255


# --- Subsistence rate ------------------------------------------------------

@pytest.mark.parametrize("phase", list(ClimatePhase))
def test_subsistence_rate_is_the_m34_baseline_in_grain_goods(phase):
    crop = CLIMATE_CLASS_MOD[0][_CLIMATE_PHASE_INDEX[phase.value]]
    assert subsistence_goods_per_worker(None, phase) == pytest.approx(
        goods_per_worker(GRAIN, 0.15 * crop))


def test_subsistence_rate_reads_the_tuning_override():
    class World:
        tuning_overrides = {"ecology.subsistence_baseline": 0.30}
    assert subsistence_goods_per_worker(World(), ClimatePhase.TEMPERATE) == pytest.approx(
        2 * subsistence_goods_per_worker(None, ClimatePhase.TEMPERATE))


def test_subsistence_feeds_a_forager_under_half_a_ration_in_temperate():
    rate = subsistence_goods_per_worker(None, ClimatePhase.TEMPERATE)
    assert 0.0 < rate < PER_CAPITA_FOOD


# --- Labor split (mirror of Rust allocate_farm_labor) ---------------------

def test_farm_labor_without_foraging_is_the_food_first_split():
    labor, forage, rate = farm_labor([GRAIN, ORE, EMPTY], [1.0, 2.0, 0.0], 40, 30.0, 0.36)
    assert labor == food_first_slot_labor([GRAIN, ORE, EMPTY], [1.0, 2.0, 0.0], 40, 30.0)
    assert (forage, rate) == (0.0, 0.0)
    _, forage, _ = farm_labor([GRAIN, ORE, EMPTY], [0.01, 2.0, 0.0], 40, 30.0, 0.36)
    assert forage == 0.0


def test_farm_labor_forages_without_a_food_slot():
    labor, forage, rate = farm_labor([ORE, PRECIOUS, EMPTY], [1.0, 1.0, 0.0], 30, 5.0, 0.25)
    assert forage == pytest.approx(20.0)
    assert labor == pytest.approx([5.0, 5.0, 0.0])
    assert rate == 0.25
    labor, forage, _ = farm_labor([ORE, PRECIOUS, EMPTY], [1.0, 1.0, 0.0], 30, 500.0, 0.25)
    assert forage == pytest.approx(25.0)
    assert labor[0] == pytest.approx(2.5)
    _, forage, _ = farm_labor([EMPTY] * 3, [0.0] * 3, 12, 1.0, 0.25)
    assert forage == 12
    labor, forage, _ = farm_labor([ORE, PRECIOUS, EMPTY], [1.0, 1.0, 0.0], 30, 9.0, 0.3)
    assert sum(labor) + forage == pytest.approx(30.0)


def test_farm_labor_forages_on_barren_food_slots():
    labor, forage, _ = farm_labor([GRAIN, FISH, ORE], [0.0, 0.0, 2.0], 30, 100.0, 0.3)
    assert labor[:2] == [0.0, 0.0]
    assert labor[2] == pytest.approx(2.5)
    assert forage == pytest.approx(27.5)


def test_allocated_production_credits_foraged_grain():
    produced = compute_allocated_production(
        [ORE, EMPTY, EMPTY], [1.0, 0.0, 0.0], 10, food_demand=10.0, subsistence_yield=0.4)
    assert produced["grain"] == pytest.approx(8.75 * 0.4)
    assert produced["ore"] == pytest.approx(1.25)
    # Without the rate (the default) nothing changes.
    assert compute_allocated_production(
        [ORE, EMPTY, EMPTY], [1.0, 0.0, 0.0], 10, food_demand=10.0) == {"ore": 10.0}
