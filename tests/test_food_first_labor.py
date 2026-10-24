"""Food-first farmer labor split (Python oracle mirror of Rust food_first_slot_labor)."""
import pytest

from chronicler.economy import compute_allocated_production, food_first_slot_labor
from chronicler.models import ResourceType

GRAIN, TIMBER, BOTANICALS, ORE = (
    int(ResourceType.GRAIN), int(ResourceType.TIMBER), int(ResourceType.BOTANICALS), int(ResourceType.ORE),
)
EMPTY = 255


def test_equal_split_without_demand():
    assert food_first_slot_labor([GRAIN, TIMBER, ORE], [1.0, 2.0, 3.0], 60, None) == [20.0, 20.0, 20.0]
    produced = compute_allocated_production([GRAIN, TIMBER, ORE], [1.0, 2.0, 3.0], 60)
    assert produced == {"grain": 20.0, "timber": 40.0, "ore": 60.0}


def test_food_first_covers_demand_then_shares_the_rest():
    # 25 farmers on grain would cover 25 food; the equal share (20) would not.
    labor = food_first_slot_labor([GRAIN, TIMBER, ORE], [1.0, 2.0, 3.0], 60, 25.0)
    assert labor == pytest.approx([25.0, 17.5, 17.5])
    produced = compute_allocated_production(
        [GRAIN, TIMBER, ORE], [1.0, 2.0, 3.0], 60, food_demand=25.0,
    )
    assert produced == pytest.approx({"grain": 25.0, "timber": 35.0, "ore": 52.5})
    assert sum(labor) == pytest.approx(60.0)


def test_non_food_slots_keep_a_quarter_of_their_equal_share():
    labor = food_first_slot_labor([GRAIN, TIMBER, ORE], [1.0, 2.0, 3.0], 60, 50.0)
    assert labor == pytest.approx([50.0, 5.0, 5.0])
    assert food_first_slot_labor([GRAIN, TIMBER, EMPTY], [0.5, 2.0, 0.0], 40, 1000.0) == pytest.approx(
        [35.0, 5.0, 0.0])


def test_food_first_leaves_other_cases_unchanged():
    # Equal share already covers food demand.
    assert food_first_slot_labor([GRAIN, TIMBER, EMPTY], [5.0, 2.0, 0.0], 40, 10.0) == [20.0, 20.0, 0.0]
    # Food-only and zero-food-yield regions keep the equal split.
    assert food_first_slot_labor([GRAIN, BOTANICALS, EMPTY], [1.0, 1.0, 0.0], 40, 1000.0) == [20.0, 20.0, 0.0]
    assert food_first_slot_labor([GRAIN, TIMBER, EMPTY], [0.0, 2.0, 0.0], 40, 1000.0) == [20.0, 20.0, 0.0]
