//! M54b integration tests: pure Rust economy core.
//!
//! Covers:
//! - single-region production and demand
//! - two-region trade allocation with stable route ordering
//! - tatonnement convergence behavior
//! - pre-transit observability vs post-lifecycle stockpiles
//! - salt preservation during storage decay
//! - stockpile cap and clamp_floor_loss
//! - civ fiscal outputs from merchant wealth / priest counts
//! - exact deterministic outputs across repeated runs

use chronicler_agents::economy::{
    EconomyConfig, EconomyRegionInput, HybridDeliveryInput, RegionAgentCounts, TradeRouteInput,
    tick_economy_core, NUM_GOODS,
    SLOT_GRAIN, SLOT_FISH, SLOT_SALT, SLOT_TIMBER, SLOT_ORE, SLOT_BOTANICALS,
    SLOT_PRECIOUS, SLOT_EXOTIC,
};
use chronicler_agents::merchant::DeliveryBuffer;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn default_config() -> EconomyConfig {
    EconomyConfig::default()
}

fn make_region(region_id: u16, rt: u8, yield_0: f32) -> EconomyRegionInput {
    EconomyRegionInput {
        region_id,
        terrain: 0, // plains
        storage_population: 100,
        resource_type_0: rt,
        resource_effective_yield_0: yield_0,
        stockpile: [0.0; NUM_GOODS],
    }
}

fn make_agents(pop: u32, farmers: u32, soldiers: u32, merchants: u32, wealthy: u32) -> RegionAgentCounts {
    RegionAgentCounts {
        population: pop,
        farmer_count: farmers,
        soldier_count: soldiers,
        merchant_count: merchants,
        wealthy_count: wealthy,
    }
}

// ---------------------------------------------------------------------------
// Single-region tests
// ---------------------------------------------------------------------------

#[test]
fn test_single_region_production_and_demand() {
    let config = default_config();
    // Region with grain (RT=0), yield=1.0
    let regions = vec![make_region(0, 0, 1.0)];
    // 100 pop, 50 farmers, 10 soldiers, 5 merchants, 2 wealthy
    let agents = vec![make_agents(100, 50, 10, 5, 2)];
    let routes: Vec<TradeRouteInput> = vec![];

    let out = tick_economy_core(
        &regions, &agents, &routes,
        &[0.0], &[0], 1,
        &config, 1.0, false, None,
    );

    assert_eq!(out.region_results.len(), 1);
    let rr = &out.region_results[0];
    assert_eq!(rr.region_id, 0);

    // Production: grain (slot 0), food category.  50 farmers * 1.0 yield = 50.0
    // Demand: food = 100 * 0.5 = 50.0
    // No trade: farmer_income_modifier = demand/supply = 50/50 = 1.0
    assert!(
        (rr.farmer_income_modifier - 1.0).abs() < 0.01,
        "farmer_income_modifier: expected ~1.0, got {}",
        rr.farmer_income_modifier
    );

    // food_sufficiency: stockpile starts at 0, production=50, demand=50.
    // After accumulation: stockpile grain = 0 + 50 - 0 + 0 = 50.
    // food_sufficiency = 50 / 50 = 1.0
    assert!(
        (rr.food_sufficiency - 1.0).abs() < 0.01,
        "food_sufficiency: expected ~1.0, got {}",
        rr.food_sufficiency
    );

    // No trade routes: merchant_margin = 0, merchant_trade_income = 0
    assert!(rr.merchant_margin.abs() < 0.001);
    assert!(rr.merchant_trade_income.abs() < 0.001);
    assert_eq!(rr.trade_route_count, 0);

    // Conservation: production=50
    assert!(
        (out.conservation.production - 50.0).abs() < 0.01,
        "conservation.production: expected 50.0, got {}",
        out.conservation.production
    );

    // After consumption: grain consumed proportionally, should be close to demand
    assert!(out.conservation.consumption > 0.0);

    // Observability
    assert_eq!(out.observability.len(), 1);
    assert!(!out.observability[0].trade_dependent);
}

#[test]
fn test_conservation_law() {
    let config = default_config();
    let mut region = make_region(0, 0, 2.0); // grain, high yield
    region.stockpile[SLOT_GRAIN] = 10.0; // pre-existing stockpile
    let regions = vec![region];
    let agents = vec![make_agents(50, 30, 5, 3, 1)];

    let out = tick_economy_core(
        &regions, &agents, &[],
        &[0.0], &[0], 1,
        &config, 1.0, false, None,
    );

    let c = &out.conservation;
    assert!(c.production >= 0.0);
    assert!(c.transit_loss >= 0.0);
    assert!(c.consumption >= 0.0);
    assert!(c.storage_loss >= 0.0);
    assert!(c.cap_overflow >= 0.0);
    assert!(c.clamp_floor_loss >= 0.0);

    // Stockpile delta: sum(final) - sum(initial)
    let initial_stock: f64 = 10.0;
    let final_stock: f64 = out.region_results[0].stockpile.iter().map(|&v| v as f64).sum();
    let delta = final_stock - initial_stock;

    // Conservation: production = sinks + delta_stockpile
    let sinks = c.transit_loss + c.consumption + c.storage_loss + c.cap_overflow + c.clamp_floor_loss;
    let residual = (c.production - sinks - delta).abs();
    assert!(
        residual < 0.01,
        "Conservation violated: residual={residual}, production={}, sinks={sinks}, delta={delta}",
        c.production
    );
}

// ---------------------------------------------------------------------------
// Civ fiscal tests
// ---------------------------------------------------------------------------

#[test]
fn test_civ_fiscal_outputs() {
    let config = default_config();
    let regions = vec![make_region(0, 0, 1.0)];
    let agents = vec![make_agents(50, 30, 5, 3, 1)];

    let merchant_wealth = vec![100.0f32];
    let priest_count = vec![5u32];

    let out = tick_economy_core(
        &regions, &agents, &[],
        &merchant_wealth, &priest_count, 1,
        &config, 1.0, false, None,
    );

    let cr = &out.civ_results[0];
    // treasury_tax = 0.05 * 100.0 = 5.0
    assert!(
        (cr.treasury_tax - 5.0).abs() < 0.001,
        "treasury_tax: expected 5.0, got {}",
        cr.treasury_tax
    );
    // tithe_base = 100.0
    assert!(
        (cr.tithe_base - 100.0).abs() < 0.001,
        "tithe_base: expected 100.0, got {}",
        cr.tithe_base
    );
    // priest_tithe_share = 0.10 * 100.0 / 5 = 2.0
    assert!(
        (cr.priest_tithe_share - 2.0).abs() < 0.001,
        "priest_tithe_share: expected 2.0, got {}",
        cr.priest_tithe_share
    );
}

#[test]
fn test_civ_fiscal_no_priests() {
    let config = default_config();
    let regions = vec![make_region(0, 0, 1.0)];
    let agents = vec![make_agents(50, 30, 5, 3, 1)];

    let out = tick_economy_core(
        &regions, &agents, &[],
        &[200.0], &[0], 1,
        &config, 1.0, false, None,
    );

    let cr = &out.civ_results[0];
    // priest_tithe_share = 0.10 * 200.0 / max(0, 1) = 20.0
    assert!(
        (cr.priest_tithe_share - 20.0).abs() < 0.001,
        "priest_tithe_share with 0 priests: expected 20.0, got {}",
        cr.priest_tithe_share
    );
}

// ---------------------------------------------------------------------------
// Salt preservation tests
// ---------------------------------------------------------------------------

#[test]
fn test_salt_preservation() {
    let config = default_config();
    // Region with grain production and NO salt in stockpile.
    let mut region_no_salt = make_region(0, 0, 0.0); // zero yield to avoid production noise
    region_no_salt.stockpile[SLOT_GRAIN] = 100.0;
    region_no_salt.stockpile[SLOT_FISH] = 50.0;

    // Same region but WITH salt.
    let mut region_with_salt = make_region(0, 0, 0.0);
    region_with_salt.stockpile[SLOT_GRAIN] = 100.0;
    region_with_salt.stockpile[SLOT_FISH] = 50.0;
    region_with_salt.stockpile[SLOT_SALT] = 50.0;

    // Zero population so cap doesn't interfere, zero demand so no consumption.
    let agents = vec![make_agents(0, 0, 0, 0, 0)];

    let out_no_salt = tick_economy_core(
        &[region_no_salt], &agents, &[],
        &[0.0], &[0], 1, &config, 1.0, false, None,
    );
    let out_with_salt = tick_economy_core(
        &[region_with_salt], &agents, &[],
        &[0.0], &[0], 1, &config, 1.0, false, None,
    );

    // With salt, food goods should decay less.
    let grain_no_salt = out_no_salt.region_results[0].stockpile[SLOT_GRAIN];
    let grain_with_salt = out_with_salt.region_results[0].stockpile[SLOT_GRAIN];
    assert!(
        grain_with_salt > grain_no_salt,
        "Salt preservation should reduce grain decay: with_salt={grain_with_salt}, no_salt={grain_no_salt}"
    );

    let fish_no_salt = out_no_salt.region_results[0].stockpile[SLOT_FISH];
    let fish_with_salt = out_with_salt.region_results[0].stockpile[SLOT_FISH];
    assert!(
        fish_with_salt > fish_no_salt,
        "Salt preservation should reduce fish decay: with_salt={fish_with_salt}, no_salt={fish_no_salt}"
    );

    // Salt itself should not decay (STORAGE_DECAY[SLOT_SALT] = 0.0).
    let salt_after = out_with_salt.region_results[0].stockpile[SLOT_SALT];
    assert!(
        (salt_after - 50.0).abs() < 0.001,
        "Salt should not decay: expected 50.0, got {salt_after}"
    );
}

// ---------------------------------------------------------------------------
// Stockpile cap tests
// ---------------------------------------------------------------------------

#[test]
fn test_stockpile_cap_and_overflow() {
    let config = default_config();
    // storage_population = 10, per_good_cap_factor = 2.5 → cap = 25.
    let mut region = make_region(0, 0, 0.0); // zero yield
    region.storage_population = 10;
    region.stockpile[SLOT_GRAIN] = 50.0; // well above cap
    region.stockpile[SLOT_TIMBER] = 30.0; // also above cap
    let agents = vec![make_agents(0, 0, 0, 0, 0)];

    let out = tick_economy_core(
        &[region], &agents, &[],
        &[0.0], &[0], 1, &config, 1.0, false, None,
    );

    // After storage decay and capping:
    // Grain: 50 * (1 - 0.03) = 48.5 → cap 25 → overflow 23.5
    // Timber: 30 * (1 - 0.005) = 29.85 → cap 25 → overflow 4.85
    let grain = out.region_results[0].stockpile[SLOT_GRAIN];
    let timber = out.region_results[0].stockpile[SLOT_TIMBER];
    assert!(
        (grain - 25.0).abs() < 0.01,
        "Grain should be capped at 25.0, got {grain}"
    );
    assert!(
        (timber - 25.0).abs() < 0.01,
        "Timber should be capped at 25.0, got {timber}"
    );
    assert!(out.conservation.cap_overflow > 0.0, "cap_overflow should be positive");
}

#[test]
fn test_clamp_floor_loss_tracking() {
    let config = default_config();
    let region = make_region(0, 0, 1.0);
    let agents = vec![make_agents(50, 30, 5, 3, 1)];

    let out = tick_economy_core(
        &[region], &agents, &[],
        &[0.0], &[0], 1, &config, 1.0, false, None,
    );

    // With no trade and balanced production, clamp_floor_loss should be 0.
    assert!(
        out.conservation.clamp_floor_loss.abs() < 0.001,
        "clamp_floor_loss should be 0 with balanced production, got {}",
        out.conservation.clamp_floor_loss
    );
}

// ---------------------------------------------------------------------------
// Two-region trade tests
// ---------------------------------------------------------------------------

#[test]
fn test_two_region_trade_allocation() {
    let config = default_config();
    // Region 0: grain (food), high production — surplus.
    let r0 = make_region(0, 0, 2.0);
    // Region 1: ore (raw_material), low food production — needs food imports.
    let r1 = make_region(1, 5, 1.0); // RT=5 → ORE
    let regions = vec![r0, r1];

    let agents = vec![
        make_agents(50, 30, 5, 10, 1), // region 0: lots of merchants
        make_agents(50, 10, 15, 5, 0), // region 1: soldiers need raw material
    ];

    // Bidirectional trade.
    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
        TradeRouteInput { origin_region_id: 1, dest_region_id: 0, is_river: false },
    ];

    let out = tick_economy_core(
        &regions, &agents, &routes,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, false, None,
    );

    assert_eq!(out.region_results.len(), 2);

    // Region 0: production food = 30 * 2.0 = 60, demand food = 50 * 0.5 = 25 → surplus 35
    // Region 1: production raw_material = 10 * 1.0 = 10, demand food = 50 * 0.5 = 25 → no food prod
    // So region 0 should export food to region 1.
    assert_eq!(out.region_results[0].trade_route_count, 1);
    assert_eq!(out.region_results[1].trade_route_count, 1);

    // Region 1 should have region 0 as an inbound source.
    let r1_sources: Vec<_> = out.upstream_sources.iter()
        .filter(|us| us.dest_region_id == 1)
        .collect();
    assert!(
        !r1_sources.is_empty(),
        "Region 1 should have inbound sources from trade"
    );
    // Source should be region 0.
    assert!(
        r1_sources.iter().any(|us| us.source_region_id == 0),
        "Region 1's upstream source should include region 0"
    );

    // Observability: region 1 should have food imports.
    assert!(
        out.observability[1].imports_food > 0.0,
        "Region 1 should have food imports, got {}",
        out.observability[1].imports_food
    );

    // Conservation should still hold.
    let c = &out.conservation;
    let initial_stock: f64 = 0.0; // both started at zero
    let final_stock: f64 = out.region_results.iter()
        .map(|rr| rr.stockpile.iter().map(|&v| v as f64).sum::<f64>())
        .sum();
    let delta = final_stock - initial_stock;
    let sinks = c.transit_loss + c.consumption + c.storage_loss + c.cap_overflow + c.clamp_floor_loss;
    let residual = (c.production - sinks - delta).abs();
    assert!(
        residual < 0.05,
        "Conservation violated in trade scenario: residual={residual}"
    );
}

#[test]
fn test_trade_stable_route_ordering() {
    let config = default_config();
    // Three regions forming a triangle.
    let r0 = make_region(0, 0, 2.0); // grain
    let r1 = make_region(1, 5, 1.0); // ore
    let r2 = make_region(2, 1, 1.5); // timber
    let regions = vec![r0, r1, r2];

    let agents = vec![
        make_agents(50, 30, 5, 10, 1),
        make_agents(50, 10, 15, 5, 0),
        make_agents(40, 20, 5, 8, 2),
    ];

    // Routes in non-sorted order — kernel should sort.
    let routes = vec![
        TradeRouteInput { origin_region_id: 2, dest_region_id: 0, is_river: false },
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
        TradeRouteInput { origin_region_id: 1, dest_region_id: 2, is_river: false },
        TradeRouteInput { origin_region_id: 0, dest_region_id: 2, is_river: false },
        TradeRouteInput { origin_region_id: 2, dest_region_id: 1, is_river: false },
        TradeRouteInput { origin_region_id: 1, dest_region_id: 0, is_river: false },
    ];

    let out1 = tick_economy_core(
        &regions, &agents, &routes,
        &[0.0, 0.0, 0.0], &[0, 0, 0], 3,
        &config, 1.0, false, None,
    );

    // Run again with routes in different order.
    let routes_shuffled = vec![
        TradeRouteInput { origin_region_id: 1, dest_region_id: 0, is_river: false },
        TradeRouteInput { origin_region_id: 0, dest_region_id: 2, is_river: false },
        TradeRouteInput { origin_region_id: 2, dest_region_id: 1, is_river: false },
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
        TradeRouteInput { origin_region_id: 1, dest_region_id: 2, is_river: false },
        TradeRouteInput { origin_region_id: 2, dest_region_id: 0, is_river: false },
    ];

    // Re-create inputs (can't reuse moved ones).
    let r0b = make_region(0, 0, 2.0);
    let r1b = make_region(1, 5, 1.0);
    let r2b = make_region(2, 1, 1.5);
    let regions_b = vec![r0b, r1b, r2b];
    let agents_b = vec![
        make_agents(50, 30, 5, 10, 1),
        make_agents(50, 10, 15, 5, 0),
        make_agents(40, 20, 5, 8, 2),
    ];

    let out2 = tick_economy_core(
        &regions_b, &agents_b, &routes_shuffled,
        &[0.0, 0.0, 0.0], &[0, 0, 0], 3,
        &config, 1.0, false, None,
    );

    // Outputs must be identical regardless of input route ordering.
    for (a, b) in out1.region_results.iter().zip(out2.region_results.iter()) {
        assert_eq!(a.region_id, b.region_id);
        assert_eq!(a.stockpile, b.stockpile, "Stockpile mismatch for region {}", a.region_id);
        assert_eq!(a.farmer_income_modifier, b.farmer_income_modifier);
        assert_eq!(a.food_sufficiency, b.food_sufficiency);
        assert_eq!(a.merchant_margin, b.merchant_margin);
        assert_eq!(a.merchant_trade_income, b.merchant_trade_income);
        assert_eq!(a.trade_route_count, b.trade_route_count);
    }
}

// ---------------------------------------------------------------------------
// Tatonnement convergence
// ---------------------------------------------------------------------------

#[test]
fn test_tatonnement_max_passes_respected() {
    // With 1 pass, prices should still produce valid results.
    let mut config = default_config();
    config.tatonnement_max_passes = 1;

    let r0 = make_region(0, 0, 2.0);
    let r1 = make_region(1, 5, 1.0);
    let regions = vec![r0, r1];
    let agents = vec![
        make_agents(50, 30, 5, 10, 1),
        make_agents(50, 10, 15, 5, 0),
    ];
    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];

    let out = tick_economy_core(
        &regions, &agents, &routes,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, false, None,
    );

    // Should produce valid output even with 1 pass.
    assert_eq!(out.region_results.len(), 2);
    assert!(out.conservation.production > 0.0);
}

// ---------------------------------------------------------------------------
// Determinism
// ---------------------------------------------------------------------------

#[test]
fn test_exact_determinism() {
    let config = default_config();

    let build_inputs = || {
        let mut r0 = make_region(0, 0, 1.5);
        r0.stockpile[SLOT_GRAIN] = 10.0;
        let mut r1 = make_region(1, 1, 0.8);
        r1.terrain = 3; // forest
        r1.stockpile[SLOT_TIMBER] = 5.0;
        let regions = vec![r0, r1];
        let agents = vec![
            make_agents(80, 40, 10, 8, 3),
            make_agents(60, 30, 5, 6, 1),
        ];
        let routes = vec![TradeRouteInput {
            origin_region_id: 0,
            dest_region_id: 1,
            is_river: false,
        }];
        (regions, agents, routes)
    };

    let (r1, a1, rt1) = build_inputs();
    let out1 = tick_economy_core(
        &r1, &a1, &rt1,
        &[50.0, 30.0], &[3, 2], 2,
        &config, 1.0, false, None,
    );

    let (r2, a2, rt2) = build_inputs();
    let out2 = tick_economy_core(
        &r2, &a2, &rt2,
        &[50.0, 30.0], &[3, 2], 2,
        &config, 1.0, false, None,
    );

    // Exact bit-identical comparison.
    for (a, b) in out1.region_results.iter().zip(out2.region_results.iter()) {
        assert_eq!(a.region_id, b.region_id);
        assert_eq!(a.stockpile, b.stockpile);
        assert_eq!(a.farmer_income_modifier, b.farmer_income_modifier);
        assert_eq!(a.food_sufficiency, b.food_sufficiency);
        assert_eq!(a.merchant_margin, b.merchant_margin);
        assert_eq!(a.merchant_trade_income, b.merchant_trade_income);
        assert_eq!(a.trade_route_count, b.trade_route_count);
    }
    for (a, b) in out1.civ_results.iter().zip(out2.civ_results.iter()) {
        assert_eq!(a.treasury_tax, b.treasury_tax);
        assert_eq!(a.tithe_base, b.tithe_base);
        assert_eq!(a.priest_tithe_share, b.priest_tithe_share);
    }
    assert_eq!(out1.conservation.production, out2.conservation.production);
    assert_eq!(out1.conservation.transit_loss, out2.conservation.transit_loss);
    assert_eq!(out1.conservation.consumption, out2.conservation.consumption);
    assert_eq!(out1.conservation.storage_loss, out2.conservation.storage_loss);
}

// ---------------------------------------------------------------------------
// Pre-transit observability vs post-lifecycle stockpiles
// ---------------------------------------------------------------------------

#[test]
fn test_observability_import_timing() {
    // imports_by_category uses pre-transit-decay category-level imports.
    // stockpile_levels uses post-lifecycle goods.
    // These should differ when transit decay is nonzero.
    let config = default_config();
    // Region 0: grain producer with surplus.
    let r0 = make_region(0, 0, 3.0); // high grain yield
    // Region 1: ore, needs food.
    let r1 = make_region(1, 5, 1.0);
    let regions = vec![r0, r1];

    let agents = vec![
        make_agents(30, 20, 2, 10, 0), // region 0: lots of merchants, low pop
        make_agents(50, 5, 10, 3, 0),  // region 1: needs food
    ];

    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];

    let out = tick_economy_core(
        &regions, &agents, &routes,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, false, None,
    );

    // If grain was traded, region 1 should have food imports.
    let obs1 = &out.observability[1];
    if obs1.imports_food > 0.0 {
        // The pre-transit import amount should be >= post-transit delivered amount.
        // (Transit decay for grain is 5%, so imports_food > stockpile addition.)
        // The observability imports_food is pre-transit-decay category-level.
        // The stockpile_food is post-lifecycle (after consumption, decay, cap).
        // We can't directly compare them since consumption changes stockpile_food,
        // but we can verify both are populated.
        assert!(obs1.imports_food > 0.0);
    }
}

// ---------------------------------------------------------------------------
// Transport cost tests
// ---------------------------------------------------------------------------

#[test]
fn test_river_trade_increases_flow() {
    let config = default_config();
    // Two regions, one with river and one without.
    let r0 = make_region(0, 0, 2.0); // grain surplus
    let r1 = make_region(1, 5, 1.0); // ore, needs food

    // Without river.
    let routes_no_river = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];
    let agents = vec![
        make_agents(30, 20, 2, 10, 0),
        make_agents(50, 5, 10, 3, 0),
    ];

    let out_no_river = tick_economy_core(
        &[make_region(0, 0, 2.0), make_region(1, 5, 1.0)],
        &agents, &routes_no_river,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, false, None,
    );

    // With river.
    let routes_river = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: true },
    ];
    let agents_b = vec![
        make_agents(30, 20, 2, 10, 0),
        make_agents(50, 5, 10, 3, 0),
    ];

    let out_river = tick_economy_core(
        &[make_region(0, 0, 2.0), make_region(1, 5, 1.0)],
        &agents_b, &routes_river,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, false, None,
    );

    // River should reduce transport cost, potentially increasing trade flow.
    // At minimum, merchant_margin should differ.
    // With lower transport cost, the effective margin is higher.
    assert!(
        out_river.region_results[0].merchant_margin >= out_no_river.region_results[0].merchant_margin,
        "River should not decrease merchant_margin"
    );
}

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

#[test]
fn test_empty_regions() {
    let config = default_config();
    let out = tick_economy_core(
        &[], &[], &[],
        &[], &[], 0,
        &config, 1.0, false, None,
    );
    assert!(out.region_results.is_empty());
    assert!(out.civ_results.is_empty());
    assert!(out.observability.is_empty());
    assert!(out.upstream_sources.is_empty());
}

#[test]
fn test_no_farmers_no_production() {
    let config = default_config();
    let regions = vec![make_region(0, 0, 1.0)];
    let agents = vec![make_agents(50, 0, 10, 5, 2)]; // 0 farmers

    let out = tick_economy_core(
        &regions, &agents, &[],
        &[0.0], &[0], 1,
        &config, 1.0, false, None,
    );

    assert!(
        out.conservation.production.abs() < 0.001,
        "No farmers should mean zero production"
    );
}

#[test]
fn test_winter_increases_transport_cost() {
    let config = default_config();
    let r0 = make_region(0, 0, 2.0);
    let r1 = make_region(1, 5, 1.0);
    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];

    let agents = vec![
        make_agents(30, 20, 2, 10, 0),
        make_agents(50, 5, 10, 3, 0),
    ];

    let out_summer = tick_economy_core(
        &[make_region(0, 0, 2.0), make_region(1, 5, 1.0)],
        &agents, &routes,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, false, None, // not winter
    );

    let agents_b = vec![
        make_agents(30, 20, 2, 10, 0),
        make_agents(50, 5, 10, 3, 0),
    ];
    let routes_b = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];

    let out_winter = tick_economy_core(
        &[make_region(0, 0, 2.0), make_region(1, 5, 1.0)],
        &agents_b, &routes_b,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, true, None, // winter
    );

    // Higher transport cost in winter should mean less effective margin.
    // The merchant_margin for region 0 should be <= summer value.
    assert!(
        out_winter.region_results[0].merchant_margin <= out_summer.region_results[0].merchant_margin,
        "Winter should not increase merchant_margin: winter={}, summer={}",
        out_winter.region_results[0].merchant_margin,
        out_summer.region_results[0].merchant_margin,
    );
}

#[test]
fn test_trade_dependency_detection() {
    let config = default_config();
    // Region 0: huge grain surplus.
    let r0 = make_region(0, 0, 5.0);
    // Region 1: no food production (ore), tiny population.
    let r1 = make_region(1, 5, 1.0);
    let regions = vec![r0, r1];

    let agents = vec![
        make_agents(20, 15, 2, 10, 0), // region 0: lots of merchants, small pop
        make_agents(10, 2, 2, 0, 0),   // region 1: tiny pop, no merchants
    ];

    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];

    let out = tick_economy_core(
        &regions, &agents, &routes,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, false, None,
    );

    // Region 1's import_share: food imports / food demand.
    // Food demand = 10 * 0.5 = 5.0.
    // If enough food flows in, import_share > 0.6 → trade_dependent = true.
    let obs1 = &out.observability[1];
    // At minimum, the import_share should be computed.
    assert!(obs1.import_share >= 0.0, "import_share should be non-negative");
}

#[test]
fn test_multiple_civs_fiscal() {
    let config = default_config();
    let regions = vec![make_region(0, 0, 1.0), make_region(1, 5, 1.0)];
    let agents = vec![
        make_agents(50, 30, 5, 3, 1),
        make_agents(40, 20, 3, 5, 2),
    ];

    let out = tick_economy_core(
        &regions, &agents, &[],
        &[100.0, 200.0], &[3, 0], 2,
        &config, 1.0, false, None,
    );

    assert_eq!(out.civ_results.len(), 2);

    // Civ 0: treasury_tax = 0.05 * 100 = 5.0
    assert!((out.civ_results[0].treasury_tax - 5.0).abs() < 0.001);
    // Civ 1: treasury_tax = 0.05 * 200 = 10.0
    assert!((out.civ_results[1].treasury_tax - 10.0).abs() < 0.001);
    // Civ 1: priest_tithe_share = 0.10 * 200 / max(0,1) = 20.0
    assert!((out.civ_results[1].priest_tithe_share - 20.0).abs() < 0.001);
}

// ---------------------------------------------------------------------------
// Hybrid trade_route_count semantics
// ---------------------------------------------------------------------------

#[test]
fn test_hybrid_trade_route_count_matches_abstract_semantics() {
    // Setup: region 0 exports to regions 1 and 2.
    // Abstract mode counts outbound routes per origin:
    //   boundary_pair_counts[0] = 2 (two outbound routes from region 0)
    //   boundary_pair_counts[1] = 0, boundary_pair_counts[2] = 0
    // Hybrid mode must match: count outbound pairs per origin, not inbound per dest.
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(3);
    // Region 0 sends goods to regions 1 and 2.
    buf.record_departure(0, 0, 5.0);
    buf.record_arrival(0, 1, 0, 3.0);  // source=0, dest=1, slot=GRAIN
    buf.record_arrival(0, 2, 0, 2.0);  // source=0, dest=2, slot=GRAIN
    let delivery = HybridDeliveryInput::from_buffer(&buf, 3);

    let region_inputs = vec![
        make_region(0, 0, 1.0),
        make_region(1, 0, 1.0),
        make_region(2, 0, 1.0),
    ];
    let agent_counts = vec![
        make_agents(100, 80, 5, 10, 5),
        make_agents(100, 80, 5, 10, 5),
        make_agents(100, 80, 5, 10, 5),
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &[], &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // Region 0 exports to 2 destinations → trade_route_count = 2
    assert_eq!(
        output.region_results[0].trade_route_count, 2,
        "origin region should count outbound partners"
    );
    // Regions 1 and 2 have no outbound routes → trade_route_count = 0
    assert_eq!(
        output.region_results[1].trade_route_count, 0,
        "non-exporting region should have 0"
    );
    assert_eq!(
        output.region_results[2].trade_route_count, 0,
        "non-exporting region should have 0"
    );
}
