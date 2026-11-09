"""Python economy oracle. Not called by the simulation; the Rust `tick_economy` is authoritative.

``compute_economy`` and its oracle-only helpers live here (CON-7). The tests
compare them with the native economy; no production module calls them.
``chronicler.economy`` keeps the constants, the production-side helpers, the
FFI batch builders and ``EconomyResult``, and resolves the names moved here
lazily so older ``from chronicler.economy import compute_economy`` imports
keep working.

Names that stay in ``chronicler.economy`` are read through the module
(``_eco.NAME``) at call time, so a test that patches one there still reaches
the oracle, as it did before the move.
"""

from __future__ import annotations

import math

import numpy as np

from chronicler import economy as _eco
# Oracle-only names that still live in economy.py; they are re-exported here.
from chronicler.economy import compute_production, derive_farmer_income_modifier

__all__ = [
    "accumulate_stockpile",
    "allocate_trade_flow",
    "apply_stockpile_cap",
    "apply_storage_decay",
    "apply_transit_decay",
    "compute_demand",
    "compute_economy",
    "compute_prices",
    "compute_production",
    "consume_from_stockpile",
    "derive_farmer_income_modifier",
    "derive_food_sufficiency_from_stockpile",
    "derive_merchant_margin",
    "derive_merchant_trade_income",
]


# ---------------------------------------------------------------------------
# M43a: Perishability — transit decay
# ---------------------------------------------------------------------------

def apply_transit_decay(shipped: float, good: str) -> float:
    """Apply per-good transit decay to shipped volume. Returns delivered amount."""
    rate = _eco.TRANSIT_DECAY.get(good, 0.0)
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
    total_food = sum(goods.get(g, 0.0) for g in _eco.FOOD_GOODS if g != "salt")
    salt_amount = goods.get("salt", 0.0)
    salt_ratio = salt_amount / max(total_food, 0.1)
    preservation = min(salt_ratio * _eco.SALT_PRESERVATION_FACTOR, _eco.MAX_PRESERVATION)

    total_loss = 0.0
    for good in list(goods.keys()):
        if good == "salt":
            continue
        rate = _eco.STORAGE_DECAY.get(good, 0.0)
        if rate <= 0.0:
            continue
        if good in _eco.FOOD_GOODS:
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

    Returns the inventory deficit covered by non-negative clamping.
    This diagnostic is an artificial source, not a physical loss; valid bounded
    exports keep it zero. The legacy field name is retained for compatibility.
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
    total_food = sum(goods.get(g, 0.0) for g in _eco.FOOD_GOODS)
    d = max(food_demand, _eco._SUPPLY_FLOOR)
    return max(0.0, min(total_food / d, 2.0))


def consume_from_stockpile(
    goods: dict[str, float],
    food_demand: float,
) -> float:
    """Draw food demand from stockpile proportional to composition. Mutates in place.

    Clamped: consumption per good can't exceed available stockpile.
    Returns total consumed (for conservation law verification).
    """
    total_food = sum(goods.get(g, 0.0) for g in _eco.FOOD_GOODS)
    if total_food <= 0.0 or food_demand <= 0.0:
        return 0.0
    total_consumed = 0.0
    for good in _eco.FOOD_GOODS:
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

    cap = _eco.PER_GOOD_CAP_FACTOR * population
    total_overflow = 0.0
    for good in list(goods.keys()):
        if goods[good] > cap:
            total_overflow += goods[good] - cap
            goods[good] = cap
    return total_overflow


# ---------------------------------------------------------------------------
# Category totals and demand
# ---------------------------------------------------------------------------

def _category_totals(goods: dict[str, float]) -> dict[str, float]:
    return {cat: sum(goods.get(good, 0.0) for good in _eco.FIXED_GOODS
                     if good in _eco.CATEGORY_GOODS[cat]) for cat in _eco.CATEGORIES}


def _decompose_category_flow(
    flow: dict[str, float], available_goods: dict[str, float],
) -> dict[str, float]:
    """Draw category exports proportionally from the origin's available goods."""
    totals = _category_totals(available_goods)
    return {
        good: flow[cat] * available_goods.get(good, 0.0) / totals[cat]
        for cat in _eco.CATEGORIES if totals[cat] > 0.0
        for good in _eco.FIXED_GOODS if good in _eco.CATEGORY_GOODS[cat]
    }


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
        "food": population * _eco.PER_CAPITA_FOOD,
        "raw_material": soldier_count * _eco.RAW_MATERIAL_PER_SOLDIER,
        "luxury": wealthy_count * _eco.LUXURY_PER_WEALTHY_AGENT,
        # Wares: the cities' input (``cities.economy_columns``), not modelled
        # by this oracle.
        "craft": 0.0,
    }


# ---------------------------------------------------------------------------
# Task 5: Price computation
# ---------------------------------------------------------------------------

def compute_prices(
    supply: dict[str, float],
    demand: dict[str, float],
) -> dict[str, float]:
    """Compute price per category from supply/demand ratio.

    price = BASE_PRICE × (demand / max(supply, 0.1))
    """
    prices: dict[str, float] = {}
    for cat in _eco.CATEGORIES:
        d = demand.get(cat, 0.0)
        s = max(supply.get(cat, 0.0), _eco._SUPPLY_FLOOR)
        prices[cat] = _eco.BASE_PRICE * (d / s)
    return prices


# ---------------------------------------------------------------------------
# Tasks 6-7: Trade flow allocation
# ---------------------------------------------------------------------------

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
    capacity = merchant_count * _eco.CARRY_PER_MERCHANT
    if capacity <= 0 or not outbound_routes:
        return {route: _eco._empty_category_dict() for route in outbound_routes}

    cat_weights: dict[str, float] = {}
    route_margins: dict[str, dict[tuple[str, str], float]] = {
        cat: {} for cat in _eco.CATEGORIES
    }

    for cat in _eco.CATEGORIES:
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
        return {route: _eco._empty_category_dict() for route in outbound_routes}

    cat_budgets: dict[str, float] = {}
    for cat in _eco.CATEGORIES:
        cat_budgets[cat] = (cat_weights[cat] / total_weight) * capacity

    flow: dict[tuple[str, str], dict[str, float]] = {
        route: _eco._empty_category_dict() for route in outbound_routes
    }

    for cat in _eco.CATEGORIES:
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

def derive_merchant_margin(total_raw_margin: float, route_count: int) -> float:
    """Derive merchant_margin. Normalized to [0.0, 1.0]."""
    if route_count <= 0:
        return 0.0
    avg = total_raw_margin / route_count
    return max(0.0, min(avg / _eco.MERCHANT_MARGIN_NORMALIZER, 1.0))


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
        "wealthy_count": int((w > _eco.LUXURY_DEMAND_THRESHOLD).sum()),
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
) -> _eco.EconomyResult:
    """Phase 2 goods sub-sequence: production -> demand -> prices -> trade -> signals.

    Prices use accessible inventory before consumption: starting stocks plus
    current harvest, minus exports, plus delivered imports (after transit decay).
    Callers prepare resource_current_yields using the read-only ecology preview.
    """
    if active_trade_routes is None:
        from chronicler.resources import get_active_trade_routes
        active_trade_routes = get_active_trade_routes(world)
    active_trade_routes = _eco.filter_goods_trade_routes(world, active_trade_routes)

    result = _eco.EconomyResult()
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
    river_pairs = _eco.build_river_route_set(world.rivers) if hasattr(world, 'rivers') and world.rivers else set()
    from chronicler.resources import get_season_id
    is_winter = get_season_id(world.turn) == 3

    # Extract snapshot arrays ONCE
    snap_regions = snapshot.column("region").to_numpy()
    snap_occupations = snapshot.column("occupation").to_numpy()
    snap_wealth = snapshot.column("wealth").to_numpy()
    snap_civ_affinity = snapshot.column("civ_affinity").to_numpy()

    # --- Step 2a: Production + Step 2b: Demand ---
    region_production: dict[str, dict[str, float]] = {}
    region_per_good_production: dict[str, dict[str, float]] = {}
    available_goods: dict[str, dict[str, float]] = {}
    available_supply: dict[str, dict[str, float]] = {}
    region_demand: dict[str, dict[str, float]] = {}
    region_agent_data: dict[str, dict] = {}

    for region in regions:
        rname = region.name
        ridx = region_idx_map[rname]
        agent_data = _extract_region_agent_counts_from_arrays(
            snap_regions, snap_occupations, snap_wealth, ridx,
        )
        region_agent_data[rname] = agent_data

        demand = compute_demand(
            agent_data["population"], agent_data["soldier_count"], agent_data["wealthy_count"],
        )
        slot_yields = [_eco.economy_yield(world, region, slot) for slot in range(3)]
        farmers = agent_data["farmer_count"]
        labor_ref, labor_half = _eco.farm_labor_curve(world, region)
        subsistence = _eco.region_subsistence_yield(world, region, slot_yields)
        slot_curves = _eco.slot_labor_curves(world, region) if labor_ref > 0.0 else None
        split = None
        if slot_curves is not None:
            *split, productivity = _eco.slot_curve_labor(
                region.resource_types, slot_yields, farmers, demand["food"], subsistence,
                (labor_ref, labor_half), slot_curves,
            )
            farm_labor = farmers
            if farmers > 0 and productivity != 1.0:
                result.farm_productivity[rname] = productivity
        else:
            farm_labor = _eco.effective_farm_labor(farmers, labor_ref, labor_half)
            if labor_ref > 0.0 and farmers > 0 and farm_labor != farmers:
                result.farm_productivity[rname] = farm_labor / farmers
        outputs: list[float] = []
        produced = _eco.compute_allocated_production(
            region.resource_types,
            slot_yields,
            farm_labor,
            production_caps=[_eco.catch_budget(world, region, slot) for slot in range(3)],
            food_demand=demand["food"],
            subsistence_yield=subsistence,
            slot_labor=tuple(split) if split is not None else None,
            slot_output=outputs,
        )
        result.slot_output[rname] = (outputs[0], outputs[1], outputs[2])
        result.forage_output[rname] = outputs[3]
        region_per_good_production[rname] = produced
        region_production[rname] = _category_totals(produced)
        result.conservation["production"] += sum(produced.values())
        available_goods[rname] = {
            good: region.stockpile.goods.get(good, 0.0) + produced.get(good, 0.0)
            for good in _eco.FIXED_GOODS
        }
        available_supply[rname] = _category_totals(available_goods[rname])
        region_demand[rname] = demand

    # --- Step 2c: Pre-trade prices (accessible stock plus current harvest) ---
    pre_trade_prices: dict[str, dict[str, float]] = {}
    for rname in region_production:
        pre_trade_prices[rname] = compute_prices(available_supply[rname], region_demand[rname])

    # --- Step 2d: Exportable surplus (constant across tatonnement passes) ---
    exportable_surplus: dict[str, dict[str, float]] = {}
    for rname in region_production:
        exportable_surplus[rname] = {
            cat: max(available_supply[rname][cat] - region_demand[rname][cat], 0.0)
            for cat in _eco.CATEGORIES
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
            pairs = _eco.decompose_trade_routes(src_regions, dst_regions, region_map)
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
            route_transport_costs[route] = _eco.compute_transport_cost(
                origin_region.terrain, dest_region.terrain,
                is_river=is_river, is_coastal=is_coastal, is_winter=is_winter,
                friction_multiplier=get_multiplier(world, K_TRADE_FRICTION),
            )

    # --- M47: Tatonnement price iteration ---
    TATONNEMENT_MAX_PASSES = 3
    TATONNEMENT_DAMPING = 0.2
    TATONNEMENT_CONVERGENCE = 0.01
    TATONNEMENT_PRICE_CLAMP = (0.5, 2.0)

    region_imports: dict[str, dict[str, float]] = {rname: _eco._empty_category_dict() for rname in region_production}
    region_exports: dict[str, dict[str, float]] = {rname: _eco._empty_category_dict() for rname in region_production}
    all_route_flows: dict[str, dict[tuple[str, str], dict[str, float]]] = {}

    for _pass in range(TATONNEMENT_MAX_PASSES):
        prev_prices = {rn: dict(p) for rn, p in pre_trade_prices.items()}

        # Re-zero accumulators
        region_imports = {rname: _eco._empty_category_dict() for rname in region_production}
        region_exports = {rname: _eco._empty_category_dict() for rname in region_production}
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
                routes, pre_trade_prices.get(origin_name, _eco._empty_category_dict()),
                dest_prices, exportable_surplus.get(origin_name, _eco._empty_category_dict()),
                merchant_count,
                transport_costs=route_transport_costs,
            )
            all_route_flows[origin_name] = flow

            for route, cat_flows in flow.items():
                _, dest = route
                for cat in _eco.CATEGORIES:
                    amount = cat_flows[cat]
                    region_exports[origin_name][cat] += amount
                    region_imports.setdefault(dest, _eco._empty_category_dict())
                shipped_goods = _decompose_category_flow(cat_flows, available_goods[origin_name])
                delivered = _category_totals({
                    good: apply_transit_decay(amount, good)
                    for good, amount in shipped_goods.items()
                })
                for cat in _eco.CATEGORIES:
                    region_imports[dest][cat] += delivered[cat]

        # Recompute accessible-inventory prices with damping
        for rname in region_production:
            supply = {
                cat: available_supply[rname][cat] - region_exports[rname][cat]
                     + region_imports.get(rname, _eco._empty_category_dict())[cat]
                for cat in _eco.CATEGORIES
            }
            new_prices = compute_prices(supply, region_demand[rname])
            for cat in _eco.CATEGORIES:
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
            for cat in _eco.CATEGORIES:
                delta = abs(pre_trade_prices[rname].get(cat, 0) - prev_prices.get(rname, {}).get(cat, 0))
                if delta > max_delta:
                    max_delta = delta
        if max_delta < TATONNEMENT_CONVERGENCE:
            break

    # Track inbound sources after final pass
    for origin_name, flow in all_route_flows.items():
        for route, cat_flows in flow.items():
            _, dest = route
            for cat in _eco.CATEGORIES:
                amount = cat_flows[cat]
                if amount > 0:
                    result.inbound_sources.setdefault(dest, [])
                    if origin_name not in result.inbound_sources[dest]:
                        result.inbound_sources[dest].append(origin_name)

    # Decompose final flows exactly as in allocation. Each origin exports only
    # from starting stocks + harvest; incoming goods cannot be re-exported in
    # the same tick. Transit losses are accounted once, on this final pass.
    region_per_good_imports = {rname: {} for rname in region_production}
    region_per_good_exports = {rname: {} for rname in region_production}
    for origin_name, route_flows in all_route_flows.items():
        for (_, dest_name), cat_flows in route_flows.items():
            shipped_goods = _decompose_category_flow(cat_flows, available_goods[origin_name])
            for good, shipped in shipped_goods.items():
                delivered = apply_transit_decay(shipped, good)
                result.conservation["transit_loss"] += shipped - delivered
                exports = region_per_good_exports[origin_name]
                exports[good] = exports.get(good, 0.0) + shipped
                imports = region_per_good_imports.setdefault(dest_name, {})
                imports[good] = imports.get(good, 0.0) + delivered

    # --- Step 2f: Post-trade prices ---
    post_trade_prices: dict[str, dict[str, float]] = {}
    for rname in region_production:
        post_trade_supply = {
            cat: available_supply[rname][cat] - region_exports[rname][cat] + region_imports[rname][cat]
            for cat in _eco.CATEGORIES
        }
        post_trade_prices[rname] = compute_prices(post_trade_supply, region_demand[rname])

    # --- M43a: Steps 2g-2l — Stockpile sub-sequence ---
    for region in regions:
        rname = region.name
        demand = region_demand.get(rname, _eco._empty_category_dict())

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
        result.imports_by_region[rname] = dict(region_imports.get(rname, _eco._empty_category_dict()))
        cat_stockpile = _eco._empty_category_dict()
        for good, amount in region.stockpile.goods.items():
            for cat, goods_set in _eco.CATEGORY_GOODS.items():
                if good in goods_set:
                    cat_stockpile[cat] += amount
                    break
        result.stockpile_levels[rname] = cat_stockpile
        food_demand = region_demand.get(rname, _eco._empty_category_dict()).get("food", 0.0)
        food_imports = region_imports.get(rname, _eco._empty_category_dict()).get("food", 0.0)
        share = food_imports / max(food_demand, 0.1)
        result.import_share[rname] = share
        result.trade_dependent[rname] = share > _eco.TRADE_DEPENDENCY_THRESHOLD

    # --- Signal derivation ---
    for region in regions:
        rname = region.name
        agent_data = region_agent_data.get(rname, {})
        post_prices = post_trade_prices.get(rname, _eco._empty_category_dict())
        demand = region_demand.get(rname, _eco._empty_category_dict())
        # All producing slots contribute to the farmer's sale-price signal.
        production = region_production[rname]
        total_production = sum(production.values())
        if agent_data.get("farmer_count", 0) == 0 or total_production <= 0.0:
            result.farmer_income_modifiers[rname] = 1.0
        else:
            price_ratio = sum(production[cat] * post_prices[cat] / _eco.BASE_PRICE
                              for cat in _eco.CATEGORIES) / total_production
            result.farmer_income_modifiers[rname] = max(
                _eco.FARMER_INCOME_MODIFIER_FLOOR, min(price_ratio, _eco.FARMER_INCOME_MODIFIER_CAP),
            )

        routes = origin_routes.get(rname, [])
        total_raw_margin = 0.0
        for route in routes:
            _, dest = route
            dest_post = post_trade_prices.get(dest, _eco._empty_category_dict())
            for cat in _eco.CATEGORIES:
                total_raw_margin += max(dest_post[cat] - post_prices[cat], 0.0)
        result.merchant_margins[rname] = derive_merchant_margin(total_raw_margin, len(routes))

        # merchant_trade_income: route_flow x post-trade margin (intentional mismatch)
        total_arbitrage = 0.0
        route_flows = all_route_flows.get(rname, {})
        for route, cat_flows in route_flows.items():
            _, dest = route
            dest_post = post_trade_prices.get(dest, _eco._empty_category_dict())
            for cat in _eco.CATEGORIES:
                margin = max(dest_post[cat] - post_prices[cat], 0.0)
                total_arbitrage += cat_flows[cat] * margin
        result.merchant_trade_incomes[rname] = derive_merchant_trade_income(
            total_arbitrage, agent_data.get("merchant_count", 0),
        )

        result.trade_route_counts[rname] = boundary_pair_counts.get(rname, 0)

        rg = _eco.RegionGoods(
            production=region_production.get(rname, _eco._empty_category_dict()),
            imports=region_imports.get(rname, _eco._empty_category_dict()),
            exports=region_exports.get(rname, _eco._empty_category_dict()),
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
            result.treasury_tax[civ_idx] = _eco.TAX_RATE * merchant_wealth

            # H-2: Gate tithe on food sufficiency — reduce/skip when food is scarce
            avg_food_suff = 1.0
            if civ_regions:
                suff_values = [result.food_sufficiency.get(rn, 1.0) for rn in civ_regions]
                avg_food_suff = sum(suff_values) / len(suff_values)
            tithe_scale = avg_food_suff / _eco.TITHE_FOOD_GATE if avg_food_suff < _eco.TITHE_FOOD_GATE else 1.0
            scaled_tithe_base = merchant_wealth * tithe_scale

            result.tithe_base[civ_idx] = scaled_tithe_base
            result.priest_tithe_shares[civ_idx] = (
                TITHE_RATE * scaled_tithe_base / max(priest_count, 1)
            )

            # H-3: Track treasury flows in conservation
            result.conservation["treasury_tax"] += result.treasury_tax[civ_idx]
            result.conservation["treasury_tithe"] += TITHE_RATE * scaled_tithe_base

    return result
