//! Production ledger (2026-10, docs/integration/production-ledger.md): the
//! overextraction streak and the mines' soil charge follow the economy's
//! realized output, the overextraction penalty reaches the yields, the tick
//! reports what it took, and the economy's slot output, foraged grain and
//! wares are its whole production.

use chronicler_agents::ecology::{
    compute_yields, effective_capacity, mine_crew_ratio, overextraction_take, tick_ecology,
    tick_ecology_with_ledger, yield_penalty_factor, EcologyConfig, RiverTopology,
};
use chronicler_agents::economy::{
    tick_economy_core, EconomyConfig, EconomyRegionInput, RegionAgentCounts, TradeRouteInput, NUM_GOODS,
};
use chronicler_agents::RegionState;

const RT_GRAIN: u8 = 0;
const RT_TIMBER: u8 = 1;
const RT_FISH: u8 = 3;
const RT_ORE: u8 = 5;
const RT_PRECIOUS: u8 = 6;
const EMPTY: u8 = 255;

fn region(id: u16, population: u16, types: [u8; 3]) -> RegionState {
    let mut r = RegionState::new(id);
    r.terrain = 0; // plains: the soil cap (0.95) leaves room for recovery
    r.carrying_capacity = 60;
    r.population = population;
    r.controller_civ = 0;
    r.soil = 0.5;
    r.water = 0.8;
    r.resource_types = types;
    r.resource_base_yield = [1.0, 0.8, 0.0];
    r.resource_effective_yield = [1.0, 0.8, 0.0];
    r.resource_reserves = [1.0, 1.0, 1.0];
    r.prev_turn_water = 0.8;
    r
}

fn tick(regions: &mut [RegionState], config: &EcologyConfig) -> Vec<chronicler_agents::ecology::ExtractionLedger> {
    let n = regions.len();
    let (_, _, ledgers) = tick_ecology_with_ledger(
        regions, config, 6, 0, &vec![false; n], &vec![false; n], &RiverTopology::default(),
    );
    ledgers
}

// ---------------------------------------------------------------------------
// Overextraction streak
// ---------------------------------------------------------------------------

#[test]
fn the_take_is_realized_output_in_worker_equivalents() {
    let config = EcologyConfig::default();
    let mut r = region(0, 2000, [RT_GRAIN, RT_FISH, EMPTY]);
    assert_eq!(overextraction_take(&r, &config, 0), 400.0); // population / 5
    r.realized_extraction = Some([30.0, 4.0, 0.0]);
    assert_eq!(overextraction_take(&r, &config, 0), 30.0);
    assert_eq!(overextraction_take(&r, &config, 1), 5.0); // 4 goods at base 0.8
    let mut old = config.clone();
    old.overextraction_realized = false;
    assert_eq!(overextraction_take(&r, &old, 0), 400.0);
}

#[test]
fn a_crowd_that_takes_little_keeps_its_streak_at_zero() {
    // 2000 people: the proxy's 400 workers exceed 200 sustainable each turn.
    let config = EcologyConfig::default();
    let mut proxy = vec![region(0, 2000, [RT_GRAIN, EMPTY, EMPTY])];
    let mut realized = proxy.clone();
    for _ in 0..3 {
        tick(&mut proxy, &config);
        realized[0].realized_extraction = Some([20.0, 0.0, 0.0]);
        let ledgers = tick(&mut realized, &config);
        assert_eq!(ledgers[0].overextraction_take[0], 20.0);
        realized[0].realized_extraction = None; // consumed by the FFI after each tick
    }
    assert_eq!(proxy[0].overextraction_streak[0], 3);
    assert_eq!(realized[0].overextraction_streak[0], 0);
    // A small crowd taking more than the slot sustains does overextract.
    let mut heavy = vec![region(0, 10, [RT_GRAIN, EMPTY, EMPTY])];
    heavy[0].realized_extraction = Some([300.0, 0.0, 0.0]);
    tick(&mut heavy, &config);
    assert_eq!(heavy[0].overextraction_streak[0], 1);
}

#[test]
fn without_an_economy_the_streak_keeps_the_proxy_bit_for_bit() {
    let config = EcologyConfig::default();
    let mut a = vec![region(0, 2000, [RT_GRAIN, RT_ORE, EMPTY])];
    let mut b = a.clone();
    let mut old = config.clone();
    old.overextraction_realized = false;
    old.mine_soil_realized = false;
    old.yield_penalty_reaches_goods = false;
    for _ in 0..40 {
        tick(&mut a, &config);
        tick(&mut b, &old);
    }
    assert_eq!(a[0].overextraction_streak, b[0].overextraction_streak);
    assert_eq!(a[0].resource_effective_yield, b[0].resource_effective_yield);
    assert_eq!(a[0].soil.to_bits(), b[0].soil.to_bits());
    assert_eq!(a[0].resource_reserves[1].to_bits(), b[0].resource_reserves[1].to_bits());
    // 40 turns at 400 > 200 workers: one penalty at 35.
    assert!(a[0].resource_effective_yield[0] < 1.0);
}

// ---------------------------------------------------------------------------
// The overextraction penalty reaches the yields
// ---------------------------------------------------------------------------

#[test]
fn a_degraded_slot_yields_its_share() {
    let config = EcologyConfig::default();
    let mut whole = region(0, 30, [RT_GRAIN, RT_ORE, EMPTY]);
    let mut degraded = whole.clone();
    degraded.resource_effective_yield = [0.81, 0.72, 0.0];
    assert_eq!(yield_penalty_factor(&whole, 0), 1.0);
    assert!((yield_penalty_factor(&degraded, 0) - 0.81).abs() < 1e-6);
    let yw = compute_yields(&mut whole.clone(), &config, 2, 0);
    let yd = compute_yields(&mut degraded.clone(), &config, 2, 0);
    assert!((yd[0] / yw[0] - 0.81).abs() < 1e-5);
    assert!((yd[1] / yw[1] - 0.9).abs() < 1e-5);
    // Exhausted mines' trickle carries it too.
    whole.resource_reserves[1] = 0.0;
    degraded.resource_reserves[1] = 0.0;
    let tw = compute_yields(&mut whole, &config, 2, 0);
    let td = compute_yields(&mut degraded, &config, 2, 0);
    assert!((td[1] / tw[1] - 0.9).abs() < 1e-5);
    // The old rule reads base yields.
    let mut old = config.clone();
    old.yield_penalty_reaches_goods = false;
    let mut d = region(0, 30, [RT_GRAIN, RT_ORE, EMPTY]);
    d.resource_effective_yield = [0.81, 0.72, 0.0];
    let yo = compute_yields(&mut d, &old, 2, 0);
    assert_eq!(yo[0].to_bits(), yw[0].to_bits());
}

#[test]
fn undegraded_and_uninitialized_slots_keep_their_bits() {
    let config = EcologyConfig::default();
    let mut old = config.clone();
    old.yield_penalty_reaches_goods = false;
    let mut a = region(0, 30, [RT_GRAIN, RT_TIMBER, EMPTY]);
    a.resource_effective_yield = [1.0, 0.0, 0.0]; // timber never initialized (old scenario saves)
    let mut b = a.clone();
    let ya = compute_yields(&mut a, &config, 1, 3);
    let yb = compute_yields(&mut b, &old, 1, 3);
    assert_eq!(ya.map(f32::to_bits), yb.map(f32::to_bits));
    assert_eq!(yield_penalty_factor(&a, 1), 1.0);
}

// ---------------------------------------------------------------------------
// The mines' soil charge
// ---------------------------------------------------------------------------

#[test]
fn an_idle_mine_takes_no_soil_and_a_target_crew_the_old_rate() {
    let config = EcologyConfig::default();
    let mut idle = vec![region(0, 30, [RT_ORE, EMPTY, EMPTY])];
    idle[0].has_mines = true;
    let mut flat = idle.clone();
    let mut crewed = idle.clone();
    let crew = (effective_capacity(&crewed[0], &config) / 3).max(1) as f32;
    idle[0].realized_extraction = Some([0.0; 3]);
    crewed[0].realized_extraction = Some([crew, 0.0, 0.0]); // base yield 1.0
    let l_idle = tick(&mut idle, &config);
    let l_flat = tick(&mut flat, &config);
    let l_crew = tick(&mut crewed, &config);
    assert_eq!(l_idle[0].mine_soil, 0.0);
    assert_eq!(l_idle[0].proxy_mine_soil, config.mine_soil_degradation);
    assert_eq!(l_flat[0].mine_soil, config.mine_soil_degradation); // no economy: flat
    assert!((l_crew[0].mine_soil - config.mine_soil_degradation).abs() < 1e-7);
    assert!((l_crew[0].mine_crew_ratio - 1.0).abs() < 1e-6);
    // The idle mine's soil gained what the flat rule took.
    assert!((idle[0].soil - flat[0].soil - config.mine_soil_degradation).abs() < 2e-4);
}

#[test]
fn the_crew_ratio_sums_the_mineral_slots_and_the_old_rule_is_flat() {
    let config = EcologyConfig::default();
    let mut r = region(0, 30, [RT_ORE, RT_PRECIOUS, RT_GRAIN]);
    r.resource_base_yield = [1.0, 0.5, 1.0];
    assert_eq!(mine_crew_ratio(&r, &config), None);
    let crew = (effective_capacity(&r, &config) / 3).max(1) as f32;
    r.realized_extraction = Some([crew, crew * 0.25, 50.0]); // grain does not count
    assert!((mine_crew_ratio(&r, &config).unwrap() - 1.5).abs() < 1e-6);
    let mut old = config.clone();
    old.mine_soil_realized = false;
    let mut rs = vec![r.clone()];
    rs[0].has_mines = true;
    let l = tick(&mut rs, &old);
    assert_eq!(l[0].mine_soil, old.mine_soil_degradation);
}

// ---------------------------------------------------------------------------
// The tick's ledger
// ---------------------------------------------------------------------------

#[test]
fn the_ledger_reports_the_draw_and_what_the_proxy_draws() {
    let config = EcologyConfig::default();
    let mut realized = vec![region(0, 60, [RT_ORE, EMPTY, EMPTY])];
    let mut proxy = realized.clone();
    realized[0].realized_extraction = Some([2.0, 0.0, 0.0]);
    let lr = tick(&mut realized, &config);
    let lp = tick(&mut proxy, &config);
    assert!(lr[0].realized && !lp[0].realized);
    assert!((lr[0].mineral_drawn[0] - (1.0 - realized[0].resource_reserves[0])).abs() < 1e-7);
    assert!((lp[0].mineral_drawn[0] - (1.0 - proxy[0].resource_reserves[0])).abs() < 1e-7);
    // The proxy draw beside the realized one is what the proxy rule drew.
    assert_eq!(lr[0].proxy_mineral_draw[0].to_bits(), lp[0].mineral_drawn[0].to_bits());
    assert_eq!(lp[0].proxy_mineral_draw[0].to_bits(), lp[0].mineral_drawn[0].to_bits());
    let crew = lr[0].target_crew;
    assert!((lr[0].mineral_drawn[0] - 2.0 / crew * config.depletion_rate).abs() < 1e-7);
}

#[test]
fn the_ledger_changes_nothing() {
    let config = EcologyConfig::default();
    let mut a = vec![region(0, 45, [RT_ORE, RT_GRAIN, EMPTY]), region(1, 2000, [RT_FISH, EMPTY, EMPTY])];
    a[0].has_mines = true;
    let mut b = a.clone();
    for turn in 0..24u32 {
        for rs in [&mut a, &mut b] {
            rs[0].realized_extraction = Some([3.0, 10.0, 0.0]);
        }
        let n = a.len();
        let (ya, ea) = tick_ecology(&mut a, &config, turn, (turn / 6 % 4) as u8, &vec![false; n],
                                    &vec![false; n], &RiverTopology::default());
        let (yb, eb, _) = tick_ecology_with_ledger(&mut b, &config, turn, (turn / 6 % 4) as u8,
                                                   &vec![false; n], &vec![false; n], &RiverTopology::default());
        assert_eq!(ya, yb);
        assert_eq!(ea, eb);
        for rs in [&mut a, &mut b] {
            rs[0].realized_extraction = None;
        }
    }
    assert_eq!(a[0].soil.to_bits(), b[0].soil.to_bits());
    assert_eq!(a[0].resource_reserves, b[0].resource_reserves);
}

// ---------------------------------------------------------------------------
// Goods: slot output, foraging and wares are the production
// ---------------------------------------------------------------------------

fn economy_region(id: u16, types: [u8; 3], yields: [f32; 3]) -> EconomyRegionInput {
    EconomyRegionInput {
        region_id: id,
        terrain: 0,
        storage_population: 100,
        resource_types: types,
        resource_yields: yields,
        production_caps: [None; 3],
        stockpile: [0.0; NUM_GOODS],
        subsistence_yield: 0.3,
        farm_labor_factor: 1.0,
        craft_raw_demand: 0.0,
        craft_demand: 0.0,
        farm_labor_ref: 20.0,
        farm_labor_half: 20.0,
        slot_curves: true,
        slot_labor_ref: [10.0, 10.0, 10.0],
        slot_labor_half: [10.0, 10.0, 10.0],
    }
}

#[test]
fn slot_output_forage_and_wares_add_up_to_production() {
    let mut regions = vec![
        economy_region(0, [RT_GRAIN, RT_ORE, RT_TIMBER], [1.2, 0.9, 0.7]),
        economy_region(1, [RT_ORE, EMPTY, EMPTY], [1.0, 0.0, 0.0]), // forages
        economy_region(2, [RT_FISH, RT_GRAIN, EMPTY], [0.8, 0.0, 0.0]),
    ];
    regions[2].production_caps = [Some(3.0), None, None];
    regions[0].craft_raw_demand = 2.0;
    regions[0].craft_demand = 1.0;
    regions[0].stockpile[4] = 5.0; // ore on hand for the crafts
    let agents: Vec<RegionAgentCounts> = (0..3)
        .map(|_| RegionAgentCounts { population: 60, farmer_count: 30, soldier_count: 5, merchant_count: 3, wealthy_count: 2 })
        .collect();
    let routes: Vec<TradeRouteInput> = vec![];
    let out = tick_economy_core(&regions, &agents, &routes, &[0.0], &[0], 1, &[0, 0, 0],
                                &EconomyConfig::default(), 1.0, false, None);
    let mut total = 0.0f64;
    for rr in &out.region_results {
        total += rr.slot_output.iter().map(|&x| x as f64).sum::<f64>();
        total += rr.forage_output as f64 + rr.craft_output as f64;
    }
    assert!((total - out.conservation.production).abs() < 1e-4, "{total} vs {}", out.conservation.production);
    assert!(out.region_results[1].forage_output > 0.0);
    assert_eq!(out.region_results[0].forage_output, 0.0);
    assert!(out.region_results[2].slot_output[0] <= 3.0 + 1e-6); // the catch cap
    assert!(out.region_results[0].craft_output > 0.0);
}
