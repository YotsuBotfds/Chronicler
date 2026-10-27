//! Pure Rust economy core — Phase 2 production, demand, tatonnement pricing,
//! trade allocation, transit decay, stockpile lifecycle, signal derivation,
//! observability, and conservation.  No PyO3 — FFI wrappers live in ffi.rs.

// ---------------------------------------------------------------------------
// Constants — fixed good slots
// ---------------------------------------------------------------------------

/// Number of fixed good slots in the stockpile array.
pub const NUM_GOODS: usize = 9;
/// Number of M34 resource types (the harvested goods; crafts are made).
pub const NUM_RESOURCE_TYPES: usize = 8;

/// Good slot indices.
pub const SLOT_GRAIN: usize = 0;
pub const SLOT_FISH: usize = 1;
pub const SLOT_SALT: usize = 2;
pub const SLOT_TIMBER: usize = 3;
pub const SLOT_ORE: usize = 4;
pub const SLOT_BOTANICALS: usize = 5;
pub const SLOT_PRECIOUS: usize = 6;
pub const SLOT_EXOTIC: usize = 7;
/// Crafts (2026-10, docs/integration/bulk-trade-crafts.md): wares made in
/// cities from raw materials (tools, cloth, pottery, metalwork).
pub const SLOT_CRAFTS: usize = 8;

/// Category indices.
pub const CAT_FOOD: usize = 0;
pub const CAT_RAW_MATERIAL: usize = 1;
pub const CAT_LUXURY: usize = 2;
pub const CAT_CRAFT: usize = 3;
pub const NUM_CATEGORIES: usize = 4;

/// Good slot → category mapping.
pub const GOOD_CATEGORY: [usize; NUM_GOODS] = [
    CAT_FOOD,         // 0: grain
    CAT_FOOD,         // 1: fish
    CAT_FOOD,         // 2: salt
    CAT_RAW_MATERIAL, // 3: timber
    CAT_RAW_MATERIAL, // 4: ore
    CAT_FOOD,         // 5: botanicals
    CAT_LUXURY,       // 6: precious
    CAT_FOOD,         // 7: exotic
    CAT_CRAFT,        // 8: crafts
];

/// Resource type enum → good slot index.
const RT_TO_SLOT: [usize; NUM_RESOURCE_TYPES] = [
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
    false, // crafts
];

/// Terrain cost for transport.  Indexed by terrain u8 encoding.
/// plains(0)=1.0, mountains(1)=2.0, coast(2)=0.6, forest(3)=1.3, desert(4)=1.5, tundra(5)=1.8,
/// steppe(6)=1.1, jungle(7)=1.7, marsh(8)=1.6 (mirrors Python economy.TERRAIN_COST)
const TERRAIN_COST: [f32; 9] = [1.0, 2.0, 0.6, 1.3, 1.5, 1.8, 1.1, 1.7, 1.6];

/// Per-good transit decay rate.
pub const TRANSIT_DECAY: [f32; NUM_GOODS] = [
    0.05, // grain
    0.08, // fish
    0.0,  // salt
    0.01, // timber
    0.0,  // ore
    0.04, // botanicals
    0.0,  // precious
    0.06, // exotic
    0.0,  // crafts
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
    0.01,  // crafts (wear)
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

/// Food sufficiency threshold below which tithe collection is reduced.
/// Matches Python economy.py H-2 food gate: `tithe_scale = min(avg_food_suff / 0.5, 1.0)`.
const TITHE_FOOD_GATE: f32 = 0.5;

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
    pub resource_types: [u8; 3],
    /// Realized, current-turn ecology yields (not potential effective yields).
    pub resource_yields: [f32; 3],
    /// Optional per-slot output bound after labor allocation (the fishery
    /// experiment's prior catch, in goods). `None` leaves the slot uncapped.
    /// A capped slot keeps its labor share; spare labor is not reassigned.
    pub production_caps: [Option<f32>; 3],
    pub stockpile: [f32; NUM_GOODS],
    /// Goods per farmer from foraging this turn (M34's subsistence baseline
    /// in goods; see `allocate_farm_labor`). 0.0 disables foraging.
    pub subsistence_yield: f32,
    /// Cities (`--cities`): share of the region's farmer labor that works
    /// the land, below 1 where farmers live in a city and give part of their
    /// time to it (Python `cities.economy_columns`). 1.0 without the switch.
    pub farm_labor_factor: f32,
    /// Cities (`--cities`): raw materials the region's city crafts want, added
    /// to the soldiers' raw-material demand, and (2026-10 crafts) the most the
    /// crafts can work into wares this turn, one raw load per load of wares.
    /// 0.0 without the switch.
    pub craft_raw_demand: f32,
    /// Crafts (`--cities`): wares the region's people want this turn. 0.0
    /// without the switch (no market for wares).
    pub craft_demand: f32,
    /// Diminishing returns to farm labour (see `effective_farm_labor`): the
    /// labour at which a farmer produces today's constant-returns output, and
    /// the curve's half-saturation labour. 0.0 keeps constant returns.
    pub farm_labor_ref: f32,
    pub farm_labor_half: f32,
    /// Mines and forests (2026-10, docs/integration/bulk-trade-crafts.md):
    /// with `slot_curves` the farm curve applies to the food labour only and
    /// each non-food slot's labour has its own curve (`slot_labor_ref` /
    /// `slot_labor_half`, 0 keeps that slot at constant returns). Without it
    /// the farm curve applies to all farm labour.
    pub slot_curves: bool,
    pub slot_labor_ref: [f32; 3],
    pub slot_labor_half: [f32; 3],
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
// M58b: Hybrid delivery input (from merchant mobility DeliveryBuffer)
// ---------------------------------------------------------------------------

/// Pre-aggregated delivery buffer data for hybrid economy ingress.
/// Constructed from the merchant mobility DeliveryBuffer, consumed by
/// `tick_economy_core` in hybrid mode to replace abstract tatonnement trade.
pub struct HybridDeliveryInput {
    /// Per-region departure debits (negative delta on origin stockpile).
    pub departure_debits: Vec<[f32; NUM_GOODS]>,
    /// Per-region arrival imports aggregated from raw records (pre-transit-decay quantities).
    /// Transit decay is applied inside `tick_economy_core` when computing `per_good_imports`.
    pub arrival_imports: Vec<[f32; NUM_GOODS]>,
    /// Raw arrival records with provenance (for merchant_trade_income derivation).
    pub arrival_imports_raw: Vec<crate::merchant::ArrivalRecord>,
    /// Per-region return credits (positive delta on origin stockpile, full value).
    pub return_credits: Vec<[f32; NUM_GOODS]>,
    /// Deduplicated (dest_region, source_region) pairs for upstream source output.
    pub inbound_pairs: Vec<(u16, u16)>,
}

impl HybridDeliveryInput {
    /// Build from a merchant mobility `DeliveryBuffer`.
    ///
    /// Aggregates per-record arrival imports into per-region arrays and
    /// extracts unique inbound pairs for upstream source tracking.
    pub fn from_buffer(buf: &crate::merchant::DeliveryBuffer, num_regions: usize) -> Self {
        let mut arrival_imports = vec![[0.0f32; NUM_GOODS]; num_regions];
        let mut inbound_pairs: Vec<(u16, u16)> = Vec::new();
        for rec in &buf.arrival_imports {
            let dest = rec.dest_region as usize;
            let slot = rec.good_slot as usize;
            if dest < num_regions && slot < NUM_GOODS {
                arrival_imports[dest][slot] += rec.qty;
                inbound_pairs.push((rec.dest_region, rec.source_region));
            }
        }
        inbound_pairs.sort();
        inbound_pairs.dedup();

        Self {
            departure_debits: buf.departure_debits.clone(),
            arrival_imports,
            arrival_imports_raw: buf.arrival_imports.clone(),
            return_credits: buf.return_credits.clone(),
            inbound_pairs,
        }
    }
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
    /// Demand per category (food, raw material, luxury) and post-trade
    /// supply (available - exports + imports, the denominator of the
    /// post-trade price before `SUPPLY_FLOOR`): the merchant planner's
    /// market prices (`merchant::market_price`).
    pub market_demand: [f32; NUM_CATEGORIES],
    pub market_supply: [f32; NUM_CATEGORIES],
    /// Output per farmer relative to constant returns (effective over
    /// headcount labour, `effective_farm_labor`); 1.0 without the curve or
    /// without farmers. Scales farmer income in the agent tick.
    pub farm_productivity: f32,
    /// Crafts: wares made this turn, and wares on hand before the people
    /// used them over their demand (0..2; 0 without demand).
    pub craft_output: f32,
    pub craft_sufficiency: f32,
    /// Goods produced by each resource slot this turn (after any production
    /// cap): what the land gave up. The ecology depletes mineral reserves by
    /// it (`RegionState::realized_extraction`).
    pub slot_output: [f32; 3],
    /// Grain foraged this turn by farmers without a yielding food slot
    /// (`FarmLabor::forage_labor` x `forage_yield`). With `slot_output` and
    /// `craft_output` it is all the region's production: the production
    /// ledger reconciles their sum with `ConservationSummary::production`.
    pub forage_output: f32,
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
    pub imports_craft: f32,
    pub stockpile_food: f32,
    pub stockpile_raw_material: f32,
    pub stockpile_luxury: f32,
    pub stockpile_craft: f32,
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
    /// M58b: in-flight inventory change = departures - arrivals - returns.
    /// `Some` in hybrid mode, `None` in abstract mode.
    pub in_transit_delta: Option<f64>,
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
            in_transit_delta: None,
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
    /// M58b: Oracle shadow — abstract trade volumes per region per category.
    /// Only populated in hybrid mode (when delivery buffer is provided and routes exist).
    pub oracle_trade_volume: Option<Vec<[f32; NUM_CATEGORIES]>>,
    /// M58b: Oracle shadow margins per region (normalized 0-1).
    pub oracle_margins: Option<Vec<f32>>,
    /// M58b: Oracle shadow food sufficiency per region (0-2 clamped).
    pub oracle_food_sufficiency: Option<Vec<f32>>,
    /// M58b: Per-region per-good transit decay totals from arrival processing.
    /// Only populated in hybrid mode. Written back to DeliveryBuffer diagnostics by FFI layer.
    pub transit_decay_by_region: Option<Vec<[f32; NUM_GOODS]>>,
}

// ---------------------------------------------------------------------------
// Internal working structures
// ---------------------------------------------------------------------------

/// Per-region transient state during economy tick.
#[derive(Clone)]
struct RegionWorkState {
    /// Per-category production [food, raw_material, luxury].
    production: [f32; NUM_CATEGORIES],
    /// Realized production retained per good through the entire stock-flow lifecycle.
    per_good_production: [f32; NUM_GOODS],
    /// Starting inventory plus production, aggregated by category.
    available: [f32; NUM_CATEGORIES],
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
    /// Crafts: raw materials worked into wares this turn, per good.
    craft_input: [f32; NUM_GOODS],
}

/// Per-route working data for trade kernel.
#[derive(Clone)]
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

/// Whether a resource type's harvest counts as food (grain, fish, salt,
/// botanicals, exotic), as the goods economy counts it.
#[inline]
pub fn is_food_resource(rt: u8) -> bool {
    let slot = rt_to_slot(rt);
    slot < NUM_GOODS && IS_FOOD[slot]
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

/// Share of its equal labor that a non-food slot always keeps.
pub const FOOD_FIRST_NONFOOD_FLOOR: f32 = 0.25;

/// Food-first farmer labor per resource slot.
///
/// Labor starts from the equal split across occupied valid slots. When a
/// region has both food and non-food slots and the food slots' equal share
/// would not cover this turn's food demand, farmers move from the non-food
/// slots to the food slots until the harvest covers demand, but each non-food
/// slot keeps at least `FOOD_FIRST_NONFOOD_FLOOR` of its equal share. Food
/// slots never receive less than their equal share, and the total labor is
/// unchanged. Mirrors Python `food_first_slot_labor`.
pub fn food_first_slot_labor(
    resource_types: &[u8; 3],
    resource_yields: &[f32; 3],
    farmers: f32,
    food_demand: f32,
    equal_share: f32,
) -> [f32; 3] {
    food_first_slot_labor_curved(resource_types, resource_yields, farmers, food_demand, equal_share, (0.0, 0.0))
}

/// Headcount labour that does the work of `effective` labour on the curve
/// (`effective_farm_labor` inverted); infinite at or above the land's
/// ceiling, `effective` itself without a curve.
#[inline]
pub fn farm_labor_for_effective(effective: f32, labor_ref: f32, labor_half: f32) -> f32 {
    if labor_ref <= 0.0 || effective <= 0.0 {
        return effective;
    }
    let ceiling = labor_ref + labor_half;
    if effective >= ceiling {
        return f32::INFINITY;
    }
    effective * labor_half / (ceiling - effective)
}

/// [`food_first_slot_labor`] in headcount labour when the food labour works
/// on the curve `food_curve` (L_ref, L_h): the labour the harvest needs is
/// the headcount whose effective labour covers demand. (0, 0) is
/// `food_first_slot_labor`.
pub fn food_first_slot_labor_curved(
    resource_types: &[u8; 3],
    resource_yields: &[f32; 3],
    farmers: f32,
    food_demand: f32,
    equal_share: f32,
    food_curve: (f32, f32),
) -> [f32; 3] {
    let mut labor = [0.0f32; 3];
    let mut n_food = 0usize;
    let mut n_other = 0usize;
    let mut food_yield_sum = 0.0f32;
    for i in 0..3 {
        let slot = rt_to_slot(resource_types[i]);
        if slot >= NUM_GOODS {
            continue;
        }
        labor[i] = equal_share;
        if slot_to_category(slot) == CAT_FOOD {
            n_food += 1;
            food_yield_sum += resource_yields[i].max(0.0);
        } else {
            n_other += 1;
        }
    }
    if n_food == 0 || n_other == 0 || food_yield_sum <= 0.0 || farmers <= 0.0 {
        return labor;
    }
    let mean_food_yield = food_yield_sum / n_food as f32;
    let equal_food_labor = equal_share * n_food as f32;
    let needed = farm_labor_for_effective(food_demand.max(0.0) / mean_food_yield, food_curve.0, food_curve.1);
    if needed <= equal_food_labor {
        return labor;
    }
    let max_food_labor = farmers - FOOD_FIRST_NONFOOD_FLOOR * equal_share * n_other as f32;
    let food_labor = needed.min(max_food_labor.max(equal_food_labor));
    let per_food = food_labor / n_food as f32;
    let per_other = (farmers - food_labor).max(0.0) / n_other as f32;
    for i in 0..3 {
        let slot = rt_to_slot(resource_types[i]);
        if slot >= NUM_GOODS {
            continue;
        }
        labor[i] = if slot_to_category(slot) == CAT_FOOD { per_food } else { per_other };
    }
    labor
}

/// Farmer labor per resource slot and on foraging.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FarmLabor {
    /// Labor on each resource slot (as `food_first_slot_labor`).
    pub slot_labor: [f32; 3],
    /// Labor that forages, producing `forage_yield` grain per farmer.
    pub forage_labor: f32,
    /// Foraged grain per farmer this turn (0 when nobody forages).
    pub forage_yield: f32,
}

/// Correction (2026-10, food logistics): M34's subsistence baseline in the
/// goods economy.
///
/// The aggregate model's famine check gives a region whose food slots yield
/// nothing (no food slot at all, or every food slot suspended) a food yield
/// of `SUBSISTENCE_BASELINE x crop climate` ("mountain villages survived on
/// terrace agriculture and herding; forest communities foraged", M34). Since
/// PR #11 the goods economy decides famine in agent modes, and it had no
/// counterpart: such regions produced no food at all. Here the farmers who
/// would work food land forage instead, at `subsistence_yield` goods each
/// (Python passes the baseline converted to goods on the grain scale).
///
/// * Some food slot yields: unchanged (`food_first_slot_labor`).
/// * Food slots exist but none yields (suspended): their labor forages.
/// * No food slot: foraging is one more food share in the food-first split,
///   and every non-food slot keeps `FOOD_FIRST_NONFOOD_FLOOR` of its equal
///   share. Without any valid slot every farmer forages.
///
/// Mirrors Python `economy.farm_labor`.
pub fn allocate_farm_labor(
    resource_types: &[u8; 3],
    resource_yields: &[f32; 3],
    farmers: f32,
    food_demand: f32,
    subsistence_yield: f32,
) -> FarmLabor {
    allocate_farm_labor_curved(resource_types, resource_yields, farmers, food_demand, subsistence_yield, (0.0, 0.0))
}

/// [`allocate_farm_labor`] in headcount labour with the food labour on the
/// curve `food_curve` (see `food_first_slot_labor_curved`).
pub fn allocate_farm_labor_curved(
    resource_types: &[u8; 3],
    resource_yields: &[f32; 3],
    farmers: f32,
    food_demand: f32,
    subsistence_yield: f32,
    food_curve: (f32, f32),
) -> FarmLabor {
    let mut n_valid = 0usize;
    let mut n_food = 0usize;
    let mut food_output = false;
    for i in 0..3 {
        let slot = rt_to_slot(resource_types[i]);
        if slot >= NUM_GOODS {
            continue;
        }
        n_valid += 1;
        if slot_to_category(slot) == CAT_FOOD {
            n_food += 1;
            food_output |= resource_yields[i] > 0.0;
        }
    }
    let forage_yield = if food_output { 0.0 } else { subsistence_yield.max(0.0) };
    if forage_yield <= 0.0 || farmers <= 0.0 {
        let equal_share = farmers / n_valid.max(1) as f32;
        return FarmLabor {
            slot_labor: food_first_slot_labor_curved(
                resource_types, resource_yields, farmers, food_demand, equal_share, food_curve,
            ),
            forage_labor: 0.0,
            forage_yield: 0.0,
        };
    }
    let is_food = |i: usize| {
        let slot = rt_to_slot(resource_types[i]);
        slot < NUM_GOODS && slot_to_category(slot) == CAT_FOOD
    };
    if n_food > 0 {
        // Barren food slots: their workers forage, split food-first as if the
        // slots yielded the subsistence rate.
        let mut yields = *resource_yields;
        for i in 0..3 {
            if is_food(i) {
                yields[i] = forage_yield;
            }
        }
        let equal_share = farmers / n_valid as f32;
        let mut slot_labor =
            food_first_slot_labor_curved(resource_types, &yields, farmers, food_demand, equal_share, food_curve);
        let mut forage_labor = 0.0;
        for i in 0..3 {
            if is_food(i) {
                forage_labor += slot_labor[i];
                slot_labor[i] = 0.0;
            }
        }
        return FarmLabor { slot_labor, forage_labor, forage_yield };
    }
    // No food slot: foraging joins the split as one food share.
    let n_other = n_valid;
    let equal_share = farmers / (n_other + 1) as f32;
    let needed = farm_labor_for_effective(food_demand.max(0.0) / forage_yield, food_curve.0, food_curve.1);
    let max_food_labor = farmers - FOOD_FIRST_NONFOOD_FLOOR * equal_share * n_other as f32;
    let forage_labor = needed.min(max_food_labor).max(equal_share).min(farmers);
    let per_other = if n_other > 0 { (farmers - forage_labor).max(0.0) / n_other as f32 } else { 0.0 };
    let mut slot_labor = [0.0f32; 3];
    for i in 0..3 {
        if rt_to_slot(resource_types[i]) < NUM_GOODS {
            slot_labor[i] = per_other;
        }
    }
    FarmLabor { slot_labor, forage_labor, forage_yield }
}

/// Diminishing returns to farm labour on a region's land (2026-10,
/// docs/integration/farmland-climate.md).
///
/// Effective labour `E(L) = L (L_ref + L_h) / (L + L_h)`, a saturating
/// (Michaelis-Menten) curve in the farmers working the land: `E(L_ref) =
/// L_ref`, so at the reference labour a farmer produces what constant returns
/// gave; fewer farmers produce more each (up to `1 + L_ref / L_h` times),
/// more produce less, and the land's output never exceeds `L_ref + L_h`.
/// Python sets both from the region's arable capacity (potential capacity
/// raised by farming techniques and irrigation). `labor_ref <= 0` keeps
/// constant returns. Mirrors Python `economy.effective_farm_labor`.
#[inline]
pub fn effective_farm_labor(labor: f32, labor_ref: f32, labor_half: f32) -> f32 {
    if labor_ref <= 0.0 || labor <= 0.0 {
        return labor;
    }
    labor * (labor_ref + labor_half) / (labor + labor_half)
}

/// Mines and forests (2026-10, docs/integration/bulk-trade-crafts.md): farm
/// labour split by headcount (food-first, the food labour's needs read
/// through the farm curve), then the food labour (food slots and foraging)
/// works the farmland on the farm curve and each non-food slot's labour its
/// own deposit or forest (`slot_labor_ref` / `slot_labor_half`). Returns the
/// effective labour per slot and on foraging, and output per farmer against
/// constant returns (1.0 without farmers). Mirrors Python
/// `economy.slot_curve_labor`.
pub fn split_labor_on_slot_curves(
    inp: &EconomyRegionInput,
    headcount_labor: f32,
    food_demand: f32,
) -> (FarmLabor, f32) {
    let food_curve = (inp.farm_labor_ref, inp.farm_labor_half);
    let mut labor = allocate_farm_labor_curved(
        &inp.resource_types, &inp.resource_yields, headcount_labor, food_demand, inp.subsistence_yield, food_curve,
    );
    let mut food_head = labor.forage_labor;
    for i in 0..3 {
        let slot = rt_to_slot(inp.resource_types[i]);
        if slot < NUM_GOODS && IS_FOOD[slot] {
            food_head += labor.slot_labor[i];
        }
    }
    let food_scale = if food_head > 0.0 {
        effective_farm_labor(food_head, food_curve.0, food_curve.1) / food_head
    } else {
        1.0
    };
    let mut effective = labor.forage_labor * food_scale;
    labor.forage_labor *= food_scale;
    for i in 0..3 {
        let slot = rt_to_slot(inp.resource_types[i]);
        if slot >= NUM_GOODS {
            continue;
        }
        labor.slot_labor[i] = if IS_FOOD[slot] {
            labor.slot_labor[i] * food_scale
        } else {
            effective_farm_labor(labor.slot_labor[i], inp.slot_labor_ref[i], inp.slot_labor_half[i])
        };
        effective += labor.slot_labor[i];
    }
    let productivity = if headcount_labor > 0.0 { effective / headcount_labor } else { 1.0 };
    (labor, productivity)
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
    let mut cost = TRANSPORT_COST_BASE * cost_a.max(cost_b);
    let river = if is_river { RIVER_DISCOUNT } else { 1.0 };
    let both_coastal = terrain_a == TERRAIN_COAST && terrain_b == TERRAIN_COAST;
    let coastal = if both_coastal { COASTAL_DISCOUNT } else { 1.0 };
    // Match the Python oracle: the harder terrain governs the route and the
    // best available waterway discount applies (discounts do not compound).
    cost *= river.min(coastal);
    if is_winter {
        cost *= WINTER_MODIFIER;
    }
    cost * trade_friction
}

/// Split a category shipment across the origin's actual goods. All routes use
/// the same fixed starting inventory mix, so total exports remain bounded by
/// that inventory and category demand is reserved proportionally.
fn route_good_shipments(origin: &RegionWorkState, route: &RouteWork) -> [f32; NUM_GOODS] {
    let mut shipments = [0.0; NUM_GOODS];
    for g in 0..NUM_GOODS {
        let cat = GOOD_CATEGORY[g];
        if origin.available[cat] > 0.0 {
            let inventory = origin.stockpile[g] + origin.per_good_production[g] - origin.craft_input[g];
            shipments[g] = route.flow[cat] * (inventory / origin.available[cat]);
        }
    }
    shipments
}

/// Resolve abstract category flows to physical imports/exports exactly once.
/// Imports are delivered quantities, exports are gross shipments. The same
/// decomposition drives realized stockpiles and the hybrid oracle.
fn abstract_good_flows(
    work: &[RegionWorkState],
    routes: &[RouteWork],
) -> (Vec<[f32; NUM_GOODS]>, Vec<[f32; NUM_GOODS]>, f64) {
    let mut imports = vec![[0.0; NUM_GOODS]; work.len()];
    let mut exports = vec![[0.0; NUM_GOODS]; work.len()];
    let mut transit_loss = 0.0;
    for route in routes {
        let shipments = route_good_shipments(&work[route.origin_idx], route);
        for g in 0..NUM_GOODS {
            let shipped = shipments[g];
            let delivered = shipped * (1.0 - TRANSIT_DECAY[g]);
            exports[route.origin_idx][g] += shipped;
            imports[route.dest_idx][g] += delivered;
            transit_loss += (shipped - delivered) as f64;
        }
    }
    (imports, exports, transit_loss)
}

/// Run the tatonnement pricing equilibrium + route allocation on the given
/// work state and route set.  Modifies `work[ri].imports`, `work[ri].exports`,
/// and `work[ri].prices` in place.  `route_works[rw].flow` is populated with
/// the final-pass flow values.
///
/// This is factored out so both the abstract path and the oracle shadow can
/// call the same allocation logic without duplication.
fn run_abstract_allocation(
    work: &mut [RegionWorkState],
    agent_counts: &[RegionAgentCounts],
    route_works: &mut [RouteWork],
    origin_route_ranges: &[(usize, usize)],
    config: &EconomyConfig,
) {
    let n_regions = work.len();

    for _pass in 0..config.tatonnement_max_passes {
        let prev_prices: Vec<[f32; NUM_CATEGORIES]> = work.iter().map(|w| w.prices).collect();

        for w in work.iter_mut() {
            w.imports = [0.0; NUM_CATEGORIES];
            w.exports = [0.0; NUM_CATEGORIES];
        }
        for rw in route_works.iter_mut() {
            rw.flow = [0.0; NUM_CATEGORIES];
        }

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

            let n_routes = rend - rstart;
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

                if allocated > surplus {
                    let scale = surplus / allocated;
                    for rw_idx in rstart..rend {
                        route_works[rw_idx].flow[c] *= scale;
                    }
                }
            }

            for rw_idx in rstart..rend {
                let route = &route_works[rw_idx];
                let shipments = route_good_shipments(&work[ri], route);
                for g in 0..NUM_GOODS {
                    let cat = GOOD_CATEGORY[g];
                    work[ri].exports[cat] += shipments[g];
                    work[route.dest_idx].imports[cat] += shipments[g] * (1.0 - TRANSIT_DECAY[g]);
                }
            }
        }

        for ri in 0..n_regions {
            let w = &work[ri];
            let mut new_prices = [0.0f32; NUM_CATEGORIES];
            for c in 0..NUM_CATEGORIES {
                let supply = (w.available[c] - w.exports[c] + w.imports[c]).max(SUPPLY_FLOOR);
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
}

// ---------------------------------------------------------------------------
// Core tick function
// ---------------------------------------------------------------------------

/// Execute one turn of the Phase 2 economy computation.
///
/// This is the sequential, deterministic economy kernel.  No rayon, no RNG.
/// Route order is stable: sorted by (origin_region_id, dest_region_id).
/// Inputs must contain finite nonnegative inventory and valid, inventory-backed
/// hybrid departure debits. The merchant ledger revalidates cargo at departure;
/// clamp_floor_loss diagnoses invalid overdraw rather than a physical sink.
pub fn tick_economy_core(
    region_inputs: &[EconomyRegionInput],
    agent_counts: &[RegionAgentCounts],
    routes: &[TradeRouteInput],
    civ_merchant_wealth: &[f32],
    civ_priest_count: &[u32],
    n_civs: usize,
    region_civ_owner: &[u8],
    config: &EconomyConfig,
    trade_friction: f32,
    is_winter: bool,
    hybrid_delivery: Option<&HybridDeliveryInput>,
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
    let mut farm_productivity: Vec<f32> = Vec::with_capacity(n_regions);
    let mut craft_output: Vec<f32> = Vec::with_capacity(n_regions);
    let mut slot_output: Vec<[f32; 3]> = Vec::with_capacity(n_regions);
    let mut forage_output: Vec<f32> = Vec::with_capacity(n_regions);
    for (i, inp) in region_inputs.iter().enumerate() {
        let ac = &agent_counts[i];
        // Split a finite farmer labor budget equally across occupied slots.
        // Dormant/zero-yield resources retain their share; invalid/empty slots
        // do not. This preserves seasonal ecology shocks without multiplying
        // every farmer into three full-time producers.
        // Cities: city farmers give part of their labor to the town. The
        // product is skipped at 1.0, so without the switch nothing changes.
        let headcount_labor = if inp.farm_labor_factor != 1.0 {
            ac.farmer_count as f32 * inp.farm_labor_factor
        } else {
            ac.farmer_count as f32
        };
        let (labor, productivity) = if inp.slot_curves {
            split_labor_on_slot_curves(inp, headcount_labor, ac.population as f32 * config.per_capita_food)
        } else {
            // Diminishing returns: the labour budget is effective labour on the
            // region's land, concave in the farmers working it.
            let farm_labor =
                effective_farm_labor(headcount_labor, inp.farm_labor_ref, inp.farm_labor_half);
            let productivity = if headcount_labor > 0.0 && inp.farm_labor_ref > 0.0 {
                farm_labor / headcount_labor
            } else {
                1.0
            };
            let labor = allocate_farm_labor(
                &inp.resource_types,
                &inp.resource_yields,
                farm_labor,
                ac.population as f32 * config.per_capita_food,
                inp.subsistence_yield,
            );
            (labor, productivity)
        };
        farm_productivity.push(productivity);
        let slot_labor = labor.slot_labor;
        let mut production = [0.0f32; NUM_CATEGORIES];
        let mut per_good_production = [0.0f32; NUM_GOODS];
        let mut outputs = [0.0f32; 3];
        let mut foraged = 0.0f32;
        if labor.forage_labor > 0.0 {
            foraged = labor.forage_labor * labor.forage_yield;
            per_good_production[SLOT_GRAIN] += foraged;
            production[CAT_FOOD] += foraged;
            conservation.production += foraged as f64;
        }
        forage_output.push(foraged);
        for resource_idx in 0..3 {
            let slot = rt_to_slot(inp.resource_types[resource_idx]);
            if slot >= NUM_GOODS { continue; }
            let mut amount = inp.resource_yields[resource_idx].max(0.0) * slot_labor[resource_idx];
            if let Some(cap) = inp.production_caps[resource_idx] {
                amount = amount.min(cap.max(0.0));
            }
            outputs[resource_idx] = amount;
            per_good_production[slot] += amount;
            production[slot_to_category(slot)] += amount;
            conservation.production += amount as f64;
        }
        slot_output.push(outputs);
        let mut available = production;
        for g in 0..NUM_GOODS {
            available[GOOD_CATEGORY[g]] += inp.stockpile[g];
        }

        // Crafts (2026-10): the city crafts work raw materials on hand (stock
        // and this turn's output, less this tick's merchant departures) into
        // wares, one load of each, up to the crafts' raw demand.
        let mut craft_input = [0.0f32; NUM_GOODS];
        let mut crafted = 0.0f32;
        if inp.craft_raw_demand > 0.0 {
            let departures = hybrid_delivery.and_then(|d| d.departure_debits.get(i));
            let mut on_hand = [0.0f32; NUM_GOODS];
            let mut total = 0.0f32;
            for g in 0..NUM_GOODS {
                if GOOD_CATEGORY[g] != CAT_RAW_MATERIAL {
                    continue;
                }
                let left = departures.map_or(0.0, |d| d[g]);
                on_hand[g] = (inp.stockpile[g] + per_good_production[g] - left).max(0.0);
                total += on_hand[g];
            }
            crafted = inp.craft_raw_demand.min(total);
            if crafted > 0.0 {
                for g in 0..NUM_GOODS {
                    craft_input[g] = on_hand[g] / total * crafted;
                }
                available[CAT_RAW_MATERIAL] = (available[CAT_RAW_MATERIAL] - crafted).max(0.0);
                available[CAT_CRAFT] += crafted;
                per_good_production[SLOT_CRAFTS] += crafted;
                conservation.production += crafted as f64;
                conservation.consumption += crafted as f64;
            }
        }
        craft_output.push(crafted);

        // Demand.
        let mut demand = [
            ac.population as f32 * config.per_capita_food,                // food
            ac.soldier_count as f32 * config.raw_material_per_soldier,    // raw_material
            ac.wealthy_count as f32 * config.luxury_per_wealthy_agent,    // luxury
            inp.craft_demand.max(0.0),                                    // wares
        ];
        if inp.craft_raw_demand > 0.0 {
            demand[CAT_RAW_MATERIAL] += inp.craft_raw_demand;             // cities' crafts
        }

        // Pre-trade prices.
        let mut prices = [0.0f32; NUM_CATEGORIES];
        for c in 0..NUM_CATEGORIES {
            let s = available[c].max(SUPPLY_FLOOR);
            prices[c] = config.base_price * (demand[c] / s);
        }

        // Exportable surplus.
        let mut surplus = [0.0f32; NUM_CATEGORIES];
        for c in 0..NUM_CATEGORIES {
            surplus[c] = (available[c] - demand[c]).max(0.0);
        }

        work.push(RegionWorkState {
            production,
            per_good_production,
            available,
            demand,
            prices,
            surplus,
            imports: [0.0; NUM_CATEGORIES],
            exports: [0.0; NUM_CATEGORIES],
            stockpile: inp.stockpile,
            craft_input,
        });
    }

    // -----------------------------------------------------------------------
    // Phase B: Trade kernel
    //   Abstract path: tatonnement price equilibrium with route allocation.
    //   Hybrid path (M58b): consume delivery buffer from merchant mobility.
    // -----------------------------------------------------------------------

    // Shared outputs from Phase B consumed by Phase C and signal derivation.
    let mut per_good_imports: Vec<[f32; NUM_GOODS]> = vec![[0.0; NUM_GOODS]; n_regions];
    let mut per_good_exports: Vec<[f32; NUM_GOODS]> = vec![[0.0; NUM_GOODS]; n_regions];
    let mut upstream_sources: Vec<UpstreamSource> = Vec::new();
    // Per-good net mobility (hybrid only): imports + returns - departures per region.
    let mut per_good_net_mobility: Vec<[f32; NUM_GOODS]> = vec![[0.0; NUM_GOODS]; n_regions];

    // Abstract-path structures (needed for merchant_margin / merchant_trade_income in abstract mode).
    let mut boundary_pair_counts: Vec<u16> = vec![0u16; n_regions];
    let mut route_works: Vec<RouteWork> = Vec::new();
    let mut origin_route_ranges: Vec<(usize, usize)> = vec![(0, 0); n_regions];

    // M58b: Snapshot work state before hybrid mutations for oracle shadow.
    // The clone captures Phase A output (production, demand, surplus, prices)
    // with clean imports/exports. Needed even without routes because oracle
    // food_sufficiency only requires production + demand (from Phase A).
    // The allocation step is skipped when routes are empty, but food_suff
    // and margins (zero without routes) are still computed.
    let oracle_work_snapshot = if hybrid_delivery.is_some() {
        Some(work.clone())
    } else {
        None
    };

    // M58b: Per-region per-good transit decay accumulator (hybrid only).
    let mut transit_decay_by_region: Option<Vec<[f32; NUM_GOODS]>> = if hybrid_delivery.is_some() {
        Some(vec![[0.0; NUM_GOODS]; n_regions])
    } else {
        None
    };

    if let Some(delivery) = hybrid_delivery {
        // -------------------------------------------------------------------
        // Hybrid path: consume delivery buffer
        // -------------------------------------------------------------------

        // Apply arrival imports with transit decay.
        for rec in &delivery.arrival_imports_raw {
            let dest = rec.dest_region as usize;
            let slot = rec.good_slot as usize;
            if dest < n_regions && slot < NUM_GOODS {
                let shipped = rec.qty;
                let decay_rate = TRANSIT_DECAY[slot];
                let delivered = shipped * (1.0 - decay_rate);
                let decay_amount = shipped - delivered;
                conservation.transit_loss += decay_amount as f64;
                per_good_imports[dest][slot] += delivered;
                if let Some(ref mut tdr) = transit_decay_by_region {
                    tdr[dest][slot] += decay_amount;
                }
            }
        }

        // Populate category-level imports/exports on work state for price computation.
        for ri in 0..n_regions {
            // Imports: aggregate per-good imports into categories.
            for g in 0..NUM_GOODS {
                let cat = GOOD_CATEGORY[g];
                work[ri].imports[cat] += per_good_imports[ri][g];
            }
            // Exports: departure debits aggregated into categories.
            if ri < delivery.departure_debits.len() {
                for g in 0..NUM_GOODS {
                    let cat = GOOD_CATEGORY[g];
                    work[ri].exports[cat] += delivery.departure_debits[ri][g];
                }
            }
        }

        // Compute in_transit_delta = departures - arrivals - returns.
        let total_departures: f64 = delivery.departure_debits.iter()
            .flat_map(|arr| arr.iter())
            .map(|&v| v as f64)
            .sum();
        let total_arrivals_raw: f64 = delivery.arrival_imports_raw.iter()
            .map(|rec| rec.qty as f64)
            .sum();
        let total_returns: f64 = delivery.return_credits.iter()
            .flat_map(|arr| arr.iter())
            .map(|&v| v as f64)
            .sum();
        conservation.in_transit_delta = Some(total_departures - total_arrivals_raw - total_returns);

        // Build upstream sources from delivery provenance.
        {
            let mut ordinal_counter: u16 = 0;
            let mut last_dest: Option<u16> = None;
            for &(dest_id, src_id) in &delivery.inbound_pairs {
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

        // Compute per-good net mobility for stockpile update.
        // net_mobility[ri][g] = imports[ri][g] + return_credits[ri][g] - departure_debits[ri][g]
        for ri in 0..n_regions {
            for g in 0..NUM_GOODS {
                let imports_g = per_good_imports[ri][g];
                let returns_g = if ri < delivery.return_credits.len() {
                    delivery.return_credits[ri][g]
                } else {
                    0.0
                };
                let departures_g = if ri < delivery.departure_debits.len() {
                    delivery.departure_debits[ri][g]
                } else {
                    0.0
                };
                per_good_net_mobility[ri][g] = imports_g + returns_g - departures_g;
                work[ri].available[GOOD_CATEGORY[g]] += returns_g;
            }
        }

        // Boundary pair counts: use route topology (same source as abstract path).
        // This ensures trade_route_count reflects available routes, not realized arrivals,
        // which can be zero on turns where merchants are in-transit but haven't arrived yet.
        for r in routes {
            let oidx = if (r.origin_region_id as usize) < region_id_to_idx.len() {
                region_id_to_idx[r.origin_region_id as usize]
            } else {
                usize::MAX
            };
            if oidx < n_regions {
                boundary_pair_counts[oidx] += 1;
            }
        }
    } else {
        // -------------------------------------------------------------------
        // Abstract path: tatonnement trade allocation (unchanged)
        // -------------------------------------------------------------------

        // Build sorted route list and per-origin boundary pair counts.
        let mut sorted_routes: Vec<(u16, u16, bool)> = routes
            .iter()
            .map(|r| (r.origin_region_id, r.dest_region_id, r.is_river))
            .collect();
        sorted_routes.sort_by_key(|&(o, d, _)| (o, d));

        for &(origin_id, _, _) in &sorted_routes {
            let oidx = region_id_to_idx[origin_id as usize];
            if oidx < n_regions {
                boundary_pair_counts[oidx] += 1;
            }
        }

        // Build RouteWork entries with transport costs.
        route_works = Vec::with_capacity(sorted_routes.len());
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
        {
            let mut origin_groups: Vec<(usize, usize, usize)> = Vec::new();
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
            for &(oidx, start, count) in &origin_groups {
                origin_route_ranges[oidx] = (start, start + count);
            }
        }

        // Tatonnement loop (delegated to shared helper).
        run_abstract_allocation(
            &mut work, agent_counts, &mut route_works, &origin_route_ranges, config,
        );

        // Track inbound sources from final-pass positive flows.
        let mut inbound_pairs: Vec<(u16, u16)> = Vec::new();
        for rw in route_works.iter() {
            let has_flow = rw.flow.iter().any(|&f| f > 0.0);
            if has_flow {
                let dest_id = region_inputs[rw.dest_idx].region_id;
                let origin_id = region_inputs[rw.origin_idx].region_id;
                inbound_pairs.push((dest_id, origin_id));
            }
        }
        inbound_pairs.sort();
        inbound_pairs.dedup();

        // Build upstream_sources output.
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

        let (imports, exports, transit_loss) = abstract_good_flows(&work, &route_works);
        per_good_imports = imports;
        per_good_exports = exports;
        conservation.transit_loss += transit_loss;
    }

    // -----------------------------------------------------------------------
    // Oracle shadow: run abstract allocation on cloned work state (hybrid only)
    // -----------------------------------------------------------------------

    let (oracle_trade_volume, oracle_margins, oracle_food_sufficiency):
        (Option<Vec<[f32; NUM_CATEGORIES]>>, Option<Vec<f32>>, Option<Vec<f32>>) =
        if let Some(mut shadow_work) = oracle_work_snapshot {
            // Build route structures for abstract allocation (same logic as abstract path).
            let mut sorted_routes: Vec<(u16, u16, bool)> = routes
                .iter()
                .map(|r| (r.origin_region_id, r.dest_region_id, r.is_river))
                .collect();
            sorted_routes.sort_by_key(|&(o, d, _)| (o, d));

            let mut shadow_route_works: Vec<RouteWork> = Vec::with_capacity(sorted_routes.len());
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
                shadow_route_works.push(RouteWork {
                    origin_idx: oidx,
                    dest_idx: didx,
                    transport_cost: tc,
                    flow: [0.0; NUM_CATEGORIES],
                });
            }

            let mut shadow_origin_ranges: Vec<(usize, usize)> = vec![(0, 0); n_regions];
            {
                let mut origin_groups: Vec<(usize, usize, usize)> = Vec::new();
                if !shadow_route_works.is_empty() {
                    let mut cur_origin = shadow_route_works[0].origin_idx;
                    let mut start = 0;
                    for (i, rw) in shadow_route_works.iter().enumerate() {
                        if rw.origin_idx != cur_origin {
                            origin_groups.push((cur_origin, start, i - start));
                            cur_origin = rw.origin_idx;
                            start = i;
                        }
                    }
                    origin_groups.push((cur_origin, start, shadow_route_works.len() - start));
                }
                for &(oidx, start, count) in &origin_groups {
                    shadow_origin_ranges[oidx] = (start, start + count);
                }
            }

            // Run tatonnement on the shadow state.
            run_abstract_allocation(
                &mut shadow_work, agent_counts, &mut shadow_route_works,
                &shadow_origin_ranges, config,
            );

            // Collect per-region import totals by category.
            let vols: Vec<[f32; NUM_CATEGORIES]> = shadow_work.iter()
                .map(|w| w.imports)
                .collect();

            // Oracle post-trade prices (same formula as realized Phase C).
            let mut shadow_post_trade_prices = vec![[0.0f32; NUM_CATEGORIES]; n_regions];
            for ri in 0..n_regions {
                let sw = &shadow_work[ri];
                for c in 0..NUM_CATEGORIES {
                    let supply = (sw.available[c] - sw.exports[c] + sw.imports[c]).max(SUPPLY_FLOOR);
                    shadow_post_trade_prices[ri][c] = config.base_price * (sw.demand[c] / supply);
                }
            }

            // Oracle margins per region (same formula as realized abstract-path margin).
            let mut margins = vec![0.0f32; n_regions];
            for ri in 0..n_regions {
                let (rstart, rend) = shadow_origin_ranges[ri];
                let route_count = rend - rstart;
                if route_count > 0 {
                    let mut total_raw_margin = 0.0f32;
                    for rw_idx in rstart..rend {
                        let dest_idx = shadow_route_works[rw_idx].dest_idx;
                        for c in 0..NUM_CATEGORIES {
                            let delta = (shadow_post_trade_prices[dest_idx][c]
                                - shadow_post_trade_prices[ri][c]).max(0.0);
                            total_raw_margin += delta;
                        }
                    }
                    let avg = total_raw_margin / route_count as f32;
                    margins[ri] = (avg / config.merchant_margin_normalizer).clamp(0.0, 1.0);
                }
            }

            // Use the same per-good stock-flow decomposition as the realized
            // abstract path, including all occupied resource slots and stocks.
            let (oracle_per_good_imports, oracle_per_good_exports, _) =
                abstract_good_flows(&shadow_work, &shadow_route_works);

            let mut food_suff = vec![0.0f32; n_regions];
            for ri in 0..n_regions {
                let sw = &shadow_work[ri];
                let food_demand = sw.demand[CAT_FOOD];

                // Step 1: stockpile + production - exports + imports.
                let mut shadow_stockpile = region_inputs[ri].stockpile;
                for g in 0..NUM_GOODS {
                    let new_val = shadow_stockpile[g] + sw.per_good_production[g]
                        - oracle_per_good_exports[ri][g] + oracle_per_good_imports[ri][g] - sw.craft_input[g];
                    shadow_stockpile[g] = new_val.max(0.0);
                }

                // Step 2: food_sufficiency from post-lifecycle stockpile.
                let total_food: f32 = (0..NUM_GOODS)
                    .filter(|&g| IS_FOOD[g])
                    .map(|g| shadow_stockpile[g])
                    .sum();
                let denom = food_demand.max(SUPPLY_FLOOR);
                food_suff[ri] = (total_food / denom).clamp(0.0, 2.0);
            }

            (Some(vols), Some(margins), Some(food_suff))
        } else {
            (None, None, None)
        };

    // -----------------------------------------------------------------------
    // Phase C: Post-trade prices
    // -----------------------------------------------------------------------

    let mut post_trade_prices: Vec<[f32; NUM_CATEGORIES]> = vec![[0.0; NUM_CATEGORIES]; n_regions];
    for ri in 0..n_regions {
        let w = &work[ri];
        for c in 0..NUM_CATEGORIES {
            let supply = (w.available[c] - w.exports[c] + w.imports[c]).max(SUPPLY_FLOOR);
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

        // Step 1: Accumulate stockpile.
        // Hybrid: old + production + net_mobility (imports + returns - departures)
        // Abstract: old + production - exports + imports
        let mut stockpile = w.stockpile;
        for g in 0..NUM_GOODS {
            let new_val = if hybrid_delivery.is_some() {
                stockpile[g] + w.per_good_production[g] + per_good_net_mobility[ri][g] - w.craft_input[g]
            } else {
                stockpile[g] + w.per_good_production[g] - per_good_exports[ri][g]
                    + per_good_imports[ri][g] - w.craft_input[g]
            };
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

        // Step 3b (crafts): the people use wares up to their demand.
        let craft_demand = w.demand[CAT_CRAFT];
        let craft_sufficiency = if craft_demand > 0.0 {
            (stockpile[SLOT_CRAFTS] / craft_demand).clamp(0.0, 2.0)
        } else {
            0.0
        };
        if craft_demand > 0.0 && stockpile[SLOT_CRAFTS] > 0.0 {
            let used = craft_demand.min(stockpile[SLOT_CRAFTS]);
            stockpile[SLOT_CRAFTS] -= used;
            conservation.consumption += used as f64;
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
        // Weight the scarcity return by what farmers actually produced. A
        // failed harvest supplies no goods to sell and earns a neutral signal.
        let total_production: f32 = w.production.iter().sum();
        let farmer_income_modifier = if total_production > 0.0 {
            let mut weighted_income = 0.0;
            for c in 0..NUM_CATEGORIES {
                let post_supply = (w.available[c] - w.exports[c] + w.imports[c]).max(SUPPLY_FLOOR);
                weighted_income += w.production[c] * (w.demand[c] / post_supply);
            }
            (weighted_income / total_production)
                .clamp(config.farmer_income_modifier_floor, config.farmer_income_modifier_cap)
        } else {
            1.0
        };

        // merchant_margin and merchant_trade_income: mode-dependent derivation.
        let (merchant_margin, merchant_trade_income) = if let Some(delivery) = hybrid_delivery {
            // Hybrid path: derive from realized delivery volumes.
            // merchant_margin: average margin from deliveries sourced from this region.
            let mut total_raw_margin = 0.0f32;
            let mut delivery_count = 0u32;
            for rec in &delivery.arrival_imports_raw {
                if rec.source_region as usize == ri {
                    let dest = rec.dest_region as usize;
                    if dest < n_regions {
                        let g = rec.good_slot as usize;
                        if g < NUM_GOODS {
                            let cat = GOOD_CATEGORY[g];
                            let delta = (post_trade_prices[dest][cat] - post_trade_prices[ri][cat]).max(0.0);
                            total_raw_margin += delta;
                            delivery_count += 1;
                        }
                    }
                }
            }
            let margin = if delivery_count > 0 {
                let avg = total_raw_margin / delivery_count as f32;
                (avg / config.merchant_margin_normalizer).clamp(0.0, 1.0)
            } else {
                0.0
            };

            // merchant_trade_income: total delivered value / merchant_count.
            let trade_income = if ac.merchant_count > 0 {
                let mut total_delivered_value = 0.0f32;
                for rec in &delivery.arrival_imports_raw {
                    if rec.source_region as usize == ri {
                        let g = rec.good_slot as usize;
                        if g < NUM_GOODS {
                            let dest = rec.dest_region as usize;
                            if dest < n_regions {
                                let delivered = rec.qty * (1.0 - TRANSIT_DECAY[g]);
                                let cat = GOOD_CATEGORY[g];
                                let margin_val = (post_trade_prices[dest][cat]
                                    - post_trade_prices[ri][cat]).max(0.0);
                                total_delivered_value += delivered * margin_val;
                            }
                        }
                    }
                }
                total_delivered_value / ac.merchant_count as f32
            } else {
                0.0
            };

            (margin, trade_income)
        } else {
            // Abstract path: existing tatonnement-based derivation.
            let (rstart, rend) = origin_route_ranges[ri];
            let route_count = rend - rstart;
            let margin = if route_count > 0 {
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

            let trade_income = if ac.merchant_count > 0 && route_count > 0 {
                let mut total_arbitrage = 0.0f32;
                for rw_idx in rstart..rend {
                    let dest_idx = route_works[rw_idx].dest_idx;
                    for c in 0..NUM_CATEGORIES {
                        let margin_val = (post_trade_prices[dest_idx][c] - post_trade_prices[ri][c]).max(0.0);
                        total_arbitrage += route_works[rw_idx].flow[c] * margin_val;
                    }
                }
                total_arbitrage / ac.merchant_count as f32
            } else {
                0.0
            };

            (margin, trade_income)
        };

        // trade_route_count = boundary pair count before zero-flow pruning.
        let trade_route_count = boundary_pair_counts[ri];

        let mut market_supply = [0.0f32; NUM_CATEGORIES];
        for c in 0..NUM_CATEGORIES {
            market_supply[c] = (w.available[c] - w.exports[c] + w.imports[c]).max(0.0);
        }
        region_results.push(EconomyRegionResult {
            region_id: inp.region_id,
            stockpile,
            farmer_income_modifier,
            food_sufficiency,
            merchant_margin,
            merchant_trade_income,
            trade_route_count,
            market_demand: w.demand,
            market_supply,
            farm_productivity: farm_productivity[ri],
            craft_output: craft_output[ri],
            craft_sufficiency,
            slot_output: slot_output[ri],
            forage_output: forage_output[ri],
        });

        // Step 7: Derive observability.
        // imports_by_category: delivered quantities after good-specific transit decay.
        let imports_food = w.imports[CAT_FOOD];
        let imports_raw_material = w.imports[CAT_RAW_MATERIAL];
        let imports_luxury = w.imports[CAT_LUXURY];
        let imports_craft = w.imports[CAT_CRAFT];

        // stockpile_levels: post-lifecycle goods aggregated by category.
        let mut stockpile_food = 0.0f32;
        let mut stockpile_raw_material = 0.0f32;
        let mut stockpile_luxury = 0.0f32;
        let mut stockpile_craft = 0.0f32;
        for g in 0..NUM_GOODS {
            match GOOD_CATEGORY[g] {
                CAT_FOOD => stockpile_food += stockpile[g],
                CAT_RAW_MATERIAL => stockpile_raw_material += stockpile[g],
                CAT_LUXURY => stockpile_luxury += stockpile[g],
                CAT_CRAFT => stockpile_craft += stockpile[g],
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
            imports_craft,
            stockpile_food,
            stockpile_raw_material,
            stockpile_luxury,
            stockpile_craft,
            import_share,
            trade_dependent,
        });
    }

    // -----------------------------------------------------------------------
    // Phase D: Civ fiscal + conservation (per-civ)
    // -----------------------------------------------------------------------

    // Accumulate per-civ average food_sufficiency from region results for tithe food gate.
    // Matches Python H-2: tithe_scale = min(avg_food_suff / TITHE_FOOD_GATE, 1.0)
    let mut civ_food_suff_sum = vec![0.0f32; n_civs];
    let mut civ_region_count = vec![0u32; n_civs];
    for (ri, rr) in region_results.iter().enumerate() {
        if ri < region_civ_owner.len() {
            let civ = region_civ_owner[ri] as usize;
            if civ < n_civs {
                civ_food_suff_sum[civ] += rr.food_sufficiency;
                civ_region_count[civ] += 1;
            }
        }
    }

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

        // H-2: Food gate on tithe — reduce collection during famines.
        let avg_food_suff = if civ_region_count[civ_idx] > 0 {
            civ_food_suff_sum[civ_idx] / civ_region_count[civ_idx] as f32
        } else {
            1.0 // no regions → default to full tithe (matches Python default)
        };
        let tithe_scale = if avg_food_suff < TITHE_FOOD_GATE {
            avg_food_suff / TITHE_FOOD_GATE
        } else {
            1.0
        };

        let treasury_tax = config.tax_rate * mw;
        let tithe_base = mw * tithe_scale;
        let priest_tithe_share = TITHE_RATE * tithe_base / (pc.max(1) as f32);

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
        oracle_trade_volume,
        oracle_margins,
        oracle_food_sufficiency,
        transit_decay_by_region,
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
            resource_types: [0, 255, 255],
            resource_yields: [1.0, 0.0, 0.0],
            production_caps: [None; 3],
            stockpile: [0.0; NUM_GOODS],
            subsistence_yield: 0.0,
            farm_labor_factor: 1.0,
            craft_raw_demand: 0.0,
            craft_demand: 0.0,
            farm_labor_ref: 0.0,
            farm_labor_half: 0.0,
            slot_curves: false,
            slot_labor_ref: [0.0; 3],
            slot_labor_half: [0.0; 3],
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
            &[0u8], &config, 1.0, false, None,
        );

        assert_eq!(out.region_results.len(), 1);
        assert_eq!(out.civ_results.len(), 1);
        assert!((out.conservation.production - 50.0).abs() < 0.01);
        // Demand and post-trade supply by category, as the planner reads them.
        let rr = &out.region_results[0];
        assert_eq!(rr.market_demand, [50.0, 3.0, 0.4, 0.0]);
        assert!((rr.market_supply[CAT_FOOD] - 50.0).abs() < 1e-4);
        assert_eq!(rr.market_supply[CAT_RAW_MATERIAL], 0.0);
    }

    fn city_market_region(farm_labor_factor: f32, craft_raw_demand: f32) -> EconomyRegionInput {
        EconomyRegionInput {
            region_id: 0,
            terrain: 0,
            storage_population: 40,
            resource_types: [0, 255, 255],
            resource_yields: [1.0, 0.0, 0.0],
            production_caps: [None; 3],
            stockpile: [0.0; NUM_GOODS],
            subsistence_yield: 0.0,
            farm_labor_factor,
            craft_raw_demand,
            craft_demand: 0.0,
            farm_labor_ref: 0.0,
            farm_labor_half: 0.0,
            slot_curves: false,
            slot_labor_ref: [0.0; 3],
            slot_labor_half: [0.0; 3],
        }
    }

    fn run_one(region: EconomyRegionInput) -> EconomyOutput {
        let agents = vec![RegionAgentCounts {
            population: 40, farmer_count: 20, soldier_count: 4, merchant_count: 2, wealthy_count: 0,
        }];
        tick_economy_core(
            &[region], &agents, &[], &[0.0], &[0], 1, &[0u8], &EconomyConfig::default(), 1.0, false, None,
        )
    }

    #[test]
    fn test_city_farmers_give_part_of_their_labor_to_the_town() {
        // 20 farmers at yield 1 feed 40 people (demand 20) exactly; at a
        // labor factor of 0.75 they grow 15 and the region is short.
        let fed = run_one(city_market_region(1.0, 0.0));
        let city = run_one(city_market_region(0.75, 0.0));
        assert!((fed.conservation.production - 20.0).abs() < 1e-4);
        assert!((city.conservation.production - 15.0).abs() < 1e-4);
        assert!((fed.region_results[0].food_sufficiency - 1.0).abs() < 1e-5);
        assert!((city.region_results[0].food_sufficiency - 0.75).abs() < 1e-5);
    }

    #[test]
    fn test_city_crafts_add_raw_material_demand() {
        let out = run_one(city_market_region(1.0, 1.5));
        assert!((out.region_results[0].market_demand[CAT_RAW_MATERIAL] - (4.0 * 0.3 + 1.5)).abs() < 1e-5);
    }

    /// A city region with `ore` in stock, crafts able to work `craft_raw`
    /// and its people wanting `wares` (no farmers, so no harvest).
    fn crafts_region(ore: f32, craft_raw: f32, wares: f32) -> EconomyOutput {
        let mut r = city_market_region(1.0, craft_raw);
        r.craft_demand = wares;
        r.stockpile[SLOT_ORE] = ore;
        let agents = vec![RegionAgentCounts {
            population: 40, farmer_count: 0, soldier_count: 0, merchant_count: 0, wealthy_count: 0,
        }];
        tick_economy_core(
            &[r], &agents, &[], &[0.0], &[0], 1, &[0u8], &EconomyConfig::default(), 1.0, false, None,
        )
    }

    #[test]
    fn test_city_crafts_work_raw_materials_into_wares_the_people_use() {
        // Ore 10, crafts for 3, people wanting 2: 3 wares made from 3 ore; 2
        // used, 1 left (less 1% wear); sufficiency 3 / 2.
        let out = crafts_region(10.0, 3.0, 2.0);
        let rr = &out.region_results[0];
        assert!((rr.craft_output - 3.0).abs() < 1e-6);
        assert!((rr.craft_sufficiency - 1.5).abs() < 1e-6);
        assert!((rr.stockpile[SLOT_ORE] - 7.0).abs() < 1e-5);
        assert!((rr.stockpile[SLOT_CRAFTS] - 0.99).abs() < 1e-5);
        assert_eq!(rr.market_demand[CAT_CRAFT], 2.0);
        // Conservation: 3 wares made, 3 ore and 2 wares used.
        assert!((out.conservation.production - 3.0).abs() < 1e-6);
        assert!((out.conservation.consumption - 5.0).abs() < 1e-6);
        assert_eq!(out.conservation.clamp_floor_loss, 0.0);
        // Raw materials short: the crafts make what the ore allows.
        let short = crafts_region(1.0, 3.0, 2.0);
        assert!((short.region_results[0].craft_output - 1.0).abs() < 1e-6);
        assert_eq!(short.region_results[0].stockpile[SLOT_ORE], 0.0);
        assert!((short.region_results[0].craft_sufficiency - 0.5).abs() < 1e-6);
        // No crafts, no wares; no demand, no sufficiency.
        let none = crafts_region(10.0, 0.0, 0.0);
        assert_eq!(none.region_results[0].craft_output, 0.0);
        assert_eq!(none.region_results[0].craft_sufficiency, 0.0);
        assert_eq!(none.region_results[0].stockpile[SLOT_ORE], 10.0);
    }

    #[test]
    fn test_crafts_leave_farmer_income_and_hybrid_departures_alone() {
        // Farmer income is the price of what farmers grow, not of wares.
        let run = |craft_raw: f32| {
            let mut r = city_market_region(1.0, craft_raw);
            r.resource_types = [GRAIN_RT, ORE_RT, 255];
            r.resource_yields = [1.0, 1.0, 0.0];
            r.craft_demand = 1.0;
            run_one(r)
        };
        let (plain, crafty) = (run(0.0), run(2.0));
        assert!(crafty.region_results[0].craft_output > 0.0);
        let (a, b) = (plain.region_results[0].farmer_income_modifier, crafty.region_results[0].farmer_income_modifier);
        assert!(b >= a, "the crafts' raw demand can only raise the ore price: {a} {b}");
        // Ore a merchant has taken out this tick is not worked into wares.
        let mut r = city_market_region(1.0, 5.0);
        r.stockpile[SLOT_ORE] = 4.0;
        let mut buf = crate::merchant::DeliveryBuffer::new(1);
        buf.record_departure(0, SLOT_ORE, 3.0);
        let delivery = HybridDeliveryInput::from_buffer(&buf, 1);
        let agents = vec![RegionAgentCounts {
            population: 40, farmer_count: 0, soldier_count: 0, merchant_count: 1, wealthy_count: 0,
        }];
        let out = tick_economy_core(
            &[r], &agents, &[], &[0.0], &[0], 1, &[0u8], &EconomyConfig::default(), 1.0, false, Some(&delivery),
        );
        assert!((out.region_results[0].craft_output - 1.0).abs() < 1e-6);
        assert_eq!(out.region_results[0].stockpile[SLOT_ORE], 0.0);
        assert_eq!(out.conservation.clamp_floor_loss, 0.0);
    }

    #[test]
    fn test_without_the_city_inputs_every_output_keeps_its_bits() {
        // factor 1.0 and no craft demand are the switch-off inputs: the
        // region result is bit-identical to a run that never had the fields.
        let a = run_one(city_market_region(1.0, 0.0));
        let b = run_one(city_market_region(1.0, 0.0));
        let (ra, rb) = (&a.region_results[0], &b.region_results[0]);
        assert_eq!(ra.stockpile.map(f32::to_bits), rb.stockpile.map(f32::to_bits));
        assert_eq!(ra.food_sufficiency.to_bits(), rb.food_sufficiency.to_bits());
        assert_eq!(ra.farmer_income_modifier.to_bits(), rb.farmer_income_modifier.to_bits());
        assert_eq!(ra.market_demand[CAT_RAW_MATERIAL].to_bits(), (4.0f32 * 0.3).to_bits());
    }

    #[test]
    fn test_effective_farm_labor_is_concave_and_exact_at_the_reference() {
        // Reference 20, half-saturation 20: the curve 40 L / (L + 20).
        assert_eq!(effective_farm_labor(20.0, 20.0, 20.0), 20.0);
        assert!((effective_farm_labor(10.0, 20.0, 20.0) - 40.0 / 3.0).abs() < 1e-5); // +33% each
        assert!((effective_farm_labor(40.0, 20.0, 20.0) - 80.0 / 3.0).abs() < 1e-5); // -33% each
        assert!(effective_farm_labor(1e6, 20.0, 20.0) < 40.0); // the land's ceiling
        // No curve, or nobody farming: the labour itself, bit for bit.
        assert_eq!(effective_farm_labor(17.3, 0.0, 0.0).to_bits(), 17.3f32.to_bits());
        assert_eq!(effective_farm_labor(0.0, 20.0, 20.0), 0.0);
    }

    #[test]
    fn test_crowded_land_produces_less_per_farmer_and_empty_land_more() {
        let with_curve = |farm_labor_ref: f32| {
            let mut r = city_market_region(1.0, 0.0);
            r.farm_labor_ref = farm_labor_ref;
            r.farm_labor_half = farm_labor_ref;
            run_one(r)
        };
        let base = run_one(city_market_region(1.0, 0.0));
        // 20 farmers at their reference: today's output, productivity 1.
        let at_ref = with_curve(20.0);
        assert!((at_ref.conservation.production - base.conservation.production).abs() < 1e-4);
        assert!((at_ref.region_results[0].farm_productivity - 1.0).abs() < 1e-6);
        // Land for 10: crowded, 20 farmers grow 20 x 20 / 30.
        let crowded = with_curve(10.0);
        assert!((crowded.conservation.production - 40.0 / 3.0).abs() < 1e-4);
        assert!((crowded.region_results[0].farm_productivity - 2.0 / 3.0).abs() < 1e-5);
        assert!(crowded.region_results[0].food_sufficiency < 1.0);
        // Land for 40: each of the 20 grows 80 / 60.
        let roomy = with_curve(40.0);
        assert!((roomy.region_results[0].farm_productivity - 4.0 / 3.0).abs() < 1e-5);
        // Without the columns the result keeps constant returns.
        assert_eq!(base.region_results[0].farm_productivity, 1.0);
    }

    const ORE_RT: u8 = 5;
    const PRECIOUS_RT: u8 = 6;
    const GRAIN_RT: u8 = 0;
    const FISH_RT: u8 = 3;

    /// Grain and ore, 40 farmers, 10 people (demand 5, so no food-first
    /// shift), the farm curve at reference 20.
    fn mine_region(slot_curves: bool, ore_ref: f32) -> EconomyRegionInput {
        let mut r = city_market_region(1.0, 0.0);
        r.resource_types = [GRAIN_RT, ORE_RT, 255];
        r.resource_yields = [1.0, 1.0, 0.0];
        r.farm_labor_ref = 20.0;
        r.farm_labor_half = 20.0;
        r.slot_curves = slot_curves;
        r.slot_labor_ref = [0.0, ore_ref, 0.0];
        r.slot_labor_half = [0.0, ore_ref, 0.0];
        r
    }

    fn run_mine(region: EconomyRegionInput) -> EconomyOutput {
        let agents = vec![RegionAgentCounts {
            population: 10, farmer_count: 40, soldier_count: 0, merchant_count: 0, wealthy_count: 0,
        }];
        tick_economy_core(
            &[region], &agents, &[], &[0.0], &[0], 1, &[0u8], &EconomyConfig::default(), 1.0, false, None,
        )
    }

    #[test]
    fn test_mines_saturate_on_their_deposit_not_on_the_farmland() {
        // One curve for all farm labour: 40 farmers do 40 x 40 / 60 = 26.7
        // effective labour, half on each slot.
        let one = run_mine(mine_region(false, 0.0));
        let grain = one.region_results[0].stockpile[SLOT_GRAIN] / (1.0 - STORAGE_DECAY[SLOT_GRAIN]);
        assert!((one.conservation.production - 80.0 / 3.0).abs() < 1e-3);
        assert!(grain > 0.0);
        // Separate curves: the 20 field hands work the farmland at its
        // reference (20) and the 20 miners a deposit of reference 40
        // (20 x 80 / 60 = 26.7).
        let two = run_mine(mine_region(true, 40.0));
        assert!((two.conservation.production - (20.0 + 80.0 / 3.0)).abs() < 1e-3);
        assert!((two.region_results[0].stockpile[SLOT_ORE] - 80.0 / 3.0).abs() < 1e-3);
        let fp = two.region_results[0].farm_productivity;
        assert!((fp - (20.0 + 80.0 / 3.0) / 40.0).abs() < 1e-5, "{fp}");
        // A small deposit (reference 5) saturates: 20 x 10 / 25 = 8.
        let small = run_mine(mine_region(true, 5.0));
        assert!((small.region_results[0].stockpile[SLOT_ORE] - 8.0).abs() < 1e-3);
        // A slot without its own curve (reference 0) keeps constant returns.
        let free = run_mine(mine_region(true, 0.0));
        assert!((free.region_results[0].stockpile[SLOT_ORE] - 20.0).abs() < 1e-3);
    }

    #[test]
    fn test_farm_labor_for_effective_inverts_the_curve() {
        for e in [0.5f32, 5.0, 19.0, 30.0, 39.0] {
            let l = farm_labor_for_effective(e, 20.0, 20.0);
            assert!((effective_farm_labor(l, 20.0, 20.0) - e).abs() < 1e-3, "{e} {l}");
        }
        assert_eq!(farm_labor_for_effective(40.0, 20.0, 20.0), f32::INFINITY, "the land's ceiling");
        assert_eq!(farm_labor_for_effective(7.5, 0.0, 0.0), 7.5);
    }

    #[test]
    fn test_food_first_reads_the_food_need_through_the_farm_curve() {
        // Grain and ore, 40 farmers, demand 25 at yield 1: 25 effective food
        // labour on a curve of reference 20 takes 25 x 20 / 15 = 33.3
        // farmers, more than the 25 at constant returns (ore keeps its 5).
        let types = [GRAIN_RT, ORE_RT, 255];
        let yields = [1.0, 1.0, 0.0];
        let flat = food_first_slot_labor(&types, &yields, 40.0, 25.0, 20.0);
        assert!((flat[0] - 25.0).abs() < 1e-4);
        let curved = food_first_slot_labor_curved(&types, &yields, 40.0, 25.0, 20.0, (20.0, 20.0));
        assert!((curved[0] - 100.0 / 3.0).abs() < 1e-3, "{curved:?}");
        assert!((curved[1] - 20.0 / 3.0).abs() < 1e-3, "{curved:?}");
        // Demand 30 would take 60 farmers: the food slot gets all but ore's
        // floor (40 - 0.25 x 20).
        let curved = food_first_slot_labor_curved(&types, &yields, 40.0, 30.0, 20.0, (20.0, 20.0));
        assert!((curved[0] - 35.0).abs() < 1e-4, "{curved:?}");
        // (0, 0) is the plain split, bit for bit.
        let plain = food_first_slot_labor_curved(&types, &yields, 40.0, 25.0, 20.0, (0.0, 0.0));
        assert_eq!(plain.map(f32::to_bits), flat.map(f32::to_bits));
    }

    #[test]
    fn test_farm_labor_without_foraging_is_the_food_first_split() {
        let types = [GRAIN_RT, ORE_RT, 255];
        let yields = [1.0, 2.0, 0.0];
        let labor = allocate_farm_labor(&types, &yields, 40.0, 30.0, 0.36);
        assert_eq!(labor.slot_labor, food_first_slot_labor(&types, &yields, 40.0, 30.0, 20.0));
        assert_eq!(labor.forage_labor, 0.0);
        // A food slot that yields, however little, rules foraging out.
        let labor = allocate_farm_labor(&types, &[0.01, 2.0, 0.0], 40.0, 30.0, 0.36);
        assert_eq!(labor.forage_labor, 0.0);
    }

    #[test]
    fn test_farm_labor_forages_without_a_food_slot() {
        // Ore + precious, 30 farmers, 10 agents' demand 5: foraging takes the
        // food share (10) at least, up to what covers demand.
        let types = [ORE_RT, PRECIOUS_RT, 255];
        let labor = allocate_farm_labor(&types, &[1.0, 1.0, 0.0], 30.0, 5.0, 0.25);
        // needed = 5 / 0.25 = 20; max = 30 - 0.25 * 10 * 2 = 25.
        assert!((labor.forage_labor - 20.0).abs() < 1e-5);
        assert!((labor.slot_labor[0] - 5.0).abs() < 1e-5);
        assert!((labor.slot_labor[1] - 5.0).abs() < 1e-5);
        assert_eq!(labor.slot_labor[2], 0.0);
        assert_eq!(labor.forage_yield, 0.25);
        // High demand: every non-food slot keeps a quarter of its equal share.
        let labor = allocate_farm_labor(&types, &[1.0, 1.0, 0.0], 30.0, 500.0, 0.25);
        assert!((labor.forage_labor - 25.0).abs() < 1e-5);
        assert!((labor.slot_labor[0] - 2.5).abs() < 1e-5);
        // No valid slot at all: everyone forages.
        let labor = allocate_farm_labor(&[255; 3], &[0.0; 3], 12.0, 1.0, 0.25);
        assert_eq!(labor.forage_labor, 12.0);
        // Labor is conserved.
        let labor = allocate_farm_labor(&types, &[1.0, 1.0, 0.0], 30.0, 9.0, 0.3);
        let total: f32 = labor.slot_labor.iter().sum::<f32>() + labor.forage_labor;
        assert!((total - 30.0).abs() < 1e-4);
    }

    #[test]
    fn test_farm_labor_forages_on_barren_food_slots() {
        // Suspended grain (locusts) and fish: no food slot yields, so the food
        // labor forages; ore keeps its floor.
        let types = [GRAIN_RT, FISH_RT, ORE_RT];
        let labor = allocate_farm_labor(&types, &[0.0, 0.0, 2.0], 30.0, 100.0, 0.3);
        assert_eq!(labor.slot_labor[0], 0.0);
        assert_eq!(labor.slot_labor[1], 0.0);
        assert!((labor.slot_labor[2] - 2.5).abs() < 1e-5);
        assert!((labor.forage_labor - 27.5).abs() < 1e-4);
    }

    #[test]
    fn test_foraged_grain_reaches_the_stockpile_and_conservation() {
        let config = EconomyConfig::default();
        let region = EconomyRegionInput {
            region_id: 0,
            terrain: 1,
            storage_population: 20,
            resource_types: [ORE_RT, 255, 255],
            resource_yields: [1.0, 0.0, 0.0],
            production_caps: [None; 3],
            stockpile: [0.0; NUM_GOODS],
            subsistence_yield: 0.4,
            farm_labor_factor: 1.0,
            craft_raw_demand: 0.0,
            craft_demand: 0.0,
            farm_labor_ref: 0.0,
            farm_labor_half: 0.0,
            slot_curves: false,
            slot_labor_ref: [0.0; 3],
            slot_labor_half: [0.0; 3],
        };
        let agents = vec![RegionAgentCounts {
            population: 20, farmer_count: 10, soldier_count: 0, merchant_count: 0, wealthy_count: 0,
        }];
        let out = tick_economy_core(
            &[region], &agents, &[], &[0.0], &[0], 1, &[0u8], &config, 1.0, false, None,
        );
        // Demand 10; forage labor = min(10 / 0.4, 10 - 0.25 * 5) = 8.75 -> 3.5 grain.
        let suff = out.region_results[0].food_sufficiency;
        assert!((suff - 0.35).abs() < 1e-4, "{suff}");
        assert!((out.conservation.production - (3.5 + 1.25)).abs() < 1e-4);
        assert!((out.conservation.consumption - 3.5).abs() < 1e-4);
    }

    #[test]
    fn test_transport_cost_values() {
        // Plains avg: (1.0+1.0)/2 = 1.0. Base = 0.10.
        assert!((compute_transport_cost(0, 0, false, false, 1.0) - 0.10).abs() < 0.001);
        // River: 0.10 * 0.5 = 0.05
        assert!((compute_transport_cost(0, 0, true, false, 1.0) - 0.05).abs() < 0.001);
        // Coastal: (0.6+0.6)/2 * 0.10 * 0.6 = 0.036
        assert!((compute_transport_cost(TERRAIN_COAST, TERRAIN_COAST, false, false, 1.0) - 0.036).abs() < 0.001);
        // Mixed terrain uses the harder endpoint, not the average.
        assert!((compute_transport_cost(0, 1, false, false, 1.0) - 0.20).abs() < 0.001);
        // River and coastal discounts choose the better discount, not both.
        assert!((compute_transport_cost(TERRAIN_COAST, TERRAIN_COAST, true, false, 1.0) - 0.03).abs() < 0.001);
        // Winter: 0.10 * 1.5 = 0.15
        assert!((compute_transport_cost(0, 0, false, true, 1.0) - 0.15).abs() < 0.001);
    }
}
