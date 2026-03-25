//! Pure Rust economy core — Phase 2 production, demand, tatonnement pricing,
//! trade allocation, transit decay, stockpile lifecycle, signal derivation,
//! observability, and conservation.  No PyO3 — FFI wrappers live in ffi.rs.

// ---------------------------------------------------------------------------
// Constants — fixed good slots
// ---------------------------------------------------------------------------

/// Number of fixed good slots in the stockpile array.
pub const NUM_GOODS: usize = 8;

/// Good slot indices.
pub const SLOT_GRAIN: usize = 0;
pub const SLOT_FISH: usize = 1;
pub const SLOT_SALT: usize = 2;
pub const SLOT_TIMBER: usize = 3;
pub const SLOT_ORE: usize = 4;
pub const SLOT_BOTANICALS: usize = 5;
pub const SLOT_PRECIOUS: usize = 6;
pub const SLOT_EXOTIC: usize = 7;

/// Category indices.
pub const CAT_FOOD: usize = 0;
pub const CAT_RAW_MATERIAL: usize = 1;
pub const CAT_LUXURY: usize = 2;
pub const NUM_CATEGORIES: usize = 3;

/// Good slot → category mapping.
const GOOD_CATEGORY: [usize; NUM_GOODS] = [
    CAT_FOOD,         // 0: grain
    CAT_FOOD,         // 1: fish
    CAT_FOOD,         // 2: salt
    CAT_RAW_MATERIAL, // 3: timber
    CAT_RAW_MATERIAL, // 4: ore
    CAT_FOOD,         // 5: botanicals
    CAT_LUXURY,       // 6: precious
    CAT_FOOD,         // 7: exotic
];

/// Resource type enum → good slot index.
const RT_TO_SLOT: [usize; NUM_GOODS] = [
    SLOT_GRAIN,      // RT 0 (GRAIN)
    SLOT_TIMBER,     // RT 1 (TIMBER)
    SLOT_BOTANICALS, // RT 2 (BOTANICALS)
    SLOT_FISH,       // RT 3 (FISH)
    SLOT_SALT,       // RT 4 (SALT)
    SLOT_ORE,        // RT 5 (ORE)
    SLOT_PRECIOUS,   // RT 6 (PRECIOUS)
    SLOT_EXOTIC,     // RT 7 (EXOTIC)
];

/// Whether a good slot is food.  food = {grain, fish, salt, botanicals, exotic}.
const IS_FOOD: [bool; NUM_GOODS] = [
    true,  // grain
    true,  // fish
    true,  // salt
    false, // timber
    false, // ore
    true,  // botanicals
    false, // precious
    true,  // exotic
];

/// Terrain cost for transport.  Indexed by terrain u8 encoding.
/// plains(0)=1.0, mountains(1)=2.0, coast(2)=0.6, forest(3)=1.3, desert(4)=1.5, tundra(5)=1.8
const TERRAIN_COST: [f32; 6] = [1.0, 2.0, 0.6, 1.3, 1.5, 1.8];

/// Per-good transit decay rate.
const TRANSIT_DECAY: [f32; NUM_GOODS] = [
    0.05, // grain
    0.08, // fish
    0.0,  // salt
    0.01, // timber
    0.0,  // ore
    0.04, // botanicals
    0.0,  // precious
    0.06, // exotic
];

/// Per-good storage decay rate.
const STORAGE_DECAY: [f32; NUM_GOODS] = [
    0.03,  // grain
    0.06,  // fish
    0.0,   // salt
    0.005, // timber
    0.0,   // ore
    0.02,  // botanicals
    0.0,   // precious
    0.04,  // exotic
];

/// Terrain encoding for coast (used for both_coastal check).
const TERRAIN_COAST: u8 = 2;

/// Transport cost constants.
const TRANSPORT_COST_BASE: f32 = 0.10;
const RIVER_DISCOUNT: f32 = 0.5;
const COASTAL_DISCOUNT: f32 = 0.6;
const WINTER_MODIFIER: f32 = 1.5;

/// Tithe rate from Python factions.py.
const TITHE_RATE: f32 = 0.10;

/// Supply floor for price computation (avoid division by zero).
const SUPPLY_FLOOR: f32 = 0.1;

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

/// Economy tuning knobs.  Constructed Python-side, passed to Rust once.
#[derive(Clone, Debug)]
pub struct EconomyConfig {
    pub base_price: f32,
    pub per_capita_food: f32,
    pub raw_material_per_soldier: f32,
    pub luxury_per_wealthy_agent: f32,
    pub luxury_demand_threshold: f32,
    pub carry_per_merchant: f32,
    pub farmer_income_modifier_floor: f32,
    pub farmer_income_modifier_cap: f32,
    pub merchant_margin_normalizer: f32,
    pub tax_rate: f32,
    pub trade_dependency_threshold: f32,
    pub per_good_cap_factor: f32,
    pub salt_preservation_factor: f32,
    pub max_preservation: f32,
    // Tatonnement
    pub tatonnement_max_passes: u32,
    pub tatonnement_damping: f32,
    pub tatonnement_convergence: f32,
    pub tatonnement_price_clamp_lo: f32,
    pub tatonnement_price_clamp_hi: f32,
}

impl Default for EconomyConfig {
    fn default() -> Self {
        Self {
            base_price: 1.0,
            per_capita_food: 0.5,
            raw_material_per_soldier: 0.3,
            luxury_per_wealthy_agent: 0.2,
            luxury_demand_threshold: 10.0,
            carry_per_merchant: 1.0,
            farmer_income_modifier_floor: 0.5,
            farmer_income_modifier_cap: 3.0,
            merchant_margin_normalizer: 5.0,
            tax_rate: 0.05,
            trade_dependency_threshold: 0.6,
            per_good_cap_factor: 5.0 * 0.5, // PER_GOOD_CAP_FACTOR = 5.0 * PER_CAPITA_FOOD
            salt_preservation_factor: 2.5,
            max_preservation: 0.5,
            tatonnement_max_passes: 3,
            tatonnement_damping: 0.2,
            tatonnement_convergence: 0.01,
            tatonnement_price_clamp_lo: 0.5,
            tatonnement_price_clamp_hi: 2.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Input structs
// ---------------------------------------------------------------------------

/// Input row per region from Python.
pub struct EconomyRegionInput {
    pub region_id: u16,
    pub terrain: u8,
    pub storage_population: u16,
    pub resource_type_0: u8,
    pub resource_effective_yield_0: f32,
    pub stockpile: [f32; NUM_GOODS],
}

/// Derived per-region agent counts (computed inside Rust from pool).
pub struct RegionAgentCounts {
    pub population: u32,
    pub farmer_count: u32,
    pub soldier_count: u32,
    pub merchant_count: u32,
    pub wealthy_count: u32,
}

/// Input row per trade route.
pub struct TradeRouteInput {
    pub origin_region_id: u16,
    pub dest_region_id: u16,
    pub is_river: bool,
}

// ---------------------------------------------------------------------------
// Output structs
// ---------------------------------------------------------------------------

/// Output row per region.
pub struct EconomyRegionResult {
    pub region_id: u16,
    pub stockpile: [f32; NUM_GOODS],
    pub farmer_income_modifier: f32,
    pub food_sufficiency: f32,
    pub merchant_margin: f32,
    pub merchant_trade_income: f32,
    pub trade_route_count: u16,
}

/// Output row per civ.
pub struct EconomyCivResult {
    pub civ_id: u16,
    pub treasury_tax: f32,
    pub tithe_base: f32,
    pub priest_tithe_share: f32,
}

/// Output row per region for observability.
pub struct EconomyObservability {
    pub region_id: u16,
    pub imports_food: f32,
    pub imports_raw_material: f32,
    pub imports_luxury: f32,
    pub stockpile_food: f32,
    pub stockpile_raw_material: f32,
    pub stockpile_luxury: f32,
    pub import_share: f32,
    pub trade_dependent: bool,
}

/// Flat upstream source row.
pub struct UpstreamSource {
    pub dest_region_id: u16,
    pub source_ordinal: u16,
    pub source_region_id: u16,
}

/// Conservation summary (single row).  Uses f64 for precision.
pub struct ConservationSummary {
    pub production: f64,
    pub transit_loss: f64,
    pub consumption: f64,
    pub storage_loss: f64,
    pub cap_overflow: f64,
    pub clamp_floor_loss: f64,
}

impl ConservationSummary {
    fn new() -> Self {
        Self {
            production: 0.0,
            transit_loss: 0.0,
            consumption: 0.0,
            storage_loss: 0.0,
            cap_overflow: 0.0,
            clamp_floor_loss: 0.0,
        }
    }
}

/// Full return from tick_economy_core.
pub struct EconomyOutput {
    pub region_results: Vec<EconomyRegionResult>,
    pub civ_results: Vec<EconomyCivResult>,
    pub observability: Vec<EconomyObservability>,
    pub upstream_sources: Vec<UpstreamSource>,
    pub conservation: ConservationSummary,
}

// ---------------------------------------------------------------------------
// Internal working structures
// ---------------------------------------------------------------------------

/// Per-region transient state during economy tick.
struct RegionWorkState {
    /// Per-category production [food, raw_material, luxury].
    production: [f32; NUM_CATEGORIES],
    /// Per-category demand.
    demand: [f32; NUM_CATEGORIES],
    /// Per-category prices (updated during tatonnement).
    prices: [f32; NUM_CATEGORIES],
    /// Per-category exportable surplus (constant across tatonnement).
    surplus: [f32; NUM_CATEGORIES],
    /// Per-category imports (updated each tatonnement pass).
    imports: [f32; NUM_CATEGORIES],
    /// Per-category exports (updated each tatonnement pass).
    exports: [f32; NUM_CATEGORIES],
    /// Per-good stockpile (mutable copy from input).
    stockpile: [f32; NUM_GOODS],
    /// Good slot of the region's primary resource (or NUM_GOODS if none).
    primary_good_slot: usize,
    /// Category of the region's primary resource.
    primary_category: usize,
}

/// Per-route working data for trade kernel.
struct RouteWork {
    origin_idx: usize,   // index into region_inputs/work arrays
    dest_idx: usize,     // index into region_inputs/work arrays
    transport_cost: f32,
    /// Per-category flow allocated in last tatonnement pass.
    flow: [f32; NUM_CATEGORIES],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Get terrain cost, defaulting to 1.0 for unknown terrain codes.
#[inline]
fn terrain_cost(terrain: u8) -> f32 {
    if (terrain as usize) < TERRAIN_COST.len() {
        TERRAIN_COST[terrain as usize]
    } else {
        1.0
    }
}

/// Map resource type to good slot index.  Returns NUM_GOODS for invalid/empty types.
#[inline]
fn rt_to_slot(rt: u8) -> usize {
    if (rt as usize) < RT_TO_SLOT.len() {
        RT_TO_SLOT[rt as usize]
    } else {
        NUM_GOODS
    }
}

/// Map good slot to category index.
#[inline]
fn slot_to_category(slot: usize) -> usize {
    if slot < NUM_GOODS {
        GOOD_CATEGORY[slot]
    } else {
        CAT_FOOD // fallback; shouldn't be reached with valid data
    }
}

/// Compute transport cost for a single route.
fn compute_transport_cost(
    terrain_a: u8,
    terrain_b: u8,
    is_river: bool,
    is_winter: bool,
    trade_friction: f32,
) -> f32 {
    let cost_a = terrain_cost(terrain_a);
    let cost_b = terrain_cost(terrain_b);
    let mut cost = TRANSPORT_COST_BASE * (cost_a + cost_b) / 2.0;
    if is_river {
        cost *= RIVER_DISCOUNT;
    }
    let both_coastal = terrain_a == TERRAIN_COAST && terrain_b == TERRAIN_COAST;
    if both_coastal {
        cost *= COASTAL_DISCOUNT;
    }
    if is_winter {
        cost *= WINTER_MODIFIER;
    }
    cost * trade_friction
}

// ---------------------------------------------------------------------------
// Core tick function
// ---------------------------------------------------------------------------

/// Execute one turn of the Phase 2 economy computation.
///
/// This is the sequential, deterministic economy kernel.  No rayon, no RNG.
/// Route order is stable: sorted by (origin_region_id, dest_region_id).
pub fn tick_economy_core(
    region_inputs: &[EconomyRegionInput],
    agent_counts: &[RegionAgentCounts],
    routes: &[TradeRouteInput],
    civ_merchant_wealth: &[f32],
    civ_priest_count: &[u32],
    n_civs: usize,
    config: &EconomyConfig,
    trade_friction: f32,
    is_winter: bool,
) -> EconomyOutput {
    let n_regions = region_inputs.len();
    assert_eq!(agent_counts.len(), n_regions, "agent_counts length mismatch");

    // Build region_id → index lookup.
    let mut region_id_to_idx: Vec<usize> = Vec::new();
    let mut max_region_id: usize = 0;
    for inp in region_inputs.iter() {
        let rid = inp.region_id as usize;
        if rid > max_region_id {
            max_region_id = rid;
        }
    }
    region_id_to_idx.resize(max_region_id + 1, usize::MAX);
    for (idx, inp) in region_inputs.iter().enumerate() {
        region_id_to_idx[inp.region_id as usize] = idx;
    }

    let mut conservation = ConservationSummary::new();

    // -----------------------------------------------------------------------
    // Phase A: Production & demand (per-region)
    // -----------------------------------------------------------------------

    let mut work: Vec<RegionWorkState> = Vec::with_capacity(n_regions);
    for (i, inp) in region_inputs.iter().enumerate() {
        let ac = &agent_counts[i];
        let slot = rt_to_slot(inp.resource_type_0);
        let cat = if slot < NUM_GOODS { slot_to_category(slot) } else { CAT_FOOD };

        // Production: single resource slot.
        let mut production = [0.0f32; NUM_CATEGORIES];
        let amount = if slot < NUM_GOODS {
            inp.resource_effective_yield_0 * ac.farmer_count as f32
        } else {
            0.0
        };
        production[cat] = amount;
        conservation.production += amount as f64;

        // Demand.
        let demand = [
            ac.population as f32 * config.per_capita_food,                // food
            ac.soldier_count as f32 * config.raw_material_per_soldier,    // raw_material
            ac.wealthy_count as f32 * config.luxury_per_wealthy_agent,    // luxury
        ];

        // Pre-trade prices.
        let mut prices = [0.0f32; NUM_CATEGORIES];
        for c in 0..NUM_CATEGORIES {
            let s = production[c].max(SUPPLY_FLOOR);
            prices[c] = config.base_price * (demand[c] / s);
        }

        // Exportable surplus.
        let mut surplus = [0.0f32; NUM_CATEGORIES];
        for c in 0..NUM_CATEGORIES {
            surplus[c] = (production[c] - demand[c]).max(0.0);
        }

        work.push(RegionWorkState {
            production,
            demand,
            prices,
            surplus,
            imports: [0.0; NUM_CATEGORIES],
            exports: [0.0; NUM_CATEGORIES],
            stockpile: inp.stockpile,
            primary_good_slot: slot,
            primary_category: cat,
        });
    }

    // -----------------------------------------------------------------------
    // Phase B: Trade kernel (sequential, deterministic)
    // -----------------------------------------------------------------------

    // Build sorted route list and per-origin boundary pair counts.
    let mut sorted_routes: Vec<(u16, u16, bool)> = routes
        .iter()
        .map(|r| (r.origin_region_id, r.dest_region_id, r.is_river))
        .collect();
    sorted_routes.sort_by_key(|&(o, d, _)| (o, d));

    // Boundary pair counts per origin (before zero-flow pruning).
    let mut boundary_pair_counts: Vec<u16> = vec![0u16; n_regions];
    for &(origin_id, _, _) in &sorted_routes {
        let oidx = region_id_to_idx[origin_id as usize];
        if oidx < n_regions {
            boundary_pair_counts[oidx] += 1;
        }
    }

    // Build RouteWork entries with transport costs.
    let mut route_works: Vec<RouteWork> = Vec::with_capacity(sorted_routes.len());
    for &(origin_id, dest_id, is_river) in &sorted_routes {
        let oidx = region_id_to_idx[origin_id as usize];
        let didx = region_id_to_idx[dest_id as usize];
        if oidx >= n_regions || didx >= n_regions {
            continue;
        }
        let tc = compute_transport_cost(
            region_inputs[oidx].terrain,
            region_inputs[didx].terrain,
            is_river,
            is_winter,
            trade_friction,
        );
        route_works.push(RouteWork {
            origin_idx: oidx,
            dest_idx: didx,
            transport_cost: tc,
            flow: [0.0; NUM_CATEGORIES],
        });
    }

    // Group routes by origin index for allocation.
    // Build an index: for each origin region, a range into route_works.
    let mut origin_route_ranges: Vec<(usize, usize)> = Vec::new(); // (start, end) per origin
    {
        let mut origin_groups: Vec<(usize, usize, usize)> = Vec::new(); // (origin_idx, start, count)
        if !route_works.is_empty() {
            let mut cur_origin = route_works[0].origin_idx;
            let mut start = 0;
            for (i, rw) in route_works.iter().enumerate() {
                if rw.origin_idx != cur_origin {
                    origin_groups.push((cur_origin, start, i - start));
                    cur_origin = rw.origin_idx;
                    start = i;
                }
            }
            origin_groups.push((cur_origin, start, route_works.len() - start));
        }

        // Store in a flat lookup by region index.
        origin_route_ranges.resize(n_regions, (0, 0));
        for &(oidx, start, count) in &origin_groups {
            origin_route_ranges[oidx] = (start, start + count);
        }
    }

    // Tatonnement loop.
    for _pass in 0..config.tatonnement_max_passes {
        // Save previous prices for convergence check and damping.
        let prev_prices: Vec<[f32; NUM_CATEGORIES]> = work.iter().map(|w| w.prices).collect();

        // Re-zero import/export accumulators.
        for w in work.iter_mut() {
            w.imports = [0.0; NUM_CATEGORIES];
            w.exports = [0.0; NUM_CATEGORIES];
        }

        // Zero route flows.
        for rw in route_works.iter_mut() {
            rw.flow = [0.0; NUM_CATEGORIES];
        }

        // For each origin, allocate trade flow.
        for ri in 0..n_regions {
            let (rstart, rend) = origin_route_ranges[ri];
            if rstart == rend {
                continue;
            }
            let merchant_count = agent_counts[ri].merchant_count;
            let capacity = merchant_count as f32 * config.carry_per_merchant;
            if capacity <= 0.0 {
                continue;
            }

            let origin_prices = work[ri].prices;
            let origin_surplus = work[ri].surplus;

            // Compute margin weights per category per route.
            let n_routes = rend - rstart;
            // Flatten: route_cat_weights[route_local * NUM_CATEGORIES + cat]
            let mut route_cat_weights: Vec<f32> = vec![0.0; n_routes * NUM_CATEGORIES];
            let mut cat_total_weights = [0.0f32; NUM_CATEGORIES];

            for (local_i, rw_idx) in (rstart..rend).enumerate() {
                let dest_idx = route_works[rw_idx].dest_idx;
                let tc = route_works[rw_idx].transport_cost;
                let dest_prices = work[dest_idx].prices;
                for c in 0..NUM_CATEGORIES {
                    let price_gap = dest_prices[c] - origin_prices[c];
                    let raw_margin = (price_gap - tc).max(0.0);
                    let weight = (1.0 + raw_margin).ln();
                    route_cat_weights[local_i * NUM_CATEGORIES + c] = weight;
                    cat_total_weights[c] += weight;
                }
            }

            let total_weight: f32 = cat_total_weights.iter().sum();
            if total_weight <= 0.0 {
                continue;
            }

            // Allocate per category.
            for c in 0..NUM_CATEGORIES {
                let cat_budget = (cat_total_weights[c] / total_weight) * capacity;
                let surplus = origin_surplus[c];
                if cat_budget <= 0.0 || surplus <= 0.0 {
                    continue;
                }
                let cat_w = cat_total_weights[c];
                if cat_w <= 0.0 {
                    continue;
                }

                // Pro-rata allocation within category by route weight.
                let mut allocated = 0.0f32;
                for (local_i, rw_idx) in (rstart..rend).enumerate() {
                    let w = route_cat_weights[local_i * NUM_CATEGORIES + c];
                    if w <= 0.0 {
                        continue;
                    }
                    let amount = (w / cat_w) * cat_budget;
                    route_works[rw_idx].flow[c] = amount;
                    allocated += amount;
                }

                // Scale down if allocated exceeds surplus.
                if allocated > surplus {
                    let scale = surplus / allocated;
                    for rw_idx in rstart..rend {
                        route_works[rw_idx].flow[c] *= scale;
                    }
                }
            }

            // Accumulate exports/imports from this origin's routes.
            for rw_idx in rstart..rend {
                let dest_idx = route_works[rw_idx].dest_idx;
                for c in 0..NUM_CATEGORIES {
                    let amount = route_works[rw_idx].flow[c];
                    work[ri].exports[c] += amount;
                    work[dest_idx].imports[c] += amount;
                }
            }
        }

        // Recompute prices from production + imports with damping.
        for ri in 0..n_regions {
            let w = &work[ri];
            let mut new_prices = [0.0f32; NUM_CATEGORIES];
            for c in 0..NUM_CATEGORIES {
                let supply = (w.production[c] + w.imports[c]).max(SUPPLY_FLOOR);
                new_prices[c] = config.base_price * (w.demand[c] / supply);
            }
            for c in 0..NUM_CATEGORIES {
                let old_p = prev_prices[ri][c];
                if old_p < 0.001 {
                    work[ri].prices[c] = new_prices[c];
                    continue;
                }
                let ratio = new_prices[c] / old_p;
                let clamped = ratio.clamp(config.tatonnement_price_clamp_lo, config.tatonnement_price_clamp_hi);
                work[ri].prices[c] = old_p * (1.0 + config.tatonnement_damping * (clamped - 1.0));
            }
        }

        // Convergence check.
        let mut max_delta = 0.0f32;
        for ri in 0..n_regions {
            for c in 0..NUM_CATEGORIES {
                let delta = (work[ri].prices[c] - prev_prices[ri][c]).abs();
                if delta > max_delta {
                    max_delta = delta;
                }
            }
        }
        if max_delta < config.tatonnement_convergence {
            break;
        }
    }

    // Track inbound sources from final-pass positive flows.
    // Collect as (dest_region_id, source_region_id) pairs, deduped.
    let mut inbound_pairs: Vec<(u16, u16)> = Vec::new();
    for rw in route_works.iter() {
        let has_flow = rw.flow.iter().any(|&f| f > 0.0);
        if has_flow {
            let dest_id = region_inputs[rw.dest_idx].region_id;
            let origin_id = region_inputs[rw.origin_idx].region_id;
            inbound_pairs.push((dest_id, origin_id));
        }
    }
    // Sort and dedup for deterministic output.
    inbound_pairs.sort();
    inbound_pairs.dedup();

    // Build upstream_sources output.
    let mut upstream_sources: Vec<UpstreamSource> = Vec::new();
    {
        let mut ordinal_counter: u16 = 0;
        let mut last_dest: Option<u16> = None;
        for &(dest_id, src_id) in &inbound_pairs {
            if last_dest != Some(dest_id) {
                ordinal_counter = 0;
                last_dest = Some(dest_id);
            }
            upstream_sources.push(UpstreamSource {
                dest_region_id: dest_id,
                source_ordinal: ordinal_counter,
                source_region_id: src_id,
            });
            ordinal_counter += 1;
        }
    }

    // Per-good import decomposition with transit decay.
    // Per-route, per-good: only decomposes flows matching the origin's primary resource category.
    let mut per_good_imports: Vec<[f32; NUM_GOODS]> = vec![[0.0; NUM_GOODS]; n_regions];
    for rw in route_works.iter() {
        let origin_slot = work[rw.origin_idx].primary_good_slot;
        if origin_slot >= NUM_GOODS {
            continue;
        }
        let origin_cat = work[rw.origin_idx].primary_category;
        let shipped = rw.flow[origin_cat];
        if shipped <= 0.0 {
            continue;
        }
        let decay_rate = TRANSIT_DECAY[origin_slot];
        let delivered = shipped * (1.0 - decay_rate);
        conservation.transit_loss += (shipped - delivered) as f64;
        per_good_imports[rw.dest_idx][origin_slot] += delivered;
    }

    // -----------------------------------------------------------------------
    // Phase C: Post-trade prices
    // -----------------------------------------------------------------------

    let mut post_trade_prices: Vec<[f32; NUM_CATEGORIES]> = vec![[0.0; NUM_CATEGORIES]; n_regions];
    for ri in 0..n_regions {
        let w = &work[ri];
        for c in 0..NUM_CATEGORIES {
            let supply = (w.production[c] + w.imports[c]).max(SUPPLY_FLOOR);
            post_trade_prices[ri][c] = config.base_price * (w.demand[c] / supply);
        }
    }

    // -----------------------------------------------------------------------
    // Phase C: Stockpile lifecycle & signal derivation (per-region)
    // -----------------------------------------------------------------------

    let mut region_results: Vec<EconomyRegionResult> = Vec::with_capacity(n_regions);
    let mut observability: Vec<EconomyObservability> = Vec::with_capacity(n_regions);

    for ri in 0..n_regions {
        let inp = &region_inputs[ri];
        let ac = &agent_counts[ri];
        let w = &work[ri];

        // Per-good production and exports (map category amounts to good slot).
        let mut per_good_production = [0.0f32; NUM_GOODS];
        let mut per_good_exports = [0.0f32; NUM_GOODS];
        if w.primary_good_slot < NUM_GOODS {
            per_good_production[w.primary_good_slot] = w.production[w.primary_category];
            per_good_exports[w.primary_good_slot] = w.exports[w.primary_category];
        }

        // Step 1: Accumulate stockpile: old + production - exports + imports per good.
        let mut stockpile = w.stockpile;
        for g in 0..NUM_GOODS {
            let new_val = stockpile[g] + per_good_production[g] - per_good_exports[g]
                + per_good_imports[ri][g];
            if new_val < 0.0 {
                conservation.clamp_floor_loss += (-new_val) as f64;
                stockpile[g] = 0.0;
            } else {
                stockpile[g] = new_val;
            }
        }

        // Step 2: Derive food_sufficiency from pre-consumption stockpile.
        let food_demand = w.demand[CAT_FOOD];
        let total_food_stock: f32 = (0..NUM_GOODS)
            .filter(|&g| IS_FOOD[g])
            .map(|g| stockpile[g])
            .sum();
        let food_suff_denom = food_demand.max(SUPPLY_FLOOR);
        let food_sufficiency = (total_food_stock / food_suff_denom).clamp(0.0, 2.0);

        // Step 3: Consume from stockpile (proportional drawdown from food goods).
        if total_food_stock > 0.0 && food_demand > 0.0 {
            for g in 0..NUM_GOODS {
                if !IS_FOOD[g] {
                    continue;
                }
                let amount = stockpile[g];
                if amount <= 0.0 {
                    continue;
                }
                let share = amount / total_food_stock;
                let demand_for_good = food_demand * share;
                let consumed = demand_for_good.min(amount);
                stockpile[g] -= consumed;
                conservation.consumption += consumed as f64;
            }
        }

        // Step 4: Storage decay with salt preservation.
        {
            let total_food_excl_salt: f32 = (0..NUM_GOODS)
                .filter(|&g| IS_FOOD[g] && g != SLOT_SALT)
                .map(|g| stockpile[g])
                .sum();
            let salt_amount = stockpile[SLOT_SALT];
            let salt_ratio = salt_amount / total_food_excl_salt.max(0.1);
            let preservation = (salt_ratio * config.salt_preservation_factor)
                .min(config.max_preservation);

            for g in 0..NUM_GOODS {
                if g == SLOT_SALT {
                    continue;
                }
                let rate = STORAGE_DECAY[g];
                if rate <= 0.0 {
                    continue;
                }
                let effective_rate = if IS_FOOD[g] {
                    rate * (1.0 - preservation)
                } else {
                    rate
                };
                let old = stockpile[g];
                stockpile[g] *= 1.0 - effective_rate;
                conservation.storage_loss += (old - stockpile[g]) as f64;
            }
        }

        // Step 5: Cap stockpile.
        let cap = config.per_good_cap_factor * inp.storage_population as f32;
        for g in 0..NUM_GOODS {
            if stockpile[g] > cap {
                conservation.cap_overflow += (stockpile[g] - cap) as f64;
                stockpile[g] = cap;
            }
        }

        // Step 6: Derive signals.
        // farmer_income_modifier: demand / max(post_supply, 0.1) for the primary resource's category.
        let farmer_income_modifier = if w.primary_good_slot < NUM_GOODS {
            let cat = w.primary_category;
            let post_supply = (w.production[cat] + w.imports[cat]).max(SUPPLY_FLOOR);
            let raw = w.demand[cat] / post_supply;
            raw.clamp(config.farmer_income_modifier_floor, config.farmer_income_modifier_cap)
        } else {
            config.farmer_income_modifier_floor
        };

        // merchant_margin: normalized avg positive post-trade price delta across outgoing routes.
        let (rstart, rend) = origin_route_ranges[ri];
        let route_count = rend - rstart;
        let merchant_margin = if route_count > 0 {
            let mut total_raw_margin = 0.0f32;
            for rw_idx in rstart..rend {
                let dest_idx = route_works[rw_idx].dest_idx;
                for c in 0..NUM_CATEGORIES {
                    let delta = post_trade_prices[dest_idx][c] - post_trade_prices[ri][c];
                    total_raw_margin += delta.max(0.0);
                }
            }
            let avg = total_raw_margin / route_count as f32;
            (avg / config.merchant_margin_normalizer).clamp(0.0, 1.0)
        } else {
            0.0
        };

        // merchant_trade_income: route_flow x post-trade margin / merchant_count.
        let merchant_trade_income = if ac.merchant_count > 0 && route_count > 0 {
            let mut total_arbitrage = 0.0f32;
            for rw_idx in rstart..rend {
                let dest_idx = route_works[rw_idx].dest_idx;
                for c in 0..NUM_CATEGORIES {
                    let margin = (post_trade_prices[dest_idx][c] - post_trade_prices[ri][c]).max(0.0);
                    total_arbitrage += route_works[rw_idx].flow[c] * margin;
                }
            }
            total_arbitrage / ac.merchant_count as f32
        } else {
            0.0
        };

        // trade_route_count = boundary pair count before zero-flow pruning.
        let trade_route_count = boundary_pair_counts[ri];

        region_results.push(EconomyRegionResult {
            region_id: inp.region_id,
            stockpile,
            farmer_income_modifier,
            food_sufficiency,
            merchant_margin,
            merchant_trade_income,
            trade_route_count,
        });

        // Step 7: Derive observability.
        // imports_by_category: from pre-transit-decay category-level imports (tatonnement accumulation).
        let imports_food = w.imports[CAT_FOOD];
        let imports_raw_material = w.imports[CAT_RAW_MATERIAL];
        let imports_luxury = w.imports[CAT_LUXURY];

        // stockpile_levels: post-lifecycle goods aggregated by category.
        let mut stockpile_food = 0.0f32;
        let mut stockpile_raw_material = 0.0f32;
        let mut stockpile_luxury = 0.0f32;
        for g in 0..NUM_GOODS {
            match GOOD_CATEGORY[g] {
                CAT_FOOD => stockpile_food += stockpile[g],
                CAT_RAW_MATERIAL => stockpile_raw_material += stockpile[g],
                CAT_LUXURY => stockpile_luxury += stockpile[g],
                _ => {}
            }
        }

        // import_share: food_imports / max(food_demand, 0.1).
        let import_share = imports_food / food_demand.max(SUPPLY_FLOOR);
        let trade_dependent = import_share > config.trade_dependency_threshold;

        observability.push(EconomyObservability {
            region_id: inp.region_id,
            imports_food,
            imports_raw_material,
            imports_luxury,
            stockpile_food,
            stockpile_raw_material,
            stockpile_luxury,
            import_share,
            trade_dependent,
        });
    }

    // -----------------------------------------------------------------------
    // Phase D: Civ fiscal + conservation (per-civ)
    // -----------------------------------------------------------------------

    let mut civ_results: Vec<EconomyCivResult> = Vec::with_capacity(n_civs);
    for civ_idx in 0..n_civs {
        let mw = if civ_idx < civ_merchant_wealth.len() {
            civ_merchant_wealth[civ_idx]
        } else {
            0.0
        };
        let pc = if civ_idx < civ_priest_count.len() {
            civ_priest_count[civ_idx]
        } else {
            0
        };

        let treasury_tax = config.tax_rate * mw;
        let tithe_base = mw;
        let priest_tithe_share = TITHE_RATE * mw / (pc.max(1) as f32);

        civ_results.push(EconomyCivResult {
            civ_id: civ_idx as u16,
            treasury_tax,
            tithe_base,
            priest_tithe_share,
        });
    }

    EconomyOutput {
        region_results,
        civ_results,
        observability,
        upstream_sources,
        conservation,
    }
}

// ---------------------------------------------------------------------------
// Tests — minimal smoke tests.  Comprehensive coverage in tests/test_economy.rs.
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_smoke_single_region() {
        let config = EconomyConfig::default();
        let regions = vec![EconomyRegionInput {
            region_id: 0,
            terrain: 0,
            storage_population: 100,
            resource_type_0: 0,
            resource_effective_yield_0: 1.0,
            stockpile: [0.0; NUM_GOODS],
        }];
        let agents = vec![RegionAgentCounts {
            population: 100,
            farmer_count: 50,
            soldier_count: 10,
            merchant_count: 5,
            wealthy_count: 2,
        }];

        let out = tick_economy_core(
            &regions, &agents, &[], &[0.0], &[0], 1,
            &config, 1.0, false,
        );

        assert_eq!(out.region_results.len(), 1);
        assert_eq!(out.civ_results.len(), 1);
        assert!((out.conservation.production - 50.0).abs() < 0.01);
    }

    #[test]
    fn test_transport_cost_values() {
        // Plains avg: (1.0+1.0)/2 = 1.0. Base = 0.10.
        assert!((compute_transport_cost(0, 0, false, false, 1.0) - 0.10).abs() < 0.001);
        // River: 0.10 * 0.5 = 0.05
        assert!((compute_transport_cost(0, 0, true, false, 1.0) - 0.05).abs() < 0.001);
        // Coastal: (0.6+0.6)/2 * 0.10 * 0.6 = 0.036
        assert!((compute_transport_cost(TERRAIN_COAST, TERRAIN_COAST, false, false, 1.0) - 0.036).abs() < 0.001);
        // Winter: 0.10 * 1.5 = 0.15
        assert!((compute_transport_cost(0, 0, false, true, 1.0) - 0.15).abs() < 0.001);
    }
}
