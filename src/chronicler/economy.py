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
from chronicler.utils import get_region_map

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

# M54b: Fixed good slot ordering for FFI — no variable-length dicts cross the boundary
FIXED_GOODS: tuple[str, ...] = (
    "grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic",
)

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


def bootstrap_region_stockpile(region, population: int | None = None) -> bool:
    """Seed a newly settled region with a minimal starting stockpile.

    The bootstrap mirrors turn-0 world generation: seed the primary good for the
    region's current population, and also seed grain when the primary good is
    not itself food. Existing goods are preserved.
    """
    if region.resource_types[0] == 255:
        return False

    target_population = region.population if population is None else population
    if target_population <= 0:
        return False

    good = map_resource_to_good(region.resource_types[0])
    amount = INITIAL_BUFFER * target_population
    seeded = False

    if region.stockpile.goods.get(good, 0.0) <= 0.0:
        region.stockpile.goods[good] = amount
        seeded = True

    if good not in FOOD_GOODS:
        food_total = sum(region.stockpile.goods.get(food, 0.0) for food in FOOD_GOODS)
        if food_total <= 0.0:
            region.stockpile.goods["grain"] = amount
            seeded = True

    return seeded


def settle_pending_stockpile_bootstraps(regions: list) -> int:
    """Fulfill one-shot region bootstrap requests once settlers are present."""
    settled = 0
    for region in regions:
        if not getattr(region, "_stockpile_bootstrap_pending", False):
            continue
        if region.controller is None or region.resource_types[0] == 255:
            region._stockpile_bootstrap_pending = False
            continue
        if region.population <= 0:
            continue
        bootstrap_region_stockpile(region)
        region._stockpile_bootstrap_pending = False
        settled += 1
    return settled


# ---------------------------------------------------------------------------
# M43b: EconomyTracker — persistent analytics state across turns
# ---------------------------------------------------------------------------

class EconomyTracker:
    """Persistent economy analytics state across turns. Not world state.

    Tracks exponential moving averages (alpha=0.33, ~3-turn window) for:
    - Per-region per-category stockpile levels (shock detection)
    - Per-region per-category import levels (upstream source classification)
    """

    def __init__(self):
        self.trailing_avg: dict[str, dict[str, float]] = {}
        self.import_avg: dict[str, dict[str, float]] = {}

    def update_stockpile(self, region_name: str, category: str, current: float):
        key = self.trailing_avg.setdefault(region_name, {})
        if category not in key:
            key[category] = current
        else:
            key[category] = 0.67 * key[category] + 0.33 * current

    def update_imports(self, region_name: str, category: str, current: float):
        key = self.import_avg.setdefault(region_name, {})
        if category not in key:
            key[category] = current
        else:
            key[category] = 0.67 * key[category] + 0.33 * current


# M43b constants
SHOCK_DELTA_THRESHOLD = 0.30  # [CALIBRATE] 30% drop triggers detection
SHOCK_SEVERITY_FLOOR = 0.8   # [CALIBRATE] food_sufficiency below this = crisis

# M43b: Raider constants
RAIDER_THRESHOLD = 200.0  # [CALIBRATE] set after M43a 200-seed data
RAIDER_WAR_WEIGHT = 0.15  # [CALIBRATE] base additive WAR bonus at 1x overshoot
RAIDER_CAP = 2.0          # max overshoot multiplier (bonus caps at 0.30)


def _get_adjacent_enemy_regions(civ, world) -> list:
    """Find regions adjacent to civ's territory controlled by hostile/suspicious civs."""
    from chronicler.models import Disposition

    enemy_civs = set()
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                enemy_civs.add(other_name)
    if not enemy_civs:
        return []

    region_map = get_region_map(world)
    own_regions = set(civ.regions)
    adjacent_enemy = []
    seen = set()
    for rname in own_regions:
        region = region_map.get(rname)
        if region is None:
            continue
        for adj_name in region.adjacencies:
            if adj_name in seen:
                continue
            adj_region = region_map.get(adj_name)
            if adj_region and adj_region.controller in enemy_civs:
                adjacent_enemy.append(adj_region)
                seen.add(adj_name)
    return adjacent_enemy


def classify_upstream_source(
    world,
    economy_tracker: EconomyTracker,
    economy_result: "EconomyResult",
    region_name: str,
    category: str,
    region_map: dict,
) -> str | None:
    """Find upstream civ if shock is import-driven.

    Returns the controller of the first inbound source region when imports
    have dropped by SHOCK_DELTA_THRESHOLD or more relative to the EMA.
    Source stockpile state is checked only to prefer regions that have also
    experienced a stockpile decline; any inbound source qualifies as fallback.
    """
    current_imports = economy_result.imports_by_region.get(region_name, {}).get(category, 0.0)
    avg_imports = economy_tracker.import_avg.get(region_name, {}).get(category, current_imports)

    if avg_imports <= 0 or current_imports / avg_imports > (1.0 - SHOCK_DELTA_THRESHOLD):
        return None

    # Prefer a source whose own stockpile also dropped (supply disruption signal)
    for source_name in economy_result.inbound_sources.get(region_name, []):
        source_stockpile = economy_result.stockpile_levels.get(source_name, {}).get(category, 0.0)
        source_avg = economy_tracker.trailing_avg.get(source_name, {}).get(category, source_stockpile)
        if source_avg > 0 and source_stockpile / source_avg < (1.0 - SHOCK_DELTA_THRESHOLD):
            source_region = region_map.get(source_name)
            if source_region and source_region.controller:
                return source_region.controller

    return None  # imports dropped but no upstream stockpile crash — likely embargo


def detect_supply_shocks(
    world,
    stockpiles: dict,
    economy_tracker: EconomyTracker,
    economy_result: "EconomyResult",
    region_map: dict,
) -> list:
    """Detect supply shocks: delta trigger + absolute severity gate."""
    from chronicler.models import Event

    shocks = []
    for name, sp in stockpiles.items():
        region = region_map.get(name)
        if region is None or region.controller is None:
            continue
        owner_civ_name = region.controller
        for cat, goods in CATEGORY_GOODS.items():
            current = sum(sp.goods.get(g, 0.0) for g in goods)
            avg = economy_tracker.trailing_avg.get(name, {}).get(cat, current)
            if avg <= 0 or current / avg >= (1.0 - SHOCK_DELTA_THRESHOLD):
                continue
            if cat == "food":
                food_suff = economy_result.food_sufficiency.get(name, 1.0)
                if food_suff >= SHOCK_SEVERITY_FLOOR:
                    continue
                severity = 1.0 - (food_suff / SHOCK_SEVERITY_FLOOR)
            else:
                severity = min(1.0 - (current / max(avg, 0.1)), 1.0)

            upstream = classify_upstream_source(
                world, economy_tracker, economy_result, name, cat, region_map,
            )
            actors = [owner_civ_name]
            if upstream:
                actors.append(upstream)
            shocks.append(Event(
                turn=world.turn,
                event_type="supply_shock",
                actors=actors,
                description=f"Supply shock: {cat} in {name}",
                consequences=[],
                importance=5 + int(severity * 4),
                source="economy",
                shock_region=name,
                shock_category=cat,
            ))
    return shocks


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
) -> float:
    """Add (production - exports + imports) to stockpile per good. Mutates in place.

    Returns total clamp floor loss (goods lost to non-negative clamping).
    """
    clamp_floor_loss = 0.0
    all_keys = set(goods.keys()) | set(production.keys()) | set(exports.keys()) | set(imports.keys())
    for good in all_keys:
        current = goods.get(good, 0.0)
        produced = production.get(good, 0.0)
        exported = exports.get(good, 0.0)
        imported = imports.get(good, 0.0)
        raw = current + (produced - exported) + imported
        if raw < 0.0:
            clamp_floor_loss += -raw
            goods[good] = 0.0
        else:
            goods[good] = raw
    return clamp_floor_loss


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
    if population <= 0:
        # Preserve stock in temporarily unpopulated regions; cap resumes on recolonization.
        return 0.0

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
    friction_multiplier: float = 1.0,
) -> float:
    """Per-route transport cost. Subtracted from raw margin for effective margin.

    Args:
        terrain_a: Terrain type of origin region.
        terrain_b: Terrain type of destination region.
        is_river: Both regions on same river path.
        is_coastal: Both regions are coast terrain.
        is_winter: Current season is winter.
        friction_multiplier: M47 K_TRADE_FRICTION scaling (default 1.0).
    """
    terrain_factor = max(TERRAIN_COST.get(terrain_a, 1.0), TERRAIN_COST.get(terrain_b, 1.0))
    river = RIVER_DISCOUNT if is_river else 1.0
    coastal = COASTAL_DISCOUNT if is_coastal else 1.0
    seasonal = WINTER_MODIFIER if is_winter else 1.0
    infra = INFRASTRUCTURE_DISCOUNT
    return TRANSPORT_COST_BASE * terrain_factor * infra * min(river, coastal) * seasonal * friction_multiplier


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
    # M43a: Conservation law tracking (H-3: includes treasury flows)
    conservation: dict[str, float] = field(default_factory=lambda: {
        "production": 0.0, "transit_loss": 0.0, "consumption": 0.0,
        "storage_loss": 0.0, "cap_overflow": 0.0, "clamp_floor_loss": 0.0,
        "in_transit_delta": 0.0,
        "treasury_tax": 0.0, "treasury_tithe": 0.0,
    })
    # M43b: Supply shock detection and trade dependency
    imports_by_region: dict[str, dict[str, float]] = field(default_factory=dict)
    inbound_sources: dict[str, list[str]] = field(default_factory=dict)
    stockpile_levels: dict[str, dict[str, float]] = field(default_factory=dict)
    import_share: dict[str, float] = field(default_factory=dict)
    trade_dependent: dict[str, bool] = field(default_factory=dict)
    # M58b: Oracle shadow imports (from observability batch oracle columns)
    oracle_imports: dict[str, dict[str, float]] = field(default_factory=dict)


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
    """Decompose a civ-level trade route into region-level boundary pairs.

    H-5 Design note: This intentionally filters to adjacent-only pairs.
    Non-adjacent routes (NAVIGATION/RAILWAYS/federation) exist at the civ
    level for treasury income and diplomatic weight, but do NOT participate
    in the goods economy. Goods flow requires physical adjacency for
    transport cost computation and transit decay. The treasury-only benefit
    for non-adjacent routes is bounded by TAX_RATE (0.05) applied to
    merchant wealth, which is itself derived from adjacent-goods-flow
    arbitrage. This means non-adjacent routes provide diplomatic/prestige
    value but cannot create unbounded treasury without adjacent trade.
    """
    pairs: list[tuple[str, str]] = []
    for region_name in civ_a_regions:
        region = region_map[region_name]
        for neighbor_name in region.adjacencies:
            if neighbor_name in civ_b_regions:
                pairs.append((region_name, neighbor_name))
    return pairs


def filter_goods_trade_routes(
    world,
    active_trade_routes: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Keep only civ-level routes that have at least one adjacent region boundary.

    Some systems model longer-range connectivity (navigation, railways,
    federations), but the goods economy and treasury trade income must stay
    aligned with boundary-pair goods flow.
    """
    if not active_trade_routes:
        return []

    region_map = get_region_map(world)
    civ_lookup: dict[str, set[str]] = {}
    for civ in world.civilizations:
        if len(civ.regions) > 0:
            civ_lookup[civ.name] = set(civ.regions)

    filtered: list[tuple[str, str]] = []
    for civ_a_name, civ_b_name in active_trade_routes:
        a_regions = civ_lookup.get(civ_a_name)
        b_regions = civ_lookup.get(civ_b_name)
        if not a_regions or not b_regions:
            continue
        if (
            decompose_trade_routes(a_regions, b_regions, region_map)
            or decompose_trade_routes(b_regions, a_regions, region_map)
        ):
            filtered.append((civ_a_name, civ_b_name))
    return filtered


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
    farmer_count: int = -1,
) -> float:
    """Derive farmer_income_modifier from post-trade price ratio.

    H-4: When farmer_count is 0, return neutral 1.0 — no farmers means the
    signal is meaningless; the previous code would compute amplified values
    from zero-production supply floors.
    """
    if farmer_count == 0:
        return 1.0
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
# M54b: Dedicated economy FFI batch builders
# ---------------------------------------------------------------------------

def build_economy_region_input_batch(world) -> "pa.RecordBatch":
    """Pack world-state inputs for the Rust economy kernel.

    One row per region. Columns: region_id, terrain, storage_population,
    resource_type_0, resource_effective_yield_0, stockpile_<good> x8.
    Does NOT include agent counts — Rust derives those from the live pool.
    """
    import pyarrow as pa
    from chronicler.ffi_constants import TERRAIN_MAP

    regions = world.regions
    data = {
        "region_id": pa.array(range(len(regions)), type=pa.uint16()),
        "terrain": pa.array([TERRAIN_MAP[r.terrain] for r in regions], type=pa.uint8()),
        "storage_population": pa.array([r.population for r in regions], type=pa.uint16()),
        "resource_type_0": pa.array([r.resource_types[0] for r in regions], type=pa.uint8()),
        "resource_effective_yield_0": pa.array(
            [r.resource_effective_yields[0] for r in regions], type=pa.float32(),
        ),
    }
    for good in FIXED_GOODS:
        data[f"stockpile_{good}"] = pa.array(
            [r.stockpile.goods.get(good, 0.0) for r in regions], type=pa.float32(),
        )
    return pa.record_batch(data)


def build_economy_trade_route_batch(world, active_trade_routes=None) -> "pa.RecordBatch":
    """Pack decomposed boundary-pair trade routes for the Rust economy kernel.

    Rows are stable-sorted by (origin_region_id, dest_region_id).
    Columns: origin_region_id, dest_region_id, is_river.
    """
    import pyarrow as pa

    if active_trade_routes is None:
        from chronicler.resources import get_active_trade_routes
        active_trade_routes = get_active_trade_routes(world)
    active_trade_routes = filter_goods_trade_routes(world, active_trade_routes)

    region_map = get_region_map(world)
    region_idx_map = {r.name: i for i, r in enumerate(world.regions)}
    river_pairs = build_river_route_set(world.rivers) if hasattr(world, "rivers") and world.rivers else set()

    civ_lookup: dict[str, set[str]] = {}
    for civ in world.civilizations:
        if len(civ.regions) > 0:
            civ_lookup[civ.name] = set(civ.regions)

    pairs: list[tuple[str, str]] = []
    for civ_a_name, civ_b_name in active_trade_routes:
        if civ_a_name not in civ_lookup or civ_b_name not in civ_lookup:
            continue
        a_regions = civ_lookup[civ_a_name]
        b_regions = civ_lookup[civ_b_name]
        for src_regions, dst_regions in [(a_regions, b_regions), (b_regions, a_regions)]:
            pairs.extend(decompose_trade_routes(src_regions, dst_regions, region_map))

    # Stable sort by (origin_region_id, dest_region_id)
    pairs.sort(key=lambda p: (region_idx_map[p[0]], region_idx_map[p[1]]))

    origin_ids = []
    dest_ids = []
    is_river_flags = []
    for origin, dest in pairs:
        origin_ids.append(region_idx_map[origin])
        dest_ids.append(region_idx_map[dest])
        is_river_flags.append(frozenset({origin, dest}) in river_pairs)

    return pa.record_batch({
        "origin_region_id": pa.array(origin_ids, type=pa.uint16()),
        "dest_region_id": pa.array(dest_ids, type=pa.uint16()),
        "is_river": pa.array(is_river_flags, type=pa.bool_()),
    })


# ---------------------------------------------------------------------------
# M58a: Merchant route graph — edge-list batch for Rust pathfinding
# ---------------------------------------------------------------------------

# Disposition ordering for trade permission checks.
_DISP_NUMERIC: dict[str, int] = {
    "hostile": 0, "suspicious": 1, "neutral": 2, "friendly": 3, "allied": 4,
}


def _regions_share_river(r1, r2) -> bool:
    """Check if two regions share a river connection.

    river_mask is a per-river bitmask: bit ``river_idx`` is set for every
    region along that river's path.  Two adjacent regions share a river iff
    their masks have at least one common bit (i.e. they both lie on the same
    river).
    """
    return bool(r1.river_mask & r2.river_mask)


def _transport_cost(r1, r2, is_winter: bool) -> float:
    """Compute directed transport cost from *r1* to *r2*.

    Keep merchant-route graph costs aligned with the Python goods economy's
    canonical transport-cost formula.
    """
    return compute_transport_cost(
        r1.terrain,
        r2.terrain,
        is_river=_regions_share_river(r1, r2),
        is_coastal=(r1.terrain == "coast" and r2.terrain == "coast"),
        is_winter=is_winter,
    )


def build_merchant_route_graph(world) -> "pa.RecordBatch":
    """Build a directed edge-list batch for Rust merchant pathfinding.

    Edges are region adjacency pairs filtered by diplomatic permissions:
    - Intra-civ edges always allowed.
    - Cross-civ edges gated by: neutral+ disposition (both sides),
      no active war, no embargo, no route_suspensions.
    - Uncontrolled regions are not traversable.

    Returns a RecordBatch with columns:
    ``from_region`` (uint16), ``to_region`` (uint16),
    ``is_river`` (bool), ``transport_cost`` (float32).
    """
    import pyarrow as pa
    from chronicler.resources import get_season_id

    regions = world.regions
    region_idx = {r.name: i for i, r in enumerate(regions)}
    is_winter = get_season_id(world.turn) == 3

    # Pre-build lookup sets for O(1) gating checks.
    war_set: set[frozenset[str]] = set()
    for a, b in world.active_wars:
        war_set.add(frozenset({a, b}))

    embargo_set: set[frozenset[str]] = set()
    for a, b in world.embargoes:
        embargo_set.add(frozenset({a, b}))

    from_ids: list[int] = []
    to_ids: list[int] = []
    is_river_flags: list[bool] = []
    transport_costs: list[float] = []

    for r1 in regions:
        if r1.controller is None:
            continue
        for adj_name in r1.adjacencies:
            adj_idx = region_idx.get(adj_name)
            if adj_idx is None:
                continue
            r2 = regions[adj_idx]
            if r2.controller is None:
                continue

            # Route suspensions are region-scoped on the "trade_route" key.
            # If either endpoint has an active trade-route suspension, block the edge.
            if (
                r1.route_suspensions.get("trade_route", 0) > 0
                or r2.route_suspensions.get("trade_route", 0) > 0
            ):
                continue

            # Intra-civ: allowed unless blocked by endpoint suspensions above.
            if r1.controller != r2.controller:
                # Cross-civ gating: war check
                civ_pair = frozenset({r1.controller, r2.controller})
                if civ_pair in war_set:
                    continue
                # Embargo check
                if civ_pair in embargo_set:
                    continue
                # Disposition check: both sides must be >= neutral (2)
                rel_ab = world.relationships.get(r1.controller, {}).get(r2.controller)
                rel_ba = world.relationships.get(r2.controller, {}).get(r1.controller)
                if rel_ab is None or rel_ba is None:
                    continue
                if _DISP_NUMERIC.get(rel_ab.disposition.value, 0) < 2:
                    continue
                if _DISP_NUMERIC.get(rel_ba.disposition.value, 0) < 2:
                    continue

            from_ids.append(region_idx[r1.name])
            to_ids.append(region_idx[r2.name])
            is_river_flags.append(_regions_share_river(r1, r2))
            transport_costs.append(_transport_cost(r1, r2, is_winter))

    return pa.record_batch({
        "from_region": pa.array(from_ids, type=pa.uint16()),
        "to_region": pa.array(to_ids, type=pa.uint16()),
        "is_river": pa.array(is_river_flags, type=pa.bool_()),
        "transport_cost": pa.array(transport_costs, type=pa.float32()),
    })


def reconstruct_economy_result(
    region_result_batch,
    civ_result_batch,
    observability_batch,
    upstream_sources_batch,
    conservation_batch,
    world,
    require_oracle_shadow: bool = False,
) -> EconomyResult:
    """Reconstruct a Python EconomyResult from five Rust return batches.

    Produces the same field shapes as compute_economy() so that downstream
    consumers (agent_bridge, action_engine, tick_factions, EconomyTracker,
    detect_supply_shocks) need no contract changes.
    """
    result = EconomyResult()
    region_names = [r.name for r in world.regions]
    n_regions = len(region_names)

    # In hybrid mode (M58b), oracle shadow columns are required for convergence
    # diagnostics. Fail fast on schema mismatch instead of silently zero-filling.
    if require_oracle_shadow:
        obs_cols = set(observability_batch.schema.names)
        required_oracle_cols = {
            "oracle_imports_food",
            "oracle_imports_raw_material",
            "oracle_imports_luxury",
            "oracle_margin",
            "oracle_food_sufficiency",
        }
        missing = sorted(required_oracle_cols - obs_cols)
        if missing:
            raise ValueError(
                "Hybrid economy missing required oracle observability columns: "
                f"{missing}. This usually indicates a stale chronicler-agents extension "
                "binary that does not match the current Rust schema."
            )

    # --- Region result batch → stockpile write-back + signals ---
    rr_ids = region_result_batch.column("region_id").to_pylist()
    for col_good in FIXED_GOODS:
        vals = region_result_batch.column(f"stockpile_{col_good}").to_pylist()
        for i, rid in enumerate(rr_ids):
            rname = region_names[rid]
            world.regions[rid].stockpile.goods[col_good] = vals[i]

    for signal in ("farmer_income_modifier", "food_sufficiency", "merchant_margin", "merchant_trade_income"):
        vals = region_result_batch.column(signal).to_pylist()
        target = {
            "farmer_income_modifier": result.farmer_income_modifiers,
            "food_sufficiency": result.food_sufficiency,
            "merchant_margin": result.merchant_margins,
            "merchant_trade_income": result.merchant_trade_incomes,
        }[signal]
        for i, rid in enumerate(rr_ids):
            target[region_names[rid]] = vals[i]

    trc_vals = region_result_batch.column("trade_route_count").to_pylist()
    for i, rid in enumerate(rr_ids):
        result.trade_route_counts[region_names[rid]] = trc_vals[i]

    # --- Civ result batch → fiscal outputs ---
    cr_ids = civ_result_batch.column("civ_id").to_pylist()
    for field_name, target in [
        ("treasury_tax", result.treasury_tax),
        ("tithe_base", result.tithe_base),
        ("priest_tithe_share", result.priest_tithe_shares),
    ]:
        vals = civ_result_batch.column(field_name).to_pylist()
        for i, cid in enumerate(cr_ids):
            target[cid] = vals[i]

    # --- Observability batch → imports, stockpile levels, trade dependency ---
    obs_ids = observability_batch.column("region_id").to_pylist()
    for i, rid in enumerate(obs_ids):
        rname = region_names[rid]
        result.imports_by_region[rname] = {
            cat: observability_batch.column(f"imports_{cat}").to_pylist()[i]
            for cat in CATEGORIES
        }
        result.stockpile_levels[rname] = {
            cat: observability_batch.column(f"stockpile_{cat}").to_pylist()[i]
            for cat in CATEGORIES
        }
        result.import_share[rname] = observability_batch.column("import_share").to_pylist()[i]
        result.trade_dependent[rname] = bool(observability_batch.column("trade_dependent").to_pylist()[i])

    # --- Upstream sources batch → inbound_sources ---
    if upstream_sources_batch.num_rows > 0:
        dest_ids = upstream_sources_batch.column("dest_region_id").to_pylist()
        ordinals = upstream_sources_batch.column("source_ordinal").to_pylist()
        source_ids = upstream_sources_batch.column("source_region_id").to_pylist()
        # Group by dest, sort by ordinal, map ids to names
        from collections import defaultdict
        grouped: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for dest_id, ordinal, source_id in zip(dest_ids, ordinals, source_ids):
            grouped[dest_id].append((ordinal, source_id))
        for dest_id, entries in grouped.items():
            entries.sort(key=lambda x: x[0])
            result.inbound_sources[region_names[dest_id]] = [
                region_names[src_id] for _, src_id in entries
            ]

    # --- Conservation batch ---
    for field_name in ("production", "transit_loss", "consumption", "storage_loss", "cap_overflow", "clamp_floor_loss"):
        result.conservation[field_name] = conservation_batch.column(field_name).to_pylist()[0]
    # M58b: in_transit_delta (nullable, absent in pre-M58b batches)
    if "in_transit_delta" in conservation_batch.schema.names:
        result.conservation["in_transit_delta"] = conservation_batch.column("in_transit_delta").to_pylist()[0]

    # --- M58b: Oracle shadow imports (nullable columns, zero when no oracle) ---
    if "oracle_imports_food" in observability_batch.schema.names:
        obs_ids = observability_batch.column("region_id").to_pylist()
        oracle_food = observability_batch.column("oracle_imports_food").to_pylist()
        oracle_rm = observability_batch.column("oracle_imports_raw_material").to_pylist()
        oracle_lux = observability_batch.column("oracle_imports_luxury").to_pylist()
        for i, rid in enumerate(obs_ids):
            rname = region_names[rid]
            result.oracle_imports[rname] = {
                "food": oracle_food[i],
                "raw_material": oracle_rm[i],
                "luxury": oracle_lux[i],
            }

    # --- M58b: Oracle shadow margins and food sufficiency ---
    if "oracle_margin" in observability_batch.schema.names:
        obs_ids = observability_batch.column("region_id").to_pylist()
        oracle_margins = observability_batch.column("oracle_margin").to_pylist()
        oracle_food_suff = observability_batch.column("oracle_food_sufficiency").to_pylist()
        for i, rid in enumerate(obs_ids):
            rname = region_names[rid]
            if rname not in result.oracle_imports:
                result.oracle_imports[rname] = {}
            result.oracle_imports[rname]["margin"] = oracle_margins[i]
            result.oracle_imports[rname]["food_sufficiency"] = oracle_food_suff[i]

    return result


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
    active_trade_routes = filter_goods_trade_routes(world, active_trade_routes)

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

    # --- Step 2c: Pre-trade prices (initial from local production only) ---
    pre_trade_prices: dict[str, dict[str, float]] = {}
    for rname in region_production:
        pre_trade_prices[rname] = compute_prices(region_production[rname], region_demand[rname])

    # --- Step 2d: Exportable surplus (constant across tatonnement passes) ---
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
            from chronicler.tuning import get_multiplier, K_TRADE_FRICTION
            route_transport_costs[route] = compute_transport_cost(
                origin_region.terrain, dest_region.terrain,
                is_river=is_river, is_coastal=is_coastal, is_winter=is_winter,
                friction_multiplier=get_multiplier(world, K_TRADE_FRICTION),
            )

    # --- M47: Tatonnement price iteration ---
    TATONNEMENT_MAX_PASSES = 3
    TATONNEMENT_DAMPING = 0.2
    TATONNEMENT_CONVERGENCE = 0.01
    TATONNEMENT_PRICE_CLAMP = (0.5, 2.0)

    region_imports: dict[str, dict[str, float]] = {rname: _empty_category_dict() for rname in region_production}
    region_exports: dict[str, dict[str, float]] = {rname: _empty_category_dict() for rname in region_production}
    all_route_flows: dict[str, dict[tuple[str, str], dict[str, float]]] = {}

    for _pass in range(TATONNEMENT_MAX_PASSES):
        prev_prices = {rn: dict(p) for rn, p in pre_trade_prices.items()}

        # Re-zero accumulators
        region_imports = {rname: _empty_category_dict() for rname in region_production}
        region_exports = {rname: _empty_category_dict() for rname in region_production}
        all_route_flows = {}

        # Trade allocation with current prices
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

        # Recompute prices from production + imports with damping
        for rname in region_production:
            supply = {
                cat: region_production[rname][cat] + region_imports.get(rname, _empty_category_dict())[cat]
                for cat in CATEGORIES
            }
            new_prices = compute_prices(supply, region_demand[rname])
            for cat in CATEGORIES:
                old_p = prev_prices.get(rname, {}).get(cat, 1.0)
                if old_p < 0.001:
                    pre_trade_prices[rname][cat] = new_prices[cat]
                    continue
                ratio = new_prices[cat] / old_p
                clamped = max(TATONNEMENT_PRICE_CLAMP[0], min(ratio, TATONNEMENT_PRICE_CLAMP[1]))
                pre_trade_prices[rname][cat] = old_p * (1.0 + TATONNEMENT_DAMPING * (clamped - 1.0))

        # Convergence check
        max_delta = 0.0
        for rname in region_production:
            for cat in CATEGORIES:
                delta = abs(pre_trade_prices[rname].get(cat, 0) - prev_prices.get(rname, {}).get(cat, 0))
                if delta > max_delta:
                    max_delta = delta
        if max_delta < TATONNEMENT_CONVERGENCE:
            break

    # Track inbound sources after final pass
    for origin_name, flow in all_route_flows.items():
        for route, cat_flows in flow.items():
            _, dest = route
            for cat in CATEGORIES:
                amount = cat_flows[cat]
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
        clamp_loss = accumulate_stockpile(
            region.stockpile.goods,
            production=region_per_good_production.get(rname, {}),
            exports=region_per_good_exports.get(rname, {}),
            imports=region_per_good_imports.get(rname, {}),
        )
        result.conservation["clamp_floor_loss"] += clamp_loss

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
            farmer_count=agent_data.get("farmer_count", 0),
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

        for civ_name, (civ_idx, civ_regions) in civ_lookup.items():
            merchant_wealth = _extract_civ_merchant_wealth(
                snap_civ_affinity, snap_occupations, snap_wealth, civ_idx,
            )
            priest_count = _extract_civ_priest_count(
                snap_civ_affinity, snap_occupations, civ_idx,
            )
            result.treasury_tax[civ_idx] = TAX_RATE * merchant_wealth

            # H-2: Gate tithe on food sufficiency — reduce/skip when food is scarce
            avg_food_suff = 1.0
            if civ_regions:
                suff_values = [result.food_sufficiency.get(rn, 1.0) for rn in civ_regions]
                avg_food_suff = sum(suff_values) / len(suff_values)
            TITHE_FOOD_GATE = 0.5
            tithe_scale = min(avg_food_suff / TITHE_FOOD_GATE, 1.0) if avg_food_suff < TITHE_FOOD_GATE else 1.0
            scaled_tithe_base = merchant_wealth * tithe_scale

            result.tithe_base[civ_idx] = scaled_tithe_base
            result.priest_tithe_shares[civ_idx] = (
                TITHE_RATE * scaled_tithe_base / max(priest_count, 1)
            )

            # H-3: Track treasury flows in conservation
            result.conservation["treasury_tax"] += result.treasury_tax[civ_idx]
            result.conservation["treasury_tithe"] += TITHE_RATE * scaled_tithe_base

    return result
