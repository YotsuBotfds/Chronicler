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

import numpy as np

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

# ---------------------------------------------------------------------------
# M43a Constants  [CALIBRATE]
# ---------------------------------------------------------------------------

FOOD_GOODS: frozenset[str] = frozenset({"grain", "fish", "botanicals", "exotic", "salt"})
ALL_GOODS: frozenset[str] = frozenset({
    "grain", "timber", "botanicals", "fish", "salt", "ore", "precious", "exotic",
})

TERRAIN_COST: dict[str, float] = {
    "plains": 1.0,
    "forest": 1.3,
    "desert": 1.5,
    "mountains": 2.0,
    "tundra": 1.8,
    "coast": 0.6,
}
TRANSPORT_COST_BASE: float = 0.10
RIVER_DISCOUNT: float = 0.5
COASTAL_DISCOUNT: float = 0.6
INFRASTRUCTURE_DISCOUNT: float = 1.0  # placeholder — no roads yet
WINTER_MODIFIER: float = 1.5

TRANSIT_DECAY: dict[str, float] = {
    "grain": 0.05, "fish": 0.08, "botanicals": 0.04, "exotic": 0.06,
    "salt": 0.0, "timber": 0.01, "ore": 0.0, "precious": 0.0,
}
STORAGE_DECAY: dict[str, float] = {
    "grain": 0.03, "fish": 0.06, "botanicals": 0.02, "exotic": 0.04,
    "salt": 0.0, "timber": 0.005, "ore": 0.0, "precious": 0.0,
}

SALT_PRESERVATION_FACTOR: float = 2.5
MAX_PRESERVATION: float = 0.5

CATEGORY_GOODS: dict[str, frozenset[str]] = {
    "food": frozenset({"grain", "fish", "botanicals", "exotic", "salt"}),
    "raw_material": frozenset({"timber", "ore"}),
    "luxury": frozenset({"precious"}),
}

TRADE_DEPENDENCY_THRESHOLD: float = 0.6  # [CALIBRATE] >60% food import share

PER_GOOD_CAP_FACTOR: float = 5.0 * PER_CAPITA_FOOD
INITIAL_BUFFER: float = 2.0 * PER_CAPITA_FOOD
CONQUEST_STOCKPILE_SURVIVAL: float = 0.5

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


_GOOD_MAP: dict[int, str] = {
    0: "grain", 1: "timber", 2: "botanicals", 3: "fish",
    4: "salt", 5: "ore", 6: "precious", 7: "exotic",
}


def map_resource_to_good(resource_type: int) -> str:
    """Map M34 resource type enum value to per-good stockpile key."""
    return _GOOD_MAP[resource_type]


# ---------------------------------------------------------------------------
# M43a: Transport cost
# ---------------------------------------------------------------------------

def build_river_route_set(rivers: list) -> set[frozenset]:
    """Pre-build set of river-connected region pairs for O(1) lookup.

    Each River.path is an ordered list of region names along the river.
    Adjacent pairs in the path are river-connected.
    """
    pairs: set[frozenset] = set()
    for river in rivers:
        path = river.path
        for i in range(len(path) - 1):
            pairs.add(frozenset({path[i], path[i + 1]}))
    return pairs


# ---------------------------------------------------------------------------
# M43a: Perishability — transit decay
# ---------------------------------------------------------------------------

def apply_transit_decay(shipped: float, good: str) -> float:
    """Apply per-good transit decay to shipped volume. Returns delivered amount."""
    rate = TRANSIT_DECAY.get(good, 0.0)
    return shipped * (1.0 - rate)


# ---------------------------------------------------------------------------
# M43a: Perishability — storage decay with salt preservation
# ---------------------------------------------------------------------------

def apply_storage_decay(goods: dict[str, float]) -> float:
    """Apply per-turn storage decay to stockpile goods dict. Mutates in place.

    Salt preservation: proportional to salt-to-food ratio, capped at MAX_PRESERVATION.
    Only affects food goods. Salt itself has zero decay.
    Returns total storage loss (for conservation law verification).
    """
    total_food = sum(goods.get(g, 0.0) for g in FOOD_GOODS if g != "salt")
    salt_amount = goods.get("salt", 0.0)
    salt_ratio = salt_amount / max(total_food, 0.1)
    preservation = min(salt_ratio * SALT_PRESERVATION_FACTOR, MAX_PRESERVATION)

    total_loss = 0.0
    for good in list(goods.keys()):
        if good == "salt":
            continue
        rate = STORAGE_DECAY.get(good, 0.0)
        if rate <= 0.0:
            continue
        if good in FOOD_GOODS:
            rate *= (1.0 - preservation)
        old = goods[good]
        goods[good] *= (1.0 - rate)
        total_loss += old - goods[good]
    return total_loss


# ---------------------------------------------------------------------------
# M43a: Stockpile operations
# ---------------------------------------------------------------------------

def accumulate_stockpile(
    goods: dict[str, float],
    production: dict[str, float],
    exports: dict[str, float],
    imports: dict[str, float],
) -> None:
    """Add (production - exports + imports) to stockpile per good. Mutates in place."""
    all_keys = set(goods.keys()) | set(production.keys()) | set(exports.keys()) | set(imports.keys())
    for good in all_keys:
        current = goods.get(good, 0.0)
        produced = production.get(good, 0.0)
        exported = exports.get(good, 0.0)
        imported = imports.get(good, 0.0)
        goods[good] = max(current + (produced - exported) + imported, 0.0)


def derive_food_sufficiency_from_stockpile(
    goods: dict[str, float],
    food_demand: float,
) -> float:
    """Derive food_sufficiency from pre-consumption stockpile. Clamped [0.0, 2.0].

    Computed BEFORE demand drawdown (Decision 9). Sum all food goods including salt.
    """
    total_food = sum(goods.get(g, 0.0) for g in FOOD_GOODS)
    d = max(food_demand, _SUPPLY_FLOOR)
    return max(0.0, min(total_food / d, 2.0))


def consume_from_stockpile(
    goods: dict[str, float],
    food_demand: float,
) -> float:
    """Draw food demand from stockpile proportional to composition. Mutates in place.

    Clamped: consumption per good can't exceed available stockpile.
    Returns total consumed (for conservation law verification).
    """
    total_food = sum(goods.get(g, 0.0) for g in FOOD_GOODS)
    if total_food <= 0.0 or food_demand <= 0.0:
        return 0.0
    total_consumed = 0.0
    for good in FOOD_GOODS:
        amount = goods.get(good, 0.0)
        if amount <= 0.0:
            continue
        share = amount / total_food
        demand_for_good = food_demand * share
        consumed = min(demand_for_good, amount)
        goods[good] = amount - consumed
        total_consumed += consumed
    return total_consumed


def apply_stockpile_cap(
    goods: dict[str, float],
    population: int,
) -> float:
    """Cap each good at PER_GOOD_CAP_FACTOR * population. Mutates in place.

    Returns total overflow (for conservation law verification).
    """
    cap = PER_GOOD_CAP_FACTOR * population
    total_overflow = 0.0
    for good in list(goods.keys()):
        if goods[good] > cap:
            total_overflow += goods[good] - cap
            goods[good] = cap
    return total_overflow


def compute_transport_cost(
    terrain_a: str,
    terrain_b: str,
    *,
    is_river: bool,
    is_coastal: bool,
    is_winter: bool,
) -> float:
    """Per-route transport cost. Subtracted from raw margin for effective margin.

    Args:
        terrain_a: Terrain type of origin region.
        terrain_b: Terrain type of destination region.
        is_river: Both regions on same river path.
        is_coastal: Both regions are coast terrain.
        is_winter: Current season is winter.
    """
    terrain_factor = max(TERRAIN_COST.get(terrain_a, 1.0), TERRAIN_COST.get(terrain_b, 1.0))
    river = RIVER_DISCOUNT if is_river else 1.0
    coastal = COASTAL_DISCOUNT if is_coastal else 1.0
    seasonal = WINTER_MODIFIER if is_winter else 1.0
    infra = INFRASTRUCTURE_DISCOUNT
    return TRANSPORT_COST_BASE * terrain_factor * infra * min(river, coastal) * seasonal


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
    # M43a: Conservation law tracking
    conservation: dict[str, float] = field(default_factory=lambda: {
        "production": 0.0, "transit_loss": 0.0, "consumption": 0.0,
        "storage_loss": 0.0, "cap_overflow": 0.0,
    })
    # M43b: Supply shock detection and trade dependency
    imports_by_region: dict[str, dict[str, float]] = field(default_factory=dict)
    inbound_sources: dict[str, list[str]] = field(default_factory=dict)
    stockpile_levels: dict[str, dict[str, float]] = field(default_factory=dict)
    import_share: dict[str, float] = field(default_factory=dict)
    trade_dependent: dict[str, bool] = field(default_factory=dict)


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
        for neighbor_name in region.adjacencies:
            if neighbor_name in civ_b_regions:
                pairs.append((region_name, neighbor_name))
    return pairs


def allocate_trade_flow(
    outbound_routes: list[tuple[str, str]],
    origin_prices: dict[str, float],
    dest_prices: dict[str, dict[str, float]],
    exportable_surplus: dict[str, float],
    merchant_count: int,
    transport_costs: dict[tuple[str, str], float] | None = None,
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
            price_gap = d_prices.get(cat, 0.0) - origin_prices.get(cat, 0.0)
            t_cost = transport_costs.get(route, 0.0) if transport_costs else 0.0
            raw_margin = max(price_gap - t_cost, 0.0)
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


# ---------------------------------------------------------------------------
# Task 10: Agent data extraction helpers
# ---------------------------------------------------------------------------

def _extract_region_agent_counts_from_arrays(
    regions: np.ndarray,
    occupations: np.ndarray,
    wealth: np.ndarray,
    region_idx: int,
) -> dict:
    """Extract occupation counts and wealthy agent count for a region.
    Takes pre-extracted numpy arrays (extracted once, not per-region).
    """
    mask = regions == region_idx
    occ = occupations[mask]
    w = wealth[mask]
    return {
        "population": int(mask.sum()),
        "farmer_count": int((occ == 0).sum()),
        "soldier_count": int((occ == 1).sum()),
        "merchant_count": int((occ == 2).sum()),
        "scholar_count": int((occ == 3).sum()),
        "priest_count": int((occ == 4).sum()),
        "wealthy_count": int((w > LUXURY_DEMAND_THRESHOLD).sum()),
    }


def _extract_civ_merchant_wealth(
    civ_affinity: np.ndarray,
    occupations: np.ndarray,
    wealth: np.ndarray,
    civ_idx: int,
) -> float:
    """Sum of merchant wealth for a civ. Uses pre-extracted arrays."""
    mask = (civ_affinity == civ_idx) & (occupations == 2)
    return float(np.sum(wealth[mask]))


def _extract_civ_priest_count(
    civ_affinity: np.ndarray,
    occupations: np.ndarray,
    civ_idx: int,
) -> int:
    """Count of priests for a civ. Uses pre-extracted arrays."""
    mask = (civ_affinity == civ_idx) & (occupations == 4)
    return int(mask.sum())


# ---------------------------------------------------------------------------
# Task 10: compute_economy entry point
# ---------------------------------------------------------------------------

def compute_economy(
    world,
    snapshot,
    region_map: dict,
    agent_mode: bool,
    active_trade_routes: list[tuple[str, str]] | None = None,
) -> EconomyResult:
    """Phase 2 goods sub-sequence: production -> demand -> prices -> trade -> signals.

    Two-pass price model:
    - Pre-trade prices (from production alone) drive margin computation
    - Post-trade prices (from production + imports) produce final signals
    """
    if active_trade_routes is None:
        from chronicler.resources import get_active_trade_routes
        active_trade_routes = get_active_trade_routes(world)

    result = EconomyResult()
    regions = world.regions
    civs = world.civilizations

    # Build lookups
    civ_lookup: dict[str, tuple[int, set[str]]] = {}
    for civ_idx, civ in enumerate(civs):
        if len(civ.regions) > 0:
            civ_lookup[civ.name] = (civ_idx, set(civ.regions))

    region_idx_map: dict[str, int] = {}
    for i, region in enumerate(regions):
        region_idx_map[region.name] = i

    # M43a: Build river route set for transport cost lookups
    river_pairs = build_river_route_set(world.rivers) if hasattr(world, 'rivers') and world.rivers else set()
    from chronicler.resources import get_season_id
    is_winter = get_season_id(world.turn) == 3

    # Extract snapshot arrays ONCE
    snap_regions = snapshot.column("region").to_numpy()
    snap_occupations = snapshot.column("occupation").to_numpy()
    snap_wealth = snapshot.column("wealth").to_numpy()
    snap_civ_affinity = snapshot.column("civ_affinity").to_numpy()

    # --- Step 2a: Production + Step 2b: Demand ---
    region_production: dict[str, dict[str, float]] = {}
    region_demand: dict[str, dict[str, float]] = {}
    region_agent_data: dict[str, dict] = {}

    for region in regions:
        rname = region.name
        ridx = region_idx_map[rname]
        agent_data = _extract_region_agent_counts_from_arrays(
            snap_regions, snap_occupations, snap_wealth, ridx,
        )
        region_agent_data[rname] = agent_data

        prod = _empty_category_dict()
        cat, amount = compute_production(
            region.resource_types[0], region.resource_effective_yields[0], agent_data["farmer_count"],
        )
        prod[cat] = amount
        result.conservation["production"] += amount
        region_production[rname] = prod

        demand = compute_demand(
            agent_data["population"], agent_data["soldier_count"], agent_data["wealthy_count"],
        )
        region_demand[rname] = demand

    # --- Step 2c: Pre-trade prices ---
    pre_trade_prices: dict[str, dict[str, float]] = {}
    for rname in region_production:
        pre_trade_prices[rname] = compute_prices(region_production[rname], region_demand[rname])

    # --- Step 2d: Exportable surplus ---
    exportable_surplus: dict[str, dict[str, float]] = {}
    for rname in region_production:
        exportable_surplus[rname] = {
            cat: max(region_production[rname][cat] - region_demand[rname][cat], 0.0)
            for cat in CATEGORIES
        }

    # --- Step 2e: Trade flow ---
    origin_routes: dict[str, list[tuple[str, str]]] = {}
    boundary_pair_counts: dict[str, int] = {}

    for civ_a_name, civ_b_name in active_trade_routes:
        if civ_a_name not in civ_lookup or civ_b_name not in civ_lookup:
            continue
        _, a_regions = civ_lookup[civ_a_name]
        _, b_regions = civ_lookup[civ_b_name]
        # Both directions
        for src_regions, dst_regions in [(a_regions, b_regions), (b_regions, a_regions)]:
            pairs = decompose_trade_routes(src_regions, dst_regions, region_map)
            for origin, dest in pairs:
                origin_routes.setdefault(origin, []).append((origin, dest))
                boundary_pair_counts[origin] = boundary_pair_counts.get(origin, 0) + 1

    # M43a: Compute transport costs per route
    route_transport_costs: dict[tuple[str, str], float] = {}
    for origin_name, routes in origin_routes.items():
        origin_region = region_map.get(origin_name)
        if origin_region is None:
            continue
        for route in routes:
            _, dest_name = route
            dest_region = region_map.get(dest_name)
            if dest_region is None:
                continue
            is_river = frozenset({origin_name, dest_name}) in river_pairs
            is_coastal = origin_region.terrain == "coast" and dest_region.terrain == "coast"
            route_transport_costs[route] = compute_transport_cost(
                origin_region.terrain, dest_region.terrain,
                is_river=is_river, is_coastal=is_coastal, is_winter=is_winter,
            )

    region_imports: dict[str, dict[str, float]] = {rname: _empty_category_dict() for rname in region_production}
    region_exports: dict[str, dict[str, float]] = {rname: _empty_category_dict() for rname in region_production}
    all_route_flows: dict[str, dict[tuple[str, str], dict[str, float]]] = {}

    for origin_name, routes in origin_routes.items():
        if origin_name not in region_production:
            continue
        merchant_count = region_agent_data.get(origin_name, {}).get("merchant_count", 0)
        dest_prices: dict[str, dict[str, float]] = {}
        for _, dest in routes:
            if dest in pre_trade_prices:
                dest_prices[dest] = pre_trade_prices[dest]

        flow = allocate_trade_flow(
            routes, pre_trade_prices.get(origin_name, _empty_category_dict()),
            dest_prices, exportable_surplus.get(origin_name, _empty_category_dict()),
            merchant_count,
            transport_costs=route_transport_costs,
        )
        all_route_flows[origin_name] = flow

        for route, cat_flows in flow.items():
            _, dest = route
            for cat in CATEGORIES:
                amount = cat_flows[cat]
                region_exports[origin_name][cat] += amount
                region_imports.setdefault(dest, _empty_category_dict())
                region_imports[dest][cat] += amount
                if amount > 0:
                    result.inbound_sources.setdefault(dest, [])
                    if origin_name not in result.inbound_sources[dest]:
                        result.inbound_sources[dest].append(origin_name)

    # M43a: Decompose category-level flows to per-good with transit decay
    # Pre-seed with empty dicts for all known regions; import targets may include
    # regions outside region_production (handled by setdefault in the loop below).
    region_per_good_imports: dict[str, dict[str, float]] = {rname: {} for rname in region_production}
    region_per_good_exports: dict[str, dict[str, float]] = {}
    region_per_good_production: dict[str, dict[str, float]] = {}

    for region in regions:
        rname = region.name
        # Per-good production
        if region.resource_types[0] != 255:
            good = map_resource_to_good(region.resource_types[0])
            cat = map_resource_to_category(region.resource_types[0])
            region_per_good_production[rname] = {good: region_production.get(rname, _empty_category_dict()).get(cat, 0.0)}
        else:
            region_per_good_production[rname] = {}

        # Per-good exports
        if region.resource_types[0] != 255:
            good = map_resource_to_good(region.resource_types[0])
            cat = map_resource_to_category(region.resource_types[0])
            region_per_good_exports[rname] = {good: region_exports.get(rname, _empty_category_dict()).get(cat, 0.0)}
        else:
            region_per_good_exports[rname] = {}

    # Per-good imports with transit decay (per-route, per-good, decay before aggregate).
    # NOTE: Only decomposes flows matching the origin's primary resource category.
    # Non-primary-category flows (if any) are silently dropped. Correct today due to
    # single-resource-slot constraint (M41 Decision 14). A future multi-slot milestone
    # would need to decompose across all production categories to maintain conservation.
    for origin_name, route_flows_for_origin in all_route_flows.items():
        origin_region = region_map.get(origin_name)
        if origin_region is None or origin_region.resource_types[0] == 255:
            continue
        source_good = map_resource_to_good(origin_region.resource_types[0])
        source_cat = map_resource_to_category(origin_region.resource_types[0])
        for route, cat_flows in route_flows_for_origin.items():
            _, dest_name = route
            shipped = cat_flows.get(source_cat, 0.0)
            if shipped <= 0.0:
                continue
            delivered = apply_transit_decay(shipped, source_good)
            result.conservation["transit_loss"] += shipped - delivered
            dest_imports = region_per_good_imports.setdefault(dest_name, {})
            dest_imports[source_good] = dest_imports.get(source_good, 0.0) + delivered

    # --- Step 2f: Post-trade prices ---
    post_trade_prices: dict[str, dict[str, float]] = {}
    for rname in region_production:
        post_trade_supply = {
            cat: region_production[rname][cat] + region_imports[rname][cat]
            for cat in CATEGORIES
        }
        post_trade_prices[rname] = compute_prices(post_trade_supply, region_demand[rname])

    # --- M43a: Steps 2g-2l — Stockpile sub-sequence ---
    for region in regions:
        rname = region.name
        demand = region_demand.get(rname, _empty_category_dict())

        # Step 2g: Stockpile accumulation
        accumulate_stockpile(
            region.stockpile.goods,
            production=region_per_good_production.get(rname, {}),
            exports=region_per_good_exports.get(rname, {}),
            imports=region_per_good_imports.get(rname, {}),
        )

        # Step 2h: food_sufficiency from pre-consumption stockpile
        food_demand = demand.get("food", 0.0)
        result.food_sufficiency[rname] = derive_food_sufficiency_from_stockpile(
            region.stockpile.goods, food_demand,
        )

        # Step 2i: Demand drawdown from stockpile (clamped)
        consumed = consume_from_stockpile(region.stockpile.goods, food_demand)
        result.conservation["consumption"] += consumed

        # Step 2j: Storage decay with salt preservation
        storage_loss = apply_storage_decay(region.stockpile.goods)
        result.conservation["storage_loss"] += storage_loss

        # Step 2k: Cap stockpile (use region.population — physical storage capacity)
        cap_overflow = apply_stockpile_cap(region.stockpile.goods, region.population)
        result.conservation["cap_overflow"] += cap_overflow

    # --- M43b: Capture imports_by_region, stockpile_levels, trade dependency ---
    for region in regions:
        rname = region.name
        result.imports_by_region[rname] = dict(region_imports.get(rname, _empty_category_dict()))
        cat_stockpile = _empty_category_dict()
        for good, amount in region.stockpile.goods.items():
            for cat, goods_set in CATEGORY_GOODS.items():
                if good in goods_set:
                    cat_stockpile[cat] += amount
                    break
        result.stockpile_levels[rname] = cat_stockpile
        food_demand = region_demand.get(rname, _empty_category_dict()).get("food", 0.0)
        food_imports = region_imports.get(rname, _empty_category_dict()).get("food", 0.0)
        share = food_imports / max(food_demand, 0.1)
        result.import_share[rname] = share
        result.trade_dependent[rname] = share > TRADE_DEPENDENCY_THRESHOLD

    # --- Signal derivation ---
    for region in regions:
        rname = region.name
        agent_data = region_agent_data.get(rname, {})
        post_prices = post_trade_prices.get(rname, _empty_category_dict())
        demand = region_demand.get(rname, _empty_category_dict())
        post_supply = {
            cat: region_production.get(rname, _empty_category_dict())[cat]
                 + region_imports.get(rname, _empty_category_dict())[cat]
            for cat in CATEGORIES
        }

        result.farmer_income_modifiers[rname] = derive_farmer_income_modifier(
            region.resource_types[0], post_supply, demand,
        )

        routes = origin_routes.get(rname, [])
        total_raw_margin = 0.0
        for route in routes:
            _, dest = route
            dest_post = post_trade_prices.get(dest, _empty_category_dict())
            for cat in CATEGORIES:
                total_raw_margin += max(dest_post[cat] - post_prices[cat], 0.0)
        result.merchant_margins[rname] = derive_merchant_margin(total_raw_margin, len(routes))

        # merchant_trade_income: route_flow x post-trade margin (intentional mismatch)
        total_arbitrage = 0.0
        route_flows = all_route_flows.get(rname, {})
        for route, cat_flows in route_flows.items():
            _, dest = route
            dest_post = post_trade_prices.get(dest, _empty_category_dict())
            for cat in CATEGORIES:
                margin = max(dest_post[cat] - post_prices[cat], 0.0)
                total_arbitrage += cat_flows[cat] * margin
        result.merchant_trade_incomes[rname] = derive_merchant_trade_income(
            total_arbitrage, agent_data.get("merchant_count", 0),
        )

        result.trade_route_counts[rname] = boundary_pair_counts.get(rname, 0)

        rg = RegionGoods(
            production=region_production.get(rname, _empty_category_dict()),
            imports=region_imports.get(rname, _empty_category_dict()),
            exports=region_exports.get(rname, _empty_category_dict()),
            prices=dict(post_prices),
        )
        result.region_goods[rname] = rg

    # --- M41 deferred integrations (agent mode only) ---
    if agent_mode:
        from chronicler.factions import TITHE_RATE

        for civ_name, (civ_idx, _) in civ_lookup.items():
            merchant_wealth = _extract_civ_merchant_wealth(
                snap_civ_affinity, snap_occupations, snap_wealth, civ_idx,
            )
            priest_count = _extract_civ_priest_count(
                snap_civ_affinity, snap_occupations, civ_idx,
            )
            result.treasury_tax[civ_idx] = TAX_RATE * merchant_wealth
            result.tithe_base[civ_idx] = merchant_wealth
            result.priest_tithe_shares[civ_idx] = (
                TITHE_RATE * merchant_wealth / max(priest_count, 1)
            )

    return result
