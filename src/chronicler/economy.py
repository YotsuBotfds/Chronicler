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


# ---------------------------------------------------------------------------
# Task 5: Price computation
# ---------------------------------------------------------------------------

_SUPPLY_FLOOR: float = 0.1


def compute_prices(
    supply: dict[str, float],
    demand: dict[str, float],
) -> dict[str, float]:
    """Compute price per category from supply/demand ratio.

    price = BASE_PRICE × (demand / max(supply, 0.1))
    """
    prices: dict[str, float] = {}
    for cat in CATEGORIES:
        d = demand.get(cat, 0.0)
        s = max(supply.get(cat, 0.0), _SUPPLY_FLOOR)
        prices[cat] = BASE_PRICE * (d / s)
    return prices


# ---------------------------------------------------------------------------
# Tasks 6-7: Trade route decomposition and flow allocation
# ---------------------------------------------------------------------------

def decompose_trade_routes(
    civ_a_regions: set[str],
    civ_b_regions: set[str],
    region_map: dict,
) -> list[tuple[str, str]]:
    """Decompose a civ-level trade route into region-level boundary pairs."""
    pairs: list[tuple[str, str]] = []
    for region_name in civ_a_regions:
        region = region_map[region_name]
        for neighbor_name in region.adjacency:
            if neighbor_name in civ_b_regions:
                pairs.append((region_name, neighbor_name))
    return pairs


def allocate_trade_flow(
    outbound_routes: list[tuple[str, str]],
    origin_prices: dict[str, float],
    dest_prices: dict[str, dict[str, float]],
    exportable_surplus: dict[str, float],
    merchant_count: int,
) -> dict[tuple[str, str], dict[str, float]]:
    """Two-level log-dampened margin-weighted pro-rata allocation.

    Uses pre-trade prices for margin computation.
    Log-dampening (ln(1 + margin)) compresses extreme price ratios.
    """
    capacity = merchant_count * CARRY_PER_MERCHANT
    if capacity <= 0 or not outbound_routes:
        return {route: _empty_category_dict() for route in outbound_routes}

    cat_weights: dict[str, float] = {}
    route_margins: dict[str, dict[tuple[str, str], float]] = {
        cat: {} for cat in CATEGORIES
    }

    for cat in CATEGORIES:
        total_w = 0.0
        for route in outbound_routes:
            _, dest = route
            d_prices = dest_prices.get(dest, {})
            raw_margin = max(d_prices.get(cat, 0.0) - origin_prices.get(cat, 0.0), 0.0)
            weight = math.log1p(raw_margin)
            route_margins[cat][route] = weight
            total_w += weight
        cat_weights[cat] = total_w

    total_weight = sum(cat_weights.values())
    if total_weight <= 0:
        return {route: _empty_category_dict() for route in outbound_routes}

    cat_budgets: dict[str, float] = {}
    for cat in CATEGORIES:
        cat_budgets[cat] = (cat_weights[cat] / total_weight) * capacity

    flow: dict[tuple[str, str], dict[str, float]] = {
        route: _empty_category_dict() for route in outbound_routes
    }

    for cat in CATEGORIES:
        budget = cat_budgets[cat]
        surplus = exportable_surplus.get(cat, 0.0)
        if budget <= 0 or surplus <= 0:
            continue

        cat_total_w = cat_weights[cat]
        if cat_total_w <= 0:
            continue

        allocated = 0.0
        for route in outbound_routes:
            w = route_margins[cat][route]
            if w <= 0:
                continue
            amount = (w / cat_total_w) * budget
            flow[route][cat] = amount
            allocated += amount

        if allocated > surplus:
            scale = surplus / allocated
            for route in outbound_routes:
                flow[route][cat] *= scale

    return flow


# ---------------------------------------------------------------------------
# Tasks 8-9: Signal derivation
# ---------------------------------------------------------------------------

def derive_farmer_income_modifier(
    resource_type: int,
    post_trade_supply: dict[str, float],
    demand: dict[str, float],
) -> float:
    """Derive farmer_income_modifier from post-trade price ratio."""
    cat = map_resource_to_category(resource_type)
    s = max(post_trade_supply.get(cat, 0.0), _SUPPLY_FLOOR)
    d = demand.get(cat, 0.0)
    raw = d / s
    return max(FARMER_INCOME_MODIFIER_FLOOR, min(raw, FARMER_INCOME_MODIFIER_CAP))


def derive_food_sufficiency(food_supply: float, food_demand: float) -> float:
    """Derive food_sufficiency from post-trade food supply/demand ratio. Clamped [0.0, 2.0]."""
    d = max(food_demand, _SUPPLY_FLOOR)
    return max(0.0, min(food_supply / d, 2.0))


def derive_merchant_margin(total_raw_margin: float, route_count: int) -> float:
    """Derive merchant_margin. Normalized to [0.0, 1.0]."""
    if route_count <= 0:
        return 0.0
    avg = total_raw_margin / route_count
    return max(0.0, min(avg / MERCHANT_MARGIN_NORMALIZER, 1.0))


def derive_merchant_trade_income(
    total_arbitrage: float,
    merchant_count: int,
) -> float:
    """Derive per-merchant income from total arbitrage profit."""
    if merchant_count <= 0:
        return 0.0
    return total_arbitrage / merchant_count
