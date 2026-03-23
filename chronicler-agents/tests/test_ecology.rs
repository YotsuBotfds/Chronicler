//! M54a integration tests: pure Rust ecology core.
//!
//! Covers the scenarios from the implementation plan:
//! - basic plains tick
//! - uncontrolled-region divergence
//! - disease flare + pandemic suppression
//! - soil pressure streak threshold
//! - overextraction event emission
//! - river cascade second clamp
//! - reserve depletion / exhausted trickle
//! - mixed terrain caps/floors
//! - determinism harness (1/4/8/16 threads)

use chronicler_agents::RegionState;
use chronicler_agents::ecology::{
    EcologyConfig, EcologyEvent, RiverTopology, effective_capacity, pressure_multiplier,
    tick_ecology, compute_yields, season_id_from_turn,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TERRAIN_PLAINS: u8 = 0;
const TERRAIN_MOUNTAINS: u8 = 1;
const TERRAIN_COAST: u8 = 2;
const TERRAIN_FOREST: u8 = 3;
const TERRAIN_DESERT: u8 = 4;
const TERRAIN_TUNDRA: u8 = 5;

const CLIMATE_TEMPERATE: u8 = 0;
const CLIMATE_WARMING: u8 = 1;
const CLIMATE_DROUGHT: u8 = 2;
const CLIMATE_COOLING: u8 = 3;

const RT_GRAIN: u8 = 0;
const RT_TIMBER: u8 = 1;
const RT_ORE: u8 = 5;
const RT_PRECIOUS: u8 = 6;
const EMPTY_SLOT: u8 = 255;

fn default_config() -> EcologyConfig {
    EcologyConfig::default()
}

fn empty_river() -> RiverTopology {
    RiverTopology::default()
}

/// Make a controlled plains region with sensible defaults.
fn make_plains(id: u16) -> RegionState {
    let mut r = RegionState::new(id);
    r.terrain = TERRAIN_PLAINS;
    r.soil = 0.80;
    r.water = 0.60;
    r.forest_cover = 0.20;
    r.carrying_capacity = 60;
    r.population = 30;
    r.controller_civ = 0;
    r.capacity_modifier = 1.0;
    r.prev_turn_water = 0.60;
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];
    r
}

/// Make an uncontrolled region (controller_civ = 255).
fn make_uncontrolled(id: u16) -> RegionState {
    let mut r = make_plains(id);
    r.controller_civ = 255;
    r
}

// ---------------------------------------------------------------------------
// Test: Basic plains tick
// ---------------------------------------------------------------------------

#[test]
fn test_basic_plains_tick() {
    let config = default_config();
    let mut regions = vec![make_plains(0)];
    let pandemic = vec![false];
    let army = vec![false];

    let (yields, events) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    let r = &regions[0];

    // Soil: pop 30 < eff_cap 48 < eff_cap*0.75=36 => recovery path active
    // recovery = 0.05 * pressure_mult(0.375) = 0.01875
    // 0.80 + 0.01875 = 0.81875 => after clamp/round4 = 0.8188 (round4 of 0.81875)
    // Actually round4(0.81875) = round(8187.5) / 10000 = 8188 / 10000 = 0.8188
    assert!((r.soil - 0.8188).abs() < 0.001, "soil={}", r.soil);

    // Water: temperate => recovery = 0.03 * 0.375 = 0.01125
    // 0.60 + 0.01125 = 0.61125 => round4 = 0.6113 (round(6112.5)/10000 = 6113/10000)
    // Capped at 0.70 for plains — 0.6113 < 0.70, OK
    assert!((r.water - 0.6113).abs() < 0.001, "water={}", r.water);

    // Forest: pop 30 == carrying_capacity * 0.5 = 30 => NOT > threshold
    // Regrowth: pop < threshold AND water >= 0.3 => regrowth active
    // Actually pop 30 is NOT < threshold (30 < 30 is false).
    // So neither clearing nor regrowth fires.
    // forest stays at 0.20 => round4 = 0.2
    assert!((r.forest_cover - 0.20).abs() < 0.001, "forest={}", r.forest_cover);

    // prev_turn_water set to current water
    assert!((r.prev_turn_water - r.water).abs() < f32::EPSILON);

    // Yields should have a non-zero grain yield
    assert!(yields[0][0] > 0.0, "grain yield should be positive");

    // No events expected
    assert!(events.is_empty(), "no events expected for basic tick");
}

// ---------------------------------------------------------------------------
// Test: Uncontrolled-region divergence
// ---------------------------------------------------------------------------

#[test]
fn test_uncontrolled_diverges_from_controlled() {
    let config = default_config();

    let mut controlled = vec![make_plains(0)];
    controlled[0].has_mines = true;
    controlled[0].active_focus = 2; // METALLURGY

    let mut uncontrolled = vec![make_uncontrolled(0)];
    uncontrolled[0].has_mines = true;
    uncontrolled[0].active_focus = 2;

    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut controlled, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );
    let (_, _) = tick_ecology(
        &mut uncontrolled, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Uncontrolled should NOT get mine soil degradation.
    // Controlled: soil degraded by mine_soil_degradation * metallurgy_mine_reduction
    // = 0.03 * 0.5 = 0.015 (subtracted) then recovery may kick in.
    // Uncontrolled: only natural recovery applies, no mine degradation.
    // So uncontrolled soil should be HIGHER than controlled soil.
    assert!(
        uncontrolled[0].soil > controlled[0].soil,
        "uncontrolled soil {} should be > controlled soil {} (no mine degradation)",
        uncontrolled[0].soil, controlled[0].soil
    );
}

// ---------------------------------------------------------------------------
// Test: Disease flare triggers
// ---------------------------------------------------------------------------

#[test]
fn test_disease_flare_overcrowding() {
    let config = default_config();
    let mut r = make_plains(0);
    r.population = 55; // 55 > 60 * 0.8 = 48 overcrowding threshold
    r.disease_baseline = 0.01;
    r.endemic_severity = 0.01;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Overcrowding spike of 0.04 should have fired.
    // 0.01 + 0.04 = 0.05, capped at 0.15
    assert!(
        regions[0].endemic_severity > 0.01,
        "severity {} should be above baseline after overcrowding flare",
        regions[0].endemic_severity
    );
    assert!(
        (regions[0].endemic_severity - 0.05).abs() < 0.001,
        "severity {} expected ~0.05",
        regions[0].endemic_severity
    );
}

#[test]
fn test_disease_flare_army_passage() {
    let config = default_config();
    let mut r = make_plains(0);
    r.disease_baseline = 0.01;
    r.endemic_severity = 0.01;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![true]; // Army arrived

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Army spike of 0.03 fires.
    // 0.01 + 0.03 = 0.04
    assert!(
        (regions[0].endemic_severity - 0.04).abs() < 0.001,
        "severity {} expected ~0.04 after army passage",
        regions[0].endemic_severity
    );
}

#[test]
fn test_disease_flare_low_water() {
    let config = default_config();
    let mut r = make_plains(0);
    r.water = 0.25; // Below 0.3 threshold, non-desert
    r.prev_turn_water = 0.25;
    r.disease_baseline = 0.01;
    r.endemic_severity = 0.01;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Water spike of 0.02 fires.
    assert!(
        regions[0].endemic_severity > 0.01,
        "severity {} should spike from low water",
        regions[0].endemic_severity
    );
}

#[test]
fn test_disease_pandemic_suppression() {
    let config = default_config();
    let mut r = make_plains(0);
    r.population = 55; // Would trigger overcrowding
    r.disease_baseline = 0.01;
    r.endemic_severity = 0.05; // Above baseline, will decay

    let mut regions = vec![r];
    let pandemic = vec![true]; // Pandemic suppresses flares
    let army = vec![true]; // Would trigger army flare too

    let initial_severity = regions[0].endemic_severity;
    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // With pandemic suppression, all flares are suppressed.
    // Severity should decay toward baseline (0.01).
    // Decay: severity -= 0.25 * (0.05 - 0.01) = 0.25 * 0.04 = 0.01
    // New: 0.05 - 0.01 = 0.04
    assert!(
        regions[0].endemic_severity < initial_severity,
        "severity {} should have decayed (was {})",
        regions[0].endemic_severity, initial_severity
    );
    assert!(
        (regions[0].endemic_severity - 0.04).abs() < 0.001,
        "severity {} expected ~0.04 after suppressed decay",
        regions[0].endemic_severity
    );
}

// ---------------------------------------------------------------------------
// Test: Soil pressure streak threshold
// ---------------------------------------------------------------------------

#[test]
fn test_soil_pressure_streak_threshold() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    // Pop above soil_pressure_threshold (0.7) * carrying_capacity (60) = 42
    r.population = 50;
    // Set streak just below limit
    r.soil_pressure_streak = 29; // limit is 30

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, events) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Streak should have been incremented to 30, hitting the limit.
    // A soil_exhaustion event should be emitted.
    let soil_events: Vec<_> = events.iter().filter(|e| e.event_type == 0).collect();
    assert!(
        !soil_events.is_empty(),
        "expected soil_exhaustion event when streak hits limit"
    );
    assert_eq!(soil_events[0].slot, 255);
    assert!((soil_events[0].magnitude - 2.0).abs() < f32::EPSILON);
}

#[test]
fn test_soil_pressure_streak_resets_below_threshold() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r.population = 30; // Below threshold (42)
    r.soil_pressure_streak = 15;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, events) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert_eq!(regions[0].soil_pressure_streak, 0, "streak should reset when below threshold");
    let soil_events: Vec<_> = events.iter().filter(|e| e.event_type == 0).collect();
    assert!(soil_events.is_empty(), "no soil_exhaustion event when below threshold");
}

// ---------------------------------------------------------------------------
// Test: Overextraction event emission
// ---------------------------------------------------------------------------

#[test]
fn test_overextraction_event_emission() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_effective_yield = [0.001, 0.0, 0.0]; // Very low yield
    r.population = 50; // worker_count = 50/5 = 10
    // sustainable = 0.001 * 200 = 0.2, 10 > 0.2 => overextraction
    r.overextraction_streak = [34, 0, 0]; // One below limit (35)

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, events) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Streak was 34, incremented to 35, hits limit => event + reset to 0
    let depletion_events: Vec<_> = events.iter().filter(|e| e.event_type == 1).collect();
    assert!(
        !depletion_events.is_empty(),
        "expected resource_depletion event when overextraction streak hits limit"
    );
    assert_eq!(depletion_events[0].slot, 0);
    assert!((depletion_events[0].magnitude - 0.10).abs() < f32::EPSILON);

    // Streak should be reset to 0
    assert_eq!(regions[0].overextraction_streak[0], 0);

    // Effective yield should have been degraded by 10%
    let expected_eff = 0.001 * (1.0 - 0.10);
    assert!(
        (regions[0].resource_effective_yield[0] - expected_eff).abs() < 0.0001,
        "effective yield {} expected {}",
        regions[0].resource_effective_yield[0], expected_eff
    );
}

// ---------------------------------------------------------------------------
// Test: River cascade with second clamp
// ---------------------------------------------------------------------------

#[test]
fn test_river_cascade_second_clamp() {
    let config = default_config();

    // 3-region river: 0 (upstream) -> 1 (middle) -> 2 (downstream)
    let mut r0 = make_plains(0);
    r0.forest_cover = 0.05; // Below deforestation threshold (0.2)

    let mut r1 = make_plains(1);
    r1.water = 0.15; // Will be reduced further, should clamp to floor 0.10

    let mut r2 = make_plains(2);
    r2.water = 0.60;

    let mut regions = vec![r0, r1, r2];
    let pandemic = vec![false; 3];
    let army = vec![false; 3];

    let topo = RiverTopology {
        rivers: vec![vec![0, 1, 2]],
    };

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &topo,
    );

    // r0 is deforested (forest_cover=0.05 < 0.2), so downstream r1 and r2
    // get deforestation_water_loss (0.05) applied.
    //
    // r1 starts at 0.15, gets temperate recovery (+small amount), then in the
    // first clamp pass gets clamped.  Then cascade applies -0.05.
    // After second clamp, r1.water should be floored at 0.10.
    assert!(
        regions[1].water >= 0.10 - 0.001,
        "r1 water {} should be >= floor 0.10 after second clamp",
        regions[1].water
    );

    // r2 should have lost 0.05 from the cascade.
    // Started at 0.60, got temperate recovery, cascade -0.05, second clamp.
    // The exact value depends on recovery, but it should be less than what
    // a region without cascade would have.

    // Verify the cascade actually ran by checking r2 water is meaningfully
    // different from what it would be without cascade.
    let mut r2_nocascade = make_plains(2);
    r2_nocascade.water = 0.60;
    let mut regions_nc = vec![r2_nocascade];
    let pandemic_nc = vec![false];
    let army_nc = vec![false];
    let (_, _) = tick_ecology(
        &mut regions_nc, &config, 0, CLIMATE_TEMPERATE, &pandemic_nc, &army_nc, &empty_river(),
    );

    assert!(
        regions[2].water < regions_nc[0].water,
        "r2 water {} should be less than no-cascade water {} due to upstream deforestation",
        regions[2].water, regions_nc[0].water
    );
}

// ---------------------------------------------------------------------------
// Test: Reserve depletion / exhausted trickle
// ---------------------------------------------------------------------------

#[test]
fn test_reserve_depletion_exhausted_trickle() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_ORE, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];
    r.resource_reserves = [0.005, 1.0, 1.0]; // Near zero reserves
    r.population = 30;
    r.terrain = TERRAIN_MOUNTAINS;
    r.soil = 0.40;
    r.water = 0.80;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (yields, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Reserves were 0.005, below 0.01, so depletion math skips,
    // and we go straight to exhausted trickle check.
    // Wait — reserves=0.005 > 0.01 is FALSE, and pop > 0 is TRUE.
    // So the depletion branch fires: reserves=0.005 > 0.01 is false.
    // Actually 0.005 is NOT > 0.01.  So the depletion extraction does NOT fire.
    // Then reserves check: 0.005 < 0.01 => exhausted trickle path.
    // Yield = base * trickle_fraction = 1.0 * 0.04 = 0.04
    assert!(
        (yields[0][0] - 0.04).abs() < 0.001,
        "ore yield {} expected 0.04 (exhausted trickle)",
        yields[0][0]
    );
}

#[test]
fn test_reserve_depletion_gradual() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_ORE, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];
    r.resource_reserves = [0.50, 1.0, 1.0]; // Moderate reserves
    r.population = 30;
    r.terrain = TERRAIN_MOUNTAINS;
    r.soil = 0.40;
    r.water = 0.80;

    let initial_reserves = r.resource_reserves[0];
    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Reserves should have decreased from depletion.
    assert!(
        regions[0].resource_reserves[0] < initial_reserves,
        "reserves {} should have decreased (was {})",
        regions[0].resource_reserves[0], initial_reserves
    );
    assert!(regions[0].resource_reserves[0] >= 0.0, "reserves should never go negative");
}

// ---------------------------------------------------------------------------
// Test: Mixed terrain caps/floors
// ---------------------------------------------------------------------------

#[test]
fn test_terrain_caps_desert() {
    let config = default_config();
    let mut r = make_plains(0);
    r.terrain = TERRAIN_DESERT;
    r.soil = 0.90; // Above desert cap 0.30
    r.water = 0.50; // Above desert cap 0.20
    r.forest_cover = 0.50; // Above desert cap 0.10
    r.controller_civ = 0;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(regions[0].soil <= 0.30 + 0.001, "desert soil {} should be <= 0.30", regions[0].soil);
    assert!(regions[0].water <= 0.20 + 0.001, "desert water {} should be <= 0.20", regions[0].water);
    assert!(regions[0].forest_cover <= 0.10 + 0.001, "desert forest {} should be <= 0.10", regions[0].forest_cover);
}

#[test]
fn test_terrain_caps_tundra() {
    let config = default_config();
    let mut r = make_plains(0);
    r.terrain = TERRAIN_TUNDRA;
    r.soil = 0.80;
    r.water = 0.90;
    r.forest_cover = 0.50;
    r.controller_civ = 0;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(regions[0].soil <= 0.20 + 0.001, "tundra soil {} should be <= 0.20", regions[0].soil);
    assert!(regions[0].water <= 0.60 + 0.001, "tundra water {} should be <= 0.60", regions[0].water);
    assert!(regions[0].forest_cover <= 0.15 + 0.001, "tundra forest {} should be <= 0.15", regions[0].forest_cover);
}

#[test]
fn test_terrain_floors() {
    let config = default_config();
    let mut r = make_plains(0);
    r.soil = -0.5;
    r.water = -0.5;
    r.forest_cover = -0.5;
    r.controller_civ = 0;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Floors: soil=0.05, water=0.10, forest=0.00
    // But soil may have recovered during the tick.  Check the floor is respected.
    assert!(regions[0].soil >= 0.05, "soil {} should be >= floor 0.05", regions[0].soil);
    assert!(regions[0].water >= 0.10, "water {} should be >= floor 0.10", regions[0].water);
    assert!(regions[0].forest_cover >= 0.00, "forest {} should be >= floor 0.00", regions[0].forest_cover);
}

#[test]
fn test_terrain_caps_mountains() {
    let config = default_config();
    let mut r = make_plains(0);
    r.terrain = TERRAIN_MOUNTAINS;
    r.soil = 0.80; // Above mountains cap 0.50
    r.water = 1.0; // Above mountains cap 0.90
    r.forest_cover = 0.80; // Above mountains cap 0.40
    r.controller_civ = 0;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(regions[0].soil <= 0.50 + 0.001, "mountains soil {} should be <= 0.50", regions[0].soil);
    assert!(regions[0].water <= 0.90 + 0.001, "mountains water {} should be <= 0.90", regions[0].water);
    assert!(regions[0].forest_cover <= 0.40 + 0.001, "mountains forest {} should be <= 0.40", regions[0].forest_cover);
}

#[test]
fn test_terrain_caps_coast() {
    let config = default_config();
    let mut r = make_plains(0);
    r.terrain = TERRAIN_COAST;
    r.soil = 1.0;
    r.water = 1.0;
    r.forest_cover = 1.0;
    r.controller_civ = 0;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(regions[0].soil <= 0.80 + 0.001, "coast soil {} should be <= 0.80", regions[0].soil);
    assert!(regions[0].water <= 0.90 + 0.001, "coast water {} should be <= 0.90", regions[0].water);
    assert!(regions[0].forest_cover <= 0.40 + 0.001, "coast forest {} should be <= 0.40", regions[0].forest_cover);
}

#[test]
fn test_terrain_caps_forest() {
    let config = default_config();
    let mut r = make_plains(0);
    r.terrain = TERRAIN_FOREST;
    r.soil = 1.0;
    r.water = 1.0;
    r.forest_cover = 1.0;
    r.controller_civ = 0;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(regions[0].soil <= 0.80 + 0.001, "forest soil {} should be <= 0.80", regions[0].soil);
    assert!(regions[0].water <= 0.80 + 0.001, "forest water {} should be <= 0.80", regions[0].water);
    assert!(regions[0].forest_cover <= 0.95 + 0.001, "forest forest_cover {} should be <= 0.95", regions[0].forest_cover);
}

// ---------------------------------------------------------------------------
// Test: Disease seasonal peak (fever + plague)
// ---------------------------------------------------------------------------

#[test]
fn test_disease_seasonal_peak_fever() {
    let config = default_config();
    let mut r = make_plains(0);
    r.disease_baseline = 0.03; // >= 0.02, so "fever" vector
    r.endemic_severity = 0.03;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    // Turn 3 => season_id = 1 (summer) — fever peaks in summer
    let (_, _) = tick_ecology(
        &mut regions, &config, 3, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Season spike of 0.02 should fire.
    assert!(
        regions[0].endemic_severity > 0.03,
        "fever severity {} should spike in summer",
        regions[0].endemic_severity
    );
}

#[test]
fn test_disease_seasonal_peak_plague() {
    let config = default_config();
    let mut r = make_plains(0);
    r.disease_baseline = 0.005; // <= 0.01, not fever, not cholera => "plague"
    r.endemic_severity = 0.005;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    // Turn 9 => season_id = 3 (winter) — plague peaks in winter
    let (_, _) = tick_ecology(
        &mut regions, &config, 9, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(
        regions[0].endemic_severity > 0.005,
        "plague severity {} should spike in winter",
        regions[0].endemic_severity
    );
}

// ---------------------------------------------------------------------------
// Test: Water inter-turn drop flare
// ---------------------------------------------------------------------------

#[test]
fn test_disease_water_drop_flare() {
    let config = default_config();
    let mut r = make_plains(0);
    r.water = 0.50;
    r.prev_turn_water = 0.65; // Drop of 0.15, which is > 0.1
    r.disease_baseline = 0.01;
    r.endemic_severity = 0.01;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Water drop > 0.1 AND water >= 0.3 (no double-count) => water spike fires.
    assert!(
        regions[0].endemic_severity > 0.01,
        "severity {} should spike from water drop",
        regions[0].endemic_severity
    );
}

// ---------------------------------------------------------------------------
// Test: Effective capacity and pressure multiplier edge cases
// ---------------------------------------------------------------------------

#[test]
fn test_effective_capacity_min_one() {
    let config = default_config();
    let mut r = RegionState::new(0);
    r.soil = 0.0;
    r.water = 0.0;
    r.carrying_capacity = 0;
    r.capacity_modifier = 1.0;
    let eff = effective_capacity(&r, &config);
    assert_eq!(eff, 1, "effective capacity should be at least 1");
}

#[test]
fn test_pressure_multiplier_overpopulated() {
    let config = default_config();
    let mut r = make_plains(0);
    r.population = 60; // Well above eff_cap of 48
    let pm = pressure_multiplier(&r, &config);
    // 1.0 - 60/48 = 1.0 - 1.25 = -0.25, clamped to 0.1
    assert!((pm - 0.1).abs() < 0.001, "pressure_multiplier should floor at 0.1");
}

// ---------------------------------------------------------------------------
// Test: Climate phase effects
// ---------------------------------------------------------------------------

#[test]
fn test_drought_water_loss() {
    let config = default_config();
    let mut r = make_plains(0);
    r.water = 0.60;
    r.has_irrigation = false;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_DROUGHT, &pandemic, &army, &empty_river(),
    );

    // Drought: -0.04, no irrigation multiplier
    // 0.60 - 0.04 = 0.56.  Clamp: plains water cap 0.70, floor 0.10. 0.56 is OK.
    // Also no temperate recovery, no irrigation bonus during drought.
    assert!(
        regions[0].water < 0.60,
        "water {} should decrease during drought",
        regions[0].water
    );
}

#[test]
fn test_drought_irrigation_amplifies() {
    let config = default_config();
    let mut r = make_plains(0);
    r.water = 0.60;
    r.has_irrigation = true;

    let mut r2 = r.clone();
    r2.has_irrigation = false;

    let mut regions_irrig = vec![r];
    let mut regions_no_irrig = vec![r2];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions_irrig, &config, 0, CLIMATE_DROUGHT, &pandemic, &army, &empty_river(),
    );
    let (_, _) = tick_ecology(
        &mut regions_no_irrig, &config, 0, CLIMATE_DROUGHT, &pandemic, &army, &empty_river(),
    );

    // With irrigation: rate = 0.04 * 1.5 = 0.06 loss
    // Without irrigation: rate = 0.04 loss
    // Irrigation AMPLIFIES drought damage.
    assert!(
        regions_irrig[0].water < regions_no_irrig[0].water,
        "irrigation water {} should be lower than no-irrigation {} during drought",
        regions_irrig[0].water, regions_no_irrig[0].water
    );
}

#[test]
fn test_cooling_effects() {
    let config = default_config();
    let mut r = make_plains(0);
    r.water = 0.60;
    r.forest_cover = 0.30;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_COOLING, &pandemic, &army, &empty_river(),
    );

    // Cooling: water -= 0.02, forest -= 0.01
    // But there's also recovery/clearing logic.  At minimum, check directional.
    // The forest should be lower due to cooling damage.
    assert!(regions[0].forest_cover < 0.30, "forest should decrease during cooling");
}

#[test]
fn test_warming_tundra_water_gain() {
    let config = default_config();
    let mut r = make_plains(0);
    r.terrain = TERRAIN_TUNDRA;
    r.water = 0.40;
    r.soil = 0.15;
    r.forest_cover = 0.10;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_WARMING, &pandemic, &army, &empty_river(),
    );

    // Warming + tundra: water += 0.05.  But tundra cap is 0.60.
    // 0.40 + 0.05 = 0.45, within cap.
    assert!(
        regions[0].water > 0.40,
        "tundra water {} should increase during warming",
        regions[0].water
    );
}

// ---------------------------------------------------------------------------
// Test: Cross-effects (forest -> soil)
// ---------------------------------------------------------------------------

#[test]
fn test_cross_effect_forest_soil_bonus() {
    let config = default_config();
    let mut r = make_plains(0);
    r.terrain = TERRAIN_FOREST;
    r.forest_cover = 0.70; // Above cross_effect_forest_threshold (0.5)
    r.soil = 0.50;

    let mut r_low = r.clone();
    r_low.forest_cover = 0.30; // Below threshold

    let mut regions_high = vec![r];
    let mut regions_low = vec![r_low];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions_high, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );
    let (_, _) = tick_ecology(
        &mut regions_low, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // High forest should get +0.01 soil bonus from cross-effects.
    // (Exact comparison tricky due to other soil effects, but high should be higher.)
    assert!(
        regions_high[0].soil > regions_low[0].soil,
        "high-forest soil {} should be > low-forest soil {} due to cross-effect",
        regions_high[0].soil, regions_low[0].soil
    );
}

// ---------------------------------------------------------------------------
// Test: Yield computation
// ---------------------------------------------------------------------------

#[test]
fn test_yield_grain_basic() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];
    r.soil = 0.80;
    r.water = 0.60;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    // Turn 0 => season_id 0 (spring)
    let (yields, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // The soil/water will change from the ecology tick before yields are computed.
    // But the yield should be: base * season_mod * climate_mod * ecology_mod * abundance
    // season_mod for GRAIN at spring = 0.8
    // climate_mod for Crop at temperate = 1.0
    // ecology_mod for Crop = soil * water (post-tick values)
    // abundance = 1.0
    assert!(yields[0][0] > 0.0, "grain yield should be positive");

    // Also check that the yield was written to region.resource_yields
    assert!(
        (regions[0].resource_yields[0] - yields[0][0]).abs() < f32::EPSILON,
        "resource_yields should match returned yields"
    );
}

#[test]
fn test_yield_suspended_resource() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, RT_TIMBER, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 1.0, 0.0];
    r.resource_effective_yield = [1.0, 1.0, 0.0];
    r.resource_suspension = [true, false, false]; // Grain suspended

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (yields, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(
        yields[0][0].abs() < f32::EPSILON,
        "suspended grain yield {} should be 0.0",
        yields[0][0]
    );
    assert!(
        yields[0][1] > 0.0,
        "non-suspended timber yield {} should be positive",
        yields[0][1]
    );
}

// ---------------------------------------------------------------------------
// Test: prev_turn_water finalization
// ---------------------------------------------------------------------------

#[test]
fn test_prev_turn_water_finalization() {
    let config = default_config();
    let mut r = make_plains(0);
    r.water = 0.60;
    r.prev_turn_water = 0.50; // Old value

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // After tick, prev_turn_water should equal current water.
    assert!(
        (regions[0].prev_turn_water - regions[0].water).abs() < f32::EPSILON,
        "prev_turn_water {} should equal water {} after tick",
        regions[0].prev_turn_water, regions[0].water
    );
}

// ---------------------------------------------------------------------------
// Test: Event sorting
// ---------------------------------------------------------------------------

#[test]
fn test_events_sorted_by_region_type_slot() {
    let config = default_config();

    // Create two regions that will both trigger events.
    let mut r0 = make_plains(0);
    r0.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r0.population = 50;
    r0.soil_pressure_streak = 29; // Will hit 30

    let mut r1 = make_plains(1);
    r1.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r1.resource_effective_yield = [0.001, 0.0, 0.0];
    r1.population = 50;
    r1.overextraction_streak = [34, 0, 0];

    let mut regions = vec![r0, r1];
    let pandemic = vec![false; 2];
    let army = vec![false; 2];

    let (_, events) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // Check events are sorted by (region_id, event_type, slot).
    for w in events.windows(2) {
        let ok = w[0].region_id < w[1].region_id
            || (w[0].region_id == w[1].region_id && w[0].event_type < w[1].event_type)
            || (w[0].region_id == w[1].region_id
                && w[0].event_type == w[1].event_type
                && w[0].slot <= w[1].slot);
        assert!(ok, "events not sorted: {:?} vs {:?}", w[0], w[1]);
    }
}

// ---------------------------------------------------------------------------
// Test: Multi-turn persistence
// ---------------------------------------------------------------------------

#[test]
fn test_multi_turn_streak_persistence() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r.population = 50; // Above soil_pressure_threshold
    r.soil_pressure_streak = 0;

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    // Run 5 turns.  Streak should increment each turn.
    for turn in 0..5_u32 {
        let (_, _) = tick_ecology(
            &mut regions, &config, turn, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
        );
    }

    assert_eq!(
        regions[0].soil_pressure_streak, 5,
        "streak should be 5 after 5 turns of pressure"
    );
}

// ---------------------------------------------------------------------------
// Test: Soil degradation multiplier from streak
// ---------------------------------------------------------------------------

#[test]
fn test_soil_degradation_mult_from_streak() {
    let config = default_config();

    // Region with streak at the limit — soil_mult should be 2.0
    let mut r_at_limit = make_plains(0);
    r_at_limit.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r_at_limit.population = 55; // Above eff_cap to trigger degradation
    r_at_limit.soil_pressure_streak = 30; // At limit
    r_at_limit.soil = 0.80;

    // Region with streak below limit — soil_mult should be 1.0
    let mut r_below = make_plains(1);
    r_below.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r_below.population = 55;
    r_below.soil_pressure_streak = 10;
    r_below.soil = 0.80;

    let mut regions_at = vec![r_at_limit];
    let mut regions_below = vec![r_below];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions_at, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );
    let (_, _) = tick_ecology(
        &mut regions_below, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // The at-limit region should have MORE soil degradation (2x multiplier).
    assert!(
        regions_at[0].soil < regions_below[0].soil,
        "at-limit soil {} should be lower than below-limit soil {} due to 2x degradation",
        regions_at[0].soil, regions_below[0].soil
    );
}

// ---------------------------------------------------------------------------
// Test: Agriculture focus soil bonus
// ---------------------------------------------------------------------------

#[test]
fn test_agriculture_focus_bonus() {
    let config = default_config();

    let mut r_agri = make_plains(0);
    r_agri.active_focus = 1; // AGRICULTURE
    r_agri.population = 20; // Low pop for recovery

    let mut r_none = make_plains(1);
    r_none.active_focus = 0; // NONE
    r_none.population = 20;

    let mut regions_agri = vec![r_agri];
    let mut regions_none = vec![r_none];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions_agri, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );
    let (_, _) = tick_ecology(
        &mut regions_none, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(
        regions_agri[0].soil > regions_none[0].soil,
        "agriculture focus soil {} should be > no-focus soil {}",
        regions_agri[0].soil, regions_none[0].soil
    );
}

// ---------------------------------------------------------------------------
// Test: Irrigation water bonus (non-drought)
// ---------------------------------------------------------------------------

#[test]
fn test_irrigation_bonus_temperate() {
    let config = default_config();

    let mut r_irrig = make_plains(0);
    r_irrig.has_irrigation = true;

    let mut r_none = make_plains(1);
    r_none.has_irrigation = false;

    let mut regions_irrig = vec![r_irrig];
    let mut regions_none = vec![r_none];
    let pandemic = vec![false];
    let army = vec![false];

    let (_, _) = tick_ecology(
        &mut regions_irrig, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );
    let (_, _) = tick_ecology(
        &mut regions_none, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(
        regions_irrig[0].water > regions_none[0].water,
        "irrigated water {} should be > non-irrigated {} in temperate",
        regions_irrig[0].water, regions_none[0].water
    );
}

// ---------------------------------------------------------------------------
// Determinism harness: verify exact output across 1/4/8/16 threads
// ---------------------------------------------------------------------------

/// Run tick_ecology on a clone of the given regions inside a rayon thread pool
/// with the specified number of threads, and return the resulting (regions, yields, events).
fn run_with_threads(
    regions: &[RegionState],
    config: &EcologyConfig,
    turn: u32,
    climate_phase: u8,
    pandemic: &[bool],
    army: &[bool],
    topo: &RiverTopology,
    num_threads: usize,
) -> (Vec<RegionState>, Vec<[f32; 3]>, Vec<EcologyEvent>) {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(num_threads)
        .build()
        .unwrap();

    let mut cloned = regions.to_vec();
    let (yields, events) = pool.install(|| {
        tick_ecology(&mut cloned, config, turn, climate_phase, pandemic, army, topo)
    });
    (cloned, yields, events)
}

/// Compare two sets of tick_ecology results for exact equality.
fn assert_results_equal(
    label: &str,
    a_regions: &[RegionState],
    a_yields: &[f32; 3],
    a_events: &[EcologyEvent],
    b_regions: &[RegionState],
    b_yields: &[f32; 3],
    b_events: &[EcologyEvent],
    region_count: usize,
) {
    // Compare events
    assert_eq!(
        a_events.len(),
        b_events.len(),
        "{}: event count mismatch",
        label
    );
    for (i, (ea, eb)) in a_events.iter().zip(b_events.iter()).enumerate() {
        assert_eq!(ea, eb, "{}: event {} mismatch", label, i);
    }

    // Compare yields (exact — no epsilon)
    for j in 0..3 {
        assert_eq!(
            a_yields[j].to_bits(),
            b_yields[j].to_bits(),
            "{}: yield slot {} mismatch: {} vs {}",
            label, j, a_yields[j], b_yields[j]
        );
    }

    // Compare region state
    for i in 0..region_count {
        let ra = &a_regions[i];
        let rb = &b_regions[i];
        assert_eq!(ra.soil.to_bits(), rb.soil.to_bits(), "{}: region {} soil mismatch", label, i);
        assert_eq!(ra.water.to_bits(), rb.water.to_bits(), "{}: region {} water mismatch", label, i);
        assert_eq!(ra.forest_cover.to_bits(), rb.forest_cover.to_bits(), "{}: region {} forest mismatch", label, i);
        assert_eq!(ra.endemic_severity.to_bits(), rb.endemic_severity.to_bits(), "{}: region {} severity mismatch", label, i);
        assert_eq!(ra.prev_turn_water.to_bits(), rb.prev_turn_water.to_bits(), "{}: region {} prev_water mismatch", label, i);
        assert_eq!(ra.soil_pressure_streak, rb.soil_pressure_streak, "{}: region {} soil streak mismatch", label, i);
        for s in 0..3 {
            assert_eq!(ra.overextraction_streak[s], rb.overextraction_streak[s], "{}: region {} overext streak[{}] mismatch", label, i, s);
            assert_eq!(ra.resource_reserves[s].to_bits(), rb.resource_reserves[s].to_bits(), "{}: region {} reserves[{}] mismatch", label, i, s);
            assert_eq!(ra.resource_effective_yield[s].to_bits(), rb.resource_effective_yield[s].to_bits(), "{}: region {} eff_yield[{}] mismatch", label, i, s);
            assert_eq!(ra.resource_yields[s].to_bits(), rb.resource_yields[s].to_bits(), "{}: region {} yields[{}] mismatch", label, i, s);
        }
    }
}

#[test]
fn test_determinism_across_thread_counts() {
    let config = default_config();

    // Build a varied scenario: 8 regions with mixed terrain/population/resources.
    let mut regions: Vec<RegionState> = Vec::new();

    let mut r0 = make_plains(0);
    r0.resource_types = [RT_GRAIN, RT_TIMBER, EMPTY_SLOT];
    r0.resource_base_yield = [1.0, 0.8, 0.0];
    r0.resource_effective_yield = [1.0, 0.8, 0.0];
    r0.forest_cover = 0.10; // Deforested — triggers river cascade
    regions.push(r0);

    let mut r1 = RegionState::new(1);
    r1.terrain = TERRAIN_MOUNTAINS;
    r1.soil = 0.40;
    r1.water = 0.80;
    r1.forest_cover = 0.30;
    r1.carrying_capacity = 40;
    r1.population = 20;
    r1.controller_civ = 1;
    r1.capacity_modifier = 1.0;
    r1.prev_turn_water = 0.80;
    r1.resource_types = [RT_ORE, RT_PRECIOUS, EMPTY_SLOT];
    r1.resource_base_yield = [1.0, 0.5, 0.0];
    r1.resource_effective_yield = [1.0, 0.5, 0.0];
    r1.resource_reserves = [0.50, 0.10, 1.0];
    r1.has_mines = true;
    regions.push(r1);

    let mut r2 = RegionState::new(2);
    r2.terrain = TERRAIN_DESERT;
    r2.soil = 0.20;
    r2.water = 0.10;
    r2.forest_cover = 0.05;
    r2.carrying_capacity = 20;
    r2.population = 15;
    r2.controller_civ = 0;
    r2.capacity_modifier = 1.0;
    r2.prev_turn_water = 0.10;
    r2.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r2.resource_base_yield = [0.5, 0.0, 0.0];
    r2.resource_effective_yield = [0.5, 0.0, 0.0];
    r2.disease_baseline = 0.03;
    r2.endemic_severity = 0.05;
    regions.push(r2);

    let r3 = make_uncontrolled(3);
    regions.push(r3);

    let mut r4 = RegionState::new(4);
    r4.terrain = TERRAIN_COAST;
    r4.soil = 0.70;
    r4.water = 0.80;
    r4.forest_cover = 0.30;
    r4.carrying_capacity = 50;
    r4.population = 25;
    r4.controller_civ = 2;
    r4.capacity_modifier = 1.0;
    r4.prev_turn_water = 0.80;
    r4.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r4.resource_base_yield = [0.8, 0.0, 0.0];
    r4.resource_effective_yield = [0.8, 0.0, 0.0];
    r4.has_irrigation = true;
    regions.push(r4);

    let mut r5 = RegionState::new(5);
    r5.terrain = TERRAIN_TUNDRA;
    r5.soil = 0.15;
    r5.water = 0.50;
    r5.forest_cover = 0.10;
    r5.carrying_capacity = 25;
    r5.population = 5;
    r5.controller_civ = 3;
    r5.capacity_modifier = 1.0;
    r5.prev_turn_water = 0.50;
    r5.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r5.resource_base_yield = [0.3, 0.0, 0.0];
    r5.resource_effective_yield = [0.3, 0.0, 0.0];
    regions.push(r5);

    let mut r6 = RegionState::new(6);
    r6.terrain = TERRAIN_FOREST;
    r6.soil = 0.70;
    r6.water = 0.70;
    r6.forest_cover = 0.80;
    r6.carrying_capacity = 50;
    r6.population = 10;
    r6.controller_civ = 0;
    r6.capacity_modifier = 1.0;
    r6.prev_turn_water = 0.70;
    r6.resource_types = [RT_TIMBER, EMPTY_SLOT, EMPTY_SLOT];
    r6.resource_base_yield = [1.2, 0.0, 0.0];
    r6.resource_effective_yield = [1.2, 0.0, 0.0];
    regions.push(r6);

    let r7 = make_uncontrolled(7);
    regions.push(r7);

    let pandemic = vec![false, false, false, false, false, false, false, false];
    let army = vec![false, true, false, false, false, false, false, false];

    let topo = RiverTopology {
        rivers: vec![vec![0, 1, 4]], // r0 deforested, cascade to r1 and r4
    };

    let thread_counts = [1, 4, 8, 16];
    let mut results: Vec<(Vec<RegionState>, Vec<[f32; 3]>, Vec<EcologyEvent>)> = Vec::new();

    for &threads in &thread_counts {
        let (regs, yields, events) = run_with_threads(
            &regions, &config, 5, CLIMATE_TEMPERATE, &pandemic, &army, &topo, threads,
        );
        results.push((regs, yields, events));
    }

    // Compare all thread counts against the 1-thread baseline.
    let (ref base_regs, ref base_yields, ref base_events) = results[0];
    for (idx, &threads) in thread_counts.iter().enumerate().skip(1) {
        let (ref regs, ref yields, ref events) = results[idx];
        for region_idx in 0..8 {
            assert_results_equal(
                &format!("1 vs {} threads, region {}", threads, region_idx),
                base_regs,
                &base_yields[region_idx],
                base_events,
                regs,
                &yields[region_idx],
                events,
                8,
            );
        }
    }
}

// ---------------------------------------------------------------------------
// Test: Empty region list
// ---------------------------------------------------------------------------

#[test]
fn test_empty_regions() {
    let config = default_config();
    let mut regions: Vec<RegionState> = vec![];
    let pandemic: Vec<bool> = vec![];
    let army: Vec<bool> = vec![];

    let (yields, events) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    assert!(yields.is_empty());
    assert!(events.is_empty());
}

// ---------------------------------------------------------------------------
// Schema tests (carried forward from Task 1)
// ---------------------------------------------------------------------------

#[test]
fn test_region_new_has_ecology_defaults() {
    let r = RegionState::new(0);
    assert!((r.disease_baseline - 0.0).abs() < f32::EPSILON);
    assert!((r.capacity_modifier - 1.0).abs() < f32::EPSILON);
    assert_eq!(r.resource_base_yield, [0.0, 0.0, 0.0]);
    assert_eq!(r.resource_effective_yield, [0.0, 0.0, 0.0]);
    assert_eq!(r.resource_suspension, [false, false, false]);
    assert!(!r.has_irrigation);
    assert!(!r.has_mines);
    assert_eq!(r.active_focus, 0);
    assert!((r.prev_turn_water - 0.0).abs() < f32::EPSILON);
    assert_eq!(r.soil_pressure_streak, 0);
    assert_eq!(r.overextraction_streak, [0, 0, 0]);
}

#[test]
fn test_region_ecology_fields_independent_from_legacy() {
    let r = RegionState::new(3);
    assert_eq!(r.resource_yields, [0.0, 0.0, 0.0]);
    assert_eq!(r.resource_base_yield, [0.0, 0.0, 0.0]);
    assert_eq!(r.resource_reserves, [1.0, 1.0, 1.0]);
    let mut r2 = r.clone();
    r2.resource_base_yield[0] = 2.5;
    assert_eq!(r2.resource_yields[0], 0.0);
    r2.resource_yields[1] = 1.0;
    assert_eq!(r2.resource_base_yield[1], 0.0);
}

#[test]
fn test_region_new_has_existing_endemic_severity_unchanged() {
    let r = RegionState::new(0);
    assert!((r.endemic_severity - 0.0).abs() < f32::EPSILON);
}

// ===========================================================================
// M54a Task 3: FFI ecology surface tests
// ===========================================================================

// ---------------------------------------------------------------------------
// Test: ecology_region_schema is stable
// ---------------------------------------------------------------------------

#[test]
fn test_ecology_region_schema_columns() {
    let schema = chronicler_agents::ffi_schemas::ecology_region_schema();
    let names: Vec<&str> = schema.fields().iter().map(|f| f.name().as_str()).collect();
    let expected = vec![
        "region_id",
        "soil", "water", "forest_cover",
        "endemic_severity", "prev_turn_water",
        "soil_pressure_streak",
        "overextraction_streak_0", "overextraction_streak_1", "overextraction_streak_2",
        "resource_reserve_0", "resource_reserve_1", "resource_reserve_2",
        "resource_effective_yield_0", "resource_effective_yield_1", "resource_effective_yield_2",
        "current_turn_yield_0", "current_turn_yield_1", "current_turn_yield_2",
    ];
    assert_eq!(names, expected, "ecology_region_schema column names should match spec");
    assert_eq!(schema.fields().len(), 19, "ecology_region_schema should have 19 columns");
}

#[test]
fn test_ecology_events_schema_columns() {
    let schema = chronicler_agents::ffi_schemas::ecology_events_schema();
    let names: Vec<&str> = schema.fields().iter().map(|f| f.name().as_str()).collect();
    assert_eq!(names, vec!["event_type", "region_id", "slot", "magnitude"]);
    assert_eq!(schema.fields().len(), 4);
}

// ---------------------------------------------------------------------------
// Test: compute_yields is callable (made pub in ecology.rs)
// ---------------------------------------------------------------------------

#[test]
fn test_compute_yields_public() {
    let config = EcologyConfig::default();
    let mut r = RegionState::new(0);
    r.terrain = TERRAIN_PLAINS;
    r.soil = 0.80;
    r.water = 0.60;
    r.forest_cover = 0.20;
    r.carrying_capacity = 60;
    r.population = 30;
    r.controller_civ = 0;
    r.capacity_modifier = 1.0;
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];

    let yields = compute_yields(&mut r, &config, 0, CLIMATE_TEMPERATE);
    assert!(yields[0] > 0.0, "grain yield should be > 0");
    assert!((yields[1] - 0.0).abs() < f32::EPSILON, "empty slot yield should be 0");
    assert!((yields[2] - 0.0).abs() < f32::EPSILON, "empty slot yield should be 0");
}

// ---------------------------------------------------------------------------
// Test: season_id_from_turn is public
// ---------------------------------------------------------------------------

#[test]
fn test_season_id_from_turn_public() {
    assert_eq!(season_id_from_turn(0), 0);
    assert_eq!(season_id_from_turn(3), 1);
    assert_eq!(season_id_from_turn(6), 2);
    assert_eq!(season_id_from_turn(9), 3);
    assert_eq!(season_id_from_turn(12), 0);
}

// ---------------------------------------------------------------------------
// Test: tick_ecology writes yields into resource_yields
// ---------------------------------------------------------------------------

#[test]
fn test_tick_ecology_writes_yields_to_resource_yields() {
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, RT_TIMBER, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.8, 0.0];
    r.resource_effective_yield = [1.0, 0.8, 0.0];
    r.resource_yields = [0.0, 0.0, 0.0]; // Start at zero

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (yields, _events) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // tick_ecology returns yields but does NOT write them to region.resource_yields
    // (that's the FFI layer's job). However yields should be non-zero.
    assert!(yields[0][0] > 0.0, "grain yield should be > 0");
    assert!(yields[0][1] > 0.0, "timber yield should be > 0");

    // The ecology core writes to resource_yields in compute_yields, so they
    // should be updated after tick.
    assert!(regions[0].resource_yields[0] > 0.0, "region resource_yields[0] should be updated");
    assert!(regions[0].resource_yields[1] > 0.0, "region resource_yields[1] should be updated");
}

// ---------------------------------------------------------------------------
// Test: patch detection of ecology-affecting fields
// ---------------------------------------------------------------------------

#[test]
fn test_patch_soil_change_detected_as_ecology_affecting() {
    // Verify the concept: if soil changes, yield recompute is needed.
    // Test via the ecology core: same region, different soil => different yields.
    let config = default_config();

    let mut r1 = make_plains(0);
    r1.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r1.resource_base_yield = [1.0, 0.0, 0.0];
    r1.resource_effective_yield = [1.0, 0.0, 0.0];
    r1.soil = 0.80;

    let mut r2 = r1.clone();
    r2.soil = 0.40; // Lower soil

    let y1 = compute_yields(&mut r1, &config, 0, CLIMATE_TEMPERATE);
    let y2 = compute_yields(&mut r2, &config, 0, CLIMATE_TEMPERATE);

    assert!(
        (y1[0] - y2[0]).abs() > 0.01,
        "different soil should produce different yields: y1={}, y2={}",
        y1[0], y2[0]
    );
}

// ---------------------------------------------------------------------------
// Test: population-only patch does NOT need yield recompute
// ---------------------------------------------------------------------------

#[test]
fn test_population_only_change_same_yields() {
    let config = default_config();

    let mut r1 = make_plains(0);
    r1.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r1.resource_base_yield = [1.0, 0.0, 0.0];
    r1.resource_effective_yield = [1.0, 0.0, 0.0];
    r1.population = 30;

    let mut r2 = r1.clone();
    r2.population = 50; // Different population, same ecology fields

    let y1 = compute_yields(&mut r1, &config, 0, CLIMATE_TEMPERATE);
    let y2 = compute_yields(&mut r2, &config, 0, CLIMATE_TEMPERATE);

    // compute_yields does NOT depend on population directly (only through
    // depletion mechanics which are separate), so yields should be identical.
    assert!(
        (y1[0] - y2[0]).abs() < f32::EPSILON,
        "same ecology fields should produce same yields regardless of population: y1={}, y2={}",
        y1[0], y2[0]
    );
}

// ===========================================================================
// M54a Task 5: Additional determinism and parity tests
// ===========================================================================

// ---------------------------------------------------------------------------
// Test: Exact current_turn_yields values for known inputs
// ---------------------------------------------------------------------------

#[test]
fn test_exact_current_turn_yields_grain_spring() {
    // Verify exact yield for GRAIN at spring with known ecology state.
    // base=1.0, season_mod=0.8 (spring grain), climate_mod=1.0 (temperate crop),
    // ecology_mod = soil * water = 0.80 * 0.60 = 0.48
    // yield = 1.0 * 0.8 * 1.0 * 0.48 * 1.0 = 0.384
    //
    // BUT: tick_ecology modifies soil/water BEFORE computing yields.
    // So we must run through tick_ecology to get the actual value.
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (yields, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // After ecology tick: soil recovered, water recovered.
    // Compute expected from post-tick values.
    let post_soil = regions[0].soil;
    let post_water = regions[0].water;
    let expected_ecology_mod = post_soil * post_water;
    let expected_yield = 1.0 * 0.8 * 1.0 * expected_ecology_mod * 1.0;

    assert!(
        (yields[0][0] - expected_yield).abs() < 0.0001,
        "grain yield {} expected {} (soil={}, water={})",
        yields[0][0], expected_yield, post_soil, post_water
    );

    // Also verify the yield is stored in region.resource_yields
    assert_eq!(
        regions[0].resource_yields[0].to_bits(),
        yields[0][0].to_bits(),
        "resource_yields[0] should exactly match returned yield"
    );
}

#[test]
fn test_exact_current_turn_yields_multi_slot() {
    // Verify yields for a region with GRAIN + TIMBER + ORE
    let config = default_config();
    let mut r = RegionState::new(0);
    r.terrain = TERRAIN_FOREST;
    r.soil = 0.70;
    r.water = 0.70;
    r.forest_cover = 0.80;
    r.carrying_capacity = 50;
    r.population = 10;
    r.controller_civ = 0;
    r.capacity_modifier = 1.0;
    r.prev_turn_water = 0.70;
    r.resource_types = [RT_GRAIN, RT_TIMBER, RT_ORE];
    r.resource_base_yield = [1.0, 1.0, 1.0];
    r.resource_effective_yield = [1.0, 1.0, 1.0];
    r.resource_reserves = [1.0, 1.0, 0.50]; // ORE partially depleted

    let mut regions = vec![r];
    let pandemic = vec![false];
    let army = vec![false];

    let (yields, _) = tick_ecology(
        &mut regions, &config, 0, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
    );

    // All three slots should produce non-zero yields
    assert!(yields[0][0] > 0.0, "grain yield should be > 0, got {}", yields[0][0]);
    assert!(yields[0][1] > 0.0, "timber yield should be > 0, got {}", yields[0][1]);
    assert!(yields[0][2] > 0.0, "ore yield should be > 0, got {}", yields[0][2]);

    // ORE yield should be affected by reserve ramp
    // Reserves started at 0.50 but depletion may have reduced them
    let ore_reserves = regions[0].resource_reserves[2];
    assert!(ore_reserves <= 0.50, "ore reserves should have decreased or stayed");

    // Grain ecology_mod = soil * water (crop class)
    // Timber ecology_mod = forest_cover (forestry class)
    // ORE ecology_mod = 1.0 (mineral class) but with reserve_ramp
    // Timber should be higher than grain (forest terrain has higher forest_cover effect)
    // This is a sanity check — not exact equality
}

// ---------------------------------------------------------------------------
// Test: Multi-turn determinism (10 turns, same seed = same output)
// ---------------------------------------------------------------------------

#[test]
fn test_multi_turn_determinism_10_turns() {
    let config = default_config();
    let initial = vec![
        make_plains(0),
        {
            let mut r = make_plains(1);
            r.terrain = TERRAIN_DESERT;
            r.soil = 0.20;
            r.water = 0.15;
            r.forest_cover = 0.05;
            r.carrying_capacity = 20;
            r.population = 15;
            r
        },
        make_uncontrolled(2),
    ];
    let pandemic = vec![false; 3];
    let army = vec![false; 3];

    // Run A
    let mut regions_a = initial.clone();
    let mut all_yields_a: Vec<Vec<[f32; 3]>> = Vec::new();
    let mut all_events_a: Vec<Vec<EcologyEvent>> = Vec::new();
    for turn in 0..10_u32 {
        let (y, e) = tick_ecology(
            &mut regions_a, &config, turn, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
        );
        all_yields_a.push(y);
        all_events_a.push(e);
    }

    // Run B (identical)
    let mut regions_b = initial.clone();
    let mut all_yields_b: Vec<Vec<[f32; 3]>> = Vec::new();
    let mut all_events_b: Vec<Vec<EcologyEvent>> = Vec::new();
    for turn in 0..10_u32 {
        let (y, e) = tick_ecology(
            &mut regions_b, &config, turn, CLIMATE_TEMPERATE, &pandemic, &army, &empty_river(),
        );
        all_yields_b.push(y);
        all_events_b.push(e);
    }

    // Exact equality at every turn
    for turn in 0..10 {
        assert_eq!(
            all_events_a[turn].len(), all_events_b[turn].len(),
            "turn {}: event count mismatch", turn
        );
        for i in 0..all_events_a[turn].len() {
            assert_eq!(all_events_a[turn][i], all_events_b[turn][i], "turn {}: event {} mismatch", turn, i);
        }
        for rid in 0..3 {
            for slot in 0..3 {
                assert_eq!(
                    all_yields_a[turn][rid][slot].to_bits(),
                    all_yields_b[turn][rid][slot].to_bits(),
                    "turn {}: region {} yield slot {} mismatch",
                    turn, rid, slot
                );
            }
        }
    }

    // Final region state must match exactly
    for i in 0..3 {
        assert_eq!(regions_a[i].soil.to_bits(), regions_b[i].soil.to_bits(), "region {} soil", i);
        assert_eq!(regions_a[i].water.to_bits(), regions_b[i].water.to_bits(), "region {} water", i);
        assert_eq!(regions_a[i].forest_cover.to_bits(), regions_b[i].forest_cover.to_bits(), "region {} forest", i);
        assert_eq!(regions_a[i].endemic_severity.to_bits(), regions_b[i].endemic_severity.to_bits(), "region {} severity", i);
        assert_eq!(regions_a[i].soil_pressure_streak, regions_b[i].soil_pressure_streak, "region {} streak", i);
        for s in 0..3 {
            assert_eq!(regions_a[i].resource_reserves[s].to_bits(), regions_b[i].resource_reserves[s].to_bits(), "region {} reserves[{}]", i, s);
            assert_eq!(regions_a[i].resource_effective_yield[s].to_bits(), regions_b[i].resource_effective_yield[s].to_bits(), "region {} eff_yield[{}]", i, s);
        }
    }
}

// ---------------------------------------------------------------------------
// Test: Patched-yield recompute behavior
// ---------------------------------------------------------------------------

#[test]
fn test_patched_yield_recompute_after_soil_change() {
    // After a post-pass patch that changes soil, the yields should be different
    // from what they were before the patch.
    let config = default_config();
    let mut r = make_plains(0);
    r.resource_types = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];
    r.soil = 0.80;
    r.water = 0.60;

    // Compute yields at current state
    let mut r_pre = r.clone();
    let y_pre = compute_yields(&mut r_pre, &config, 0, CLIMATE_TEMPERATE);

    // Simulate post-pass: soil changed by famine/tradition effects
    r.soil = 0.40;
    let mut r_post = r.clone();
    let y_post = compute_yields(&mut r_post, &config, 0, CLIMATE_TEMPERATE);

    // Yields must differ because ecology_mod changed
    assert!(
        (y_pre[0] - y_post[0]).abs() > 0.01,
        "yield before patch {} should differ from after patch {} (soil changed)",
        y_pre[0], y_post[0]
    );

    // Post yield should be lower (lower soil)
    assert!(
        y_post[0] < y_pre[0],
        "lower soil should produce lower yield: pre={}, post={}",
        y_pre[0], y_post[0]
    );
}
