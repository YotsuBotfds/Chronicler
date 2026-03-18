"""M42: Goods production, trade flow, and supply-demand pricing.

Computes regional goods production from farmer counts × resource yields,
routes surplus along M35 trade corridors via margin-weighted pro-rata
allocation, derives per-region prices from supply/demand ratios, and
produces FFI signals for Rust agent behavior.

Called from simulation.py Phase 2 before existing treasury logic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants  [CALIBRATE] — all tunable, see spec for tuning targets
# ---------------------------------------------------------------------------

BASE_PRICE: float = 1.0
PER_CAPITA_FOOD: float = 0.5
RAW_MATERIAL_PER_SOLDIER: float = 0.3
LUXURY_PER_WEALTHY_AGENT: float = 0.2
LUXURY_DEMAND_THRESHOLD: float = 10.0
CARRY_PER_MERCHANT: float = 1.0
FARMER_INCOME_MODIFIER_FLOOR: float = 0.5
FARMER_INCOME_MODIFIER_CAP: float = 3.0
MERCHANT_MARGIN_NORMALIZER: float = 5.0
TAX_RATE: float = 0.05

CATEGORIES: tuple[str, ...] = ("food", "raw_material", "luxury")

_CATEGORY_MAP: dict[int, str] = {
    0: "food",          # GRAIN
    1: "raw_material",  # TIMBER
    2: "food",          # BOTANICALS
    3: "food",          # FISH
    4: "food",          # SALT
    5: "raw_material",  # ORE
    6: "luxury",        # PRECIOUS
    7: "food",          # EXOTIC
}


def map_resource_to_category(resource_type: int) -> str:
    """Map M34 resource type enum value to one of three goods categories."""
    return _CATEGORY_MAP[resource_type]


def _empty_category_dict() -> dict[str, float]:
    """Return zeroed dict for all three categories."""
    return {cat: 0.0 for cat in CATEGORIES}


@dataclass
class RegionGoods:
    """Transient per-region goods state for one turn. Not persisted."""

    production: dict[str, float] = field(default_factory=_empty_category_dict)
    imports: dict[str, float] = field(default_factory=_empty_category_dict)
    exports: dict[str, float] = field(default_factory=_empty_category_dict)
    prices: dict[str, float] = field(default_factory=_empty_category_dict)


@dataclass
class EconomyResult:
    """Output of compute_economy(). Consumed by simulation.py, then dropped."""

    region_goods: dict[str, RegionGoods] = field(default_factory=dict)
    farmer_income_modifiers: dict[str, float] = field(default_factory=dict)
    food_sufficiency: dict[str, float] = field(default_factory=dict)
    merchant_margins: dict[str, float] = field(default_factory=dict)
    merchant_trade_incomes: dict[str, float] = field(default_factory=dict)
    trade_route_counts: dict[str, int] = field(default_factory=dict)
    priest_tithe_shares: dict[int, float] = field(default_factory=dict)
    treasury_tax: dict[int, float] = field(default_factory=dict)
    tithe_base: dict[int, float] = field(default_factory=dict)


def compute_production(
    resource_type: int,
    resource_yield: float,
    farmer_count: int,
) -> tuple[str, float]:
    """Compute goods output for a region.

    Returns (category, amount). Only primary resource slot (index 0) is used.
    """
    category = map_resource_to_category(resource_type)
    amount = resource_yield * farmer_count
    return category, amount


def compute_demand(
    population: int,
    soldier_count: int,
    wealthy_count: int,
) -> dict[str, float]:
    """Compute per-region demand for each goods category.

    Args:
        population: total agent count in region (everyone eats)
        soldier_count: agents with occupation == Soldier
        wealthy_count: agents with wealth > LUXURY_DEMAND_THRESHOLD
    """
    return {
        "food": population * PER_CAPITA_FOOD,
        "raw_material": soldier_count * RAW_MATERIAL_PER_SOLDIER,
        "luxury": wealthy_count * LUXURY_PER_WEALTHY_AGENT,
    }
